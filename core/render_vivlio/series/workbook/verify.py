"""워크북 검수 게이트 — 계열 고유.

워크북에서 반복된 사고는 "조판은 성공했는데 내용이 조용히 빠졌다"였다
(W80: 한 줄이 정답부를 잘라 뒤 115줄 증발 · 파일럿 이전 여러 건). 그래서
**원고(플랜) ↔ PDF 직접 대조**를 첫 게이트로 둔다. 면 수·넘침은 그 다음이다.

지면 규칙(상단/하단 자리)은 텍스트 대조로 안 잡힌다 — `docs/워크북_섹션_지면규칙.md`
가 못 박은 그대로다. 그래서 **자리 게이트**를 따로 둔다.
"""
import re
import unicodedata

from core.render_vivlio import probe
from core.render_vivlio.series.workbook import data as data_mod

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
_RE_ANSLEAK = re.compile(r"[?.]\s*[①②③④⑤⑥⑦⑧⑨⑩]\s*$")


def _norm(s):
    s = unicodedata.normalize("NFC", s or "")
    s = (s.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"'))
    return re.sub(r"\s+", " ", s).strip()


def _words(s):
    return set(w.lower() for w in _RE_WORD.findall(_norm(s)))


def check(cfg, log, report):
    pdf = cfg.out_pdf()
    d = data_mod.load(cfg)
    texts = probe.page_texts(pdf)
    joined = _norm(" ".join(texts))
    pdf_words = _words(joined)

    # ── ① 내용 보존: 원고 낱말이 PDF 에 있는가 ──
    missing_rows = []
    total = 0
    for st in d["steps"]:
        lost = []
        for g in st["groups"]:
            for blocks in g["units"]:
                for b in blocks:
                    t = b.get("text") or ""
                    ws = _words(t)
                    if len(ws) < 3:
                        continue
                    total += 1
                    gone = ws - pdf_words
                    if len(gone) > max(1, len(ws) * 0.34):
                        lost.append((_norm(t)[:70], sorted(gone)[:6]))
        if lost:
            missing_rows.append((st["key"], lost))
    if missing_rows:
        for key, lost in missing_rows:
            report.fail(f"[내용 유실] {key} — {len(lost)}단락이 PDF 에 없다")
            for t, gone in lost[:4]:
                report.note(f"      · {t} … 없는 낱말 {gone}")
    else:
        report.note(f"내용 보존 — 검사 단락 {total}개, 유실 0")

    # ── ② 정답 누출: 발문 꼬리에 동그라미 숫자 ──
    leaks = [t for t in texts if _RE_ANSLEAK.search(_norm(t))]
    if leaks:
        report.fail(f"[정답 누출] 발문 꼬리에 정답 표시가 인쇄된 면 {len(leaks)}개")
    else:
        report.note("정답 누출 없음")

    # ── ③ 빈 면 ──
    blanks = probe.blank_pages(texts)
    allow = set((cfg.section("verify") or {}).get("blank_pages") or [])
    unexpected = [p for p in blanks if p not in allow and p > 3]
    if unexpected:
        report.warn(f"[빈 면] {unexpected[:10]} — 간지·마감 면이 아니면 유실 신호")
    else:
        report.note(f"빈 면 {len(blanks)}개 (모두 예상 범위)")

    # ── ④ 자리(상/하): pair 스텝의 하단 발문이 아래쪽에 있는가 ──
    _check_zones(pdf, d, report, cfg.build_dir)

    # ── ⑤ 머리말만 있고 본문이 빈 면 ──
    _check_empty_body(cfg, report)

    # ── ⑥ 원고 퇴화: 빈칸 스텝이 '낱말 목록'이면 원고가 잘못 골렸다 ──
    _check_degraded(d, report)

    # ── ⑦ 서체 폴백: 스텝 로고가 대체 서체로 찍혔는가 ──
    _check_fonts(cfg, report)

    # ── ⑧ 장 넘김: '위 글' 문항이 앞장을 넘겨봐야 하는가 ──
    _check_turn(cfg, report)

    # ── ⑨ 면 수 ──
    report.note(f"면 수 {probe.page_count(pdf)}p")
    return report


def _check_zones(pdf, d, report, cfg_build_dir=None):
    """넘침 — 칸 끝 표식(.zend, 흰 0.4mm 사각)의 y 를 잰다.

    눈으로는 안 보이는 사고다: 내용이 판면 아래로 흘러나가면 조판은 성공했다고
    나오고 PDF 만 잘려 있다. 표식이 판면 바닥(286.5mm)을 넘으면 넘침이다.
    """
    doc = probe.open_pdf(pdf)
    over = []
    marks = 0
    for i in range(doc.page_count):
        for rect, fill, _c, _w in probe.drawings_mm(doc[i]):
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if not (0.25 < w < 0.6 and 0.25 < h < 0.6):
                continue
            if not fill or len(fill) < 3:
                continue
            if not (fill[0] > 0.99 and fill[1] > 0.99 and 0.994 < fill[2] < 1.001):
                continue
            marks += 1
            if rect[3] > 286.5:
                over.append((i + 1, round(rect[3], 1)))
    doc.close()
    # 표식이 **사라진** 것도 넘침이다 — 판면 밖으로 나가면 PDF 에 안 그려진다.
    want = 0
    try:
        import os
        with open(os.path.join(cfg_build_dir, "index.html"), encoding="utf-8") as f:
            want = f.read().count('class="zend"')
    except Exception:
        pass
    if over:
        report.fail(f"[넘침] 칸을 넘긴 면 {len(over)}개 — {over[:8]}")
    elif want and marks < want:
        report.fail(f"[넘침] 칸 끝 표식이 사라졌다 — 만든 것 {want} / 찍힌 것 {marks} "
                    f"(판면 밖으로 흘러 내용이 잘렸다는 뜻)")
    else:
        report.note(f"넘침 없음 (칸 끝 표식 {marks}/{want or marks}개 확인)")


def _check_empty_body(cfg, report):
    """머리말·꼬리말만 있고 **판면이 빈 면** — 보통 면 나눔이 새고 있다는 뜻.

    `blank_pages` 는 이런 면을 못 잡는다(머리말 글자가 있어서 '빈 면'이 아니다).
    실측으로 섹션마다 이런 면이 하나씩 새고 있었는데 게이트가 조용히 통과시켰다.
    """
    pdf = cfg.out_pdf()
    doc = probe.open_pdf(pdf)
    bad = []
    for i in range(doc.page_count):
        page = doc[i]
        body = [1 for (x0, y0, x1, y1) in probe.text_blocks_mm(page)
                if 30.0 < y0 < 280.0 and x0 < 195.0]   # 사이드 탭 제외
        if body:
            continue
        # 간지는 색면이 판면을 덮는다 — 큰 색면이 있으면 간지로 본다
        big = any((r[2] - r[0]) > 150 and (r[3] - r[1]) > 150
                  for r, f, _c, _w in probe.drawings_mm(page) if f)
        if not big and page.get_text().strip():
            bad.append(i + 1)
    doc.close()
    allow = set((cfg.section("verify") or {}).get("blank_pages") or [])
    bad = [p for p in bad if p not in allow]
    if bad:
        report.fail(f"[빈 지면] 머리말만 있고 본문이 없는 면 {len(bad)}개 — {bad[:10]}")
    else:
        report.note("빈 지면 없음 (머리말만 있는 면 0)")


_RE_WORDLIST = re.compile(r"^\s*\d+\.\s*[A-Za-z][A-Za-z'\-]*\s*$")


def _check_degraded(d, report):
    """빈칸 스텝에 **문장이 없고 낱말만** 있으면 세운다.

    빈칸 지면의 정상 모양은 `1[Bad] 2[lighting] can 3[increase] …` 처럼 **문장**
    안에 정답이 표시된 것이다(해설지 원고를 넣고 정답 부분을 감춘다). 문장이
    없이 `1. encourage` 만 늘어서면 지면이 낱말 목록으로 인쇄된다.

    ⚠ 원인은 단정하지 않는다 — 원고 선택일 수도, 파서가 문장을 못 살린 것일
    수도 있다. 증상만 정확히 말하고 사람이 판단하게 둔다.
    """
    for st in d["steps"]:
        if st["key"] not in ("step1_c2", "step2_c1"):
            continue
        rows = [b.get("text") or "" for g in st["groups"]
                for u in g["units"] for b in u
                if b["role"] in ("blank_vocab", "blank_gram")]
        if len(rows) < 5:
            continue
        wordish = sum(1 for t in rows if _RE_WORDLIST.match(t))
        if wordish > len(rows) * 0.8:
            report.fail(
                f"[원고 퇴화] {st['key']} — {len(rows)}줄이 거의 다 '번호. 낱말' "
                f"목록이다({wordish}줄) — 문장이 없어 지면이 낱말 목록으로 "
                f"인쇄된다. 원고(문제지/해설지)를 확인할 것")


def _check_fonts(cfg, report):
    """스텝 로고 서체가 실제로 실렸는가 — 폴백은 조용히 예뻐 보인다.

    TTMamablock 은 로컬에 설치돼 있지 않아 리포 동봉본을 쓴다. 그 파일이
    빠지거나 cmap 이 없으면 Gmarket 으로 대체돼 **로고만 딴 서체**가 된다.
    실측으로 한 번 겪은 사고라 게이트로 남긴다.
    """
    import os
    fdir = os.path.join(cfg.build_dir, "fonts")
    want = "TTMamablockB.ttf"
    if not os.path.exists(os.path.join(fdir, want)):
        report.fail(f"[서체] {want} 가 빌드에 없다 — 스텝 로고가 대체 서체로 찍힌다")
        return
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(os.path.join(fdir, want))
        cm = f.getBestCmap() if "cmap" in f else None
        missing = [c for c in "ABCS12" if not cm or ord(c) not in cm
                   or not f["glyf"][cm[ord(c)]].numberOfContours]
        if missing:
            report.fail(f"[서체] 로고 글자 {missing} 의 아웃라인이 없다 — "
                        f"대체 서체로 찍힌다")
        else:
            report.note("스텝 로고 서체 정상 (TTMamablock 아웃라인 확인)")
    except Exception as e:
        report.warn(f"[서체] 확인 못 함: {e}")


_RE_REF = re.compile(r"^\s*(위 ?글|윗글|위의 글|In the above|위 그림)")


def _mark_pages(doc, lo, hi, blue_lo, blue_hi):
    """흰 표식(크기로 구분)이 있는 면 번호들."""
    out = []
    for i in range(doc.page_count):
        for rect, fill, _c, _w in probe.drawings_mm(doc[i]):
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if not (lo < w < hi and lo < h < hi):
                continue
            if not (fill and len(fill) >= 3 and fill[0] > 0.99 and fill[1] > 0.99
                    and blue_lo < fill[2] < blue_hi):
                continue
            out.append(i + 1)
            break
    return out


def _check_turn(cfg, report):
    """'위 글' 문항이 **장을 넘겨야** 보이는가.

    펼침면은 (짝수 왼쪽, 홀수 오른쪽)이다. 세트(안내문+지문+딸린 문항)가
    **홀수(오른쪽) 면에서 시작해 다음 면으로 넘어가면** 학생이 장을 넘겨 가며
    풀어야 한다 — 그것만 잡는다(왼쪽→오른쪽은 같은 펼침면이라 괜찮다).

    ⚠ 지문 유무를 글자 길이로 재려던 첫 판은 **헛돌았다** — 2단이라 줄이 다
      짧아 완성본까지 0건으로 통과했다. 그래서 렌더러가 세트의 처음(0.6mm)과
      끝(0.8mm)에 심어 둔 흰 표식으로 **면 구간**을 직접 잰다.
    """
    # 짝 맺기는 **당겨붙이기 패스와 같은 코드**를 쓴다 — 게이트와 고치는 쪽이
    # 다른 셈을 하면, 고쳤다고 나온 판이 게이트에서 걸린다(실제로 걸렸다).
    from core.render_vivlio.series.workbook import fit as _fit
    pdf = cfg.out_pdf()
    bad = _fit.turns(pdf)
    doc = probe.open_pdf(pdf)
    n_set = sum(1 for m in _fit._marks(doc) if m[3] == "sbeg")
    doc.close()
    if not n_set:
        report.note("장 넘김 — 세트가 없어 검사 안 함")
        return
    if bad:
        report.fail(f"[장 넘김] 오른쪽 면에서 시작해 장을 넘기는 세트 {len(bad)}건 — "
                    + ", ".join(f"p{a}→p{b}" for _i, a, b, _c, _y in bad[:6]))
    else:
        report.note(f"장 넘김 없음 (세트 {n_set}개 · 오른쪽에서 시작해 장을 "
                    f"넘기는 세트 0개)")
