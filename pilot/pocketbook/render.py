# -*- coding: utf-8 -*-
"""하베스트한 지문 JSON → HTML → Vivliostyle → PDF (왼쪽 면 재현 파일럿).

목적은 **구문분석 주석이 붙은 지문 면을 코드로 재현할 수 있는가** 하나다.
주석은 낱말에 앵커된 절대배치 span 으로 그린다 — 줄바꿈은 브라우저가 하고,
주석은 낱말을 따라간다(원고가 길어져도 사람이 손볼 곳이 없다).
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

FONTS = [
    "NotoSansCJKkr-Regular.otf", "NotoSansCJKkr-Medium.otf",
    "NotoSansCJKkr-Bold.otf", "EliceDXNeolliOTF-Bold.otf",
    "EliceDXNeolliOTF-Medium.otf", "HakgyoansimUndongjangOTFL.otf",
    "KCCDodamdodam_OTF.otf", "JalnanOTF.otf",
]

ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def esc(s):
    return "".join(ESC.get(c, c) for c in s)


def word_html(w, skip_hl=False):
    cls = ["w"]
    if w.get("color") in ("blue", "red"):
        cls.append(w["color"])
    style = ""
    if w.get("hl") and not skip_hl:
        style += "--hl:%s;" % w["hl"]
        cls.append("hl")
    if w.get("ul"):
        style += "--ul:%s;" % w["ul"]
        cls.append("ul")
    inner = esc(w["t"])
    for slot in ("up", "dn"):
        for a in w.get(slot, []):
            c = ' style="color:%s"' % a["color"] if a.get("color") else ""
            inner += '<i class="%s"%s>%s</i>' % (slot, c, esc(a["t"]))
    return '<span class="%s"%s>%s</span>' % (
        " ".join(cls), ' style="%s"' % style if style else "", inner)


def build_html(data, meta):
    # 형광펜은 **연속 구간**이다. 낱말마다 칠하면 어절 사이 공백이 비어 원본의
    # 이어진 띠가 끊긴 줄무늬가 된다(1차 시안에서 그렇게 나왔다).
    flat = [w for ln in data["lines"] for w in ln["words"]]
    parts, run, run_hl = [], [], None
    def flush():
        if not run:
            return
        inner = " ".join(run)
        parts.append('<mark style="--hl:%s">%s</mark>' % (run_hl, inner)
                     if run_hl else inner)
        run[:] = []
    for w in flat:
        hl = w.get("hl")
        if hl != run_hl:
            flush()
            run_hl = hl
        run.append(word_html(w, skip_hl=True))
    flush()
    body = " ".join(parts)
    trans = "".join("<p>%s</p>" % esc(t) for t in meta.get("translation", []))
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>포켓북 파일럿</title>
<link rel="stylesheet" href="pocket.css">
</head><body>
<section class="pg left"><div class="trim">
  <div class="badge">%s</div>
  <div class="passage">%s</div>
  <div class="rule"></div>
  <div class="chip pic">PICTURE</div>
  <div class="chip trn">TRANSLATION</div>
  <figure class="illust"><img src="%s" alt=""><figcaption>%s</figcaption></figure>
  <div class="translation">%s</div>
  <div class="folio"><b>%s</b> POCKET BOOK</div>
</div></section>
</body></html>
""" % (esc(meta["passage_no"]), body, meta["illust"], esc(meta["caption"]),
       trans, esc(meta["folio"]))


