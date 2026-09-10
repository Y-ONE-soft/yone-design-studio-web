# -*- coding: utf-8 -*-
"""분석본(STEP UP, 216×303mm) IDML → 지문 구조. **InDesign 없이 순수 파이썬.**

`idml.py`(완성 포켓북 파서)와 **같은 모양**의 dict 를 낸다 —
`pno · label · passage · translation · topic · summary · synonyms …`.
코퍼스가 두 출처를 구분 없이 담아야 하기 때문이다.

────────────────────────────────────────────────────────────────────
실측으로 밝혀진 것 (104권 전수 조사 — 25-2-기말 37권 + 26-2-중간 67권,
학교 25곳)
────────────────────────────────────────────────────────────────────

1. **분석본에는 쓸 만한 문단 스타일이 없다.**
   `Resources/Styles.xml` 의 ParagraphStyle 이 26권 전부 `본문` 하나뿐이다
   (+ InDesign 기본 2개). 완성 포켓북은 `본문·한글·플로우노트·주제/요약문·
   동반의어·암기테스트` 6종으로 역할을 갈랐는데 **분석본은 그 축이 없다.**
   → 역할 판정을 **문자 스타일**로 옮긴다. 이것이 idml.py 와 갈리는 지점이다.

2. **영어 지문과 한글 해석이 한 스토리에 번갈아 든 책이 있다.**
   · 광문1·배재1 계열 = 지문 스토리 / 해석 스토리가 따로.
   · 명일1·광문2 계열 = 한 스토리 안에서 `문장 → 해석 → 문장 → 해석` 교차.
   → **프레임(스토리) 단위로 역할을 정하면 안 되고 줄 단위로 정해야 한다.**

3. **해석 프레임 첫머리에 영어 제목이 영어 지문 스타일로 들어 있다**(교과서 계열).
   `[영어 지문]Rescuing Cultural Treasures [한글 해석]문화유산 구하기 …`
   → 스타일만 보고 run 을 지문으로 끌어가면 지문 끝에 제목이 붙는다.
     **해석 프레임 안에서는** 한글 해석 run 이 하나라도 있으면 그 줄 전체가
     해석이고, 머리의 영어 조각은 소제목으로 떼어 낸다(`title`).
     ⚠ 그 규칙을 **지문 프레임에 그대로 쓰면 지문이 통째로 사라진다.**
       안내문 지문(성덕1 27·28번)은 영어 본문 704자 뒤에 해석 스타일 37자가
       붙어 있어서, 줄 전체가 해석으로 넘어가 그 스프레드가 통째로 빠졌다.
       → 프레임 성격은 **그 스토리의 글자 수**로 정하고(`_story_is_translation`),
         지문 프레임에서는 줄을 역할 그룹으로 갈라 각자 제자리로 보낸다(`_route`).

4. **주제와 요약을 가르는 것은 줄바꿈이 아니라 `주제/요약:상단제목` run** 이다.
   내용이 공백뿐인 빈 run 이 구분자로 심겨 있다(아이콘 자리). 광문1 은 주제와
   요약이 **한 줄**에 붙어 있어서 "첫 줄=주제"로 가르면 통째로 주제가 된다.

5. **한 스프레드에 지문이 둘인 면이 있다**(짤지문 18·19번, 25·26번 …).
   판정은 좌표가 아니라 **머리말 프레임 수**로 한다 — 좌·우 면에 서로 다른
   `마스터페이지:챕터` 가 하나씩 있으면 지문 둘이다.
   반대로 `43~45번` 장문은 **좌·우 면 머리말이 같아서** 한 지문으로 붙는다.
   명일1 외부지문은 스프레드를 넘어가며 같은 머리말이 이어진다 → 이어 붙인다.

6. **머리말이 통째로 1면(간지)에 쌓여 있는 책이 있다**(광문1_분석본01·02).
   내용 스프레드에는 머리말 프레임이 아예 없고, 간지 스프레드에 10개가
   겹쳐 있다. 더미 맨 앞에는 템플릿에서 딸려온 남의 머리말이 한 벌 섞여
   있어서(`능률(오) 1과 / A Journey into Yourself`) **뒤에서부터** 지문 수만큼
   가져온다. 숫자칸·챕터칸은 프레임 순서가 섞여 있어 **따로** 모은다.

7. **VOCA 는 텍스트가 아니라 표**다. `<Table>` 은 ParagraphStyleRange 의
   자식이라 idml.py 의 `paragraphs()` 로는 **한 글자도 안 잡힌다.**
   셀 이름이 `열:행` 이고 짝수 열=중요어휘 / 홀수 열=의미인데, 셀에 붙은
   문자 스타일은 `어휘:뜻` 이어야 할 자리에 `어휘:단어` 가 흔하다
   → **스타일을 믿지 말고 열 번호로 가르고, 한글 비율로 뒤집힘을 바로잡는다.**

8. **`지문분석:지문 번호` 는 완성본과 뜻이 다르다.**
   완성본에서는 지문 키(`250921`·`3과 04`)지만 분석본에서는 **문장 번호**(1·2·3)
   와 어법 설명 불릿(`*`)이다. idml.py 의 `mark_of()` 는 이걸 `pno` 로 읽으므로
   **그 표를 그대로 쓰면 안 된다** → 여기서 `snum` 으로 덮어쓴다.

9. 편집 중 메모가 지문 스타일로 남아 있다(`<< 여기서 변경`, 9자).
   → 지문/해석 글자가 30자 미만인 스토리는 지문이 아니다(idml.py 와 같은 기준).

학교별 스타일 이름 차이는 **없었다.** 37권이 같은 템플릿에서 나왔다
(`지문분석:` · `주제/요약:` · `핵심기출문제:` · `마스터페이지:` · `어휘:`).
다만 선언만 되고 안 쓰이는 스타일이 있다 — `A 지문분석:영어 지문`(15권),
`지문분석:본문 한글 해석(미니)`(7권), `플로우:*` · `서술형:*` · `어휘:*`
텍스트판(전권). **차이는 이름이 아니라 지면 구성에서 난다**(위 3·5·6).

────────────────────────────────────────────────────────────────────
원고 세대가 둘이다 (26-2-중간 67권을 더해 104권 재검증)
────────────────────────────────────────────────────────────────────

같은 템플릿에서 나왔지만 **26-2-중간 세대는 서식 운용이 다르다.** 파일명이나
폴더로 세대를 묻지 않고, 아래 넷을 전부 **구조로** 판정한다.

10. **주제/요약 경계가 세대마다 다르다.**
    · 구세대 532면 전부 `주제/요약:상단제목` 빈 run 이 구분자.
      주제·요약이 **한 줄**에 붙은 면이 300개라 줄바꿈으로는 못 가른다.
    · 신세대 532면 중 453면은 **구분자가 아예 없고** 단락으로 갈려 있다.
    → 빈 구분자가 하나라도 있으면 그것이 경계, 없으면 줄바꿈이 경계.
    ⚠ `상단제목` 이 **글자를 담고 있으면 구분자가 아니라 본문**이다
      (강동2 는 주제 177자를 이 스타일로 찍었다).
    ⚠ 조각을 이을 때 **run 은 붙이고 줄만 띄운다.** 자간 오버라이드로 낱말
      한가운데서 run 이 갈린 원고가 있어 run 마다 공백을 넣으면
      `The wo rd "hip-hop"` 처럼 낱말이 갈라진다.

11. **신세대는 내용의 상당 부분을 문자 스타일 없이 찍는다**
    (`$ID/[No character style]` — 구세대 181자 → 신세대 439,119자).
    이름이 없으니 스토리를 보고 판정한다(`_relabel`). 안 하면 해석 125건이
    통째로 새고 주제 169건이 사라진다.

12. **스타일 이름이 문서 간 복사로 갈아 끼워진다** —
    `마스터페이지:MIGRATED_b5c7ef__챕터_숫자`. 접두를 붙여 잠근 규칙은
    그때 조용히 깨진다(배재2 에서 지문 라벨이 통째로 빠졌다) → **꼬리말로만**
    판정한다. [[analysis_swatch_edit_breaks_body]] 의 그 구조다.

13. **스타일 이름에 오타가 있다** — `지문분석:형관펜_보라`(5권). 오타를
    안 받아 주면 형광펜 친 낱말이 지문에서 빠진다.

플로우노트·동반의어는 분석본에 **없다**(완성본에서만 사람이 채운다) →
`flownote`·`synonyms` 는 빈 채로 내고 플로우노트DB·완성본 하베스트가 채운다.
삽화도 걸린 그림이 0개다 — 링크는 GDrive 삽화 폴더에서 붙인다.
"""
import os
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET

