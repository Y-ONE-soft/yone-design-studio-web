# -*- coding: utf-8 -*-
"""선택 워크북 산출물 교차검증 (G3) — PDF 기반, InDesign 무접촉.

기계검증(오버셋·링크·폰트·프리플라이트)이 **원리적으로 통과시키는** 결함을
잡는다. 2026-08-08 실측으로 전부 실제 발생한 것들:

  - 짝 스텝 상·하단이 서로 다른 지문 (13페이지)
  - 발문 유형(밑줄형/네모형)이 문제 유형과 불일치
  - 보충 원고 헤더가 지면에 그대로 인쇄
  - trim 전 PDF 가 남아 INDD 와 페이지 수 불일치
  - 섹션 내 같은 지문 중복

사용:
    python3 scripts/wbsel_verify_output.py <pdf> [--indd-pages N] [--codes N]

종료코드 0 = 전항 통과.

⚠ 검사기 자체의 유효성을 먼저 확인할 것 — 망가진 이전 산출물에 돌려
   결함이 검출되는지 보고 나서야 "통과"를 인정한다. 무조건 통과하는 검사는
   검사가 아니다.
"""
import argparse
import collections
import re
import sys

import fitz

_PROMPT = re.compile(r'어법.{0,10}(틀린|맞는)')
_SEC = re.compile(
    r'(A1\s+어휘\s*선택\s*[12]?|A2\s+본문\s*O/X|B1\s+본문\s*정리'
    r'|B2\s+내용\s*종합|C1\s+문장\s*배열|C2\s+빈칸\s*어휘|A1\s+어법\s*선택'
    r'|B1\s+어법\s*O/X|C1\s+빈칸\s*어법|C2\s+영작\s*배열|S\s+실전\s*문제)')
_HDR_RESIDUE = re.compile(r'no\.\s*\d|\d+강\s*-\s*no')
_EN = re.compile(r"[A-Za-z']+")


def _words(s):
    return _EN.findall(s)


def _same_passage(top, btm, window=40, take=8):
    """하단 앞 take어절이 상단 앞 window어절 안에 순서대로 나오는가.

    상단(어법선택)은 [A / B] 선택지로 어절이 늘어나고 하단은 ①~⑤가 붙어서
    단순 문자열 비교로는 같은 지문도 다르다고 나온다."""
    b = [w.lower() for w in _words(btm)][:take]
    a = [w.lower() for w in _words(top)][:window]
    if not b:
        return True
    i = 0
    for w in a:
        if w == b[i]:
            i += 1
            if i == len(b):
                return True
    return False


