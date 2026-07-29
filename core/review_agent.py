"""시각 검수 2층 자동화 — headless Claude(검수 에이전트)를 조판 후 자동 실행 (W41).

1층(core.visual_inspect)은 기계 검사(오버셋/지오메트리/픽셀)까지, 2층은
사람 눈 대행(.claude/skills/visual-review 체크리스트)인데 지금까지는
사람이 스킬을 수동 실행해야 했다. 이 모듈은 verify 완료 후 파이프라인
훅(opt-in)에서 `claude -p`(비대화 headless)를 subprocess로 호출해 2층을
자동화한다.

채택 방식 (2026-07-21 실측 — 대안 Agent SDK 대비 선택 근거):
  - 이 기기에 Claude Code CLI 2.1.197 설치·인증(keychain OAuth) 완료 —
    `env -i HOME PATH=/usr/bin:/bin` 최소 환경(launchd 근사)에서도 인증·
    PNG 비전 Read·`--json-schema` 구조화 출력 모두 동작 확인.
  - Agent SDK(python)는 별도 의존성 + 같은 CLI를 내부 호출 — subprocess가
    가장 단순·견고 (requirements 무변경, 버전은 CLI가 자체 관리).
  - 실측 비용/시간: sonnet 페이지 1장 검수 14.8s / $0.29 (시스템 프롬프트
    캐시 생성 41k tok 포함), 표본 8~10장 검수는 약 2~5분 / $0.5~1.5 수준.
    → --max-budget-usd 상한 + subprocess 타임아웃으로 이중 방어.

판정 분류 (findings[].judgement):
  auto_fixable       조판 실행 유래(잔존 템플릿/부분 산출 등) — 결정론적
                     재조판으로 해소 기대. UI가 "재조판" 버튼을 제안하고
                     실제 재실행은 사용자 클릭(/api/rerun) — 무단 재조판 금지.
  manuscript_error   원고 유래(번호 소실/내용 오류/오탈자) — 사용자가 원고를
                     고쳐야 함. 오류 리스트로 UI 표시.
  operator_judgment  의도인지 결함인지 이미지로 확정 불가 — 운영자 확인 필요.

철학: 전부 fail-open — 에이전트가 죽어도(미설치/타임아웃/예산 초과) 조판
결과 전달은 정상. 판정은 advisory — result["ok"]를 바꾸지 않고 warnings로만
합류. 호출부는 core/pipeline.py의 YONE_REVIEW_AGENT 훅.
"""
import json
import os
import random
import re
import shutil
import subprocess
import time

# ── 설정 (환경변수로 조정) ────────────────────────────────────────────────────
DEFAULT_MODEL = "sonnet"          # YONE_REVIEW_AGENT_MODEL
DEFAULT_TIMEOUT = 600             # 초, YONE_REVIEW_AGENT_TIMEOUT
DEFAULT_BUDGET_USD = "2.0"        # YONE_REVIEW_AGENT_BUDGET_USD
DEFAULT_MAX_PAGES = 10            # YONE_REVIEW_AGENT_MAX_PAGES (표본 페이지 상한)
DEFAULT_DPI = 120                 # YONE_REVIEW_AGENT_DPI (눈으로 읽을 해상도)
RANDOM_SAMPLE = 3                 # 무작위 표본 수 (플래그 외)

REPORT_FILENAME = "review_result.json"
INPUT_FILENAME = "review_input.json"

# 구조화 출력 스키마 (claude -p --json-schema) — UI/파이프라인이 소비하는 계약.
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "suspect", "fail"]},
        "pages_reviewed": {"type": "array", "items": {"type": "integer"}},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "check": {"type": "string"},
                    "page": {"type": "integer"},
                    "grade": {"type": "string",
                              "enum": ["fail", "suspect", "info"]},
                    "detail": {"type": "string"},
                    "evidence_png": {"type": "string"},
                    "judgement": {"type": "string",
                                  "enum": ["auto_fixable", "manuscript_error",
                                           "operator_judgment"]},
                    "suggestion": {"type": "string"},
                },
                "required": ["type", "page", "grade", "detail", "judgement"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["verdict", "pages_reviewed", "findings", "notes"],
}

