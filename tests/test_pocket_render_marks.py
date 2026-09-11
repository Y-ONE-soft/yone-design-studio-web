"""포켓북 왼쪽 면 표시 — 물결 밑줄 · 여러 낱말 주석. 실제로 틀렸던 자리를 못 박는다.

  · 물결 SVG 를 데이터 URI 에 넣으면서 `stroke='#EE4C9B'` 를 그대로 적어
    `#` 에서 URL 이 끊겼다 → 물결이 **어느 책에서도 한 번도 안 찍혔다**.
  · 주석 낱말(`.w`)은 inline-block 이라 물결을 거기 칠하면 주석 줄을 긋는다.
  · `no matter how` 에 걸린 `부접` 이 낱말마다 찍혀 세 번 나왔다(광문2 40곳).
"""
import re

from core.render_vivlio.series.pocketbook import render as R
from core.render_vivlio.series.pocketbook import theme as T


def _css():
    src = open(T.__file__, encoding="utf-8").read()
    return src


def test_wave_svg_escapes_hash():
    src = _css()
    assert "stroke='__wave_url__'" in src
    assert "stroke='__wave__'" not in src
    assert '"wave_url"' in src and '.replace("#", "%23")' in src


def test_multiword_ruby_prints_once():
    R.ruby_reset()
    runs = [{"t": "won't yield "},
            {"t": "no matter how", "ruby": "부접", "slot": "dn"},
            {"t": " damning, and"},
            {"t": " in which", "ruby": "전치사+관계사", "slot": "dn"},
            {"t": " they"}]
    h = R.runs_html(runs)
    assert h.count("부접") == 1 and h.count("전치사+관계사") == 1
    assert "no matter how<i" in h
    assert R.ruby_count() == 2


def test_single_word_ruby_html_unchanged():
    R.ruby_reset()
    assert (R._run_html({"t": "researcher", "ruby": "S", "slot": "dn"})
            == '<span class="w">researcher<i class="dn">S</i></span>')


def test_wave_on_ruby_word_wraps_text_only():
    R.ruby_reset()
    h = R._run_html({"t": "confirming", "mark": "blue", "ruby": "동명사1",
                     "slot": "dn", "wave": True})
    assert h == ('<span class="w blue"><span class="wave">confirming</span>'
                 '<i class="dn">동명사1</i></span>')
    h2 = R._run_html({"t": "pick", "mark": "wave", "ruby": "V1", "slot": "dn"})
    assert re.search(r'class="w"><span class="wave">pick</span>', h2)
    assert R._run_html({"t": "to", "mark": "wave"}) == '<span class="wave">to</span>'
