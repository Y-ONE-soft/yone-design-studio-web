"""동형모의고사 v2 파서 — 원고 → content.json v2 (표준 문항 IR).

새 아키텍처 파일럿: core.extract(추출) → core.structure(단락종류/유형)
→ 문항 그룹핑 → v2 IR (core.schema 검증).

기존 engines/mockexam(v1)과 완전 분리 — v1은 무변경 운영.
"""
import os
import re
import unicodedata

from core.extract import (
    _docx_extract_paragraphs,
    _hwp_extract_paragraphs,
    _hwp_is_hwpx,
    _hwpx_extract_paragraphs,
)
from core.structure import classify_paragraphs

# 발문 머리 번호/마커: "1." / "서술형1." / "[1~2]" / "1~2."
_RE_NUM = re.compile(r'^\s*(\d+)\s*[.)]\s*')
_RE_SRV_NUM = re.compile(r'^\s*서술형\s*(\d+)\s*[.)]?\s*')
_RE_GROUP = re.compile(r'^\s*\[(\d+)\s*[~\-]\s*(\d+)\]\s*')
# 묶음 머리는 **괄호 종류가 학교마다 다르다** — 대괄호만 보면 놓친다.
#   배재 【 8 – 9 】 / 강동2 (1~3) / 한영3 <1~2> / 상일2 [1~5] / 명일1 ※ [2~3]
# 표기가 아니라 '범위를 선언한 머리' 라는 구조로 잡는다.
_RE_RANGE_HEAD = re.compile(
    r'^\s*[※▶]?\s*[\[(<【〈]\s*(?:선택형|객관식)?\s*(\d{1,2})\s*[~\-–—]\s*'
    r'(?:서답형|서술형)?\s*(\d{1,2})\s*[\])>】〉]')
# 인라인 선지 분할: "① in    ② of    ③ to ..." 한 단락에 여러 선지
_RE_CIRCLED_SPLIT = re.compile(r'(?=[①②③④⑤])')
# 출처/배점: "[24년 10월 20번]" / "[3점]" / "(3점)"
_RE_SOURCE = re.compile(r'\[(\d{2}년\s*\d{1,2}월\s*\d{1,3}번[^\]]*)\]')
_RE_SCORE = re.compile(r'[\[(](\d+(?:\.\d+)?)\s*점[\])]')


# ── 원고 그림 ──────────────────────────────────────────────────────────────
# 도표 문항은 그림이 빠지면 문제가 성립하지 않는다(성덕1·성덕2·강동2 실증).
# 공유 추출기는 텍스트만 넘기므로 여기서 따로 훑어 제자리에 꽂는다.
_RE_HP_T = re.compile(r"<hp:t>(.*?)</hp:t>", re.S)
_RE_HP_PIC = re.compile(r"<hp:pic\b")
_RE_BIN_ID = re.compile(r'binaryItemIDRef="([^"]+)"')
_RE_HP_SZ = re.compile(r'<hp:sz[^>]*width="(\d+)"[^>]*height="(\d+)"')


def _hwpx_pictures(path):
    """원고 안 그림 목록. [{"anchor", "data", "ext", "w_mm", "h_mm"}]

    anchor = 그림 **직전** 텍스트(짧은 꼬리). 그 텍스트를 가진 단락 뒤에 꽂는다.
    """
    import zipfile
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return []
    names = z.namelist()
    bins = {}
    for n in names:
        if n.startswith("BinData/"):
            bins[os.path.basename(n).split(".")[0].lower()] = n
    if not bins:
        return []
    out = []
    for sec in sorted(n for n in names if "section" in n.lower()):
        try:
            xml = z.read(sec).decode("utf-8", "ignore")
        except Exception:
            continue
        for m in _RE_HP_PIC.finditer(xml):
            head = xml[:m.start()]
            texts = [t for t in (_unescape_xml(x) for x in _RE_HP_T.findall(head))
                     if t.strip()]
            anchor = texts[-1].strip() if texts else ""
            tail = xml[m.start():m.start() + 1200]
            bid = _RE_BIN_ID.search(tail)
            key = (bid.group(1).lower() if bid else "")
            path_in = bins.get(key) or bins.get(key.lstrip("0")) or \
                (list(bins.values())[0] if len(bins) == 1 else None)
            if not path_in:
                continue
            sz = _RE_HP_SZ.search(tail)
            w = h = None
            if sz:
                w = round(int(sz.group(1)) / 7200 * 25.4, 1)
                h = round(int(sz.group(2)) / 7200 * 25.4, 1)
            out.append({"anchor": anchor, "data": z.read(path_in),
                        "ext": os.path.splitext(path_in)[1].lower(),
                        "w_mm": w, "h_mm": h})
    return out


