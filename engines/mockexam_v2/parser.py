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


def extract_file_paragraphs(path):
    """파일 확장자별 core.extract 위임 (밑줄 포함)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _docx_extract_paragraphs(path, extract_underline=True)
    if ext == ".hwpx":
        return _hwpx_extract_paragraphs(path, extract_underline=True,
                                        exclude_footnotes=True)
    if ext == ".hwp":
        if _hwp_is_hwpx(path):
            return _hwpx_extract_paragraphs(path, extract_underline=True,
                                            exclude_footnotes=True)
        return _hwp_extract_paragraphs(path, extract_underline=True,
                                       exclude_footnotes=True)
    raise ValueError(f"지원하지 않는 형식: {ext}")


def _clean_question(text):
    """발문에서 머리 번호를 떼고 발문 본문만."""
    t = _RE_GROUP.sub("", text)
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
_RE_SRV_ENDING = re.compile(r'(?:시오|쓰기|작성|완성|서술|영작|배열)\s*[.。]?\s*$')
_RE_OBJ_ENDING = re.compile(r'(?:것은|것을|곳은|개수는|고르면|고른다면)\s*[?？]?\s*[.。]?\s*$')


_RE_SRV_MARKER = re.compile(r'^\s*[\[【〔<(]?\s*서[답술]형\s*\d')


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
    if (cur.get("choices") or {}).get("items"):
        return "객관식", "선지"
    if any(_RE_INLINE_CIRCLED.search(b.get("content") or "") for b in blocks):
        return "객관식", "지문 안 자리표"
    if taxonomy_kind:
        return taxonomy_kind, "발문 유형"
    q = cur.get("question") or ""
    if _RE_SRV_ENDING.search(q):
        return "서술형", "지시형 어미"
    if _RE_OBJ_ENDING.search(q):
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
        # 선지 무리(연속 C)의 시작 위치들
        starts = [k for k, r in enumerate(body)
                  if r["kind"] == "C" and (k == 0 or body[k - 1]["kind"] != "C")]
        if count < 2 or len(starts) != count:
            if count >= 2 and warnings is not None:
                warnings.append(
                    f"묶음 '{row['text'][:24]}' 은 {count}문항인데 선지 무리가 "
                    f"{len(starts)}개다 — 펼치지 않았다")
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


def build_ir(paras, meta=None, log=None):
    """단락 목록 → content v2 문서. (단락종류 시퀀스 기반 문항 그룹핑)"""
    from engines._taxonomy import classify

    # 동형 원고는 서술형 답란을 괄호 기입란으로 준다("(1) (   )번",
    # "(2) (틀린 부분:      )"). 이 줄을 답란으로 잡아야 서술형 판정이 선다.
    # 공용 기본값이 아니라 이 계열에서만 켠다 — 워크북 계열은 같은 모양을
    # 지문 스타일로 인쇄하는 관행이라 켜면 그쪽 산출물이 바뀐다.
    annotated = classify_paragraphs(paras, {"blank_fill_answer": True,
                                            "strip_source_tag": True})
    _pre_warn = []
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
            para = r.get("para")
            if isinstance(para, dict):
                marks = []
                pos = 0
                for run in para.get("runs", []):
                    t = run.get("t", "")
                    if run.get("ul") and t.strip():
                        marks.append({"type": "underline", "id": None,
                                      "span": [pos, pos + len(t)]})
                    pos += len(t)
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
            for part in parts:
                part = part.strip()
                if part[:1] in "①②③④⑤":
                    cur["choices"]["items"].append(
                        {"label": part[:1], "content": part[1:].strip()})
                else:
                    cur["choices"]["items"].append({"label": "", "content": part})
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