import idml as _I

# ── 문자 스타일 → 역할 ────────────────────────────────────
#   접두가 계열마다 흔들린다(`지문분석:` vs `A 지문분석:`). 꼬리말로 판정한다.
#   순서가 곧 우선순위다 — `1. 일반 영어 지문 파란색` 은 '영어 지문' 에 걸려야 하고
#   `본문 한글 해석(미니)` 는 '한글 해석' 에 걸려야 한다.
_ROLE = [
    (re.compile(r"한글\s*해석"), "translation"),
    (re.compile(r"본문\s*풀이"), "grammar"),
    (re.compile(r"상단제목"), "topic_sep"),
    (re.compile(r"주제요약"), "topic"),
    # `형관펜` 은 오타가 아니라 실제로 원고에 있는 스타일 이름이다(5권·51자).
    # 안 받아 주면 형광펜 친 낱말이 지문에서 조용히 빠진다.
    (re.compile(r"영어\s*지문|형[광관]펜"), "passage"),
    (re.compile(r"지문\s*번호"), "snum"),      # ← 분석본에서는 '문장 번호'다
    (re.compile(r"핵심기출문제|박스\s*지문"), "exam"),
    # ⚠ 접두를 붙여 잠그면 안 된다 — 문서 간 복사로 스타일이 갈아 끼워지면
    #   `마스터페이지:MIGRATED_b5c7ef__챕터_숫자` 가 된다(배재2 실측).
    (re.compile(r"챕터_숫자"), "head_num"),
    (re.compile(r"챕터"), "head_ch"),
    (re.compile(r"마스터페이지:|페이지번호"), "running"),
    (re.compile(r"^간지:|A_메뉴"), "cover"),
    (re.compile(r"^어휘:"), "voca"),
]

# 완성본 파서의 의미 클래스 표(파란색·형광펜 …)는 그대로 쓴다. 다만 `지문 번호`
# 만 뜻이 정반대라 여기서 가로챈다(위 8번).
_SNUM = re.compile(r"지문\s*번호")

_WS = re.compile(r"[ \t   ]+")
_MOCK = re.compile(
    r"(\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,3})\s*(?:[~\-–]\s*(\d{1,3}))?\s*번")


def nfc(s):
    """맥 파일명·IDML 안 한글이 NFD 로 섞여 온다. 비교 전에 반드시 정규화한다."""
    return unicodedata.normalize("NFC", s or "")


# 무스타일 run 에 붙이는 **합성 스타일**. 26-2-중간 세대는 내용의 상당 부분을
# 문자 스타일 없이(`$ID/[No character style]`) 찍어서 이름으로는 못 가른다
# (구세대 181자 → 신세대 430,234자). 스토리를 보고 미리 이름을 붙여 준다.
_SYN_BODY = "\x00body"      # 지문/해석 프레임 안의 무스타일 → 내용으로 가른다
_SYN_TOPIC = "\x00topic"    # 통째로 무스타일인 주제/요약 프레임


def role_of(style_name):
    n = nfc(style_name)
    if n == _SYN_BODY:
        return "body"
    if n == _SYN_TOPIC:
        return "topic"
    for pat, role in _ROLE:
        if pat.search(n):
            return role
    return None


def mark_of(style_name):
    """의미 클래스. idml.mark_of 를 쓰되 `지문 번호` 만 덮어쓴다."""
    if _SNUM.search(nfc(style_name)):
        return "snum", None
    return _I.mark_of(style_name)


def _join_head(have, add):
    """머리말을 잇되 **같은 말은 두 번 넣지 않는다**.

    교재팀이 머리말 프레임을 복제해 두는 일이 있다(광문1 분석본03 실측: 한
    스프레드에 `1강`·`분석` 이 두 벌씩 있고 `<< 여기서 변경` 메모가 붙어 있다).
    그대로 이으면 라벨이 `1강 1강`·`분석 분석` 이 되어 배지와 저술물 이름이
    통째로 어긋난다.
    """
    add = _sq(add)
    if not add:
        return have
    if not have:
        return add
    if add == have or add in have.split():
        return have
    return _sq(have + " " + add)


def _sq(s):
    return _WS.sub(" ", nfc(s or "")).strip()


