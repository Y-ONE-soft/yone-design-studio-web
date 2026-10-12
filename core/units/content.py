"""원고 넣기 — 틀(인터페이스)에 원고(구현체)를 넣는다.

틀   = 글상자마다 자리 이름(atom.bind) + 임시 글(atom.text) + 스타일. 스타일은 틀이 가진다.
원고 = {"자리 이름": "글" | ["글1", "글2", …]} — 같은 자리가 여러 번이면 문서 읽는 순서대로 하나씩:
       쪽 순서 → 쪽 안에서는 위에서 아래(같은 높이면 왼쪽부터). 지면에 단(columns)이 있으면 단 순서
       (왼쪽 단 위→아래, 다음 단 — 여러 단에 걸친 상자는 그 높이에서 먼저). 원고에는 글만 온다.
글 잇기(atom.story) = 상자 여럿이 글 하나를 차례로 흘린다 — 자리는 첫 상자 하나, 넘친 줄은 그리기(units_compose.js)가 넘긴다.
넣으면 그 자리의 임시 글 대신 원고 글이 나온다. 원고에 없는 자리는 임시 글 그대로.

규약: docs/편집기_재현/원고자리_규약.md
"""
import copy


def plan_page_ids(plan):
    """문서(틀)의 쪽 id 순서 — 앞면 → 구간(간지 + 쪽) → 뒷면."""
    ids = list(plan.get("front") or [])
    for sc in plan.get("sections") or []:
        if sc.get("divider"):
            ids.append(sc["divider"])
        ids.extend(p["page"] if isinstance(p, dict) else p for p in sc.get("pages") or [])
    ids.extend(plan.get("back") or [])
    return ids


def plan_pages(plan, pages_by_id, content=None):
    """문서의 쪽 차례(쪽 사본 목록) — 「원고마다」(repeat each_set) 쪽이 이어진 묶음은 원고가 준 목록만큼 되풀이한다(인디자인 데이터 병합의 레코드).
    묶음의 원고 = content[묶음 첫 쪽 이름] = [{자리: 글 | [글…]}, …] — 한 벌이 레코드 하나. 둘째 벌부터 쪽 id 는 「id~2」….
    잇닿은 「원고마다」 쪽 중 원고를 받는 이름의 쪽에서 새 묶음이 시작된다(제목 면 + 이어지는 면 = 한 묶음, 다음 유형 제목 면 = 새 묶음).
    목록이 없으면 한 번(전처럼). 되풀이한 쪽은 _rec 에 제 레코드를 갖고 fill 이 그 자리부터 채운다."""
    content = content or {}
    out = []
    if isinstance(content.get("원고"), list):
        return _faces_by_chunk(plan, pages_by_id, content["원고"])

    def put(pid, rec=None, k=0):
        pg = pages_by_id.get(pid)
        if not pg:
            return
        if rec is not None:
            pg = copy.deepcopy(pg)
            pg["_rec"] = rec
            if k:
                pg["id"] = f"{pid}~{k + 1}"
        out.append(pg)

    def recs_of(pid):
        r = content.get((pages_by_id.get(pid) or {}).get("name") or "")
        return r if isinstance(r, list) and r and all(isinstance(x, dict) for x in r) else None

    def flush(run):
        recs = recs_of(run[0]) if run else None
        if recs:
            for k, rec in enumerate(recs):
                for pid in run:
                    put(pid, rec, k)
        else:
            for pid in run:
                put(pid)
    for pid in plan.get("front") or []:
        put(pid)
    for sc in plan.get("sections") or []:
        if sc.get("divider"):
            put(sc["divider"])
        run = []
        for e in sc.get("pages") or []:
            pid = e["page"] if isinstance(e, dict) else e
            if isinstance(e, dict) and e.get("repeat") == "each_set":
                if run and recs_of(pid):                                 # 원고를 받는 이름의 쪽 = 새 묶음 (A1 묶음 바로 뒤 A2 묶음)
                    flush(run)
                    run = []
                run.append(pid)
                continue
            flush(run)
            run = []
            put(pid)
        flush(run)
    for pid in plan.get("back") or []:
        put(pid)
    return out