def _pair_rows(doc, sec_of):
    """짝 스텝(상단+하단) 페이지 → [(page, top, btm, prompt)]"""
    rows = []
    for pno in range(doc.page_count):
        page = doc[pno]
        raw = page.get_text()
        # 실전(STEP3)은 1지문 다문항이라 상·하단 짝 개념이 없다.
        # 러닝헤더 문자열만 보면 놓치므로 섹션 구간으로도 거른다.
        if "STEP03" in raw or "실전 문제" in raw:
            continue
        if sec_of.get(pno + 1) == "S 실전 문제":
            continue
        blocks = sorted(page.get_text("blocks"), key=lambda b: b[1])
        py, prompt = None, ""
        for b in blocks:
            if _PROMPT.search(b[4]):
                py, prompt = b[1], b[4].strip()
                break
        if py is None:
            continue

        def first_en(bs):
            for b in bs:
                if len(_words(b[4])) >= 8:
                    return b[4].replace("\n", " ").strip()
            return None

        top = first_en([b for b in blocks if b[3] <= py])
        btm = first_en([b for b in blocks if b[1] > py])
        if top and btm:
            rows.append((pno + 1, top, btm, prompt))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--indd-pages", type=int, default=0,
                    help="INDD 페이지 수 (trim 후 재출력 누락 검출)")
    ap.add_argument("--codes", type=int, default=0, help="요청 문항 수")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    texts = [doc[i].get_text() for i in range(doc.page_count)]
    fails = []

    print("PDF 페이지: %d" % doc.page_count)
    if args.indd_pages:
        ok = doc.page_count == args.indd_pages
        print("1) PDF==INDD 페이지 수: %s (%d vs %d)"
              % ("OK" if ok else "실패", doc.page_count, args.indd_pages))
        if not ok:
            fails.append("PDF 가 trim 이전 상태 — 재출력 필요")
    else:
        print("1) PDF==INDD 페이지 수: 생략 (--indd-pages 미지정)")

    residue = [(i + 1, l.strip()) for i, t in enumerate(texts)
               for l in t.split("\n") if _HDR_RESIDUE.search(l)]
    print("2) 헤더/라벨 인쇄 잔재: %d건 %s"
          % (len(residue), residue[:3] if residue else ""))
    if residue:
        fails.append("헤더 잔재 %d건" % len(residue))

    cur, sec_of = None, {}
    for i, t in enumerate(texts):
        m = _SEC.search(t)
        if m:
            cur = re.sub(r'\s+', ' ', m.group(1))
        sec_of[i + 1] = cur

    # 구조적 페이지는 빈 페이지가 정상이다:
    #   앞부속(p1~2) / 판권부(뒤 3p) / 간지 스프레드(빈 좌측 + "고N 모의고사" 우측)
    def _is_divider(idx):
        return (idx < len(texts) and "모의고사" in texts[idx]
                and len(re.sub(r'\s', '', texts[idx])) < 25)

    blank_real = []
    for i, t in enumerate(texts):
        if len(re.sub(r'\s', '', t)) >= 25:
            continue
        if i + 1 <= 2 or i + 1 >= doc.page_count - 2:
            continue                      # 앞부속 / 판권부
        if _is_divider(i):
            continue                      # 간지 우측
        if _is_divider(i + 1):
            continue                      # 간지 좌측(빈 페이지 + 다음이 간지)
        blank_real.append(i + 1)
    print("3) 빈 페이지: %d개 %s (앞부속·간지·판권부 제외)"
          % (len(blank_real), blank_real[:10]))
    if blank_real:
        fails.append("빈 페이지 %d개" % len(blank_real))
    first = collections.defaultdict(list)
    for i, t in enumerate(texts):
        for line in t.split("\n"):
            w = _words(line)
            if len(w) >= 8:
                first[" ".join(w[:8]).lower()].append(i + 1)
                break
    dupes = []
    for k, v in first.items():
        if len(v) < 2 or k.startswith("s t e p"):
            continue
        c = collections.Counter(sec_of.get(p) for p in v)
        for s, n in c.items():
            if n > 1 and s != "S 실전 문제":
                dupes.append((s, k[:38]))
    print("4) 섹션 내 지문 중복: %d건 %s" % (len(dupes), dupes[:3]))
    if dupes:
        fails.append("지문 중복 %d건" % len(dupes))

    rows = _pair_rows(doc, sec_of)
    mism = [(p, t, b) for p, t, b, _ in rows if not _same_passage(t, b)]
    print("5) 짝 스텝 상·하단 지문 일치: %d/%d (불일치 %d)"
          % (len(rows) - len(mism), len(rows), len(mism)))
    for p, t, b in mism[:5]:
        print("     p%-4d 상단 %-34s 하단 %s" % (p, t[:32], b[:32]))
    if mism:
        fails.append("상·하단 불일치 %d페이지" % len(mism))

    # 발문 유형 == 문제 유형 (네모형은 (A)(B)(C), 밑줄형은 ①~⑤)
    bad_prompt = []
    for p, _t, b, prompt in rows:
        box_q = bool(re.search(r'\(\s*A\s*\).{0,80}\(\s*B\s*\)', b))
        box_p = "네모" in prompt
        if box_q != box_p:
            bad_prompt.append((p, "네모형 문제/밑줄형 발문" if box_q
                               else "밑줄형 문제/네모형 발문"))
    print("6) 발문 유형 == 문제 유형: %d건 불일치 %s"
          % (len(bad_prompt), bad_prompt[:5]))
    if bad_prompt:
        fails.append("발문 유형 불일치 %d건" % len(bad_prompt))

    if args.codes and rows:
        print("7) 짝 페이지 수: %d (요청 문항 %d)" % (len(rows), args.codes))
        if len(rows) != args.codes:
            fails.append("짝 페이지 %d ≠ 문항 %d (일부 문항의 상·하단이 "
                         "다른 페이지로 갈라졌을 수 있다)"
                         % (len(rows), args.codes))

    print("\n===== 판정 =====")
    if fails:
        for f in fails:
            print("  실패: " + f)
        return 1
    print("  전항 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
