"""core.extract — 공용 원고 추출 API.

신규 코드는 여기의 공개 이름을 사용한다. (밑줄 이름은 기존 엔진 호환용)
"""

from core.extract.extractors import (  # noqa: F401
    _NS_W,
    _nfc,
    _docx_extract_paragraphs,
    _parse_underline_ids,
    _hwpx_extract_segments,
    _hwpx_extract_paragraphs,
    _hwp_is_hwpx,
    _hwp_decode_paratext,
    _hwp_decode_para_charshape,
    _hwp_build_charshape_ul,
    _hwp_text_with_underline,
    _DINGBAT_TO_STD,
    _normalize_circled_numbers,
    _RE_SRC_BAR,
    _hwp_extract_paragraphs,
)

# 공개 별칭 (Phase 2+에서 이쪽으로 정리)
nfc = _nfc
docx_extract_paragraphs = _docx_extract_paragraphs
hwpx_extract_paragraphs = _hwpx_extract_paragraphs
hwp_extract_paragraphs = _hwp_extract_paragraphs
parse_underline_ids = _parse_underline_ids
normalize_circled_numbers = _normalize_circled_numbers
is_hwpx = _hwp_is_hwpx
