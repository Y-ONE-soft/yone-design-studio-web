"""core/uploads.py — 업로드 파일명 정규화 + 확장자 화이트리스트 (C1-3)."""
import unicodedata

from core.uploads import sanitize_filename, allowed_by_accept


# ── sanitize_filename ────────────────────────────────────────────────

def test_korean_filename_preserved():
    # secure_filename과 달리 한글이 전멸하지 않아야 함 (기존 정상 업로드 보존)
    assert sanitize_filename("성덕고1_워크북_원고.docx") == "성덕고1_워크북_원고.docx"


def test_plain_ascii_unchanged():
    assert sanitize_filename("manuscript_final.hwpx") == "manuscript_final.hwpx"


def test_posix_path_traversal_stripped():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/etc/passwd") == "passwd"


def test_windows_path_separator_stripped():
    assert sanitize_filename("C:\\Users\\evil\\원고.docx") == "원고.docx"


def test_null_byte_and_control_chars_removed():
    assert sanitize_filename("bad\x00name.docx") == "badname.docx"
    assert sanitize_filename("a\nb\tc.hwp") == "abc.hwp"


def test_leading_dots_stripped():
    assert sanitize_filename(".hidden.docx") == "hidden.docx"
    assert sanitize_filename("..") == "upload"


def test_empty_falls_back():
    assert sanitize_filename("") == "upload"
    assert sanitize_filename("///") == "upload"
    assert sanitize_filename("\x00") == "upload"


def test_nfd_normalized_to_nfc():
    nfd = unicodedata.normalize("NFD", "원고.docx")
    out = sanitize_filename(nfd)
    assert out == "원고.docx"
    assert unicodedata.is_normalized("NFC", out)


# ── allowed_by_accept ────────────────────────────────────────────────

def test_accept_matches_listed_extension():
    assert allowed_by_accept("원고.docx", ".docx,.hwp,.hwpx")
    assert allowed_by_accept("원고.hwpx", ".docx,.hwp,.hwpx")


def test_accept_case_insensitive():
    assert allowed_by_accept("MANUSCRIPT.DOCX", ".docx,.hwp,.hwpx")
    assert allowed_by_accept("cover.AI", ".ai")


def test_accept_rejects_unlisted_extension():
    assert not allowed_by_accept("evil.exe", ".docx,.hwp,.hwpx")
    assert not allowed_by_accept("script.jsx", ".docx")
    assert not allowed_by_accept("noext", ".docx")


def test_no_accept_passes_everything():
    # 슬롯에 accept 명시가 없으면 기존 동작 유지 (통과)
    assert allowed_by_accept("anything.xyz", "")
    assert allowed_by_accept("anything.xyz", None)


def test_accept_without_extension_tokens_passes():
    # MIME 타입만 있는 accept는 강제하지 않음 (방어적)
    assert allowed_by_accept("file.docx", "application/msword")


def test_accept_with_spaces():
    assert allowed_by_accept("a.hwp", ".docx, .hwp, .hwpx")