def _faces(plan, pages_by_id):
    """문서의 상위 페이지(「레코드마다」 페이지 하나, 「두 페이지짜리」면 다음 페이지까지) · 첫 상위 페이지 앞 「한 번만」 페이지 · 뒤 「한 번만」 페이지.
    상위 페이지 = {"pages": [쪽 id …], "구분": 분류, "occ": {데이터 필드: 개수}}"""
    faces, head, tail, spread = [], [], [], False
    for sc in plan.get("sections") or []:
        if sc.get("divider"):
            (tail if faces else head).append(sc["divider"])
        for e in sc.get("pages") or []:
            pid = e["page"] if isinstance(e, dict) else e
            each = isinstance(e, dict) and e.get("repeat") == "each_set"
            if not each:
                if not (isinstance(e, dict) and e.get("repeat") == "none"):
                    (tail if faces else head).append(pid)
                continue
            if spread and faces:                                           # 앞 쪽이 「두 페이지짜리」 — 이 쪽은 그 펼침면의 둘째 쪽
                faces[-1]["pages"].append(pid)
                spread = False
                continue
            faces.append({"pages": [pid], "구분": (e.get("구분") or "").strip()})
            spread = bool(e.get("펼침면"))
    for f in faces:
        occ = {}
        for pid in f["pages"]:
            for it in (pages_by_id.get(pid) or {}).get("items") or []:
                b = _slot(it)
                if b:
                    occ[b] = occ.get(b, 0) + 1
        f["occ"] = occ
    return faces, head, tail


def to_records(plan, pages_by_id, old):
    """옛 꼴 원고 → 레코드 차례 원고({원고: [레코드 …]}) — 이 문서의 상위 페이지 차례대로(데이터 병합 원고 꼴 통일, 2026-10-12).
    옛 꼴 = {상위 페이지 첫 페이지 이름: [레코드 …], 책 머리 데이터 필드: 값 | [값 …]}(워크북 · 분석본 어댑터가 만드는 꼴).
    - 첫 페이지 이름이 옛 원고 키인 상위 페이지: 그 레코드들을 차례로
    - 아니면 그 상위 페이지 데이터 필드가 모두 옛 원고의 책 머리 데이터 필드면: 그 값으로 레코드 하나(STEP 시작 · 간지 · 실전 한 줄기).
      글 목록이면 상위 페이지마다 하나씩 꺼내고, 한 줄기(목록의 목록)는 통째로.
      장을 여는 상위 페이지(첫 페이지 이름이 같은 상위 페이지가 여럿 — STEP 간지)는 다음 장 전까지 레코드가 있을 때만
    - 분류가 있는 상위 페이지의 레코드엔 그 분류(「구분」)를 단다 — 자동 상위 페이지 적용이 같은 상위 페이지를 고르게
    꺼내지 않은 책 머리 데이터 필드(앞 · 뒤 「한 번만」 페이지 몫)는 그대로 둔다."""
    old = old or {}
    if isinstance(old.get("원고"), list):
        return old
    faces, _, _ = _faces(plan, pages_by_id)
    name = lambda f: (pages_by_id.get(f["pages"][0]) or {}).get("name") or ""
    face_names = {name(f) for f in faces}                                 # 상위 페이지 이름 키만 레코드 목록 — 여러 칸 데이터 필드(「교재명+강제목」)의 목록은 값이다
    recs_of = lambda k: old[k] if k in face_names and isinstance(old.get(k), list) and old[k] and all(isinstance(x, dict) for x in old[k]) else None
    whole = lambda v: isinstance(v, list) and v and isinstance(v[0], (list, dict))   # 한 줄기(실전 문제) — 통째로
    queue = {k: (list(v) if isinstance(v, list) else v) for k, v in old.items() if not recs_of(k)}
    names = [name(f) for f in faces]
    rows = []                                                              # [(상위 페이지, 레코드, 장을 여나)]
    for f, nm in zip(faces, names):
        if recs_of(nm):
            rows += [(f, r, False) for r in recs_of(nm)]
            continue
        keys = [k for k in f["occ"] if not k.startswith("sys.")]
        if not keys or not all(k in queue for k in keys):
            continue
        rec = {}
        for k in keys:
            v = queue[k]
            if whole(v):
                rec[k] = v
            elif isinstance(v, list):
                rec[k] = v.pop(0) if v else ""
            else:
                rec[k] = v
        rows.append((f, rec, names.count(nm) > 1))
    keep = []
    for i, (f, rec, opener) in enumerate(rows):
        if opener:                                                         # 장을 여는 상위 페이지 — 다음 장 전까지 레코드가 있어야
            j = next((j for j in range(i + 1, len(rows)) if rows[j][2]), len(rows))
            if not any(not rows[k][2] for k in range(i + 1, j)):
                continue
        r = dict(rec)
        if f["구분"]:
            r["구분"] = f["구분"]
        keep.append(r)
    out = {"원고": keep}
    used = {k for f, rec, _ in rows for k in rec if not recs_of(name(f))}
    out.update({k: v for k, v in old.items() if not recs_of(k) and k not in used})
    return out