CSS = r"""
@font-face{font-family:PBBody;src:url("fonts/NotoSansCJKkr-Regular.otf");font-weight:400}
@font-face{font-family:PBBody;src:url("fonts/NotoSansCJKkr-Medium.otf");font-weight:500}
@font-face{font-family:PBHand;src:url("fonts/HakgyoansimUndongjangOTFL.otf")}
@font-face{font-family:PBElice;src:url("fonts/EliceDXNeolliOTF-Bold.otf");font-weight:700}
@font-face{font-family:PBElice;src:url("fonts/EliceDXNeolliOTF-Medium.otf");font-weight:500}
@font-face{font-family:PBDodam;src:url("fonts/KCCDodamdodam_OTF.otf")}

:root{
  --band:#EAE6DC;      /* 위·아래 띠 */
  --navy:#54669E;      /* 지문번호 배지 */
  --chip:#869CD0;      /* PICTURE / TRANSLATION 칩 */
  --blue:#224E8E; --red:#D2232A; --ink:#231F20; --anno:#A7A9AC;
  --lead:24pt;         /* 본문 행간 (실측) */
  --up-dy:4.3pt;       /* 주석 위치 — 원본 baseline −9.4pt 가 되도록 보정 */
  --dn-dy:6.8pt;       /* 원본 baseline +8.6pt */
}
/* 도련 사방 3mm — 최종 출력물이 고품질 인쇄다.
   판면 좌표는 전부 재단선(trim) 기준으로 쓰고, 3mm 밀어 놓은 .trim 안에 담는다.
   그래야 실측 상수를 도련 유무와 무관하게 그대로 쓸 수 있다.
   TrimBox 는 조판 뒤 bleed.stamp_trimbox 가 박는다(다른 계열과 동일). */
@page{size:154mm 216mm;margin:0}
html,body{margin:0;padding:0}
.pg{position:relative;width:154mm;height:216mm;overflow:hidden;
    font-family:PBBody,sans-serif;color:var(--ink);break-after:page}
.trim{position:absolute;left:3mm;top:3mm;width:148mm;height:210mm}
/* 띠는 재단선 밖 3mm 까지 나가야 한다 — 판면 기준으로 두면 흰 줄이 생긴다 */
.pg::before,.pg::after{content:"";position:absolute;left:0;width:154mm;
    background:var(--band)}
.pg::before{top:0;height:8.5mm}
.pg::after{top:207.5mm;height:8.5mm}

.badge{position:absolute;left:15mm;top:15mm;width:18mm;height:5.5mm;
  background:var(--navy);color:#fff;font-family:PBDodam;font-size:8pt;
  display:flex;align-items:center;justify-content:center;letter-spacing:.02em}

.passage{position:absolute;left:15mm;top:calc(24mm - 7.7pt);width:115mm;height:118mm;
  font-size:9pt;line-height:var(--lead);text-align:justify;
  text-justify:inter-word;letter-spacing:-0.022em}   /* 실측 보정: 이 값에서 원본과 행바꿈이 일치한다 */
.passage .w{position:relative;display:inline-block;line-height:var(--lead)}
.passage .blue,.passage .w.blue{color:var(--blue)}
.passage .red,.passage .w.red{color:var(--red)}
.passage mark{color:inherit;background:linear-gradient(var(--hl),var(--hl));background-size:100% 9pt;background-position:0 calc(50% + 1.2pt);background-repeat:no-repeat}
.passage .hl{background:linear-gradient(var(--hl),var(--hl));
  background-size:100% 9pt;background-position:0 calc(50% + 1.2pt);
  background-repeat:no-repeat}
.passage .ul{box-shadow:inset 0 -0.4pt 0 0 var(--ul)}
.passage i{position:absolute;left:50%;transform:translateX(-50%);
  font-family:PBHand;font-size:7pt;line-height:1;color:var(--anno);
  white-space:nowrap;font-style:normal;pointer-events:none}
.passage i.up{bottom:calc(50% + var(--up-dy))}
.passage i.dn{top:calc(50% + var(--dn-dy))}

.rule{position:absolute;left:15mm;top:148mm;width:115mm;height:0;
  border-top:.5pt solid var(--chip)}
.chip{position:absolute;top:145.2mm;height:2.71mm;width:16mm;
  background:var(--chip);color:#EAE6DC;font-family:PBHand;font-size:6pt;
  display:flex;align-items:center;justify-content:center}
.chip.pic{left:56.5mm}
.chip.trn{left:114mm}

.illust{position:absolute;left:12.88mm;top:149.1mm;width:59.62mm;margin:0}
.illust img{width:100%;display:block}
.illust figcaption{margin-top:1mm;text-align:center;font-size:5.5pt;
  color:#58595B}

.translation{position:absolute;left:74mm;top:150mm;width:56mm;
  font-size:5.9pt;line-height:3.2mm;color:#58595B;text-align:justify}
.translation p{margin:0}

.folio{position:absolute;left:12.9mm;top:196.5mm;font-family:PBElice;
  font-size:6pt;font-weight:700}
.folio b{color:var(--navy)}
"""


def stage_fonts(build_dir):
    from core.render_vivlio import stage
    stage.stage_fonts(build_dir, FONTS, required=True)


def main(json_path, meta_path, out_pdf):
    build = os.path.join(HERE, "build")
    os.makedirs(build, exist_ok=True)
    data = json.load(open(json_path, encoding="utf-8"))
    meta = json.load(open(meta_path, encoding="utf-8"))
    if meta.get("illust_src"):
        shutil.copy2(meta["illust_src"], os.path.join(build, meta["illust"]))
    stage_fonts(build)
    open(os.path.join(build, "pocket.css"), "w", encoding="utf-8").write(CSS)
    html = os.path.join(build, "index.html")
    open(html, "w", encoding="utf-8").write(build_html(data, meta))
    from core.render_vivlio import cli
    dt = cli.run_build(html, out_pdf, log=print)
    from core.render_vivlio import bleed
    bleed.finish(out_pdf, {"trim": {"bleed": 3.0}}, log=print)
    print("→", out_pdf, "%.1fs" % dt)


if __name__ == "__main__":
    main(*sys.argv[1:4])
