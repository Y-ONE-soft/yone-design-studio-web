"""화이트북 v2 인-리포 파서 — 섹션 인식 구조화 (W35 배치 C).

배경 (docs/인식지점_전수감사.md §3.1·§7 리스크 4위·§9 C안):
외부 parse_whitebook.py 의 SECTION_HEADERS 는 발문 문구 리터럴 5종이라
토씨 하나('해석'→'뜻')에 섹션이 통째로 침묵 소멸(직전 섹션에 흡수)했다
(감사 실증 #7). whitebook_v2 verify 도 플랜 기준 대조라 파서 계층 누락은
미검출이었다.

전환 방식 (W31 방법론 계승):
  1선(구조 신호): 라인 선두 `[A-E]` + 구분자(`.` / `)`) + 한국어 발문(한글 포함)
                  — 발문 문구 자체에는 의존하지 않는다.
  프라이어:      기존 발문 문구 리터럴(스냅샷 SECTION_HEADERS — 데이터 테이블)
                  은 하위호환 하한으로 유지. 구조 신호가 리터럴의 상위집합이므로
                  기존 인식분은 100% 그대로다 (부분집합 가드 테스트).
  침묵 금지:     Day 는 A~E 5섹션 고정 구조 — 결손/중복 시 WhitebookSectionError
                  ([오류]) 로 조판 중단. 직전 섹션 침묵 흡수 금지.

본체 파싱(A~E 각 섹션·정답·Day 분할)은 리포 스냅샷
engines/whitebook/external/parse_whitebook.py 를 그대로 재사용한다
(byte 파리티 — 골든 2케이스 diff 0). v1(engines/whitebook)은 종전대로 외부
경로 subprocess — 운영 무변경.
"""
import os
import re

from engines.whitebook.external import parse_whitebook as _snap

# 섹션 문자 고정 구조 (화이트북 Day 는 항상 A~E 5섹션)
SECTION_LETTERS = ("A", "B", "C", "D", "E")

# 구조 신호: 라인 선두 섹션 문자 + 구분자. 발문 문구 무관.
_RE_SECTION_STRUCT = re.compile(r"^([A-E])[.)]\s*(.*)$")
_RE_KOREAN = re.compile(r"[가-힣]")

# 프라이어(데이터 테이블): 기존 발문 문구 리터럴 — 스냅샷의 SECTION_HEADERS 공유.
# 새 표기가 와도 여기 추가할 필요는 없다(구조 신호가 1선). 하위호환 하한 역할.
SECTION_PHRASE_PRIORS = dict(_snap.SECTION_HEADERS)


class WhitebookSectionError(ValueError):
    """Day 내 A~E 섹션 결손/중복 — 침묵 소멸 금지 ([오류] 조판 중단)."""


def match_section_header(line):
    """섹션 헤더면 섹션 문자('A'~'E'), 아니면 None.

    구조 신호 1선: `[A-E]` + `.`/`)` + 한국어 발문(한글 1자 이상).
    한글 조건은 영어 본문 오탐 방지(예: 'A. significant' 같은 항목 라인).
    프라이어: 알려진 발문 문구 리터럴이면 무조건 헤더 (하위호환 하한).
    """
    stripped = (line or "").strip()
    m = _RE_SECTION_STRUCT.match(stripped)
    if not m:
        return None
    letter, rest = m.group(1), m.group(2)
    prior = SECTION_PHRASE_PRIORS.get(letter)
    if prior is not None and prior.match(stripped):
        return letter
    if _RE_KOREAN.search(rest):
        return letter
    return None


def split_by_sections_struct(day_lines, day_num=None):
    """A~E 섹션 분할 (구조 신호 1선 + 발문 프라이어 + 침묵 금지).

    스냅샷 split_by_sections 와 동일한 반환 형태({letter: [lines]})이되,
    결손/중복 시 WhitebookSectionError 를 던진다 — 직전 섹션 침묵 흡수 금지.
    """
    sections = {}
    current = None
    day_label = f"Day {day_num}" if day_num is not None else "Day ?"
    for line in day_lines:
        letter = match_section_header(line)
        if letter is not None:
            if letter in sections:
                raise WhitebookSectionError(
                    f"[오류] {day_label}: {letter} 섹션 헤더 중복 — "
                    f"원고 구조 확인 필요 (중복 라인: {line.strip()[:60]!r})")
            current = letter
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    missing = [c for c in SECTION_LETTERS if c not in sections]
    if missing:
        raise WhitebookSectionError(
            f"[오류] {day_label}: 섹션 결손 {'/'.join(missing)} "
            f"(인식된 섹션: {'/'.join(sorted(sections)) or '없음'}) — "
            "섹션 헤더가 인식되지 않으면 해당 섹션이 직전 섹션에 흡수되므로 "
            "침묵 진행하지 않고 중단합니다. 원고의 A~E 발문 라인을 확인하세요.")
    return sections


