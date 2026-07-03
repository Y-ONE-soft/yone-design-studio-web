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
    if cur["type"] is None:
        w = f"미분류 발문 (문항 {cur['id']}): {cur['question'][:50]!r}"
        warnings.append(w)
        cur["_warnings"].append(w)
    if not cur["_warnings"]:
        del cur["_warnings"]
    items.append(cur)
    return None


def build_ir(paras, meta=None, log=None):
    """단락 목록 → content v2 문서. (단락종류 시퀀스 기반 문항 그룹핑)"""
    from engines._taxonomy import classify

    annotated = classify_paragraphs(paras)
    items = []
    warnings = []
    cur = None
    group_intro = None       # 직전 Q-INTRO의 group 정보 (묶음 문항 상속)
    pending_stimulus = []    # 발문보다 앞에 온 공유 지문 (묶음/서답형 배치)
    seq = 0

    for r in annotated:
        kind, text = r["kind"], r["text"]
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
            if pending_stimulus:
                for pr in pending_stimulus:
                    block = {"kind": "para" if pr["kind"] == "P-CONTEXT" else "text",
                             "label": None, "content": pr["text"]}
                    cur["stimulus"]["blocks"].append(block)
                pending_stimulus = []
            continue

        if cur is None:
            # 묶음/서답형: 공유 지문이 도입문 뒤·첫 발문 앞에 오는 배치 —
            # 버퍼에 담아 다음 문항의 지문으로 붙인다 (드랍 금지).
            if kind in ("P", "P-CONTEXT"):
                pending_stimulus.append(r)
                continue
            # 그 외(표지/안내 등)는 경고만
            if text:
                warnings.append(f"발문 이전 고아 단락: {text[:50]!r}")
            continue

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
