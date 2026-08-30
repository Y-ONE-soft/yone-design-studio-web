"""W82 — 부교재 Step3 침묵 소실 (job 4b8b05f8 실증).

Step3 원고가 책 제목으로 이름 붙으면('수능만만 기본문법 PART1 09 관계사.docx')
파일명 라우터(route_step3)의 토큰 세 종류(스텝3/N번/변형문제)에 하나도 걸리지
않아 루트에 남고, v1 파서의 스텝1/2 파일명 매칭에도 안 걸려 **Step3 전체가
0유닛으로 조용히 사라진다** (Step3 폴더가 비어 있으니 reconcile_step3도 통과).

수리는 파일명 화이트리스트를 늘리는 게 아니라 원고 '구조'로 판정 —
번호 붙은 한국어 발문 + ①선지 줄이 함께 많으면 실전/변형문제 문항 모음이다.
"""
import os

import pytest


def _pool_texts(n=8):
    """실전문제 문항 모음 모양 — 번호 발문 + ①~⑤ 선지 + 영어 지문."""
    out = []
    for i in range(1, n + 1):
        out.append(f"{i}. 다음 글의 빈칸에 들어갈 말로 가장 적절한 것은?{i})")
        out.append("A person who chooses to avoid using or consuming animal "
                   "products is known as a vegan and this is a long passage.")
        for mark in "①②③④⑤":
            out.append(f"{mark} choice text {i}")
    return out


def test_pool_shape_recognizes_manuscript_without_step_token():
    from engines.workbook_v2.routing import looks_like_step3_pool, route_step3
    # 파일명으로는 못 알아본다 (이것이 W82 결함의 출발점)
    assert not route_step3("수능만만 기본문법 PART1 09 관계사.docx")
    ok, prompts, choices = looks_like_step3_pool(_pool_texts())
    assert ok and prompts >= 5 and choices >= 5


def test_pool_shape_rejects_step12_shapes():
    """두 조건의 '교집합'이 갈라준다 — 실측 코퍼스(Step3 471 / 루트 1864)."""
    from engines.workbook_v2.routing import looks_like_step3_pool
    # 'Step1 A2 본문OX' 계열: 번호 발문은 많지만 ①선지 줄은 거의 없다
    prompts_only = [f"{i}. 다음 밑줄 친 부분이 어법상 맞는가?" for i in range(1, 16)]
    assert not looks_like_step3_pool(prompts_only)[0]
    # 'Step1 B2 내용종합' 계열: ①선지 줄은 많지만 번호 발문이 없다
    choices_only = [f"① item {i}" for i in range(1, 30)]
    assert not looks_like_step3_pool(choices_only)[0]


def _make_docx(path, texts):
    from docx import Document
    doc = Document()
    for t in texts:
        doc.add_paragraph(t)
    doc.save(path)


def test_rescue_moves_pool_into_step3_and_keeps_others(tmp_path):
    from engines.workbook_v2.routing import rescue_unrouted_step3
    root = tmp_path / "uploads"
    root.mkdir()
    consumed = "Step1 C2 빈칸어휘 해설지.docx"
    _make_docx(str(root / consumed), ["1. 지문", "본문"])
    _make_docx(str(root / "Step1 C2 빈칸어휘.docx"), ["1. 지문", "본문"])
    _make_docx(str(root / "Step2 A1 어법선택 정답지.docx"), ["1. who"])
    pool = "수능만만 기본문법 PART1 09 관계사.docx"
    _make_docx(str(root / pool), _pool_texts())

    data = {"steps": {"step1_c2": {"filename": consumed}}}
    logs = []
    rescued = rescue_unrouted_step3(str(root), data, logs.append)

    assert rescued == [pool]
    assert (root / "Step3" / pool).exists()
    # 같은 계열 예비본·답지류는 옮기지 않는다 (범위 최소)
    assert not (root / "Step3" / "Step1 C2 빈칸어휘.docx").exists()
    assert not (root / "Step3" / "Step2 A1 어법선택 정답지.docx").exists()
    assert any("같은 계열" in m for m in logs)


def test_rescue_respects_staged_candidates(tmp_path):
    """업로드 원본('manuscripts_…')이 같은 폴더에 남아 사본과 짝으로 중복
    구제되면 Step3 분량이 2배가 된다 — 엔진이 스테이징한 사본만 후보."""
    from engines.workbook_v2.routing import rescue_unrouted_step3
    root = tmp_path / "uploads"
    root.mkdir()
    pool = "수능만만 기본문법 PART1 09 관계사.docx"
    _make_docx(str(root / pool), _pool_texts())
    _make_docx(str(root / ("manuscripts_" + pool)), _pool_texts())

    rescued = rescue_unrouted_step3(str(root), {"steps": {}}, lambda s: None,
                                    candidates={pool})
    assert rescued == [pool]
    assert len(os.listdir(root / "Step3")) == 1


def test_rescue_reports_unconsumed_manuscripts(tmp_path):
    """구제 대상이 아니어도 미소비 원고는 반드시 로그에 남는다 (침묵 금지)."""
    from engines.workbook_v2.routing import rescue_unrouted_step3
    root = tmp_path / "uploads"
    root.mkdir()
    _make_docx(str(root / "Step2 직보.docx"), ["Q. 어법상 고치시오.", "본문"])
    logs = []
    rescued = rescue_unrouted_step3(str(root), {"steps": {}}, logs.append)
    assert rescued == []
    assert any("미소비 원고" in m and "직보" in m for m in logs)