# ── 스프레드 기하 ─────────────────────────────────────────
def _tx(item_transform):
    try:
        return float((item_transform or "").split()[4])
    except (IndexError, ValueError):
        return 0.0


def _spreads_ex(doc):
    """idml.Idml.spreads() 는 면 좌표를 안 준다. 좌·우 면을 갈라야 해서
    (짤지문 스프레드) 여기서 다시 읽는다. idml.py 는 건드리지 않는다."""
    for f in doc.spread_files:
        root = ET.fromstring(doc.z.read(f))
        sp = root.find("Spread")
        if sp is None:
            continue
        pages = []
        for p in sp.iter("Page"):
            pages.append({"name": p.get("Name"),
                          "master": nfc(urllib.parse.unquote(
                              p.get("AppliedMaster") or "").replace(
                                  "MasterSpread/", "")),
                          "x": _tx(p.get("ItemTransform"))})
        pages.sort(key=lambda p: p["x"])
        frames, links = [], []
        for tf in sp.iter("TextFrame"):
            frames.append({"story": tf.get("ParentStory"),
                           "x": _tx(tf.get("ItemTransform"))})
        for rect in sp.iter("Rectangle"):
            for im in list(rect.iter("Image")) + list(rect.iter("PDF")):
                lk = im.find("Link")
                if lk is not None and lk.get("LinkResourceURI"):
                    links.append(lk.get("LinkResourceURI"))
        yield {"file": f, "pages": pages, "frames": frames, "links": links}


def _page_index(pages, x):
    """프레임 x → 면 번호. 면 원점 중 x 이하인 것 가운데 가장 오른쪽."""
    idx = 0
    for i, p in enumerate(pages):
        if x >= p["x"] - 1.0:
            idx = i
    return idx


# ── 스토리 → 줄, 줄 → 역할 ────────────────────────────────
def _classify(line, tr_story=True):
    """줄 하나의 역할.

    **해석 프레임**(`tr_story`)에서는 한글 해석 run 이 하나라도 있으면 그 줄
    전체가 해석이다 — 해석 줄 머리의 영어 소제목이 지문으로 새어 나가는 것을
    막는 유일한 방법이다(위 3번).

    **지문 프레임**에서는 그럴 수 없다. 안내문 지문은 영어 본문 704자 끝에
    해석 스타일 37자(해석 쪽 소제목)가 붙어 있어서, 같은 규칙을 쓰면 지문
    전체가 해석으로 넘어가고 그 지문이 통째로 사라진다(성덕1 실측).
    → 프레임의 성격은 **그 스토리에서 어느 쪽 글자가 더 많은가**로 정하고,
      지문 프레임 안에서는 줄도 글자 수로 가른 뒤 소수 쪽을 제자리로 보낸다.
    """
    got = {}
    for r in line:
        if not r["t"].strip():
            continue
        role = role_of(r["style"])
        got[role] = got.get(role, 0) + len(r["t"])
    if not got:
        # 내용이 공백뿐인 줄이라도 `상단제목` 이면 버리면 안 된다 — 주제와 요약을
        # 가르는 구분자가 바로 그 빈 run 이다(위 4번).
        if line and all(role_of(r["style"]) == "topic_sep" for r in line):
            return "topic_sep"
        return None
    if got.get("topic_sep"):
        # `상단제목` 은 **내용이 비었을 때만** 구분자다. 글자를 담고 있으면
        # 그건 주제·요약 본문이다(강동2 는 주제 177자를 이 스타일로 찍었다).
        # `got` 에는 애초에 공백 아닌 run 만 세므로 여기 온 건 전부 본문이다.
        got["topic"] = got.get("topic", 0) + got.pop("topic_sep")
    for pref in ("topic", "grammar", "exam",
                 "head_ch", "head_num", "voca", "cover"):
        if got.get(pref):
            return pref
    p = got.get("passage", 0) + got.get("snum", 0)
    t = got.get("translation", 0)
    if got.get("body"):
        # 무스타일 조각은 내용으로 가른다 — 한글이면 해석, 영어면 지문
        btxt = "".join(r["t"] for r in line
                       if role_of(r["style"]) == "body")
        if _I.han_ratio(btxt) > 0.35:
            t += got["body"]
        else:
            p += got["body"]
    if t and (tr_story or t > p):
        return "translation"
    if p:
        # 안전망 — 스타일이 영어 지문인데 내용이 한글이면 해석이다.
        if _I.han_ratio("".join(r["t"] for r in line)) > 0.35:
            return "translation"
        return "passage" if got.get("passage") else "snum"
    return None


_CHOICE = re.compile(r"[\u2460-\u2469\u24d0-\u24d9]")   # ①~⑩ · ⓐ~ⓙ


def _relabel(paras):
    """무스타일 run 에 합성 스타일을 붙인다. 이름이 없으니 **스토리**로 판정한다.

    ① 스타일 붙은 지문/해석 run 이 같은 스토리에 있으면 = 지문 프레임이다.
       무스타일 조각은 그 프레임의 본문이므로 `_SYN_BODY` → 내용으로 가른다.
       (신세대 해석 125건이 통째로 이 자리에서 새고 있었다.)
    ② 스토리 전체가 무스타일이면 주제/요약일 수도, 기출문제일 수도 있다.
       실측 1,447개를 갈라 보니 신호 셋이면 완전히 나뉜다.
         · 발문은 한국어다 — 한글로 시작하면 기출문제다(606개).
         · 선지 ①~⑤ 가 있으면 기출문제다(영어 발문 7개가 여기 걸린다).
         · 주제 줄과 요약 줄이 있어야 하므로 **두 줄 이상**이다
           (한 줄짜리 138개는 내용이 `1` 뿐인 번호 프레임이다).
       셋을 통과한 140개는 길이가 191~361자로 주제/요약 프레임 그대로였고
       400자를 넘는 것이 하나도 없었다(기출문제는 1,000자 이상).
    """
    runs = [r for p in paras for r in p["runs"] if r["t"].strip()]
    if not runs:
        return paras
    plain_runs = [r for r in runs if role_of(r["style"]) is None]
    if not plain_runs:
        return paras
    anchored = any(role_of(r["style"]) in ("passage", "translation")
                   for r in runs)
    if anchored:
        syn = _SYN_BODY
    else:
        if len(plain_runs) != len(runs):
            return paras          # 무스타일과 다른 역할이 섞였다 — 손대지 않는다
        txt = _sq("".join(r["t"] for r in runs))
        if (_I.han_ratio(txt[:40]) > 0.2 or _CHOICE.search(txt)
                or len(_I.lines_of(paras)) < 2):
            return paras          # 기출문제·번호 프레임 — 그대로 버린다
        syn = _SYN_TOPIC
    out = []
    for para in paras:
        rs = []
        for r in para["runs"]:
            if role_of(r["style"]) is None:
                r = dict(r, style=syn)
            rs.append(r)
        out.append({"style": para["style"], "runs": rs})
    return out


