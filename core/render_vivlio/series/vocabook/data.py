"""단어장 원고 → data.json.

입력(책 config 의 `manuscript.files`):
    part1     조판용 xlsx — 시트 4개: 표제어 / 파생어&연관어휘 / more with / VOCA vs. VOCA
    workbook  워크북 hwpx (Day별 A~D)
    answers   워크북 정답 hwpx

인식 원칙(형식이 아니라 구조):
  - Part1 단어 블록: 'Day' 마커행 → 다음 행이 (Day번호, 표제어, 뜻) → 라벨행/연속행
  - Part2 섹션: 라인 선두 [A-E] + 구분자(./)) + 한글 발문 (문구 리터럴에 의존 안 함)
  - Part2 문항: ^\\d+\\.  / 보기: 〈보기〉·「보기」·[문제 N]
  - 정답: '▶ X' 섹션 마커 + ^\\d+\\.

**인식 게이트**: 기대 수량과 어긋나면 조판하지 않고 중단한다(침묵 유실 금지).
기대값은 책 config 의 `options.expect`.
"""
import json
import os
import re
import zipfile

_RE_SECTION = re.compile(r"^([A-E])[.)]\s*(.*)$")
_RE_KOREAN = re.compile(r"[가-힣]")
_RE_ITEM = re.compile(r"^\s*(\d+)\.\s*(.*)$")
_RE_BOGI = re.compile(r"^\s*[〈<]보기[〉>]\s*(.*)$")
_RE_QGROUP = re.compile(r"^\s*\[문제\s*(\d+)\]\s*$")
_RE_ANS_SEC = re.compile(r"^\s*▶\s*([A-E])\s*$")
_RE_DAY = re.compile(r"^\s*Day\s*(\d+)\s*$", re.I)

SHEETS = ("표제어", "파생어&연관어휘", "more with", "VOCA vs. VOCA")


# ────────────────────────────── Part 1 (xlsx) ──────────────────────────────
def _cells(ws):
    for row in ws.iter_rows(values_only=True):
        vals = [("" if v is None else str(v).strip()) for v in row]
        while len(vals) < 4:
            vals.append("")
        yield vals


def parse_word_sheet(ws):
    """표제어 / 파생어&연관어휘 공통 — Day 마커 기반 단어 블록."""
    blocks, cur, expect_word = [], None, False
    for a, b, c, _d in _cells(ws):
        if a == "Day":
            expect_word = True
            continue
        if expect_word and a.isdigit():
            cur = {"day": int(a), "word": b, "meaning": c, "rows": []}
            blocks.append(cur)
            expect_word = False
            continue
        if cur is None or not (a or b or c):
            continue
        if b:                                   # 라벨행 (예문/유반의어/영영풀이)
            cur["rows"].append({"label": b, "lines": [c] if c else []})
        elif c and cur["rows"]:                 # 연속행 → 직전 라벨에 귀속
            cur["rows"][-1]["lines"].append(c)
        elif c:                                 # 라벨 없는 선행 연속행 (방어)
            cur["rows"].append({"label": "", "lines": [c]})
    return blocks


def parse_more_with(ws, roots):
    """more with — 원고에 어근명이 없어 config 의 `more_with_roots` 표로 나눈다."""
    items = [{"word": a, "meaning": b} for a, b, *_ in _cells(ws) if a]
    groups, i = [], 0
    for root, n in roots:
        groups.append({"root": root, "items": items[i:i + n]})
        i += n
    if i != len(items):
        raise SystemExit(
            f"[오류] more with 묶음 합계 {i} ≠ 원고 항목 {len(items)} — "
            f"config options.more_with_roots 를 원고에 맞게 수정하세요.")
    return groups


def parse_vs_voca(ws, groups_spec):
    """빈 행 = 항목 경계. 묶음 경계·제목은 원고에 없어 config 표로 나눈다."""
    entries, cur = [], None
    for a, b, *_ in _cells(ws):
        if not a and not b:
            cur = None
            continue
        if a == "예문":
            if cur is not None:
                cur["ex"].append([b, ""])
            continue
        if a:
            cur = {"word": a, "meaning": b, "ex": []}
            entries.append(cur)
        elif cur is not None and cur["ex"]:      # 예문 다음 줄 = 해석
            cur["ex"][-1][1] = b
    groups, i = [], 0
    for n, title in groups_spec:
        groups.append({"title": title, "items": entries[i:i + n]})
        i += n
    if i != len(entries):
        raise SystemExit(
            f"[오류] VOCA vs. VOCA 묶음 합계 {i} ≠ 원고 항목 {len(entries)} — "
            f"config options.vs_groups 를 원고에 맞게 수정하세요.")
    return groups


