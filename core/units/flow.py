"""넘침 — 값이 끼워진 지면이 면 아래로 넘치면 **다음 면으로 이어 흘린다**. 인디자인의 텍스트 스레드.

    thread(ctx, page, spec) → [면1, 면2, …]   (각각 items 가 조정된 지면 사본)

규칙
  · 한계선 = 면 높이 - 아래 여백(page.margins.bottom, 없으면 20mm).
  · 놓았을 때(place_items) 한계선을 넘는 첫 요소를 찾는다. 머리말·쪽번호(system)는 고정이라 안 본다.
  · 그 요소가 글 자리(콘텐츠 블록, rich/text 필드)면 **글을 자른다**: 들어가는 만큼은 이 면에, 나머지는
    다음 면 같은 자리에. 글이 아니면(선지 목록 등) 통째로 다음 면으로.
  · 그 뒤의(더 아래 놓인) 요소들은 다음 면으로 같이 넘어간다 — 원래 자리(템플릿 좌표)에 다시 놓인다.
  · 다음 면 = 같은 지면 템플릿. 앞선 요소들은 빠지고, 고정 요소는 그대로.
  · 글 자르기는 render.text_h 와 같은 어림(글자 폭)으로 센다 — 브라우저 줄바꿈과 몇 mm 어긋날 수 있다.
"""
import json
import math

from core.units import render, sample

MIN_KEEP = 24          # 이만큼도 안 들어가면 자르지 않고 통째로 넘긴다 (글자 수)


def _limit(page, spec):
    m = page.get("margins") or {}
    return float(spec["h"]) - float(m.get("bottom") or 20)


def _text_atoms(ctx, it):
    """블록 요소의 (부품, [글 원자 with bind]) — 자를 후보."""
    blk = ctx.blocks.get(it.get("block")) if it.get("block") else None
    if not blk:
        return None, []
    v = render.variant_of(ctx, blk)
    part = ctx.parts.get(v.get("part")) if v else None
    if not part:
        return None, []
    types = blk.get("fields") or {}
    atoms = [ctx.styled(a) for a in part["atoms"] if a.get("t") == "text" and a.get("bind") and (types.get(a["bind"]) or {}).get("type") in ("rich", "text")]
    return part, atoms


def _plain(v):
    return render.rich_plain(v)


def _split_value(v, n):
    """값(문자열 또는 서식 조각 목록)을 앞 n 글자 / 나머지로. 낱말 경계에서 자른다."""
    plain = _plain(v)
    cut = plain.rfind(" ", 0, n + 1)
    if cut < n * 0.6:
        cut = n
    if isinstance(v, str):
        return v[:cut].rstrip(), v[cut:].lstrip()
    # 서식 조각 목록 — 조각 경계 따라 나눈다
    head, tail, used = [], [], 0
    for frag in v:
        t = frag if isinstance(frag, str) else str(frag.get("t", ""))
        if used >= cut:
            tail.append(frag)
            continue
        if used + len(t) <= cut:
            head.append(frag)
            used += len(t)
            continue
        k = cut - used
        if isinstance(frag, str):
            head.append(frag[:k].rstrip()); tail.append(frag[k:].lstrip())
        else:
            a, b = dict(frag), dict(frag)
            a["t"], b["t"] = t[:k].rstrip(), t[k:].lstrip()
            head.append(a); tail.append(b)
        used = cut
    return head, tail