def _story_is_translation(paras):
    """스토리가 해석 프레임인가 — 한글 해석 글자가 영어 지문 글자보다 많은가."""
    p = t = 0
    for para in paras:
        for r in para["runs"]:
            if not r["t"].strip():
                continue
            role = role_of(r["style"])
            if role == "translation":
                t += len(r["t"])
            elif role in ("passage", "snum"):
                p += len(r["t"])
    return t > p


def _route(line):
    """줄 → [(역할, runs)]. 지문 프레임 안에 섞여 든 해석 조각을 제자리로 보낸다.

    공백만 있는 run 은 앞 그룹에 붙인다 — 해석 줄 사이사이에 영어 지문 스타일의
    공백 한 칸이 끼어 있어서, 그걸 새 그룹으로 세면 한 줄이 수십 조각이 난다.
    """
    groups = []
    for r in line:
        role = role_of(r["style"])
        if role not in ("translation", "body"):
            role = "passage"
        if not r["t"].strip() and groups:
            groups[-1][1].append(r)
            continue
        if groups and groups[-1][0] == role:
            groups[-1][1].append(r)
        else:
            groups.append([role, [r]])
    out = []
    for role, rs in groups:
        # 무스타일 조각은 제 그룹으로 모은 뒤 내용으로 가른다. 스타일 있는
        # 영어 지문과 한 그룹으로 합쳐 버리면 한글 비율이 묽어져 못 가른다.
        if role in ("passage", "body") and _I.han_ratio(
                "".join(x["t"] for x in rs)) > 0.35:
            role = "translation"
        elif role == "body":
            role = "passage"
        if out and out[-1][0] == role:
            out[-1][1].extend(rs)
        else:
            out.append([role, rs])
    return [(role, rs) for role, rs in out
            if any(x["t"].strip() for x in rs)]


def _runs(line):
    """run 을 코퍼스용으로 다시 싼다. 루비(구문분석 주석)와 의미 클래스를 보존."""
    out = []
    for r in line:
        if not r["t"]:
            continue
        mark, hl = mark_of(r["style"])
        # 합성 스타일은 우리가 붙인 것이지 원고에 있는 이름이 아니다 → 지운다
        style = "" if r["style"] in (_SYN_BODY, _SYN_TOPIC) else nfc(r["style"])
        out.append({"t": r["t"], "style": style, "mark": mark,
                    "hl": hl, "ruby": r["ruby"], "slot": r["slot"]})
    return out


# ── VOCA 표 ───────────────────────────────────────────────
_CELL = re.compile(r"^(\d+):(\d+)$")


def _tables_of(doc, story_id):
    st = doc.stories.get(story_id)
    return list(st.iter("Table")) if st is not None else []


def _voca_of(table):
    """표 → [{w, ko}]. 셀 이름은 `열:행`.

    셀에 붙은 문자 스타일은 못 믿는다 — 뜻 칸이 `어휘:단어` 로 찍힌 책이 많다.
    **짝수 열=어휘 / 홀수 열=의미**로 가르고, 한글 비율이 뒤집혀 있으면 바꾼다.
    """
    grid = {}
    for cell in table.iter("Cell"):
        m = _CELL.match(cell.get("Name") or "")
        if not m:
            continue
        col, row = int(m.group(1)), int(m.group(2))
        txt = _sq("".join(c.text or "" for c in cell.iter("Content")))
        grid[(col, row)] = txt
    if not grid:
        return []
    ncol = max(c for c, _ in grid) + 1
    out = []
    for row in sorted(set(r for _, r in grid)):
        for col in range(0, ncol - 1, 2):
            w = grid.get((col, row), "")
            ko = grid.get((col + 1, row), "")
            if not w and not ko:
                continue
            if _I.han_ratio(w) > _I.han_ratio(ko) and ko:
                w, ko = ko, w          # 열이 뒤집힌 책 보정
            out.append({"w": w, "ko": ko})
    return out


# ── 주제 / 요약 ───────────────────────────────────────────
def _split_topic(items):
    """주제/요약 조각들 → (주제, 요약, 경계이름).

    **원고 세대마다 경계가 다르다**(실측 104권).

      · 25-2-기말 구세대 — 532면 중 전부 `주제/요약:상단제목` 구분자 2개.
        주제와 요약이 **한 줄**에 붙어 있는 면이 300개라 줄바꿈으로는 못 가른다.
      · 26-2-중간 신세대 — 532면 중 453면에 **구분자가 아예 없고**, 대신
        주제와 요약이 **단락**으로 갈려 있다. 나머지 79면은 구분자가 남아 있다.

    → 구분자가 하나라도 있으면 구분자가 경계고(줄바꿈은 무시한다),
      하나도 없으면 줄바꿈이 경계다. 세대를 파일명이나 폴더로 묻지 않는다.

    둘 다 안 되면 **통째로 주제에 넣지 않는다.** 포켓북 오른쪽 면은 주제 줄과
    요약 줄을 따로 찍는데, 주제 줄이 비면 눈에 띄지만 두 개가 한 문단으로
    붙어 나오면 오래 안 보인다 → 요약에 넣고 주제를 비운 뒤 note 를 남긴다.
    """
    def is_sep(r):
        # 구분자는 **빈** `상단제목` run 이다(위 규칙과 같은 판정).
        return role_of(r["style"]) == "topic_sep" and not r["t"].strip()

    has_sep = any(kind == "sep" for kind, _ in items) or any(
        is_sep(r) for kind, line in items for r in line if kind == "line")
    # ⚠ run 은 붙이고 줄은 띄운다. 자간 오버라이드 때문에 낱말 한가운데서
    #   run 이 갈린 원고가 있어서(강동2), run 사이에 공백을 넣으면
    #   `The wo rd "hip-hop"` 처럼 낱말이 갈라진다.
    segs, cur = [], []

    def flush():
        segs.append(" ".join(cur))
        del cur[:]

    for kind, line in items:
        if kind == "sep":
            flush()
            continue
        parts = []
        for r in line:
            if is_sep(r):
                if parts:
                    cur.append("".join(parts))
                    parts = []
                flush()
            elif r["t"]:
                parts.append(r["t"])
        if parts:
            cur.append("".join(parts))
        if not has_sep:
            # 구분자가 없는 세대에서는 줄 하나가 곧 조각 하나다
            flush()
    flush()
    segs = [x for x in (_sq(x) for x in segs) if x]
    how = "상단제목 구분자" if has_sep else "줄바꿈"
    if not segs:
        return "", "", how
    if len(segs) == 1:
        return "", segs[0], "못 가름(주제 비움)"
    return segs[0], _sq(" ".join(segs[1:])), how


