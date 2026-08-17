"""배N제 v2 엔진 — 새 아키텍처 운영 래퍼 (seseospecial_v2/whitebook_v2 패턴).

파이프라인: 구조 인식 파서(engines/baenje_v2/parser.py — 원고 → content.json)
→ bj-flows 렌더 플랜(plan.py, 스타일 결정은 core/structure/style_map.json)
→ core/jsx/baenje_flow.body.jsx(실행만) → 검수 게이트 내장.

v1(engines/baenje) 무변경. 출력 파일명 `_v2` 접미로 공존. 템플릿/출력 경로는
v1의 engines/baenje/config.json을 공유한다.

v1 대비 달라진 점
- v1은 원고를 RTF로 바꿔 InDesign에 던지고 단락 종류 판정을 run.jsx 상태머신이
  했다. RTF 경유가 사라져 원고 텍스트가 변형 없이 그대로 조판되고, 검수에서
  플랜 ↔ 완제품 1:1 대조가 가능하다.
- v1 verify는 조판 로그의 숫자만 정규식으로 읽었다(오버플로우/PDF 존재).
  v2는 완제품 .indd를 다시 열어(core.inspect.dump_indd) 원고 원본 단어셋과
  대조하고, 배N제 고유 불변식 6종을 게이트로 판정한다.

검수 게이트
  B1 내용 보존   — 원고 원본 재추출 단어셋 − 완제품 단어셋 ≠ ∅ → 실패
  B2 번호 연속   — 본문/정답지 문항 번호가 1..N 연속이 아니면 실패
  B3 블록 유지   — 정답지 한 문항 블록이 펼침면을 넘으면 실패
  B4 러닝헤드    — 유닛 수만큼 머리말 소스가 페이지에 걸리지 않으면 실패
  B5 오버플로우  — 본문/정답지 오버플로우 > 0이면 실패(위치 지목)
  B6 스타일/마스터 부재 — 실행기가 [경고]로 남긴 것이 있으면 실패
  B7 발문 단락 수 = 문항 수 — 선지 레이아웃이 발문을 삼키면 실패
  B8 플랜 ↔ 완제품 텍스트 대조 — 누락·병합·순서 뒤바뀜 감지
  B9 출력물 불변식 — 답란이 지문 스타일/재작성 단락 서식 불균일/크레딧
"""
import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "baenje", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "baenje_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")

# 업로드 파일명에서 유닛(과) 라벨을 유도할 때 쓰는 힌트
_RE_LESSON = re.compile(r"(\d+)\s*과")


def _norm_typo(s):
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["indd_output_dir", "indd_original"])


