#!/usr/bin/env python3
"""**원고 직독 content.json 빌더** (B6 교체).

지금 파이널이 워크북 `.indd` 에서 되수확하던 자리를 원고로 갈아 끼운다.

    python3 scripts/final_manuscript_build.py <job> [-o content_원고.json]

바꾸는 것 (원고에서 직접):
    · 문장배열      `Step1 C1 문장배열` — 라벨도 원고가 말한다
    · 문장삽입      같은 파일의 **중첩 표**(하단 문제). 발문만 규칙으로 얹는다
    · 서술형영작    `Step2 C2 영작배열`

그대로 두는 것 (원래 원고·시트가 정본이라 바꿀 게 없다):
    · 어법수정      이미 교과서작업/EBS작업의 2열 표 docx 를 읽는다
    · 중요어휘      구글시트(고1·고2) — 선생님이 고른 부분집합이라 유도 불가

원고에 하단 문제가 없는 출처(옛 모의 회차·리딩파워·고3 수특·외부지문)는
되수확본을 그대로 데려온다.

시험범위는 **워크북 파일 이름**이 말한다(`…(리딩파워12강,14강)…`). 그 강·과의
지문은 전부 싣는다 — 되수확본이 흘린 것(리딩파워 14강 6지문)이 여기서 돌아온다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.final import manuscript as M          # noqa: E402
from engines.final import manuscript_locate as L   # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from final_manuscript_diff import auto_sources, words as _words  # noqa: E402
from engines.final import scope_source as S                       # noqa: E402
from engines.final import assemble as ASM                         # noqa: E402


# ── 차례(canonical) ─────────────────────────────────────────────────────
RE_TB = re.compile(r"^교과서(\d+)과\s*(.+)$")
RE_UNIT = re.compile(r"^(올포|리딩파워)\s*(\d+)강\s*(.+)$")
RE_MOCK = re.compile(r"^(\d{2})(\d{2})(\d{2})(?:~\d{2})?$")
RE_G3 = re.compile(r"^(?:(\d+)강|test(\d+))\s*(.+)$")
TB_TAIL = {"RM": 90, "딥러닝": 95}
UNIT_TAIL = {"분석": 0, "서술형": 90, "논술형": 95}


def order_key(label):
    """파이널의 차례 — 교과서 → 강(올포·리딩파워) → 모의(날짜) → 고3."""
    m = RE_TB.match(label)
    if m:
        tail = m.group(2)
        n = TB_TAIL.get(tail)
        if n is None:
            mm = re.search(r"(\d+)", tail)
            n = int(mm.group(1)) if mm else 50
        return (0, int(m.group(1)), n, label)
    m = RE_UNIT.match(label)
    if m:
        tail = m.group(3)
        n = UNIT_TAIL.get(tail)
        if n is None:
            if tail.startswith("Ex"):
                n = int(re.sub(r"\D", "", tail) or 0)
            elif tail.startswith("본문"):
                n = 10 + int(re.sub(r"\D", "", tail) or 0)
            else:
                n = 10 + int(re.sub(r"\D", "", tail) or 0)
        return (1, int(m.group(2)), n, label)
    m = RE_MOCK.match(label)
    if m:
        return (2, int(m.group(1)) * 100 + int(m.group(2)),
                int(m.group(3)), label)
    m = RE_G3.match(label)
    if m:
        unit = int(m.group(1)) if m.group(1) else 100 + int(m.group(2))
        return (3, unit, int(re.sub(r"\D", "", m.group(3)) or 0), label)
    return (9, 0, 0, label)


# ── 시험범위 ────────────────────────────────────────────────────────────
def scope_labels(content):
    """시험범위 = **어느 한 섹션에라도 있는 지문**.

    어법수정(교재 docx)·중요어휘(구글시트)·영작은 워크북 `.indd` 와 **다른
    출처**다. 한 섹션에서 빠진 지문이 다른 섹션에는 살아 있는 일이 흔하고
    (광문2 리딩파워 14강은 어법·영작에만 있었다), 그 합집합이 실제 범위다.
    시트를 다시 부르지 않아도 되고, 비대칭 자체가 근거가 된다.
    """
    out = set()
    v1, v2 = content.get("vol1") or {}, content.get("vol2") or {}
    for sec in ("문장배열", "문장삽입"):
        out |= {b["header"] for b in v1.get(sec) or []}
    out |= set(v2.get("어법_헤더") or [])
    out |= {d["header"] for d in v2.get("영작_헤더_상세") or []}
    # 중요어휘는 한 덩어리 문자열 — 빈 줄로 끊고 요약 표제가 아닌 머리만
    text = v1.get("중요어휘_왼") or ""
    group, first = [], True
    for ln in text.split("\n"):
        if ln.strip():
            if first:
                group.append(ln.strip())
                first = False
        else:
            first = True
    from core.render_vivlio.series.final import data as _d
    out |= {_d.norm_header(g) for g in group if not _d.is_summary_mark(g)}
    return out


# ── 빌드 ────────────────────────────────────────────────────────────────
def _tok_of(spec):
    """폴더 spec → 범위 토큰(같은 것끼리 견주려고)."""
    k = spec.get("kind")
    if k == "lesson":
        return ("lesson", spec["lesson"])
    if k == "mock":
        return ("mock", spec["year"], spec["month"])
    return (k, spec.get("unit"))


def sources_from_scope(content, scope_text, log=print):
    """시험범위 **글** 하나로 원고 폴더를 정한다 — 워크북이 필요 없다.

    워크북 파일 이름을 읽던 자리를 대신한다. 이름은 범위의 대역일 뿐이라
    빠뜨리는 게 있었다(명일1: 시트의 `공통영어2 YBM(김) 4과` 가 파일 이름에
    없어 그 7지문이 '외부지문' 으로 들어왔다).
    """
    cfg = json.load(open(os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))),
        "engines", "final", "config.json"), encoding="utf-8"))
    base = os.path.expanduser(cfg["gdrive_content_base"])
    grade = int(re.sub(r"\D", "", content.get("grade", "0")) or 0)
    sc = S.parse(scope_text, grade=grade)
    log("■ 시험범위: " + ", ".join(S.token_text(t) for t in sc["tokens"]))
    return S.folders(sc, base, grade=grade, log=log)


RE_VOCAB_LAB = re.compile(
    r"^(?:\d{6}(?:~\d{2})?|올포 \d+강 .+|리딩파워 \d+강 .+|교과서\d+과 .+)$")


def _vocab_labels(text):
    """중요어휘 글에서 지문 라벨만 — 늘고 준 것을 말하려고."""
    return [l.strip() for l in (text or "").split("\n")
            if RE_VOCAB_LAB.match(l.strip())]


def build(content, log=print, keep_all=False, scope_text=None, yos=None):
    """`yos` 를 주면 시험범위의 정본이 그것이다 — 워크북도 되수확본도 안 본다."""
    if yos:
        cfg = json.load(open(os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))),
            "engines", "final", "config.json"), encoding="utf-8"))
        yos = S.from_json(yos) if "items" in yos else yos
        grade = yos.get("grade") or 0
        log("■ 시험범위(Y.OS): "
            + ", ".join(S.token_text(t) for t in yos["tokens"]))
        srcs = S.folders(yos, os.path.expanduser(cfg["gdrive_content_base"]),
                         grade=grade, log=log)
    else:
        srcs = (sources_from_scope(content, scope_text, log) if scope_text
                else auto_sources(content, log))
    if yos:
        scope = None          # 라벨 목록이 아니라 판정 함수로 건다
    else:
        scope = None if keep_all else scope_labels(content)
    ok = (lambda lab: S.in_scope(lab, yos)) if yos else (
        lambda lab: scope is None or lab in scope)
    arrange, insert, writing, seen = [], [], [], set()
    # 같은 지문이 두 벌 들어가지 않게 — 배열만이 아니라 **섹션마다** 막는다.
    # 추가본문 폴더가 두 과에 걸쳐 있어 실제로 두 번 실렸다(상일1 딥러닝).
    seen_i, seen_w = set(), set()
    _seen_in_source = {}
    for d, spec in srcs:
        if not spec:
            continue
        name = os.path.basename(d)
        blocks, path = M.read(d, "arrange")
        if spec:
            _seen_in_source[S._key(_tok_of(spec))] = len(blocks)
        for b in blocks:
            lab = L.to_final_label(spec, b["raw"])
            if not lab:
                log(f"  [라벨 없음] {b['raw']} [{name}]")
                continue
            if lab in seen or not ok(lab):
                continue
            seen.add(lab)
            items = list(b["items"])
            # 첫 항목이 표기 없는 줄이면 그것이 **주어진 문장**이다
            given = ""
            if items and not re.match(r"^\s*\([A-Z]\)", items[0]):
                given = items.pop(0)
            arrange.append({"source": os.path.basename(path or name),
                            "header": lab, "items": items,
                            **({"passage": given} if given else {})})
        for b in M.read(d, "insert")[0]:
            lab = L.to_final_label(spec, b["raw"])
            if not lab or not ok(lab):
                continue
            if lab in seen_i:
                continue
            seen_i.add(lab)
            insert.append({"source": name, "header": lab, "paras": (
                [{"style": "문장 배열 하단 문제", "text": b["prompt"]},
                 {"style": "문장 배열 하단", "text": b["given"]}]
                + [{"style": "문장 배열 하단 문제", "text": x}
                   for x in b["items"]])})
        wb, wpath = M.read(d, "writing")
        for b in wb:
            lab = L.to_final_label(spec, b["raw"])
            if not lab or not b["pairs"]:
                continue
            if not ok(lab):
                continue
            if lab in seen_w:
                continue
            seen_w.add(lab)
            writing.append({"header": lab, "pairs": b["pairs"]})

    # 원고가 없는 지문(외부지문 업로드본 등)은 **되수확본을 그대로 데려온다** —
    # 갈아 끼우면서 잃는 것이 하나도 없어야 한다.
    # ⚠ 다만 **내용이 이미 들어와 있으면** 데려오지 않는다. 되수확본에는 같은
    #   글이 엉뚱한 라벨로 한 번 더 들어 있는 자리가 있어서(광문2 영작
    #   `리딩파워 2강 02` 등 7건), 그대로 데려오면 중복이 된다.
    def _n(t):
        # 공백을 통째로 지운다 — 되수확본은 같은 문장을 띄어쓰기만 달리
        # 담아 둔 자리가 있어서, 한 칸 차이로 '중복 아님'이 된다.
        return re.sub(r"\s+", "", re.sub(r"^\s*\([A-Z]\)\s*", "", t or ""))

    def _covered(lines, pool):
        """이 글이 이미 들어와 있는가 — **문장 단위 완전 일치**로 본다.

        낱말 겹침으로 보면 짧은 글이 엉뚱하게 '중복'이 된다(명일1 외부지문
        본문1 이 그렇게 버려졌다).
        """
        got = [_n(x) for x in lines if len(_n(x)) > 15]
        return bool(got) and all(g in pool for g in got)

    have = {b["header"] for b in arrange}
    pool_a = {_n(x) for b in arrange
              for x in [b.get("passage", "")] + b["items"]}
    for b in content["vol1"].get("문장배열") or []:
        if b["header"] in have:
            continue
        if _covered([b.get("passage", "")] + (b.get("items") or []), pool_a):
            log(f"  [중복 — 버림] 문장배열 {b['header']}")
            continue
        arrange.append(dict(b, source=(b.get("source", "") + " [되수확]")))
        log(f"  [원고 없음 → 되수확 유지] 문장배열 {b['header']}")

    havei = {b["header"] for b in insert}
    pool_i = {_n(p["text"]) for b in insert for p in b["paras"]}
    for b in content["vol1"].get("문장삽입") or []:
        if b["header"] in havei:
            continue
        if _covered([p["text"] for p in b["paras"][1:]], pool_i):
            log(f"  [중복 — 버림] 문장삽입 {b['header']}")
            continue
        insert.append(b)
        log(f"  [원고 없음 → 되수확 유지] 문장삽입 {b['header']}")

    havew = {b["header"] for b in writing}
    pool_w = {_n(p["korean"]) for b in writing for p in b["pairs"]}
    old_pairs = content["vol2"].get("서술형영작") or []
    det = sorted(content["vol2"].get("영작_헤더_상세") or [],
                 key=lambda d: d["start_idx"])
    for k, d in enumerate(det):
        if d["header"] in havew:
            continue
        e = det[k + 1]["start_idx"] if k + 1 < len(det) else len(old_pairs)
        chunk = old_pairs[d["start_idx"]:e]
        if not chunk:
            continue
        if _covered([p["korean"] for p in chunk], pool_w):
            log(f"  [중복 — 버림] 영작 {d['header']}")
            continue
        writing.append({"header": d["header"], "pairs": chunk})
        log(f"  [원고 없음 → 되수확 유지] 영작 {d['header']}")

    # ⚠ 차례는 **한 규칙**(`S.label_order`)으로만. 여기 있던 옛 `order_key`
    #   는 특별 단원(`교과서SL`)을 몰라 SL 이 올포 뒤로 밀렸다 — 어법·어휘만
    #   맞고 배열·삽입·영작이 어긋났다(광문1 실측).
    arrange.sort(key=lambda b: S.label_order(b["header"]))
    insert.sort(key=lambda b: S.label_order(b["header"]))
    writing.sort(key=lambda b: S.label_order(b["header"]))

    out = json.loads(json.dumps(content, ensure_ascii=False))
    # 범위 글이 지문 하나만 짚었는데 원고엔 여럿 있으면 알린다.
    # `Test2 3` 같은 표기가 '3번만'인지 '3번부터'인지 글로는 알 수 없다 —
    # 좁게 읽으면 지문이 조용히 빠진다. 짐작하지 말고 말한다.
    if yos:
        for t in yos["tokens"]:
            only = (yos.get("detail", {}).get(t) or {}).get("only") or []
            if len(only) != 1:
                continue
            same = [b for b in arrange
                    if S.label_token(b["header"])[0]
                    and S._key(S.label_token(b["header"])[0]) == S._key(t)]
            all_n = _seen_in_source.get(S._key(t), 0)
            if all_n >= 3:
                log("  [범위 확인] %s — 범위 글은 %d번 하나만 짚었는데 원고엔 "
                    "%d지문이 있습니다(‘%d번부터’일 수 있습니다)"
                    % (S.token_text(t), only[0], all_n, only[0]))

    # 원고에 하단 문제가 없는 지문을 **이름으로** 알린다 — 숫자만 보면
    # 무엇이 비었는지 알 수 없고, 조용히 넘어가면 책이 얇아진 줄만 안다.
    if yos or scope_text:
        # 고3은 문장삽입 섹션 자체가 없다 — 그때는 '없다'고 말할 일이 아니다.
        no_bottom = ([b["header"] for b in arrange
                      if b["header"] not in {x["header"] for x in insert}]
                     if insert else [])
        if no_bottom:
            log("  [하단 문제 없음] %d지문 — %s"
                % (len(no_bottom), ", ".join(no_bottom[:10])
                   + (" …" if len(no_bottom) > 10 else "")))
    out["_from_manuscript"] = True
    out["vol1"]["문장배열"] = arrange
    out["vol1"]["문장삽입"] = insert
    pairs, det = [], []
    for b in writing:
        det.append({"header": b["header"], "start_idx": len(pairs)})
        pairs += b["pairs"]
    # 어법수정도 원고에서 직접 — 정본(Y.OS/시트)이 있을 때만.
    # 되수확본에서 실어 오던 자리를 끊는다. 라벨 규칙이 문장배열과 같아지므로
    # 섹션 사이 지문번호가 어긋날 수 없다(명일1 '외부지문 본문1~7' 이 사실
    # 교과서4과였던 것도 여기서 제자리를 찾는다).
    if yos or scope_text:
        sc = yos or S.parse(scope_text, grade=int(
            re.sub(r"\D", "", content.get("grade", "0")) or 0))
        cfg2 = json.load(open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engines", "final", "config.json"),
            encoding="utf-8"))
        glines, ghdrs = ASM.grammar(
            sc, os.path.expanduser(cfg2["gdrive_content_base"]),
            content.get("grade", ""), log=log)
        if ghdrs:
            old = out["vol2"].get("어법_헤더") or []
            log("■ 어법수정 %d → %d  (되찾음 %d · 사라짐 %d)"
                % (len(old), len(ghdrs),
                   len([h for h in ghdrs if h not in old]),
                   len([h for h in old if h not in ghdrs])))
            out["vol2"]["어법수정"] = glines
            out["vol2"]["어법_헤더"] = ghdrs
        else:
            log("  [어법] 원고에서 한 줄도 못 읽어 되수확본을 그대로 둡니다")

        # 중요어휘 — 시트가 정본이다(원고에서 유도할 수 없다).
        # 고3 은 시트에 없고 워크북 빈칸어휘에서 나오므로 그대로 둔다.
        # 장문은 라벨이 `240941~42` 인데 시트 코드는 `240941` 이다 — 앞
        # 여섯 자리로 맞춰 보낸다(안 맞추면 그 지문만 어휘가 빠진다).
        codes = [b["header"][:6] for b in arrange
                 if re.match(r"^\d{6}", b["header"])] or None
        vl, vr = ASM.vocab(content.get("school", ""), content.get("grade", ""),
                           content.get("exam_period", ""), scope=sc,
                           codes=codes, log=log)
        if vl:
            oldv = _vocab_labels(out["vol1"].get("중요어휘_왼", ""))
            newv = _vocab_labels(vl)
            log("■ 중요어휘 %d → %d  (되찾음 %d · 사라짐 %d)"
                % (len(oldv), len(newv),
                   len([x for x in newv if x not in oldv]),
                   len([x for x in oldv if x not in newv])))
            for x in oldv:
                if x not in newv:
                    log("    [중요어휘] 시트에 없어짐 — %s" % x)
            out["vol1"]["중요어휘_왼"] = vl
            out["vol1"]["중요어휘_오"] = vr

    out["vol2"]["서술형영작"] = pairs
    out["vol2"]["영작_헤더_상세"] = det
    out["vol2"]["영작_헤더"] = [d["header"] for d in det]
    out["총_문장배열"] = sum(len(b["items"]) for b in arrange)
    out["총_문장삽입"] = sum(len(b["paras"]) for b in insert)
    out["총_서술형영작"] = len(pairs)
    out["_source"] = "manuscript"
    # 어디서 읽었는지 남긴다 — 이 파일만으로 다시 대조·재빌드가 된다
    out["_manuscript_sources"] = [{"dir": d, "spec": spec}
                                  for d, spec in srcs if spec]
    # 연구원이 앞선 책에서 잡아 준 것을 얹는다 — **지문 이름과 글자로** 걸어
    # 두었으므로 학교가 달라도 같은 지문이면 그대로 반영된다.
    from engines.final import marks as MK
    out["_marks"] = MK.apply(out, log=log,
                             src="%s %s" % (content.get("school", ""),
                                            content.get("exam_period", "")))
    return out


EMPTY = {"vol1": {"문장배열": [], "문장삽입": [], "중요어휘_왼": "",
                  "중요어휘_오": ""},
         "vol2": {"어법수정": [], "어법_헤더": [], "서술형영작": [],
                  "영작_헤더_상세": [], "영작_헤더": []}}


def scratch(school, grade, exam_period):
    """**아무것도 없는 데서** 시작하는 껍데기 — 워크북을 아예 안 본다.

    되수확본이 없으니 데려올 것도 없다. 원고에 없는 것은 그대로 비고,
    빌더가 무엇이 비었는지 말한다.
    """
    import copy
    out = copy.deepcopy(EMPTY)
    out.update({"school": school, "grade": grade, "exam_period": exam_period})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--all", action="store_true",
                    help="시험범위를 무시하고 그 강·과의 지문을 전부 싣는다")
    ap.add_argument("--scope-text",
                    help="시험범위 글(Y.OS/시트). 주면 워크북 파일 이름을 안 본다")
    ap.add_argument("--scope-json",
                    help="final_scope_fetch.py 가 만든 scope.json (정본)")
    ap.add_argument("--scratch", action="store_true",
                    help="워크북 되수확본 없이 원고·시트만으로 만든다")
    ap.add_argument("--school")
    ap.add_argument("--grade")
    ap.add_argument("--period")
    a = ap.parse_args()
    if a.scratch:
        if not (a.school and a.grade and a.period):
            ap.error("--scratch 에는 --school/--grade/--period 가 필요합니다")
        content = scratch(a.school, a.grade, a.period)
        p = a.out or "content_원고.json"
        if not a.scope_text and not a.scope_json:
            g = int("".join(c for c in a.grade if c.isdigit()) or 0)
            sc = S.from_sheet(a.school, a.period, grade=g, log=print)
            if not sc:
                sys.exit("[범위] 시험범위를 찾지 못했습니다")
            a.scope_json = None
            globals()["_SCRATCH_SCOPE"] = sc
    else:
        p = a.job
        if not p:
            ap.error("job 폴더가 필요합니다 (또는 --scratch)")
        if os.path.isdir(p):
            p = os.path.join(p, "content.json")
        with open(p, encoding="utf-8") as f:
            content = json.load(f)
    old_a = {b["header"] for b in content["vol1"]["문장배열"]}
    old_i = {b["header"] for b in content["vol1"].get("문장삽입") or []}
    old_w = {d["header"] for d in content["vol2"]["영작_헤더_상세"]}
    yos = (json.load(open(a.scope_json, encoding="utf-8"))
           if a.scope_json else globals().get("_SCRATCH_SCOPE"))
    out = build(content, keep_all=a.all, scope_text=a.scope_text, yos=yos)
    new_a = {b["header"] for b in out["vol1"]["문장배열"]}
    new_w = {d["header"] for d in out["vol2"]["영작_헤더_상세"]}
    print(f"■ 문장배열 {len(old_a)} → {len(new_a)}"
          f"  (되찾음 {len(new_a - old_a)} · 사라짐 {len(old_a - new_a)})")
    if new_a - old_a:
        print("   + " + ", ".join(sorted(new_a - old_a)[:12]))
    if old_a - new_a:
        print("   - " + ", ".join(sorted(old_a - new_a)[:12]))
    new_i = {b["header"] for b in out["vol1"]["문장삽입"]}
    print(f"■ 문장삽입 {len(old_i)} → {len(new_i)}"
          f"  (되찾음 {len(new_i - old_i)} · 사라짐 {len(old_i - new_i)})")
    print(f"■ 서술형영작 {len(old_w)} → {len(new_w)}"
          f"  (되찾음 {len(new_w - old_w)} · 사라짐 {len(old_w - new_w)})")
    if old_w - new_w:
        print("   - " + ", ".join(sorted(old_w - new_w)[:12]))
    dest = a.out or (p if a.scratch
                     else os.path.join(os.path.dirname(p), "content_원고.json"))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("→", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