# ── 지문 키 ───────────────────────────────────────────────
def passage_no(label):
    """`고1 25년 9월 29번` → `250929`, `고2 25년 9월 43~45번` → `250943~45`.

    이건 역할 판정이 아니라 **키 유도**다. 못 읽으면 조용히 빈 문자열을 내고
    label 을 원문 그대로 남긴다 — 절대 게이트로 쓰지 않는다.
    """
    m = _MOCK.search(nfc(label))
    if not m:
        return ""
    yy, mm, n1, n2 = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    pno = "%s%02d%02d" % (yy, mm, n1)
    if n2:
        pno += "~%02d" % int(n2)
    return pno


# ── 본체 ──────────────────────────────────────────────────
def _unit_key(u):
    return (u["head_num"], u["head_ch"])


def read_book(path):
    """분석본 IDML → [지문]. 반환 모양은 idml.read_book() 과 같다.

    passage/translation 은 idml.py 와 같이 **문단 목록**이다
    (`[{"style":…, "runs":[{"t","mark","hl","ruby","slot"}]}]`).
    분석본은 문장별 해석이지만 포켓북은 지문 전체 해석 한 덩이라
    **해석은 여기서 합친다.**
    """
    doc = _I.Idml(path)
    base = nfc(os.path.basename(path))
    raw = []          # 면 단위 조각

    for si, sp in enumerate(_spreads_ex(doc)):
        npages = max(1, len(sp["pages"]))
        # 면 단위 버킷
        bucket = [{"lines": [], "voca": [], "head_ch": "", "head_num": "",
                   "page": (sp["pages"][i]["name"] if i < len(sp["pages"])
                            else ""),
                   "master": (sp["pages"][i]["master"] if i < len(sp["pages"])
                              else ""),
                   "nhead": 0}
                  for i in range(npages)]
        seen = set()
        for fr in sp["frames"]:
            sid = fr["story"]
            if sid in seen:
                continue          # 한 스토리가 여러 프레임에 흐른다 — 한 번만
            seen.add(sid)
            paras = _relabel(doc.paragraphs(sid))
            tabs = _tables_of(doc, sid)
            if not paras and not tabs:
                continue
            pi = _page_index(sp["pages"], fr["x"]) if sp["pages"] else 0
            pi = min(pi, npages - 1)
            b = bucket[pi]
            for t in tabs:
                b["voca"].extend(_voca_of(t))
            trs = _story_is_translation(paras)
            lines = [(_classify(l, trs), l) for l in _I.lines_of(paras)]
            body = sum(len("".join(r["t"] for r in l).strip())
                       for k, l in lines if k in ("passage", "translation"))
            if body and body < 30:
                # 편집 메모(`<< 여기서 변경`)가 지문 스타일로 남은 프레임
                continue
            for k, l in lines:
                if k == "head_ch":
                    b["head_ch"] = _join_head(b["head_ch"],
                                              "".join(r["t"] for r in l))
                    b["nhead"] += 1
                elif k == "head_num":
                    b["head_num"] = _join_head(b["head_num"],
                                               "".join(r["t"] for r in l))
                elif k:
                    b["lines"].append((k, l, sid, trs))
        for b in bucket:
            b["spread"] = si
        # 스프레드 안에서 지문이 하나인가 둘인가 — 머리말로 가른다(위 5번)
        heads = [(b["head_num"], b["head_ch"]) for b in bucket
                 if b["head_ch"] or b["head_num"]]
        if len(bucket) > 1 and len(heads) > 1 and len(set(heads)) > 1:
            raw.extend(bucket)                 # 면마다 지문 하나 (짤지문)
        else:
            merged = {"lines": [], "voca": [], "spread": si,
                      "head_ch": "", "head_num": "",
                      "page": [b["page"] for b in bucket],
                      "master": [b["master"] for b in bucket]}
            for b in bucket:
                merged["lines"].extend(b["lines"])
                merged["voca"].extend(b["voca"])
                merged["head_ch"] = merged["head_ch"] or b["head_ch"]
                merged["head_num"] = merged["head_num"] or b["head_num"]
            raw.append(merged)

    for b in raw:
        if not isinstance(b["page"], list):
            b["page"] = [b["page"]]
            b["master"] = [b["master"]]

    # 지문이 없는 조각(간지·빈 면)은 버린다
    units = [b for b in raw
             if any(k == "passage" for k, _, _s, _t in b["lines"])]

    # 같은 머리말이 이어지면 한 지문이다(장문 43~45번·외부지문 연재)
    merged = []
    for u in units:
        if (merged and _unit_key(u) == _unit_key(merged[-1])
                and (u["head_ch"] or u["head_num"])):
            m = merged[-1]
            m["lines"].extend(u["lines"])
            m["voca"].extend(u["voca"])
            m["page"].extend(u["page"])
            m["master"].extend(u["master"])
        else:
            merged.append(u)
    units = merged

    notes = []
    # 머리말이 간지에 통째로 쌓인 책 — 개수가 딱 맞을 때만 순서대로 얹는다
    if units and not any(u["head_ch"] or u["head_num"] for u in units):
        nums, chs = _header_pile(doc)
        n = len(units)
        got = []
        # 더미 맨 앞에는 템플릿에서 딸려온 남의 머리말이 한 벌 섞여 있다
        # (`능률(오) 1과 / A Journey into Yourself`) → **뒤에서부터** n 개.
        for slot, pile in (("head_num", nums), ("head_ch", chs)):
            if len(pile) >= n:
                for u, h in zip(units, pile[-n:]):
                    u[slot] = h
                got.append(slot)
        if got:
            notes.append("머리말이 간지 면에 쌓여 있어 뒤에서 %d개를 순서대로 "
                         "얹음(%s)" % (n, ",".join(got)))
        else:
            notes.append("머리말 없음 — 간지 더미(숫자%d·챕터%d)가 지문 %d개보다 "
                         "적어 얹지 않음" % (len(nums), len(chs), n))

    chs = [u["head_ch"] for u in units]
    nums = [u["head_num"] for u in units]
    out = []
    for u in units:
        out.append(_build(u, base, chs, nums, notes))
    for d in out:
        _cut_extras(d)
    return _drop_summary_pages(out)