class BaenjeV2Engine(BaseEngine):

    jsx_timeout = 1500

    @property
    def material_id(self):
        return "baenje_v2"

    @property
    def display_name(self):
        return "배N제 v2 (베타)"

    @property
    def description(self):
        return "프리미엄북 배N제 조판 v2 — 구조 인식 파서 + 데이터 플랜 + 자동 검수"

    @property
    def subject_prefix(self):
        return "배N제"

    @property
    def upload_spec(self):
        # v1은 원고 1 + 정답지 1. v2는 과(유닛)별 분리 원고를 그대로 받는다.
        return {
            "slots": [
                {"key": "manuscript", "label": "문제 원고 (.docx/.hwpx, 여러 개)",
                 "required": True, "multiple": True},
                {"key": "answers", "label": "해설 원고 (.docx/.hwpx, 여러 개)",
                 "required": False, "multiple": True},
            ]
        }

    def _get_meta(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p, encoding="utf-8").read().strip() \
            if os.path.exists(p) else default

    # ── 1단계: parse — 구조 인식 ───────────────────────────────────────────

    @staticmethod
    def _as_list(v):
        if not v:
            return []
        return list(v) if isinstance(v, (list, tuple)) else [v]

    def _unit_labels(self, job_dir, problem_files, log):
        """유닛(머리말) 라벨 — meta의 unit_labels.json 우선, 없으면 원고에서 유도.

        unit_labels.json: [{"start_q": 1, "text": "영어Ⅱ YBM(박) Lesson 1"}, ...]
        """
        p = os.path.join(job_dir, "unit_labels.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        # 폴백: 문제 원고 파일 순서대로 유닛 1개씩, 라벨은 파일명의 'N과'
        from engines.baenje_v2.parser import _extract, RE_QNUM
        subject = _nfc(self._get_meta(job_dir, "subject", ""))
        labels, seen_first = [], None
        for path in problem_files:
            rows = _extract(path)
            first = None
            for r in rows:
                m = RE_QNUM.match(r["text"].strip())
                if m:
                    first = int(m.group(1))
                    break
            if first is None:
                continue
            # macOS/GDrive 파일명은 NFD로 오므로 정규화 후 매칭
            base = _nfc(os.path.basename(path))
            lm = _RE_LESSON.search(base)
            if lm:
                text = f"{subject} Lesson {lm.group(1)}".strip() if subject \
                    else f"Lesson {lm.group(1)}"
            else:
                text = os.path.splitext(base)[0]
            labels.append({"start_q": first, "text": text})
            if seen_first is None:
                seen_first = first
        if labels:
            log(f"[유닛] 파일명 유도: " +
                ", ".join(f"{x['start_q']}번~ '{x['text']}'" for x in labels))
        return labels

    def parse(self, uploaded_files, job_dir, log):
        from engines.baenje_v2.parser import parse_manuscripts

        problem_files = self._as_list(uploaded_files.get("manuscript"))
        answer_files = self._as_list(uploaded_files.get("answers"))
        if not problem_files:
            raise ValueError("문제 원고가 없습니다.")
        problem_files = sorted(problem_files)
        answer_files = sorted(answer_files)

        units = self._unit_labels(job_dir, problem_files, log)
        content = parse_manuscripts(problem_files, answer_files, units, log)
        content["_source"] = {
            "problem_files": [os.path.basename(p) for p in problem_files],
            "answer_files": [os.path.basename(p) for p in answer_files],
        }
        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        log(f"[파서] 문항 {len(content['problems'])} / 해설 {len(content['answers'])}"
            f" / 유닛 {len(content['units'])} / 경고 {len(content['warnings'])}")
        for w in content["warnings"][:10]:
            log("  " + w)
        return json_path

    # ── 2단계: prepare_jsx ─────────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.baenje_v2.plan import content_to_plan

        cfg = _load_v1_config()
        school = _nfc(self._get_meta(job_dir, "school", "학교미선택"))
        issue_num = _nfc(self._get_meta(job_dir, "issue_num", "01"))

        with open(json_path, encoding="utf-8") as f:
            content = json.load(f)
        plan = content_to_plan(content, log)
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)

        num = issue_num.zfill(2)
        prefix = cfg["indd_name_prefix"]
        out_dir = cfg["indd_output_dir"]
        os.makedirs(out_dir, exist_ok=True)
        indd_path = os.path.join(out_dir, f"{school}_{prefix}{num}_내지_v2.indd")

        try:
            from core.indesign.runner import close_open_indd
            close_open_indd(indd_path, log)
        except Exception:
            pass

        src = cfg.get("indd_original", "")
        if os.path.exists(src):
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 원본 없음: {src}")

        pdf_path = indd_path.replace(".indd", ".pdf")
        result_path = os.path.abspath(os.path.join(job_dir, "render_result.json"))
        jsx_log = os.path.abspath(os.path.join(job_dir, "조판_로그.txt"))
        jsx_path = build_jsx(
            _RENDER_BODY,
            {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
             "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path,
             "__RESULT_PATH__": result_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))

        settings = {"engine": "baenje_v2", "indd_path": indd_path,
                    "pdf_path": pdf_path, "jsx_path": jsx_path,
                    "log_path": jsx_log, "json_path": json_path,
                    "plan_path": plan_path, "result_path": result_path,
                    "school": school, "issue_num": issue_num,
                    "output_dir": job_dir}
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return os.path.join(job_dir, ".settings.json")

    # ── 3단계: run_indesign ────────────────────────────────────────────────

    def run_indesign(self, job_dir, log):
        from core.indesign.runner import run_jsx
        with open(os.path.join(job_dir, ".settings.json"), encoding="utf-8") as f:
            settings = json.load(f)
        try:
            os.remove(settings["log_path"])
        except OSError:
            pass
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="배N제 v2 조판 완료",
                stall_limit=900)

    # ── 4단계: verify — 검수 게이트 ────────────────────────────────────────

    @staticmethod
    def _norm_para(t):
        t = re.sub(u"[\u0000-\u001f\ufffc]", "", t or "")
        return _nfc(_norm_typo(t)).rstrip()

    def verify(self, job_dir, log):
        from core.inspect import dump_indd

        with open(os.path.join(job_dir, ".settings.json"), encoding="utf-8") as f:
            settings = json.load(f)
        with open(settings["plan_path"], encoding="utf-8") as f:
            plan = json.load(f)
        with open(settings["json_path"], encoding="utf-8") as f:
            content = json.load(f)
        result = {}
        if os.path.exists(settings.get("result_path", "")):
            with open(settings["result_path"], encoding="utf-8") as f:
                result = json.load(f)

        warnings = []
        ok = True

        dump = dump_indd(settings["indd_path"],
                         os.path.join(job_dir, "typeset_dump.json"), log)
        got_words = set()
        for st in dump["stories"]:
            for pp in st["paragraphs"]:
                for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                    got_words.add(w.lower())

        # B1 내용 보존 — 플랜(=원고 구조) 단어셋과 대조
        want_words = set()
        for flow in plan["flows"]:
            for unit in flow["units"]:
                for p in unit["paras"]:
                    for w in _RE_WORD.findall(_norm_typo(p["t"])):
                        want_words.add(w.lower())
        lost = sorted(want_words - got_words)
        if lost:
            ok = False
            warnings.append(f"❌ B1 내용 누락 {len(lost)}단어: {lost[:8]}")
        log(f"[검수] B1 내용 보존: 원고 {len(want_words)}단어 / 누락 {len(lost)}")

        # B2 번호 연속
        for key, label in (("problems", "본문"), ("answers", "정답지")):
            nums = [x["no"] for x in content.get(key) or []]
            if not nums:
                continue
            expect = list(range(nums[0], nums[0] + len(nums)))
            if nums != expect:
                ok = False
                bad = [n for n, e in zip(nums, expect) if n != e][:5]
                warnings.append(f"❌ B2 {label} 문항 번호 불연속: {bad}")
        log("[검수] B2 번호 연속: " +
            f"본문 {len(content.get('problems') or [])} / "
            f"정답지 {len(content.get('answers') or [])}")

        # B3 정답지 블록 펼침면 유지 (실행기가 옮긴 뒤 남은 걸침은 0이어야 함)
        crossed = result.get("blocks_crossing_after")
        if crossed:
            ok = False
            warnings.append(f"❌ B3 정답지 블록 펼침면 걸침 {len(crossed)}건: {crossed[:5]}")
        log(f"[검수] B3 블록 유지: 이동 {len(result.get('moved_blocks') or [])}건")

        # B4 러닝헤드 소스
        want_units = len(content.get("units") or [])
        got_heads = result.get("header_texts") or []
        body_heads = [h for h in got_heads if h.get("area") == "본문"]
        if want_units and len(body_heads) < want_units:
            ok = False
            warnings.append(
                f"❌ B4 본문 러닝헤드 {len(body_heads)}/{want_units} — 유닛 라벨 미배치")
        log(f"[검수] B4 러닝헤드: 본문 {len(body_heads)} / 정답지 "
            f"{len([h for h in got_heads if h.get('area') == '정답지'])}")

        # B5 오버플로우
        overflow = int(result.get("overflow") or 0)
        if overflow:
            ok = False
            warnings.append(f"❌ B5 오버플로우 {overflow}개: "
                            f"{(result.get('overflow_heads') or [])[:3]}")
        log(f"[검수] B5 오버플로우: {overflow}개 / 페이지 {result.get('pages')}")

        # B8 플랜 ↔ 완제품 대조 (영역별 텍스트 전량 + 스타일)
        #    공백/탭 정규화 후 이어붙여 비교 → 누락·병합·중복·순서 뒤바뀜을 잡는다.
        #    (3열 묶기·머리행 재작성은 공백만 달라지므로 정규화로 흡수된다)
        def _flat(txts):
            # 빈칸 표현(전각공백/＿)은 조판에서 '밑줄 친 공백'으로 바뀌므로
            # 양쪽 모두에서 제거하고 실제 내용만 비교한다.
            t = _nfc(_norm_typo("".join(txts)))
            return re.sub(r"[\s\u3000\uff3f_]+", "", t)

        dump_by_story = []
        for st in dump["stories"]:
            dump_by_story.append(st["paragraphs"])
        for area, flow in (("body", plan["flows"][0]),
                           ("answers", plan["flows"][1] if len(plan["flows"]) > 1 else None)):
            if not flow or not flow["units"]:
                continue
            want = []
            for unit in flow["units"]:
                if unit.get("unit_label"):
                    want.append(unit["unit_label"])
                for pp in unit["paras"]:
                    want.append(pp["t"])
            wtxt = _flat(want)
            best, best_diff = None, None
            for paras in dump_by_story:
                got = _flat([p["t"] for p in paras])
                if not got:
                    continue
                diff = abs(len(got) - len(wtxt))
                if best_diff is None or diff < best_diff:
                    best, best_diff = got, diff
            if best is None:
                continue
            if best != wtxt:
                ok = False
                # 첫 불일치 지점 보고
                i = 0
                while i < min(len(best), len(wtxt)) and best[i] == wtxt[i]:
                    i += 1
                warnings.append(
                    f"❌ B8 {area} 플랜↔완제품 텍스트 불일치 "
                    f"(플랜 {len(wtxt)}자 / 완제품 {len(best)}자, 첫 차이 {i}자째: "
                    f"플랜 '{wtxt[i:i+24]}' vs 완제품 '{best[i:i+24]}')")
            else:
                log(f"[검수] B8 {area} 플랜↔완제품 텍스트 일치 ({len(wtxt)}자)")

        # B9 출력물 불변식 (파서와 독립 — 완제품을 직접 검사)
        alp = result.get("answer_line_as_passage") or []
        if alp:
            ok = False
            warnings.append(f"❌ B9 서술형 답란이 지문 스타일로 조판됨 {len(alp)}건: {alp[:3]}")
        mixed = result.get("mixed_format") or []
        if mixed:
            ok = False
            warnings.append(f"❌ B9 재작성 단락 문자 서식 불균일 {len(mixed)}건: {mixed[:3]}")
        orphan = result.get("orphan_moved") or []
        orphan_left = result.get("orphan_remaining") or []
        if orphan_left:
            ok = False
            warnings.append(
                f"❌ B9 정답지 고아 블록 잔존 {len(orphan_left)}건 "
                f"(번호+2줄 이하만 남고 넘어감): {orphan_left[:4]}")
        trimmed = result.get("trimmed_pages") or 0
        of = result.get("oneline_failed") or []
        if of:
            warnings.append(f"⚠️ B9 답란 한 줄 맞춤 실패 {len(of)}건: {of[:2]}")
        if not result.get("credit_placed"):
            warnings.append("⚠️ B9 마지막 페이지 크레딧 미배치")
        # 뒤쪽 빈 페이지가 2쪽 이상 남으면 낭비 (짝수 유지분 1쪽까지만 허용)
        blanks = result.get("memo_pages") or []
        if len(blanks) > 1:
            warnings.append(f"⚠️ B9 뒤쪽 빈 페이지 {len(blanks)}쪽: {blanks}")
        log(f"[검수] B9 답란-지문 {len(alp)} / 서식불균일 {len(mixed)} / "
            f"한줄맞춤 {result.get('oneline_fitted')} / 크레딧 "
            f"{len(result.get('credit_placed') or [])} / 고아블록 {len(orphan)} / "
            f"빈페이지정리 {trimmed} / 색정합 {result.get('recolored')}")

        # B7 레이아웃 후 발문 단락 수 = 문항 수 (자동번호 밀림 감지)
        cl = result.get("choice_layout") or {}
        if cl.get("stems") is not None and cl.get("units") is not None:
            if cl["stems"] != cl["units"]:
                ok = False
                warnings.append(
                    f"❌ B7 발문 단락 {cl['stems']} ≠ 문항 {cl['units']} — "
                    "선지 레이아웃이 발문을 삼켰을 수 있음(자동번호 밀림)")
        log(f"[검수] B7 발문 단락: {cl.get('stems')} / 문항 {cl.get('units')} "
            f"| 3열 {cl.get('packed')} · 머리행 {cl.get('aligned')} · "
            f"프레임확장 {cl.get('grown')}")

        # B6 스타일·마스터 부재
        miss = list(result.get("missing_styles") or []) + \
            list(result.get("missing_masters") or [])
        if miss:
            ok = False
            warnings.append(f"❌ B6 템플릿에 없는 스타일/마스터: {sorted(set(miss))[:6]}")

        # 파서 경고는 정보성
        for w in (content.get("warnings") or [])[:10]:
            warnings.append("⚠️ " + w)

        pdf_ok = os.path.exists(settings["pdf_path"])
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 없음")

        log(f"[검수] {'통과' if ok else '실패'} | 경고 {len(warnings)}건")
        return {
            "ok": ok,
            "overflow": overflow,
            "pages": result.get("pages"),
            "pdf_path": settings["pdf_path"] if pdf_ok else None,
            "indd_path": settings["indd_path"],
            "warnings": warnings,
        }
