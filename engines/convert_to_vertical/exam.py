# -*- coding: utf-8 -*-
"""S2 — 실전(O) 구간을 지문별 블록으로 분해한다.

현행 엔진은 '페이지 첫 프레임의 코드 마커'로만 경계를 잡아, 프레임 중간에서
시작하는 지문을 앞 블록에 흡수시킨다 (26년 6월: 지문 30·33 소실, 짤지문 26도
같은 형태). 여기서는 **프레임 전문(全文)에서 마커 위치를 찾아** 경계를 잡고,
프레임 중간 경계는 '분할 필요'로 표시해 JSX 에 넘긴다.
"""

from __future__ import annotations

import json
import re

from .inventory import normalize_code, resolve_to_canon

# {YYMMQQ} — 실전 구간의 지문 코드 표기
_RE_EXAM_CODE = re.compile(r"\{(\d{4})(\d{2}(?:\s*[-~]\s*\d+)?)\}")

# 프레임 머리로 볼 오프셋 허용치 (선두 공백/제어문자 흡수)
HEAD_SLACK = 5


def exam_frames(frames_json, first_page, last_page):
    d = json.load(open(frames_json, encoding="utf-8"))
    fs = [f for f in d["frames"]
          if f["gb"][0] > 0 and f["chars"] > 0
          and first_page <= f["pidx"] + 1 <= last_page]
    fs.sort(key=lambda f: (f["pidx"], f["gb"][1], f["gb"][0]))
    return fs, d["page_count"]


def find_boundaries(frames):
    """실전 구간의 지문 경계. [{code, page, offset, at_head, fid}] (문서 순).

    at_head 는 **페이지 머리**를 뜻한다 — 프레임 머리가 아니다. 실전은 2단
    조판이라 페이지마다 프레임이 여럿이고, 오른쪽 단 머리에서 시작하는 지문을
    "분할 불필요"로 보면 그 페이지가 통째로 다음 지문 블록에 들어가면서 왼쪽
    단(앞 지문의 꼬리)까지 딸려간다. 26년 6월 실측: 지문 31↔32·32↔33·36↔37 이
    한 페이지에 좌우로 섞였고, 검수가 '섹션 관통 스레드 3개'로 잡았다.
    """
    first_fid = {}
    for f in frames:                      # frames 는 (pidx, x, y) 정렬
        first_fid.setdefault(f["pidx"], f["fid"])
    out = []
    for f in frames:
        text = f.get("text") or ""
        is_first = first_fid.get(f["pidx"]) == f["fid"]
        for m in _RE_EXAM_CODE.finditer(text):
            out.append({
                "code": normalize_code(m.group(2)),
                "page": f["pidx"] + 1,
                "offset": m.start(),
                "at_head": is_first and m.start() <= HEAD_SLACK,
                "fid": f["fid"],
                "sid": f["sid"],
            })
    return out


def page_info(frames_json):
    """페이지 → {master, has_content}. 간지/빈 페이지를 블록에서 빼기 위함."""
    d = json.load(open(frames_json, encoding="utf-8"))
    info = {}
    for f in d["frames"]:
        pg = f["pidx"] + 1
        rec = info.setdefault(pg, {"master": f.get("master") or "", "chars": 0})
        if f["gb"][0] > 0:
            rec["chars"] += f["chars"]
    for pg, rec in info.items():
        rec["has_content"] = rec["chars"] > 0
        rec["structural"] = ("간지" in rec["master"]) or not rec["master"]
    return info


def trim_block(pages, info):
    """블록에서 구조 페이지(간지/[none])를 빼고, 꼬리의 빈 페이지를 잘라낸다.

    이걸 안 하면 마지막 블록이 문서 끝의 빈 O 페이지·뒤부속까지 흡수한다
    (26년 6월: 짤지문 43이 p263~273 으로 11p 로 잡혔다 — 실제 내용은 263~269).
    """
    out = [p for p in pages
           if not info.get(p, {}).get("structural")]
    while out and not info.get(out[-1], {}).get("has_content"):
        out.pop()
    return out


def blocks_from_boundaries(boundaries, last_page):
    """경계 → 지문별 페이지 구간.

    구간 끝 = 다음 경계의 시작 페이지 직전. 다음 경계가 프레임 중간이면 그
    페이지는 앞 지문과 **공유**되므로 `shared_end=True` 로 표시한다 (분할 후
    페이지가 1장 늘어난다).
    """
    blocks = []
    for i, b in enumerate(boundaries):
        nxt = boundaries[i + 1] if i + 1 < len(boundaries) else None
        if nxt is None:
            end, shared = last_page, False
        elif nxt["at_head"]:
            end, shared = nxt["page"] - 1, False
        else:
            end, shared = nxt["page"], True     # 다음 지문과 같은 페이지를 공유
        blocks.append({"code": b["code"], "start": b["page"], "end": end,
                       "pages": list(range(b["page"], end + 1)),
                       "needs_split": not b["at_head"],
                       "split_offset": None if b["at_head"] else b["offset"],
                       "split_fid": None if b["at_head"] else b["fid"],
                       "shared_end": shared})
    return blocks


def split_targets(blocks):
    """JSX 에 넘길 분할 지시 — 프레임 중간에서 시작하는 지문만."""
    return [{"code": b["code"], "fid": b["split_fid"],
             "offset": b["split_offset"], "page": b["start"]}
            for b in blocks if b["needs_split"]]


