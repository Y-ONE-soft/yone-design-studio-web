"""시안 매트릭스 — 같은 견본을 **여러 값으로 한꺼번에** 뽑아 나란히 붙인다.

## 왜

지금까지 시안은 **순차**였다. 헤더 시안 A 를 만들어 PDF 로 보고, 지적을 받고,
B 를 만들어 다시 보고… 상일보카는 헤더 시안 A/B/C + 마름모 시안, 광교관 특강은
10차까지 갔다. 왕복 하나하나가 대화 한 판이다.

값 하나만 다른 시안이라면 **동시에 뽑아 한 장에 놓고 고르면** 된다. 손잡이가
선언돼 있으니 "어느 값을 어떻게 바꿀지"를 기계가 안다.

    bin/viv "<책폴더>" variants --knob=palette.accent \\
            --values="#d06397,#c08618,#6f7e2c"

→ `<책폴더>/_시안_accent.pdf` (견본 앞면들을 값마다 한 줄씩)

## ⚠ config.json 을 건드리지 않는다

값은 **메모리 안에서만** 갈아 끼우고 조판한다. 시안을 뽑다가 책의 설정이
바뀌면 안 된다(그 사고가 나면 되돌릴 방법이 백업뿐이다).
"""
import os

from core.render_vivlio import knobs as kn


def _sample_pdf(cfg, series, log):
    res = series.build(cfg, log, sample=True)
    return res["pdf"] if isinstance(res, dict) else None


def run(cfg, series, key, values, log=print, pages=4, out=None):
    """`key` 를 `values` 로 바꿔 가며 견본을 뽑고 한 장으로 붙인다."""
    import fitz

    known = {k.key: k for k in kn.of(cfg, series)}
    if key not in known:
        raise SystemExit(f"모르는 손잡이: {key}\n  → `knobs` 로 목록을 볼 것")
    knob = known[key]
    had = kn.has(cfg.data, key)
    before = kn.get(cfg.data, key)

    shots = []
    try:
        for v in values:
            val = v
            if knob.kind in ("mm", "pt", "number"):
                val = float(v) if "." in str(v) else int(v)
            kn.put(cfg.data, key, val)
            log(f"[시안] {key} = {val}")
            pdf = _sample_pdf(cfg, series, log)
            if not pdf or not os.path.exists(pdf):
                log(f"  [건너뜀] 견본이 안 나왔다 ({val})")
                continue
            d = fitz.open(pdf)
            # 앞면 몇 장만 — 글자가 있는 면부터(1면은 간지·표식 면일 때가 많다)
            picked = []
            for i in range(d.page_count):
                if len(d[i].get_text("text").strip()) > 40:
                    picked.append(d[i].get_pixmap(dpi=72))
                if len(picked) >= pages:
                    break
            d.close()
            if picked:
                shots.append((str(val), picked))
    finally:
        # **반드시 되돌린다** — 메모리 안이라도 뒤에 이어 도는 것이 있을 수 있다
        if had:
            kn.put(cfg.data, key, before)
        else:
            kn.unset(cfg.data, key)

    if not shots:
        raise SystemExit("시안을 하나도 못 만들었다")

    out = out or cfg.path("_시안_%s.pdf" % key.rsplit(".", 1)[-1])
    pad, lab = 8, 22
    w = max(sum(p.width for p in ps) + pad * (len(ps) + 1) for _, ps in shots)
    h = sum(max(p.height for p in ps) + pad + lab for _, ps in shots) + pad
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.draw_rect(fitz.Rect(0, 0, w, h), color=None, fill=(1, 1, 1))
    y = pad
    for name, ps in shots:
        page.insert_text(fitz.Point(pad, y + 14), f"{key} = {name}",
                         fontsize=11, color=(0.1, 0.1, 0.1))
        y += lab
        x = pad
        for p in ps:
            page.insert_image(fitz.Rect(x, y, x + p.width, y + p.height),
                              pixmap=p)
            page.draw_rect(fitz.Rect(x, y, x + p.width, y + p.height),
                           color=(0.8, 0.8, 0.8), width=0.5)
            x += p.width + pad
        y += max(p.height for p in ps) + pad
    doc.save(out)
    doc.close()
    log(f"OK  시안 {len(shots)}개 × {pages}면 → {out}")
    return {"pdf": out, "variants": len(shots)}