def parse_workbook_files(hwpx_files, answer_files=None, log=print):
    """스냅샷 parse_workbook_files 와 동일 파이프라인 + 구조 섹션 분할.

    차이는 두 가지뿐:
      - split_by_sections → split_by_sections_struct (구조 1선 + 침묵 금지)
      - print → log 콜백 (Flask 잡 로그 합류)
    반환 dict 는 스냅샷과 동일 구조 (골든 파리티 계약).
    """
    all_days_content = {}
    all_days_answers = {}

    for hwpx_path in hwpx_files:
        log(f"[원고 파싱] {os.path.basename(hwpx_path)}")
        lines = _snap.extract_lines_from_hwpx(hwpx_path)
        day_groups = _snap.split_by_days(lines)
        # 배치 G (W37): Day 분할 침묵 가시화 — 'Day N' 단독 라인 미인식이면
        # 원고 전체가 조용히 버려지던 지점 ([경고], 동작 무변경).
        if not day_groups and any(l.strip() for l in lines):
            log(f"[경고] {os.path.basename(hwpx_path)}: 'Day N' 헤더가 하나도 "
                f"인식되지 않아 내용({sum(1 for l in lines if l.strip())}라인)이 "
                "전부 무시됩니다. Day 표기 형식을 확인하세요.")
        for day_num, day_lines in day_groups:
            sections = split_by_sections_struct(day_lines, day_num=day_num)
            all_days_content[day_num] = {
                "A": _snap.parse_section_a(sections.get("A", [])),
                "B": _snap.parse_section_b(sections.get("B", [])),
                "C": _snap.parse_section_c(sections.get("C", [])),
                "D": _snap.parse_section_d(sections.get("D", [])),
                "E": _snap.parse_section_e(sections.get("E", [])),
            }
            c = all_days_content[day_num]
            log(f"  Day {day_num}: A={len(c['A'])} B={len(c['B'])} "
                f"C={len(c['C'])} sets D={len(c['D']['items'])} items "
                f"E={len(c['E'])}")

    if answer_files:
        for ans_path in answer_files:
            log(f"[정답 파싱] {os.path.basename(ans_path)}")
            lines = _snap.extract_lines_from_hwpx(ans_path)
            day_groups = _snap.split_by_days(lines)
            if not day_groups and any(l.strip() for l in lines):
                log(f"[경고] {os.path.basename(ans_path)}: 정답 hwpx에서 "
                    "'Day N' 헤더가 하나도 인식되지 않아 정답 전체가 무시됩니다.")
            for day_num, day_lines in day_groups:
                all_days_answers[day_num] = _snap.parse_answer_day(day_lines)
                ans = all_days_answers[day_num]
                log(f"  Day {day_num}: A={len(ans['A'])} B={len(ans['B'])} "
                    f"C={len(ans['C'])} D={len(ans['D'])} E={len(ans['E'])}")
                # 배치 G (W37): 정답 섹션 마커 '▶ X' 침묵 가시화 — 스냅샷
                # ANSWER_SECTION_PAT 미매치 섹션은 조용히 빈 리스트로 남아
                # 하류(verify 스토리수/단어 보존)에서야 드러났다 ([경고]만,
                # 스냅샷·동작 무변경. W35 미해결 (2)).
                empty_secs = [s for s in SECTION_LETTERS if not ans.get(s)]
                if empty_secs:
                    marker_like = [
                        l.strip() for l in day_lines
                        if "▶" in l and not any(
                            p.match(l.strip())
                            for p in _snap.ANSWER_SECTION_PAT.values())
                    ]
                    log(f"[경고] Day {day_num} 정답: 섹션 "
                        f"{'/'.join(empty_secs)} 이 비어 있음 — '▶ X' 마커 "
                        "미인식 또는 원고 결손 가능.")
                    for ml in marker_like[:3]:
                        log(f"    미매치 '▶' 후보 라인: {ml[:50]!r}")

    result = {"days": []}
    for day_num in sorted(all_days_content.keys()):
        result["days"].append({
            "day_num": day_num,
            "content": all_days_content[day_num],
            "answers": all_days_answers.get(day_num, {}),
        })
    return result
