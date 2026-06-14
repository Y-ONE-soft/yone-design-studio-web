#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_listening_hwpx.py — 듣기 원고(hwpx)를 포켓북 조판용 텍스트로 변환.

사용법:
    python3 parse_listening_hwpx.py <input.hwpx> <output.txt>

출력 형식 (engines/pocketbook/jsx/run.jsx 의 4.5 듣기 배치가 기대하는 형식):
    ===SECTION===<섹션명>
    ===PASSAGE===<지문명>
    ===SCRIPT===
    <영어 스크립트 줄들>
    ===KOREAN===
    <한글 해석 줄들>

입력 양식 규칙:
    ===== 교재 Lesson N =====   → 섹션
    [지문 제목]                  → 지문 (앞 '[' , 뒤 ']' 제거. 닫는 ']' 누락 허용)
    [Script]                     → 영어 스크립트 시작
    [해석]                       → 한글 해석 시작
    그 외 줄                     → 현재 모드(스크립트/해석)의 본문
    주의) [Telephone rings.] 처럼 스크립트/해석 '본문 안'의 대괄호 줄은 지문
    제목이 아니라 본문이다. 다음에 [Script]/[해석]가 곧장 오지 않으면(= 다른
    대괄호/섹션을 먼저 만나면) 본문으로 처리한다(lookahead).
    또한 [Script] 마커가 생략된 지문도 있으므로, 제목 직후 첫 본문이 나오면
    ===SCRIPT=== 를 자동 삽입한다.
"""
import sys
import os
import re
import zipfile
import html

SCRIPT_MARK = "[Script]"
KOREAN_MARK = "[해석]"


def log(msg):
    sys.stderr.write(str(msg) + "\n")


def read_section_xml(hwpx_path):
    """hwpx(zip)에서 Contents/section*.xml 본문을 순서대로 이어붙여 반환."""
    parts = []
    with zipfile.ZipFile(hwpx_path) as z:
        names = [n for n in z.namelist()
                 if re.search(r'Contents/section\d+\.xml$', n)]
        names.sort()
        for n in names:
            parts.append(z.read(n).decode("utf-8", "ignore"))
    return "".join(parts)


def extract_paragraphs(xml):
    """<hp:p> 단위로, 각 문단의 <hp:t> 텍스트를 이어붙여 한 줄로 만든다."""
    out = []
    for p in re.findall(r'<hp:p\b.*?</hp:p>', xml, re.S):
        # 문단 내 줄바꿈/탭 인라인 요소는 공백으로
        p2 = re.sub(r'<hp:lineBreak\b[^>]*/?>', ' ', p)
        p2 = re.sub(r'<hp:tab\b[^>]*/?>', ' ', p2)
        ts = re.findall(r'<hp:t\b[^>]*>(.*?)</hp:t>', p2, re.S)
        txt = html.unescape("".join(ts))
        # 연속 공백 정리(줄바꿈 치환 흔적)
        txt = re.sub(r'[ \t]+', ' ', txt)
        out.append(txt.strip())
    return out


def is_section(t):
    return t.startswith("=====")


def section_name(t):
    return t.strip("= ").strip()


def passage_title(t):
    """'[제목' 또는 '[제목]' → '제목'."""
    s = t[1:] if t.startswith("[") else t
    if s.endswith("]"):
        s = s[:-1]
    return s.strip()


def lookahead_kind(paras, idx):
    """paras[idx]의 대괄호 줄이 '지문제목(title)'인지 '본문(inline)'인지 판정.
    다음 문단부터 살펴, [Script]/[해석]를 먼저 만나면 title,
    다른 대괄호/섹션을 먼저 만나면 inline. (일반 텍스트는 건너뜀 — 제목 직후
    [Script] 가 생략된 스크립트 본문일 수 있으므로.)"""
    for j in range(idx + 1, len(paras)):
        tj = paras[j]
        if tj == "":
            continue
        if tj == SCRIPT_MARK or tj == KOREAN_MARK:
            return "title"
        if tj.startswith("[") or tj.startswith("====="):
            return "inline"
    return "title"


def parse(paras):
    out = []
    stats = {"section": 0, "passage": 0, "script": 0, "korean": 0}
    mode = [None]  # None / "script_pending" / "script" / "korean"

    def ensure_script():
        if mode[0] == "script_pending":
            out.append("===SCRIPT===")
            mode[0] = "script"

    for i, t in enumerate(paras):
        if t == "":
            continue
        if is_section(t):
            out.append("===SECTION===" + section_name(t))
            stats["section"] += 1
            mode[0] = None
            continue
        if t == SCRIPT_MARK:
            out.append("===SCRIPT===")
            mode[0] = "script"
            continue
        if t == KOREAN_MARK:
            out.append("===KOREAN===")
            mode[0] = "korean"
            continue
        if t.startswith("["):
            # 스크립트 본문 안의 대괄호 지시문은 무조건 본문
            if mode[0] == "script":
                out.append(t)
                stats["script"] += 1
                continue
            kind = lookahead_kind(paras, i)
            if kind == "title":
                out.append("===PASSAGE===" + passage_title(t))
                stats["passage"] += 1
                mode[0] = "script_pending"
                continue
            # 본문 지시문 (해석 모드 등)
            if mode[0] == "korean":
                out.append(t)
                stats["korean"] += 1
            else:
                ensure_script()
                out.append(t)
                stats["script"] += 1
            continue
        # 일반 텍스트
        if mode[0] == "korean":
            out.append(t)
            stats["korean"] += 1
        else:
            ensure_script()
            out.append(t)
            stats["script"] += 1
    return out, stats


def main():
    if len(sys.argv) < 3:
        log("사용법: parse_listening_hwpx.py <input.hwpx> <output.txt>")
        return 2
    hwpx_path, out_path = sys.argv[1], sys.argv[2]
    if not os.path.exists(hwpx_path):
        log("입력 hwpx 없음: " + hwpx_path)
        return 1
    try:
        xml = read_section_xml(hwpx_path)
    except Exception as e:
        log("hwpx 읽기 오류: " + repr(e))
        return 1
    paras = extract_paragraphs(xml)
    out, stats = parse(paras)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
        f.write("\n")
    log("섹션 %d개, 지문 %d개, 스크립트 %d줄, 해석 %d줄"
        % (stats["section"], stats["passage"], stats["script"], stats["korean"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