# visual-review 스킬 로드 실패 시 폴백 체크리스트 (스킬과 동일 항목 요약).
_FALLBACK_CHECKLIST = """\
| C1 | 텍스트 잘림 | 프레임 끝에서 문장이 중간에 끊김, 마지막 줄 반토막 |
| C2 | 프레임 겹침/어긋남 | 본문·발문·박스가 서로 침범, 정렬 불일치 |
| C3 | 번호 연속성 | 문항/지문 번호 순서, 중복·건너뜀 |
| C4 | 스타일 일관성 | 같은 역할의 글꼴·크기·배경이 페이지 간 동일한가 |
| C5 | 여백/빈 공간 | 비정상 공백, 반쯤 빈 페이지, 여백 침범 |
| C6 | 간지/머리말 | 간지 제목·머리말·쪽번호가 단원과 일치 |
| C7 | 이미지/아이콘 | 깨짐, 저해상, placeholder, 어긋난 인라인 아이콘 |
| C8 | 좌/우 마스터 | 좌우 페이지 여백 방향·단 구성 |"""


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_checklist():
    """visual-review 스킬의 체크리스트 표를 재사용 (실패 시 폴백)."""
    path = os.path.join(_repo_root(), ".claude", "skills", "visual-review",
                        "SKILL.md")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"### 체크리스트.*?(?=\n### )", src, re.S)
        if m:
            return m.group(0).strip()
    except OSError:
        pass
    return _FALLBACK_CHECKLIST


