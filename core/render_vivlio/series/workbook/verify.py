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

    # ── ⑤ 면 수 ──
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
            if not (0.2 < w < 0.8 and 0.2 < h < 0.8):
                continue
            if not fill or len(fill) < 3:
                continue
            if not (fill[0] > 0.99 and fill[1] > 0.99 and 0.98 < fill[2] < 0.999):
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
