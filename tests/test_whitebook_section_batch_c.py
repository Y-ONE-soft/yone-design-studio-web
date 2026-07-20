"""W35 배치 C — 화이트북 외부 파서 리포 흡수 + 섹션 인식 구조화.

감사(docs/인식지점_전수감사.md) 리스크 4위 · §9 C안:
  1) 외부 parse_whitebook.py 를 engines/whitebook/external/ 로 byte 스냅샷
     흡수 (원본 무수정 — divergence 는 byte-parity 테스트가 감시)
  2) v2 섹션 분할을 구조 신호(`^[A-E][.)]` + 한국어 발문) 1선 + 발문 문구
     프라이어로 — 실증 #7('해석'→'뜻') 인식 회복
  3) 침묵 소멸 금지 — Day 내 A~E 결손/중복 시 [오류]
  4) 골든 2케이스 diff 0 (byte 파리티 계약) — v2 parse 가 인-리포 경로로
     전환된 뒤에도 산출물 무변화
"""
import json
import os
import zipfile
from xml.sax.saxutils import escape

import pytest

import _replay
from engines.whitebook.external import parse_whitebook as snap
from engines.whitebook_v2 import wb_parser
from engines.whitebook_v2.wb_parser import (
    WhitebookSectionError, match_section_header, split_by_sections_struct)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

# 규정 발문 (스냅샷 SECTION_HEADERS 가 인식하는 실물 문구 — 코퍼스 실측)
CANON_HEADERS = {
    "A": "A. 주어진 단어에 해당하는 우리말 뜻을 빈칸에 써보세요.",
    "B": "B. 다음 우리말 해석을 참고하여 빈칸에 알맞은 단어를 써보세요.",
    "C": "C. 다음 영영사전 풀이에 해당하는 단어를 찾아 <보기>에서 골라 써보세요.",
    "D": "D. 주어진 단어와 유사한 뜻 혹은 반대되는 뜻을 가진 것을 모두 찾아 번호를 쓰세요.",
    "E": "E. 주어진 단어와 어울리는 전치사를 빈칸에 적으시오.",
}


def _day_lines(headers=None):
    h = dict(CANON_HEADERS)
    h.update(headers or {})
    return [
        h["A"],
        "1. significant",
        h["B"],
        "1. The result was s__________.",
        "그 결과는 중요했다.",
        h["C"],
        "[문제 1]",
        "〈보기〉 significant / exhibit",
        "1. very important : ______",
        h["D"],
        "〈보기〉",
        "① concord  ② discord",
        "1. significant [반의어] : ______",
        h["E"],
        "1. The boat is anchored ______ the dock.",
    ]


# ── 1. 리포 흡수 (스냅샷) ──────────────────────────────────────────────────

def test_snapshot_byte_parity_with_external():
    """스냅샷 ↔ 외부 원본 byte 동일 — divergence 시 여기서 드러난다
    (감사 사각 해소 지점). 외부 경로 없는 환경(CI 등)에서는 skip."""
    from core.paths import resolve
    cfg = json.load(open(os.path.join(
        REPO, "engines", "whitebook", "config.json"), encoding="utf-8"))
    external = resolve(cfg["parse_script"])
    if not os.path.isfile(external):
        pytest.skip("외부 원본 경로 없음 — byte 파리티 감시는 원본 보유 기기에서")
    absorbed = os.path.join(REPO, "engines", "whitebook", "external",
                            "parse_whitebook.py")
    assert open(absorbed, "rb").read() == open(external, "rb").read(), (
        "리포 스냅샷과 외부 원본이 다름 — 외부 파일이 수정되었으면 "
        "스냅샷 재흡수 + 골든 파리티 재검증 필요")


def test_priors_are_snapshot_section_headers():
    """프라이어 테이블 = 스냅샷 SECTION_HEADERS (데이터 테이블 공유 — 같은 눈)."""
    assert set(wb_parser.SECTION_PHRASE_PRIORS) == set("ABCDE")
    for k, pat in snap.SECTION_HEADERS.items():
        assert wb_parser.SECTION_PHRASE_PRIORS[k].pattern == pat.pattern


# ── 2. 구조 신호 — 리터럴의 상위집합 (하위호환 하한) ───────────────────────

def test_struct_recognizes_all_canonical_headers():
    for letter, line in CANON_HEADERS.items():
        assert snap.SECTION_HEADERS[letter].match(line), "실물 발문 검증"
        assert match_section_header(line) == letter