def find_claude_bin():
    """claude CLI 경로 — launchd-spawn Flask는 PATH에 ~/.local/bin이 없음."""
    env_bin = os.environ.get("YONE_CLAUDE_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin
    p = shutil.which("claude")
    if p:
        return p
    for cand in (os.path.expanduser("~/.local/bin/claude"),
                 "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if os.path.isfile(cand):
            return cand
    return None


# ── 표본 큐 구성 (scripts/visual_review.py 큐 의미론 준용 + 상한) ─────────────

def build_queue(report, max_pages=DEFAULT_MAX_PAGES, sample=RANDOM_SAMPLE,
                seed=0):
    """1층 리포트 → 검수 대상 페이지 목록 (우선순위: critical > review >
    고정 표본(첫/가운데/끝) > 무작위 표본, max_pages로 절단)."""
    n = report.get("page_count", 0)
    if n <= 0:
        return []
    by_level = {"critical": [], "review": []}
    for rec in report.get("pages", []):
        levels = {f["level"] for f in rec.get("flags", [])}
        if "critical" in levels:
            by_level["critical"].append(rec["page"])
        elif "review" in levels:
            by_level["review"].append(rec["page"])
    fixed = [1, max(1, n // 2), n]
    taken = []
    flagged = set(by_level["critical"]) | set(by_level["review"])
    rng = random.Random(seed)
    rest = [p for p in range(1, n + 1)
            if p not in flagged and p not in set(fixed)]
    randoms = sorted(rng.sample(rest, min(sample, len(rest))))
    for group in (by_level["critical"], by_level["review"], fixed, randoms):
        for p in group:
            if p not in taken:
                taken.append(p)
            if len(taken) >= max_pages:
                break
        if len(taken) >= max_pages:
            break

    page_by_num = {rec["page"]: rec for rec in report.get("pages", [])}
    queue = []
    for p in sorted(taken):
        rec = page_by_num.get(p, {})
        reasons = [f"{f['code']}({f['level']}): {f['detail']}"
                   for f in rec.get("flags", [])
                   if f.get("level") in ("critical", "review")]
        if not reasons:
            reasons = ["고정 표본" if p in fixed else "무작위 표본"]
        queue.append({"page": p, "reasons": reasons})
    return queue


def _render_queue_pages(pdf_path, pages, out_dir, dpi, log):
    """큐 페이지만 선별 렌더 (pdftoppm -f/-l 페이지 단위, 폴백 pypdfium2).

    1층 visual_pages는 72dpi(기계 검사용)라 본문 글자 판독이 어렵다 —
    2층은 눈으로 읽어야 하므로 필요한 페이지만 고해상도로 다시 렌더.
    반환 {page: png_path}. 실패 페이지는 제외 (부분 성공 허용).
    """
    from core.visual_inspect import _pdftoppm_bin
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    bin_ = _pdftoppm_bin()
    for p in pages:
        dst = os.path.join(out_dir, f"page-{p:04d}.png")
        if os.path.isfile(dst):
            out[p] = dst
            continue
        ok = False
        if bin_:
            prefix = os.path.join(out_dir, f"pg{p:04d}")
            try:
                cp = subprocess.run(
                    [bin_, "-png", "-r", str(dpi), "-f", str(p), "-l", str(p),
                     pdf_path, prefix],
                    capture_output=True, text=True, timeout=120)
                if cp.returncode == 0:
                    made = sorted(
                        os.path.join(out_dir, f) for f in os.listdir(out_dir)
                        if f.startswith(f"pg{p:04d}") and f.endswith(".png"))
                    if made:
                        os.replace(made[0], dst)
                        for extra in made[1:]:
                            os.remove(extra)
                        out[p] = dst
                        ok = True
            except (OSError, subprocess.SubprocessError):
                pass
        if not ok:
            try:
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(pdf_path)
                try:
                    bmp = doc[p - 1].render(scale=dpi / 72.0)
                    bmp.to_pil().save(dst)
                    out[p] = dst
                finally:
                    doc.close()
            except Exception as e:   # 부분 실패 허용 — 남은 페이지 계속
                if log:
                    log(f"[AI검수] p{p} 렌더 실패 (건너뜀): {e}")
    return out


# ── 프롬프트/호출 ─────────────────────────────────────────────────────────────

def build_prompt(input_rel_path=INPUT_FILENAME):
    checklist = _load_checklist()
    return f"""너는 영어 교재 조판 산출물의 시각 검수자다 (사람 눈 대행).
현재 폴더는 조판 job 폴더이고, `{input_rel_path}` 에 검수 입력이 있다:
- `layer1`: 1층 기계 검사 요약 (critical/review 플래그)
- `verify`: 조판 검수 게이트 결과 요약 (오버플로우/경고)
- `queue`: 검수할 페이지 목록 — 각 항목의 `png` 이미지 경로와 플래그 사유

절차:
1. `{input_rel_path}` 를 Read로 읽는다.
2. queue의 각 페이지 PNG를 Read로 **직접 열어** 아래 체크리스트로 본다.
   플래그 사유가 있는 페이지는 그 사유가 실제 결함인지 이미지로 확인한다.
3. 발견 항목마다 판정(judgement)을 분류한다:
   - auto_fixable: 원고 내용은 정상인데 조판 실행 과정 유래로 보이는 결함
     (잔존 템플릿 페이지, 부분 산출, 스타일 미적용 잔재 등) — 같은 원고로
     재조판하면 해소될 가능성이 높은 것만. suggestion에 "재조판"이라고 쓴다.
   - manuscript_error: 원고 유래 결함 (문항 번호 소실/중복, 내용 누락·오탈자,
     발문-지문 불일치 등) — 재조판으로는 해소되지 않고 원고 수정이 필요한 것.
   - operator_judgment: 의도인지 결함인지 이미지만으로 확정 불가한 것.
4. 확신 없는 항목은 grade를 suspect로 낮춰라 — 추측으로 fail 판정 금지.
   1층 리포트만 보고 판정하지 말 것: 반드시 이미지를 연 페이지만
   pages_reviewed에 넣고, 그 근거로만 findings를 쓴다.

{checklist}

판정 등급: fail(인쇄 불가 결함) / suspect(사람 확인 필요) / info(참고).
verdict는 findings 최고 등급을 따른다 (fail > suspect > pass).
findings[].evidence_png 에는 근거 이미지 경로(queue의 png 값)를 넣는다.
findings는 페이지·체크 항목·증거를 특정해서 쓴다 ("이상해 보임" 금지).
구조화 출력(JSON 스키마)으로만 답하라."""


def _summarize_verify(result):
    """verify 결과에서 에이전트에게 유용한 부분만 추출 (대형 필드 제외)."""
    if not isinstance(result, dict):
        return {}
    out = {}
    for k in ("ok", "overflow", "warnings", "stories"):
        if k in result:
            out[k] = result[k]
    ins = result.get("inspect")
    if isinstance(ins, dict):
        out["inspect"] = {k: ins.get(k) for k in
                          ("ok", "missing_words", "missing_sample",
                           "overflow_stories") if k in ins}
    return out


def invoke_claude(prompt, job_dir, log, model=None, timeout=None, budget=None):
    """claude -p 호출 → (structured dict|None, meta dict). 예외는 위로 던진다."""
    bin_ = find_claude_bin()
    if not bin_:
        raise RuntimeError("claude CLI를 찾을 수 없음 (YONE_CLAUDE_BIN 설정 가능)")
    model = model or os.environ.get("YONE_REVIEW_AGENT_MODEL", DEFAULT_MODEL)
    timeout = timeout or int(os.environ.get("YONE_REVIEW_AGENT_TIMEOUT",
                                            DEFAULT_TIMEOUT))
    budget = budget or os.environ.get("YONE_REVIEW_AGENT_BUDGET_USD",
                                      DEFAULT_BUDGET_USD)
    cmd = [
        bin_, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--json-schema", json.dumps(REVIEW_SCHEMA, ensure_ascii=False),
        # 읽기 전용 — 도구 집합 자체를 Read/Glob/Grep으로 제한 (이중 방어).
        "--tools", "Read,Glob,Grep",
        "--allowedTools", "Read,Glob,Grep",
        "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Task",
        "--permission-mode", "default",
        "--no-session-persistence",
        "--max-budget-usd", str(budget),
    ]
    env = dict(os.environ)
    # launchd 최소 PATH 보강 (claude 내부에서 node 등 호출)
    env["PATH"] = os.pathsep.join(
        [os.path.dirname(bin_), env.get("PATH", ""), "/usr/bin", "/bin"])
    t0 = time.time()
    cp = subprocess.run(cmd, cwd=job_dir, env=env, timeout=timeout,
                        stdin=subprocess.DEVNULL, capture_output=True,
                        text=True)
    wall_s = round(time.time() - t0, 1)
    if cp.returncode != 0:
        tail = (cp.stderr or cp.stdout or "")[-500:]
        raise RuntimeError(f"claude 종료코드 {cp.returncode}: {tail}")
    try:
        obj = json.loads(cp.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"claude 출력 JSON 파싱 실패: {cp.stdout[-300:]}")
    meta = {
        "wall_s": wall_s,
        "cost_usd": obj.get("total_cost_usd"),
        "duration_ms": obj.get("duration_ms"),
        "num_turns": obj.get("num_turns"),
        "model": model,
        "is_error": obj.get("is_error", False),
    }
    structured = obj.get("structured_output")
    if structured is None:
        # 폴백: result 텍스트에서 JSON 추출 (코드펜스 허용)
        txt = obj.get("result") or ""
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                structured = json.loads(m.group(0))
            except ValueError:
                structured = None
    return structured, meta


# ── job 레벨 진입점 (파이프라인 훅) ──────────────────────────────────────────

def _write_error_report(job_dir, exc, queue):
    """검수 에이전트 실행/파싱 실패를 review_result.json에 영속화 (진단용).

    침묵 실패 금지 — review_input.json은 있는데 review_result.json이 없는
    '원인 미상' 상태를 없앤다. verdict="error"이므로 UI/파이프라인은 정상
    판정과 구분해 처리하고, 판정 자체는 여전히 advisory(ok 무영향)다."""
    try:
        report = {
            "reviewer": "claude-review-agent",
            "date": time.strftime("%Y-%m-%d"),
            "verdict": "error",
            "error": str(exc)[:800],
            "error_type": type(exc).__name__,
            "pages_reviewed": [],
            "findings": [],
            "notes": ("검수 에이전트 실행 실패 — review_input.json은 생성됐으나 "
                      "headless 검수 호출/파싱 단계에서 예외. 원인은 error 필드 "
                      "참조 (인증/타임아웃/예산/CLI 부재 등)."),
            "queue_pages": [q.get("page") for q in queue],
        }
        with open(os.path.join(job_dir, REPORT_FILENAME), "w",
                  encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def run_review_agent(job_dir, log, result=None):
    """조판 job 산출물에 대해 검수 에이전트 실행 → review_result.json.

    반환: 요약 dict (verdict/counts/findings/report_path/cost) 또는
    None(대상 없음 — PDF/1층 리포트 부재). 예외는 위로 던진다(호출부 fail-open).
    """
    job_dir = os.path.abspath(job_dir)

    # 1층 리포트 확보 — 없으면 즉석 실행 (PDF 없는 흐름은 None → 스킵.
    # InDesign 재기동을 강제하지 않는다: allow_indesign=False)
    report = None
    report_path = os.path.join(job_dir, "visual_report.json")
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    else:
        from core.visual_inspect import inspect_job_visual
        report = inspect_job_visual(job_dir, log, result=result)
    if not report:
        if log:
            log("[AI검수] 대상 없음 (PDF/시각 리포트 부재) — 건너뜀")
        return None

    max_pages = int(os.environ.get("YONE_REVIEW_AGENT_MAX_PAGES",
                                   DEFAULT_MAX_PAGES))
    dpi = int(os.environ.get("YONE_REVIEW_AGENT_DPI", DEFAULT_DPI))
    queue = build_queue(report, max_pages=max_pages)
    if not queue:
        if log:
            log("[AI검수] 검수할 페이지 없음 — 건너뜀")
        return None

    # 표본 페이지 고해상도 렌더 (PDF 소스일 때). indd 렌더(1층 PNG)면 재사용.
    src = report.get("source", "")
    pages_needed = [q["page"] for q in queue]
    png_by_page = {}
    if src.lower().endswith(".pdf") and os.path.isfile(src):
        png_by_page = _render_queue_pages(
            src, pages_needed, os.path.join(job_dir, "review_pages"), dpi, log)
    if not png_by_page:   # 폴백: 1층 렌더 산출(visual_pages) 재사용
        for rec in report.get("pages", []):
            if rec["page"] in pages_needed and os.path.isfile(rec.get("png", "")):
                png_by_page[rec["page"]] = rec["png"]
    queue = [dict(q, png=os.path.relpath(png_by_page[q["page"]], job_dir))
             for q in queue if q["page"] in png_by_page]
    if not queue:
        if log:
            log("[AI검수] 표본 페이지 렌더 실패 — 건너뜀")
        return None

    # 검수 입력 파일 (에이전트가 Read로 소비)
    doc_flags = [f"{f['code']}({f['level']}): {f['detail']}"
                 for f in report.get("doc_flags", [])]
    review_input = {
        "source": src,
        "page_count": report.get("page_count"),
        "layer1": {"critical": report["summary"]["critical"],
                   "review": report["summary"]["review"],
                   "flagged_pages": report["summary"]["flagged_pages"],
                   "doc_flags": doc_flags},
        "verify": _summarize_verify(result),
        "queue": queue,
    }
    with open(os.path.join(job_dir, INPUT_FILENAME), "w",
              encoding="utf-8") as f:
        json.dump(review_input, f, ensure_ascii=False, indent=1)

    if log:
        log(f"[AI검수] 검수 에이전트 실행 — 표본 {len(queue)}페이지 "
            f"({[q['page'] for q in queue]})")
    # W49 (실서비스 0e3e6469 실증 — 침묵 실패 금지): invoke/파싱 실패는 지금까지
    # 파이프라인 훅이 로그(휘발성 SSE)만 남기고 삼켜서, review_input.json은
    # 있는데 review_result.json이 없는 '진단 불가' 상태가 됐다. 실패해도 반드시
    # review_result.json(verdict="error")을 남겨 사후 원인 규명이 가능하게 한다
    # (fail-open은 유지 — 여전히 위로 rethrow해 조판 결과 전달은 정상).
    try:
        structured, meta = invoke_claude(build_prompt(), job_dir, log)
        if not structured:
            raise RuntimeError(f"검수 에이전트 구조화 출력 없음 (meta={meta})")
    except Exception as exc:                                    # noqa: BLE001
        _write_error_report(job_dir, exc, queue)
        raise

    findings = structured.get("findings") or []
    counts = {"auto_fixable": 0, "manuscript_error": 0, "operator_judgment": 0}
    for fd in findings:
        j = fd.get("judgement")
        if j in counts:
            counts[j] += 1
    report_out = {
        "reviewer": "claude-review-agent",
        "date": time.strftime("%Y-%m-%d"),
        "source": src,
        "verdict": structured.get("verdict"),
        "pages_reviewed": structured.get("pages_reviewed") or [],
        "findings": findings,
        "notes": structured.get("notes") or "",
        "counts": counts,
        "meta": meta,
    }
    out_path = os.path.join(job_dir, REPORT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_out, f, ensure_ascii=False, indent=1)

    if log:
        log(f"[AI검수] 판정 {report_out['verdict']} — 발견 {len(findings)}건 "
            f"(자동수정가능 {counts['auto_fixable']}, "
            f"원고오류 {counts['manuscript_error']}, "
            f"운영판단 {counts['operator_judgment']}) "
            f"/ {meta.get('wall_s')}s, ${meta.get('cost_usd') or '?'}")
    return {
        "verdict": report_out["verdict"],
        "counts": counts,
        "findings": findings,
        "pages_reviewed": report_out["pages_reviewed"],
        "notes": report_out["notes"],
        "report_path": out_path,
        "cost_usd": meta.get("cost_usd"),
        "wall_s": meta.get("wall_s"),
    }