def _faces_by_chunk(plan, pages_by_id, chunks):
    """원고 덩어리 차례로 면 고르기 — 원고 = [덩어리 …](원본 차례). 덩어리마다 그 자리를 가장 많이 담는 「원고마다」 면을 골라 그 덩어리로 찍는다.
    면(상위 페이지) = 「원고마다」 쪽 하나, 그 쪽에 「두 페이지짜리」(펼침면)를 켰으면 다음 쪽까지 둘(인디자인 펼침면 상위 페이지 — 쪽 이름은 안 본다). 고르기:
    ① 덩어리의 자리 이름이 면 자리와 가장 많이 맞는 면 ② 면 설정 「구분」이 덩어리 「구분」과 같은 면 ③ 덩어리에 없어 비는 면 자리가 적은 면(그림 없는 지문 → 그림 자리 없는 면)
    ④ 같은 자리가 여럿인 면은 그 개수가 원고 목록 길이와 맞는 면.
    맨 앞 · 맨 뒤 · 「한 번만」 쪽은 그 자리에(구간의 「한 번만」 쪽은 첫 「원고마다」 면보다 앞이면 앞, 뒤면 뒤). 맞는 자리가 없는 덩어리는 건너뛴다."""
    faces, head, tail = _faces(plan, pages_by_id)

    def score(f, rec):
        keys = [k for k in rec if not k.startswith("_")]
        hit = sum(1 for k in keys if k in f["occ"])
        g = (rec.get("구분") or "").strip()
        gub = 0 if not (f["구분"] and g) else (1 if f["구분"] == g else -1)
        empty = -sum(1 for k in f["occ"] if k not in rec)
        cap = -sum(abs(len(rec[k]) - f["occ"][k]) for k in keys if k in f["occ"] and f["occ"][k] > 1 and isinstance(rec[k], list))
        return hit, gub, empty, cap

    out, n = [], {}

    def put(pid, rec=None, k=0):
        pg = pages_by_id.get(pid)
        if not pg:
            return
        if rec is not None:
            pg = copy.deepcopy(pg)
            pg["_rec"] = rec
            if k:
                pg["id"] = f"{pid}~{k + 1}"
        out.append(pg)
    for pid in list(plan.get("front") or []) + head:
        put(pid)
    for rec in chunks:
        if not isinstance(rec, dict) or not faces:
            continue
        best = max(faces, key=lambda f: score(f, rec))
        if score(best, rec)[0] == 0:
            continue
        k = n.get(best["pages"][0], 0)
        n[best["pages"][0]] = k + 1
        for pid in best["pages"]:
            put(pid, rec, k)
    for pid in tail + list(plan.get("back") or []):
        put(pid)
    return out


def _slot(it):
    """글상자 · 그림 칸의 자리 이름. 글 잇기의 이어지는 상자(story_seq ≥ 2)는 자리가 아니다 — 이야기 하나 = 자리 하나, 원고는 첫 상자에만."""
    from core.units.render import story_cont
    a = it.get("atom") or {}
    b = (a.get("bind") or "").strip()
    if b and not b.startswith("sys.") and a.get("t") == "image":          # 그림 칸 자리 — 원고 값 = 그림 주소(http · data:) (인디자인 데이터 병합 이미지 필드)
        return b
    return b if b and not b.startswith("sys.") and a.get("t") == "text" and not story_cont(a) else None