# 26-2 분석본은 지문 뒤에 **영어 요약과 문장삽입 문제**를 같은 글에 이어 붙인다
# (`… ( ① ) … ( ⑤ ) 답: ③`). 문자 스타일이 지문과 **똑같아서** 스타일로는 못
# 가른다 — 그대로 두면 문제와 정답까지 본문에 인쇄된다(광문1 2강 02 실측).
_RE_EXTRA = re.compile(r"\(\s*[①②③④⑤⑥]\s*\)|답\s*[:：]")
# 해석 쪽에는 문장 번호가 없어서 번호로 못 자른다 — **발문**을 알아본다.
# (`글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳은?`)
# 발문은 늘 정해진 말로 시작한다 — 그 자리에서 자른다. 끝에서만 찾으면
# `Becky Bloom 드림` 같은 맺음말까지 함께 잘린다(실측).
_RE_PROMPT = re.compile(
    r"(?:다음 글|윗글|글의 흐름으로 보아|주어진 문장|위 글)[^?]*\?\s*$")
_SENT_TAIL = ('.', '?', '!', '\u201d', '"', "'")


_RE_SUMHEAD = re.compile(r"(요약|주제|정답|해설|다음 글|윗글|밑줄|빈칸|어법|"
                         r"[①②③④⑤]|Summary|Topic)")


def _strip_korean_runs(d):
    """영어 지문에 **끼어든 한글 줄**을 걸러 낸다(실용문).

    안내문·도표 지문은 분석본이 영어 항목 바로 밑에 우리말을 나란히 앉혀 둔다.
    그 줄이 영어 본문에 그대로 섞여 인쇄됐다(`- Oakwood University 컴퓨터실`,
    `• 1등: 300달러` 등, 연구원 지적 8건).

    ⚠ 지문 전체가 한글인 것(해석)까지 지우면 안 된다. **영어 지문**(한글 비율
      20% 미만)에서, **한글이 4분의 1을 넘는 런**만 덜어 낸다.
    """
    paras = d.get("passage") or []
    if not paras:
        return
    runs = paras[0].get("runs") or []
    txt = "".join(r.get("t", "") for r in runs)
    if not txt:
        return
    han = sum(1 for c in txt if "\uac00" <= c <= "\ud7a3")
    if han / len(txt) >= 0.20:          # 한글 지문이면 손대지 않는다
        return
    keep, cut = [], 0
    for r in runs:
        t = r.get("t", "")
        h = sum(1 for c in t if "\uac00" <= c <= "\ud7a3")
        if t.strip() and h and h / len(t) > 0.25:
            cut += 1
            continue
        keep.append(r)
    if cut:
        paras[0]["runs"] = keep
        d.setdefault("notes", []).append("영어 지문에 섞인 한글 %d줄 걸러 냄" % cut)


def _is_extra(tail):
    """이 꼬리가 **지문이 아니라 부속물**(요약·문제)이라는 증거가 있는가.

    ⚠ 길이만 보고 자르면 안 된다 — 번호가 안 붙은 진짜 마지막 문장이 길면
      통째로 사라진다(실측 5지문). 증거는 셋이다:
      ① 문항 표시(`( ① )`·`답:`) ② 요약·발문 낱말 ③ **한글이 섞인 영어 지문**
    """
    if not tail:
        return False
    if _RE_EXTRA.search(tail) or _RE_SUMHEAD.search(tail):
        return True
    han = sum(1 for c in tail if "\uac00" <= c <= "\ud7a3")
    return han / max(len(tail), 1) > 0.2


def _cut_extras(d):
    """지문 뒤에 붙은 요약·문제를 잘라 낸다 — **마지막 번호 문장까지**만 남긴다.

    가르는 것은 **문장 번호**(`지문분석:지문 번호`)다. 진짜 지문은 문장마다
    번호가 붙어 오고, 뒤에 붙은 요약과 문제에는 하나도 없다.
    """
    _strip_korean_runs(d)
    for key in ("passage", "translation"):
        paras = d.get(key)
        if not paras:
            continue
        runs = paras[0].get("runs") or []
        runs = paras[0].get("runs") or []
        nums = [i for i, r in enumerate(runs) if r.get("mark") == "snum"]
        if not nums:
            _cut_prompt(paras[0])       # 번호가 없으면 발문만 떼어 낸다(해석 쪽)
            continue
        end, seen = len(runs), 0
        for j in range(nums[-1] + 1, len(runs)):
            t = runs[j].get("t", "")
            if t.rstrip().endswith(_SENT_TAIL):
                end = j + 1
                break
            # ⚠ 마지막 문장이 마침표로 안 끝나는 글도 있다(`Warm regards, Becky
            #   Bloom`). 그럴 땐 **빈 런 다음에 긴 글이 오는 자리**가 경계다.
            if seen and not t.strip() and j + 1 < len(runs) \
                    and len(runs[j + 1].get("t", "")) >= 25:
                end = j
                break
            if t.strip():
                seen += 1
        tail = "".join(r.get("t", "") for r in runs[end:]).strip()
        # 문제(`( ① )`)가 없고 **요약문만** 붙는 경우도 있다(광문1 1강 분석).
        # ⚠ 예전엔 꼬리가 **40자만 넘으면** 잘랐다. 그래서 번호가 안 붙은 진짜
        #   마지막 문장이 통째로 사라졌다(`It's better to include all of the
        #   information…` 등 5지문, 연구원 지적). 이제 **요약·문제라는 증거**가
        #   있을 때만 자른다 — 글은 증거 없이 지우지 않는다.
        if end < len(runs) and _is_extra(tail):
            paras[0]["runs"] = runs[:end]
        else:
            _cut_prompt(paras[0])
            d.setdefault("notes", []).append(
                "지문 뒤 요약·문제 %d런을 잘라 냄" % (len(runs) - end))


def _has_snum(p):
    """문장 번호(`지문분석:지문 번호`)가 하나라도 있는가."""
    for para in (p.get("passage") or []):
        for r in para.get("runs") or []:
            if r.get("mark") == "snum":
                return True
    return False


