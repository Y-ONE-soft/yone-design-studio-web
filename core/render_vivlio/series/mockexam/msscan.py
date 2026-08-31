# -*- coding: utf-8 -*-
"""원고 규칙 계측 — 학교별 동형 원고(hwp/hwpx/docx)가 무엇을 주고 무엇을 안 주는지.

기출 정본이 '결과의 진실'이라면, 원고는 '입력의 진실'이다. 학교마다 원고 관행이
달라서(번호를 아예 안 쓰는 학교, `서술형1.` 을 쓰는 학교, dingbat `➀` 를 쓰는 학교
…) 같은 파서로 같은 결과가 나오지 않는다. 이 모듈은 원고 한 부에서 아래를 센다.

  머리 메타       "선택형: 23문항" / "객관식 27개 서답형 3개" / 없음
  문항 번호       원고가 주는가(`1.`) 없는가(조판이 자동번호)
  선지 마커       ① / ➀(U+2780) / ⓐ / (A) / ⅰ
  서술형 표기      서술형N. / 서답형N. / [서답형 N] / 없음(구조로만)
  묶음 표기       [N~M] / 【 】 / 없음(공유 지문 = '윗글' 참조로만)
  보기·조건        <보기> <조건> <요약문> [보기] 표기와 개수
  출처 태그       [25년 3월 21번] / [N과 추가지문]
  답란            답: ____ / (A) ____ / [답]
  화살표          ↓ ⇓ ⇩ → 코드포인트

산출은 증거다. 판정(프로파일)은 사람이 확정한다.
"""
import collections
import os
import re
import unicodedata


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


RE_META = {
    "선택형: N문항": re.compile(r"선택형\s*[::]\s*\d+\s*문항"),
    "서술형: N문항": re.compile(r"서술형\s*[::]\s*\d+\s*문항"),
    "서답형: N문항": re.compile(r"서답형\s*[::]\s*\d+\s*문항"),
    "총계: N문항": re.compile(r"총계\s*[::]\s*\d+\s*문항"),
    "객관식 N …서(답|술)형 M": re.compile(r"객(?:관식)?\s*\d+.{0,8}서[답술]형\s*\d+"),
    "선택형 N": re.compile(r"(?m)^\s*선택형\s*\d+\s*$"),
    "제목줄(학교+회차)": re.compile(r"(?m)^\s*[가-힣]+고?\d?\s*동형\s*\d+회\s*$"),
}
RE_CHOICE = {
    "①(U+2460)": re.compile(r"[①-⑤]"),
    "➀(U+2780)": re.compile(r"[➀-➄]"),
    "㉠(U+3260)": re.compile(r"[㉠-㉭]"),
    "ⓐ(U+24D0)": re.compile(r"[ⓐ-ⓩ]"),
    "(A)": re.compile(r"\([A-E]\)"),
    "ⅰ": re.compile(r"[ⅰ-ⅴ]"),
    "HWP원문자(U+F000대)": re.compile(r"[-]"),
}
RE_SRV = {
    "서술형N.": re.compile(r"(?m)^\s*서술형\s*\d+\s*[.)]"),
    "서답형N.": re.compile(r"(?m)^\s*서답형\s*\d+\s*[.)]"),
    "[서답형N]": re.compile(r"\[\s*서답형\s*\d+\s*(?:번)?\s*\]"),
    "[서술형N]": re.compile(r"\[\s*서술형\s*\d+\s*(?:번)?\s*\]"),
    "〔서술형N〕": re.compile(r"〔\s*서[술답]형\s*\d+\s*〕"),
    "【서답형N】": re.compile(r"【[^】]*서[술답]형[^】]*】"),
}
RE_GROUP = {
    "[N~M]": re.compile(r"(?m)^\s*\[\s*\d+\s*[~\-–]\s*\d+\s*\]"),
    "【…】": re.compile(r"【[^】\n]{1,40}】"),
    "<…번…>": re.compile(r"<[^<>\n]{0,30}번[^<>\n]{0,30}>"),
    "묶음지시문": re.compile(r"다음 글을 읽고\s*,?\s*(?:물음|질문)에 답하시오"),
}
RE_BOX = {
    "<보기>": re.compile(r"<\s*보\s*기\s*>"),
    "[보기]": re.compile(r"\[\s*보\s*기\s*\]"),
    "<조건>": re.compile(r"<\s*조\s*건\s*>"),
    "[조건]": re.compile(r"\[\s*조\s*건\s*\]"),
    "<요약문>": re.compile(r"<\s*요약문?\s*>"),
    "[정답 작성 안내]": re.compile(r"\[\s*정답\s*작성\s*안내\s*\]"),
    "@TABLE/표": re.compile(r"(?m)^@TABLE"),
}
RE_SOURCE = {
    "[YY년 M월 N번]": re.compile(r"\[\s*\d{2}\s*년\s*\d{1,2}\s*월[^\]]{0,20}\]"),
    "[N과 …지문]": re.compile(r"\[\s*\d+\s*과[^\]]{0,20}지문\s*\]"),
    "[YYYY. M. N번]": re.compile(r"\[\s*\d{4}\s*\.[^\]]{0,20}번[^\]]{0,6}\]"),
}
RE_ANSFIELD = {
    "답:____": re.compile(r"(?m)^\s*답\s*[:：]"),
    "[답]": re.compile(r"\[\s*답\s*\]"),
    "(A) ____": re.compile(r"\([A-E]\)\s*_{4,}"),
    "밑줄기입란": re.compile(r"_{8,}"),
    "→ 고친": re.compile(r"→\s*\(?\s*고친"),
}
RE_ARROWS = re.compile(r"[←-⇿⬀-⬏]")
RE_NUMBERED_LINE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.)]\s*\S")


