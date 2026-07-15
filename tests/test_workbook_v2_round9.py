"""W19 품질 루프 9라운드 가드 — 신규 선정 2종:
c19 EBS 작업/Reading Power 유형편(기본)/Unit 22 Example, 1~3 워크북
    → workbook_supp_v2 + school=세종1 (학교 전용 내지 lookup 첫 실기)
c20 모의고사 작업/고2/고2 25년 3월 워크북 폴더 → workbook_v2 (본가,
    U+F003B 보유 실증 폴더 — W14 (2) mockexam 잠복의 워크북 경로 확인)

결함 재현→수리 고정:
  D1 (c19) 세종 내지(42p)에는 '내용 종합'(step1_b2) 섹션이 없음 — 마커/
     페이지 58 모두 부재(실물 probe + v1 실물 세종1_워크북리딩파워20강
     42p 동일). 미지원 매핑 없이 렌더하면 '스토리 못 찾음' 후 116단어
     침묵 유실(1차 조판 실측, verify ok=False) → supp 템플릿별 스텝
     카탈로그(_SEJONG_STEP_MAP, base _plan_ctx 훅 컨텍스트) → unsupported
     보고.
  D2 (c19) 꼬리 공백 전용 overset — 플랜 꼬리 빈 단락(\\r)이 마지막
     프레임을 정확히 채운 스토리에서 overset 잔존 (확장 페이지가 공백
     전용으로 생겼다가 page_cleanup 스레드 절단/삭제로 재발하는 순환)
     → 실행기 trimWsOverset (배치 밖 공백만 제거, 본문 무손실).
  D3 (c20) 선지 자동번호가 재인쇄 지문에 ① 중복 부여 — ※ 다중 문항
     아이템의 도표/불일치류 발문 뒤 재인쇄 지문(inline ①~⑤)이
     passage_above 우회로 선지 후보가 되어 '①The graph … ① In Germany …'
     기형 번호 + 선지 스타일 인쇄 (v1 실물은 지문 스타일·무접두) →
     파서 prepend 루프에 inline 번호 통단락 가드 + 게이트 G21 [원문자중복].
"""
import json
import os

from engines.workbook.parser import _add_step3_choice_numbers
from engines.workbook_v2.gate import inspect_workbook_finish

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_C = "STEP 03 > S_선지 올림포스"


def _fixture(name):
    path = os.path.join(TESTS_DIR, "fixtures", "w19_defect_dumps", name)
    return json.load(open(path, encoding="utf-8"))


def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"],
                         "b": [0, 0]}],
            "stale_pages": []}


# ── D3 게이트: G21 원문자 ① 중복 오염 ───────────────────────────────────────

_POLLUTED = ("①The graph above shows the percentages of the primary "
             "reasons for E-bike purchase in five European countries in "
             "2022. ① In Germany, recreational purpose accounted for the "
             "highest percentage of reasons, while in the Netherlands "
             "commuting was ranked first among the five countries. "
             "② The share of sporting activity was below twenty percent "
             "in all five countries.")


def test_gate_g21_detects_duplicated_circled_prefix():
    d = _dump([{"t": _POLLUTED, "s": _ST_C}])
    r = inspect_workbook_finish({}, {}, d)
    assert any("원문자중복" in c for c in r["critical"])
    assert r["stats"]["choice_polluted_passages"] == 1


def test_gate_g21_fires_on_c20_pre_fix_dump_excerpt():
    # 수리 전 실덤프 발췌(고2_25년_03월_전체(C)_v2_2.indd) — 검출 근거 보존
    r = inspect_workbook_finish({}, {}, _fixture(
        "c20_dup_circled_pre_fix.json"))
    assert any("원문자중복" in c for c in r["critical"])


def test_gate_g21_passes_typed_inline_numbering():
    # 원고에 타이핑된 inline 번호 지문 — ①이 1회뿐 (c19 8번/0a5da924 실측)
    typed = ("①Families don’t grow strong unless parents invest precious "
             "time in them. In New Man, ②Gary Oliver writes about a "
             "difficult decision made by professional baseball player "
             "Tim Burke concerning his family. ③Burke had always dreamed "
             "of playing professional baseball.")
    spaced = ("① Remember how you learned to drive or cook? You practiced "
              "with care. ② Talking about what something smells like is "
              "hard. ③ Even so you managed it in the end with practice "
              "and patience over a long period of time indeed.")
    for t in (typed, spaced):
        d = _dump([{"t": t, "s": _ST_C}])
        r = inspect_workbook_finish({}, {}, d)
        assert not any("원문자중복" in c for c in r["critical"]), t[:20]


def test_gate_g21_ignores_short_choice_lines():
    d = _dump([{"t": "① 2개   ② 3개   ③ 4개   ④ 5개   ⑤ 6개", "s": _ST_C}])
    r = inspect_workbook_finish({}, {}, d)
    assert not any("원문자중복" in c for c in r["critical"])


# ── D3 파서: prepend 루프의 inline 번호 통단락 가드 ─────────────────────────

