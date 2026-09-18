"""워크북 블록·에셋 카탈로그 — 지면(틀) 아래 두 층.

    지면   판형 + 틀(칸) + 껍데기 — `data.STEP_META.layout`, `render.page_block/zone/running_head`
    블록   콘텐츠가 들어가는 덩어리 14종 — 원고 역할(`roles.ROLE_WORDS`)을 받아 `render.blocks_html`/
           `s3_blocks` 가 그린다. 여기서 "어떤 역할이 한 블록인가·필드가 무엇인가·어떤 에셋으로 그리나"를 적는다
    에셋   블록을 그리는 것 — CSS 클래스(테마), SVG, 손잡이(팔레트·서체). `themes/workbook.css`·`knobs`

이 표는 **렌더러를 설명하는 데이터**다. 렌더러(render.py)가 바뀌면 여기도 바뀌어야 한다 —
카탈로그 미리보기(`make --what=blocks`)가 렌더러로 그리므로, 어긋나면 그림에서 드러난다.
"""

# ── 블록 14종 ─────────────────────────────────────────────────────
# roles  : 이 블록이 받는 원고 역할(첫 것이 머리). 미리보기는 이 역할들이 이어진 단락을 뽑아 그린다
# fields : 콘텐츠가 주는 칸
# assets : 그리는 데 쓰는 에셋 id
# steps  : 지금 어느 스텝(지면)에 나오나
BLOCKS = [
    {"id": "passage", "name": "지문 상자", "desc": "원문 또는 변형 지문(어휘·어법 선택 마크 포함)",
     "roles": ["box_body", "vocab_sel", "gram_sel", "gram_bottom", "arr_bottom", "q_passage", "s3_passage"],
     "fields": ["지문 글", "선택 마크(ⓐ/ⓑ · 밑줄)", "지문 번호"],
     "assets": ["box_body", "box_sky", "box_q", "box_lined", "box_orange", "sel_mark", "font_body"],
     "steps": ["step1_a1", "step1_a2", "step1_b1", "step2_a1", "step3"], "max": 1},
    {"id": "pnum", "name": "지문 번호 라벨", "desc": "묶음 머리의 번호(20 · 실전01)",
     "roles": [], "fields": ["번호"], "assets": ["pnum_style", "font_pnum", "color_pnum"],
     "steps": ["*"], "label": True},
    {"id": "prompt", "name": "발문", "desc": "번호 + 발문 문장 + 체크 아이콘",
     "roles": ["q_prompt", "b2_q", "s3_q"], "fields": ["번호", "발문", "아이콘"],
     "assets": ["q_head", "icon_check", "font_disp"], "steps": ["step1_b1", "step1_b2", "step3"], "max": 1},
    {"id": "choices", "name": "선지 목록", "desc": "①~⑤ 선택지",
     "roles": ["q_choice", "b2_choice", "s3_choice"], "fields": ["선지 5줄"],
     "assets": ["choices", "color_sel"], "steps": ["step1_b1", "step1_b2", "step3"], "max": 5},
    {"id": "cond", "name": "조건·보기·배경 상자", "desc": "실전 문항의 <조건> <보기> 배경 글",
     "roles": ["s3_cond", "s3_bogi", "s3_bg"], "fields": ["상자 글(여러 줄)"],
     "assets": ["box_cond", "box_bogi", "box_bg"], "steps": ["step3"], "max": 4},
    {"id": "intro", "name": "세트 안내문", "desc": "'다음 글을 읽고 물음에 답하시오'",
     "roles": ["intro"], "fields": ["안내문"], "assets": ["s3_intro"], "steps": ["step3"], "max": 1},
    {"id": "ox", "name": "O/X 문항 줄", "desc": "번호 + 문장 + O|X 마크",
     "roles": ["ox_item"], "fields": ["번호", "문장", "정답(O/X)"],
     "assets": ["ox_row", "mark_ox"], "steps": ["step1_a2"], "max": 4},
    {"id": "summary", "name": "내용 정리", "desc": "주제·제목 배지 + 정리 줄",
     "roles": ["sum_topic", "sum_line", "sum_title"], "fields": ["주제", "제목", "정리 줄(복수)"],
     "assets": ["badge_topic", "badge_title", "sum_card"], "steps": ["step1_b1"], "max": 8},
    {"id": "arrange", "name": "문장 배열", "desc": "(A)(B)(C) 배열 줄 + 주어진 문장 상자",
     "roles": ["arr_line", "arr_given"], "fields": ["주어진 문장", "배열 줄 3~4", "정답"],
     "assets": ["box_given", "box_arr", "albl"], "steps": ["step1_c1"], "max": 5},
    {"id": "blank", "name": "빈칸 줄", "desc": "빈칸(첫 글자 힌트) + 해석 줄",
     "roles": ["blank_vocab", "blank_kr", "blank_gram"], "fields": ["번호", "빈칸 문장", "해석", "정답"],
     "assets": ["blank_line", "blk_kr", "color_blank"], "steps": ["step1_c2", "step2_c1"], "max": 4},
    {"id": "gram_ox", "name": "어법 O/X 줄", "desc": "문장 + O|X + 고치기 칸",
     "roles": ["gram_ox"], "fields": ["번호", "문장", "틀린 곳·고침"],
     "assets": ["gox_row", "mark_ox", "icon_check"], "steps": ["step2_b1"], "max": 4},
    {"id": "write", "name": "영작 배열", "desc": "해석 줄 + 청크 보기 상자 + 답 줄",
     "roles": ["write_kr", "write_box", "basic"], "fields": ["번호", "해석", "청크 보기", "정답"],
     "assets": ["wr_row", "box_write", "ansline"], "steps": ["step2_c2"], "max": 4},
    {"id": "answer", "name": "답란·영단어 칸", "desc": "서답형 답 쓰는 줄, 영단어 칸",
     "roles": ["s3_answer", "s3_word"], "fields": ["답란 수", "영단어"],
     "assets": ["ansline", "ans3"], "steps": ["step3"], "max": 3},
    {"id": "icon", "name": "아이콘 줄", "desc": "답지 표시 아이콘만 있는 줄",
     "roles": [], "fields": ["아이콘 종류"], "assets": ["icon_check", "ansline"], "steps": ["*"], "icon": True},
]

