import re
# -*- coding: utf-8 -*-
"""포켓북 테마 CSS — 값은 전부 **완성본 실측**이고, 전부 손잡이다.

수치를 코드에 박지 않는다. `config.json` 의 `palette`·`metrics` 로 덮어쓸 수 있게
기본값만 여기 둔다(자립화 계획 S3). 기본값 = 지금 납품본과 같은 지면.

실측 출처: 상일2 26-2 포켓북 내지 PDF(148×210) 2·3면.
"""

# ── 색 (실측) ─────────────────────────────────────────────
PALETTE = {
    "band":      "#EAE6DC",   # 위·아래 띠
    "navy":      "#54669E",   # 지문번호 배지 · 쪽번호
    "chip":      "#869CD0",   # PICTURE / TRANSLATION 칩
    "ink":       "#231F20",   # 본문
    "blue":      "#224E8E",   # 강조 파랑
    "red":       "#D2232A",   # 강조 빨강
    "anno":      "#A7A9AC",   # 구문분석 주석
    "trans":     "#58595B",   # 번역
    "topic_bg":  "#FAFAF8",   # 주제/요약 띠
    "flow_bg":   "#EAECD8",   # 플로우노트 모눈 바탕
    "flow_line": "#BFC3C9",   # 모눈 선
    "flow_arrow": "#F39857",  # 플로우 화살표 줄
    "syn_word":  "#231F20",
    "syn_syn":   "#224E8E",   # `=` 유의어
    "syn_ant":   "#E14E6B",   # `↔` 반의어
    "card1":     "#F8F6E2",   # 동반의어 1열
    "card2":     "#ECE1EB",   # 2열
    "card3":     "#D6E3EF",   # 3열
}

# 형광펜 — 인디자인 문자 스타일 이름 그대로 쓴다(`형광펜_노랑` …)
HIGHLIGHT = {
    "yellow": "#FDF598", "mint": "#E8F5F0", "pink": "#FBEEF2",
    "sky": "#E9F1FA", "violet": "#F0EDF8", "orange": "#FDF0E4",
}

# ── 치수 mm/pt (실측) ─────────────────────────────────────
METRICS = {
    "page_w": 148.0, "page_h": 210.0, "bleed": 3.0,
    "band_h": 5.5,                 # 위·아래 띠 (도련까지 8.5)
    "margin_l": 15.0, "margin_r": 18.0,
    "badge": [15.0, 15.0, 18.0, 5.5],       # x y w h
    "passage": [15.0, 24.0, 115.0, 118.0],  # x y w h
    "passage_size": 9.0, "passage_lead": 24.0,
    "passage_track": -0.022,       # em — 이 값에서 원본과 행바꿈이 일치한다
    "first_baseline_fix": -7.7,    # pt, 인디자인 '어센트' 기준 보정
    "anno_size": 7.0, "anno_up": 4.3, "anno_dn": 6.8,
    "hl_weight": 9.0, "hl_offset": 1.2,     # pt — 인디자인 밑줄 9pt / offset -3
    "rule_y": 148.0,
    "chip": [16.0, 2.71], "chip_pic_x": 56.5, "chip_trn_x": 114.0,
    "chip_y": 145.2,
    "illust": [12.88, 149.1, 59.62, 45.9],
    "trans": [74.0, 150.0, 56.0], "trans_size": 5.9, "trans_lead": 3.2,
    "folio_y": 196.5, "folio_size": 6.0,
    # 오른쪽 면
    "flow": [18.0, 18.31, 115.0, 41.0], "flow_size": 7.0, "flow_lead": 2.85,
    "flow_grid": 1.44, "flow_chip": [104.0, 12.86, 29.0, 5.45],
    "topic": [18.0, 59.31, 115.0, 23.09], "topic_size": 8.0,
    "topic_lead": 3.5, "topic_text_x": 29.8,
    "syn_panel": [18.09, 88.11, 114.82, 106.89],
    "syn_title": [20.7, 85.1, 22.6, 5.17],
    "card": [21.2, 90.83, 34.6, 32.0],
    "card_gap_x": 37.25, "card_gap_y": 34.72,
    "card_size": 7.0, "card_lead": 4.2, "card_pad": 2.0,
    # 암기테스트
    "memtest": [18.0, 20.4, 112.0, 174.6], "memtest_size": 9.0,
    "memtest_lead": 20.0,
}


def _mm(v):
    return "%gmm" % v


