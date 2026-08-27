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


def _dump(indd, tag, log, stall_limit=None):
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
            completion_marker="===== 덤프 완료 =====",
            stall_limit=stall_limit)
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


# 지면에 나오지 않는 문단(덤프가 사유를 찍는다) — 대조 대상이 아니다.
# 세로에서도 인쇄되지 않으므로 "가로에 없다"가 결함이 아니다. 다만 이 수를
# 조용히 0으로 만들지는 않는다: 세로 쪽 오버셋은 세로 자체의 문제이므로
# 호출부가 볼 수 있게 따로 돌려준다.
_UNPRINTED = ("OVF", "PB", "?")


def _template_paras(template_indd, log, stall_limit):
    """세로 템플릿의 문단 집합 — 조판으로 채워지지 않은 자리의 샘플 텍스트.

    세로결합은 템플릿 위에 내용을 얹는다. 원고가 없는 자리에는 템플릿의
    **샘플 문장이 그대로 남는다**(실측: "All experimental equipment must be
    handled with care." 가 세로중간본 p123·p223 에 잔존). 가로는 trim_unused
    가 그 미사용 페이지를 지우므로 없는 게 정상이다. 유실로 세면 안 된다.

    덤프는 8초쯤 걸려서 파일 mtime 기준으로 캐시한다.
    """
    import hashlib
    if not template_indd or not os.path.exists(template_indd):
        return set()
    sig = hashlib.md5(
        ("%s|%s" % (template_indd, os.path.getmtime(template_indd)))
        .encode("utf-8")).hexdigest()[:12]
    cache = "/tmp/v2hdiff_tpl_%s.txt" % sig
    if not os.path.exists(cache):
        rows = _dump(template_indd, "tpl", log, stall_limit=stall_limit)
        with open(cache, "w", encoding="utf-8") as f:
            for _, t in rows:
                f.write(t.replace("\n", " ") + "\n")
    out = set()
    for line in open(cache, encoding="utf-8", errors="ignore"):
        n = _norm(line.rstrip("\n"))
        if len(n) >= 12:
            out.add(n)
    log("템플릿 샘플 문단 %d개 로드 (대조에서 잔재로 분류)" % len(out))
    return out


def compare(verti, horiz, log=None, stall_limit=900, unprinted_out=None,
            template_indd=None, leftover_out=None):
    """세로/가로 .indd 를 덤프해 대조 → (대조한 문단 수, 유실 목록).

    유실 목록은 [(세로 페이지, 문단 텍스트)]. 빈 리스트면 손실 0.
    파이프라인(scripts/mt_pipeline.py)이 완료 판정에 그대로 쓴다 — CLI 와
    같은 판정을 쓰려고 함수로 떼어냈다(로직 분기 금지).

    unprinted_out: 리스트를 주면 세로에서 인쇄되지 않는 문단을 담아 준다.
    template_indd: 세로 템플릿 경로. 주면 그 안의 샘플 문단은 유실이 아니라
        **템플릿 잔재**로 분류한다(_template_paras 주석 참조).
    leftover_out: 리스트를 주면 그 잔재를 담아 준다.
    """
    if log is None:
        def log(m):
            print("  " + str(m), flush=True)

    tpl = _template_paras(template_indd, log, stall_limit)

    print("[대조] 세로 덤프…", flush=True)
    v = _dump(verti, "v", log, stall_limit=stall_limit)
    print("[대조] 가로 덤프…", flush=True)
    h = _dump(horiz, "h", log, stall_limit=stall_limit)

    # 가로 문단 집합 — **지면에 나오는 것만** 넣는다.
    # 종전엔 오버셋 문단까지 넣어서, 가로에서 프레임에 안 들어가 인쇄되지
    # 않는 내용을 "있다"고 판정했다(2026-08-25 실측: 13강 17~32권에서 세로
    # 인쇄문단 2885개 중 546개가 가로 오버셋이었는데 대조는 손실 0 통과).
    # 이 대조의 질문은 "가로 파일에 존재하는가"가 아니라 "가로 지면에
    # 나오는가"다. 라벨 차이를 흡수하는 완화형은 종전 그대로.
    h_printed = [(pg, t) for pg, t in h if pg not in _UNPRINTED]
    n_ovf_h = len(h) - len(h_printed)
    if n_ovf_h:
        log("가로에서 인쇄되지 않는 문단 %d개 — 대조 집합에서 제외" % n_ovf_h)
    hset = set()
    for _, t in h_printed:
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
    unprinted = 0
    for page, t in v:
        n = _norm(t)
        if not n or len(n) < 12:          # 너무 짧은 조각은 오탐이 많다
            continue
        if page in _UNPRINTED:
            unprinted += 1
            if unprinted_out is not None:
                unprinted_out.append((page, t))
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
        if n in tpl:
            # 원고가 안 채운 자리의 템플릿 샘플 — 가로엔 없는 게 정상
            if leftover_out is not None:
                leftover_out.append((page, t))
            continue
        missing.append((page, t))

    if unprinted:
        log("세로에서 인쇄되지 않는 문단 %d개 — 대조 제외 "
            "(OVF=오버셋 / PB=붙임 영역)" % unprinted)
    if leftover_out:
        log("템플릿 잔재 %d개 — 대조 제외 (원고가 안 채운 자리의 샘플 문장)"
            % len(leftover_out))
    return total, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verti")
    ap.add_argument("horiz")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--template", default="",
                    help="세로 템플릿 .indd — 채워지지 않은 자리의 샘플 문장을 "
                         "유실이 아니라 잔재로 분류한다")
    args = ap.parse_args()

    total, missing = compare(args.verti, args.horiz,
                             template_indd=args.template or None)

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
