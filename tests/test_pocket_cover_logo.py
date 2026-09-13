"""앞 간지 로고 — 만든 연구소는 **학교마다 다르다**(사용자 지시 2026-09-13).

예전에는 `세희영어연구소 · 각인Books` 가 코드에 박혀 있어 배재 책에도 그대로
찍혔다. 광문 = 세희영어연구소 · 배재 = 윤기영어연구소 · 나머지는 각인Books 만.
"""
from core.render_vivlio.series.pocketbook import cover


def test_gwangmun_keeps_sehee():
    assert cover.logo_text("광문1") == "세희영어연구소 · 각인Books"
    assert cover.logo_text("광문2") == "세희영어연구소 · 각인Books"


def test_baejae_is_yungi():
    assert cover.logo_text("배재1") == "윤기영어연구소 · 각인Books"
    assert cover.logo_text("배재2") == "윤기영어연구소 · 각인Books"


def test_other_schools_are_gakin_only():
    for s in ("명일2", "강동1", "한영2", "상일1", "세종1", ""):
        assert cover.logo_text(s) == "각인Books", s


def test_first_page_prints_it():
    assert '<div class="logo">윤기영어연구소 · 각인Books</div>' in \
        cover.first_page("배재1", "2학기 중간고사")
    assert '<div class="logo">각인Books</div>' in \
        cover.first_page("명일2", "2학기 중간고사")