def build_css(palette=None, metrics=None, highlight=None):
    """CSS 문자열. 치환은 `__이름__` 토큰 하나로만 한다.

    ⚠ `%%` 포맷을 쓰면 CSS 의 `100%`·`50%` 를 전부 escape 해야 해서 조용히
      깨진다(한 번 그렇게 만들었다가 되돌렸다). 토큰 치환이 안전하다.
    """
    P = dict(PALETTE); P.update(palette or {})
    M = dict(METRICS); M.update(metrics or {})
    H = dict(HIGHLIGHT); H.update(highlight or {})

    bl = M["bleed"]
    tok = {}
    for k, v in P.items():
        tok[k] = v
    tok.update({
        "media_w": _mm(M["page_w"] + 2 * bl),
        "media_h": _mm(M["page_h"] + 2 * bl),
        "page_w": _mm(M["page_w"]), "page_h": _mm(M["page_h"]),
        "bleed": _mm(bl), "band_bleed": _mm(M["band_h"] + bl),
        "lead": "%g" % M["passage_lead"],
        "up_dy": "%g" % M["anno_up"], "dn_dy": "%g" % M["anno_dn"],
        "pass_size": "%g" % M["passage_size"],
        "track": "%g" % M["passage_track"],
        "hlw": "%g" % M["hl_weight"], "hlo": "%g" % M["hl_offset"],
        "anno_size": "%g" % M["anno_size"],
        "trans_size": "%g" % M["trans_size"],
        "trans_lead": "%g" % M["trans_lead"],
        "folio": "%g" % M["folio_size"],
        "grid": "%g" % M["flow_grid"],
        "flow_size": "%g" % M["flow_size"], "flow_lead": "%g" % M["flow_lead"],
        "topic_size": "%g" % M["topic_size"],
        "topic_lead": "%g" % M["topic_lead"],
        "card_size": "%g" % M["card_size"], "card_lead": "%g" % M["card_lead"],
        "cardpad": "%g" % M["card_pad"],
        "mt_size": "%g" % M["memtest_size"], "mt_lead": "%g" % M["memtest_lead"],
        "blank": "8",
    })
    css = CSS_TMPL
    for k, v in tok.items():
        css = css.replace("__%s__" % k, str(v))
    hl = "\n".join(".hl-%s{--hl:%s}" % (k, v) for k, v in sorted(H.items()))
    css = css.replace("__HIGHLIGHTS__", hl)
    left = re.findall(r"__[a-z0-9_]+__", css)
    if left:
        raise ValueError("치환 안 된 토큰: %s" % sorted(set(left)))
    return css


