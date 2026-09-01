# -*- coding: utf-8 -*-
"""**시험범위만으로** 어법수정·중요어휘를 모은다 — 되수확본 없이.

지금까지 빌더는 이미 만든 `content.json` 에서 이 둘을 실어 왔다. 원고와
시트가 정본인데도 그랬던 건, 엔진의 파싱 단계를 한 번 돌려야 이 둘이
나왔기 때문이다. 그 배선을 끊는 자리다.

  · 어법수정  교재·EBS·모의 폴더의 **2열 표 docx** (`grammar_word_parser`)
  · 중요어휘  구글시트 (`vocab_fetcher`) — 선생님이 고른 부분집합이라
              원고에서 유도할 수 없다. 여긴 시트가 정본이다.

엔진과 **같은 함수**를 부른다(찾기·파싱·헤더 변환). 다른 것은 그 함수를
무엇으로 몰아 주느냐뿐 — 워크북 파일 이름이 아니라 시험범위 토큰이다.
"""
import os

from engines.final import scope_source as S
from engines.final.engine import _convert_grammar_header
from engines.final.grammar_word_parser import (
    find_ebs_grammar_files, find_grammar_word_files,
    find_mockexam_grammar_files, parse_grammar_word,
)

# 토큰 종류 → 엔진이 쓰는 scope 유형(헤더 변환이 이걸 본다)
SCOPE_TYPE = {"lesson": "textbook", "olpo": "ebs_olympos",
              "rp": "ebs_readingpower", "teuk": "ebs_olympos",
              "bare": "ebs_olympos", "mock": "mockexam"}


def _files_for(token, detail, base, grade, raw, log):
    """이 토큰의 어법수정 docx 들 → [(경로, 강 번호 or None)]."""
    kind = token[0]
    if kind == "lesson":
        subj, pub = detail.get("subject"), detail.get("publisher")
        if not (subj and pub):
            log("  [어법] 과목·출판사를 몰라 건너뜀 — %s" % S.token_text(token))
            return []
        return [(f, None) for f in
                (find_grammar_word_files(base, subj, pub, [str(token[1])],
                                         log=log) or [])]
    if kind == "mock":
        got = find_mockexam_grammar_files(
            base, "%d년%d월" % (token[1], token[2]), grade, log=log) or []
        return [(f[0], None) if isinstance(f, tuple) else (f, None)
                for f in got]
    if kind in ("olpo", "rp", "teuk", "bare"):
        name = {"olpo": "올림포스", "rp": "리딩파워"}.get(kind, "수능특강")
        got = find_ebs_grammar_files(base, "%s%d강" % (name, token[1]),
                                     log=log, grade=grade) or []
        return [f if isinstance(f, tuple) else (f, None) for f in got]
    return []


def grammar(scope, base, grade, log=lambda m: None):
    """시험범위 → (`어법수정` 평평한 목록, `어법_헤더`).

    `어법수정` 은 [헤더, 본문, 헤더, 본문, …] 꼴이다(엔진과 같은 모양).
    범위 안인 지문만 남긴다 — 판정은 `scope_source.in_scope()` 하나로 한다.
    """
    lines, headers, seen = [], [], set()
    for t in scope["tokens"]:
        d = scope.get("detail", {}).get(t) or {}
        stype = SCOPE_TYPE.get(t[0])
        if not stype:
            continue
        stext = S.token_text(t)
        for path, unit in _files_for(t, d, base, grade, scope.get("raw", ""),
                                     log):
            if path in seen:
                continue
            seen.add(path)
            for blk in parse_grammar_word(path, log=log) or []:
                lab = _convert_grammar_header(
                    blk.get("header", ""), stext, stype,
                    ebs_lecture=(unit if unit is not None else t[1]
                                 if len(t) > 1 else None))
                if not lab or lab in headers:
                    continue
                if not S.in_scope(lab, scope):
                    continue
                headers.append(lab)
                lines += [lab, blk.get("text", "")]
    return lines, headers


def vocab(school, grade, exam_period, order=None, log=lambda m: None):
    """중요어휘(고1·고2) — 구글시트. 돌려주는 것: (왼쪽 글, 오른쪽 글).

    고3 은 시트에 없다(엔진과 같다) — 빈 글을 돌려준다.
    """
    if grade not in ("고1", "고2"):
        return "", ""
    from engines.final.vocab_fetcher import fetch_vocab_for_school
    got = fetch_vocab_for_school(school, grade, log=log,
                                 workbook_order=order,
                                 exam_period=exam_period) or {}
    return got.get("left_text", ""), got.get("right_text", "")
