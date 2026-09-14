"""`fixes.json` — 분석본 원고 자체의 오타·누락을 **라벨로** 고친다(광문2 검수 2026-09-14)."""
import json

from core.render_vivlio.series.pocketbook import _apply_fixes


class _Cfg:
    def __init__(self, root):
        self.root = root

    def path(self, name):
        return str(self.root / name)


def _rows():
    return [{"label": "6강 04", "passage": [{"style": "본문", "runs": [
                {"t": "it is generally agreed that under standing is something"}]}],
             "translation": [{"style": "한글", "runs": [{"t": "옛 해석"}]}]},
            {"label": "6강 05~06", "passage": [], "translation": [
                {"style": "한글", "runs": [{"t": "셋째 문장이 빠진 해석"}]}]}]


def test_passage_replace_and_translation_swap(tmp_path):
    (tmp_path / "fixes.json").write_text(json.dumps({
        "6강 04": {"passage": [["under standing", "understanding"]]},
        "6강 05~06": {"translation": "새 해석 전체"}}, ensure_ascii=False), encoding="utf-8")
    rows, logs = _rows(), []
    _apply_fixes(_Cfg(tmp_path), rows, logs.append)
    assert "understanding is something" in rows[0]["passage"][0]["runs"][0]["t"]
    assert rows[1]["translation"][0]["runs"][0]["t"] == "새 해석 전체"
    assert any("2곳" in l for l in logs)


def test_missing_target_is_reported(tmp_path):
    (tmp_path / "fixes.json").write_text(json.dumps({
        "6강 04": {"passage": [["no such text", "x"]]},
        "9강 99": {"translation": "x"}}), encoding="utf-8")
    logs = []
    _apply_fixes(_Cfg(tmp_path), _rows(), logs.append)
    assert any("못 건 것 2개" in l for l in logs)


def test_no_file_is_silent(tmp_path):
    logs = []
    _apply_fixes(_Cfg(tmp_path), _rows(), logs.append)
    assert logs == []
