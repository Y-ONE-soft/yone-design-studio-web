"""모의고사 도표 짤지문(25번)에 도표 그림을 넣는다(배재2 240925·250925, 사용자 지적)."""
from core.render_vivlio.verify import Report
from core.render_vivlio.series.pocketbook import data as D, checks as K


def _row(pno, short, label=None):
    return {"kind": "passage", "pno": pno, "label": label or pno, "grade": "고2",
            "short": short, "passage": [], "category": "고2 24년 9월 모의고사"}


def test_short_chart_gets_picture_without_credit_crop(tmp_path):
    charts = tmp_path / "_도표"
    (charts / "고2" / "24년 9월").mkdir(parents=True)
    (charts / "고2" / "24년 9월" / "25.png").write_bytes(b"\x89PNG fake")
    build = tmp_path / "build"
    rows = D.prepare([_row("240925", True), _row("240926", True)], str(build),
                     illust_dirs=[], grade="고2", chart_dirs=[str(charts)])
    assert rows[0]["illust"] and rows[0]["chart"] and rows[0]["illust_src"].endswith("25.png")
    assert (build / rows[0]["illust"]).read_bytes() == b"\x89PNG fake"
    assert not rows[1]["illust"] and not rows[1]["chart"]


def test_full_passage_does_not_use_chart_dir(tmp_path):
    charts = tmp_path / "_도표"
    (charts / "고2" / "24년 9월").mkdir(parents=True)
    (charts / "고2" / "24년 9월" / "29.png").write_bytes(b"x")
    rows = D.prepare([_row("240929", False)], str(tmp_path / "b"), illust_dirs=[],
                     grade="고2", chart_dirs=[str(charts)])
    assert not rows[0]["illust"]


def test_chart_missing_warns_only_for_chart_numbers():
    rows = [dict(_row("240925", True), illust=None), dict(_row("240918", True), illust=None),
            dict(_row("250925", True), illust="img/p1.png")]
    rep = Report()
    K.chart_missing(rows, rep, lambda *_: None)
    assert len(rep.warns) == 1 and "240925" in rep.warns[0] and "250925" not in rep.warns[0]
