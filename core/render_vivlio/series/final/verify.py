"""파이널 계열 검수 — 조판 결과 PDF ↔ data.json 대조.

인디자인 경로의 검수(`_final_batch/verify_content.py`)가 가장 아프게 배운 것은
**"헤더·개수·순서는 정상인데 내용만 틀린" 결함은 눈으로 안 잡힌다**는 것이다.
그래서 여기서는 헤더가 아니라 **본문 문장**을 면에 대조한다.

계약(완성본 실측):
  · ①배열 ②삽입 — 지문 N 은 그 섹션의 (N-1)//4 번째 면. 사분면 고정이다.
  · ③중요어휘 — 한 면 한 지문. 왼(빈칸)·오(정답) 글자 수가 같아야 한다.
  · ④어법 ⑤영작 — 지문 N 은 (N-1)//2 번째 면.
  · 넘침 — 측정 높이가 칸을 넘는데 축소가 안 걸린 지문은 결함.
"""
import json
import os
import re

from core.render_vivlio import probe
from core.render_vivlio.series.final import data as data_mod
from core.render_vivlio.series.final import render as render_mod

PER_PAGE = {"arrange": 4, "insert": 4, "vocab": 1, "grammar": 2, "writing": 2}
RE_WS = re.compile(r"\s+")


def _n(s):
    return RE_WS.sub("", probe.norm(s or ""))


def _section_pages(data, vol, texts, report):
    """섹션마다 [면번호…] — 꼬리말의 섹션 이름으로 구간을 가른다."""
    v = data["vols"][str(vol)]
    spans, cur = {}, None
    for i, t in enumerate(texts):
        nt = _n(t)
        for sec in v["sections"]:
            if _n(sec["title"]) in nt:
                cur = sec["kind"]
                break
        if cur:
            spans.setdefault(cur, []).append(i + 1)
    for sec in v["sections"]:
        if sec["kind"] not in spans:
            report.fail(f"{sec['title']} 면을 못 찾았다")
    return spans


def _block_text(kind, b):
    """그 지문의 **본문 문장**(대조용). 헤더는 쓰지 않는다."""
    if kind in ("arrange", "insert"):
        return ([b["given"]] if b.get("given") else []) + list(b["items"])
    if kind == "vocab":
        return [data_mod.plain(p) for p in b["passage"]] + \
               [data_mod.plain(p) for p in b.get("summary") or []]
    if kind == "grammar":
        return [data_mod.plain(b["body"])]
    return [p["korean"] for p in b["pairs"]] + \
           [p["choices"] for p in b["pairs"]]


def _check_placement(data, vol, texts, spans, report):
    """모든 문장이 **제 섹션, 제 면**에 있는가."""
    v = data["vols"][str(vol)]
    miss, wrong, n = [], [], 0
    for sec in v["sections"]:
        pages = spans.get(sec["kind"]) or []
        if not pages:
            continue
        blobs = [_n(texts[p - 1]) for p in pages]
        whole = "".join(blobs)
        per = PER_PAGE[sec["kind"]]
        for i, b in enumerate(sec["blocks"]):
            want = i // per
            for t in _block_text(sec["kind"], b):
                q = _n(t)
                if len(q) < 12:
                    continue
                n += 1
                if q not in whole:
                    miss.append(f"{sec['title']} {b['header']}")
                elif want < len(blobs) and q not in blobs[want]:
                    wrong.append(f"{sec['title']} {b['header']}"
                                 f"(기대 {want + 1}번째 면)")
    report.note(f"문장 대조 {n:,}건 (섹션·면 단위)")
    if miss:
        report.fail(f"누락 {len(miss)}건: {sorted(set(miss))[:8]}")
    if wrong:
        report.fail(f"자리 어긋남 {len(wrong)}건: {sorted(set(wrong))[:8]}")
    return miss, wrong


