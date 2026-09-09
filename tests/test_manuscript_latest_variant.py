"""같은 단계 원고가 여럿(개정본 등)이면 최신본을 조판한다 — 사용자 지시 2026-09-10.

실측: 모의고사 워크북 26개 회차의 원고 폴더에 'Step1 C2 빈칸어휘 정답지.docx'
와 '… 정답지(개정).docx' 가 함께 있는데, config 파일명과 정확히 같은 구판이
항상 채택돼 (개정) 파일은 한 번도 조판된 적이 없었다.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.workbook.parser import (_manu_family_key, _has_revision_token,
                                     _prefer_latest_variant,
                                     parse_manuscript_folder)


def _make_docx(path, texts):
    from docx import Document
    doc = Document()
    for t in texts:
        doc.add_paragraph(t)
    doc.save(path)


def _touch(path, when):
    os.utime(path, (when, when))


_OLD = ["고1_2025_09월 - 읽기영역(18~45번)", "어휘완성(해설지)", "1. p2-no.20",
        "1[Inefficient] teachers 2[overlook] the 3[potential] power of class.",
        "비효율적인 교사들은 수업의 잠재적인 힘을 간과한다.",
        "2. p3-no.21",
        "Many atoms in your body are nearly as 4[old] as the 5[universe] itself.",
        "당신 몸의 많은 원자는 우주만큼 오래되었다."]
_NEW = ["고1_2025_09월 - 읽기영역(18~45번)", "어휘완성(해설지)", "1. p2-no.20",
        "1[Inefficient] teachers overlook the 2[potential] power of class.",
        "비효율적인 교사들은 수업의 잠재적인 힘을 간과한다.",
        "2. p3-no.21",
        "Many 3[atoms] in your body are nearly as old as the 4[universe] itself.",
        "당신 몸의 많은 원자는 우주만큼 오래되었다."]

_CFG = {"manuscript_file_map": {"step1_c2": "Step1 C2 빈칸어휘 정답지.docx"},
        "needs_underline": [], "mockexam": {}}


def test_family_key_strips_revision_tokens_only():
    k = _manu_family_key("Step1 C2 빈칸어휘 정답지.docx")
    assert k == "step1c2빈칸어휘정답지"
    assert _manu_family_key("Step1 C2 빈칸어휘 정답지(개정).docx") == k
    assert _manu_family_key("Step1 C2빈칸어휘 정답지(개정).docx") == k
    assert _manu_family_key("Step1 C2 빈칸어휘 정답지 수정본.docx") == k
    assert _manu_family_key("Step1 C2 빈칸어휘 정답지(2차 수정).docx") == k
    assert _manu_family_key("manuscripts_Step1 C2 빈칸어휘 정답지_v2.docx") == k
    # 슬롯을 가르는 괄호(객관식/서술형)·답안 토큰은 가족을 나눈다
    assert (_manu_family_key("Step2 A1 어법선택(객관식).docx")
            != _manu_family_key("Step2 A1 어법선택.docx"))
    assert (_manu_family_key("Step1 C2 빈칸어휘.docx")
            != _manu_family_key("Step1 C2 빈칸어휘 정답지.docx"))
    assert _has_revision_token("Step1 C2 빈칸어휘 정답지(개정).docx")
    assert not _has_revision_token("Step1 C2 빈칸어휘 정답지.docx")
    # 영문 낱말 안의 'new/rev' 는 개정 표기가 아니다
    assert not _has_revision_token("Step3 review sheet.docx")


def test_newer_revision_wins_over_exact_config_name(tmp_path):
    old = tmp_path / "Step1 C2 빈칸어휘 정답지.docx"
    new = tmp_path / "Step1 C2 빈칸어휘 정답지(개정).docx"
    _make_docx(str(old), _OLD)
    _make_docx(str(new), _NEW)
    now = time.time()
    _touch(str(old), now - 86400 * 300)
    _touch(str(new), now - 86400 * 10)
    logs = []
    data = parse_manuscript_folder(str(tmp_path), _CFG, 1, 25, 9, logs.append)
    st = data["steps"]["step1_c2"]
    assert st["filename"] == new.name
    assert data.get("superseded_manuscripts") == [old.name]
    texts = " ".join(p["text"] for p in st["paragraphs"])
    assert "3[atoms]" in texts and "2[overlook]" not in texts
    assert any("[선택] step1_c2" in l and "최신" in l for l in logs)


def test_newer_plain_file_wins_over_older_marked(tmp_path):
    # 규칙은 '최신 업로드' — 개정 표기가 있어도 더 오래됐으면 밀린다
    old = tmp_path / "Step1 C2 빈칸어휘 정답지(개정).docx"
    new = tmp_path / "Step1 C2 빈칸어휘 정답지.docx"
    _make_docx(str(old), _OLD)
    _make_docx(str(new), _NEW)
    now = time.time()
    _touch(str(old), now - 86400 * 300)
    _touch(str(new), now - 86400 * 10)
    data = parse_manuscript_folder(str(tmp_path), _CFG, 1, 25, 9)
    assert data["steps"]["step1_c2"]["filename"] == new.name
    assert data.get("superseded_manuscripts") == [old.name]


def test_tie_prefers_revision_marked_file(tmp_path):
    # 폴더째 업로드 등으로 수정시각이 같으면 개정 표기가 있는 쪽
    old = tmp_path / "Step1 C2 빈칸어휘 정답지.docx"
    new = tmp_path / "Step1 C2 빈칸어휘 정답지(개정).docx"
    _make_docx(str(old), _OLD)
    _make_docx(str(new), _NEW)
    t0 = time.time() - 1000
    _touch(str(old), t0)
    _touch(str(new), t0)
    data = parse_manuscript_folder(str(tmp_path), _CFG, 1, 25, 9)
    assert data["steps"]["step1_c2"]["filename"] == new.name


def test_single_file_unchanged(tmp_path):
    only = tmp_path / "Step1 C2 빈칸어휘 정답지.docx"
    _make_docx(str(only), _OLD)
    logs = []
    data = parse_manuscript_folder(str(tmp_path), _CFG, 1, 25, 9, logs.append)
    assert data["steps"]["step1_c2"]["filename"] == only.name
    assert "superseded_manuscripts" not in data
    assert not any("[선택]" in l for l in logs)


def test_paren_slot_variants_are_not_a_family(tmp_path):
    # 어법선택(상단) / 어법선택(객관식)(하단) 은 다른 슬롯 — 최신 규칙 무관
    top = tmp_path / "Step2 A1 어법선택.docx"
    btm = tmp_path / "Step2 A1 어법선택(객관식).docx"
    _make_docx(str(top), ["1. p2-no.20", "He (go / goes) to school."])
    _make_docx(str(btm), ["1. p2-no.20", "① go ② goes ③ going ④ gone ⑤ went"])
    now = time.time()
    _touch(str(top), now - 86400 * 300)
    _touch(str(btm), now - 86400)
    cfg = {"manuscript_file_map": {
                "step2_a1": "Step2 A1 어법선택.docx",
                "step2_a1_btm": "Step2 A1 어법선택(객관식).docx"},
           "needs_underline": [], "mockexam": {}}
    data = parse_manuscript_folder(str(tmp_path), cfg, 1, 25, 9)
    assert data["steps"]["step2_a1"]["filename"] == top.name
    assert data["steps"]["step2_a1_btm"]["filename"] == btm.name
    assert "superseded_manuscripts" not in data


def test_prefer_latest_variant_skips_lock_and_used_files(tmp_path):
    a = tmp_path / "Step1 C2 빈칸어휘 정답지.docx"
    b = tmp_path / "Step1 C2 빈칸어휘 정답지(개정).docx"
    lock = tmp_path / "~$ep1 C2 빈칸어휘 정답지(개정).docx"
    for p in (a, b, lock):
        p.write_bytes(b"x")
    now = time.time()
    _touch(str(a), now - 100)
    _touch(str(b), now - 10)
    _touch(str(lock), now)
    pick, losers = _prefer_latest_variant(str(tmp_path), str(a), set())
    assert os.path.basename(pick) == b.name
    assert [os.path.basename(x) for x in losers] == [a.name]
    # 이미 다른 슬롯에 쓰인 파일은 후보가 아니다
    pick2, losers2 = _prefer_latest_variant(str(tmp_path), str(a), {str(b)})
    assert pick2 == str(a) and losers2 == []


def test_gate_treats_superseded_as_expected_unused(tmp_path):
    from engines.workbook_v2.gate import find_unused_uploads
    up = tmp_path / "uploads"
    up.mkdir()
    (up / "Step1 A1 어휘선택.docx").write_bytes(b"x")
    (up / "Step1 A1 어휘선택(개정).docx").write_bytes(b"x")
    content = {"steps": {"step1_a1": {"filename": "Step1 A1 어휘선택(개정).docx"}},
               "superseded_manuscripts": ["Step1 A1 어휘선택.docx"]}
    expected, suspicious = find_unused_uploads(content, str(up))
    assert "Step1 A1 어휘선택.docx" in expected
    assert suspicious == []