def _unescape_xml(t):
    return (t.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&amp;", "&").replace("&quot;", '"'))


def _attach_pictures(paras, path):
    """그림을 단락 목록의 제자리에 꽂는다(그림 전용 단락으로)."""
    if os.path.splitext(path)[1].lower() not in (".hwpx", ".hwp"):
        return paras
    pics = _hwpx_pictures(path)
    if not pics:
        return paras
    out = list(paras)
    for pic in pics:
        at = None
        a = (pic.get("anchor") or "").strip()
        if a:
            for i, p in enumerate(out):
                if a and a in (p.get("text") or ""):
                    at = i + 1
            # 마지막 일치 지점을 쓴다 — 같은 문구가 앞에도 나올 수 있다
        if at is None:
            # 앵커를 못 찾으면 도표를 묻는 발문 뒤에 둔다
            for i, p in enumerate(out):
                if "도표" in (p.get("text") or ""):
                    at = i + 1
                    break
        if at is None:
            continue
        out.insert(at, {"text": "", "runs": [], "image": pic})
    return out


def extract_file_paragraphs(path):
    """파일 확장자별 core.extract 위임 (밑줄 포함)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _docx_extract_paragraphs(path, extract_underline=True)
    if ext == ".hwpx":
        return _attach_pictures(
            _hwpx_extract_paragraphs(path, extract_underline=True,
                                     exclude_footnotes=True), path)
    if ext == ".hwp":
        if _hwp_is_hwpx(path):
            return _attach_pictures(
                _hwpx_extract_paragraphs(path, extract_underline=True,
                                         exclude_footnotes=True), path)
        return _hwp_extract_paragraphs(path, extract_underline=True,
                                       exclude_footnotes=True)
    raise ValueError(f"지원하지 않는 형식: {ext}")



# 원문자 정규화 ─────────────────────────────────────────────────────────────
# 원고가 `➀`(U+2780 DINGBAT) 와 `①`(U+2460) 을 섞어 쓴다 — 같은 학교 원고 안에서도
# 문항마다 갈린다(성덕·상일·명일2 실증). 눈에는 같아 보이지만 코드가 달라서
# **딩벳 쪽 선지는 선지로 인식조차 안 되고 UNKNOWN 으로 남는다**(성덕1 2회:
# 선지 5줄이 통째로 지문 취급). 분류 전에 한 벌로 접는다.
_DINGBAT_MAP = {chr(0x2780 + i): chr(0x2460 + i) for i in range(10)}      # ➀~➉
_DINGBAT_MAP.update({chr(0x2776 + i): chr(0x2460 + i) for i in range(10)})  # ❶~❿
_RE_DINGBAT = re.compile("[" + "".join(_DINGBAT_MAP) + "]")


def normalize_marks(text):
    """원문자 이형(딩벳)을 표준 원문자로. 표시는 같고 코드만 다른 것들."""
    if not text:
        return text
    return _RE_DINGBAT.sub(lambda m: _DINGBAT_MAP[m.group(0)], text)


def _clean_question(text):
    """발문에서 머리 번호와 꼬리 출처 태그를 떼고 발문 본문만.

    출처 태그(`[23년 3월 20번]`)를 분류 단계에서만 떼고 저장은 그대로 두면
    두 번 손해다 — 저장된 발문이 `…쓰시오. [23년 3월 20번]` 으로 끝나 어미
    판정이 막히고(서술형이 미판정으로 남음), 시험지에도 태그가 인쇄된다.
    """
    from core.structure import rules as _R
    t = _R.SOURCE_TAG_TRAIL.sub("", text or "")
    t = _RE_GROUP.sub("", t)
    t = _RE_SRV_NUM.sub("", t)
    t = _RE_NUM.sub("", t)
    return t.strip()


def _header_of(text):
    """발문 텍스트 → header dict (marker/group/score/source)."""
    header = {"marker": None, "group_id": None, "source": None, "score": None}
    m = _RE_GROUP.match(text)
    if m:
        header["group_id"] = f"G-{m.group(1)}-{m.group(2)}"
        header["marker"] = m.group(0).strip()
    m = _RE_SRV_NUM.match(text)
    if m:
        header["marker"] = f"서술형{m.group(1)}."
    else:
        m = _RE_NUM.match(text)
        if m and not header["marker"]:
            header["marker"] = f"{m.group(1)}."
    m = _RE_SOURCE.search(text)
    if m:
        header["source"] = m.group(1)
    m = _RE_SCORE.search(text)
    if m:
        header["score"] = float(m.group(1))
    return header


# 인라인 마커형: 선지/위치가 본문 안 ①~⑤로 존재 — 별도 선지 단락 없음이 정상
_RE_INLINE_TYPE = re.compile(r'-UND-|FLW-IRRELEVANT|FLW-INSERT|GRM-CORRECT')

# 하위 물음 마커: "(1) ..." — 다부문 문항("물음에 답하시오" 헤더)의 내부 번호.
# 새 문항 경계가 아니라 직전 문항의 하위 물음이다 (오버레이 조건은 build_ir 참조).
_RE_SUBITEM = re.compile(r'^\s*\(\d+\)\s')
_MULTIPART_HINT = "물음에 답하"


# ── 객관식/서술형은 **구조**로 가른다 ───────────────────────────────────────
# 종전에는 taxonomy 발문 정규식이 물어온 코드의 접두(OBJ/SRV)로만 갈랐다.
# 그래서 룰이 못 맞추면 kind 가 None 이 되고(원고 30부에서 미분류 다수),
# 서술형은 선언 4~8문항인데 0~4개만 잡혔다. 발문 문구는 학교·출제자마다
# 달라지지만 **문항의 구조는 안 변한다**:
#   · 답 쓰는 자리(답란)가 있으면 서술형이다.
#   · 고를 선지가 있으면 객관식이다.
#   · 선지 단락이 없어도 지문 안에 ①~⑤ 자리표가 있으면 객관식이다(밑줄·삽입형).
# 답란이 선지보다 우선한다 — 서술형이 <보기>로 ①~⑤ 목록을 주는 일이 흔해서
# (배재1 서답형3: <보기> ①~⑤ 중 고른 뒤 고쳐 쓰는 문항) 선지를 먼저 보면 뒤집힌다.
_RE_INLINE_CIRCLED = re.compile(r'[①-⑮]')
# `시오` 하나로는 못 가른다 — **고르시오는 객관식, 쓰시오는 서술형**이다.
# 어미가 같아도 시키는 일이 다르다(고르다 vs 쓰다). 그래서 '고르-' 계열만
# 빼고 지시형으로 본다.
_RE_SRV_ENDING = re.compile(
    r'(?<!고르)(?<!고를)시오\s*[.。]?\s*$'
    r'|(?:쓰기|작성|완성|서술|영작|배열|기술)\s*(?:하시오|하라)?\s*[.。]?\s*$')
_RE_PICK_ENDING = re.compile(r'고르(?:시오|세요|면|십시오)\s*[.。?]?\s*$')
# `물음에 답하시오` 는 **묶음 도입문**의 어미다. 서술형 지시가 아니다
# (한영1 실증: `[20~21] … 글을 읽고 물음에 답하시오.` 가 서술형 문항이 됐다).
_RE_GROUP_INTRO_END = re.compile(r'(?:물음|질문)에\s*답하(?:시오|세요|십시오)\s*[.。]?\s*$')
# 고르다 계열은 객관식이다 — 어미가 `시오` 여도 시키는 일이 '고르기' 다.
_RE_OBJ_ENDING = re.compile(
    r'(?:것은|것을|곳은|개수는|고르면|고른다면|고르시오|고르세요|고르십시오)'
    r'\s*[?？]?\s*[.。]?\s*$')


_RE_SRV_MARKER = re.compile(r'^\s*[\[【〔<(]?\s*서[답술]형\s*\d')


def _ul_spans(para):
    """단락 runs 에서 밑줄 구간을 단락 전체 기준 [start, end) 로 뽑는다."""
    if not isinstance(para, dict):
        return []
    out, pos = [], 0
    for run in para.get("runs", []):
        t = run.get("t", "")
        if run.get("ul") and t.strip():
            out.append((pos, pos + len(t)))
        pos += len(t)
    return out


def _marks_for(spans, start, sub):
    """단락 밑줄 구간을 부분문자열(start 위치, 길이 len(sub)) 기준으로 옮긴다.

    선지는 한 단락에 `① … ② …` 로 붙어 오기도 해서, 조각마다 제 자리의
    밑줄만 가져가야 한다. 밑줄이 없으면 빈 리스트.
    """
    end = start + len(sub)
    out = []
    for a, b in spans:
        lo, hi = max(a, start), min(b, end)
        if lo < hi:
            out.append({"type": "underline", "id": None,
                        "span": [lo - start, hi - start]})
    return out


def _q_marks(para, text):
    """발문 밑줄. 발문은 `_clean_question` 이 앞뒤를 다듬으므로 그 뒤 좌표로
    옮긴다 — `밑줄 친 … 알맞지 <u>않은</u> 것을 <u>2개</u> 고르면?` 처럼
    부정어·개수에 밑줄이 붙는다."""
    spans = _ul_spans(para)
    if not spans:
        return []
    cleaned = _clean_question(text)
    at = text.find(cleaned) if cleaned else -1
    return _marks_for(spans, at if at >= 0 else 0, cleaned)


# 원고에는 정답이 함께 온다. **시험지에 인쇄되면 안 된다.**
# `[정답 작성 안내]`(작성 조건)·`정답 및 해설의 저작권`(저작권 문구)은 정본에
# 인쇄되는 정상 요소라 건드리지 않는다 — 대괄호 안이 정확히 `정답` 이거나
# 줄이 `정답:` 으로 시작할 때만 답으로 본다.
_RE_ANSWER_LEAK = re.compile(r"^\s*(?:[\[［]\s*정답\s*[\]］]|정답\s*[:：])")


def _is_answer_leak(text):
    return bool(_RE_ANSWER_LEAK.match(str(text or "")))


def _structural_kind(cur, taxonomy_kind):
    """(kind, 근거) — 구조 신호로 객관식/서술형 판정."""
    # 원고가 대놓고 '서답형 3.' 이라고 적어 준 것보다 강한 신호는 없다.
    # (성덕1 실증: 이 라벨을 무시하고 발문 유형 룰을 먼저 봐서 서답형이
    #  객관식으로 뒤집혔다 — "빈칸 (A), (B)에 들어갈" 이 OBJ 룰에 걸림.)
    marker = ((cur.get("header") or {}).get("marker") or "")
    if _RE_SRV_MARKER.match(marker) or _RE_SRV_MARKER.match(cur.get("question") or ""):
        return "서술형", "원고 라벨"
    blocks = (cur.get("stimulus") or {}).get("blocks") or []
    labels = {b.get("label") for b in blocks}
    if labels & {"Ans", "AnsL"}:
        return "서술형", "답란"
    q = cur.get("question") or ""
    # 꼬리 괄호 단서를 떼고 본다 — `…배열하시오. (단, 주어진 표현만 한 번씩
    # 사용하며, 변형 금지)` 처럼 지시가 괄호로 이어지는 원고가 흔한데, 종결
    # 어미가 문장 끝이 아니게 되어 판정이 통째로 막혔다(강동·명일2·상일2 실증).
    from core.structure import rules as _R
    q_np = q
    for _ in range(3):
        t2 = _R.Q_TRAILING_ANGLE.sub("", q_np)
        t2 = _R.Q_TRAILING_PAREN.sub("", t2)
        if t2 == q_np:
            break
        q_np = t2
    q_np = q_np.strip() or q
    # **객관식은 고를 것이 있어야 한다.** 선지 단락도 지문 안 자리표도 없는데
    # 발문이 지시형(~시오)으로 끝나면 서술형이다 — 이 구조가 taxonomy 룰보다
    # 강하다. (명일2 실증: `…쓰시오.` 발문 셋이 OBJ 룰에 걸려 객관식이 됐다.)
    # 지시형 어미는 **지문 안 자리표보다 강하다.** 어법 고치기 서술형은
    # 지문에 ①~⑤ 자리표를 두고도 "바르게 고쳐 쓰시오" 라고 시킨다
    # (성덕2 실증: 자리표만 보고 객관식으로 뒤집혔다).
    if (not _RE_PICK_ENDING.search(q_np)
            and not _RE_GROUP_INTRO_END.search(q_np)
            and not _RE_GROUP_INTRO_END.search(q)) and (
            _RE_SRV_ENDING.search(q) or _RE_SRV_ENDING.search(q_np)):
        return "서술형", "지시형 어미"
    if (cur.get("choices") or {}).get("items"):
        return "객관식", "선지"
    if any(_RE_INLINE_CIRCLED.search(b.get("content") or "") for b in blocks):
        return "객관식", "지문 안 자리표"
    if taxonomy_kind:
        return taxonomy_kind, "발문 유형"
    if _RE_OBJ_ENDING.search(q) or _RE_OBJ_ENDING.search(q_np):
        return "객관식", "의문형 어미"
    return None, None


def _flush_item(items, cur, warnings):
    if cur is None:
        return None
    if not cur["stimulus"]["blocks"]:
        cur["stimulus"]["type"] = "empty"
    if not cur["choices"]["items"]:
        cur["choices"] = None
        # 밑줄형(*-UND-*): 선지가 본문 안 ①~⑤ 밑줄 — 별도 선지 없음이 정상
        if cur["type"] and _RE_INLINE_TYPE.search(cur["type"]):
            cur["variants"] = {"inline_marker": "V6-INLINE"}
    if not cur["given"]["content"]:
        cur["given"] = None
    else:
        cur["given"]["content"] = cur["given"]["content"].strip()
    kind, why = _structural_kind(cur, cur.get("kind"))
    if kind and kind != cur.get("kind"):
        cur["_kind_src"] = why
        cur["kind"] = kind
    elif kind:
        cur["_kind_src"] = why
    if cur.get("kind") is None:
        warnings.append(f"객관식/서술형 미판정 (문항 {cur['id']}): "
                        f"{(cur.get('question') or '')[:40]!r}")
    if cur["type"] is None:
        w = f"미분류 발문 (문항 {cur['id']}): {cur['question'][:50]!r}"
        warnings.append(w)
        cur["_warnings"].append(w)
    if not cur["_warnings"]:
        del cur["_warnings"]
    items.append(cur)
    return None



def _expand_range_groups(annotated, warnings=None):
    """범위 묶음 머리 하나가 문항 여럿을 삼키는 것을 편다.

    `(1~3) 다음 해석을 보고 …고르시오.` 는 **세 문항의 공통 지시문**이지 한
    문항이 아니다. 그런데 머리 아래 각 문항이 발문 없이 '내용 + 선지'로만
    오기 때문에(원고 관행), 파서는 셋을 한 덩어리로 삼켜 문항 수가 준다
    (강동고2 실증: 선언 35문항인데 23문항으로 파싱).

    구조로 편다 — 머리가 선언한 범위 N 과 그 아래 **선지 무리 수**가 정확히
    같을 때만, 각 무리 앞에 빈 발문을 하나씩 세워 N 문항으로 만든다.
    수가 안 맞으면 **아무것도 하지 않는다**(추측으로 쪼개지 않는다).
    """
    out = []
    i = 0
    n = len(annotated)
    while i < n:
        row = annotated[i]
        m = (_RE_RANGE_HEAD.match(row["text"])
             if row["kind"] in ("Q", "Q-INTRO") else None)
        if not m:
            out.append(row)
            i += 1
            continue
        a, b = int(m.group(1)), int(m.group(2))
        count = b - a + 1
        # 머리 아래 ~ 다음 발문/묶음머리 전까지가 이 묶음의 몸통
        j = i + 1
        while j < n and annotated[j]["kind"] not in ("Q", "Q-INTRO"):
            j += 1
        body = annotated[i + 1:j]
        # 문항 경계 후보 — 선지 무리(연속 C)가 1순위.
        starts = [k for k, r in enumerate(body)
                  if r["kind"] == "C" and (k == 0 or body[k - 1]["kind"] != "C")]
        if count >= 2 and len(starts) != count:
            # 선지 단락이 아예 없는 유형이 있다(삽입·어법 밑줄형은 ①~⑤ 가
            # 지문 안에 인라인이라 C 단락이 안 생긴다). 그때는 **지문 무리**로
            # 센다 — 묶음 안에서도 문항마다 자기 지문을 갖는다.
            p_starts = [k for k, r in enumerate(body)
                        if r["kind"] in ("P", "P-CONTEXT")
                        and (k == 0 or body[k - 1]["kind"] not in ("P", "P-CONTEXT"))]
            # 다만 **지문 무리 수가 맞는다고 다 쪼개면 안 된다** — 공유 지문 한
            # 덩이가 문단 여럿으로 나뉜 것과 구별이 안 된다(한영1·한영2 실증:
            # 그냥 쪼갰더니 +2씩 과분할). 이 폴백은 '선지 단락이 없는 유형'
            # 전용이므로, 나뉜 토막마다 **지문 안 인라인 ①~⑤ 자리표**가 있을
            # 때만 인정한다. 삽입·어법 밑줄형은 그 자리표가 문항의 선지다.
            if len(p_starts) == count and count >= 2:
                segs, ok = [], True
                for si, st in enumerate(p_starts):
                    en = p_starts[si + 1] if si + 1 < len(p_starts) else len(body)
                    segs.append(body[st:en])
                for seg in segs:
                    if not any(_RE_INLINE_CIRCLED.search(r["text"] or "")
                               for r in seg):
                        ok = False
                        break
                if ok:
                    starts = p_starts
        if count < 2 or len(starts) != count:
            if count >= 2 and warnings is not None:
                warnings.append(
                    f"묶음 '{row['text'][:24]}' 은 {count}문항인데 선지 무리가 "
                    f"{len(starts)}개다 — 펼치지 않았다")
            from core.structure import rules as _R2
            _head_txt = _R2.SOURCE_TAG_TRAIL.sub("", row["text"] or "").strip()
            # 몸통에 선지 무리가 **하나도 없다** = 구성원이 저마다 자기 발문을
            # 갖고 머리 뒤에 따로 온다는 뜻이다(강동3 실증: `[선택형6~10]` 뒤에
            # `6. 빈칸 (a)에…` `7. …` 가 이어진다). 이런 머리는 문항이 아니라
            # 도입문이다 — 문항으로 세우면 유령이 하나 생긴다.
            if not starts or _RE_GROUP_INTRO_END.search(_head_txt):
                # `…물음에 답하시오.` 형은 구성원이 저마다 발문을 갖는다.
                # 못 폈다고 머리를 문항으로 세우면 유령 문항이 하나 생긴다.
                row = dict(row)
                row["kind"] = "Q-INTRO"
            out.append(row)
            out.extend(body)
            i = j
            continue
        # 머리는 그룹 도입문으로 내리고, 각 무리 앞에 빈 발문을 세운다
        head = dict(row)
        head["kind"] = "Q-INTRO"
        out.append(head)
        # 각 문항 = 직전 무리 끝 다음 ~ 이번 무리 끝
        bounds = []
        for si, st in enumerate(starts):
            end = st
            while end + 1 < len(body) and body[end + 1]["kind"] == "C":
                end += 1
            begin = 0 if si == 0 else bounds[-1][1] + 1
            bounds.append((begin, end))
        for begin, end in bounds:
            out.append({"kind": "Q", "q_code": None, "text": "",
                        "para": {"text": ""}, "_synth_group_member": True})
            out.extend(body[begin:end + 1])
        i = j
    return out



# 선지 무리는 있는데 그 앞에 발문이 없는 자리를 메운다 ─────────────────────
# 선지 다섯 개가 붙어 있으면 그 앞 어딘가에 반드시 발문이 있다. 그런데 발문
# 종결이 화이트리스트에 없으면(`…에세이 작문 원칙은?` `…문장의 개수는?`)
# UNKNOWN 으로 남고, 그 선지 무리가 **앞 문항에 붙어** 문항 하나가 사라진다.
# 표현을 계속 늘리는 대신 '고아 선지 무리' 라는 구조로 복구한다.
_RE_KO_QEND = re.compile(r'(?:[?？]|시오\s*[.。]?|하시오|쓰시오)\s*$')
_RE_HANGUL_ANY = re.compile(r'[가-힣]')
# 발문이 **영어**로 오는 원고가 있다 — 성덕1 실증:
#   "What did Vincent van Gogh NOT draw inspiration from at the arena?"
# 한글이 없다는 이유로 지문으로 처리돼 문항 하나가 통째로 사라졌다.
_RE_EN_QEND = re.compile(r'[A-Za-z][^?]{8,}\?\s*$')


def _repair_orphan_choice_runs(annotated, warnings=None):
    """앞에 발문이 없는 선지 무리 앞의 한국어 지시문을 발문으로 승격."""
    runs = [i for i, a in enumerate(annotated)
            if a["kind"] == "C" and (i == 0 or annotated[i - 1]["kind"] != "C")]
    prev_end = -1
    fixed = 0
    for start in runs:
        end = start
        while end + 1 < len(annotated) and annotated[end + 1]["kind"] == "C":
            end += 1
        gap = range(max(prev_end + 1, 0), start)
        prev_end = end
        # **Q-INTRO 는 발문이 아니다.** 묶음 도입문("다음 글을 읽고 물음에
        # 답하시오.")은 문항의 발문 자리를 채워 주지 않는다 — 구성원은 자기
        # 발문을 따로 갖는다. 종전에는 도입문을 발문으로 쳐서, 도입문 뒤
        # 구성원의 발문이 인식 안 되면 그 문항이 통째로 사라졌다(성덕1 실증).
        if any(annotated[k]["kind"] == "Q" for k in gap):
            continue                      # 이미 발문이 있다
        # 간극에 지문이 있어야 '새 문항'이다 (짝 선지 열 나열과 구별)
        if not any(annotated[k]["kind"] in ("P", "P-CONTEXT", "K") for k in gap):
            continue
        cand = None
        for k in gap:
            t = annotated[k]["text"]
            if annotated[k]["kind"] in ("Q", "Q-INTRO", "C", "BLANK"):
                continue
            if len(t) < 15:
                continue
            if not (_RE_HANGUL_ANY.search(t) or _RE_EN_QEND.search(t)):
                continue
            if not (_RE_KO_QEND.search(t) or _RE_EN_QEND.search(t)):
                continue
            cand = k
            break
        if cand is None:
            continue
        annotated[cand]["kind"] = "Q"
        annotated[cand]["q_code"] = None
        fixed += 1
        if warnings is not None:
            warnings.append(
                f"고아 선지 무리 앞의 지시문을 발문으로 세움: "
                f"{annotated[cand]['text'][:40]!r}")
    return annotated



# 원고 선언 문항수 대조 ──────────────────────────────────────────────────────
# 원고 머리에 출제자가 적어 둔 문항수가 정답지다. 그런데 **원고 선언이 실제
# 내용과 다른 원고가 있다**(명일3 1·2회: 서술형 6 선언, 실제 5. 한영1 2회도
# 서술형 라벨이 5개뿐). 머리표 문항수는 원고 기준으로 찍기로 했으므로
# (profiles/_결정.json), 선언이 틀리면 **시험지에 틀린 문항수가 인쇄된다.**
# 조용히 넘어가지 말고 경고로 올린다.
_RE_DECL_SEL = [re.compile(r"선택형\s*[::]?\s*(\d+)"),
                re.compile(r"객관식\s*[::]?\s*(\d+)")]
_RE_DECL_SRV = [re.compile(r"서[술답]형\s*[::]?\s*(\d+)"),
                re.compile(r"서논술형\s*[::]?\s*(\d+)"),
                re.compile(r"주관식\s*[::]?\s*(\d+)")]


def declared_counts(paras, head_lines=5):
    """원고 머리에 선언된 (선택형, 서답형) 문항수. 없으면 (None, None)."""
    head = " ".join(
        unicodedata.normalize("NFC", (p.get("text") if isinstance(p, dict)
                                      else str(p)) or "")
        for p in paras[:head_lines])
    sel = next((int(m.group(1)) for r in _RE_DECL_SEL if (m := r.search(head))),
               None)
    srv = next((int(m.group(1)) for r in _RE_DECL_SRV if (m := r.search(head))),
               None)
    return sel, srv


def build_ir(paras, meta=None, log=None):
    """단락 목록 → content v2 문서. (단락종류 시퀀스 기반 문항 그룹핑)"""
    from engines._taxonomy import classify

    # 딩벳 원문자를 표준 원문자로 접고 시작한다 — 안 접으면 그 선지들이
    # 선지로 인식되지 않는다(성덕1 2회 실증).
    paras = [dict(p, text=normalize_marks(p.get("text") or ""))
             if isinstance(p, dict) else normalize_marks(str(p))
             for p in paras]

    # 동형 원고는 서술형 답란을 괄호 기입란으로 준다("(1) (   )번",
    # "(2) (틀린 부분:      )"). 이 줄을 답란으로 잡아야 서술형 판정이 선다.
    # 공용 기본값이 아니라 이 계열에서만 켠다 — 워크북 계열은 같은 모양을
    # 지문 스타일로 인쇄하는 관행이라 켜면 그쪽 산출물이 바뀐다.
    annotated = classify_paragraphs(paras, {"blank_fill_answer": True,
                                            "strip_source_tag": True,
                                            "ko_interrogative": True,
                                            "strip_tail_note": True})
    _pre_warn = []
    annotated = _repair_orphan_choice_runs(annotated, _pre_warn)
    annotated = _expand_range_groups(annotated, _pre_warn)
    items = []
    warnings = list(_pre_warn)
    cur = None
    group_intro = None       # 직전 Q-INTRO의 group 정보 (묶음 문항 상속)
    pending_stimulus = []    # 발문보다 앞에 온 공유 지문 (묶음/서답형 배치)
    pending_sum = False      # ↓ 화살표 직후 단락 = 요약문(구조 신호)
    seq = 0

    for r in annotated:
        kind, text = r["kind"], r["text"]
        if _is_answer_leak(text):
            warnings.append(f"정답 줄을 버렸다: {str(text)[:40]}")
            continue
        # 원고 그림(도표) — 텍스트가 없어 분류에서 빠지므로 여기서 먼저 챙긴다
        para = r.get("para")
        img = para.get("image") if isinstance(para, dict) else None
        if img:
            blk = {"kind": "image", "label": "Fig", "content": "",
                   "image": img}
            if cur is not None:
                cur["stimulus"]["blocks"].append(blk)
            else:
                pending_stimulus.append(r)
            continue
        # W59: 화살표(↓)는 지문과 요약문을 가르는 **구조 신호**다.
        # 통째로 버리면 요약문이 지문에 붙어 한 상자에 뭉친다(블랙북 실증).
        if kind == "Sym" and cur is not None:
            cur["stimulus"]["blocks"].append(
                {"kind": "text", "label": "Sym", "content": text})
            pending_sum = True
            continue
        if kind in ("BLANK", "GH", "A", "Sym"):
            continue

        if kind == "Q-INTRO":
            cur = _flush_item(items, cur, warnings)
            gh = _header_of(text)
            n_range = 0
            m = _RE_GROUP.match(text)
            if m:
                n_range = int(m.group(2)) - int(m.group(1)) + 1
            group_intro = {"header": gh, "text": text,
                           "remaining": n_range or 99, "fresh": True}
            continue

        if kind == "Q":
            # 하위 물음 오버레이 (발동 범위 최소화): "(N) ..." 번호 단락은
            # 직전 문항이 다부문 헤더("물음에 답하시오")일 때만 그 문항의
            # 하위 물음으로 붙인다 — 분류기가 발문으로 오인해도 경계 미분할.
            # ((1)/(2)류 미분류 하위 물음이 UNKNOWN으로 지문에 남는 것과 동일 취급)
            if (cur is not None and _RE_SUBITEM.match(text)
                    and _MULTIPART_HINT in (cur.get("question") or "")):
                cur["stimulus"]["blocks"].append(
                    {"kind": "text", "label": "UNKNOWN", "content": text})
                continue
            cur = _flush_item(items, cur, warnings)
            code, label, q_kind = classify(_clean_question(text))
            if code == "OBJ-LNG-HEADER":
                # 묶음 도입부 — 문항이 아니라 그룹 컨텍스트
                gh2 = _header_of(text)
                n_range = 0
                m2 = _RE_GROUP.match(text)
                if m2:
                    n_range = int(m2.group(2)) - int(m2.group(1)) + 1
                group_intro = {"header": gh2, "text": text,
                               "remaining": n_range or 99, "fresh": True}
                continue
            seq += 1
            header = _header_of(text)
            intro_text = None
            if group_intro and group_intro["remaining"] > 0:
                if not header["group_id"]:
                    header["group_id"] = group_intro["header"]["group_id"]
                if group_intro["fresh"]:
                    intro_text = group_intro["text"]   # 그룹 첫 문항 앞에 1회 출력
                    group_intro["fresh"] = False
                group_intro["remaining"] -= 1
            cur = {
                "id": f"q-{seq:03d}",
                "type": code,
                "kind": q_kind,
                "label": label,
                "header": header,
                "question": _clean_question(text),
                "question_marks": _q_marks(r.get("para"), text),
                "stimulus": {"type": "passage", "blocks": []},
                "given": {"type": None, "content": ""},
                "choices": {"format": "circled", "items": []},
                "constraints": [],
                "answer": None,
                "_warnings": [],
            }
            if intro_text:
                cur["_group_intro"] = intro_text
            pending_sum = False
            if pending_stimulus:
                for pr in pending_stimulus:
                    if pr["kind"] == "Box":
                        if not re.match(r'^\s*(?:<|\[)', pr["text"]) \
                                or len(pr["text"]) > 12:
                            cur["given"]["type"] = cur["given"]["type"] or "word_box"
                            cur["given"]["content"] += \
                                ("\n" if cur["given"]["content"] else "") + pr["text"]
                    elif pr["kind"] == "Cond":
                        if not re.match(r'^\s*(?:<|\[)?\s*조\s*건', pr["text"]):
                            cur["constraints"].append(pr["text"])
                    else:
                        block = {"kind": "para" if pr["kind"] == "P-CONTEXT" else "text",
                                 "label": None, "content": pr["text"]}
                        cur["stimulus"]["blocks"].append(block)
                pending_stimulus = []
            continue

        if cur is None:
            # 묶음/서답형: 공유 지문이 도입문 뒤·첫 발문 앞에 오는 배치 —
            # 버퍼에 담아 다음 문항의 지문으로 붙인다 (드랍 금지).
            if kind in ("P", "P-CONTEXT", "Box", "Cond") or (
                    kind == "UNKNOWN" and text
                    and not re.search(r"[가-힣]", text)):
                pending_stimulus.append(r)
                continue
            # 그 외(표지/안내 등)는 경고만
            if text:
                warnings.append(f"발문 이전 고아 단락: {text[:50]!r}")
            continue

        if pending_sum and kind not in ("Q", "Q-INTRO", "GH", "A", "C",
                                        "Cond", "Box"):
            # 화살표 다음 단락 = 요약문 (박스로 조판). 밑줄이 길어 답란(Ans)
            # 으로, 영영풀이라 UNKNOWN 으로 잡히더라도 화살표 신호가 우선.
            pending_sum = False
            block = {"kind": "text", "label": "Sum", "content": text}
            cur["stimulus"]["blocks"].append(block)
            continue
        pending_sum = False

        if kind in ("P", "P-CONTEXT"):
            block = {"kind": "para" if kind == "P-CONTEXT" else "text",
                     "label": None, "content": text}
            marks = _marks_for(_ul_spans(r.get("para")), 0, text)
            if marks:
                block["marks"] = marks
            cur["stimulus"]["blocks"].append(block)
        elif kind == "C":
            if re.match(r'^\(A\)(?:\s{2,}|\t)', text):
                # (A)  (B) 요약 빈칸 헤더 — 선지가 아니라 요약 박스 구성
                cur["given"]["type"] = "summary_box"
                cur["given"]["content"] += ("\n" if cur["given"]["content"] else "") + text
                continue
            parts = [t for t in _RE_CIRCLED_SPLIT.split(text) if t.strip()]
            spans = _ul_spans(r.get("para"))
            seek = 0
            for part in parts:
                at = text.find(part, seek)
                if at < 0:
                    at = seek
                seek = at + len(part)
                part_s = part.strip()
                off = at + (len(part) - len(part.lstrip()))
                if part_s[:1] in "①②③④⑤":
                    body = part_s[1:].strip()
                    boff = text.find(body, off) if body else off
                    item = {"label": part_s[:1], "content": body}
                    m = _marks_for(spans, boff if boff >= 0 else off, body)
                else:
                    item = {"label": "", "content": part_s}
                    m = _marks_for(spans, off, part_s)
                if m:
                    item["marks"] = m
                cur["choices"]["items"].append(item)
        elif kind == "Cond":
            if not re.match(r'^\s*(?:<|\[)?\s*조\s*건', text):
                cur["constraints"].append(text)
        elif kind == "Box":
            if not re.match(r'^\s*(?:<|\[)', text) or len(text) > 12:
                cur["given"]["type"] = cur["given"]["type"] or "word_box"
                cur["given"]["content"] += ("\n" if cur["given"]["content"] else "") + text
        elif kind in ("Word", "K", "Ans", "UNKNOWN"):
            # v1 범위: 지문 뒤 부속으로 보존 (Ans=답란은 조판 대상)
            cur["stimulus"]["blocks"].append(
                {"kind": "text", "label": kind, "content": text})

    _flush_item(items, cur, warnings)

    # 원고 선언 문항수와 실제를 대조한다 — 머리표를 원고 기준으로 찍기로 했으니
    # (profiles/_결정.json) 선언이 틀리면 시험지에 틀린 문항수가 인쇄된다.
    _sel, _srv = declared_counts(paras)
    n_obj = sum(1 for i in items if i.get("kind") == "객관식")
    n_srv = sum(1 for i in items if i.get("kind") == "서술형")
    if _sel is not None and n_obj != _sel:
        warnings.append(f"원고 선언 선택형 {_sel}문항 ≠ 실제 {n_obj}문항 "
                        f"— 머리표 문항수 확인 필요")
    if _srv is not None and n_srv != _srv:
        warnings.append(f"원고 선언 서답형 {_srv}문항 ≠ 실제 {n_srv}문항 "
                        f"— 머리표 문항수 확인 필요")

    doc = {"version": 2, "meta": dict(meta or {}), "items": items}
    if warnings:
        doc["meta"]["_warnings"] = warnings
        if callable(log):
            for w in warnings[:10]:
                log(f"[v2] ⚠️ {w}")
    return doc


def parse_manuscripts(paths, meta=None, log=None):
    """여러 원고 파일 → 회차별 v2 문서 목록 [(파일명, doc)]."""
    out = []
    for p in sorted(paths):
        name = unicodedata.normalize("NFC", os.path.basename(p))
        if callable(log):
            log(f"[v2] 파싱: {name}")
        paras = extract_file_paragraphs(p)
        doc = build_ir(paras, meta=dict(meta or {}, source_file=name), log=log)
        out.append((name, doc))
    return out
