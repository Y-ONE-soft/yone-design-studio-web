"""UNIT형 단어장 원고(xlsx) → data.json.

원고 형식이 **두 가지**다. 어느 쪽인지는 시트를 열어 **구조로 판정한다**
(파일 이름·머리글 문구에 기대지 않는다).

  블록형  한 표제어가 여러 행에 걸친다(발음기호·파생어·예문 짝). 행이 드문드문
          차 있어 **행당 채워진 칸이 평균 2칸 남짓**이다. → `parse_unit`
  표형    한 행이 한 낱말이다(`No · 낱말 · 단원 · 뜻 · 예문`). 모든 행이 꽉 차
          **행당 4~5칸**이고, 한 열의 값이 크게 반복된다(그게 단원 열이다).
          → `parse_flat`

책은 **대단원(part)** 여러 개로 짜인다. 대단원 하나가 원고 하나(또는 시트 하나)이고,
대단원마다 간지 2면과 지면 색을 갖는다. config `parts` 가 순서·이름·색상을 정한다.

블록형 원고 = 시트 하나가 Unit 하나. 한 표제어는 **빈 행으로 끊기는 블록**이고, 블록 안의
행 역할은 열 위치가 아니라 **구조**로 읽는다(형식 화이트리스트 금지):

    B      C            D
    DAYnn  회독                     ← 블록 시작 마커 (문구는 무엇이든, **B 가 숫자가
                                        아닌 채로 차 있다**는 것이 앵커)
    1      sensible     [형] 분별력…  ← 번호 · 표제어 · 뜻
           [ˈsɛnsəbəl]                ← 발음기호 (대괄호로 열고 닫는 한 줄)
           sensitivity [명] …  It was… ← 파생어(C) · 예문 첫 줄(D)
                              너무 늦은…  ← 예문 해석
                              This work…  ← 예문(영/한 번갈아)

인식 게이트: `options.expect` 의 기대 수량(unit 수·unit 당 표제어 수)과 어긋나면
**조판하지 않고 중단한다**(침묵 유실 금지).

파생어 셀은 여러 파생어가 한 칸에 이어 붙어 온다 —
`sensitivity [명] … sensibility [명] …`. `영단어 + [품사]` 를 경계로 잘라 줄을
나눈다(품사 대괄호가 앵커라 파생어 개수·순서에 의존하지 않는다). 다만 품사
대괄호는 **자르는 경계일 뿐 파생어의 조건이 아니다** — 품사가 없는 파생어도
그대로 살린다.
"""
import json
import os
import re

# 발음기호 — 대괄호로 열고 닫히고 한글이 없는 한 줄
_RE_PRON = re.compile(r"^\[[^\]]*\]$")
# 품사 대괄호 — 뜻·파생어의 구조 앵커
_POS = "명동형부전접대감조"
_RE_POS = re.compile(rf"\[([{_POS}])\]")
# 파생어 경계 — 영단어(구) 다음에 바로 품사 대괄호가 오면 새 파생어가 시작된 것
_RE_DERIV_SPLIT = re.compile(rf"(?<=\S)\s+(?=[A-Za-z][A-Za-z'’\- ]*\[[{_POS}]\])")


def _rows(ws):
    """시트 → 행마다 **모든 열**의 문자열 목록.

    ⚠ 예전엔 여기서 B·C·D 세 칸만 잘라 돌려줬다 — 블록형만 있던 시절의 잔재다.
    표형은 다섯 칸을 다 쓰므로 자르면 형식 판정부터 실패한다(대단원이 통째로
    0개가 되는 사고를 실제로 겪었다).
    """
    out = []
    for row in ws.iter_rows(values_only=True):
        vals = [("" if v is None else str(v).replace(" ", " ").strip())
                for v in row]
        while len(vals) < 4:
            vals.append("")
        out.append(vals)
    return out


def split_deriv(cell):
    """파생어 셀 → 파생어 줄 목록."""
    cell = (cell or "").strip()
    if not cell:
        return []
    return [s.strip() for s in _RE_DERIV_SPLIT.split(cell) if s.strip()]


