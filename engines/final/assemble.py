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
import re

from engines.final import scope_source as S
from engines.final import manuscript_locate as L
from engines.final.grammar_word_parser import (
    find_deeplearning_grammar_files, find_ebs_grammar_files,
    find_grammar_word_files,
    find_mockexam_grammar_files, parse_grammar_word,
)

# 토큰 종류 → 어법수정 docx 를 찾는 길
SCOPE_TYPE = {"lesson": "textbook", "olpo": "ebs_olympos",
              "rp": "ebs_readingpower", "teuk": "ebs_olympos",
              "bare": "ebs_olympos", "mock": "mockexam"}


def _files_for(token, detail, base, grade, log):
    """이 토큰의 어법수정 docx 들 → [(경로, 강 번호 or None)]."""
    kind = token[0]
    if kind == "lesson":
        subj, pub = detail.get("subject"), detail.get("publisher")
        if not (subj and pub):
            log("  [어법] 과목·출판사를 몰라 건너뜀 — %s" % S.token_text(token))
            return []
        # ⚠ 추가본문(딥러닝)은 **다른 파일**이다. 같은 찾기 함수를 쓰면 과 폴더의
        #   파일이 딥러닝 몫으로 먼저 잡히고, 그 뒤 본디 과가 통째로 사라진다.
        if detail.get("deeplearning"):
            return [(f, None) for f in
                    (find_deeplearning_grammar_files(base, subj, pub,
                                                     log=log) or [])]
        return [(f, None) for f in
                (find_grammar_word_files(base, subj, pub, [str(token[1])],
                                         log=log) or [])]
    if kind == "mock":
        got = find_mockexam_grammar_files(
            base, "%d년%d월" % (token[1], token[2]), grade, log=log) or []
        return [(f[0], None) if isinstance(f, tuple) else (f, None)
                for f in got]
    if kind in ("olpo", "rp", "bare"):
        name = {"olpo": "올림포스", "rp": "리딩파워"}.get(kind, "수능특강")
        got = find_ebs_grammar_files(base, "%s%d강" % (name, token[1]),
                                     log=log, grade=grade) or []
        return [f if isinstance(f, tuple) else (f, None) for f in got]
    return []


def grammar(scope, base, grade, log=lambda m: None):
    """시험범위 → (`어법수정` 평평한 목록, `어법_헤더`).

    `어법수정` 은 [헤더, 본문, 헤더, 본문, …] 꼴이다(엔진과 같은 모양).

    고1·고2 는 어법수정 docx 가 폴더 밖에도 흩어져 있어 **엔진의 찾기 함수**를
    그대로 쓰고, 고3 은 원고 폴더 안 `5. 어법선택` 한 장이라 그것을 읽는다.
    라벨은 어느 쪽이든 `to_final_label` **한 규칙**으로만 만든다 — 규칙이
    갈라지면 같은 지문이 섹션마다 다른 이름을 갖는다.
    """
    from engines.final import manuscript as M
    lines, headers, seen = [], [], set()
    g = int("".join(c for c in str(grade) if c.isdigit()) or 0)
    for d, spec in S.folders(scope, base, grade=g, log=log):
        kind = spec.get("kind")
        blocks = []
        if kind in ("teuk", "test"):
            blocks = [(b["raw"], b["text"]) for b in M.read(d, "grammar")[0]]
        else:
            t = _token_of(spec)
            for path, _unit in _files_for(t, spec, base, grade, log):
                if path in seen:
                    continue
                seen.add(path)
                # 엔진의 파서 대신 **원고 리더 하나**로 읽는다 —
                # 엔진 파서는 어떤 교과서 파일(YBM)에서 지문을 통째로
                # 놓쳤다(블록 1개, 헤더 '본문'). 형태는 다 같은 꼴이다.
                for blk in M.read_grammar(path):
                    blocks.append((blk["raw"], blk["text"]))
        for raw, text in blocks:
            lab = L.to_final_label(spec, re.sub(r"^\s*\d+\.\s*", "", raw))
            if not lab or lab in headers or not S.in_scope(lab, scope):
                continue
            headers.append(lab)
            lines += [lab, text]
    return lines, headers


def _token_of(spec):
    k = spec.get("kind")
    if k == "lesson":
        return ("lesson", spec["lesson"])
    if k == "mock":
        return ("mock", spec["year"], spec["month"])
    return (k, spec.get("unit"))


def vocab(school, grade, exam_period, scope=None, order=None,
          log=lambda m: None):
    """중요어휘(고1·고2) — 구글시트. 돌려주는 것: (왼쪽 글, 오른쪽 글).

    시트가 정본이라 원고에서 유도할 수 없다(선생님이 고른 부분집합).
    고3 은 시트에 없다 — 빈 글을 돌려준다(엔진과 같다).

    ⚠ 시트에서 받은 그대로 쓰면 안 된다. 엔진이 하던 두 가지를 그대로 한다:
      · `>>내용요약` 앞 빈 줄이 소스마다 제멋대로라 두 줄로 맞춘다
      · 영어 사이에 낀 `式` 는 `─` 가 깨진 것이다(낱말 뜻의 한자는 그대로)
    """
    if grade not in ("고1", "고2"):
        return "", ""
    from engines.final.vocab_fetcher import fetch_vocab_for_school
    olpo = rp = None
    if scope:
        olpo = sorted({t[1] for t in scope["tokens"] if t[0] == "olpo"}) or None
        rp = sorted({t[1] for t in scope["tokens"] if t[0] == "rp"}) or None
        # 모의고사 차례 — 다른 섹션과 같은 오름차순(YYMM)
        if order is None:
            order = sorted({("%02d" % t[1], "%02d" % t[2])
                            for t in scope["tokens"] if t[0] == "mock"})
    got = fetch_vocab_for_school(school, grade, log=log,
                                 olpo_lectures=olpo, rp_lectures=rp,
                                 workbook_order=order or None,
                                 exam_period=exam_period) or {}
    out = []
    for t in (got.get("left_text", ""), got.get("right_text", "")):
        t = re.sub(r"\s*>>내용요약", "\n\n\n>>내용요약", t)
        t = re.sub("(?<=[\x21-\x7e])\\s+式\\s+(?=[\x21-\x7e])", " \u2500 ", t)
        out.append(t)
    return out[0], out[1]