@pytest.mark.parametrize("variant,letter", [
    # 실증 #7: '해석'→'뜻' 한 단어 변형 (기존 리터럴은 B 소멸)
    ("B. 다음 우리말 뜻을 참고하여 빈칸에 알맞은 단어를 써보세요.", "B"),
    # 발문 전면 재작성/구분자 변형도 구조 신호로 흡수
    ("A) 우리말 뜻 쓰기", "A"),
    ("C. 영영풀이에 맞는 단어를 고르시오.", "C"),
    ("E.빈칸에 알맞은 전치사를 쓰시오.", "E"),
])
def test_struct_recognizes_phrase_variants(variant, letter):
    assert not any(p.match(variant)
                   for p in snap.SECTION_HEADERS.values()), "리터럴 미인식 전제"
    assert match_section_header(variant) == letter


@pytest.mark.parametrize("line", [
    "1. significant",              # 번호 항목
    "A. significant",              # 영어 본문 (한글 없음 — 헤더 아님)
    "E. coli is a bacterium.",     # 영어 문장
    "F. 다음 우리말 해석을 참고하세요.",  # A~E 밖 문자
    "▶ A",                          # 정답 섹션 마커
    "그 결과는 중요했다.",           # 한글 해석 라인
])
def test_struct_rejects_non_headers(line):
    assert match_section_header(line) is None


# ── 3. 침묵 소멸 금지 ──────────────────────────────────────────────────────

def test_split_canonical_day():
    secs = split_by_sections_struct(_day_lines(), day_num=11)
    assert sorted(secs) == list("ABCDE")
    assert len(secs["B"]) == 2


def test_split_variant_phrase_keeps_section():
    """실증 #7 해소: '해석'→'뜻' 변형에도 B 섹션이 살아있다."""
    lines = _day_lines({"B": "B. 다음 우리말 뜻을 참고하여 빈칸에 알맞은 단어를 써보세요."})
    secs = split_by_sections_struct(lines, day_num=11)
    assert sorted(secs) == list("ABCDE")
    assert secs["B"] == ["1. The result was s__________.", "그 결과는 중요했다."]


def test_split_missing_section_raises():
    lines = [l for l in _day_lines() if not l.startswith("B.")]
    with pytest.raises(WhitebookSectionError) as ei:
        split_by_sections_struct(lines, day_num=13)
    msg = str(ei.value)
    assert "[오류]" in msg and "Day 13" in msg and "결손 B" in msg


def test_split_duplicate_section_raises():
    lines = _day_lines() + [CANON_HEADERS["C"]]
    with pytest.raises(WhitebookSectionError) as ei:
        split_by_sections_struct(lines, day_num=14)
    assert "[오류]" in str(ei.value) and "중복" in str(ei.value)


# ── 4. 엔진 parse 경유 (합성 hwpx — 오류가 조판 중단으로 전파) ─────────────

def _make_hwpx(path, lines):
    xml = ("<root>"
           + "".join(f"<p><t>{escape(l)}</t></p>" for l in lines)
           + "</root>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section0.xml", xml)


def test_engine_parse_variant_ok_and_missing_fails(tmp_path):
    from engines.whitebook_v2.engine import WhitebookV2Engine
    engine = WhitebookV2Engine()
    variant = ["Day 11"] + _day_lines(
        {"B": "B. 다음 우리말 뜻을 참고하여 빈칸에 알맞은 단어를 써보세요."})
    ok_hwpx = str(tmp_path / "ok.hwpx")
    _make_hwpx(ok_hwpx, variant)
    job = tmp_path / "job_ok"
    job.mkdir()
    logs = []
    jp = engine.parse({"w1_main": ok_hwpx}, str(job), logs.append)
    data = json.load(open(jp, encoding="utf-8"))
    assert [d["day_num"] for d in data["days"]] == [11]
    assert len(data["days"][0]["content"]["B"]) == 1  # B 생존 (침묵 소멸 아님)

    bad_hwpx = str(tmp_path / "bad.hwpx")
    _make_hwpx(bad_hwpx, ["Day 12"]
               + [l for l in _day_lines() if not l.startswith("B.")])
    job2 = tmp_path / "job_bad"
    job2.mkdir()
    with pytest.raises(WhitebookSectionError):
        engine.parse({"w1_main": bad_hwpx}, str(job2), logs.append)


# ── 5. 골든 파리티 (byte 파리티 계약 — v2 parse 인-리포 전환 후 diff 0) ────

@pytest.mark.parametrize("case", ["e41f1c70", "3b3ddc5a"])
def test_v2_parse_golden_parity(case, tmp_path):
    from engines.whitebook_v2.engine import WhitebookV2Engine
    case_dir = os.path.join(TESTS_DIR, "corpus", "whitebook", case)
    job_dir = str(tmp_path / "job")
    produced = _replay.replay(WhitebookV2Engine(), case_dir, job_dir)
    golden = json.load(open(os.path.join(case_dir, "golden", "content.json"),
                            encoding="utf-8"))
    diff = _replay.first_diff(_replay.canonicalize(produced, [job_dir]),
                              _replay.canonicalize(golden, []))
    assert diff is None, f"인-리포 파서가 골든과 다름: {diff}"