def parse_unit(rows, unit_label):
    """한 시트 → 표제어 블록 목록.

    블록 경계 = '번호 행'(B 열이 숫자). 마커 행("DAYnn / 회독")은 무시해도
    구조가 잡히므로 문구에 기대지 않는다.
    """
    blocks, cur = [], None
    for row in rows:
        b, c, d = row[1], row[2], row[3]
        if b.isdigit():                                   # ① 번호 · 표제어 · 뜻
            cur = {"no": int(b), "unit": unit_label, "word": c, "meaning": d,
                   "pron": "", "deriv": [], "ex": []}
            blocks.append(cur)
            continue
        if b:                                              # ② 블록 시작 마커 행
            continue                                       #    (B 가 차 있고 숫자가 아니다)
        if cur is None:
            continue
        if c and _RE_PRON.match(c) and not cur["pron"]:    # ③ 발음기호
            cur["pron"] = c
            if d:
                cur["ex"].append(d)
            continue
        if c:                                              # ④ 파생어
            # 품사 대괄호는 **여러 파생어를 자르는 경계**일 뿐, 파생어인지를
            # 가리는 조건이 아니다. 마커 행을 위에서 걸렀으니 남은 C 는 파생어다.
            # (조건으로 쓰면 품사 없는 파생어가 조용히 사라진다 — legally 사고)
            cur["deriv"] += split_deriv(c)
            if d:
                cur["ex"].append(d)
            continue
        if d:                                              # ⑤ 예문 / 해석
            cur["ex"].append(d)
    for blk in blocks:
        # 예문은 영/한 짝 — 홀수로 끝나면 해석이 빈 짝으로 남는다(원고 그대로)
        lines = blk.pop("ex")
        blk["pairs"] = [[lines[i], lines[i + 1] if i + 1 < len(lines) else ""]
                        for i in range(0, len(lines), 2)]
    return blocks


# ── 표형 원고 ───────────────────────────────────────────────────────────
_RE_UNIT_SPLIT = re.compile(r"\s+-\s+")
_RE_LATIN = re.compile(r"[A-Za-z]")
_RE_HANGUL = re.compile(r"[가-힣]")
_RE_TAIL_NUM = re.compile(r"(\d+)\s*$")


def _filled(rows):
    """행당 채워진 칸 수의 평균 — 블록형/표형을 가르는 구조 지표."""
    live = [r for r in rows if any(r)]
    if not live:
        return 0.0
    return sum(sum(1 for c in r if c) for r in live) / len(live)


def is_flat(rows):
    """표형인가 — 행이 꽉 차 있고, 값이 크게 반복되는 열(=단원)이 있다."""
    live = [r for r in rows if any(r)]
    if len(live) < 5 or _filled(rows) < 3.5:
        return False
    n = max(len(r) for r in live)
    for c in range(n):
        col = [r[c] for r in live if c < len(r) and r[c]]
        if len(col) > len(live) * 0.9 and len(set(col)) < len(col) * 0.5:
            return True
    return False


def _roles(cols):
    """열 → 역할. 이름이 아니라 **값의 성질**로 가른다.

    번호  = 거의 다 정수        단원 = 값이 크게 반복된다
    예문  = 가장 긴 영문         낱말 = 남은 영문 중 짧은 쪽
    뜻    = 한글이 있는 남은 열
    """
    def stat(col):
        vals = [v for v in col if v]
        n = max(len(vals), 1)
        return {
            "num": sum(1 for v in vals if v.isdigit()) / n,
            "lat": sum(1 for v in vals if _RE_LATIN.search(v)) / n,
            "kor": sum(1 for v in vals if _RE_HANGUL.search(v)) / n,
            "len": sum(len(v) for v in vals) / n,
            "uniq": len(set(vals)) / n,
        }

    st = {i: stat(c) for i, c in enumerate(cols)}
    left = set(st)
    role = {}

    def take(name, key, pick=max, among=None):
        pool = [i for i in (among if among is not None else left)]
        if not pool:
            return None
        i = pick(pool, key=lambda i: st[i][key])
        role[name] = i
        left.discard(i)
        return i

    take("ex", "len")                                    # 가장 긴 열 = 예문
    take("unit", "uniq", pick=min)                       # 가장 덜 다양한 열 = 단원
    nums = [i for i in left if st[i]["num"] > 0.9]
    if nums:
        role["no"] = nums[0]
        left.discard(nums[0])
    lat = [i for i in left if st[i]["lat"] > 0.7]
    if lat:
        take("word", "len", pick=min, among=lat)
    kor = [i for i in left if st[i]["kor"] > 0.5]
    if kor:
        take("meaning", "kor", among=kor)
    return role


def _split_unit(v):
    """`Unit 01 - Analysis` → (`Unit 01`, `Analysis`). 구분자가 없으면 소단원 없음."""
    bits = _RE_UNIT_SPLIT.split(v or "", 1)
    return bits[0].strip(), (bits[1].strip() if len(bits) > 1 else "")


