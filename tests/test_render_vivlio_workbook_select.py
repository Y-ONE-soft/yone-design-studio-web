"""워크북 `select` 계약 — 오프라인(교재 폴더도 PDF 도 필요 없다).

학교 프리셋이 「무엇을 빼고 몇 문항만 남길지」를 여기에 적는다. 그래서 이 규칙이
조용히 바뀌면 **학교마다 다른 책이 나온다**. 사람 눈으로는 못 잡으므로 못박는다.

  · exclude  뺄 목록 (프리셋)
  · include  이 책에서만 되돌리기 (교재 개별 예외) — exclude 를 이긴다
  · limits   스텝마다 남길 지문 수 — 전 스텝 공통 passages 와 달리 그 스텝에만
  · 아무것도 안 주면 **원고 그대로** 나와야 한다
"""
from core.render_vivlio.series.workbook.data import apply_select


def _steps():
    """지문 4개짜리 책 — 라벨 있는 스텝과 라벨 없는 스텝을 섞는다."""
    lab = [{"label": "실전%02d" % i, "n": i} for i in range(1, 5)]
    nolab = [{"label": None, "n": i} for i in range(1, 5)]
    return [
        {"key": "step1_a1", "groups": [dict(g) for g in lab]},
        {"key": "step1_c2", "groups": [dict(g) for g in nolab]},   # 빈칸 어휘
        {"key": "step3", "groups": [{"label": "본문", "n": 0}]},   # 지문 단위 아님
    ]


def _keys(out):
    return [s["key"] for s in out]


def _ns(out, key):
    return [g["n"] for s in out if s["key"] == key for g in s["groups"]]


def test_아무것도_안_주면_그대로():
    out = apply_select(_steps(), None, log=lambda *a: None)
    assert _keys(out) == ["step1_a1", "step1_c2", "step3"]
    assert _ns(out, "step1_c2") == [1, 2, 3, 4]


def test_exclude_는_그_스텝만_뺀다():
    out = apply_select(_steps(), {"exclude": ["step1_c2"]}, log=lambda *a: None)
    assert _keys(out) == ["step1_a1", "step3"]


def test_원고에_없는_키를_빼도_그냥_넘어간다():
    out = apply_select(_steps(), {"exclude": ["step9_z9"]}, log=lambda *a: None)
    assert _keys(out) == ["step1_a1", "step1_c2", "step3"]


def test_include_가_exclude_를_이긴다():
    """「이 학교는 빈칸 어휘를 빼지만 이 부교재는 넣어주세요」"""
    out = apply_select(_steps(),
                       {"exclude": ["step1_c2"], "include": ["step1_c2"]},
                       log=lambda *a: None)
    assert "step1_c2" in _keys(out)


def test_limits_는_그_스텝의_문항_수만_줄인다():
    """빈칸 어휘는 두되 앞에서 2개만 — 다른 스텝은 그대로."""
    out = apply_select(_steps(), {"limits": {"step1_c2": {"passages": 2}}},
                       log=lambda *a: None)
    assert _ns(out, "step1_c2") == [1, 2]
    assert _ns(out, "step1_a1") == [1, 2, 3, 4]


def test_limits_에_순번_목록도_준다():
    out = apply_select(_steps(), {"limits": {"step1_c2": {"passages": [1, 3]}}},
                       log=lambda *a: None)
    assert _ns(out, "step1_c2") == [1, 3]


def test_limits_는_지문이_아닌_묶음을_안_건드린다():
    """실전 문제처럼 통째 한 묶음인 것은 개수 제한에 걸리지 않는다."""
    out = apply_select(_steps(), {"limits": {"step3": {"passages": 0}}},
                       log=lambda *a: None)
    assert _ns(out, "step3") == [0]


def test_기존_steps_넣을_목록은_그대로_동작한다():
    out = apply_select(_steps(), {"steps": ["step1_a1", "step3"]},
                       log=lambda *a: None)
    assert _keys(out) == ["step1_a1", "step3"]


def test_전_스텝_공통_passages_는_그대로_동작한다():
    out = apply_select(_steps(), {"passages": [2, 4]}, log=lambda *a: None)
    assert _ns(out, "step1_a1") == [2, 4]
    assert _ns(out, "step1_c2") == [2, 4]


def test_order_는_적은_것을_앞으로_보낸다():
    """학교마다 푸는 차례가 다를 수 있다."""
    out = apply_select(_steps(), {"order": ["step3", "step1_c2"]},
                       log=lambda *a: None)
    assert _keys(out) == ["step3", "step1_c2", "step1_a1"]


def test_order_에_없는_것은_뒤에_원래_순서대로():
    out = apply_select(_steps(), {"order": ["step1_c2"]}, log=lambda *a: None)
    assert _keys(out) == ["step1_c2", "step1_a1", "step3"]


def test_order_와_exclude_를_같이_쓴다():
    out = apply_select(_steps(), {"order": ["step3"], "exclude": ["step1_a1"]},
                       log=lambda *a: None)
    assert _keys(out) == ["step3", "step1_c2"]
