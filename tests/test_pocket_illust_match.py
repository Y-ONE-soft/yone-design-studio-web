"""삽화 찾기 — 광문2 연구원 검수(2026-09-14)에서 틀렸던 자리.

  · 분석본 링크 그림을 삽화정리보다 먼저 써서 수특 Light 지문이 엉뚱한 그림
  · `3과 MR1 Brain Insights` — MR 번호를 못 읽어 삽화 없음
  · `4강 05~06` — 범위 파일(`4강 05~06.png`)을 못 찾음
  · 기존 포켓북에서 온 모의고사 행은 pno 가 비어 번호로 못 찾음
"""
import os

from core.render_vivlio.series.pocketbook import data as D


def _tree(tmp, files):
    for f in files:
        p = tmp / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return D.illust_index([str(tmp)])


def test_textbook_mr_number(tmp_path):
    idx = _tree(tmp_path, ["교과서/영어독해와작문 비상(황)/3과 MR1.png",
                           "교과서/영어독해와작문 비상(황)/3과 MR2.png"])
    got = D.illust_for({"label": "3과 MR1 Brain Insights", "unit": "교과서 3과"}, idx)
    assert got and got.endswith("3과 MR1.png")


def test_lecture_range_file(tmp_path):
    idx = _tree(tmp_path, ["ebs/수능특강 Light 영어독해연습(개정판)/4강 04.png",
                           "ebs/수능특강 Light 영어독해연습(개정판)/4강 05~06.png"])
    got = D.illust_for({"label": "4강 05~06", "unit": "수능특강 4강"}, idx)
    assert got and got.endswith("4강 05~06.png")


def test_light_01_not_other_books_analysis(tmp_path):
    idx = _tree(tmp_path, ["ebs/수능특강 Light 영어독해연습(개정판)/1강 01.png",
                           "고1/올림포스 영어독해 기본2/1강 분석.png"])
    got = D.illust_for({"label": "1강 01", "unit": "수능특강 1강"}, idx)
    assert got and "Light" in got


def test_pno_from_six_digit_label():
    assert D._pno_of_label({"label": "260620"}) == "260620"
    assert D._pno_of_label({"label": "260641~42"}) == "260641"
    assert D._pno_of_label({"label": "1강 02"}) == ""


def test_folder_beats_analysis_link(tmp_path):
    _tree(tmp_path, ["ebs/수능특강 Light 영어독해연습(개정판)/1강 02.png", "links/wrong.png"])
    wrong = str(tmp_path / "links/wrong.png")
    item = {"label": "1강 02", "unit": "수능특강 1강", "links": [wrong],
            "passage": [{"style": "본문", "runs": [{"t": "Hello."}]}]}
    rows = D.prepare([item], str(tmp_path / "build"), illust_dirs=[str(tmp_path)])
    src = rows[0]["illust"]
    assert src, "삽화가 안 붙었다"
    # 복사된 파일이 폴더 그림(1강 02)인지 — 크기로는 못 가르니 복사 원본 기록을 본다
    assert D.illust_for(item, D.illust_index([str(tmp_path)])).endswith("1강 02.png")
