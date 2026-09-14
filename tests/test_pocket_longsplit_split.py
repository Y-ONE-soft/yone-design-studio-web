"""장문(43~45번)은 두 면에 이어 싣는다 — 긴 지문 나누기가 또 나눠 4면이 되던 것(광문2 26년 6월)."""
from core.render_vivlio.series.pocketbook import longsplit as LS


def _item(n_chars, split):
    sent = "Anna wrote a cheerful letter to Mrs. Pike about her garden. "
    text = (sent * (n_chars // len(sent) + 1))[:n_chars]
    return {"label": "260643~45", "split": split,
            "passage": [{"style": "본문", "runs": [{"t": text}]}],
            "translation": [{"style": "한글", "runs": [{"t": "해석. " * 100}]}]}


def test_long_passage_with_split_flag_stays_one_piece():
    assert len(LS.split_all([_item(2600, True)])) == 1


def test_plain_long_passage_still_splits():
    assert len(LS.split_all([_item(2600, False)])) == 2


def test_split_passage_beyond_two_pages_still_splits():
    assert len(LS.split_all([_item(4000, True)])) == 2