_INLINE_PASSAGE = ("The graph above shows the percentages of the primary "
                   "reasons for E-bike purchase in five European countries "
                   "in 2022. ① In Germany, recreational purpose accounted "
                   "for the highest percentage. ② The share of sporting "
                   "activity was below twenty percent in all countries. "
                   "③ Commuting to work was ranked first in the "
                   "Netherlands. ④ France showed the smallest gap. "
                   "⑤ Recreational purpose was ranked lowest in Italy.")


def _p(text, **kw):
    d = {"text": text, "runs": [{"t": text, "ul": False}]}
    d.update(kw)
    return d


def test_parser_no_prepend_on_inline_numbered_passage():
    # c20 25번 재현: ※ 아이템(passage_above=True) + 마지막 5지선다 발문 뒤
    # 재인쇄 지문(inline ①~⑤) — 수리 전에는 ①이 prepend됐다.
    paras = [
        _p("※ 다음 글을 읽고 물음에 답하시오. "),
        _p("[202503H2_25도표_변형]"),
        _p(_INLINE_PASSAGE),
        _p("다음 도표의 내용과 일치하지 않는 것은?"),
        _p("[202503H2_25도표_변형]"),
        _p(_INLINE_PASSAGE),
    ]
    out = _add_step3_choice_numbers([dict(p) for p in paras])
    assert out[-1]["text"] == _INLINE_PASSAGE          # ① prepend 없음
    assert out[-1]["runs"][0]["t"] != "①"


def test_parser_prepend_still_works_on_plain_choices():
    # 정상 5지선다(자동번호 유실) — 가드가 기존 prepend를 막지 않는다
    paras = [
        _p("※ 다음 글을 읽고 물음에 답하시오. "),
        _p("다음 글의 제목으로 가장 적절한 것은?"),
        _p("Gary Oliver Who Succeeded As a Baseball Player"),
        _p("Spending Time Together: A Road to a Strong Family"),
        _p("Investing Time in Family: A Way to Success"),
        _p("Adopting Children Makes the World Better"),
        _p("Achieving One's Dream: Not a Difficult Thing"),
    ]
    out = _add_step3_choice_numbers([dict(p) for p in paras])
    assert out[2]["text"].startswith("①")
    assert out[6]["text"].startswith("⑤")


# ── D1: supp 세종 내지 스텝 카탈로그 ────────────────────────────────────────

def test_supp_sejong_step_map_excludes_b2():
    from engines.workbook_supp_v2.engine import (_SEJONG_STEP_MAP,
                                                 _STEP_MAP)
    assert "step1_b2" in _STEP_MAP
    assert "step1_b2" not in _SEJONG_STEP_MAP
    # b2 외 나머지 매핑은 동일 (pos 힌트 포함)
    for k, v in _SEJONG_STEP_MAP.items():
        assert v == _STEP_MAP[k]


def test_supp_step_map_selects_by_template_token(tmp_path):
    from engines.workbook_supp_v2.engine import (WorkbookSuppV2Engine,
                                                 _SEJONG_STEP_MAP,
                                                 _STEP_MAP)
    sejong = tmp_path / "워크북세종_내지.indd"
    sejong.write_bytes(b"x")
    default = tmp_path / "워크북C_모의고사.indd"
    default.write_bytes(b"x")
    cfg = {"indd_original": {"세종1": str(sejong),
                             "_default": str(default)}}
    eng = WorkbookSuppV2Engine()
    # 세종1 → 세종 카탈로그
    eng._plan_ctx = {"cfg": cfg, "school": "세종1",
                     "workbook_type": "모의고사"}
    assert eng._step_map() == _SEJONG_STEP_MAP
    # 다른 학교(폴백 _default) → 기본 카탈로그
    eng._plan_ctx = {"cfg": cfg, "school": "명일1",
                     "workbook_type": "모의고사"}
    assert eng._step_map() == _STEP_MAP
    # 컨텍스트 없음(구 호출 경로) → 기본 카탈로그
    eng._plan_ctx = None
    assert eng._step_map() == _STEP_MAP


def test_supp_sejong_plan_reports_b2_unsupported():
    from engines.workbook_v2.plan import steps_to_plan
    from engines.workbook_supp_v2.engine import _SEJONG_STEP_MAP
    steps = {"step1_b2": {"filename": "Step1 B2 내용종합.docx",
                          "question_numbers": [],
                          "paragraphs": [{"text": "Sample paragraph.",
                                          "runs": []}]}}
    plan = steps_to_plan(steps, step_map=_SEJONG_STEP_MAP)
    assert plan["unsupported"] == ["step1_b2"]
    assert plan["flows"] == []


# ── D2: 실행기 trimWsOverset — JSX 소스 가드 (오프라인) ─────────────────────

