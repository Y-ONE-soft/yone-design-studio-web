# -*- coding: utf-8 -*-
"""세로 변환 S1/S2/후처리 계획 — 합성 덤프로 InDesign 없이 검증.

실기 1회가 1시간이라 계획 로직은 반드시 오프라인에서 잡는다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.convert_to_vertical import exam as exam_mod          # noqa: E402
from engines.convert_to_vertical import inventory as inv_mod      # noqa: E402
from engines.convert_to_vertical import plan as plan_mod          # noqa: E402

N = 2
CODES = ["20", "21"]


def _f(pidx, master, text, fid, sid=None, y=10.0):
    return {"page": str(pidx + 1), "pidx": pidx, "master": master, "side": "R",
            "fid": str(fid), "sid": str(sid if sid is not None else fid),
            "prev": "", "next": "", "chars": len(text), "overflow": False,
            "gb": [y, 20.0, 200.0, 180.0], "head": text[:160],
            "tail": text[-80:], "text": text}


def _write(tmp_path, name, frames, page_count):
    p = os.path.join(str(tmp_path), name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"indd": "x", "page_count": page_count, "frames": frames}, f)
    return p


def _src_frames():
    """분할 전 전체(C) 모형: front3 + A12 + sep2 + C7 + 실전4 = 28p."""
    frames, fid = [], 1000
    for pi in range(0, 3):                                   # front
        frames.append(_f(pi, "간지-마스터", "표지", fid)); fid += 1
    pi = 3
    for _sect in range(6):                                   # A 6섹션 × 2지문
        for c in CODES:
            frames.append(_f(pi, "A-마스터", "[%s] 본문 내용" % c, fid))
            fid += 1; pi += 1
    for _ in range(2):                                       # sep
        frames.append(_f(pi, "", "구분", fid)); fid += 1; pi += 1
    for _sect in range(3):                                   # C 3섹션 × 2지문
        for c in CODES:
            frames.append(_f(pi, "C-마스터", "[%s] 어법 내용" % c, fid))
            fid += 1; pi += 1
    # 영작 배열 — 1페이지에 2지문이 스레드로 (프레임 중간에서 지문 21 시작)
    frames.append(_f(pi, "C-마스터",
                     "[20] 영작 첫 지문 문장들.\r[21] 영작 둘째 지문 문장들.",
                     fid)); fid += 1; pi += 1
    # 실전 — p26 첫머리 지문20, p27 중간에서 지문21 시작, p28 짤지문
    frames.append(_f(pi, "O-마스터", "{260120} 실전 지문 20 본문", fid))
    fid += 1; pi += 1
    frames.append(_f(pi, "O-마스터",
                     "앞 지문 꼬리 문장. {260121} 실전 지문 21 본문", fid))
    fid += 1; pi += 1
    frames.append(_f(pi, "O-마스터", "{260143} 짤지문 본문", fid))
    fid += 1; pi += 1
    return frames, pi


def test_구조_유도(tmp_path):
    frames, pc = _src_frames()
    fj = _write(tmp_path, "src.json", frames, pc)
    assert inv_mod.detect_n_problems(fj) == N
    sec = inv_mod.detect_sections(fj, N)
    assert sec["어휘"] == (4, 5)
    assert sec["어법"] == (18, 19)
    # 영작 배열은 C구간의 나머지 — 분할 전이라 1p 에 2지문
    assert sec["영작배열"] == (24, 24)
    assert inv_mod.detect_canon(fj, N, sec) == CODES


def test_실전_분할_대상은_프레임_중간_시작_지문뿐(tmp_path):
    frames, pc = _src_frames()
    fj = _write(tmp_path, "src.json", frames, pc)
    sec = inv_mod.detect_sections(fj, N)
    efs, page_count = exam_mod.exam_frames(fj, sec["영작배열"][1] + 1, 10 ** 6)
    bounds = exam_mod.find_boundaries(efs)
    blocks = exam_mod.blocks_from_boundaries(bounds, page_count)
    targets = exam_mod.split_targets(blocks)
    assert [t["code"] for t in targets] == ["21"]     # 20은 페이지 머리 = 분할 불필요
    exam_blocks, tail = exam_mod.partition(blocks, CODES,
                                          exam_mod.page_info(fj))
    assert sorted(exam_blocks) == CODES
    assert [t["code"] for t in tail] == ["43"]        # canon 밖 짤지문
    assert exam_mod.gate(exam_blocks, tail, CODES) == []


def test_영작배열_스레드_분할(tmp_path):
    frames, pc = _src_frames()
    fj = _write(tmp_path, "src.json", frames, pc)
    sec = inv_mod.detect_sections(fj, N)
    afs, _ = exam_mod.arrange_frames(fj, *sec["영작배열"])
    bounds = exam_mod.arrange_boundaries(afs, CODES)
    assert [b["code"] for b in bounds] == CODES
    assert exam_mod.arrange_gate(bounds, CODES) == []
    targets = exam_mod.arrange_split_targets(bounds)
    assert [t["code"] for t in targets] == ["21"]     # 프레임 중간 시작만


def test_영작배열_지문_누락은_게이트에서_잡힌다(tmp_path):
    frames, pc = _src_frames()
    frames = [f for f in frames
              if not (f["pidx"] == 23 and "영작" in f["text"])]
    frames.append(_f(23, "C-마스터", "[20] 영작 첫 지문만", 9999))
    fj = _write(tmp_path, "src.json", frames, pc)
    sec = inv_mod.detect_sections(fj, N)
    afs, _ = exam_mod.arrange_frames(fj, *sec["영작배열"])
    bounds = exam_mod.arrange_boundaries(afs, CODES)
    assert exam_mod.arrange_gate(bounds, CODES) != []


def _out_frames():
    """재배치 후 모형: front3 + [지문20: 슬롯10p + 실전2p] + [지문21: 10p+3p]."""
    frames, fid, pi = [], 5000, 0
    for _ in range(3):
        frames.append(_f(pi, "간지-마스터", "표지", fid)); fid += 1; pi += 1
    for c, exam_n in (("20", 2), ("21", 3)):
        for _slot in range(10):
            frames.append(_f(pi, "A-마스터", "[%s] 슬롯" % c, fid))
            fid += 1; pi += 1
        for _e in range(exam_n):
            frames.append(_f(pi, "O-마스터", "{2601%s} 실전" % c, fid))
            fid += 1; pi += 1
    frames.append(_f(pi, "O-마스터", "{260143} 짤지문", fid)); pi += 1
    return frames, pi


def _inventory():
    inv = {}
    for c in CODES:
        inv[c] = {name: {"kind": "frames", "pages": [1], "frames": 1}
                  for name, _s, _m in inv_mod.SLOTS}
    return inv


def test_후처리_사이클과_마스터열(tmp_path):
    frames, pc = _out_frames()
    fj = _write(tmp_path, "out.json", frames, pc)
    cycles, fails = plan_mod.build_finish_cycles(fj, _inventory(), CODES)
    assert fails == []
    cy = cycles["cycles"]
    assert [c["code"] for c in cy] == CODES
    assert (cy[0]["start"], cy[0]["end"]) == (4, 15)      # 슬롯10 + 실전2
    assert (cy[1]["start"], cy[1]["end"]) == (16, 28)     # 슬롯10 + 실전3
    # 슬롯 마스터는 SPEC 매핑 1·2→A … 9·10→E
    assert cy[0]["slot_masters"] == ["A-마스터"] * 2 + ["B-마스터"] * 2 + \
        ["C-마스터"] * 2 + ["D-마스터"] * 2 + ["E-마스터"] * 2
    assert cy[0]["pad"] is False and cy[0]["length"] == 12
    assert cy[1]["pad"] is True and cy[1]["length"] == 13   # 홀수 → M 패딩


def test_사이클_시작순서가_canon과_어긋나면_실패(tmp_path):
    frames, pc = _out_frames()
    for f in frames:                       # 두 지문 코드를 뒤바꿔 재배치 붕괴 모사
        f["head"] = f["head"].replace("[20]", "[TMP]").replace("[21]", "[20]")
        f["head"] = f["head"].replace("[TMP]", "[21]")
    fj = _write(tmp_path, "out.json", frames, pc)
    try:
        plan_mod.build_finish_cycles(fj, _inventory(), CODES)
        assert False, "순서 붕괴를 통과시켰다"
    except ValueError as e:
        assert "순서" in str(e)
