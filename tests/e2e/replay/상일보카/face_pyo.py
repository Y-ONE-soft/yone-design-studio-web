"""상일보카 — 4 표제어 · 첫 펼침면(견본 4 · 5쪽) · 5 표제어 · 본문 펼침면(견본 6 · 7쪽).
쪽 틀은 common.py(구간 공통 — 첫 펼침면 · 본문 펼침면). 단어 항목 흐름은 차례로 더한다."""
from common import *                                                    # noqa


def pyo_first(lp=4):
    st = pg_new(lp, f"④ 표제어 · 첫 펼침면 — 원본 {lp}쪽(왼쪽)", name="표제어 · 첫 펼침면")
    st += frame_first_left(lp)
    st += done("표제어 · 첫 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"④ 표제어 · 첫 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_first_right(lp + 1)
    st += done("표제어 · 첫 펼침면 오른쪽", f"p{lp + 1}.png")
    return st


def pyo_body(lp=6):
    st = pg_new(lp, f"⑤ 표제어 · 본문 펼침면 — 원본 {lp}쪽(왼쪽)", name="표제어 · 본문 펼침면")
    st += frame_body_left(lp)
    st += done("표제어 · 본문 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑤ 표제어 · 본문 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_body_right(lp + 1)
    st += done("표제어 · 본문 펼침면 오른쪽", f"p{lp + 1}.png")
    return st


FACES = {4: (pyo_first,), 5: (pyo_body,)}