def _drop_summary_pages(items):
    """지문이 아닌 **영어 요약 면**을 버린다.

    26-2 중간부터 분석본에 강마다 영어 요약 면이 한 장씩 붙었다(광문1
    분석본03 이 9/2 에 그렇게 바뀌었다). 겉모양이 지문과 같아서 그대로 두면
    지문 수가 부풀고 오른쪽 면이 빈 채로 인쇄된다.

    가르는 것은 **문장 번호**다 — 진짜 지문은 `1 Dear valued players,` 처럼
    번호가 붙어 오고, 요약 면에는 하나도 없다. 책 전체에 번호가 아예 없는
    옛 분석본도 있으므로 **번호를 쓰는 책에서만** 걸러 낸다.
    """
    if not items or not any(_has_snum(p) for p in items):
        return items
    # ⚠ 버리는 면에 **중요어휘 표**가 얹혀 있는 책이 있다(광문1 분석본03: 한
    #   스프레드에 표가 하나인데 그것이 요약 면 쪽에 있다). 그냥 버리면 어휘표가
    #   같이 사라져 동반의어를 뽑을 근거가 없어진다 — 옆 지문에 넘긴다.
    keep = []
    carry = []
    for p in items:
        if _has_snum(p):
            if carry and not p.get("voca"):
                p["voca"] = carry.pop(0)
            keep.append(p)
        elif p.get("voca"):
            if keep and not keep[-1].get("voca"):
                keep[-1]["voca"] = p["voca"]
            else:
                carry.append(p["voca"])
    return keep if keep else items


def _header_pile(doc):
    """간지(첫) 스프레드에 쌓인 머리말 프레임을 문서 순서대로 → (숫자칸, 챕터칸).

    두 칸을 **따로** 모은다. 프레임 순서가 칸끼리 섞여 있어서 짝을 인접으로
    맞추면 틀린다(한영1 실측). 칸마다 개수만 보고 뒤에서부터 얹는다.
    """
    nums, chs = [], []
    for sp in _spreads_ex(doc):
        seen = set()
        for fr in sp["frames"]:
            if fr["story"] in seen:
                continue
            seen.add(fr["story"])
            for p in doc.paragraphs(fr["story"]):
                for r in p["runs"]:
                    if not r["t"].strip():
                        continue
                    role = role_of(r["style"])
                    if role == "head_num":
                        nums.append(_sq(r["t"]))
                    elif role == "head_ch":
                        chs.append(_sq(r["t"]))
        break
    return nums, chs


# 머리말을 `[01]` 처럼 대괄호로 적어 둔 분석본이 있다(광문1 올포 6강). 그대로
# 두면 배지가 `올림포스 6강 [01]` 로 찍혀 다른 강(`올림포스 6강 01`)과 어긋난다.
_RE_BRACKET_NO = re.compile(r"^[\[［]\s*(\d{1,3})\s*[\]］]$")


def _tidy_label(label):
    m = _RE_BRACKET_NO.match((label or "").strip())
    return m.group(1) if m else label


def _label_of(u, chs, nums):
    """라벨은 **변별력**으로 고른다 — 학교마다 어느 칸이 지문을 가리키는지 다르다.

      모의고사  챕터_숫자='모의고사'(고정)  챕터='고1 25년 9월 29번'(변별)
      교과서    챕터_숫자='3과 본문1'(변별) 챕터='Our Heritage…'(과 제목, 고정)
      올림포스  둘 다 변별('올포 14-1' / '고2 24년 9월 34번')

    ① 지문 키가 나오는 칸이 있으면 그것. ② 없으면 책 안에서 **한 번만 나오는**
    칸(=그 지문만 가리키는 칸). ③ 둘 다 아니면 붙여 쓴다.
    """
    ch, num = u["head_ch"], u["head_num"]
    if passage_no(ch):
        return ch, num
    if passage_no(num):
        return num, ch
    u_ch = ch and chs.count(ch) == 1
    u_num = num and nums.count(num) == 1
    if u_ch and not u_num:
        return ch, num
    if u_num and not u_ch:
        return num, ch
    return _sq(num + " " + ch), ""


def _split_title(line):
    """해석 첫 줄 머리의 **소제목**을 떼어 낸다 → (영어제목, 한글제목, 남은 run).

    교과서 분석본은 해석 프레임 머리에 소제목을 영어·한글로 붙여 둔다.
        [영어 지문]Rescuing Cultural Treasures [한글]문화유산 구하기 [한글]제2차 세계…
    완성 포켓북은 이 소제목을 **지문 머리로 옮겨** 조판한다(실측). 떼어 놓아야
    두 출처의 passage·translation 이 글자까지 맞는다(G-P7).

    경계를 글자 수로 추측하지 않는다 — InDesign 이 남긴 **run 경계**가 곧 경계다.
    """
    i = 0
    en = []
    while i < len(line) and role_of(line[i]["style"]) == "passage":
        en.append(line[i]["t"])
        i += 1
    if not i or not "".join(en).strip():
        return "", "", line
    rest = line[i:]
    # 뒤따르는 run 이 없으면 제목이 아니라 편집 메모다(`<< 여기서 변경`).
    # 한글 제목이 한 줄에 같이 오는 책도, 다음 줄로 넘어가는 책도 있어서
    # **줄 길이가 아니라 run 이 남는지**로만 가른다.
    if not rest or not rest[0]["t"].strip():
        return "", "", line
    # 영어 제목 다음 run 이 한글이라야 '영어 제목 + 한글 제목'이다.
    # 안내문 지문은 영어가 이어지므로 손대지 않는다.
    if _I.han_ratio(rest[0]["t"]) < 0.2:
        return "", "", line
    return _sq("".join(en)), _sq(rest[0]["t"]), rest[1:]