def split_fit(ctx, it, avail, width):
    """요소가 avail mm 안에 들어가도록 글을 자른다 → (이 면 필드, 다음 면 필드) 또는 None(못 자름)."""
    part, atoms = _text_atoms(ctx, it)
    if not part or not atoms:
        return None
    fields = dict(it.get("fields") or {})
    blk = ctx.blocks.get(it["block"])
    filled = sample.fill(blk, fields)
    # 가장 긴 글 원자를 자른다 (지문 상자 등). 나머지 원자 높이는 그대로 든다고 본다
    a = max(atoms, key=lambda a: len(_plain(filled.get(a["bind"]))))
    val = filled.get(a["bind"])
    plain = _plain(val)
    if not plain:
        return None
    sx = (float(width) / float(part["w"])) if width and part.get("w") else 1.0
    aw = a["w"] * sx
    other = float(part.get("h") or 0) - a["h"]                      # 글 원자 말고 차지하는 높이
    room = avail - other
    if room <= 0:
        return None
    # 앞 n 글자가 room 에 들어가는 최대 n — 이분 탐색 (text_h 와 같은 어림)
    lo, hi = 0, len(plain)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if render.text_h(plain[:mid], aw, a["size"], a.get("leading"), a) <= room + 0.01:
            lo = mid
        else:
            hi = mid - 1
    if lo < MIN_KEEP or lo >= len(plain):
        return None
    head, tail = _split_value(val, lo)
    if not _plain(tail).strip():
        return None
    f1, f2 = dict(fields), dict(fields)
    f1[a["bind"]] = head
    f2[a["bind"]] = tail
    return f1, f2


def thread(ctx, page, spec, max_pages=40):
    """값이 끼워진 지면 → 넘침을 다음 면으로 이어 흘린 면 목록."""
    W, H = float(spec["w"]), float(spec["h"])
    limit = _limit(page, spec)
    out = []
    stuck = set()                                    # 제자리에서 넘치는데 자를 수도 없는 요소 — 그대로 둔다
    cur = json.loads(json.dumps(page))
    for _ in range(max_pages * 3):
        cur["_flowed"] = True
        placed = render.place_items(ctx, cur, W, H)
        over = [p for p in placed if not p["fixed"] and p["y"] + p["h"] > limit + 0.01 and id(p["it"]) not in stuck]
        if not over:
            out.append(cur)
            return out
        first = min(over, key=lambda p: p["y"])
        it = first["it"]
        if first["dy"] < 0.01 and not (it.get("block") and split_fit(ctx, it, (limit - first["y"]) / float(it.get("s") or 1), it.get("w"))):
            # 밀린 것도 없이 제자리에서 넘치고 자를 수도 없다 — 다음 면에 놓아도 똑같다. 그대로 두고 알린다
            ctx.warn(f"{page.get('id')}: 요소 {it.get('block') or it.get('part') or '원자'} 이 제자리에서 면 아래로 넘친다 ({first['y'] + first['h']:.0f}mm > {limit:.0f}mm) — 자리를 올릴 것")
            stuck.add(id(it))
            continue
        movers = {p["fi"] for p in placed if not p["fixed"] and p["y"] >= first["y"] - 0.01 and p["fi"] != first["fi"]}
        nxt = json.loads(json.dumps(cur))
        split = split_fit(ctx, it, (limit - first["y"]) / float(it.get("s") or 1), it.get("w")) if it.get("block") else None
        items_now, items_next = [], []
        for fi, x in enumerate(cur.get("items") or []):
            fixed = is_fixed(ctx, x)
            if fixed:
                items_now.append(x); items_next.append(json.loads(json.dumps(x)))
            elif fi == first["fi"]:
                if split:
                    a, b = split
                    x1, x2 = dict(x), dict(x)
                    x1["fields"], x2["fields"] = a, b
                    items_now.append(x1); items_next.append(x2)
                else:
                    items_next.append(x)                                # 통째로 다음 면
            elif fi in movers:
                items_next.append(x)
            else:
                items_now.append(x)
        if not split and len(items_now) == sum(1 for x in items_now if is_fixed(ctx, x)) and not out:
            ctx.warn(f"{page.get('id')}: 요소 하나가 한 면보다 크다 — 자를 수 없어 그대로 둔다")
            cur["_flowed"] = True
            out.append(cur)
            return out
        cur["items"] = items_now
        out.append(cur)
        nxt["items"] = items_next
        cur = nxt
        if not any(not is_fixed(ctx, x) for x in items_next):
            return out
    ctx.warn(f"{page.get('id')}: 넘침이 {max_pages}면을 넘었다 — 멈춤")
    return out


def is_fixed(ctx, it):
    return render.is_fixed(ctx, it)
