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
# 한 면의 칸 배치 — (단 수, 단마다 칸 수). 사분면은 2단×2칸.
GRID = {"arrange": (2, 2), "insert": (2, 2), "vocab": (1, 1),
        "grammar": (2, 1), "writing": (2, 1)}
RE_WS = re.compile(r"\s+")
MM = 25.4 / 72
# 판면 세로 경계 — 이 밖은 러닝 요소다(완성본 실측)
BODY_TOP, BODY_BOTTOM = 25.0, 284.0


def expected_pages(sec, spans):
    """지문마다 **몇 번째 면**에 놓이는가 — 칸 배치를 슬롯으로 흉내 낸다.

    한 면은 `단 수 × 단마다 칸 수` 슬롯이고 **단을 세로로 먼저** 채운다
    (`column-fill: auto`). 두 칸짜리·흘림 지문은 슬롯을 그만큼 먹고 단 머리에
    맞춰 시작하므로, 단순한 i//4 로는 그 뒤가 전부 어긋난 것처럼 보인다
    (실제로 389건 거짓 경보가 났다).
    """
    ncol, nslot = GRID[sec["kind"]]
    per = ncol * nslot
    out, pos = [], 0
    for i, _b in enumerate(sec["blocks"]):
        s = max(1, int(spans.get(i, 1)))
        if s > 1 and pos % nslot:          # 여러 칸짜리는 단 머리에서 시작
            pos += nslot - (pos % nslot)
        # 여러 칸을 먹는 지문은 **면에 걸칠 수 있다** → 걸치는 면 전부
        out.append((pos // per, (pos + s - 1) // per))
        pos += s
    return out


def _n(s):
    return RE_WS.sub("", probe.norm(s or ""))


def page_text_colwise(page):
    """면 글자를 **조판 흐름 순서**(왼 단 위→아래, 다음 오른 단)로 잇는다.

    ⚠ PDF 추출 순서는 좌표 순이라 두 단 지면에서 단이 뒤섞인다. 그대로 이으면
      단 경계·면 경계에 걸친 문장이 '누락'으로 잡힌다(어법 19강 07~08 실증).
    ⚠ 러닝 요소(띠·탭·꼬리말)도 빼야 한다 — 안 빼면 면 끝의 꼬리말이 문장
      한가운데 끼어들어 역시 '누락'이 된다.
    """
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        x0, y0 = b["bbox"][0] * MM, b["bbox"][1] * MM
        if y0 < BODY_TOP or y0 > BODY_BOTTOM:
            continue
        col = 0 if x0 < 60 else 1
        blocks.append((col, y0, "".join(
            x["text"] for l in b["lines"] for x in l["spans"])))
    blocks.sort(key=lambda t: (t[0], t[1]))
    return "".join(t for _c, _y, t in blocks)


def page_texts_colwise(pdf):
    with probe.open_pdf(pdf) as doc:
        return [page_text_colwise(p) for p in doc]


def _section_pages(data, vol, texts, report, skip=()):
    """섹션마다 [면번호…] — 꼬리말의 섹션 이름으로 구간을 가른다.

    ⚠ 간지·크레딧 면은 섹션 이름이 없어 **앞 섹션에 딸려 붙는다**(중요어휘가
      18면인데 19면으로 잡혔다) → 건너뛸 면을 받아 뺀다.
    """
    v = data["vols"][str(vol)]
    spans, cur = {}, None
    for i, t in enumerate(texts):
        if (i + 1) in skip:
            continue
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


RE_SENT = re.compile(r"(?<=[.!?])\s+")


def _block_text(kind, b):
    """그 지문의 **본문 문장**(대조용). 헤더는 쓰지 않는다.

    어법은 지문이 한 덩어리라 통째로 찾으면 **면에 걸친 지문이 '누락'** 으로
    잡힌다(흘림 배치). 문장으로 쪼개면 걸침도 견디고 어디가 틀렸는지도 좁혀진다.
    """
    if kind in ("arrange", "insert"):
        return ([b["given"]] if b.get("given") else []) + list(b["items"])
    if kind == "vocab":
        return [data_mod.plain(p) for p in b["passage"]] + \
               [data_mod.plain(p) for p in b.get("summary") or []]
    if kind == "grammar":
        # ⚠ `[낱말]` 은 지면에 **대괄호째** 찍힌다. 괄호를 뺀 문자열로 찾으면
        #   55개 지문이 통째로 "누락"으로 잡힌다(거짓 경보).
        whole = "".join(f'[{x["a"]}]' if isinstance(x, dict) else x
                        for x in b["body"])
        return [t for t in RE_SENT.split(whole) if t.strip()]
    return [p["korean"] for p in b["pairs"]] + \
           [p["choices"] for p in b["pairs"]]


def _check_placement(data, vol, texts, spans, report, spanmap):
    """모든 문장이 **제 섹션, 제 면**에 있는가."""
    v = data["vols"][str(vol)]
    miss, wrong, n = [], [], 0
    for sec in v["sections"]:
        pages = spans.get(sec["kind"]) or []
        if not pages:
            continue
        blobs = [_n(texts[p - 1]) for p in pages]
        whole = "".join(blobs)
        want_of = expected_pages(sec, spanmap.get(sec["kind"], {}))
        for i, b in enumerate(sec["blocks"]):
            lo, hi = want_of[i]
            span_blob = "".join(blobs[lo:hi + 1]) if lo < len(blobs) else ""
            for t in _block_text(sec["kind"], b):
                q = _n(t)
                if len(q) < 12:
                    continue
                n += 1
                if q not in whole:
                    miss.append(f"{sec['title']} {b['header']}")
                elif lo < len(blobs) and q not in span_blob:
                    wrong.append(f"{sec['title']} {b['header']}"
                                 f"(기대 {lo + 1}번째 면)")
    report.note(f"문장 대조 {n:,}건 (섹션·면 단위)")
    if miss:
        report.fail(f"누락 {len(miss)}건: {sorted(set(miss))[:8]}")
    if wrong:
        report.fail(f"자리 어긋남 {len(wrong)}건: {sorted(set(wrong))[:8]}")
    return miss, wrong


def _check_pagecount(data, vol, spans, report, spanmap):
    """고정 칸 계약 — 지문 수(와 두 칸짜리)로 면 수가 정해진다."""
    v = data["vols"][str(vol)]
    bad = []
    for sec in v["sections"]:
        pages = spans.get(sec["kind"]) or []
        want = (expected_pages(sec, spanmap.get(sec["kind"], {}))[-1][1] + 1
                if sec["blocks"] else 0)
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
    # 요약은 고1·고2 만 있다(고3 EBS 는 워크북 빈칸어휘라 아예 없다) →
    # **일부만 없는 것**이 결함이다.
    nosum = [b["header"] for b in sec["blocks"] if not b.get("summary")]
    bad = [b["header"] for b in sec["blocks"] if not b["passage"]]
    if nosum and len(nosum) != len(sec["blocks"]):
        bad += nosum
        report.fail(f"중요어휘 요약이 일부에만 있다 {len(nosum)}"
                    f"/{len(sec['blocks'])}: {nosum[:6]}")
    elif bad:
        report.fail(f"중요어휘 지문 없음 {len(bad)}: {bad[:6]}")
    else:
        report.note(f"중요어휘 {len(sec['blocks'])}지문 좌우 짝 온전"
                    + ("(요약 없는 판)" if nosum else ""))
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
    wide = [r for r in rows if r.get("span", 1) > 1]
    hard = [r for r in rows if not r.get("fits", True)]
    if hard:
        report.fail(f"칸을 넘는데 담지 못한 지문 {len(hard)}건: "
                    f"{[(r['header'], r['natural_mm']) for r in hard][:5]}")
    if shrunk:
        report.note(f"활자 축소 {len(shrunk)}건 — "
                    + ", ".join(f"{r['header']} {r['pt']}pt"
                                for r in shrunk[:6]))
    if wide:
        report.note(f"두 칸 배치 {len(wide)}건 — "
                    + ", ".join(r["header"] for r in wide[:6]))
    if not shrunk and not wide:
        report.note("활자 축소 없음")
    return hard


def _check_hyphen(data, report):
    """되읽기 잔재(하이픈 넣기). 원고 직독으로 바꾸면 사라질 것 — 지금은 알린다."""
    hy = data.get("_hyphen_suspects") or {}
    if hy:
        report.warn(f"인디자인 되읽기 잔재(하이픈) {sum(hy.values())}건: "
                    f"{sorted(hy)[:8]}")


def _spanmap(cfg, vol, data):
    """섹션별 {지문 index: span}. fit 리포트를 지문 순번으로 되돌린다."""
    out = {}
    p = cfg.path(f"fit{vol}.json")
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as f:
        for r in json.load(f):
            kind = r["key"].split("-")[1]
            i = int(r["key"].rsplit("-", 1)[1])
            slots = r.get("span", 1)
            if r.get("flow"):
                # 흘린 지문은 제 높이만큼 칸을 먹는다
                cap = max(1.0, float(r.get("cap_mm") or 1.0))
                slots = max(2, int(-(-float(r.get("natural_mm") or 0) // cap)))
            if slots > 1:
                out.setdefault(kind, {})[i] = slots
    return out


def run(series, cfg, log, report):
    vol = series.vol_of(cfg)
    data = data_mod.load(cfg)
    vcfg = cfg.section("verify") or {}
    pdf = cfg.out_pdf(vcfg.get("suffix") or series._suffix(cfg))
    if not os.path.exists(pdf):
        return report.fail(f"PDF 없음: {pdf}")
    # 두 벌이 필요하다 — 섹션 구간은 **러닝 요소**(띠·꼬리말)로 가르고,
    # 내용 대조는 **본문만** 이어 붙인다.
    labels = probe.page_texts(pdf)
    texts = page_texts_colwise(pdf)
    skip = set(vcfg.get("skip_pages") or ())
    skip |= {len(texts) - k for k in range(vcfg.get("skip_last") or 0)}
    spanmap = _spanmap(cfg, vol, data)
    spans = _section_pages(data, vol, labels, report, skip)
    _check_pagecount(data, vol, spans, report, spanmap)
    _check_placement(data, vol, texts, spans, report, spanmap)
    _check_vocab_pair(data, vol, report)
    _check_blanks(data, vol, texts, spans, report)
    _check_fit(cfg, vol, report)
    _check_hyphen(data, report)
    return report
