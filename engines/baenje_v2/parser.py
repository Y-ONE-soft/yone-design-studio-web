"""배N제 v2 파서 — 원고(docx/hwpx) → 구조 인식 content.json.

v1(engines/baenje/parser.py)은 원고를 RTF로 바꿔 InDesign에 던지고, 단락의
종류 판정(발문/지문/선지/보기/조건/요약/대화)을 run.jsx의 상태머신이 했다.
v2는 그 판정을 **파이썬으로 끌어와** 구조를 데이터로 남긴다. JSX는 실행만 한다.

판정 원칙 (docs/2026_여름개편_마스터플랜.md "구조가 룰보다 우선"):
- 발문 = 번호(N.)로 시작하는 한국어 지시문 (물음표/시오. 종결)
- 지문 = 발문 뒤의 긴 영문 단락
- 선지 = ①~⑤ 로 시작
- 보기/조건 = <보기>/[조건] 마커 + 그 아래 항목(구조로 이어짐)
- 대화 = "화자: 발화" 형태가 연속
- 판정 실패 단락은 버리지 않고 kind="unknown" + warning (침묵 금지)

출력 스키마 (content.json):
{
  "format": "baenje-content-v1",
  "units": [{"label": str, "start_q": int}],
  "problems": [{"no": int, "paras": [{"t": str, "kind": str, "runs": [{"t","ul"}]}]}],
  "answers":  [{"no": int, "paras": [{"t": str, "kind": str, "runs": [...]}]}],
  "warnings": [str]
}
"""
import os
import re
import unicodedata

from core.extract import (
    docx_extract_paragraphs,
    hwp_extract_paragraphs,
    hwpx_extract_paragraphs,
    is_hwpx,
    nfc,
)

# ── 구조 판정 상수 (룰은 데이터로) ──────────────────────────────────────
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RE_QNUM = re.compile(r"^\s*(\d{1,3})\.\s")
RE_CHOICE = re.compile(r"^\s*[①-⑳]")
RE_LETTER_ITEM = re.compile(r"^\s*[\(（][a-zA-Z][\)）]")
RE_CIRCLED_LETTER = re.compile(r"^\s*[ⓐ-ⓩ]")
RE_HANGUL_ITEM = re.compile(r"^\s*[ㄱ-ㅎ][.)]")
RE_NUM_ITEM = re.compile(r"^\s*\(\d+\)\s")
RE_AB_BLOCK = re.compile(r"^\s*\([A-E]\)")
RE_BOGI = re.compile(r"^\s*[<＜]보기[>＞]")
RE_COND = re.compile(r"^\s*[\[〔<]조건[\]〕>]")
RE_SUMMARY = re.compile(r"^\s*[\[〔<]요약(문)?[\]〕>]")
RE_SPEAKER = re.compile(r"^\s*[A-Z][A-Za-z.'\-]{0,14}\s*:\s")
RE_BULLET = re.compile(r"^\s*[·•･]")
RE_END_MARK = re.compile(r"^[\s\-–—]*끝[\s\-–—]*$")
RE_BLANKS_ONLY = re.compile(r"^[\s＿_（）()　\-－–—.．ㅡ]+$")
RE_ANS_NUM = re.compile(r"^\s*(\d{1,3})\s*$")
RE_ANS_MARK = re.compile(r"^\s*\[(정답|해석|해설|어휘)\]\s*")

# 발문 종결 신호 (한국어 지시문)
RE_STEM_SIGNAL = re.compile(r"([가-힣]\?|시\s*오\.|고르면\?|것은\?|쓰시오|하시오)")


def _norm(s):
    return nfc(s or "")


