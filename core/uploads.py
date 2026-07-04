"""업로드 파일명 정규화 + 확장자 화이트리스트 (리스크분석 C1-3).

werkzeug.secure_filename은 ASCII 밖 문자를 전부 제거해 한글 파일명이
전멸하므로 쓰지 않는다. 여기서는 위험 요소만 제거하고 한글은 보존한다:

- 경로 분리자(/, \\) 이후만 남김 (경로 탈출 방지 — 브라우저/OS별 구분자 모두)
- 널바이트 등 제어문자 제거
- 선행 점(.) 제거 — 숨김 파일 방지 (os.walk dot-pruning 규칙과 일관)
- 유니코드 NFC 정규화 — macOS NFD 파일명과 파서 매칭 불일치 방지
- 빈 문자열이 되면 "upload" 폴백
"""
import os
import unicodedata

_FALLBACK = "upload"


def sanitize_filename(name: str) -> str:
    """브라우저가 보낸 파일명에서 위험 요소만 제거 (한글 보존)."""
    if not name:
        return _FALLBACK
    # 경로 분리자: POSIX(/)와 Windows(\) 모두 — 마지막 조각만 사용
    name = name.replace("\\", "/").split("/")[-1]
    # 널바이트 및 기타 제어문자 제거
    name = "".join(ch for ch in name if ch >= " " and ch != "\x7f")
    # NFC 정규화 (macOS 브라우저는 NFD로 보낼 수 있음)
    name = unicodedata.normalize("NFC", name)
    # 선행 점/공백 제거 (숨김 파일 · 상대경로 트릭 방지)
    name = name.lstrip(". ").strip()
    if not name or name in (".", ".."):
        return _FALLBACK
    return name


def allowed_by_accept(filename: str, accept: str) -> bool:
    """슬롯 accept(예: ".docx,.hwp,.hwpx") 기준 확장자 화이트리스트.

    - accept가 비어 있으면(슬롯에 명시 없음) 통과 — 기존 동작 유지.
    - accept에 확장자 토큰(".xxx")이 하나도 없으면 통과 (MIME 타입 등 방어).
    - 비교는 대소문자 무시.
    """
    if not accept:
        return True
    exts = [t.strip().lower() for t in accept.split(",")
            if t.strip().startswith(".")]
    if not exts:
        return True
    ext = os.path.splitext(filename)[1].lower()
    return ext in exts
