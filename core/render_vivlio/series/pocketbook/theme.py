import re
# -*- coding: utf-8 -*-
"""포켓북 테마 CSS — 값은 전부 **완성본 실측**이고, 전부 손잡이다.

수치를 코드에 박지 않는다. `config.json` 의 `palette`·`metrics` 로 덮어쓸 수 있게
기본값만 여기 둔다(자립화 계획 S3). 기본값 = 지금 납품본과 같은 지면.

실측 출처: 상일2 26-2 포켓북 내지 PDF(148×210) 2·3면.
"""

# ── 색 (실측) ─────────────────────────────────────────────
PALETTE = {
    "band":      "#EAE6DC",   # 위·아래 띠 (기본 = 모의고사)
    # ⚠ 띠 색은 **교재 성격을 가르는 표시**다. 원본은 마스터를 나눠 그렇게 쓴다
    #   (A·F 마스터 CMYK 32/0/4/14 · I·H 43/55/0/0 · 나머지 2/3/8/6 실측).
    #   펼쳐 놓고 어느 교재인지 색으로 알아보라는 뜻이라 한 색으로 통일하면 안 된다.
    "band_lesson": "#92C3D4",   # 교과서 — 하늘
    "band_unit":   "#D5CBE3",   # 부교재(올림포스·수특·리딩파워) — 연보라
    "band_mock":   "#EAE6DC",   # 모의고사 — 베이지
    # ⚠ 완성본 실측값은 연보라 `#CAC1DB` 였으나 부교재 띠(`band_unit`)와
    #   눈으로 구별이 안 됐다(사용자 지적). 어휘는 뒤에 붙는 딴 파트라
    #   갈래가 보여야 한다 — 책이 이미 쓰는 따뜻한 강조색 계열로 옮긴다.
    "band_voca":   "#F0CBA8",   # 어휘 파트 — 살구
    "navy":      "#54669E",   # 지문번호 배지 · 쪽번호
    "chip":      "#869CD0",   # PICTURE / TRANSLATION 칩
    "ink":       "#231F20",   # 본문
    "blue":      "#224E8E",   # 강조 파랑
    "red":       "#D2232A",   # 강조 빨강
    "anno":      "#A7A9AC",   # 구문분석 주석
    "trans":     "#58595B",   # 번역
    "topic_bg":  "#FAFAF8",   # 주제/요약 띠
    # ⚠ **바탕과 선은 다른 문제다.** "플로우노트가 진하다" 는 지적을 선 색으로
    #   알아듣고 선만 계속 옅게 만들었다가 여러 번 헛돌았다. 진한 것은 **바탕
    #   색면**이고, 모눈 선은 오히려 잘 보여야 한다.
    # ⚠ 판과 상자가 같은 색이라 블록이 안 보였다(사용자 지적). 판을 한 단
    #   짙게 깔고 상자를 희게 띄운다.
    "flow_bg": "#EDEFE1", "flow_box": "#FFFFFF",
    "flow_edge": "#BFC8A8",   # 덩어리 상자 테두리
    # ⚠ 모눈 색은 **이 값이 곧 인쇄색**이다. 예전엔 진한 선(#BFC3C9)을 깔고
    #   불투명도로 옅게 만들었는데, 옅기를 맞추라는 지적을 몇 번 받고도 계속
    #   빗나갔다(불투명도는 바탕과 섞인 결과라 눈으로 겨냥이 안 된다).
    #   이제 모눈 그림을 **이 색으로 직접 그린다** — 보이는 색 = 적은 색.
    "flow_line": "#D2D8C0",   # 모눈 선 — 바탕이 옅어졌으니 선은 보이게
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
    # ⚠ 암기 TEST **본문**은 원본에 문자 스타일이 없다(런 2개/1761자) — 그래서
    #   글자색은 IDML 에서 확인할 길이 없다. 스타일시트의 `B 테스트:…_빨간색`
    #   (0/30/70/0 = #FDBB63) 을 써 봤더니 연파랑 정답면 위에서 대비 1.3:1 로
    #   읽히지가 않았다. **완성 PDF 에서 잰 예전 값**을 그대로 둔다. 상자 색만
    #   IDML 근거가 확실해 바꿨다(B-마스터 TextFrame 채움).
    "mt_ans":    "#E8963C",   # 암기 정답 낱말 (완성본 실측)
    "mt_no":     "#A7A9AC",   # 암기 번호 (완성본 실측)
    # 어휘 파트 — 완성본 문자 스타일 `뜻 빨간색` CMYK 10/85/57/0
    "voca_hit":  "#DB4D5D",
    "voca_ipa":  "#7B7B7B",
    "voca_rule": "#ECE9E1",     # 낱말 사이 가는 선 (완성본 실측)
    "syn_dot":   "#C9D1EA",     # 동반의어 괘선이 끊기는 점 (완성본 실측)
    "voca_no":   "#A7A9AC",
    "syn_word":  "#231F20",
    "syn_syn":   "#224E8E",   # `=` 유의어
    "syn_ant":   "#E14E6B",   # `↔` 반의어
    "card1":     "#F8F6E2",   # 동반의어 1열
    "card2":     "#ECE1EB",   # 2열
    "card3":     "#D6E3EF",   # 3열
}

