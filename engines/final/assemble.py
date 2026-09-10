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
import json
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
        elif _fix_files(d):
            # ⚠ 어법수정 원고가 **그 강 폴더 안에** 있으면 그것이 정본이다.
            #   엔진의 찾기 함수는 판을 학년으로 찍어 고1 2학기가 쓰는
            #   `독해 기본2` 를 `기본1` 에서 뒤졌다(광문1 실측: 1·6·7강 미발견,
            #   나머지는 엉뚱한 판). 이미 찾아 둔 폴더를 믿는다.
            for path in _fix_files(d):
                if path in seen:
                    continue
                seen.add(path)
                for blk in M.read_grammar(path):
                    blocks.append((blk["raw"], blk["text"]))
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
    # 섹션마다 차례가 달라지면 안 된다 — 폴더 차례가 아니라 **라벨 차례**로.
    # (추가본문 폴더는 두 과에 걸쳐 있어 4과 딥러닝이 4과 본문보다 앞섰다.)
    pairs = sorted(zip(headers, lines[1::2]), key=lambda x: S.label_order(x[0]))
    headers = [h for h, _t in pairs]
    lines = [x for h, t in pairs for x in (h, t)]
    return lines, headers


def _fix_files(folder):
    """그 폴더(와 `… 워크북`) 안의 **어법수정 문제지**들.

    이름이 방언을 탄다 — `…_어법수정_문제지.docx` 도 있고 `…_어법수정_문제.docx`
    도 있다(올림포스 기본2 3강). 그래서 `어법수정` 이 든 docx 중 정답·해설만
    뺀다. 파일이 없으면 빈 목록이고, 그때는 예전 길로 물러난다.
    """
    from engines.final import manuscript as M
    out = []
    for d in {folder, M.find_workbook_dir(folder)}:
        if not d or not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            n = M._nfc(name)
            if not n.endswith(".docx") or n.startswith((".", "~")):
                continue
            if "어법수정" not in n or any(a in n for a in M.ANSWER_WORDS):
                continue
            out.append(os.path.join(d, name))
    return out


def _token_of(spec):
    k = spec.get("kind")
    if k == "lesson":
        return ("lesson", spec["lesson"])
    if k == "mock":
        return ("mock", spec["year"], spec["month"])
    return (k, spec.get("unit"))


def _vocab_g3(scope, base, log=lambda m: None):
    """고3 중요어휘 — 원고의 **빈칸어휘 해설지**에서.

    고3은 시트에 어휘가 없고 워크북 빈칸어휘에서 나온다(사용자 확정).
    문제지(`4. 빈칸어휘.docx`)는 `18[i      ]` 처럼 답이 비어 있고,
    **해설지**에 `18[immediate]` 로 들어 있다 — 렌더러가 대괄호를 보고
    왼쪽은 빈칸, 오른쪽은 굵은 글씨로 가른다.
    """
    from engines.final import manuscript as M
    out = []
    for d, spec in S.folders(scope, base, grade=3, log=log):
        if spec.get("kind") not in ("teuk", "test"):
            continue
        wd = M.find_workbook_dir(d) or d
        try:
            names = [f for f in os.listdir(wd)
                     if M._nfc(f).endswith(".docx")
                     and "빈칸어휘" in M._nfc(f) and "정답" in M._nfc(f)]
        except OSError:
            names = []
        if not names:
            log("  [중요어휘] 빈칸어휘 해설지 없음 — %s" % os.path.basename(d))
            continue
        rows = [t for dep, t in M._docx_rows(os.path.join(wd, names[0]),
                                             depth=True) if dep == 0]
        cur = None
        for t in rows:
            if M.is_block_head(t):
                m = M.RE_ROW.match(t)
                lab = L.to_final_label(spec, m.group(2))
                cur = None
                if lab and S.in_scope(lab, scope):
                    cur = [lab]
                    out.append(cur)
            elif cur is not None and not M.RE_PROMPT.match(t):
                # ⚠ 해설지는 영어 한 줄 · 한글 번역 한 줄이 번갈아 온다.
                #   번역까지 실으면 지문이 두 배가 되어 한 면에 안 앉는다
                #   (광문3 Vol1 이 71p → 167p 로 튀었다). 영어만 이어 붙인다.
                if not M.RE_KO.search(t):
                    cur.append(M.strip_mark(t))   # 줄머리 `─>` 는 표시다
    out = sorted((b for b in out if len(b) > 1),
                 key=lambda b: S.label_order(b[0]))
    return "\n\n".join(b[0] + "\n" + " ".join(b[1:]) for b in out)