def parse_flat(rows, sheet, log=print):
    """표형 시트 → 단원(head) 목록. 단원 값 `A - B` 의 A 가 단원, B 가 소단원."""
    live = [r for r in rows if any(r)]
    width = max(len(r) for r in live)
    cols = [[(r[c] if c < len(r) else "") for r in live] for c in range(width)]
    role = _roles(cols)
    for need in ("word", "meaning", "unit"):
        if need not in role:
            raise SystemExit(f"[원고] {sheet}: {need} 열을 찾지 못했다 "
                             f"(찾은 역할 {sorted(role)})")

    def cell(r, name):
        i = role.get(name)
        return (r[i] if i is not None and i < len(r) else "").strip()

    # 머리글 행(`No · word · 단원 · meaning · 예문`)은 **역할에 맞지 않아서** 빠진다
    # — 문구를 알아보는 게 아니라, 번호 칸이 숫자가 아니고 뜻 칸에 한글이 없다는
    # 구조로 가른다. 몇 줄을 버렸는지는 반드시 남긴다(침묵 유실 금지).
    kor_col = ("meaning" in role
               and sum(1 for v in cols[role["meaning"]] if _RE_HANGUL.search(v))
               > 0.8 * sum(1 for v in cols[role["meaning"]] if v))

    def is_data(r):
        if not cell(r, "word") or not cell(r, "meaning"):
            return False
        if "no" in role and not cell(r, "no").isdigit():
            return False
        if kor_col and not _RE_HANGUL.search(cell(r, "meaning")):
            return False
        return True

    skipped = [r for r in live if not is_data(r)]
    if skipped:
        log(f"[원고] {sheet}: 역할에 맞지 않아 건너뛴 행 {len(skipped)}개 "
            f"(첫 행 {skipped[0][:3]})")

    units, seen = [], {}
    for r in live:
        if not is_data(r):
            continue
        w, mean = cell(r, "word"), cell(r, "meaning")
        head, tail = _split_unit(cell(r, "unit"))
        u = seen.get(head)
        if u is None:
            u = {"sheet": sheet, "head": head, "groups": [], "kind": "flat"}
            seen[head] = u
            units.append(u)
        g = u["groups"][-1] if u["groups"] and u["groups"][-1]["label"] == tail else None
        if g is None:
            g = {"label": tail, "runs": []}
            u["groups"].append(g)
        ex = cell(r, "ex")
        # 같은 예문이 이어지는 낱말들 = 한 묶음. 예문은 묶음에 한 번만 싣는다
        run = g["runs"][-1] if g["runs"] and g["runs"][-1]["ex"] == ex else None
        if run is None:
            run = {"ex": ex, "words": []}
            g["runs"].append(run)
        run["words"].append({"word": w, "meaning": mean})

    n = 0
    for u in units:
        for g in u["groups"]:
            for run in g["runs"]:
                for w in run["words"]:
                    n += 1
                    w["no"] = n
        u["words"] = [w for g in u["groups"] for run in g["runs"]
                      for w in run["words"]]
    return units


# ── 대단원(part) 조립 ───────────────────────────────────────────────────
def _head_slots(part_name, head, single):
    """① 큰 원의 세 칸 — 눈썹(대단원명) · 작은 글자 · 큰 글자.

    `Unit 15` → (어휘끝, UNIT, 15) · `Special Lesson 2` → (교과서, Special Lesson, 2)
    `2024년 9월` → (모의고사, 2024년, 9월). 끝의 숫자를 큰 칸으로 떼고, 없으면
    마지막 낱말을 큰 칸으로 쓴다.
    """
    m = _RE_TAIL_NUM.search(head or "")
    if m:
        return part_name, head[:m.start()].strip(), m.group(1)
    bits = (head or part_name).split()
    if len(bits) >= 2:
        return part_name, " ".join(bits[:-1]), bits[-1]
    return ("", part_name, head) if single and head else (part_name, "", head)


def _tab(part_name, ttl, num):
    """③ 둥근 탭 글자 — 좁아서 `대단원명 + 번호` 까지만 넣는다."""
    return " ".join(x for x in (part_name, num) if x) or ttl or part_name


def _sheets(cfg, key, cache):
    """원고 파일 → {시트명: 행목록}. 같은 파일을 대단원마다 다시 열지 않는다."""
    if key not in cache:
        import openpyxl
        wb = openpyxl.load_workbook(cfg.manuscript(key), data_only=True)
        cache[key] = [(ws.title, _rows(ws)) for ws in wb]
    return cache[key]


def _part_units(cfg, spec, log):
    """대단원 하나 → 단원 목록. 형식(블록형/표형)은 시트를 열어 구조로 판정한다."""
    o = cfg.section("options") or {}
    sheets = _sheets(cfg, spec.get("from", "words"), _part_units.cache)
    want = spec.get("sheet")
    if want:
        sheets = [(t, r) for t, r in sheets if t == want]
        if not sheets:
            raise SystemExit(f"[원고] 시트 없음: {want} ({spec.get('name')})")

    units = []
    for title, rows in sheets:
        if is_flat(rows):
            units += parse_flat(rows, title, log)
        else:
            blocks = parse_unit(rows, title)
            if blocks:
                units.append({"sheet": title, "kind": "block",
                              "head": f"{o.get('unit_word', 'UNIT')} "
                                      f"{unit_num(title):02d}",
                              "words": blocks})
    return units