def partition(blocks, canon, info=None):
    """canon 지문 블록 / 짤지문 블록으로 가른다. info 를 주면 구조 페이지를 제외."""
    exam, tail = {}, []
    for b in blocks:
        pages = trim_block(b["pages"], info) if info else b["pages"]
        if not pages:
            continue
        c = resolve_to_canon(b["code"], canon)
        if c:
            exam.setdefault(c, []).extend(pages)
        else:
            tail.append({"code": b["code"], "src_pages": pages})
    return exam, tail


def gate(exam, tail, canon):
    fails = []
    for c in (normalize_code(x) for x in canon):
        if not exam.get(c):
            fails.append("지문 %s: 실전 블록 없음" % c)
    return fails


# ── 영작 배열 스레드 분할 (SPEC 5.1 두 번째 split) ─────────────────────────
# 영작 배열은 N지문이 6프레임에 스레드로 담겨 있어, 지문 하나가 자기 페이지에서
# 시작하지 않는다. body 의 STEP4.4 는 페이지 단위로 코드를 찾으므로 프레임
# 중간에서 시작하는 지문을 놓친다 (26년 6월: arrange 섹션 17/18 — 지문 30 소실).
# 실전과 같은 방식으로 텍스트 내부 마커에서 미리 끊어 준다.
_RE_BRACKET_CODE = re.compile(r"[\[\{]\s*(\d{1,2}(?:\s*[-~]\s*\d+)?)\s*[\]\}]")


def arrange_frames(frames_json, first_page, last_page):
    return exam_frames(frames_json, first_page, last_page)


def arrange_boundaries(frames, canon):
    """영작 배열 구간의 지문 첫 등장 위치 (canon 에 없는 코드는 무시).

    같은 코드가 뒤에 또 나오는 경우(예문 안의 대괄호)는 첫 등장만 경계로 본다.
    `body_sees` 는 body(STEP4.4) 의 마커 스캔이 이 지문을 잡는지 여부다.
    """
    text, spans = story_text(frames)
    seen_ok = body_visible_codes(text, canon)
    out, seen = [], set()
    for f in frames:
        t = f.get("text") or ""
        for m in _RE_BRACKET_CODE.finditer(t):
            c = resolve_to_canon(m.group(1), canon)
            if not c or c in seen:
                continue
            seen.add(c)
            out.append({
                "code": c,
                "page": f["pidx"] + 1,
                "offset": m.start(),
                "at_head": m.start() <= HEAD_SLACK,
                "body_sees": c in seen_ok,
                "fid": f["fid"],
                "sid": f["sid"],
            })
    return out


def story_text(frames):
    """프레임 텍스트를 문서 순서대로 이어 붙여 스토리 텍스트를 복원한다."""
    parts, spans, pos = [], [], 0
    for f in frames:
        t = f.get("text") or ""
        spans.append((f["fid"], pos, pos + len(t)))
        parts.append(t)
        pos += len(t)
    return "".join(parts), spans


# body(convert_vertical.body.jsx STEP4.4) 의 마커 스캔과 **같은 규칙**:
# 단락(\r 또는 \n 구분) 머리 40자 안에서만 코드를 인정한다. 이 미러링이
# 어긋나면 "우리는 보이는데 body 는 못 보는" 지문이 침묵으로 사라진다.
_RE_BODY_CODE6 = re.compile(r"^\s*\{(\d{4})(\d{2}(?:~\d+)?)\}")
_RE_BODY_SHORT = re.compile(r"^\s*[\[{]\s*(\d{1,3}(?:~\d+)?)\s*[\]}]")


def body_visible_codes(text, canon):
    """body 의 단락 머리 스캔으로 잡히는 canon 코드 집합."""
    got = set()
    for para in re.split(r"[\r\n]", text or ""):
        head = para[:40]
        m = _RE_BODY_CODE6.match(head)
        raw = m.group(2) if m else None
        if raw is None:
            m = _RE_BODY_SHORT.match(head)
            raw = m.group(1) if m else None
        if raw is None:
            continue
        c = resolve_to_canon(raw, canon)
        if c:
            got.add(c)
    return got


def arrange_split_targets(boundaries, frames=None):
    """body 가 못 보는 지문만 분할한다.

    body 는 영작 배열 스레드를 **텍스트 마커 기준으로 통째로 재분해**하므로
    (STEP4.4: 섹션마다 새 페이지+프레임에 범위 복제, 원본 페이지 삭제) 페이지를
    미리 쪼갤 필요가 없다. 필요한 것은 단 하나 — 코드가 **단락 머리**에 오게
    하는 것이다. 26년 6월 실측: 18지문 중 [30] 만 앞에 인라인 개체 문자(￼)가
    붙어 정규식에서 빠졌고, 그래서 arrange 섹션이 17개로 줄었다.

    페이지를 과하게 쪼개면 프레임 브레이크가 꽉 찬 프레임을 밀어내 오버셋이
    난다 (17건 분할 실측: 오버셋 1건으로 분할 자체가 중단).
    """
    return [{"code": b["code"], "fid": b["fid"],
             "offset": b["offset"], "page": b["page"]}
            for b in boundaries if not b.get("body_sees")]


def arrange_gate(boundaries, canon):
    """영작 배열 게이트 — canon 전원 검출 + 순서 일치."""
    fails = []
    got = [b["code"] for b in boundaries]
    canon_n = [normalize_code(c) for c in canon]
    miss = [c for c in canon_n if c not in got]
    if miss:
        fails.append("영작배열: 지문 %s 미검출" % miss)
    ordered = [c for c in got if c in canon_n]
    if ordered and ordered != [c for c in canon_n if c in ordered]:
        fails.append("영작배열: 지문 순서가 canon 과 다름 (%s)" % ordered[:6])
    return fails