def vocab(school, grade, exam_period, scope=None, order=None, codes=None,
          log=lambda m: None):
    """중요어휘(고1·고2) — 구글시트. 돌려주는 것: (왼쪽 글, 오른쪽 글).

    시트가 정본이라 원고에서 유도할 수 없다(선생님이 고른 부분집합).
    고3 은 시트에 없다 — 빈 글을 돌려준다(엔진과 같다).

    ⚠ 시트에서 받은 그대로 쓰면 안 된다. 엔진이 하던 두 가지를 그대로 한다:
      · `>>내용요약` 앞 빈 줄이 소스마다 제멋대로라 두 줄로 맞춘다
      · 영어 사이에 낀 `式` 는 `─` 가 깨진 것이다(낱말 뜻의 한자는 그대로)
    """
    if grade not in ("고1", "고2"):
        if grade == "고3" and scope:
            cfg = json.load(open(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "config.json"), encoding="utf-8"))
            t = _vocab_g3(scope, os.path.expanduser(cfg["gdrive_content_base"]),
                          log)
            return t, t
        return "", ""
    from engines.final.vocab_fetcher import fetch_vocab_for_school
    # ⚠ **리딩파워는 중요어휘를 싣지 않는다**(사용자 확정). 시트에 데이터가
    #   있어서 강 목록을 넘기면 딸려 온다 — 광문2 가 18→54 지문으로 부풀었다.
    olpo = None
    if scope:
        olpo = sorted({t[1] for t in scope["tokens"] if t[0] == "olpo"}) or None
        # 모의고사 차례 — 다른 섹션과 같은 오름차순(YYMM)
        if order is None:
            order = sorted({("%02d" % t[1], "%02d" % t[2])
                            for t in scope["tokens"] if t[0] == "mock"})
    # ⚠ 모의고사 어휘는 **시험범위 시트의 회차**를 보고 가져온다. 정본이
    #   Y.OS 로 옮겨 온 뒤로 시트에 그 학교 행이 없을 수 있어(광문1 26-2-중간)
    #   모의 18지문이 통째로 빠졌다 — 조판된 지문 코드(`240920`)를 곧장 준다.
    got = fetch_vocab_for_school(school, grade, log=log,
                                 olpo_lectures=olpo, rp_lectures=None,
                                 workbook_order=order or None,
                                 passage_codes=codes or None,
                                 code_order=codes or None,
                                 exam_period=exam_period) or {}
    out = []
    for t in (got.get("left_text", ""), got.get("right_text", "")):
        t = _blank_before_summary(t)
        t = re.sub("(?<=[\x21-\x7e])\\s+式\\s+(?=[\x21-\x7e])", " \u2500 ", t)
        out.append(_sort_vocab(t))
    return out[0], out[1]


def _blank_before_summary(text):
    """요약 표제 앞에 **빈 줄 두 개**를 둔다 — 렌더러가 그걸로 요약을 가른다.

    ⚠ 표제 표기가 시트마다 다르다(`>>내용요약` · `>>   내용요약   ` ·
      `|  내용요약  |`). 글자로 맞추면 사이 공백이 든 방언을 놓쳐 그 지문만
      요약이 본문에 붙고, 게이트가 "요약이 일부에만 있다"며 조판을 멈춘다
      (광문1 240924 실측). 그래서 **줄 모양**으로 본다.
    """
    out = []
    for ln in (text or "").split("\n"):
        t = ln.strip()
        if "내용요약" in t and len(t) <= 24:
            while out and not out[-1].strip():
                out.pop()
            out += ["", ""]
        out.append(ln)
    return "\n".join(out)


RE_VLAB = re.compile(r"^(올포 \d+강 \S+|리딩파워 \d+강 \S+|교과서\S+ \S+|"
                     r"\d{6}\S*|\d+강 \d+|test\d+ \S+)$")


def _sort_vocab(text):
    """어휘 글을 **지문 차례**로 다시 엮는다.

    시트가 적힌 차례를 그대로 쓰면 어휘만 순서가 달라진다 — 상일1 18강이
    `분석→서술형→논술형→본문1` 로 나갔고 다른 섹션은 `분석→본문1→…` 이었다.
    """
    blocks, cur = [], None
    for ln in (text or "").split("\n"):
        if RE_VLAB.match(ln.strip()):
            cur = [ln.strip()]
            blocks.append(cur)
        elif cur is not None:
            cur.append(ln)
    if len(blocks) < 2:
        return text
    blocks.sort(key=lambda b: S.label_order(b[0]))
    return "\n".join("\n".join(b).rstrip() + "\n" for b in blocks)