def test_executor_has_ws_overset_trim():
    src = open(os.path.join(REPO, "core", "jsx",
                            "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "function trimWsOverset" in src
    # 두 호출 지점: 확장 직전 + 스레드 절단 직후
    assert src.count("trimWsOverset(") >= 3


# ── U+F003B 잠복 확인 (W14 (2) — 워크북 경로 해소 기록) ─────────────────────

def test_pua_f003b_arrow_rule_covers_plane15():
    from engines.workbook_v2.plan import _s3_arrow_para
    assert _s3_arrow_para("\U000F003B")       # c20 실증 문자
    assert _s3_arrow_para("")           # W14 c05 문자


def test_c19_pre_fix_evidence_fixture_exists():
    fx = _fixture("c19_sejong_b2_pre_fix.json")
    assert any("step1_b2" in w for w in fx["warnings"])


# ── D4: G22 간지 라벨 + 본가/supp divider op ────────────────────────────────

_CONTENT_META = {"grade": 2, "year": 25, "month": 3}


def _divider_dump(l2="26년 3월"):
    return _dump([{"t": "고2 모의고사", "s": "[기본 단락]"},
                  {"t": l2, "s": "[기본 단락]"}])


def test_gate_g22_detects_stale_divider_critical_with_op():
    r = inspect_workbook_finish(_CONTENT_META,
                                {"divider": {"line1": "x", "line2": "y"}},
                                _divider_dump())
    assert any("간지라벨" in c for c in r["critical"])


def test_gate_g22_warns_without_divider_op():
    # 과거 출력/세로 실행기(divider op 미지원) — warning 지목 (G3/G4 패턴)
    r = inspect_workbook_finish(_CONTENT_META, {}, _divider_dump())
    assert not any("간지라벨" in c for c in r["critical"])
    assert any("간지라벨" in w for w in r["warnings"])


def test_gate_g22_passes_matching_and_skips_variants():
    # 일치 라벨 통과
    r = inspect_workbook_finish(_CONTENT_META, {}, _divider_dump("25년 3월"))
    assert r["stats"]["divider_stale"] == 0
    # '짤지문' 단독 라벨은 v1도 미갱신 — 제외
    r = inspect_workbook_finish(_CONTENT_META, {},
                                _divider_dump("26년 3월 짤지문"))
    assert r["stats"]["divider_stale"] == 0
    # content 메타 없으면 검사 생략
    r = inspect_workbook_finish({}, {}, _divider_dump())
    assert r["stats"]["divider_stale"] == 0


def test_mockexam_divider_decoration(tmp_path):
    from engines.workbook_v2.engine import _mockexam_divider
    job = tmp_path / "job"
    job.mkdir()
    (job / "content.json").write_text(json.dumps(_CONTENT_META),
                                      encoding="utf-8")
    assert _mockexam_divider(str(job)) == {
        "divider": {"line1": "고2 모의고사", "line2": "25년 3월"}}
    # content 없음 → 미적용
    assert _mockexam_divider(str(tmp_path / "none")) == {}


def test_base_and_supp_decorations_include_divider(tmp_path):
    from engines.workbook_v2.engine import WorkbookV2Engine
    from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine
    job = tmp_path / "job"
    job.mkdir()
    (job / "content.json").write_text(
        json.dumps({"grade": 1, "year": 25, "month": 10, "steps": {}}),
        encoding="utf-8")
    # 본가(모의고사)는 W19 D4 그대로 — 원고 grade/year/month 라벨
    deco = WorkbookV2Engine()._plan_decorations(str(job), {})
    assert deco["divider"] == {"line1": "고1 모의고사", "line2": "25년 10월"}
    # supp는 W22 r12 사용자 확정 스펙으로 변경: 간지 문구 입력 시 그 문구,
    # 미입력 시 교재유형만 표기 ('고N 모의고사/YY년 M월'은 supp 폼이
    # 년/월을 받지 않아 기본값이 찍히던 잔재 — 폐기). 상세 가드는
    # tests/test_workbook_v2_round12.py.
    deco_s = WorkbookSuppV2Engine()._plan_decorations(str(job), {})
    assert deco_s["divider"] == {"line1": "모의고사", "line2": "",
                                 "source": "type"}


# ── D5: updateDividerPages 좌우 무관 갱신 — JSX 소스 가드 (오프라인) ─────────

def test_executor_divider_side_agnostic():
    # W19 c05 실측: page_cleanup으로 간지가 왼쪽 페이지(p122)로 밀리면
    # v1 16.7의 RIGHT_HAND 조건이 갱신을 배제 → G22 critical 잔존.
    # v2는 의도적으로 side 조건을 제거 (완제품 기준 — v1 파리티 아님).
    src = open(os.path.join(REPO, "core", "jsx",
                            "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    body = src.split("function updateDividerPages")[1].split("\nfunction ")[0]
    assert "RIGHT_HAND" not in body
    # 안전 조건(마스터 [None] + 프레임 1개 + 한글 첫 단락)은 유지
    assert "[None]" in body
    assert "textFrames.length !== 1" in body


def test_c05_divider_left_pre_fix_evidence_fixture_exists():
    fx = _fixture("c05_divider_left_pre_fix.json")
    assert fx["divider_stale"] == 1
    assert any("간지라벨" in c for c in fx["critical"])