def _alpha(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _lcs(a, b):
    """최장 공통 부분문자열 길이 — 어근 공유 판정.

    접두어 매칭으로는 안 된다: corruption·disruption·eruption·interruption 은
    `rupt` 만 공유한다.
    """
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def link_deriv_to_head(head, deriv, fix=None, min_ratio=0.4, min_share=3):
    """파생어&연관어휘 항목을 표제어에 귀속(묶음 = 같은 표제어에서 나온 것들).

    원고는 표제어 순서를 따라가며 그 표제어의 파생어를 늘어놓는다. 그래서 'Day 안에서
    표제어 인덱스가 단조 증가'라는 제약만 걸고, 어근 공유 점수 총합을 최대로 만드는
    배정을 DP 로 한 번에 구한다. 그리디로 앞에서부터 최고점을 고르면 한 번 앞서간
    포인터가 뒤 항목을 통째로 고아로 만든다(compel·appeal 5항목 실측).

    점수 = LCS(파생어, 표제어) / 표제어 길이 — 'solution' 이 solve(3/5)를
    dissolve(3/8)보다 앞세우게 하는 정규화. 낮으면 독립 묶음으로 둔다.
    """
    fix = fix or {}
    heads_by_day, deriv_by_day = {}, {}
    for b in head:
        heads_by_day.setdefault(b["day"], []).append((_alpha(b["word"]), b["word"]))
    for b in deriv:
        deriv_by_day.setdefault(b["day"], []).append(b)

    for day, items in deriv_by_day.items():
        heads = heads_by_day.get(day, [])
        if not heads:
            for i, b in enumerate(items):
                b["grp"], b["grp_head"] = f"{day}:x{i}", ""
            continue
        m = len(heads)
        sc = [[0.0] * m for _ in items]
        ln = [[0] * m for _ in items]
        for i, b in enumerate(items):
            w = _alpha(b["word"])
            for k, (hw, _orig) in enumerate(heads):
                s = _lcs(w, hw)
                ln[i][k] = s
                # 동점(recollection: recollect 9/9 vs collect 7/7)은 더 긴 공유 어근으로
                sc[i][k] = s / max(len(hw), 1) + 0.001 * s

        NEG = float("-inf")
        dp = [[NEG] * m for _ in items]
        bk = [[-1] * m for _ in items]
        for k in range(m):
            dp[0][k] = sc[0][k]
        for i in range(1, len(items)):
            best_prev, best_k = NEG, -1
            for k in range(m):        # k 는 비감소 — 누적 최대를 왼쪽부터 끌고 온다
                if dp[i - 1][k] > best_prev:
                    best_prev, best_k = dp[i - 1][k], k
                dp[i][k] = sc[i][k] + best_prev
                bk[i][k] = best_k
        k = max(range(m), key=lambda x: dp[-1][x])
        path = [0] * len(items)
        for i in range(len(items) - 1, -1, -1):
            path[i] = k
            k = bk[i][k] if i else k
        for i, b in enumerate(items):
            k = path[i]
            fx = fix.get(b["word"].lower())
            if fx:
                for kk, (_hw, orig) in enumerate(heads):
                    if orig.lower() == fx:
                        b["grp"], b["grp_head"] = f"{day}:{kk}", orig
                        break
                else:
                    b["grp"], b["grp_head"] = f"{day}:x{i}", ""
                continue
            if sc[i][k] >= min_ratio and ln[i][k] >= min_share:
                b["grp"], b["grp_head"] = f"{day}:{k}", heads[k][1]
            else:
                b["grp"], b["grp_head"] = f"{day}:x{i}", ""
    return deriv


def parse_part1(path, opts):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = opts.get("sheets") or SHEETS
    head = parse_word_sheet(wb[sheets[0]])
    deriv = link_deriv_to_head(head, parse_word_sheet(wb[sheets[1]]),
                               fix=opts.get("deriv_fix"))
    return {
        "head": head,
        "deriv": deriv,
        "more_with": parse_more_with(wb[sheets[2]],
                                     opts.get("more_with_roots") or []),
        "vs_voca": parse_vs_voca(wb[sheets[3]], opts.get("vs_groups") or []),
    }


# ────────────────────────────── Part 2 (hwpx) ──────────────────────────────
def hwpx_lines(path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.startswith("Contents/section"))
        for n in names:
            xml = z.read(n).decode("utf-8")
            for m in re.finditer(r"<hp:p\b.*?</hp:p>", xml, re.S):
                s = "".join(re.findall(r"<hp:t>(.*?)</hp:t>", m.group(0), re.S))
                s = re.sub(r"<.*?>", "", s)
                s = (s.replace("&lt;", "<").replace("&gt;", ">")
                      .replace("&amp;", "&").replace("&quot;", '"'))
                out.append(s.rstrip())
    return out


def _sec_letter(line):
    m = _RE_SECTION.match(line.strip())
    if not m:
        return None
    return m.group(1) if _RE_KOREAN.search(m.group(2)) else None


def parse_workbook(path):
    """Day → 섹션(letter, prompt, items) 구조화."""
    days, day, sec = [], None, None
    for raw in hwpx_lines(path):
        t = raw.strip()
        if not t:
            continue
        dm = _RE_DAY.match(t)
        if dm:
            day = {"day": int(dm.group(1)), "sections": []}
            days.append(day)
            sec = None
            continue
        letter = _sec_letter(t)
        if letter and day is not None:
            sec = {"letter": letter,
                   "prompt": _RE_SECTION.match(t).group(2).strip(),
                   "items": []}
            day["sections"].append(sec)
            continue
        if sec is None:
            continue
        qg = _RE_QGROUP.match(t)
        if qg:
            sec["items"].append({"kind": "qgroup", "no": qg.group(1)})
            continue
        bg = _RE_BOGI.match(t)
        if bg:
            sec["items"].append({"kind": "bogi", "text": bg.group(1).strip()})
            continue
        im = _RE_ITEM.match(t)
        if im:
            sec["items"].append({"kind": "item", "no": im.group(1),
                                 "text": im.group(2).strip()})
            continue
        sec["items"].append({"kind": "cont", "text": t})
    return days


def parse_answers(path):
    days, day, sec = [], None, None
    for raw in hwpx_lines(path):
        t = raw.strip()
        if not t:
            continue
        dm = _RE_DAY.match(t)
        if dm:
            day = {"day": int(dm.group(1)), "sections": []}
            days.append(day)
            sec = None
            continue
        am = _RE_ANS_SEC.match(t)
        if am and day is not None:
            sec = {"letter": am.group(1), "items": []}
            day["sections"].append(sec)
            continue
        if sec is None:
            continue
        im = _RE_ITEM.match(t)
        if im:
            sec["items"].append({"no": im.group(1), "text": im.group(2).strip()})
        elif sec["items"]:
            sec["items"][-1]["text"] += " " + t
    return days


# ── 인식 게이트 ─────────────────────────────────────────────────────────
def gate(data, expect):
    """기대 수량과 대조. 하나라도 어긋나면 조판하지 않고 중단한다."""
    errs = []
    n_vs = sum(len(g["items"]) for g in data["vs_voca"])
    for key, got in (("head", len(data["head"])), ("deriv", len(data["deriv"])),
                     ("vs", n_vs)):
        want = expect.get(key)
        if want is not None and got != want:
            errs.append(f"{key} {got} (기대 {want})")
    want_sec = expect.get("sections")
    if want_sec:
        for d in data["workbook"]:
            letters = [s["letter"] for s in d["sections"]]
            if letters != list(want_sec):
                errs.append(f"워크북 Day{d['day']} 섹션 {letters} (기대 {want_sec})")
    days = expect.get("days")
    if days is not None and (len(data["workbook"]) != days
                             or len(data["answers"]) != days):
        errs.append(f"Day 수 문제 {len(data['workbook'])} / "
                    f"정답 {len(data['answers'])} (기대 {days})")
    if errs:
        raise SystemExit("[오류] 원고 인식 불일치:\n  - " + "\n  - ".join(errs))


def build(cfg, log=print):
    opts = cfg.section("options") or {}
    data = parse_part1(cfg.manuscript("part1"), opts)
    data["workbook"] = parse_workbook(cfg.manuscript("workbook"))
    data["answers"] = parse_answers(cfg.manuscript("answers"))
    gate(data, opts.get("expect") or {})

    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log(f"OK  표제어 {len(data['head'])} · 파생어 {len(data['deriv'])} · "
        f"more with {sum(len(g['items']) for g in data['more_with'])} · "
        f"vs {sum(len(g['items']) for g in data['vs_voca'])} · "
        f"워크북 {len(data['workbook'])}일 → {os.path.basename(out)}")
    return out


def load(cfg, log=None):
    """data.json + 정오표(errata.json) — 읽는 자리에서 얹는다."""
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