def _extract(path):
    """원고 → [{"text", "runs":[{"t","ul"}]}] — 포맷 무관, 밑줄 보존."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        rows = docx_extract_paragraphs(path, extract_underline=True)
    elif ext in (".hwpx", ".hwp"):
        rows = (hwpx_extract_paragraphs(path, extract_underline=True)
                if is_hwpx(path)
                else hwp_extract_paragraphs(path, extract_underline=True))
    else:
        raise ValueError(f"지원하지 않는 원고 형식: {path}")
    out = []
    for r in rows:
        text = _norm(r.get("text", ""))
        runs = [{"t": _norm(x.get("t", "")), "ul": bool(x.get("ul"))}
                for x in (r.get("runs") or []) if x.get("t")]
        out.append({"text": text, "runs": runs})
    return out


def _merge_runs(runs):
    """연속 동일 밑줄 상태 병합 — 밑줄이 전혀 없으면 [] (플랜 축소)."""
    if not runs or not any(r["ul"] for r in runs):
        return []
    out = []
    for r in runs:
        if out and out[-1]["ul"] == r["ul"]:
            out[-1]["t"] += r["t"]
        else:
            out.append({"t": r["t"], "ul": r["ul"]})
    return out


def _strip_prefix_runs(runs, prefix_len):
    """앞쪽 prefix_len 글자를 runs에서 제거 (마커 제거와 동기화)."""
    if not runs or prefix_len <= 0:
        return _merge_runs(runs)
    left = prefix_len
    out = []
    for r in runs:
        if left <= 0:
            out.append(dict(r))
            continue
        if len(r["t"]) <= left:
            left -= len(r["t"])
            continue
        out.append({"t": r["t"][left:], "ul": r["ul"]})
        left = 0
    return _merge_runs(out)


def _is_stem(t):
    """발문 판정 — 번호 + 한국어 지시문 신호."""
    if not RE_QNUM.match(t):
        return False
    return bool(RE_STEM_SIGNAL.search(t))


def classify_problem_paragraphs(rows, warnings, src=""):
    """문제 원고 단락열 → [{"no", "paras":[{t,kind,runs}]}].

    상태(보기/조건/요약 안쪽)를 들고 가며 구조로 판정한다.
    """
    problems = []
    cur = None
    state = None          # None | "bogi" | "cond" | "summary"
    prev_kind = None

    for row in rows:
        text, runs = row["text"], row["runs"]
        t = text.strip()
        if not t or RE_END_MARK.match(t):
            continue

        if _is_stem(t):
            no = int(RE_QNUM.match(t).group(1))
            cur = {"no": no, "paras": []}
            problems.append(cur)
            state = None
            prev_kind = "stem"
            cur["paras"].append({"t": t, "kind": "stem", "runs": _merge_runs(runs)})
            continue

        if cur is None:
            warnings.append(f"[파서] 발문 이전 단락 무시({src}): {t[:40]}")
            continue

        kind = None
        if RE_COND.match(t):
            state, kind = "cond", "cond"
        elif RE_SUMMARY.match(t):
            state, kind = "summary", "summary"
        elif RE_BOGI.match(t):
            state, kind = "bogi", "bogi"
        elif RE_CHOICE.match(t):
            state, kind = None, "choice"
        elif state == "cond":
            kind = "cond"
        elif state == "bogi" and (
                RE_LETTER_ITEM.match(t) or RE_CIRCLED_LETTER.match(t)
                or RE_HANGUL_ITEM.match(t) or " / " in t):
            kind = "bogi"
        elif state == "summary":
            kind = "summary" if not RE_AB_BLOCK.match(t) else "choice"
        elif RE_AB_BLOCK.match(t):
            rest = RE_AB_BLOCK.sub("", t).strip(" :")
            kind = "passage" if (len(rest) >= 25 and re.match(r"^[A-Za-z\"“‘]", rest)) \
                else "choice"
        elif RE_NUM_ITEM.match(t):
            kind = "choice"
        elif RE_BULLET.match(t):
            kind = "bogi"
        elif RE_SPEAKER.match(t):
            kind = "dialogue"
        elif RE_BLANKS_ONLY.match(t):
            kind = "choice"
        elif re.match(r"^[A-Za-z\"“‘(]", t):
            kind = "passage"
        elif " / " in t:
            kind = "bogi"
        else:
            kind = "passage"
            if not re.search(r"[A-Za-z]", t):
                kind = "unknown"
                warnings.append(
                    f"[파서] 종류 미상 단락({src}, {cur['no']}번): {t[:40]}")

        if kind not in ("bogi", "cond", "summary"):
            state = None
        cur["paras"].append({"t": t, "kind": kind, "runs": _merge_runs(runs)})
        prev_kind = kind
    return problems


def classify_answer_paragraphs(rows, warnings, src=""):
    """해설 원고 단락열 → [{"no", "paras":[{t,kind,runs}]}].

    구조: 번호줄 → [정답] → [해석](+이어지는 단락) → [해설](+이어지는 단락)
    마커는 여기서 제거한다 (스타일이 '정답 |' 라벨을 자동 생성).
    """
    blocks = []
    cur = None
    mode = None
    for row in rows:
        text, runs = row["text"], row["runs"]
        t = text.strip()
        if not t or RE_END_MARK.match(t):
            continue

        m = RE_ANS_NUM.match(t)
        if m:
            cur = {"no": int(m.group(1)), "paras": [
                {"t": m.group(1), "kind": "num", "runs": []}]}
            blocks.append(cur)
            mode = None
            continue
        if cur is None:
            # 제목줄 등 첫 번호 이전 — 조판 대상 아님
            continue

        mk = RE_ANS_MARK.match(t)
        if mk:
            label = mk.group(1)
            body = RE_ANS_MARK.sub("", t)
            kind = {"정답": "answer", "해석": "trans",
                    "해설": "expl", "어휘": "vocab"}[label]
            mode = kind
            cur["paras"].append({
                "t": body, "kind": kind,
                "runs": _strip_prefix_runs(runs, len(t) - len(body))})
            continue

        cur["paras"].append({"t": t, "kind": "cont", "runs": _merge_runs(runs)})
    if not blocks:
        warnings.append(f"[파서] 해설 블록 0개({src}) — 번호줄을 못 찾음")
    return blocks


def parse_manuscripts(problem_files, answer_files, unit_labels, log=None):
    """원고 파일 묶음 → content dict."""
    warnings = []
    problems = []
    for path in problem_files:
        rows = _extract(path)
        got = classify_problem_paragraphs(rows, warnings, os.path.basename(path))
        if log:
            log(f"[파서] 문제 {os.path.basename(path)}: {len(got)}문항")
        problems.extend(got)

    answers = []
    for path in answer_files:
        rows = _extract(path)
        got = classify_answer_paragraphs(rows, warnings, os.path.basename(path))
        if log:
            log(f"[파서] 해설 {os.path.basename(path)}: {len(got)}블록")
        answers.extend(got)

    # 번호 연속성 (침묵 금지 — 어긋나면 경고로 남기고 게이트가 판정)
    for name, arr in (("문제", problems), ("해설", answers)):
        nums = [x["no"] for x in arr]
        if nums and nums != list(range(nums[0], nums[0] + len(nums))):
            warnings.append(f"[파서] {name} 번호 불연속: {nums[:5]} … {nums[-5:]}")

    units = []
    for u in unit_labels or []:
        units.append({"label": u["text"], "start_q": int(u["start_q"])})

    return {
        "format": "baenje-content-v1",
        "units": units,
        "problems": problems,
        "answers": answers,
        "warnings": warnings,
    }