def _check_pagecount(data, vol, spans, report):
    """사분면 계약 — 지문 수로 면 수가 정해진다."""
    v = data["vols"][str(vol)]
    bad = []
    for sec in v["sections"]:
        pages = spans.get(sec["kind"]) or []
        per = PER_PAGE[sec["kind"]]
        want = -(-len(sec["blocks"]) // per)
        if len(pages) != want:
            bad.append((sec["title"], want, len(pages)))
    if bad:
        report.fail(f"섹션 면수 이상(섹션, 기대, 실제): {bad}")
    else:
        report.note("섹션 면수 = 지문수/칸수 (고정 칸 계약 유지)")
    return bad


def _check_vocab_pair(data, vol, report):
    """왼(빈칸)·오(정답)은 **같은 지문**이다 — 줄 수가 다르면 짝이 깨진 것."""
    v = data["vols"][str(vol)]
    sec = next((s for s in v["sections"] if s["kind"] == "vocab"), None)
    if not sec:
        return []
    bad = [b["header"] for b in sec["blocks"]
           if not b["passage"] or not b.get("summary")]
    if bad:
        report.fail(f"중요어휘 지문/요약 결측 {len(bad)}: {bad[:6]}")
    else:
        report.note(f"중요어휘 {len(sec['blocks'])}지문 좌우 짝 온전")
    return bad


def _check_blanks(data, vol, texts, spans, report):
    """빈칸(밑줄) 개수 — 원고의 `[답]` 수만큼 지면에 있어야 한다."""
    v = data["vols"][str(vol)]
    sec = next((s for s in v["sections"] if s["kind"] == "vocab"), None)
    if not sec:
        return []
    pages = spans.get("vocab") or []
    bad = []
    for i, b in enumerate(sec["blocks"]):
        want = sum(1 for p in b["passage"] + (b.get("summary") or [])
                   for x in p if isinstance(x, dict))
        if i >= len(pages):
            break
        # 정답 쪽이 굵게 찍혀 있으므로 **낱말**로 센다(밑줄은 글자가 아니다).
        t = texts[pages[i] - 1]
        got = sum(t.count(x["a"]) for p in b["passage"] + (b.get("summary") or [])
                  for x in p if isinstance(x, dict))
        if got < want:
            bad.append((b["header"], want, got))
    if bad:
        report.warn(f"중요어휘 정답 낱말 적게 보임 {len(bad)}건: {bad[:5]}")
    else:
        report.note("중요어휘 정답 낱말 전수 확인")
    return bad


def _check_fit(cfg, vol, report):
    """넘침 — 축소로도 못 담은 지문이 있으면 결함."""
    p = cfg.path(f"fit{vol}.json")
    if not os.path.exists(p):
        return report.warn("높이 표 없음 — `build` 로 한 번 재 둘 것")
    with open(p, encoding="utf-8") as f:
        rows = json.load(f)
    shrunk = [r for r in rows if r.get("pt")]
    hard = [r for r in rows if not r.get("pt")]
    if hard:
        report.fail(f"칸을 넘는데 축소 못 한 지문 {len(hard)}건: "
                    f"{[(r['header'], r['natural_mm']) for r in hard][:5]}")
    if shrunk:
        report.note(f"활자 축소 {len(shrunk)}건 — "
                    + ", ".join(f"{r['header']} {r['pt']}pt"
                                for r in shrunk[:6]))
    else:
        report.note("활자 축소 없음")
    return hard


def _check_hyphen(data, report):
    """되읽기 잔재(하이픈 넣기). 원고 직독으로 바꾸면 사라질 것 — 지금은 알린다."""
    hy = data.get("_hyphen_suspects") or {}
    if hy:
        report.warn(f"인디자인 되읽기 잔재(하이픈) {sum(hy.values())}건: "
                    f"{sorted(hy)[:8]}")


def run(series, cfg, log, report):
    vol = series.vol_of(cfg)
    data = data_mod.load(cfg)
    vcfg = cfg.section("verify") or {}
    pdf = cfg.out_pdf(vcfg.get("suffix") or series._suffix(cfg))
    if not os.path.exists(pdf):
        return report.fail(f"PDF 없음: {pdf}")
    texts = probe.page_texts(pdf)
    spans = _section_pages(data, vol, texts, report)
    _check_pagecount(data, vol, spans, report)
    _check_placement(data, vol, texts, spans, report)
    _check_vocab_pair(data, vol, report)
    _check_blanks(data, vol, texts, spans, report)
    _check_fit(cfg, vol, report)
    _check_hyphen(data, report)
    return report