def _reading_key(pg, width):
    """쪽 안 읽는 순서 — 단이 없으면 위 → 왼쪽. 단(pg.columns.n ≥ 2)이 있으면 단 순서(왼쪽 단 위→아래, 다음 단):
    여러 단에 걸친 상자(쪽 머리 제목 등)는 그 높이에서 단 순서를 끊고 먼저 읽는다(인디자인 기사 흐름처럼)."""
    col = pg.get("columns") or {}
    n = int(col.get("n") or 1)
    yx = lambda it: (round(float(it.get("y") or 0), 1), float(it.get("x") or 0))
    if n < 2:
        return lambda it: yx(it)
    m = pg.get("margins") or {}
    left = float(m.get("left", m.get("inside", 20)) or 0)
    right = float(m.get("right", m.get("outside", 20)) or 0)
    g = float(col.get("gutter") if col.get("gutter") is not None else 5)
    cw = max((float(width) - left - right - g * (n - 1)) / n, 1.0)
    width_ = lambda it: float(it.get("w") or (it.get("atom") or {}).get("w") or 0)      # 개체 폭(패널에서 고친 값)이 먼저
    col_of = lambda it: min(n - 1, max(0, int((float(it.get("x") or 0) + width_(it) / 2 - left + g / 2) // (cw + g))))   # 가운데가 든 단
    wide = lambda it: width_(it) > cw + g                               # 단 하나보다 넓다 = 여러 단에 걸친 상자(번호가 단 경계에 조금 걸친 것은 아니다)
    cuts = sorted(float(it.get("y") or 0) for it in pg.get("items") or [] if _slot(it) and wide(it))
    def key(it):
        y = float(it.get("y") or 0)
        seg = sum(1 for c in cuts if c <= y + 0.01)
        return (seg, 0, 0) + yx(it) if wide(it) else (seg, 1, col_of(it)) + yx(it)
    return key


def slots(pages, width_of=None):
    """문서의 자리 목록 — 읽는 순서대로 [(쪽 번호, 요소 번호, 자리 이름, 임시 글)]. 쪽 순서 → 쪽 안 읽는 순서(_reading_key).
    width_of(쪽) = 쪽 폭 mm(단 나누기에 쓴다, 없으면 210)."""
    out = []
    for pi, pg in enumerate(pages):
        items = [(i, it) for i, it in enumerate(pg.get("items") or []) if _slot(it)]
        key = _reading_key(pg, (width_of(pg) if width_of else None) or 210)
        items.sort(key=lambda t: key(t[1]))
        out += [(pi, i, _slot(it), (it.get("atom") or {}).get("text") or "") for i, it in items]
    return out


def schema(pages, width_of=None):
    """바깥에 알려 줄 자리 표 — 자리 이름마다 몇 번 나오는지와 임시 글(어떤 꼴의 글이 오는지 보기)."""
    sch = {}
    for _, _, name, sample in slots(pages, width_of):
        d = sch.setdefault(name, {"count": 0, "samples": []})
        d["count"] += 1
        if len(d["samples"]) < 3:
            d["samples"].append(sample if isinstance(sample, str) else "")
    return sch


def story_value(bind, records, slot_fmt=None):
    """여러 자리를 한 줄기 글로(인디자인 한 스토리 여러 단락 스타일) — bind = "번호+발문+지문+선지",
    records = [{자리: 글, …} 또는 [[자리, 글], …], …] 문항 순서(목록이면 그 문항 안 차례 그대로). 자리마다 문단(글 안 줄바꿈 = 문단 여럿)이 되고 문단 첫머리에 그 자리 표시(ps)가 붙어
    그리기(render._text_html)가 그 자리의 단락 스타일을 입힌다. slot_fmt[자리].inline 이면 따로 문단을 만들지 않고
    다음 문단 첫머리에 붙는다(문항 번호 — 발문 첫 줄 앞)."""
    fmt = slot_fmt or {}
    parts = [p for p in bind.split("+") if p]
    out, carry = [], []

    def para(slot, line):
        nonlocal carry
        if out:
            out.append("\n")
        out.append({"ps": slot, "t": ""})
        out.extend(carry)
        carry = []
        if line:
            out.append(line)
    for rec in records:
        if isinstance(rec, dict):                                       # {자리: 글} — 자리 차례는 bind 순서
            pairs = [(s, rec.get(s)) for s in parts]
        else:                                                           # [[자리, 글], …] — 문항마다 차례가 다를 때(보기가 지문 앞·뒤)
            pairs = [(x[0], x[1]) for x in rec if isinstance(x, (list, tuple)) and len(x) == 2]
        for s, v in pairs:
            if v in (None, ""):
                continue
            if (fmt.get(s) or {}).get("inline"):
                carry.append({"ps": s, "inline": True, "t": str(v)})
                continue
            if isinstance(v, (list, dict)):                             # 꾸밈 조각(문자 스타일 · 윗주 · 옆 메모) — 조각 그대로, 글 조각의 \n 에서 문단을 나눈다
                para(s, "")
                for r in (v if isinstance(v, list) else [v]):
                    if isinstance(r, str) and "\n" in r:
                        first, *rest = r.split("\n")
                        if first:
                            out.append(first)
                        for x in rest:
                            para(s, x)
                    else:
                        out.append(r)
                continue
            for line in str(v).split("\n"):
                para(s, line)
    if carry:                                                           # 붙을 문단이 없으면 제 문단으로
        para(carry[0]["ps"], "")
    return out


def story_cells(atom, name, items):
    """여러 자리 원고 → 그 글상자 값. 표 글상자(atom.table)면 항목 하나가 한 칸(칸마다 한 줄기), 아니면 항목 전부가 한 줄기"""
    if atom.get("table"):
        return [story_value(name, [r], atom.get("slot_fmt")) for r in items]
    return story_value(name, items, atom.get("slot_fmt"))


def fill(pages, content, width_of=None):
    """원고를 자리에 나눠 넣은 쪽 사본과 보고. 쪽 원본은 건드리지 않는다.
    보고 = {"filled": n, "unfilled": {자리: 남은 자리 수}, "extra": {자리: 남은 원고 수}, "unknown": [틀에 없는 자리 이름]}."""
    pages = copy.deepcopy(pages)
    runs = {pg.get("name") for pg in pages if pg.get("_rec") is not None}           # 「원고마다」 묶음 원고(plan_pages 가 레코드로 나눠 줬다)
    chunked = isinstance((content or {}).get("원고"), list)                      # 덩어리 차례 원고 — plan_pages 가 덩어리마다 면을 골라 레코드로 줬다
    queue = {k: (list(v) if isinstance(v, list) else [v]) for k, v in (content or {}).items() if k not in runs and not (chunked and k == "원고")}
    recq = {}                                                                     # 레코드마다 꺼낼 값 — 목록은 그 레코드의 쪽들(펼침면)을 이어 차례로, 글 하나는 그 레코드의 같은 자리 모두에
    known, filled, unfilled = set(runs), 0, {}
    for pi, i, name, _ in slots(pages, width_of):
        known.add(name)
        rec = pages[pi].get("_rec")
        parts = name.split("+")
        if rec is not None and name not in rec and len(parts) > 1 and all(p in rec and not isinstance(rec[p], list) for p in parts):
            # 여러 자리 한 줄 — 레코드의 글 자리들을 이어 쓴다(쪽 꼬리 「7강  분석」 = 강 + 회차). 바깥 시스템이 같은 값을 두 번 보내지 않게
            atom = pages[pi]["items"][i].get("atom") or {}
            pages[pi]["items"][i]["fields"] = {name: story_value(name, [{p: rec[p] for p in parts}], atom.get("slot_fmt"))}
            filled += 1
            continue
        if rec is not None and name in rec:
            v = rec[name]
            if "+" in name and isinstance(v, list) and v and isinstance(v[0], (dict, list)):   # 흐름 자리
                atom = pages[pi]["items"][i].get("atom") or {}
                if per_occurrence(v) and not atom.get("story"):            # 쪽마다 제 몫 — [[왼쪽 쪽 문항들], [오른쪽 쪽 문항들]] (글 잇기 안 한 상자는 한 몫씩)
                    rq = recq.setdefault((id(rec), name), list(v))
                    items = rq.pop(0) if rq else []
                    pages[pi]["items"][i]["fields"] = {name: story_cells(atom, name, items) if items else ""}
                    filled += len(items)
                    continue
                pages[pi]["items"][i]["fields"] = {name: story_cells(atom, name, v)}   # 이 벌의 문항 목록 전부(글 잇기 상자들로 흐른다 · 표면 칸마다)
                filled += len(v)
                continue
            if not isinstance(v, list):                                            # 글 하나 = 레코드 전체의 값(두 쪽 머리의 제목 등)
                pages[pi]["items"][i]["fields"] = {name: v}
                filled += 1
                continue
            if not v:                                                              # 빈 목록 = 이 레코드엔 이 자리가 없다 — 접는다
                pages[pi]["items"][i]["fields"] = {name: ""}
                continue
            rq = recq.setdefault((id(rec), name), list(v))                         # 같은 레코드의 쪽들은 한 줄로 이어 꺼낸다 — 왼쪽 면 지문 둘, 오른쪽 면 다음 둘
            if rq:
                pages[pi]["items"][i]["fields"] = {name: rq.pop(0)}
                filled += 1
            else:                                                                  # 이 벌의 원고가 모자라다(지문 4칸에 1개) — 틀 글(«자리 이름»)을 내보이지 않고 비운다
                pages[pi]["items"][i]["fields"] = {name: ""}
                unfilled[name] = unfilled.get(name, 0) + 1
            continue
        q = queue.get(name)
        if q and "+" in name and isinstance(q[0], (dict, list)):              # 여러 자리 한 줄기 — 문항 목록 전부가 이 글(잇기 상자들로 흘러간다)
            atom = pages[pi]["items"][i].get("atom") or {}
            pages[pi]["items"][i]["fields"] = {name: story_cells(atom, name, q)}
            filled += len(q)
            q.clear()
        elif q:
            pages[pi]["items"][i]["fields"] = {name: q.pop(0)}     # 그리기는 글상자의 fields 를 자리 값으로 쓴다
            filled += 1
        else:
            unfilled[name] = unfilled.get(name, 0) + 1
    for pg in pages:                                                              # 빈 원고(""·[]) — 그 글상자는 접힌다(render.place_items: 접기 묶음째, 아래 것을 당긴다)
        for it in pg.get("items") or []:
            f = it.get("fields")
            if f and all(blank(v) for v in f.values()):
                it["_empty"] = True
    extra = {k: len(v) for k, v in queue.items() if v and k in known}
    unknown = sorted(k for k in queue if k not in known)
    return pages, {"filled": filled, "unfilled": unfilled, "extra": extra, "unknown": unknown}


def per_occurrence(v):
    """흐름 자리 원고가 「쪽마다 제 몫」 꼴인가 — [[문항, …], [문항, …]] (문항 = {자리: 글} 또는 [[자리, 글], …]).
    문항 하나가 [[자리, 글], …] 인 꼴([[["번호", "01"], …], …])과 가른다: 몫의 첫 원소가 문항(사전 또는 [자리, 글] 목록)이면 몫."""
    if not (isinstance(v, list) and v and isinstance(v[0], list)):
        return False
    f = v[0]
    if not f:
        return True
    x = f[0]
    return isinstance(x, dict) or (isinstance(x, list) and bool(x) and isinstance(x[0], list))


def blank(v):
    """원고가 일부러 비운 값 — 빈 글 · 빈 목록 · 빈 문항 줄기(인디자인 데이터 병합 「빈 필드 줄 제거」)"""
    if v is None:
        return False
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, list):
        return all(blank(x) or x == "\n" for x in v) if v else True
    if isinstance(v, dict):
        return "ps" in v and not str(v.get("t") or "").strip()
    return False
