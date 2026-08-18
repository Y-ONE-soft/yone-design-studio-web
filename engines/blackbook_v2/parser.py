"""블랙북 v2 파서 — 하이브리드 전략 + 과(강) 단위 그룹핑.

- 문제 섹션: core.extract + core.structure + build_ir (구조 인식)
- 어휘/정답 섹션: 검증된 v1 파서(engines.blackbook.kind_parser) 재사용

파일 분류는 파일명(`Part1 문제`)이 있으면 그대로 쓰고, 없으면 원고 구조로
판정한다(W38 — `블랙북01_문제_교과서_1과.docx` 처럼 Part 표기가 없는 원고가
통째로 버려지던 문제). 과 번호가 있으면 오름차순으로, 없으면 업로드 순서로
`lessons`를 만들어 [어휘 → 문제]가 과 단위로 반복되게 한다.

v1(engines/blackbook)은 무변경.
"""
import os
import unicodedata

from engines.blackbook.kind_parser import (
    _sniff_paragraphs, book_title_of, classify_file, classify_filename_reason,
    has_part_token, lesson_of, parse_by_kind, subtitle_of,
)
from engines.mockexam_v2.parser import build_ir, extract_file_paragraphs

_PART1_LABEL = "PART1"
_PART2_LABEL = "PART2"


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _clean_name(path):
    name = _nfc(os.path.basename(path))
    for pre in ("manuscript_", "answers_"):
        if name.startswith(pre):
            return name[len(pre):]
    return name


def _new_lesson(num, label):
    return {"num": num, "label": label, "subtitle": "", "book": None,
            "vocab": [], "problems": None, "answers": []}


def parse_files(paths, log=None):
    """업로드 파일들 → 과 단위 섹션.

    반환: {
      "lessons": [{num, label, subtitle, vocab, problems(IR), answers}, ...],
      # 하위호환 (검수·코퍼스 테스트용)
      "problems_p1", "problems_p2", "vocab", "answers_p1", "answers_p2",
      "unmatched", "warnings"
    }
    """
    out = {"lessons": [], "problems_p1": None, "problems_p2": None,
           "vocab": [], "answers_p1": [], "answers_p2": [],
           "unmatched": [], "warnings": []}

    def _log(msg):
        if callable(log):
            log(msg)

    buckets = {}       # key -> lesson dict
    order = []         # key 등장 순서 (과 표기 없는 원고용)

    def _bucket(key, num, label):
        if key not in buckets:
            buckets[key] = _new_lesson(num, label)
            order.append(key)
        return buckets[key]

    for path in sorted(paths):
        name = _clean_name(path)
        texts = _sniff_paragraphs(path)
        kind = classify_file(path, texts)
        if kind is None:
            reason = classify_filename_reason(name)
            out["unmatched"].append(name)
            out["warnings"].append(f"분류 실패: {name} ({reason} / 원고 구조로도 판정 불가)")
            _log(f"[경고] 원고 분류 실패(무시됨): {name} — {reason}")
            continue

        # 파일명에 Part 표기가 있는 구형 원고는 Part 단위로 묶는다.
        # (어휘 원고 안의 `<3과 본문1>` 헤더 때문에 PART1이 쪼개지면 안 됨)
        legacy = has_part_token(name)
        is_part2 = kind.startswith("part2_")
        num = None if (legacy or is_part2) else lesson_of(path, texts)
        if is_part2:
            key, label = _PART2_LABEL, _PART2_LABEL
        elif legacy:
            key, label = _PART1_LABEL, _PART1_LABEL
        elif num is not None:
            key, label = f"L{num}", f"{num}과"
        else:
            key, label = "L?", ""
        lesson = _bucket(key, num, label)

        book = book_title_of(texts)
        if book and not lesson["book"]:
            lesson["book"] = book

        if kind.endswith("_problem"):
            doc = build_ir(extract_file_paragraphs(path), log=log)
            if lesson["problems"] is None:
                lesson["problems"] = doc
            else:
                lesson["problems"]["items"].extend(doc["items"])
            _log(f"[v2] {label or kind} 문제: {name} → {len(doc['items'])}문항")
        elif kind == "part1_vocab":
            items = parse_by_kind(kind, path)
            lesson["vocab"].extend(items)
            _log(f"[v2] {label or kind} 어휘: {name} → {len(items)}본문")
        else:   # part1_answer / part2_answer
            items = parse_by_kind(kind, path)
            lesson["answers"].extend(items)
            _log(f"[v2] {label or kind} 해설: {name} → {len(items)}개")

    # 과 번호 있는 것 먼저(오름차순), 없는 것은 등장 순서, PART2는 맨 뒤
    def _sort_key(key):
        les = buckets[key]
        if key == _PART2_LABEL:
            return (2, 0, order.index(key))
        if les["num"] is None:
            return (1, 0, order.index(key))
        return (0, les["num"], order.index(key))

    for key in sorted(order, key=_sort_key):
        les = buckets[key]
        if not (les["vocab"] or les["problems"] or les["answers"]):
            continue
        les["subtitle"] = (les["book"] or "") if les["num"] is None \
            else subtitle_of(les["book"], les["num"])
        out["lessons"].append(les)

    # ── 하위호환 필드 (검수 게이트·코퍼스 테스트가 참조) ────────────────
    for les in out["lessons"]:
        if les["label"] == _PART2_LABEL:
            if les["problems"]:
                out["problems_p2"] = les["problems"]
            out["answers_p2"].extend(les["answers"])
            continue
        out["vocab"].extend(les["vocab"])
        out["answers_p1"].extend(les["answers"])
        if les["problems"]:
            if out["problems_p1"] is None:
                # 과별 IR을 그대로 참조하면 이후 extend가 원본까지 오염된다
                out["problems_p1"] = dict(les["problems"])
                out["problems_p1"]["items"] = list(les["problems"]["items"])
            else:
                out["problems_p1"]["items"].extend(les["problems"]["items"])

    _log("[v2] 과 구성: " + ", ".join(
        f"{(l['label'] or '(과 미표기)')} 어휘{len(l['vocab'])}/문제"
        f"{len(l['problems']['items']) if l['problems'] else 0}/해설{len(l['answers'])}"
        for l in out["lessons"]) or "[v2] 과 없음")
    return out