def scan_text(paras):
    """단락 텍스트 리스트 → 원고 규칙 증거 dict."""
    lines = [_nfc(p) for p in paras]
    full = "\n".join(lines)

    def census(table, limit=4):
        out = {}
        for k, pat in table.items():
            hits = pat.findall(full)
            if hits:
                seen, samp = set(), []
                for m in pat.finditer(full):
                    s = m.group(0).strip()
                    if s not in seen:
                        seen.add(s)
                        samp.append(s)
                    if len(samp) >= limit:
                        break
                out[k] = {"n": len(hits), "예": samp}
        return out

    rec = {
        "단락수": len(lines),
        "머리메타": census(RE_META),
        "선지마커": census(RE_CHOICE, 3),
        "서술형표기": census(RE_SRV),
        "묶음표기": census(RE_GROUP, 3),
        "보기조건": census(RE_BOX, 3),
        "출처태그": census(RE_SOURCE, 3),
        "답란": census(RE_ANSFIELD, 3),
    }
    # 번호가 붙은 줄 비율 — 원고가 번호를 주는지 판정
    numbered = RE_NUMBERED_LINE.findall(full)
    rec["번호줄수"] = len(numbered)
    rec["번호부여"] = len(numbered) >= 8

    arrows = collections.Counter()
    for ch in full:
        if RE_ARROWS.match(ch):
            arrows["U+%04X %s" % (ord(ch), ch)] += 1
    rec["화살표"] = dict(arrows.most_common(6))

    # 머리 5줄(메타 영역 육안 확인용)
    rec["머리5줄"] = [l[:60] for l in lines[:5]]
    rec["꼬리3줄"] = [l[:80] for l in lines[-3:]]
    return rec


def scan_file(path):
    from engines.mockexam_v2.parser import extract_file_paragraphs
    paras = extract_file_paragraphs(path)
    rec = scan_text([p.get("text", "") for p in paras])
    rec["file"] = _nfc(os.path.basename(path))
    return rec


def scan_dir(root):
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() not in (".hwp", ".hwpx", ".docx"):
                continue
            try:
                out.append(scan_file(os.path.join(dirpath, f)))
            except Exception as e:
                out.append({"file": _nfc(f), "error": str(e)[:200]})
    return out


if __name__ == "__main__":
    import json
    import sys
    t = sys.argv[1]
    res = scan_dir(t) if os.path.isdir(t) else [scan_file(t)]
    print(json.dumps(res, ensure_ascii=False, indent=1))
