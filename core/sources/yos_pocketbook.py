# -*- coding: utf-8 -*-
"""contents 포켓북(지문 하나) → 편집기 제작 포켓북 틀(배재1 포켓북 x5e277563)의 원고 — 레코드 셋과 면 고르기.

contents 는 지문마다 이것을 보낸다(가공하지 않은 분석본 조판 문서 + 고른 면):
    {"doc": TypesetDoc, "faces": ["passage", "flow", "memo", "answer"], "illust": bool,
     "flow": [{"제목", "글"}] | null, "책이름": str, (고칠 때만) "출처" · "단원" · "구분": "교과서" | "모의고사"}
출처 · 단원 · 구분은 안 보내면 조판 문서 머리에서 짓는다(_heads).

틀은 레코드의 칸으로 면을 고른다(자동 상위 페이지 적용 — docs/편집기_재현/용어.md):
    지문 레코드   출처 · 지문 · 해석 (· 그림 → 삽화 면)          → 「passage」
    흐름 레코드   흐름제목+흐름글 · 주제 · 요약문 · 낱말+뜻+동의어+반의어 → 「flow」
    암기 레코드   암기지문 [TEST, 정답] — 두 페이지짜리             → 「memo」 · 「answer」
자리 이름·꼴은 tests/e2e/replay/배재포켓북/join.py records() 와 같다(그 틀을 만든 대본의 자리).

    to_content(src) → (content, faces, report)   faces[i] = i 번째 레코드의 면 이름들(쪽 차례)

지문의 꾸밈(윗주 · 역할 색)은 분석본 변환(yos_analysis.sentence_runs) 그대로 — 역할 → 문자 스타일 이름만 이 틀의 것으로 바꾼다.
암기 빈칸 = 중요 문법 · 중요 어휘로 칠한 낱말(「N[낱말]」 — 틀의 GREP 이 TEST 면은 빈칸, 정답 면은 낱말로 그린다).
"""
import re

from core.sources import yos_analysis

FACES = ("passage", "flow", "memo", "answer")
CS_RENAME = {"빨강 물결": "분홍 물결", "형광 보라": "형광 분홍"}           # 광문 틀 이름 → 배재 포켓북 틀 이름(나머지는 같다)
BLANK_ROLES = {"grammar", "vocab"}
VOCA_MAX = 9                                                               # 동반의어 칸 — 원본 포켓북 28지문 중 가장 많은 것이 9(3×3)
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def _cs(v):
    if isinstance(v, list):
        return [CS_RENAME.get(x, x) for x in v]
    return CS_RENAME.get(v, v)


def passage_runs(doc):
    """문장들 → 한 문단 꾸밈 조각(제목이 있으면 맨 앞)"""
    runs = []
    en = ((doc.get("title") or {}).get("en") or "").strip()
    if en:
        runs.append(en + " ")
    for i, s in enumerate(doc.get("sentences") or []):
        if i:
            runs.append(" ")
        for r in yos_analysis.sentence_runs(s.get("tagged") or "", s.get("marks") or [], s.get("refs")):
            if isinstance(r, dict) and r.get("cs"):
                r = dict(r, cs=_cs(r["cs"]))
            runs.append(r)
    return yos_analysis.norm_runs(runs)


def memo_text(doc):
    """암기 지문 — 중요 문법 · 어휘 낱말을 「N[낱말]」 로(번호는 지문 안에서 1부터)"""
    out, n = [], 0
    en = ((doc.get("title") or {}).get("en") or "").strip()
    if en:
        out.append(f"<{en}> ")
    for i, s in enumerate(doc.get("sentences") or []):
        if i:
            out.append(" ")
        for r in yos_analysis.sentence_runs(s.get("tagged") or "", s.get("marks") or [], s.get("refs")):
            t = r if isinstance(r, str) else (r.get("t") or "")
            if isinstance(r, dict) and BLANK_ROLES & set(r.get("rl") or []):
                def blank(m):
                    nonlocal n
                    n += 1
                    return f"{n}[{m.group(0)}]"
                t = _WORD.sub(blank, t)
            out.append(t)
    return "".join(out), n


def _translation(doc):
    ko = ((doc.get("title") or {}).get("ko") or "").strip()
    body = " ".join((s.get("ko") or "").strip() for s in doc.get("sentences") or [] if (s.get("ko") or "").strip())
    return f"{ko} {body}".strip() if ko else body


def _heads(doc):
    """머리 칸 기본값 — 조판 문서 머리(meta.title = 단원 · 교재, meta.source = 번호)에서.
    교과서(「Lesson 1 …」)는 「1과 MR1」 · 「교과서 1과」, 그 밖(모의고사 「고1 21년 3월」)은 「고1 21년 3월 39번」 · 그 머리 그대로"""
    meta = doc.get("meta") or {}
    title, no = (meta.get("title") or "").strip(), (meta.get("source") or "").strip()
    m = re.search(r"(?:Lesson|Unit|Chapter)\s*(\d+)", title, re.I) or re.match(r"(\d+)\s*과", title)
    if m:
        return f"{int(m.group(1))}과 {no}".strip(), f"교과서 {int(m.group(1))}과", "교과서"
    return f"{title} {no}".strip(), title, "모의고사"


def to_content(src):
    doc = src.get("doc") or {}
    want = [f for f in src.get("faces") or FACES if f in FACES]
    src_d, unit_d, gubun_d = _heads(doc)
    gubun = src.get("구분") if src.get("구분") in ("교과서", "모의고사") else gubun_d
    unit = src.get("단원") or unit_d
    recs, faces, report = [], [], {"skipped": []}
    if not doc.get("sentences"):
        report["skipped"].append("분석본에 문장이 없다")
        return {"원고": []}, [], report
    if "passage" in want:
        r = {"출처": src.get("출처") or src_d, "지문": [passage_runs(doc)], "해석": _translation(doc), "책이름": src.get("책이름") or "", "구분": gubun}
        if src.get("illust"):
            r["그림"] = src.get("image") or ""                         # 그림이 아직 없어도 삽화 면(빈 그림 자리)으로
        recs.append(r)
        faces.append(["passage"])
    if "flow" in want:
        flow = [f for f in src.get("flow") or [] if isinstance(f, dict) and (f.get("제목") or f.get("글"))]
        if not flow:
            report["skipped"].append("흐름이 아직 없다 — FLOWNOTE 면을 그리지 않았다")
        else:
            voca = [v for v in doc.get("voca") or [] if v.get("word")]
            voca = sorted(voca, key=lambda v: not (v.get("synonym") or v.get("antonym")))[:VOCA_MAX]   # 동의어·반의어 있는 낱말 먼저(차례는 그 안에서 그대로)
            recs.append({"흐름제목+흐름글": [[{"흐름제목": f.get("제목") or "", "흐름글": f.get("글") or ""}] for f in flow],
                         "주제": doc.get("topic") or "", "요약문": doc.get("summary") or "",
                         "낱말+뜻+동의어+반의어": [[{"낱말": v["word"], "뜻": v.get("ko") or "", "동의어": v.get("synonym") or "",
                                                  "반의어": v.get("antonym") or ""} for v in voca]],
                         "단원": unit, "구분": gubun})
            faces.append(["flow"])
    if "memo" in want or "answer" in want:
        text, n = memo_text(doc)
        if not n:
            report["skipped"].append("중요 문법 · 어휘 표기가 없어 암기 빈칸이 없다")
        recs.append({"암기지문": [text, text], "단원": unit, "구분": gubun})
        faces.append(["memo", "answer"])
    return {"원고": recs}, faces, report
