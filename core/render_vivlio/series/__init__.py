"""계열 레지스트리 — 이름 → Series 인스턴스.

새 계열을 붙일 때 손대는 곳은 여기 한 줄뿐이다.
"""
_CACHE = {}

_FACTORIES = {}


def register(name, factory):
    _FACTORIES[name] = factory


def get(name):
    if name not in _CACHE:
        if name not in _FACTORIES:
            raise KeyError(f"등록되지 않은 계열: {name} "
                           f"(등록됨: {', '.join(sorted(_FACTORIES))})")
        _CACHE[name] = _FACTORIES[name]()
    return _CACHE[name]


def names():
    return sorted(_FACTORIES)


def _vocabook():
    from core.render_vivlio.series.vocabook import VocabookSeries
    return VocabookSeries()


def _vocaunit():
    from core.render_vivlio.series.vocaunit import VocaunitSeries
    return VocaunitSeries()


def _special():
    from core.render_vivlio.series.special import SpecialSeries
    return SpecialSeries()


def _blackbook():
    from core.render_vivlio.series.blackbook import BlackbookSeries
    return BlackbookSeries()


def _whitebook():
    from core.render_vivlio.series.whitebook import WhitebookSeries
    return WhitebookSeries()


def _final():
    from core.render_vivlio.series.final import FinalSeries
    return FinalSeries()


def _middle():
    from core.render_vivlio.series.middle import MiddleSeries
    return MiddleSeries()


register("vocabook", _vocabook)
register("vocaunit", _vocaunit)
register("blackbook", _blackbook)
register("special", _special)
register("middle", _middle)
register("whitebook", _whitebook)
register("final", _final)
