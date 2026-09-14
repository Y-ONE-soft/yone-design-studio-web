"""포켓북 G-P15~G-P17 — 광문2 연구원 검수(2026-09-14)에서 게이트를 빠져나간 결함.

  G-P15  암기 TEST 끝 잘림(`comp|any`, `17|5 million`)
  G-P16  삽화가 다른 책·다른 교과서 것(수특 Light 에 고3 수특, YBM박 에 비상(황))
  G-P17  드라이브 분석본 .indd 를 IDML 로 안 뽑아 지문이 조용히 빠짐
"""
import os
import time

from core.render_vivlio.verify import Report
from core.render_vivlio.series.pocketbook import checks as K


def _mt_rows(passage, memtest, key="230330"):
    return [{"kind": "passage", "key": key, "passage_runs": [{"t": passage}]},
            {"kind": "memtest", "answer": False, "key": key, "runs": [{"t": memtest}]},
            {"kind": "memtest", "answer": True, "key": key, "runs": [{"t": passage}]}]


P30 = ("For instance, the high price of these products is often perceived as a sign "
       "of quality and reinforces a customer's confidence in the company.")


def test_memtest_cut_mid_word_fails():
    rep, log = Report(), []
    K.memtest_tail(_mt_rows(P30, "is often 530[perceived] as a sign of quality and "
                                 "531[reinforces] a customer’s confidence in the comp"),
                   rep, log.append)
    assert rep.fails and "230330" in rep.fails[0]


def test_memtest_cut_far_before_end_still_fails():
    # 빈칸 번호가 세 자리면 수십 글자 앞에서 멈춘다 — 거리로 봐주면 안 된다
    rep = Report()
    K.memtest_tail(_mt_rows(P30, "For instance, the 101[high] price of these products"),
                   rep, lambda *_: None)
    assert rep.fails


def test_memtest_complete_passes():
    rep, log = Report(), []
    K.memtest_tail(_mt_rows(P30, "For instance, the 101[high] price of these products is "
                                 "often perceived as a sign of quality and 102[reinforces] "
                                 "a customer’s confidence in the 103[company]."),
                   rep, log.append)
    assert not rep.fails and not rep.warns


def test_memtest_other_edition_only_warns():
    rep = Report()
    K.memtest_tail(_mt_rows(P30, "An entirely different ending written for another edition."),
                   rep, lambda *_: None)
    assert not rep.fails and rep.warns


LIGHT = {"source": {"file": "광문2_분석본01(수특라이트영독1,2강)_내지.idml"}}


def test_illust_light_book_given_high3_suneung():
    r = dict(LIGHT, label="1강 02", category="수능특강 1강")
    assert "Light" in K.illust_mismatch(r, "고3/2027 수능특강/1강 2번.jpeg")


def test_illust_light_book_given_olympos_analysis():
    r = dict(LIGHT, label="1강 01", category="수능특강 1강")
    assert K.illust_mismatch(r, "고1/올림포스 영어독해 기본2/1강 분석.png")


def test_illust_light_right_file_passes():
    r = dict(LIGHT, label="4강 05~06", category="수능특강 4강")
    assert K.illust_mismatch(r, "ebs/수능특강 Light 영어독해연습(개정판)/4강 05~06.png") == ""
    assert K.illust_mismatch(r, "ebs/수능특강 Light 영어독해연습(개정판)/4강 04.png")


def test_illust_textbook_other_publisher():
    r = {"label": "3과 본문 1", "category": "교과서 3과",
         "source": {"file": "배재2_분석본01(YBM박1,2,3과)_내지.idml"}}
    assert "YBM박" in K.illust_mismatch(r, "교과서/영어독해와작문 비상(황)/3과 MR1.png")
    assert "YBM박" in K.illust_mismatch(r, "교과서/공통영어2 능률(민)/공영2 능률(민) 3과 01.png")


def test_illust_textbook_mr_passes():
    r = {"label": "3과 MR1 Brain Insights", "category": "교과서 3과",
         "source": {"file": "광문2_분석본04(비상황3과)_내지.idml"}}
    assert K.illust_mismatch(r, "교과서/영어독해와작문 비상(황)/3과 MR1.png") == ""


def test_illust_mock_wrong_round_or_number():
    r = {"label": "260620", "no": "", "grade": "고2"}
    assert K.illust_mismatch(r, "고2/26년 6월/20.jpg") == ""
    assert K.illust_mismatch(r, "고2/26년 6월/21.jpg")
    assert K.illust_mismatch(r, "고2/25년 6월/20.jpg")
    assert K.illust_mismatch(r, "고1/26년 6월/20.jpg")
    assert K.illust_mismatch({"label": "260641~42", "grade": "고2"}, "고2/26년 6월(수정완)/41-42.jpg") == ""


def test_illust_outside_folder_warns(tmp_path):
    base = tmp_path / "삽화정리"
    base.mkdir()
    rows = [{"kind": "passage", "label": "260620", "grade": "고2", "illust": "img/p0.jpg",
             "illust_src": str(tmp_path / "옛책" / "Links" / "20.jpg")}]
    rep = Report()
    K.illust_names(rows, [str(base)], rep, lambda *_: None)
    assert not rep.fails and rep.warns


def _touch(p, mtime):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    os.utime(p, (mtime, mtime))


def test_analysis_indd_without_idml(tmp_path):
    now = time.time()
    loc, drv = tmp_path / "local", tmp_path / "drive"
    for i, nm in enumerate(["수특라이트영독1,2강", "비상황3과"]):
        _touch(loc / ("광문2_분석본0%d(%s)_내지.idml" % (i + 1, nm)), now)
        _touch(drv / ("광문2_분석본0%d(%s)_내지.indd" % (i + 1, nm)), now - 10)
    _touch(drv / "광문2_분석본05(26년6월)_내지.indd", now)
    _touch(drv / ".광문2_분석본05(26년6월)_내지.bak-pre.indd", now)
    _touch(drv / "고2 26년 6월 분석본(짤지 포함).indd", now)
    missing, stale = K.compare_sources([str(loc)], [str(drv)])
    assert missing == ["광문2_분석본05(26년6월)_내지.indd"] and stale == []
    missing, _ = K.compare_sources([str(loc)], [str(drv)], skip=["분석본05"])
    assert missing == []


def test_analysis_indd_newer_than_idml(tmp_path):
    now = time.time()
    _touch(tmp_path / "l" / "배재2_분석본03(25년9월)_내지.idml", now - 5 * 86400)
    _touch(tmp_path / "d" / "배재2_분석본03(25년9월)_내지.indd", now)
    missing, stale = K.compare_sources([str(tmp_path / "l")], [str(tmp_path / "d")])
    assert missing == [] and stale == ["배재2_분석본03(25년9월)_내지.indd"]


def test_drive_dir_of():
    d = K.drive_dir_of("/x/조판/교재/포켓북/_idml/analysis/고1,고2(공통)/26-2-중간/광문2")
    assert d.endswith("인디자인 파일/분석본/고1,고2(공통)/26-2-중간/광문2")