_part_units.cache = {}


def build(cfg, log=print):
    o = cfg.section("options") or {}
    specs = cfg.section("parts") or [{"name": "", "from": "words"}]
    _part_units.cache = {}

    parts, units, total = [], [], 0
    for i, spec in enumerate(specs, 1):
        name = spec.get("name") or ""
        us = _part_units(cfg, spec, log)
        single = len(us) == 1
        for u in us:
            top, ttl, num = _head_slots(name, u["head"], single)
            u.update(part=i, part_name=name, head_top=top,
                     head_ttl=ttl, head_num=num,
                     label=_tab(name, ttl, num),
                     num=int(_RE_NUM.search(num).group(1))
                          if _RE_NUM.search(num) else i)
        parts.append({"idx": i, "name": name, "hue": spec.get("hue"),
                      "sub": spec.get("sub", ""),
                      "units": [u["head"] for u in us],
                      "words": sum(len(u["words"]) for u in us)})
        units += us
        total += sum(len(u["words"]) for u in us)

    d = {"parts": parts, "units": units,
         "counts": {"parts": len(parts), "units": len(units), "words": total}}
    gate(d, o, log)

    out = os.path.join(cfg.root, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    log("[원고] " + " · ".join(f"{p['name']} {p['words']}개" for p in parts)
        + f" (단원 {len(units)}개 · 낱말 {total}개) → {os.path.basename(out)}")
    return out


_RE_NUM = re.compile(r"(\d+)")


def unit_num(sheet):
    m = _RE_NUM.search(sheet or "")
    return int(m.group(1)) if m else 0


def unit_label(sheet, o):
    """머리말·탭에 찍히는 이름 — 기본 `UNIT 15`. config 로 접두어를 바꾼다."""
    return f"{o.get('unit_word', 'UNIT')} {unit_num(sheet):02d}"


def gate(d, o, log):
    """인식 게이트 — 기대와 어긋나면 조판하지 않는다.

    `options.expect` 는 두 가지로 쓴다.
      · 책 전체    `{"units": 9, "words": 270}`
      · 대단원별   `{"parts": {"어휘끝": {"units": 9, "words": 270}, …}}`
    """
    exp = o.get("expect") or {}
    bad = []
    if exp.get("units") and d["counts"]["units"] != exp["units"]:
        bad.append(f"단원 {d['counts']['units']}개 (기대 {exp['units']})")
    if exp.get("words") and d["counts"]["words"] != exp["words"]:
        bad.append(f"낱말 {d['counts']['words']}개 (기대 {exp['words']})")
    for name, want in (exp.get("parts") or {}).items():
        got = next((p for p in d["parts"] if p["name"] == name), None)
        if got is None:
            bad.append(f"대단원 없음: {name}")
            continue
        if want.get("units") is not None and len(got["units"]) != want["units"]:
            bad.append(f"{name}: 단원 {len(got['units'])}개 (기대 {want['units']})")
        if want.get("words") is not None and got["words"] != want["words"]:
            bad.append(f"{name}: 낱말 {got['words']}개 (기대 {want['words']})")
    per = exp.get("words_per_unit")
    if per:
        off = [u["sheet"] for u in d["units"]
               if u.get("kind") != "flat" and len(u["words"]) != per]
        if off:
            bad.append(f"낱말 수가 {per}개가 아닌 단원: {', '.join(off)}")

    # 구조 결손 — 조용히 비면 조판 사고다. 표형 원고에는 발음기호·해석이 없으므로
    # **형식마다 있어야 할 것이 다르다**(없는 걸 요구하면 게이트가 늘 실패한다).
    for u in d["units"]:
        flat = u.get("kind") == "flat"
        for w in u["words"]:
            where = f"{u['sheet']} {w['no']:02d} {w['word']}"
            if not w["word"] or not w["meaning"]:
                bad.append(f"낱말/뜻 없음: {where}")
            elif flat:
                continue
            elif not w["pron"]:
                bad.append(f"발음기호 없음: {where}")
            elif not w["pairs"]:
                bad.append(f"예문 없음: {where}")
        if flat:
            empty = [g["label"] for g in u["groups"] if not g["runs"]]
            if empty:
                bad.append(f"{u['head']}: 빈 소단원 {empty}")
    if bad:
        for b in bad[:20]:
            log(f"  - {b}")
        raise SystemExit(f"[인식 게이트] 원고 인식 결함 {len(bad)}건 — 조판 중단")


def load(cfg):
    with open(os.path.join(cfg.root, "data.json"), encoding="utf-8") as f:
        return json.load(f)
