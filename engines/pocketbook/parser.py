"""포켓북 리뷰테스트 해설지 .docx 파서.

리뷰테스트 해설지 워드 파일을 파싱하여 암기테스트용 JSON으로 변환한다.

해설지 구조:
    1. p100-수능 대비 ANALYSIS          ← 지문 구분 헤더
    Good design starts with an 1[understanding] of 2[psychology]...  ← 영어(번호+빈칸)
    좋은 디자인은 심리학과 기술에 대한 이해에서 시작된다.           ← 한글 해석
    ...
    2. p102-no.01                       ← 다음 지문
    ...
"""

import json
import os
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET


_WP_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _extract_paragraphs(docx_path):
    """docx에서 텍스트 단락 리스트 추출."""
    paragraphs = []
    with ZipFile(docx_path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    root = tree.getroot()
    ns = {"w": _WP_NS}
    for p in root.findall(".//w:p", ns):
        texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
        line = "".join(texts).strip()
        paragraphs.append(line)
    return paragraphs


def _is_passage_header(line):
    """지문 구분 헤더인지 판별.

    패턴: '1. p100-수능 대비 ANALYSIS' / '2. p102-no.01' / '3. L1-본문9'
    """
    return bool(re.match(r"^\d+\.\s+[pL]\d+", line))


def _has_korean(text):
    """한글 포함 여부."""
    return bool(re.search(r"[\uAC00-\uD7AF]", text))


def _has_brackets(text):
    """번호+대괄호 패턴 포함 여부: 1[word]"""
    return bool(re.search(r"\d+\[", text))


def _extract_bracket_words(text):
    """번호+대괄호에서 단어 추출. '1[understanding] 2[psychology]' → [(1,'understanding'), ...]"""
    return [(int(m.group(1)), m.group(2))
            for m in re.finditer(r"(\d+)\[([^\]]+)\]", text)]


def _make_blank_version(text):
    """빈칸 버전: answer_text와 동일 텍스트 반환 (JSX에서 대괄호 내 글자색을 Paper로 변경)."""
    return text


def parse_review_test(docx_path, log=None):
    """리뷰테스트 해설지 .docx → 지문별 암기테스트 데이터.

    Returns:
        {
            "source_file": str,
            "passages": [
                {
                    "header": "1. p100-수능 대비 ANALYSIS",
                    "lines_answer": ["원문 (정답 포함)..."],
                    "lines_blank": ["빈칸 버전..."],
                    "korean_lines": ["한글 해석..."],
                    "word_count": 42,
                }
            ],
            "total_words": 156,
        }
    """
    if log is None:
        log = lambda m: None

    filename = os.path.basename(docx_path)
    log(f"[파서] 리뷰테스트 해설지 파싱: {filename}")

    paragraphs = _extract_paragraphs(docx_path)

    passages = []
    current = None

    for line in paragraphs:
        if not line:
            continue

        # 지문 구분 헤더 감지
        if _is_passage_header(line):
            if current and (current["lines_answer"] or current["korean_lines"]):
                passages.append(current)
            current = {
                "header": line,
                "lines_answer": [],
                "lines_blank": [],
                "korean_lines": [],
                "word_count": 0,
            }
            continue

        if current is None:
            # 헤더 전 메타 라인 (제목, 설명 등) → 스킵
            continue

        # 번호+대괄호가 있는 영어 라인
        if _has_brackets(line):
            words = _extract_bracket_words(line)
            current["word_count"] += len(words)
            # "숫자[오답 (정답)]" -> "숫자[정답]" 변환
            cleaned = re.sub(r"(\d+)\[[^\(]+\(([^\)]+)\)\]", r"\1[\2]", line)
            current["lines_answer"].append(cleaned)
            current["lines_blank"].append(_make_blank_version(cleaned))
        elif _has_korean(line):
            current["korean_lines"].append(line)
        else:
            # 대괄호 없는 영어 라인도 정답에 포함 (변형 없이)
            if re.search(r"[A-Za-z]{3,}", line):
                current["lines_answer"].append(line)
                current["lines_blank"].append(line)

    # 마지막 지문 추가
    if current and (current["lines_answer"] or current["korean_lines"]):
        passages.append(current)

    total_words = sum(p["word_count"] for p in passages)
    log(f"[파서] {filename}: {len(passages)}개 지문, {total_words}개 빈칸 단어")

    return {
        "source_file": filename,
        "passages": passages,
        "total_words": total_words,
    }


def parse_multiple_review_tests(file_paths, output_path, log=None):
    """여러 리뷰테스트 해설지 → 통합 content JSON."""
    if log is None:
        log = lambda m: None

    all_passages = []
    for fp in file_paths:
        try:
            result = parse_review_test(fp, log)
            all_passages.extend(result["passages"])
        except Exception as e:
            log(f"[경고] {os.path.basename(fp)} 파싱 실패: {e}")

    total_words = sum(p["word_count"] for p in all_passages)
    content = {
        "type": "review_test",
        "passages": all_passages,
        "total_words": total_words,
        "total_passages": len(all_passages),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    log(f"[파서] 총 {len(all_passages)}개 지문, {total_words}개 빈칸 단어")
    return content
