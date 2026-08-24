# -*- coding: utf-8 -*-
"""세로↔가로 내용 대조 — 세로→가로 변환의 유일한 신뢰 가능한 검수.

세로→가로는 **내용 보존 변환**이다. 세로중간본에 있던 문단은 가로 결과물에
전부 있어야 한다. 조판 로그의 "오버셋 0 / 슬롯 검수 OK / 빈칸대조 일치"는
전부 통과인데 지면은 잘려 있을 수 있다 — 프레임 매칭에서 빠진 내용은 조용히
사라지기 때문이다(2026-08-25 실측: STEP3 문항이 선지 중간에서 끊기고,
문장배열 상단 카드가 통째로 소실. 로그는 전부 정상이었다).

    python3 scripts/v2h_content_diff.py <세로.indd> <가로.indd> [--max 40]

종료코드 0 = 손실 없음, 1 = 손실 있음. 완료 보고 전에 반드시 통과시킬 것.
"""
import argparse
import os
import re
import subprocess
import sys
import unicodedata

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
_JSX = os.path.join(_ROOT, "engines", "vert_to_horiz", "jsx", "dump_paras.jsx")

# 변환 과정에서 **정당하게** 바뀌는 것들 — 대조에서 제외한다.
#   지문번호 라벨: 세로 "{240937}" / "36" → 가로 "03" (fix_passage_numbers)
#   페이지 번호·러닝헤드 등 짧은 조각
_RE_LABEL_ONLY = re.compile(r"^[\[\{(]?\s*\d{1,6}\s*[\]\})]?$")
_RE_NUM_HEAD = re.compile(r"^\s*[\[\{]?\d{1,6}[\]\}]?\s*")
# 세로판 전용 섹션 표제 — 가로는 사이드 라벨로 대신하므로 없는 게 정상
_RE_SERO_HEAD = re.compile(
    r"^\s*[A-C]\s*(본문|내용|어휘|어법|빈칸|문장|영작|실전)")
_RE_DIGITS = re.compile(r"\d+")
# 빈칸 표기는 세로("424[￼]")와 가로(번호 재매김·앵커 처리)가 다르게 찍힌다.
# 글자만 남긴 형태로도 비교해 이 차이를 흡수한다.
_RE_WORDCHARS = re.compile(r"[^0-9A-Za-z가-힣]+")


def _letters(s):
    return _RE_WORDCHARS.sub("", _RE_DIGITS.sub("", unicodedata.normalize("NFC", s)))


def _norm(s):
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\s　￼]+", "", s)
    return s


def _dump(indd, tag, log):
    out = "/tmp/v2hdiff_%s.txt" % tag
    jsx = "/tmp/v2hdiff_%s.jsx" % tag
    jlog = "/tmp/v2hdiff_%s.log" % tag
    for p in (out, jlog):
        try:
            os.remove(p)
        except OSError:
            pass
    code = open(_JSX, encoding="utf-8").read()
    code = code.replace("__SRC__", indd).replace("__OUT__", out).replace("__LOG__", jlog)
    with open(jsx, "w", encoding="utf-8") as f:
        f.write(code)
    from core.indesign.runner import run_jsx
    run_jsx(jsx, log, poll_log_path=jlog, timeout=1800,
            completion_marker="===== 덤프 완료 =====")
    if not os.path.exists(out):
        raise RuntimeError("덤프 실패: %s" % indd)
    rows = []
    for line in open(out, encoding="utf-8", errors="ignore"):
        line = line.rstrip("\n")
        if not line:
            continue
        page, _, text = line.partition("\t")
        rows.append((page, text))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verti")
    ap.add_argument("horiz")
    ap.add_argument("--max", type=int, default=40)
    args = ap.parse_args()

    def log(m):
        print("  " + str(m), flush=True)

    print("[대조] 세로 덤프…", flush=True)
    v = _dump(args.verti, "v", log)
    print("[대조] 가로 덤프…", flush=True)
    h = _dump(args.horiz, "h", log)

    # 가로 문단 집합 — 라벨 차이를 흡수하려고 "번호 뗀 형태"도 함께 넣는다
    hset = set()
    for _, t in h:
        n = _norm(t)
        if not n:
            continue
        hset.add(n)
        hset.add(_norm(_RE_NUM_HEAD.sub("", t)))
        # 빈칸 번호는 후처리(fix_passage_numbers)가 정당하게 다시 매긴다.
        # 숫자를 뗀 형태로도 넣어 그 차이를 흡수한다.
        hset.add(_RE_DIGITS.sub("", n))
        lt = _letters(t)
        if len(lt) >= 12:
            hset.add("L:" + lt)

    missing = []
    total = 0
    for page, t in v:
        n = _norm(t)
        if not n or len(n) < 12:          # 너무 짧은 조각은 오탐이 많다
            continue
        if _RE_LABEL_ONLY.match(t.strip()):
            continue
        if _RE_SERO_HEAD.match(t.strip()):
            continue
        total += 1
        if n in hset:
            continue
        if _norm(_RE_NUM_HEAD.sub("", t)) in hset:
            continue
        if _RE_DIGITS.sub("", n) in hset:
            continue
        lt = _letters(t)
        if len(lt) >= 12 and ("L:" + lt) in hset:
            continue
        missing.append((page, t))

    print("")
    print("=" * 60)
    print("세로 문단 %d개 대조 / 가로에서 못 찾음 %d개" % (total, len(missing)))
    if missing:
        print("-" * 60)
        for page, t in missing[:args.max]:
            print("  세로 p%-4s %s" % (page, t[:88]))
        if len(missing) > args.max:
            print("  … 외 %d개" % (len(missing) - args.max))
        print("=" * 60)
        print("결과: 실패 — 위 내용이 가로 결과물에 없습니다.")
        return 1
    print("=" * 60)
    print("결과: 통과 — 세로 내용이 가로에 전부 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
