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
    """실전 구간의 지문 경계. [{code, page, offset, at_head, fid}] (문서 순)."""
    out = []
    for f in frames:
        text = f.get("text") or ""
        for m in _RE_EXAM_CODE.finditer(text):
            out.append({
                "code": normalize_code(m.group(2)),
                "page": f["pidx"] + 1,
                "offset": m.start(),
                "at_head": m.start() <= HEAD_SLACK,
                "fid": f["fid"],
                "sid": f["sid"],
            })
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


def partition(blocks, canon):
    """canon 지문 블록 / 짤지문 블록으로 가른다."""
    exam, tail = {}, []
    for b in blocks:
        c = resolve_to_canon(b["code"], canon)
        if c:
            exam.setdefault(c, []).extend(b["pages"])
        else:
            tail.append({"code": b["code"], "src_pages": b["pages"]})
    return exam, tail


def gate(exam, tail, canon):
    fails = []
    for c in (normalize_code(x) for x in canon):
        if not exam.get(c):
            fails.append("지문 %s: 실전 블록 없음" % c)
    return fails
