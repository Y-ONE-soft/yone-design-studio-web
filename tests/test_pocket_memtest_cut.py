"""암기 TEST 원고 자르기 — 낱말 가운데서 잘리던 것(광문2 22·24·30·32번·MR6, 배재1 1과 본문2).

`letters()` 는 숫자를 버리는데 글자 자리표는 숫자까지 세서, 원고에 숫자(빈칸
번호 `213[`, `175`)가 있을 때마다 끝이 한 칸씩 앞당겨졌다.
"""
from core.render_vivlio.series.pocketbook import memtest as MT


def test_numbers_in_blanks_do_not_shift_the_end():
    parts = [("1 The ", False), ("largest", True), (" U.S. lotteries are on the order of one in 175 ", False),
             ("million", True), (".", False), (" 2 Another passage begins here and goes on.", False)]
    want = "The largest U.S. lotteries are on the order of one in 175 million."
    got = MT.plain(MT.cut(parts, want))
    assert got.rstrip().endswith("175 million."), got


def test_numbered_blank_words_keep_their_tail():
    parts = [("It is a sign of quality and 531[", False), ("reinforces", True),
             ("] a customer’s confidence in the ", False), ("company", True), (".", False),
             (" Next text that should be dropped.", False)]
    want = "It is a sign of quality and reinforces a customer's confidence in the company."
    got = MT.plain(MT.cut(parts, want))
    assert got.rstrip().endswith("company."), got
    assert "Next text" not in got