CSS_TMPL = """
@font-face{font-family:PBBody;src:url("fonts/NotoSansCJKkr-Regular.otf");font-weight:400}
@font-face{font-family:PBBody;src:url("fonts/NotoSansCJKkr-Medium.otf");font-weight:500}
@font-face{font-family:PBBody;src:url("fonts/NotoSansCJKkr-Bold.otf");font-weight:700}
@font-face{font-family:PBHand;src:url("fonts/HakgyoansimUndongjangOTFL.otf")}
@font-face{font-family:PBElice;src:url("fonts/EliceDXNeolliOTF-Bold.otf");font-weight:700}
@font-face{font-family:PBElice;src:url("fonts/EliceDXNeolliOTF-Medium.otf");font-weight:500}
@font-face{font-family:PBDodam;src:url("fonts/KCCDodamdodam_OTF.otf")}
@font-face{font-family:PBJalnan;src:url("fonts/JalnanOTF.otf")}

:root{
  --band:__band__; --navy:__navy__; --chip:__chip__; --ink:__ink__;
  --blue:__blue__; --red:__red__; --anno:__anno__; --trans:__trans__;
  --topic-bg:__topic_bg__; --flow-bg:__flow_bg__; --flow-line:__flow_line__;
  --flow-arrow:__flow_arrow__;
  --syn-word:__syn_word__; --syn-syn:__syn_syn__; --syn-ant:__syn_ant__;
  --card1:__card1__; --card2:__card2__; --card3:__card3__;
  --lead:__lead__pt; --up-dy:__up_dy__pt; --dn-dy:__dn_dy__pt;
}
__HIGHLIGHTS__

@page{size:__media_w__ __media_h__;margin:0}
html,body{margin:0;padding:0;background:#fff}
.pg{position:relative;width:__media_w__;height:__media_h__;overflow:hidden;
    font-family:PBBody,sans-serif;color:var(--ink);break-after:page}
.pg:last-child{break-after:auto}
.trim{position:absolute;left:__bleed__;top:__bleed__;
      width:__page_w__;height:__page_h__}
/* 띠는 재단선 밖 3mm 까지 — 판면 기준으로 두면 가장자리에 흰 줄이 생긴다 */
.pg::before,.pg::after{content:"";position:absolute;left:0;width:__media_w__;
    background:var(--band)}
.pg::before{top:0;height:__band_bleed__}
.pg::after{bottom:0;height:__band_bleed__}

/* ── 왼쪽 면 ─────────────────────────────────── */
.badge{position:absolute;background:var(--navy);color:#fff;font-family:PBDodam;
  font-size:8pt;display:flex;align-items:center;justify-content:center;
  letter-spacing:.02em;padding:0 1mm;white-space:nowrap}
.passage{position:absolute;font-size:__pass_size__pt;line-height:var(--lead);
  text-align:justify;letter-spacing:__track__em;hyphens:none}
.passage .w{position:relative;display:inline-block;line-height:var(--lead)}
.w.blue,.blue{color:var(--blue)}
.w.red,.red{color:var(--red)}
.passage mark,.passage .hl{color:inherit;
  background:linear-gradient(var(--hl),var(--hl));
  background-size:100% __hlw__pt;background-position:0 calc(50% + __hlo__pt);
  background-repeat:no-repeat}
.passage i{position:absolute;left:50%;transform:translateX(-50%);
  font-family:PBHand;font-size:__anno_size__pt;line-height:1;color:var(--anno);
  white-space:nowrap;font-style:normal}
.passage i.up{bottom:calc(50% + var(--up-dy))}
.passage i.dn{top:calc(50% + var(--dn-dy))}
.wave{text-decoration:underline wavy currentColor;text-underline-offset:2pt}

.rule{position:absolute;height:0;border-top:.5pt solid var(--chip)}
.chip{position:absolute;background:var(--chip);color:var(--band);
  font-family:PBHand;font-size:6pt;display:flex;align-items:center;
  justify-content:center}
.illust{position:absolute;margin:0}
.illust img{width:100%;display:block}
.translation{position:absolute;font-size:__trans_size__pt;
  line-height:__trans_lead__mm;color:var(--trans);text-align:justify}
.translation p{margin:0}
.folio{position:absolute;font-family:PBElice;font-size:__folio__pt;
  font-weight:700}
.folio b{color:var(--navy)}
.folio.r{text-align:right}

/* ── 오른쪽 면 ───────────────────────────────── */
.flowchip{position:absolute;background:var(--band);display:flex;
  align-items:center;justify-content:center;gap:1mm;
  font-family:PBHand;font-size:8pt;color:var(--navy)}
.flow{position:absolute;overflow:hidden;
  background:
    repeating-linear-gradient(to right,var(--flow-line) 0 .1mm,transparent .1mm __grid__mm),
    repeating-linear-gradient(to bottom,var(--flow-line) 0 .1mm,transparent .1mm __grid__mm),
    var(--flow-bg);
  font-family:PBDodam;font-size:__flow_size__pt;line-height:__flow_lead__mm;
  padding:2.5mm 3mm;box-sizing:border-box;columns:2;column-gap:3mm}
.flow p{margin:0;break-inside:avoid}
.flow p.arrow{color:var(--flow-arrow)}

.topicband{position:absolute;background:var(--topic-bg);box-sizing:border-box;
  padding:1.6mm 2mm}
.tbadge{position:absolute;font-family:PBDodam;font-size:9pt;color:#fff;
  background:var(--navy);border-radius:.8mm;padding:0 1mm;line-height:1.4}
.topictext{position:absolute;font-size:__topic_size__pt;
  line-height:__topic_lead__mm}
.topictext p{margin:0}

.synpanel{position:absolute;border:1pt solid var(--band);border-radius:2mm;
  box-sizing:border-box}
.syntitle{position:absolute;background:#fff;font-family:PBJalnan;font-size:5pt;
  color:var(--navy);display:flex;align-items:center;justify-content:center;
  gap:.6mm}
.card{position:absolute;box-sizing:border-box;padding:__cardpad__mm;
  font-size:__card_size__pt;line-height:__card_lead__mm;overflow:hidden}
.card .w1{color:var(--syn-word)}
.card .s1{color:var(--syn-syn)}
.card .a1{color:var(--syn-ant)}
.card p{margin:0}
/* 접힌 모서리 — 원본의 종이 접힘 장식 */
.card::after{content:"";position:absolute;right:0;bottom:0;
  border:1.6mm solid transparent;border-right-color:rgba(0,0,0,.06);
  border-bottom-color:rgba(0,0,0,.06)}

/* ── 암기 TEST ───────────────────────────────── */
.mtchip{position:absolute;background:var(--band);font-family:PBHand;
  font-size:7pt;color:var(--navy);display:flex;align-items:center;
  padding:0 2mm}
.memtest{position:absolute;font-size:__mt_size__pt;line-height:__mt_lead__pt;
  text-align:justify;letter-spacing:__track__em}
.memtest .n{font-size:5.5pt;vertical-align:super;color:var(--anno)}
.memtest .ans{color:#E8963C}
.memtest .blank{display:inline-block;min-width:__blank__mm}
.mtbox{position:absolute;border:.4pt solid #E4E0D6;background:#FCFBF7;
  border-radius:1mm}
"""
