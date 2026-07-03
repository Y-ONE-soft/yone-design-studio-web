"""블랙북 v2 파서 — 하이브리드 전략.

- 문제 섹션(part1/part2): core.extract + core.structure + build_ir (구조 인식)
  → 검증 근거: 가드 테스트 test_build_ir_generalizes_to_blackbook (107/43 정확)
- 어휘/정답 섹션: 검증된 v1 파서(engines.blackbook.kind_parser) 재사용 (읽기 전용)

v1(engines/blackbook)은 무변경. 파일 분류도 v1의 classify_filename 재사용.
"""
import os
import unicodedata

from engines.blackbook.kind_parser import classify_filename, parse_by_kind
from engines.mockexam_v2.parser import build_ir, extract_file_paragraphs


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _clean_name(path):
    name = _nfc(os.path.basename(path))
    for pre in ("manuscript_", "answers_"):
        if name.startswith(pre):
            return name[len(pre):]
    return name


def parse_files(paths, log=None):
    """업로드 파일들 → 섹션별 파싱 결과.

    반환: {
      "problems_p1": v2 IR 문서, "problems_p2": v2 IR 문서,
      "vocab": v1 items, "answers_p1": v1 items, "answers_p2": v1 items,
      "unmatched": [파일명], "warnings": [...]
    }
    """
    out = {"problems_p1": None, "problems_p2": None, "vocab": [],
           "answers_p1": [], "answers_p2": [], "unmatched": [], "warnings": []}

    def _log(msg):
        if callable(log):
            log(msg)

    for path in sorted(paths):
        kind = classify_filename(_clean_name(path))
        if kind is None:
            out["unmatched"].append(_clean_name(path))
            out["warnings"].append(f"파일 분류 실패: {_clean_name(path)}")
            continue
        if kind in ("part1_problem", "part2_problem"):
            doc = build_ir(extract_file_paragraphs(path), log=log)
            key = "problems_p1" if kind == "part1_problem" else "problems_p2"
            if out[key] is None:
                out[key] = doc
            else:   # 분할 업로드 병합
                out[key]["items"].extend(doc["items"])
                out[key]["meta"].setdefault("_warnings", []).extend(
                    doc["meta"].get("_warnings", []))
            _log(f"[v2] {kind}: {_clean_name(path)} → 문항 {len(doc['items'])}")
        elif kind == "part1_vocab":
            items = parse_by_kind(kind, path)
            out["vocab"].extend(items)
            _log(f"[v1재사용] 어휘: {_clean_name(path)} → {len(items)}본문")
        elif kind in ("part1_answer", "part2_answer"):
            items = parse_by_kind(kind, path)
            key = "answers_p1" if kind == "part1_answer" else "answers_p2"
            out[key].extend(items)
            _log(f"[v1재사용] {kind}: {_clean_name(path)} → {len(items)}개")
    return out
