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
    "flow_arrow": "#F39857",  # 플로우 기호 (CMYK 2/48/73/0)
    # 플로우노트는 **기호마다 색이 다르다**(원본 문자 스타일 4종). 줄 전체가
    # 아니라 기호 글자에만 칠한다 — 줄을 통째로 칠하면 원본과 완전히 달라진다.
    "flow_sym2": "#5B412E",   # 기호2 (41/59/73/52)
    "flow_brk":  "#0068B4",   # [대괄호] (100/59/0/0)
    "flow_par":  "#23B096",   # (소괄호) (75/5/52/0)
    "topic_chip": "#54669F",  # 주제 딱지 (66/52/0/19)
    "sum_chip":  "#E5A97E",   # 요약문 딱지 (0/32/48/9) — 주제와 **다른 색**이다
    "wave":      "#EE4C9B",   # 물결 밑줄 (0/85/0/0)
    "mt_q_bg":   "#EAE6DC",   # 암기 문제면 바탕 (2/3/8/6)
    "mt_a_bg":   "#D6E3EF",   # 암기 정답면 바탕 (11/3/0/4)
    "mt_line":   "#869CD0",   # 암기 정답면 테두리·칩 (48/33/0/0)
    "mt_ans":    "#FDBB63",   # 암기 정답 낱말 (0/30/70/0)
    "mt_no":     "#808285",   # 암기 번호 (K60)
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
    # 형광펜 = 굵은 밑줄. 인디자인 UnderlineWeight 9 / Offset −3 이고, 실측하면
    # **획 중심이 기준선 3pt 위**다. CSS 는 밑줄의 **윗변**을 offset 으로 잡으므로
    # offset = −(중심 + 두께/2) = −7.5pt 가 되어야 글자 위에 얹힌다.
    "hl_weight": 9.0, "hl_center": 2.75,
    "rule_y": 148.0,
    "chip": [16.0, 2.71], "chip_pic_x": 56.5, "chip_trn_x": 114.0,
    "chip_y": 145.2,
    "illust": [12.88, 149.1, 59.62, 45.9],
    "trans": [74.0, 150.0, 56.0], "trans_size": 5.9, "trans_lead": 3.2,
    "folio_y": 196.5, "folio_size": 6.0,
    # 오른쪽 면
    "flow": [18.0, 18.31, 115.0, 41.0], "flow_size": 7.0, "flow_lead": 2.85,
    "flow_grid": 1.44, "flow_chip": [104.0, 12.86, 29.0, 5.45],
    # 모눈 배경은 원본에서 **불투명도 55%** 로 깔려 있다(마스터 실측).
    # 100% 로 깔면 글자보다 모눈이 세 보인다.
    "flow_grid_alpha": 0.55,
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

# ── 지면 배치 변형 — 마스터별 (완성본 실측) ────────────────
#   A = 교과서·EBS(삽화 없음): 지문이 길고 번역이 아래 전폭 띠
#   C = 모의고사(삽화 있음):   지문이 짧고 삽화 옆에 번역
#   E = EBS 변형:              A 와 같되 지문이 더 길다
# ⚠ TRANSLATION 딱지 **아래 선은 어느 마스터에나 있다**(A·C·E·G·H·I 전수 실측:
#   0.5pt, CMYK 48/33/0/0, 단 너비 전체). A·E 에 없다고 둔 것이 결함이었다.
#   자리 관계도 원본이 정한다 — 선 = 딱지 아래 2.9mm, 해석 = 선 아래 3.0mm
#   (실측: 딱지 156.5 / 선 159.3 / 해석 162.3mm).
LAYOUTS = {
    "A": {"passage_h": 127.0, "rule": 155.6,
          "chip_y": 152.7, "chip_trn_x": 114.0, "illust": None,
          "trans": [15.0, 158.6, 115.0]},
    "C": {"passage_h": 118.0, "rule": 148.1,
          "chip_y": 145.2, "chip_trn_x": 114.0, "chip_pic_x": 56.5,
          "illust": [12.88, 149.1, 59.62, 45.9],
          "trans": [74.0, 151.1, 56.0]},
    "E": {"passage_h": 131.0, "rule": 160.9,
          "chip_y": 158.0, "chip_trn_x": 114.0, "illust": None,
          "trans": [15.0, 163.9, 115.0]},
}


