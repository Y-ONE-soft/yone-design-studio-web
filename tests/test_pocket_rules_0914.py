"""포켓북 사용자 규칙(2026-09-14).

  · 교과서 삽화는 그 교과서 폴더에서만 — 없으면 삽화 없이
  · 암기 TEST 는 넣고 세어 170면을 넘을 때만 뺀다
  · 모의고사·마더텅·올림포스 고1/고2 기출은 지문 바로 뒤, 교과서는 과 끝, 올림포스·리딩파워는 강 끝
"""
from core.render_vivlio.series.pocketbook import PocketbookSeries as S  # noqa
from core.render_vivlio.series.pocketbook import data as D, memtest as MT


def _tree(tmp, files):
    for f in files:
        p = tmp / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return D.illust_index([str(tmp)])


TB = ["교과서/공통영어2 능률(민)/공영2 능률(민) 1과 01.png",
      "교과서/영어독해와작문 비상(황)/3과 MR1.png"]


def test_textbook_other_publisher_gets_no_illust(tmp_path):
    idx = _tree(tmp_path, TB)
    row = {"label": "1과 본문1", "category": "교과서 1과",
           "source": {"file": "배재1_분석본01(능률오1,2과)_내지.idml"}}
    assert D.illust_for(row, idx) is None
    row = {"label": "3과 본문 1", "category": "교과서 3과",
           "source": {"file": "배재2_분석본01(YBM박1,2,3과)_내지.idml"}}
    assert D.illust_for(row, idx) is None


def test_textbook_same_publisher_keeps_illust(tmp_path):
    idx = _tree(tmp_path, TB)
    row = {"label": "1과 본문1", "category": "교과서 1과",
           "source": {"file": "창현1_분석본01(능률민1,2과)_내지.idml"}}
    assert D.illust_for(row, idx).endswith("1과 01.png")
    row = {"label": "3과 MR1 Brain Insights", "category": "교과서 3과",
           "source": {"file": "광문2_분석본04(비상황3과)_내지.idml"}}
    assert D.illust_for(row, idx).endswith("3과 MR1.png")


def test_after_passage_books():
    f = lambda src, cat="", rank=1: MT.after_passage(
        {"source": {"file": src}, "category": cat}, rank)
    assert f("", "고2 26년 6월 모의고사", 2)
    assert f("한영1_분석본02(마더텅13강1)_내지.idml", "13강")
    assert f("상일2_분석본02(올포기출11강)_내지.idml", "11강")
    assert not f("광문1_분석본03(올포1,2강)_내지.idml", "올림포스 1강")
    assert not f("세종1_분석본02(비상홍2과,리딩파워1,2,3강)_내지.idml", "리딩파워 1강")
    assert not f("배재1_분석본01(능률오1,2과)_내지.idml", "교과서 1과", 1)


def _book(n_pas, n_mt):
    rows = []
    for i in range(n_pas):
        rows.append({"kind": "passage", "key": str(i)})
    rows += [{"kind": "memtest", "key": "x"}] * n_mt
    return rows


def test_memtest_kept_up_to_170():
    # 지문 42개 = 84면 + 암기 TEST 84면 + 앞뒤 2면 = 170 → 넣는다
    rows = _book(42, 84)
    got = S._drop_memtest_if_thick(rows, [], {}, lambda *_: None)
    assert len(got) == len(rows)


def test_memtest_dropped_over_170():
    rows = _book(43, 86)                          # 86 + 86 + 2 = 174
    got = S._drop_memtest_if_thick(rows, [], {}, lambda *_: None)
    assert not any(r["kind"] == "memtest" for r in got)


def test_memtest_rows_placed_by_book():
    entries_text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma"
    def row(key, cat, rank, src=""):
        return {"kind": "passage", "key": key, "category": cat, "_rank": rank,
                "source": {"file": src}, "passage": entries_text + " " + key * 3}
    rows = [row("t1", "교과서 1과", 1), row("t2", "교과서 1과", 1),
            row("o1", "올림포스 1강", 1, "x_분석본03(올포1,2강)_내지.idml"),
            row("o2", "올림포스 1강", 1, "x_분석본03(올포1,2강)_내지.idml"),
            row("m1", "13강", 1, "x_분석본02(마더텅13강1)_내지.idml"),
            row("m2", "13강", 1, "x_분석본02(마더텅13강1)_내지.idml"),
            row("k1", "모의고사", 2), row("k2", "모의고사", 2)]
    import core.render_vivlio.series.pocketbook.memtest as M
    orig = (M.read, M.find, M.render, M.cut)
    M.read = lambda *a, **k: [{"x": 1}]
    M.find = lambda entries, text: {"parts": [(text, False)]}
    M.cut = lambda parts, want: parts
    M.render = lambda parts, no: ("body", no + 1)
    try:
        out = M.attach(rows, ["src"])
    finally:
        M.read, M.find, M.render, M.cut = orig
    seq = ["%s%s" % ("T" if r["kind"] == "memtest" else "", r["key"])
           for r in out if r["kind"] == "passage" or not r.get("answer")]
    assert seq == ["t1", "t2", "Tt1", "Tt2", "o1", "o2", "To1", "To2",
                   "m1", "Tm1", "m2", "Tm2", "k1", "Tk1", "k2", "Tk2"], seq