# 형광펜 — 이름은 인디자인 문자 스타일 그대로(`형광펜_노랑` …).
#
# ⚠ 값은 **잉크 원색**이고, 실제로 찍히는 색은 `hl_tint` 농도로 정해진다.
#   인디자인에서도 그렇게 쓴다 — 스타일에 진한 잉크를 걸어 두고 `UnderlineTint`
#   로 낮춘다(현장 기준 **5%**). 옅은 색을 직접 적어 두면 "더 여리게" 를 맞출
#   때마다 여섯 색을 따로 손봐야 하고 서로 어긋난다.
HIGHLIGHT_INK = {
    "yellow": "#FCED00", "mint": "#13B899", "pink": "#977DB9",
    "sky": "#86B2DF", "violet": "#9D87BF", "orange": "#F39857",
}
HIGHLIGHT = {}                       # `build_css` 가 농도를 먹여 채운다

# ── 치수 mm/pt (실측) ─────────────────────────────────────
METRICS = {
    "page_w": 148.0, "page_h": 210.0, "bleed": 3.0,
    "band_h": 5.5,                 # 위·아래 띠 (도련까지 8.5)
    "margin_l": 15.0, "margin_r": 18.0,
    # 제본 안전 영역 — **스프링 제본** 기준. 안쪽(제본) 가장자리에서 이만큼은
    # 구멍이 뚫려 아예 안 보인다. 지문면(왼쪽 면)은 오른쪽이 안쪽이다.
    # 판면은 이미 130mm 에서 끝나므로, 주석이 그보다 나가더라도 여기까지다.
    "bind_safe": 12.0,
    "badge": [15.0, 15.0, 18.0, 5.5],
    # 「주제 :」 직접 써 보는 칸 — 26-1-기말 광문1 완성본(`내지2`) 실측.
    #   지문번호 딱지 오른쪽에 붙어 오른쪽 여백선까지 간다. 광문만 쓴다.
    "topicbox": [36.05, 10.44, 93.90, 10.82],
    # 두 줄 배지 — 「주제 :」 칸 왼쪽에 세워 둔다(광문). 칸과 위·아래를 맞춘다.
    "badge2": [15.0, 10.44, 19.05, 10.82],
    "badge2_pad": 1.2, "badge2_lead": 3.9,
    "topicbox_r": 0.5,                       # 모서리
    "topicbox_lab": [37.30, 11.50],          # 「주제 :」 자리
    "topicbox_pen": [126.36, 8.25, 3.72, 3.32],       # x y w h
    "badge_size": 9.5, "badge_radius": 1.0,
    "passage": [15.0, 24.0, 115.0, 118.0],  # x y w h
    "passage_size": 9.0, "passage_lead": 24.0,
    "passage_track": -0.022,       # em — 이 값에서 원본과 행바꿈이 일치한다
    "first_baseline_fix": -7.7,    # pt, 인디자인 '어센트' 기준 보정
    "anno_size": 7.0, "anno_up": 4.3, "anno_dn": 6.8,
    # 형광펜 = 굵은 밑줄. 인디자인 UnderlineWeight 9 / Offset −3 이고, 실측하면
    # **획 중심이 기준선 3pt 위**다. CSS 는 밑줄의 **윗변**을 offset 으로 잡으므로
    # offset = −(중심 + 두께/2) = −7.5pt 가 되어야 글자 위에 얹힌다.
    "hl_weight": 9.0, "hl_center": 2.75,
    "hl_tint": 5.0,                 # 형광펜 농도(%) — 인디자인 현장값
    # '서술형' 표식 — 원본 실측 9.06×5.64pt, 바닥중앙 기준 8.5pt 위
    "icon_h": 7.23, "icon_dy": 8.5,
    "rule_y": 148.0,
    "chip": [16.0, 2.71], "chip_pic_x": 56.5, "chip_trn_x": 114.0,
    "chip_y": 145.2,
    "illust": [12.88, 149.1, 59.62, 45.9],
    "trans": [74.0, 150.0, 56.0], "trans_size": 5.9, "trans_lead": 3.2,
    "folio_y": 196.5, "folio_size": 6.0,
    # 오른쪽 면
    # 플로우노트는 **8pt 가 기본**이고, 넘칠 때만 7pt 로 내린다(사용자 지시).
    # 플로우노트를 마인드맵 덩어리로 바꾸면서 자리를 키웠다(41→71.2mm).
    # 늘어난 몫은 동반의어 카드에서 났다 — 32mm 상자에 글은 중앙 11.2mm 밖에
    # 안 들어가 20mm 가 비어 있었다(완성 PDF 536장 실측).
    "flow": [18.0, 18.31, 115.0, 71.16],
    "fbox_inset": 3.0,          # 덩어리 상자가 판 안쪽에서 물러나는 거리
    "fbox_gap": 4.2,            # 상자 사이(잇는 표식이 앉을 자리)
    "fbox_pad": 2.0,
    "fbox_head": 4.6,           # 머리말 딱지가 먹는 높이
    "fconn": 3.6,               # 잇는 표식 지름
    "fconn_len": 7.4,           # 잇는 점선 길이 — 세로·대각선 모두 같다
    # 3덩어리 짜임새 — "three" 3단 나란히(사용자 선택) · "one" 한 단 3칸 ·
    #   "two" 두 단 · "auto" 들어가면 한 단, 넘치면 두 단.
    "flow3": "three",
    # 상자가 넓어진 만큼 글도 키웠다(9→9.5pt). 10pt 부터는 넘치는 덩어리가
    # 2%→12% 로 뛴다(광문1 251덩어리 실측) — 9.5 가 한계다.
    "flow_size": 9.5, "flow_lead": 4.35,
    "flow_min_size": 8.0,           # 넘칠 때 내려가는 자리
    "flow_track": -0.05,            # 자간 (원본 문자 스타일 Tracking=-50)
    "flow_sec_gap": 2.4,            # 묶음 사이 띄움(mm) — 한눈에 갈리게
    "flow_grid": 1.44, "flow_chip": [104.0, 12.86, 29.0, 5.45],
    # 모눈 배경은 원본에서 **불투명도 55%** 로 깔려 있다(마스터 실측).
    # 100% 로 깔면 글자보다 모눈이 세 보인다.
    "flow_grid_alpha": 0.3,
    # 어휘 파트 (26-1-기말 광문1 완성본 실측: 상자 115×177mm · 한 면 15낱말)
    # 어휘 파트 — 26-1-기말 광문1 완성본 124~125면 실측
    "voca": [15.0, 12.6, 114.8, 178.0],     # 상자 x y w h (끝 190.6mm)
    "voca_head": [15.0, 6.5, 37.0, 5.45],   # 머리말 딱지
    "voca_head_size": 8.0, "voca_icon": 4.1,
    "voca_col": 41.0,          # 왼쪽 단(번호·회독·표제어) 폭 = 56.0 − 15.0
    "voca_word": 10.0, "voca_no": 5.0,
    "voca_ck": 2.87, "voca_ck_gap": 0.45, "voca_hw_gap": 1.6,
    "voca_ipa_x": 15.4,        # 표제어 x(30.4) − 단 시작(15.0)
    "voca_mean": 7.0, "voca_mean_lead": 2.9,
    "voca_ex": 6.0, "voca_ex_lead": 2.47, "voca_ex_gap": 1.5,
    "voca_pad": 1.6, "voca_gap": 1.5,
    "voca_track": -0.025, "voca_ex_track": -0.03,
    "topic": [18.0, 89.47, 115.0, 23.09], "topic_size": 8.0,
    "topic_lead": 3.5, "topic_text_x": 29.8,
    "syn_panel": [18.09, 118.27, 114.82, 76.73],
    # 동반의어 제목 — 표식(A·B·C 색면)이 너무 작아 글자가 안 보인다는 지적.
    # 덮개는 **제목에 딱 붙는 폭**이라야 한다 — 넓으면 오른쪽 동그라미가 제목에서
    # 멀찍이 떨어져 선이 괜히 끊긴 것처럼 보인다(완성본 덮개 20.70~43.33).
    "syn_title": [20.7, 114.76, 24.0, 6.2],
    "syntitle_size": 7.0, "synmark_h": 5.4,
    "syntitle_dot": 1.05,           # 괘선이 끊기는 자리의 동그라미(mm·실측)
    "syntitle_dot_gap": 1.6,        # 제목과 동그라미 사이
    "tbadge_w": 9.6, "tbadge_gap": 1.2,
    # ⚠ 22.0 이면 넉 줄짜리 카드의 마지막 내려긋기가 0.5mm 삐져나온다(실측
    #   536장 중 3장). 0.6mm 를 **행 사이에서 꺼내** 상자에 주므로 판 전체
    #   높이는 그대로다.
    "card": [21.2, 120.99, 34.6, 22.6],
    "card_gap_x": 37.25, "card_gap_y": 24.72,
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
#   선은 **딱지에 붙는다**(딱지 아래 2.71mm = 딱지 높이). 원본은 0.19mm 떠 있는데
#   지면에서 끊겨 보여 붙이기로 했다(사용자 지적). 해석은 선 아래 3.0mm.
LAYOUTS = {
    "A": {"passage_h": 127.0, "rule": 155.41,
          "chip_y": 152.7, "chip_trn_x": 114.0, "illust": None,
          "trans": [15.0, 158.6, 115.0]},
    "C": {"passage_h": 118.0, "rule": 147.91,
          "chip_y": 145.2, "chip_trn_x": 114.0, "chip_pic_x": 56.5,
          "illust": [12.88, 149.1, 59.62, 45.9],
          "trans": [74.0, 151.1, 56.0]},
    "E": {"passage_h": 131.0, "rule": 160.71,
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
    # 형광펜 = 잉크에 농도를 먹인 색. `highlight` 로 색을 직접 주면 그게 이긴다.
    t = M.get("hl_tint", 5.0) / 100.0

    def _tint(hexs):
        r, g, b = (int(hexs[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02X%02X%02X" % tuple(
            round(255 - (255 - c) * t) for c in (r, g, b))

    H = {k: _tint(v) for k, v in HIGHLIGHT_INK.items()}
    H.update(highlight or {})

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
        "fbox_pad": "%g" % M["fbox_pad"],
        "fbox_head": "%g" % M["fbox_head"],
        "topic_size": "%g" % M["topic_size"],
        "topic_lead": "%g" % M["topic_lead"],
        "card_size": "%g" % M["card_size"], "card_lead": "%g" % M["card_lead"],
        "cardpad": "%g" % M["card_pad"],
        "mt_size": "%g" % M["memtest_size"], "mt_lead": "%g" % M["memtest_lead"],
        "flow_sec_gap": "%g" % M["flow_sec_gap"],
        "flow_track": "%g" % M["flow_track"],
        "topicbox_r": "%g" % M["topicbox_r"],
        "badge2_pad": "%g" % M["badge2_pad"],
        "syntitle_dot": "%g" % M["syntitle_dot"],
        "syntitle_dot_gap": "%g" % M["syntitle_dot_gap"],
        "badge_size": "%g" % M["badge_size"],
        "badge_r": "%g" % M["badge_radius"],
        "badge_w": "%g" % M["badge"][2],
        "tbadge_w": "%g" % M["tbadge_w"],
        "tbadge_gap": "%g" % M["tbadge_gap"],
        "syntitle_size": "%g" % M["syntitle_size"],
        "synmark_h": "%g" % M["synmark_h"],
        "ico_h": "%g" % M["icon_h"], "ico_dy": "%g" % M["icon_dy"],
        "voca_word": "%g" % M["voca_word"], "voca_no": "%g" % M["voca_no"],
        "voca_mean": "%g" % M["voca_mean"],
        "voca_mean_lead": "%g" % M["voca_mean_lead"],
        "voca_ex": "%g" % M["voca_ex"],
        "voca_ex_lead": "%g" % M["voca_ex_lead"],
        "voca_ex_gap": "%g" % M["voca_ex_gap"],
        "voca_gap": "%g" % M["voca_gap"], "voca_pad": "%g" % M["voca_pad"],
        "voca_col": "%g" % M["voca_col"], "voca_ck": "%g" % M["voca_ck"],
        "voca_ck_gap": "%g" % M["voca_ck_gap"],
        "voca_hw_gap": "%g" % M["voca_hw_gap"],
        "voca_ipa_x": "%g" % M["voca_ipa_x"],
        "voca_head": "%g" % M["voca_head_size"],
        "voca_icon": "%g" % M["voca_icon"],
        "voca_track": "%g" % M["voca_track"],
        "voca_ex_track": "%g" % M["voca_ex_track"],
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
  --flow-edge:__flow_edge__;
  --voca-hit:__voca_hit__; --voca-ipa:__voca_ipa__;
  --voca-rule:__voca_rule__; --voca-chip:__band_mock__;
  --syn-dot:__syn_dot__;
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
    background:var(--pgband,var(--band))}
.pg.k-lesson{--pgband:__band_lesson__}
.pg.k-unit{--pgband:__band_unit__}
.pg.k-mock{--pgband:__band_mock__}
.pg.k-voca{--pgband:__band_voca__}
.pg::before{top:0;height:__band_bleed__}
.pg::after{bottom:0;height:__band_bleed__}

/* ── 왼쪽 면 ─────────────────────────────────── */
/* 배지는 폭이 고정이다(18mm). padding 을 주면 상자가 그만큼 넓어져 원본과
   어긋난다(실측 20mm) → box-sizing 으로 안쪽에서 먹게 한다. */
/* 배지는 **글에 맞춰 늘어난다**. 폭을 18mm 로 못 박아 뒀더니 분석본에서 오는
   긴 라벨이 양옆으로 잘렸다(사용자 지적). 최소 폭만 지킨다. */
.badge{position:absolute;background:var(--navy);color:#fff;font-family:PBBadge;
  font-size:__badge_size__pt;display:inline-flex;align-items:center;
  justify-content:center;letter-spacing:.02em;padding:0 2mm;white-space:nowrap;
  box-sizing:border-box;border-radius:__badge_r__mm;min-width:__badge_w__mm}
/* 두 줄 배지 — 위 칸 교재명, 아래 칸 지문번호 */
.badge.two{flex-direction:column;justify-content:center;white-space:normal;
  padding:__badge2_pad__mm .8mm;text-align:center;letter-spacing:0}
.badge.two .bh{opacity:.82;font-size:.86em}
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
/* ⚠ 구문분석 주석이 붙은 낱말(`.w`)은 **inline-block** 이라 CSS 규칙상 조상의
   밑줄이 그려지지 않는다 — 그래서 형광펜이 낱말마다 뚝뚝 끊겨 나왔다.
   같은 밑줄을 낱말 자신에게도 준다(`--hl` 은 mark 에서 물려받는다). */
.passage mark .w,.passage .hl .w{text-decoration:underline;
  text-decoration-color:var(--hl);text-decoration-thickness:__hlw__pt;
  text-underline-offset:-__hlo2__pt;text-decoration-skip-ink:none}
/* '서술형' 표식 — 폭 0 으로 심어 줄 흐름을 건드리지 않고 글 위에 띄운다 */
/* 표식 + 첫 낱말은 한 덩이 — 사이에서 줄이 바뀌면 별표만 줄 끝에 남는다. */
.passage .nb{white-space:nowrap}
.passage .ico{position:relative;display:inline-block;width:0;height:0;
  vertical-align:baseline;text-decoration:none}
.passage .ico img{position:absolute;left:0;bottom:__ico_dy__pt;
  height:__ico_h__pt;width:auto;max-width:none}
.passage i{position:absolute;left:50%;transform:translateX(-50%);
  font-family:PBRuby;font-size:__anno_size__pt;line-height:1;color:var(--anno);
  white-space:nowrap;font-style:normal}
.passage i.up{bottom:calc(50% + var(--up-dy))}
.passage i.dn{top:calc(50% + var(--dn-dy))}
/* 물결 밑줄 — 원본은 `영어 지문 물결`(Wavy 1.5pt, offset 2, CMYK 0/85/0/0).
   currentColor 로 두면 글자색을 따라가 검은 물결이 되고, 두께를 안 주면
   브라우저 기본값이라 굵은 점선처럼 보인다. */
/* ⚠ 두께를 크게 주면 브라우저가 **굵은 지그재그**로 그려 체크무늬처럼 보인다
   (1.5pt 로 했다가 지적받았다). 원본은 가는 물결이다. */
/* ⚠ 브라우저의 `wavy` 는 두께에 따라 굵은 지그재그(1.5pt)나 점선(0.5pt)으로
   제멋대로 그려진다 — 두 번 다 지적받았다. 물결을 **직접 그려** 붙인다. */
.wave{text-decoration:none;
  background-image:url("data:image/svg+xml;utf8,\
<svg xmlns='http://www.w3.org/2000/svg' width='6' height='3' viewBox='0 0 6 3'>\
<path d='M0 2.2 Q1.5 0.3 3 2.2 T6 2.2' fill='none' stroke='__wave__' \
stroke-width='0.7' stroke-linecap='round'/></svg>");
  background-repeat:repeat-x;background-position:left calc(100% + 1.2pt);
  background-size:6px 3px;padding-bottom:1pt}

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
  line-height:__trans_lead__mm;color:var(--trans);
  /* 양끝 맞추기다(완성본과 같다). ⚠ `word-break:keep-all` 을 같이 걸면
     한글이 낱말 안에서 못 꺾여 줄이 일찍 끝나고, 그 모자란 몫을 **띄어쓰기
     몇 곳이 다 떠안아** 첫 줄 낱말 사이가 확 벌어진다(사용자 지적). 한글은
     글자 사이에서 꺾이게 두어야 줄이 꽉 차고 벌어짐이 안 생긴다. */
  text-align:justify;letter-spacing:-.03em}
.translation p{margin:0}
/* 「주제 :」 써 보는 칸 — 완성본대로 남색 테두리에 도담도담 9pt(자간 -0.1em) */
.tbox{position:absolute;border:.5pt solid var(--navy);
  border-radius:__topicbox_r__mm}
.tboxlab{position:absolute;font-family:PBDodam;font-size:9pt;
  letter-spacing:-.1em;color:var(--navy);white-space:nowrap}
.tboxpen{position:absolute}
.tboxpen svg{width:100%;height:100%;display:block}
.folio{position:absolute;font-family:PBElice;font-size:__folio__pt;
  font-weight:700}
/* 쪽번호 **옆에 붙는 말**(단원·VOCA)은 완성본이 Medium 이다 — Bold 로 두면
   쪽번호보다 세 보인다(사용자 지적). */
.folio span{font-weight:500}
.folio b{color:var(--navy)}
.folio.r{text-align:right}

/* ── 오른쪽 면 ───────────────────────────────── */
/* ⚠ 딱지가 베이지(`--band`)라 플로우 판과 따로 놀았다(사용자 지적).
   판과 같은 색으로 이어 붙이고, 판 위에 얹힌 꼴이므로 **위쪽만** 둥글게. */
.flowchip{position:absolute;background:var(--flow-bg);display:flex;
  align-items:center;justify-content:center;gap:1mm;
  border-radius:1.6mm 1.6mm 0 0;
  font-family:PBHand;font-size:8pt;color:var(--navy)}
/* 딱지 아이콘 — 원본 벡터를 그대로 심는다(이모지 아님) */
.ic-chip_flow{height:3.2mm;width:auto;flex:none}
.ic-chip_memtest{height:3.4mm;width:auto;flex:none}
.ic-pen{width:100%;height:100%;display:block}
.ic-synmark{height:__synmark_h__mm;width:auto;flex:none;overflow:visible}
/* 모눈은 원본에서 뽑은 이미지를 쓴다. CSS 그라디언트는 뷰어 반올림 때문에
   1.44mm 격자가 뭉쳐 굵은 격자무늬로 나온다(실측). */
/* 모눈은 **깔개를 따로 깐다** — 원본이 배경 이미지에 불투명도 55% 를 줬다.
   배경 레이어에는 CSS 로 불투명도를 못 주므로 밑에 한 겹 깔고 글을 그 위에
   올린다(글자까지 흐려지면 안 된다). */
/* 모눈은 조판할 때 **팔레트 색으로 그려 낸다**(`_stage_assets`). 불투명도로
   옅게 만들지 않는다 — 적은 색이 그대로 인쇄색이라야 겨냥이 된다. */
.flow{position:absolute;overflow:hidden;background:var(--flow-bg)}
/* ⚠ 단 감싸개는 **흐름 안에** 둬야 한다. 절대배치로 두면 높이를 안 정한 판
   (실측용 판)에서 높이가 0 이 되어 **잉크가 하나도 안 나오고 측정이 통째로
   실패한다**(`항목 52 vs 측정 면 0`). `height:100%` 는 부모가 높이를 안 주면
   저절로 auto 라 실측 판에서도 자연 높이가 나온다.
   z-index 는 깔개(::before)보다 위에 서려고 준다 — 안 주면 모눈이 글을 덮는다. */
/* 마인드맵 덩어리 — 모눈 판 위에 반투명 흰 상자를 얹는다.
   ⚠ 상자 안 글은 `columns` 를 쓰지 않는다. 두 단으로 흘리면 왼쪽을 다 읽고
     오른쪽으로 건너뛰어야 해 흐름이 안 보인다(그래서 갈아엎었다). */
.fbox{position:absolute;box-sizing:border-box;overflow:hidden;
  display:flex;flex-direction:column;justify-content:flex-start;
  background:url("img/flownote_grid.png") no-repeat,#fff;
  border:.5pt solid var(--flow-edge);
  border-radius:1.6mm;padding:__fbox_pad__mm;z-index:1}
.fbh{font-family:PBJalnan;font-size:7pt;color:var(--flow-brk);
  line-height:__fbox_head__mm;margin:0 0 .3mm;
  display:flex;align-items:center;gap:1.1mm}
.fbt{font-family:PBJalnan;color:var(--flow-brk)}
/* ⚠ 한 단에서는 머리말이 첫 줄에 붙는다. 색을 줄 전체에 주면 **본문까지
   파래진다**(실측) — 색은 머리말 딱지에만. */
.fbl{color:inherit}
/* ⚠ 첫 줄에 붙는 머리말은 본문 크기(9.5pt)를 물려받아 **네 덩어리짜리보다
   커 보였다**(사용자 지적). 딱지와 같은 7pt 로 못 박는다. */
.fbl .fbn{margin-right:1.1mm;vertical-align:-.5mm}
.fbl .fbt{margin-right:1.4mm;font-size:7pt}
.fbn{display:inline-flex;align-items:center;justify-content:center;
  width:3.2mm;height:3.2mm;border-radius:50%;flex:none;
  background:var(--flow-brk);color:#fff;font-size:5.5pt;line-height:1}
.fbi{font-family:PBDodam;font-size:__flow_size__pt;
  line-height:__flow_lead__mm;letter-spacing:__flow_track__em}
/* 잇는 점선 — 방향만 알려 주면 되므로 화살촉은 아주 작다. 세로와 대각선이
   같은 규격이고, 색은 주황이 아니라 **상자 테두리와 같은 색**이다
   (주황은 상자 안 `→` 몫이라 겹치면 어느 게 큰 흐름인지 안 보인다). */
.fconn{position:absolute;z-index:2;color:var(--flow-edge)}
.fconn svg{width:100%;height:100%;display:block}
/* 좁은 단에서는 한 줄이 두 줄로 접힌다 — 이어지는 줄을 들여 써서 새 항목과
   구분한다(`→` 는 줄머리에만 서고 이어지는 글은 그 아래로 붙는다). */
.fbi p{margin:0;padding-left:3.2mm;text-indent:-3.2mm}
.fbi p.sec{margin-top:__flow_sec_gap__mm}
/* 색은 **기호에만**. 원본 문자 스타일 4종이 글자 단위로 붙어 있다. */
.fbi .sym{color:var(--flow-arrow)}
.fbi .sym2{color:var(--flow-sym2)}
.fbi .brk{color:var(--flow-brk);font-weight:600}
.fbi .par{color:var(--flow-par)}

/* ── 어휘 파트 ─────────────────────────────────────────────
   완성본 문단 스타일 그대로: 표제어 10pt · 뜻 7pt(행간 12) · 예문 6pt(행간 7).
   `[…]` 로 감싼 자리가 그 낱말이 쓰인 곳이라 색이 붙는다(`뜻 빨간색`). */
/* ── 어휘 파트 ─────────────────────────────────────────────
   26-1-기말 광문1 완성본(`광문1_포켓북_내지2.pdf` 124~125면) 실측 그대로다.
   **두 단**이다 — 왼쪽에 번호·회독칸·표제어, 오른쪽에 뜻·예문.
     번호 x15.5(5pt 남색) · 회독 ○ 2.87mm 3개(19.2/22.4/25.7) · 표제어 x30.4(10pt)
     오른쪽 단 x56.0 폭73.7 · 뜻 7pt #58595B · 예문·해석 6pt · 강조 #DB4D5D
     낱말 사이 가는 선 #ECE9E1 */
.voca{position:absolute;font-family:PBBody,sans-serif;color:var(--ink);
  letter-spacing:__voca_track__em}
.voca .ent{display:table;width:100%;table-layout:fixed;
  border-top:.25pt solid var(--voca-rule);padding-top:__voca_pad__mm;
  margin-bottom:__voca_gap__mm;break-inside:avoid}
.voca .ent:first-child{border-top:0}
.voca .l{display:table-cell;width:__voca_col__mm;vertical-align:top;
  white-space:nowrap}
.voca .r{display:table-cell;vertical-align:top}
.voca .no{font-size:__voca_no__pt;color:var(--navy);font-weight:500;
  vertical-align:.9mm}
.voca .ck{display:inline-block;width:__voca_ck__mm;height:__voca_ck__mm;
  border:.25pt solid var(--trans);border-radius:50%;
  margin-left:__voca_ck_gap__mm;vertical-align:.2mm}
.voca .hw{font-size:__voca_word__pt;line-height:1;margin-left:__voca_hw_gap__mm}
/* ⚠ 발음기호는 완성본에 없던 것(26-2 원고에 새로 들어왔다). 표제어 옆에 두면
   긴 것이 왼쪽 단(41mm)을 넘어 오른쪽 단 글과 겹친다 — **아랫줄**에 앉힌다. */
.voca .ipa{display:block;font-size:__voca_no__pt;color:var(--voca-ipa);
  margin:.5mm 0 0 __voca_ipa_x__mm;line-height:1}
.voca .mn{font-size:__voca_mean__pt;color:var(--trans);margin:0;
  line-height:__voca_mean_lead__mm}
.voca .dv{font-size:__voca_ex__pt;color:var(--voca-ipa);margin:.6mm 0 0;
  line-height:__voca_ex_lead__mm}
.voca .ex{font-size:__voca_ex__pt;margin:__voca_ex_gap__mm 0 0;
  line-height:__voca_ex_lead__mm;letter-spacing:__voca_ex_track__em}
.voca .exk{font-size:__voca_ex__pt;margin:0;line-height:__voca_ex_lead__mm;
  letter-spacing:__voca_ex_track__em}
.voca .hit{color:var(--voca-hit)}
.voca .pos{color:var(--trans)}
/* 머리말 딱지 — 완성본 실측: **둥근 베이지 딱지 + 책·돋보기 아이콘**,
   글은 학교안심 운동장(PBHand) 8pt 남색이다. 네모 딱지에 본문 글꼴로 두면
   완성본과 아예 다른 물건이 된다(사용자 지적). */
.vhead{position:absolute;background:var(--voca-chip);color:var(--navy);
  font-family:PBHand;font-size:__voca_head__pt;display:inline-flex;
  align-items:center;gap:1.2mm;padding:0 2.4mm;box-sizing:border-box;
  border-radius:1.5mm;letter-spacing:-.025em;white-space:nowrap;width:auto}
.vhead svg{height:__voca_icon__mm;width:auto;flex:none}

.topicband{position:absolute;background:var(--topic-bg);box-sizing:border-box;
  padding:1.6mm 2mm}
/* 주제·요약문은 **딱지와 글이 한 줄로 묶인다**. 딱지를 따로 앉히고 자리를
   어림하면 주제가 두 줄일 때 요약문 딱지 옆에 주제가 온다(두 번 지적받았다). */
.tbadge{font-family:PBDodam;font-size:9pt;color:#fff;border-radius:.8mm;
  padding:0 1mm;line-height:1.35;flex:none;text-align:center;
  min-width:__tbadge_w__mm;align-self:flex-start}
.tbadge.t{background:var(--topic-chip)}
.tbadge.s{background:var(--sum-chip)}
.topictext{position:absolute;font-size:__topic_size__pt;
  line-height:__topic_lead__mm}
.trow{display:flex;align-items:flex-start;gap:__tbadge_gap__mm}
.trow+.trow{margin-top:__tbadge_gap__mm}
.ttext{flex:1;min-width:0}
.topictext p{margin:0}

.synpanel{position:absolute;border:1pt solid var(--band);border-radius:2mm;
  box-sizing:border-box}
/* 제목 옆 괘선이 시작·끝나는 자리의 동그라미 — 원본 장식 */
.syndot{position:absolute;width:__syntitle_dot__mm;height:__syntitle_dot__mm;
  border-radius:50%;background:var(--syn-dot)}
.syntitle{position:absolute;background:#fff;font-family:PBJalnan;
  font-size:__syntitle_size__pt;color:var(--navy);display:flex;
  align-items:center;justify-content:center;gap:.8mm}

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
/* 암기 TEST 의 구문분석 주석은 지문면과 **다른 서체·색**이다
   (원본 단락 스타일: RubyFont=강원교육현옥샘, RubyFill=CMYK 41/59/73/52) */
.memtest i{font-family:PBRubyT;color:var(--flow-sym2)}
.n{font-size:5.5pt;vertical-align:super;color:var(--mt-no)}
/* ⚠ 색면을 깔지 않는다. 마스터의 프레임 채움을 보고 베이지·연파랑을 깔았다가
   "왜 배경색이 들어갔냐" 는 지적을 받았다 — 그 채움은 지면에 안 나오는 값이다.
   두 면은 **딱지 글자**로 가른다. */
.mtbox{position:absolute;border:.5pt solid var(--band);border-radius:1mm}
.mtchip.a{background:var(--mt-line);color:#fff}
"""