def layout_for(passage):
    """지문 → 배치 이름. **삽화 유무가 가른다**(마스터를 그렇게 나눠 놨다)."""
    if passage.get("illust"):
        return "C"
    return passage.get("layout") or "A"


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
        "hlw": "%g" % M["hl_weight"],
        "hlo2": "%g" % (M["hl_center"] + M["hl_weight"] / 2.0),
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
        "flow_grid_alpha": "%g" % M["flow_grid_alpha"],
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
/* 구문분석 주석 = **휴먼범석체**(원본 RubyFont). 암기 TEST 만 강원교육현옥샘.
   지문번호 배지는 **영도체**(마스터페이지:지문 번호). 셋 다 손글씨체라
   비슷해 보이지만 글자 폭이 달라 줄바꿈까지 어긋난다. */
@font-face{font-family:PBRuby;src:url("fonts/PBRuby.otf")}
@font-face{font-family:PBRubyT;src:url("fonts/PBRubyT.otf")}
@font-face{font-family:PBBadge;src:url("fonts/YeongdoOTF.otf")}

:root{
  --band:__band__; --navy:__navy__; --chip:__chip__; --ink:__ink__;
  --blue:__blue__; --red:__red__; --anno:__anno__; --trans:__trans__;
  --topic-bg:__topic_bg__; --flow-bg:__flow_bg__; --flow-line:__flow_line__;
  --flow-arrow:__flow_arrow__; --flow-sym2:__flow_sym2__;
  --flow-brk:__flow_brk__; --flow-par:__flow_par__;
  --topic-chip:__topic_chip__; --sum-chip:__sum_chip__; --wave:__wave__;
  --mt-q-bg:__mt_q_bg__; --mt-a-bg:__mt_a_bg__; --mt-line:__mt_line__;
  --mt-ans:__mt_ans__; --mt-no:__mt_no__;
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
/* 배지는 폭이 고정이다(18mm). padding 을 주면 상자가 그만큼 넓어져 원본과
   어긋난다(실측 20mm) → box-sizing 으로 안쪽에서 먹게 한다. */
.badge{position:absolute;background:var(--navy);color:#fff;font-family:PBBadge;
  font-size:8pt;display:flex;align-items:center;justify-content:center;
  letter-spacing:.02em;padding:0 1mm;white-space:nowrap;box-sizing:border-box}
.passage{position:absolute;font-size:__pass_size__pt;line-height:var(--lead);
  text-align:justify;letter-spacing:__track__em;hyphens:none}
/* ⚠ .w 에 line-height 를 다시 주면 안 된다 — 낱말마다 24pt 로 되돌아가서
   행간 축소가 통째로 무효가 된다(그렇게 만들었다가 잡았다).
   주석 오프셋은 행간과 무관하다: 기준선은 상자 바닥에서 L/2−3.925pt 라
   (L/2 + dy) − (L/2 − 3.925) = dy + 3.925 로 L 이 상쇄된다. */
.passage .w{position:relative;display:inline-block;line-height:inherit}
.wc{white-space:nowrap}
.w.blue,.blue{color:var(--blue)}
.w.red,.red{color:var(--red)}
/* 형광펜 = **굵은 밑줄**. 인디자인이 그렇게 그린다(밑줄 9pt · offset −3).
   그라디언트 배경으로 하면 뷰어가 래스터 이미지로 굽는다(실측: 100×3.2mm
   이미지가 면마다 수십 개). 밑줄은 벡터로 남는다. */
.passage mark,.passage .hl{color:inherit;background:none;
  text-decoration:underline;text-decoration-color:var(--hl);
  text-decoration-thickness:__hlw__pt;text-underline-offset:-__hlo2__pt;
  text-decoration-skip-ink:none}
.passage i{position:absolute;left:50%;transform:translateX(-50%);
  font-family:PBRuby;font-size:__anno_size__pt;line-height:1;color:var(--anno);
  white-space:nowrap;font-style:normal}
.passage i.up{bottom:calc(50% + var(--up-dy))}
.passage i.dn{top:calc(50% + var(--dn-dy))}
/* 물결 밑줄 — 원본은 `영어 지문 물결`(Wavy 1.5pt, offset 2, CMYK 0/85/0/0).
   currentColor 로 두면 글자색을 따라가 검은 물결이 되고, 두께를 안 주면
   브라우저 기본값이라 굵은 점선처럼 보인다. */
.wave{text-decoration:underline wavy var(--wave);
  text-decoration-thickness:1.5pt;text-underline-offset:2pt;
  text-decoration-skip-ink:none}

.rule{position:absolute;height:0;border-top:.5pt solid var(--chip)}
.chip{position:absolute;background:var(--chip);color:var(--band);
  font-family:PBHand;font-size:6pt;display:flex;align-items:center;
  justify-content:center}
/* 삽화는 **틀에 맞춰 넣는다**. 폭만 주면 세로가 제멋대로 늘어 폴리오를 덮는다
   (원본 틀은 59.62×45.9mm 고정이고 캡션은 그림 안에 들어 있다). */
.illust{position:absolute;margin:0;overflow:hidden}
.illust img{width:100%;height:100%;object-fit:contain;object-position:top center;
  display:block}
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
/* 모눈은 원본에서 뽑은 이미지를 쓴다. CSS 그라디언트는 뷰어 반올림 때문에
   1.44mm 격자가 뭉쳐 굵은 격자무늬로 나온다(실측). */
/* 모눈은 **깔개를 따로 깐다** — 원본이 배경 이미지에 불투명도 55% 를 줬다.
   배경 레이어에는 CSS 로 불투명도를 못 주므로 밑에 한 겹 깔고 글을 그 위에
   올린다(글자까지 흐려지면 안 된다). */
.flow{position:absolute;overflow:hidden;background:var(--flow-bg);
  font-family:PBDodam;font-size:__flow_size__pt;line-height:__flow_lead__mm;
  padding:2.5mm 3mm;box-sizing:border-box;columns:2;column-gap:3mm}
.flow::before{content:"";position:absolute;left:0;top:0;right:0;bottom:0;
  background:url("img/flownote_grid.png") 0 0/100% 100% no-repeat;
  opacity:__flow_grid_alpha__;pointer-events:none}
.flow p{margin:0;break-inside:avoid;position:relative}
/* 색은 **기호에만**. 원본 문자 스타일 4종이 글자 단위로 붙어 있다. */
.flow .sym{color:var(--flow-arrow)}
.flow .sym2{color:var(--flow-sym2)}
.flow .brk{color:var(--flow-brk)}
.flow .par{color:var(--flow-par)}

.topicband{position:absolute;background:var(--topic-bg);box-sizing:border-box;
  padding:1.6mm 2mm}
.tbadge{position:absolute;font-family:PBDodam;font-size:9pt;color:#fff;
  border-radius:.8mm;padding:0 1mm;line-height:1.4}
.tbadge.t{background:var(--topic-chip)}
.tbadge.s{background:var(--sum-chip)}
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
.memtest .n{font-size:5.5pt;vertical-align:super;color:var(--mt-no)}
.memtest .red{color:var(--mt-ans)}    /* 정답 (CMYK 0/30/70/0) */
/* 문제면의 빈칸 — 원본은 정답 글자에 '칠하지 않음' 스와치를 줘서 자리만 남긴다.
   글자를 지우면 자리가 좁아져 정답면과 줄이 달라진다. 투명하게만 만든다. */
.memtest .blank{color:transparent;letter-spacing:.06em}
.n{font-size:5.5pt;vertical-align:super;color:var(--mt-no)}
/* 원본 B-마스터: 문제면은 베이지 바탕에 같은 색 테두리, 정답면은 연파랑
   바탕에 파란 테두리(0.5pt). 두 면을 같은 색으로 두면 어느 쪽인지 안 보인다. */
.mtbox{position:absolute;border:.5pt solid var(--mt-q-bg);
  background:var(--mt-q-bg);border-radius:1mm}
.mtbox.a{border-color:var(--mt-line);background:var(--mt-a-bg)}
.mtchip.a{background:var(--mt-line);color:#fff}
"""