# ── 에셋 25종 ─────────────────────────────────────────────────────
# kind: box 상자 · badge 배지 · mark 표시 · svg 그림 · chrome 껍데기 · divider 간지 · color 색 · font 서체
# ref : CSS 클래스(themes/workbook.css) 또는 손잡이 키(knobs)
ASSETS = [
    {"id": "box_body", "name": "본문 상자(크림)", "kind": "box", "ref": ".box-body.cream", "knob": "palette.box_body"},
    {"id": "box_sky", "name": "본문 상자(하늘)", "kind": "box", "ref": ".box-body", "knob": "palette.box_sky"},
    {"id": "box_q", "name": "문제 지문 상자", "kind": "box", "ref": ".box-q"},
    {"id": "box_lined", "name": "괘선 상자", "kind": "box", "ref": ".box-lined"},
    {"id": "box_orange", "name": "주황 상자(어법 하단)", "kind": "box", "ref": ".box-orange"},
    {"id": "box_given", "name": "주어진 문장 상자", "kind": "box", "ref": ".box-given"},
    {"id": "box_arr", "name": "배열 상자", "kind": "box", "ref": ".box-arr"},
    {"id": "box_write", "name": "영작 보기 상자", "kind": "box", "ref": ".box-write"},
    {"id": "box_cond", "name": "<조건> 상자", "kind": "box", "ref": ".cond3"},
    {"id": "box_bogi", "name": "<보기> 상자", "kind": "box", "ref": ".bogi3"},
    {"id": "box_bg", "name": "배경 상자", "kind": "box", "ref": ".bg3"},
    {"id": "badge_topic", "name": "주제 배지", "kind": "badge", "ref": ".sum.topic .badge", "knob": "palette.badge_topic"},
    {"id": "badge_title", "name": "제목 배지", "kind": "badge", "ref": ".sum.title .badge", "knob": "palette.badge_title"},
    {"id": "sum_card", "name": "정리 카드", "kind": "box", "ref": ".sum"},
    {"id": "q_head", "name": "발문 줄", "kind": "chrome", "ref": ".q-head"},
    {"id": "choices", "name": "선지 줄", "kind": "chrome", "ref": ".choices"},
    {"id": "sel_mark", "name": "선택 마크 [ⓐ/ⓑ]", "kind": "mark", "ref": ".sel", "knob": "palette.sel"},
    {"id": "blank_line", "name": "빈칸 밑줄", "kind": "mark", "ref": ".blk .bl", "knob": "palette.blank"},
    {"id": "blk_kr", "name": "해석 줄", "kind": "chrome", "ref": ".blk-kr"},
    {"id": "mark_ox", "name": "O|X 마크", "kind": "mark", "ref": ".ox-mark"},
    {"id": "ox_row", "name": "O/X 문항 줄", "kind": "chrome", "ref": ".ox"},
    {"id": "gox_row", "name": "어법 O/X 줄", "kind": "chrome", "ref": ".gox"},
    {"id": "wr_row", "name": "영작 줄", "kind": "chrome", "ref": ".wr"},
    {"id": "albl", "name": "(A)(B)(C) 라벨", "kind": "mark", "ref": ".albl"},
    {"id": "icon_check", "name": "체크 아이콘", "kind": "svg", "ref": "render.svg_chk"},
    {"id": "ansline", "name": "답란 선", "kind": "svg", "ref": "render.svg_ansline"},
    {"id": "ans3", "name": "실전 답란 줄", "kind": "chrome", "ref": ".ans3"},
    {"id": "s3_intro", "name": "세트 안내문 줄", "kind": "chrome", "ref": ".s3-intro"},
    {"id": "pnum_style", "name": "지문 번호 표시", "kind": "chrome", "ref": ".pnum"},
    {"id": "running_head", "name": "러닝헤드(바·kicker·태그·로고·단계 점)", "kind": "chrome", "ref": ".hdr", "knob": "palette.hdr_bg"},
    {"id": "side_tabs", "name": "사이드 탭", "kind": "chrome", "ref": ".tabs"},
    {"id": "folio", "name": "쪽번호", "kind": "chrome", "ref": ".folio"},
    {"id": "divider_art", "name": "간지 그래픽(큰 숫자·진행 점·워드마크)", "kind": "divider", "ref": ".divider"},
    {"id": "color_step", "name": "STEP 주색 3", "kind": "color", "ref": "palette.s1/s2/s3", "knob": "palette.s1"},
    {"id": "color_sel", "name": "선택지 파랑", "kind": "color", "ref": "palette.sel", "knob": "palette.sel"},
    {"id": "color_blank", "name": "빈칸 글자색", "kind": "color", "ref": "palette.blank", "knob": "palette.blank"},
    {"id": "color_pnum", "name": "지문 번호색", "kind": "color", "ref": "palette.pnum", "knob": "palette.pnum"},
    {"id": "font_body", "name": "문항 본문 서체", "kind": "font", "ref": "typeface.body", "knob": "typeface.body"},
    {"id": "font_disp", "name": "발문·지시문 서체", "kind": "font", "ref": "typeface.disp", "knob": "typeface.disp"},
    {"id": "font_pnum", "name": "지문 번호 서체", "kind": "font", "ref": "typeface.pnum", "knob": "typeface.pnum"},
]

BLOCK_BY_ID = {b["id"]: b for b in BLOCKS}
ASSET_BY_ID = {a["id"]: a for a in ASSETS}


def sample_paragraphs(data, block):
    """이 블록의 미리보기용 단락 — 역할이 이어진 첫 자리에서 `max` 개."""
    roles = set(block.get("roles") or [])
    if not roles:
        return None, None
    head = block["roles"][0]
    for st in data.get("steps") or []:
        for g in st.get("groups") or []:
            for key in ("units", "attach"):
                for u in g.get(key) or []:
                    for i, b in enumerate(u):
                        if b.get("role") != head:
                            continue
                        out = []
                        for bb in u[i:]:
                            if bb.get("role") in roles or (bb.get("icon") and "basic" in roles):
                                out.append(bb)
                                if len(out) >= block.get("max", 6):
                                    break
                            elif out:
                                break
                        if out:
                            return out, st
    return None, None