def _build(u, base, chs, nums, notes):
    lines = u["lines"]
    p_runs, t_runs = [], []
    grammar, exam, sentences = [], [], []
    title_en = title_ko = ""
    topic_items = []
    pend_en, prev_sid = None, None
    for kind, line, sid, tr_story in lines:
        txt = _sq("".join(r["t"] for r in line))
        if sid != prev_sid:
            # 스토리가 바뀌면 정렬을 끊는다. 지문 스토리와 해석 스토리가 따로인
            # 책(광문1·배재1)에서 마지막 문장과 첫 해석이 짝으로 붙어 버린다.
            pend_en, prev_sid = None, sid
        if kind not in ("passage", "translation", "snum"):
            pend_en = None          # 사이에 다른 것이 끼면 짝이 아니다
        if kind == "passage":
            for role, rs in (_route(line) if not tr_story
                             else [("passage", line)]):
                bucket = p_runs if role == "passage" else t_runs
                if bucket:
                    bucket.append({"t": " ", "style": "", "mark": None,
                                   "hl": None, "ruby": None, "slot": None})
                bucket.extend(_runs(rs))
                if role == "passage":
                    pend_en = _sq("".join(r["t"] for r in rs))
        elif kind == "translation":
            if not t_runs and not title_en:
                title_en, title_ko, line = _split_title(line)
                txt = _sq("".join(r["t"] for r in line))
                if not line:
                    continue
            if t_runs:
                t_runs.append({"t": " ", "style": "", "mark": None,
                               "hl": None, "ruby": None, "slot": None})
            t_runs.extend(_runs(line))
            if pend_en is not None:
                # 한 스토리에서 문장↔해석이 교차하는 책은 정렬이 공짜로 나온다
                sentences.append({"en": pend_en, "ko": txt})
                pend_en = None
        elif kind == "topic_sep":
            # 구분자만 있는 줄(공백 run) — 조각 경계로만 쓴다
            topic_items.append(("sep", line))
        elif kind == "topic":
            # 구분자는 줄이 아니라 **줄 안의 run** 으로 오기도 한다(구세대는
            # 주제·요약이 한 줄에 붙어 있다) → 자르기는 _split_topic 이 한다.
            topic_items.append(("line", line))
        elif kind == "grammar":
            grammar.append(txt)
        elif kind == "exam":
            exam.append(txt)
    topic, summary, how = _split_topic(topic_items)

    label, chapter = _label_of(u, chs, nums)
    label = _tidy_label(label)
    pno = passage_no(label) or passage_no(u["head_ch"]) or passage_no(
        u["head_num"])

    d = {
        "pno": pno,
        "label": label,
        "chapter": chapter,
        "labels": {"chapter": u["head_ch"], "number": u["head_num"]},
        "pages": [p for p in u["page"] if p],
        "masters": sorted(set(m for m in u["master"] if m)),
        "passage": ([{"style": "본문", "runs": p_runs}] if p_runs else None),
        "translation": ([{"style": "한글", "runs": t_runs}] if t_runs else None),
        "flownote": [],          # 분석본에 없다 — 플로우노트DB 가 채운다
        "title": {"en": title_en, "ko": title_ko},
        "topic": topic,
        "summary": summary,
        "synonyms": [],          # 분석본에 없다 — 완성본 하베스트/원고가 채운다
        "voca": u["voca"],       # 동반의어 씨앗
        "grammar": grammar,      # GRAMMAR POINT(어법 설명)
        "exam": exam,            # 핵심기출문제
        "sentences": sentences,  # 문장↔해석 정렬(교차형 원고에서만 채워진다)
        # 분석본에는 걸린 그림이 하나도 없다(36권 실측). 삽화는 GDrive
        # `포켓북 삽화정리/` 에서 지문 키로 붙인다 — 그래서 빈 채로 둔다.
        "links": [],
        "source": {"from": "idml-analysis", "file": base,
                   "spread": u["spread"], "notes": list(notes),
                   "topic_split": (how if topic_items else "")},
    }
    return d


# ── 검수 ──────────────────────────────────────────────────
def summarize(passages):
    """지문 목록 → 한 줄 통계. 게이트(G-P2·G-P3)의 씨앗."""
    def n(p, k):
        return sum(len(r["t"]) for pp in (p[k] or ()) for r in pp["runs"])
    return {
        "n": len(passages),
        "ruby": sum(1 for p in passages for pp in (p["passage"] or ())
                    for r in pp["runs"] if r["ruby"]),
        "no_translation": [p["label"] for p in passages if not p["translation"]],
        "no_topic": [p["label"] for p in passages if not p["topic"]],
        "no_summary": [p["label"] for p in passages if not p["summary"]],
        "no_label": [p["source"]["spread"] for p in passages if not p["label"]],
        "no_pno": [p["label"] for p in passages if not p["pno"]],
        "voca": sum(len(p["voca"]) for p in passages),
        "short": [p["label"] for p in passages if n(p, "passage") < 200],
        "notes": (passages[0]["source"]["notes"] if passages else []),
        # 주제/요약 경계를 무엇으로 잡았나 — 세대가 섞이면 여기서 드러난다
        "topic_split": sorted(set(p["source"]["topic_split"]
                                  for p in passages if p["source"]["topic_split"])),
        "topic_unsplit": [p["label"] for p in passages
                          if p["source"]["topic_split"].startswith("못 가름")],
    }


if __name__ == "__main__":
    import json
    import sys
    ps = read_book(os.path.expanduser(sys.argv[1]))
    s = summarize(ps)
    print("지문 %d개 · 루비 %d개 · VOCA %d개" % (s["n"], s["ruby"], s["voca"]))
    for m in s["notes"]:
        print("  · %s" % m)
    print("  경계:", s["topic_split"])
    for k in ("no_translation", "no_topic", "no_summary", "no_label",
              "topic_unsplit", "short"):
        if s[k]:
            print("  ⚠ %s: %s" % (k, s[k][:6]))
    for p in ps[:2]:
        print("─" * 66)
        print("pno=%r label=%r chapter=%r pages=%s"
              % (p["pno"], p["label"], p["chapter"], p["pages"]))
        print("지문:", _sq("".join(r["t"] for pp in p["passage"]
                                 for r in pp["runs"]))[:110])
        print("해석:", _sq("".join(r["t"] for pp in (p["translation"] or ())
                                 for r in pp["runs"]))[:110])
        print("주제:", p["topic"][:70])
        print("요약:", p["summary"][:70])
        print("루비:", [(r["t"], r["ruby"], r["slot"])
                      for pp in p["passage"] for r in pp["runs"]
                      if r["ruby"]][:6])
        print("VOCA:", p["voca"][:4], "| 문장정렬", len(p["sentences"]))


def _cut_prompt(para):
    """문단 끝의 **발문 한 문장**을 잘라 낸다(해석 쪽)."""
    runs = para.get("runs") or []
    txt = "".join(r.get("t", "") for r in runs)
    m = _RE_PROMPT.search(txt)
    if not m or m.start() == 0:
        return
    cut, keep, seen = m.start(), [], 0
    for r in runs:
        t = r.get("t", "")
        if seen + len(t) <= cut:
            keep.append(r)
        elif seen < cut:
            keep.append(dict(r, t=t[:cut - seen]))
        seen += len(t)
    para["runs"] = keep
