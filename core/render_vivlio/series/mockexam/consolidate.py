# -*- coding: utf-8 -*-
"""학교 프로파일 취합 — 학교마다 뭐가 다른지 한 장으로.

19개 학교·학년 프로파일이 각각 4만~5만 자다. 사람이 나란히 놓고 볼 수 있어야
"이 학교는 묶음을 안 쓴다" 같은 사실이 눈에 들어온다. 이 모듈은 프로파일들을
읽어 **학교 × 규칙 축의 대조표**와 **정합성 점검**을 낸다.

점검하는 것:
  - 스키마에 있는 절이 비어 있지 않은가 (얕게 채운 프로파일 색출)
  - 정본이 직전 회차(26-1-기말)인가, 아니면 대체인가
  - 값이 '추정'인지 '실측'인지 (typography.approx)
  - gaps / diff_vs_current 가 실제로 채워졌는가
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "profiles")
TARGET_EXAM = "26-1-기말"          # 직전 회차

# 대조표에 세울 축 — (열 제목, 프로파일 경로, 짧게 줄이는 법)
AXES = [
    ("정본 회차", "reference.exam", None),
    ("정본 성격", "reference.kind", None),
    ("단", "page.columns", None),
    ("단 괘선", "page.column_rule.on", None),
    ("쪽 테두리", "page.page_border.on", None),
    ("배점 괄호", "score.bracket", None),
    ("배점 자리", "score.attach", None),
    ("묶음 템플릿", "numbering.group.template", None),
    ("범위 구분자", "numbering.group.range_sep", None),
    ("서답형 라벨", "numbering.essay.template", None),
    ("보기 표기", "given.marker", None),
    ("보기 렌더", "given.render", None),
    ("조건 표기", "cond.marker", None),
    ("조건 렌더", "cond.render", None),
    ("요약 화살표", "summary.arrow.glyph", None),
    ("선지 배치", "choices.layout", None),
    ("(A)(B) 구분자", "choices.ab_pair.separator", None),
    ("마무리", "ending.text", None),
    ("배점표", "score_table.on", None),
    ("원고 번호", "manuscript.numbers_given", None),
    ("원고 서답형", "manuscript.essay_marked", None),
    ("원고 묶음", "manuscript.groups_marked", None),
]

SECTIONS = ["reference", "page", "running", "numbering", "score", "given",
            "cond", "summary", "choices", "typography", "ending", "manuscript"]


def _dig(d, path):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _fmt(v):
    """표 한 칸으로 — 줄바꿈·파이프가 마크다운 표를 깨뜨리므로 반드시 중화한다."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "○" if v else "✕"
    if isinstance(v, (list, dict)):
        s = json.dumps(v, ensure_ascii=False)
    else:
        s = str(v)
    s = s.replace("\n", "⏎").replace("|", "\\|").strip()
    if not s:
        return "(빈 값)"
    return s if len(s) <= 40 else s[:38] + "…"


def load_all():
    out = {}
    for f in sorted(os.listdir(PROFILES)):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        with open(os.path.join(PROFILES, f), encoding="utf-8") as fh:
            out[f[:-5]] = json.load(fh)
    return out


def lint(profiles):
    """얕게 채운 프로파일·빠진 절 색출."""
    rows = []
    for key, p in profiles.items():
        missing = [s for s in SECTIONS if not p.get(s)]
        ref = p.get("reference") or {}
        rows.append({
            "key": key,
            "size_kb": round(os.path.getsize(
                os.path.join(PROFILES, key + ".json")) / 1024, 1),
            "정본": ref.get("exam", "—"),
            "직전회차": ref.get("exam") == TARGET_EXAM,
            "성격": ref.get("kind", "—"),
            "추정치": bool(_dig(p, "typography.approx")),
            "빠진절": missing,
            "gaps": len(p.get("gaps") or []),
            "diff": len(p.get("diff_vs_current") or []),
        })
    return rows


def table(profiles):
    keys = sorted(profiles)
    lines = ["| 항목 | " + " | ".join(keys) + " |",
             "|---|" + "---|" * len(keys)]
    for title, path, _ in AXES:
        cells = [_fmt(_dig(profiles[k], path)) for k in keys]
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def report():
    profiles = load_all()
    out = ["# 동형모의고사 학교별 규칙 대조표", "",
           f"프로파일 {len(profiles)}개. 정본 기준 회차 = **{TARGET_EXAM}**(직전 회차).",
           "", "## 정합성 점검", "",
           "| 학교 | 크기 | 정본 | 직전? | 성격 | 추정 | gaps | diff | 빠진 절 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in lint(profiles):
        out.append("| {key} | {size_kb}KB | {정본} | {ok} | {성격} | {approx} | "
                   "{gaps} | {diff} | {missing} |".format(
                       ok="✔" if r["직전회차"] else "⚠ 대체",
                       approx="근사" if r["추정치"] else "실측",
                       missing=", ".join(r["빠진절"]) or "—", **r))
    out += ["", "## 규칙 대조", "", table(profiles)]
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
