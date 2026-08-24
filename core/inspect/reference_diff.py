"""완성본(기준 파일) 대조 — 신규 조판물에만 있는 구조 표기를 찾아낸다.

사용자 지침(반복): "기존 파일을 보고 거기서 어떻게 들어갔는지를 보고 거기에
맞추면 된다." 즉 **관행의 정본은 이전 완성본**이다. 육안으로 한 항목씩
지적받는 대신, 같은 계열의 완성본을 덤프해 구조를 자동 대조한다.

대조 대상은 '내용'이 아니라 '구조 표기'다 (과가 다르면 내용은 당연히 다름):
  - 단락스타일 인벤토리: 기준에 없는 스타일이 새 출력에 등장
  - 스타일 없는([기본 단락]) 줄의 **형태**(숫자·영단어를 자리표로 치환):
    완제품이 인쇄하는 라벨·머리글·안내문 집합이 관행이다.
  - 한국어 지시문 집합: 기준이 인쇄하는 발문 종류

기준 파일 선정은 호출자가 한다 (같은 과목·출판사의 다른 과 완성본).
"""
import collections
import re

_ENG = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_NUM = re.compile(r"\d+")
_INSTR = re.compile(r"(?:시오|세요|십시오)\s*[.?!]?\s*$")
_HAN = re.compile(r"[가-힣]")
_BASIC = ("[기본 단락]", "[단락 스타일 없음]")


def _norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lstrip("￼").strip()


def _shape(t):
    """숫자·영단어를 자리표로 치환한 '형태' — 내용 차이를 지운 구조 지문."""
    s = _NUM.sub("N", t)
    s = _ENG.sub("W", s)
    return re.sub(r"(W ){3,}", "W… ", s)[:60]


def profile(dump):
    """덤프 → 구조 프로파일 (스타일 / 기본단락 형태 / 지시문)."""
    styles = collections.Counter()
    basic = collections.Counter()
    instr = collections.Counter()
    examples = {}
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            t = _norm(p.get("t"))
            if not t:
                continue
            s = p.get("s") or "?"
            styles[s] += 1
            if s in _BASIC:
                sh = _shape(t)
                basic[sh] += 1
                examples.setdefault(("basic", sh), t)
            # 지시문은 **무스타일(기본 단락) 것만** 센다. 발문 계열
            # 스타일의 지시문은 문항 내용이라 과가 다르면 당연히 다르다 —
            # 구조 대조에 넣으면 노이즈가 된다.
            if (s in _BASIC and _HAN.search(t) and _INSTR.search(t)
                    and len(t) <= 90):
                instr[t] += 1
                examples.setdefault(("instr", t), t)
    return {"styles": styles, "basic": basic, "instr": instr,
            "examples": examples}


def compare(new_dump, ref_dump, ref_name=""):
    """(findings, stats) — 기준에 없는데 새 출력에만 있는 구조 표기.

    findings 는 사람이 읽을 문장 리스트. 기준에만 있는 항목은 '누락 후보'로
    따로 보고한다 (원고에 그 섹션이 없어서인 경우가 많아 참고용)."""
    a, b = profile(new_dump), profile(ref_dump)
    findings, missing = [], []
    for key, label in (("styles", "단락스타일"), ("basic", "무스타일 표기"),
                       ("instr", "지시문")):
        only_new = [k for k in a[key] if k not in b[key]]
        only_ref = [k for k in b[key] if k not in a[key]]
        for k in sorted(only_new):
            ex = a["examples"].get((key[:5], k), k)
            findings.append("%s '%s' 는 기준(%s)에 없음 (×%d) — 예: %s"
                            % (label, str(k)[:40], ref_name, a[key][k],
                               str(ex)[:50]))
        for k in sorted(only_ref):
            missing.append("%s '%s' 가 기준에는 있고 새 출력에는 없음 (×%d)"
                           % (label, str(k)[:40], b[key][k]))
    stats = {"ref": ref_name,
             "new_styles": len(a["styles"]), "ref_styles": len(b["styles"]),
             "only_new": len(findings), "only_ref": len(missing)}
    return findings, missing, stats
