"""입력 → 원자 목록(`decomposed`). PDF 면은 PyMuPDF 로 직접, 이미지·프롬프트는 클로드가 같은 형식으로 그린다.

    from_pdf(path, pno)          벡터(선·면·도형)·글(span)·이미지가 이미 오브젝트다 — 그대로 원자로.
                                 인디자인 PDF 에 실제로 있는 것을 잃지 않는다: 회전(글·그림)·불투명·선 끝·
                                 자유 도형(화살표·체크·말풍선·로고 → path)·둥근 모서리 반지름·글 안의 굵게·기울임·위첨자·다른 색(rich)
    from_ai(prompt, image=...)   클로드 — 결과 형식은 같다 (JSON 글로 받는다)
    to_part(dec, indices, ...)   후보(원자 번호 묶음) → 부품 (원점을 묶음의 왼쪽 위로 옮긴다)

색·서체는 잰 값 그대로 두지 않고 토큰(`$c1` `$f1`)으로 뺀다 — 값은 함께 나온 tokens 에 있고,
라우트가 그것을 임시 옷으로 저장한다. 그래야 부품이 옷을 갈아입을 수 있다.
"""
import collections
import json
import math
import os

PT = 25.4 / 72.0
MODEL = os.environ.get("YONE_ASSIST_MODEL", "claude-opus-5")


def _hex(c):
    if c is None:
        return None
    if isinstance(c, int):
        return "#%06x" % c
    if isinstance(c, (tuple, list)) and len(c) >= 3:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x * 255)))) for x in c[:3])
    return None


class _Tokens(object):
    """잰 색·서체에 이름을 붙인다 — 자주 나온 순서로 c1, c2… / f1, f2…"""

    def __init__(self):
        self.color = collections.Counter()
        self.font = collections.Counter()

    def c(self, hx):
        if not hx:
            return None
        self.color[hx] += 1
        return hx

    def f(self, name):
        if not name:
            return None
        self.font[name] += 1
        return name

    def finish(self, atoms):
        cmap = {hx: f"c{i + 1}" for i, (hx, _n) in enumerate(self.color.most_common())}
        fmap = {nm: f"f{i + 1}" for i, (nm, _n) in enumerate(self.font.most_common())}
        for a in atoms:
            for k in ("color", "fill"):
                if a.get(k) in cmap:
                    a[k] = "$" + cmap[a[k]]
            st = a.get("stroke")
            if st and st.get("color") in cmap:
                st["color"] = "$" + cmap[st["color"]]
            if a.get("font") in fmap:
                a["font"] = "$" + fmap[a["font"]]
            if isinstance(a.get("text"), list):
                for r in a["text"]:
                    if isinstance(r, dict):
                        if r.get("color") in cmap:
                            r["color"] = "$" + cmap[r["color"]]
                        if r.get("font") in fmap:
                            r["font"] = "$" + fmap[r["font"]]
        return {"color": {v: k for k, v in cmap.items()}, "font": {v: k for k, v in fmap.items()}}


def from_pdf(path, pno=1):
    import fitz
    doc = fitz.open(path)
    if not (1 <= pno <= len(doc)):
        raise ValueError(f"면 {pno} 없음 (1~{len(doc)})")
    page = doc[pno - 1]
    tb = page.trimbox if page.trimbox and page.trimbox.width > 10 else page.rect
    ox, oy = tb.x0, tb.y0
    W, H = tb.width * PT, tb.height * PT
    tk = _Tokens()
    texts, shapes, imgs = [], [], []           # 그리는 순서 = PDF 순서: 도형 → 그림 → 글

    def mm(v):
        return round(v * PT, 2)

    # ── 밑줄 후보: 얇은 가로 선·납작한 채운 네모. 글자 바로 밑에 있으면 글 조각의 u 가 되고 선 원자로는 안 나온다
    drawings = page.get_drawings()
    ul = {}
    for d in drawings:
        r = d.get("rect")
        if r is None or r.height > 1.6 or r.width < 2:
            continue
        if d.get("fill") or (d.get("color") and 0 < float(d.get("width") or 0) <= 1.6):
            ul[d.get("seqno")] = (r.x0, r.x1, (r.y0 + r.y1) / 2)
    consumed = set()

    # ── 글: 줄 단위로 읽어 같은 서체·크기·색이 이어지면 한 글상자로. 인디자인 PDF 는 줄마다
    #    블록이 갈리는 일이 많아 블록 경계를 넘어 잇는다 (줄 머리 간격 + 가로 겹침으로 판단).
    #    끝이 이른 줄 다음은 새 단락(\n), 둘째 줄부터 들여 있으면 내어쓰기(indent + 음수 indent_first)
    cur = None
    for b in page.get_text("rawdict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            spans = []
            for sp in ln.get("spans", []):
                sp["text"] = "".join(ch.get("c", "") for ch in sp.get("chars", []))
                if sp["text"].strip():
                    spans.append(sp)
            if not spans:
                continue
            main = max(spans, key=lambda s: len(s.get("text", "")))
            dv = ln.get("dir") or (1, 0)
            ang = round(math.degrees(math.atan2(dv[1], dv[0])), 1)      # 글 방향 → 회전(°, 시계 방향, y 아래)
            if abs(ang) < 0.5:
                ang = 0.0
            key = (main.get("font"), round(main.get("size", 0), 1), _hex(main.get("color")), main.get("flags", 0) & 19, ang)
            x0, y0, x1, y1 = ln["bbox"]
            # 밑줄 후보 중 이 줄보다 두 글자 넘게 긴 것(제목 밑 괘선)은 밑줄이 아니다
            cand = {k: v for k, v in ul.items() if v[1] - v[0] <= (x1 - x0) + 2 * key[1]} if not ang else None
            line = {"runs": _runs(spans, main, tk, cand, consumed), "x0": x0, "x1": x1}
            # 같은 서체·크기·색이고 줄 머리 간격이 두 글자 높이 안이면 같은 글상자. 회전한 줄은 줄마다 원자
            if (cur and not ang and cur["key"] == key and 0 < y0 - cur["last_y0"] < key[1] * 2.0
                    and x0 < cur["x1"] and x1 > cur["x0"]):
                cur["lines_"].append(line)
                cur["x0"], cur["x1"], cur["y1"] = min(cur["x0"], x0), max(cur["x1"], x1), max(cur["y1"], y1)
                cur["last_y0"] = y0
            else:
                if cur:
                    texts.append(_text_atom(cur, ox, oy, tk))
                cur = {"key": key, "lines_": [line], "x0": x0, "y0": y0, "x1": x1, "y1": y1, "last_y0": y0}
    if cur:
        texts.append(_text_atom(cur, ox, oy, tk))

    # ── 도형 — 선·네모·원·둥근 네모는 그 원자로, 나머지(삼각형·화살표·체크·말풍선·로고)는 path 로 잃지 않고
    page_area = tb.width * tb.height
    for d in drawings:
        items = d.get("items") or []
        r = d.get("rect")
        if r is None or not items or d.get("seqno") in consumed:
            continue
        kinds = {it[0] for it in items}
        fill, stroke = _hex(d.get("fill")), _hex(d.get("color"))
        width = float(d.get("width") or 0)
        if fill in ("#ffffff",) and r.width * r.height > page_area * 0.9:
            continue                                                  # 면 바탕
        if not fill and (not stroke or width <= 0):
            continue
        st = _stroke_of(d, stroke, width, tk)
        extra = {}
        ops = [v for v in ((d.get("fill_opacity") if fill else None), (d.get("stroke_opacity") if st else None))
               if v is not None and float(v) < 0.995]
        if ops:
            extra["opacity"] = round(float(min(ops)), 3)
        x, y, w, h = mm(r.x0 - ox), mm(r.y0 - oy), mm(r.width), mm(r.height)
        lines = [it for it in items if it[0] == "l"]
        if kinds == {"l"} and len(items) == 1 and st:
            _t, p1, p2 = items[0]
            shapes.append(dict({"t": "line", "x1": mm(p1.x - ox), "y1": mm(p1.y - oy), "x2": mm(p2.x - ox), "y2": mm(p2.y - oy), "stroke": st}, **extra))
            continue
        if kinds == {"l"} and (w < 0.3 or h < 0.3) and st:
            # 가로·세로 한 줄로 이어진 선들 — 한 선으로
            if w >= h:
                a = {"t": "line", "x1": x, "y1": round(y + h / 2, 2), "x2": round(x + w, 2), "y2": round(y + h / 2, 2), "stroke": st}
            else:
                a = {"t": "line", "x1": round(x + w / 2, 2), "y1": y, "x2": round(x + w / 2, 2), "y2": round(y + h, 2), "stroke": st}
            shapes.append(dict(a, **extra))
            continue
        a = {"t": "rect", "x": x, "y": y, "w": max(w, 0.1), "h": max(h, 0.1)}
        if kinds == {"re"} and len(items) == 1:
            pass
        elif kinds == {"l"} and 3 <= len(items) <= 4 and _on_box(lines, r):
            pass                                                      # 축에 나란한 네 변 = 네모
        elif kinds == {"c"} and len(items) == 4:
            a["t"] = "ellipse"                                        # 인디자인 원·타원 = 곡선 4개
        elif kinds == {"l", "c"} and len(items) == 8 and _on_box(lines, r):
            cs = [it for it in items if it[0] == "c"]
            a["radius"] = _corner_radii(cs, r)                            # 둥근 모서리 반지름(모서리마다 다르면 4개)
        else:
            a["t"] = "path"
            a["d"] = _unit_path(items, r, bool(d.get("closePath")))
            if d.get("even_odd"):
                a["evenodd"] = True
        if fill:
            a["fill"] = tk.c(fill)
        if st:
            a["stroke"] = st
        a.update(extra)
        shapes.append(a)

    # ── 이미지 — 회전은 변환 행렬로, 틀 안에서 잘린 것은 클립(scissor)으로: 틀 = 보이는 자리, img = 그림 전체의 자리
    n = 0
    try:
        clips = [fitz.Rect(d["scissor"]) for d in page.get_drawings(extended=True) if d.get("type") == "clip" and d.get("scissor")]
    except Exception:
        clips = []
    for info in page.get_image_info(xrefs=True):
        bx = fitz.Rect(info["bbox"])
        if bx.is_empty or bx.width < 2 or bx.height < 2:
            continue
        n += 1
        ma, mb, mc, md = (info.get("transform") or (1, 0, 0, 1, 0, 0))[:4]
        ang = round(math.degrees(math.atan2(mb, ma)), 1)               # 그림의 x 축 방향 → 회전
        iw, ih = math.hypot(ma, mb), math.hypot(mc, md)
        if abs(ang) >= 0.5 and iw > 0 and ih > 0:
            cx, cy = (bx.x0 + bx.x1) / 2 - ox, (bx.y0 + bx.y1) / 2 - oy
            imgs.append({"t": "image", "x": mm(cx - iw / 2), "y": mm(cy - ih / 2), "w": mm(iw), "h": mm(ih), "src": f"img{n}", "rotate": ang})
            continue
        frame = _image_frame(bx, clips)
        if frame is None:
            imgs.append({"t": "image", "x": mm(bx.x0 - ox), "y": mm(bx.y0 - oy), "w": mm(bx.width), "h": mm(bx.height), "src": f"img{n}"})
        else:
            imgs.append({"t": "image", "x": mm(frame.x0 - ox), "y": mm(frame.y0 - oy), "w": mm(frame.width), "h": mm(frame.height), "src": f"img{n}",
                         "img": {"x": mm(bx.x0 - frame.x0), "y": mm(bx.y0 - frame.y0), "w": mm(bx.width), "h": mm(bx.height)}})

    # 재단 밖(도련)은 잘라 내고, 밖에만 있는 것은 버린다
    atoms = [a for a in shapes + imgs + texts if _clip(a, W, H)]
    tokens = tk.finish(atoms)
    dec = {"from": f"pdf:{os.path.basename(path)}#{pno}", "w": round(W, 2), "h": round(H, 2), "atoms": atoms, "tokens": tokens}
    dec["parts"] = group(dec)
    return dec


def _clip(a, W, H):
    """재단선 안으로 자른다. 밖에만 있으면 False."""
    if a["t"] == "line":
        x0, x1 = sorted((a["x1"], a["x2"]))
        y0, y1 = sorted((a["y1"], a["y2"]))
        if x1 < 0 or y1 < 0 or x0 > W or y0 > H:
            return False
        a["x1"], a["x2"] = round(max(x0, 0), 2), round(min(x1, W), 2)      # 방향은 뜻이 없다
        a["y1"], a["y2"] = round(max(y0, 0), 2), round(min(y1, H), 2)
        return True
    x0, y0, x1, y1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return False
    if a["t"] not in ("text", "path") and not a.get("rotate"):   # 글·도형·회전한 것은 자르면 모양이 준다 — 자리만 둔다
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        a["x"], a["y"], a["w"], a["h"] = round(x0, 2), round(y0, 2), round(max(x1 - x0, 0.1), 2), round(max(y1 - y0, 0.1), 2)
    return True


def _text_atom(cur, ox, oy, tk):
    font, size, color, _flags, ang = cur["key"]
    lines = cur["lines_"]
    bw, bh = cur["x1"] - cur["x0"], cur["y1"] - cur["y0"]
    if ang:
        # 회전한 줄의 bbox 는 축에 나란한 테두리 — 원래 폭·높이를 되짚는다 (45° 근처는 글자 높이로 어림)
        c, sn = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
        det = c * c - sn * sn
        if abs(det) > 0.1:
            w_pt, h_pt = (bw * c - bh * sn) / det, (bh * c - bw * sn) / det
        else:
            h_pt = size * 1.3
            w_pt = (bw - h_pt * sn) / max(c, 0.01)
        w_pt, h_pt = max(w_pt, size), max(h_pt, size)
        cx, cy = (cur["x0"] + cur["x1"]) / 2 - ox, (cur["y0"] + cur["y1"]) / 2 - oy
        x0, y0, w_mm, h_mm = (cx - w_pt / 2) * PT, (cy - h_pt / 2) * PT, w_pt * PT + 1.5, h_pt * PT
    else:
        x0, y0, w_mm, h_mm = (cur["x0"] - ox) * PT, (cur["y0"] - oy) * PT, bw * PT + 1.5, bh * PT   # 브라우저 서체가 조금 넓어도 줄이 안 늘게
    # 단락: 끝이 이른 줄(오른쪽 끝이 글상자 오른쪽보다 1.5글자 넘게 짧다) 다음은 새 단락
    maxx1 = max(l["x1"] for l in lines)
    paras = [[lines[0]]]
    for prev, ln in zip(lines, lines[1:]):
        if prev["x1"] < maxx1 - 1.5 * size:
            paras.append([ln])
        else:
            paras[-1].append(ln)
    runs, indent = [], None
    for pi, para in enumerate(paras):
        if pi:
            runs.append({"t": "\n"})
        pr = para[0]["runs"]
        for ln in para[1:]:
            pr = _runs_join(pr, ln["runs"])
        runs.extend(pr)
        if len(para) > 1 and indent is None:
            indent = min(l["x0"] for l in para[1:]) - para[0]["x0"]         # 둘째 줄부터 들여 있으면 내어쓰기
    lead = round(h_mm / max(len(lines), 1) / PT, 1) if len(lines) > 1 else None
    a = {"t": "text", "x": round(x0, 2), "y": round(y0, 2), "w": round(w_mm, 2), "h": round(h_mm, 2),
         "font": tk.f(font), "size": round(size, 1), "color": tk.c(color) or "#000000", "text": _runs_finish(runs)}
    if lead:
        a["leading"] = lead
    if indent is not None and indent > 1.0:
        a["indent"] = round(indent * PT, 2)
        a["indent_first"] = -a["indent"]
    elif indent is not None and indent < -1.0:
        a["indent_first"] = round(-indent * PT, 2)
    if ang:
        a["rotate"] = ang
    return a


def _runs(spans, main, tk, ul=None, consumed=None):
    """줄의 span 들 → 조각. 단락의 서체·크기·색(main)과 같으면 그냥 글, 다르면 {t, b, i, u, sup, color, font, size}.
    ul(밑줄 후보 seqno → (x0, x1, y))이 있으면 글자마다 바로 밑에 선이 있는지 보고 u 를 붙인다."""
    mfont, msize, mcol, mfl = main.get("font"), round(main.get("size", 0), 1), _hex(main.get("color")), main.get("flags", 0)
    out = []
    for sp in spans:
        base = {}
        fl = sp.get("flags", 0)
        if sp.get("font") != mfont:
            base["font"] = tk.f(sp.get("font"))
        if round(sp.get("size", 0), 1) != msize:
            base["size"] = round(sp.get("size", 0), 1)
        if _hex(sp.get("color")) != mcol:
            base["color"] = tk.c(_hex(sp.get("color")))
        if fl & 16 and not mfl & 16:
            base["b"] = True
        if fl & 2 and not mfl & 2:
            base["i"] = True
        if fl & 1:
            base["sup"] = True
        chars = sp.get("chars") or []
        if not ul or not chars:
            out.append(dict(base, t=sp.get("text", "")))
            continue
        base_y = chars[0].get("origin", (0, sp["bbox"][3]))[1]
        for ch in chars:
            r = dict(base, t=ch.get("c", ""))
            cx = (ch["bbox"][0] + ch["bbox"][2]) / 2
            for seq, (ux0, ux1, uy) in ul.items():
                if ux0 - 0.5 <= cx <= ux1 + 0.5 and base_y - 0.3 <= uy <= sp["bbox"][3] + 1.5:
                    r["u"] = True
                    consumed.add(seq)
                    break
            out.append(r)
    return _merge_runs(out)


def _tags_to_runs(text):
    """클로드가 적은 <u>…</u> <b>…</b> <i>…</i> → 조각. 태그가 없으면 그대로 글."""
    import re as _re
    if not isinstance(text, str) or "<" not in text:
        return text
    runs, flags = [], {}
    for tok in _re.split(r"(</?[ubi]>)", text):
        if not tok:
            continue
        m = _re.fullmatch(r"<(/?)([ubi])>", tok)
        if m:
            flags[m.group(2)] = not m.group(1)
            continue
        runs.append(dict({k: True for k, v in flags.items() if v}, t=tok))
    return _runs_finish(runs)


def _merge_runs(runs):
    merged = []
    for r in runs:
        attrs = {k: v for k, v in r.items() if k != "t"}
        if merged and {k: v for k, v in merged[-1].items() if k != "t"} == attrs:
            merged[-1]["t"] += r["t"]
        else:
            merged.append(dict(r))
    return merged


def _runs_join(a, b):
    """줄과 줄 사이에 띄어쓰기 하나."""
    if a and not a[-1]["t"].endswith(" ") and b and not b[0]["t"].startswith(" "):
        b = [dict(b[0], t=" " + b[0]["t"])] + b[1:]
    return a + b


def _runs_finish(runs):
    """이웃한 같은 서식은 합치고, 서식이 하나도 없으면 그냥 글(str)."""
    merged = _merge_runs(runs)
    if all(len(r) == 1 for r in merged):
        return "".join(r["t"] for r in merged)
    return [r["t"] if len(r) == 1 else r for r in merged]


def _stroke_of(d, stroke, width, tk):
    if not stroke or width <= 0:
        return None
    st = {"w": round(max(width, 0.2), 2), "color": tk.c(stroke)}
    ds = d.get("dashes")
    if ds and ds not in ("[] 0", "[]", "", None):
        try:
            dash = [float(x) * PT for x in ds.strip("[] 0").replace("]", "").split()] or None
        except ValueError:
            dash = None
        if dash:
            st["dash"] = [round(x, 2) for x in dash]
    cap = d.get("lineCap")
    cap = cap[0] if isinstance(cap, (tuple, list)) and cap else cap
    if cap in (1, 2):
        st["cap"] = "round" if cap == 1 else "square"
    join = d.get("lineJoin")
    join = join[0] if isinstance(join, (tuple, list)) and join else join
    if join in (1, 2):
        st["join"] = "round" if join == 1 else "bevel"
    so = d.get("stroke_opacity")
    if so is not None and 0 <= float(so) < 1:
        st["tint"] = round(float(so) * 100)          # PDF 의 획 투명도 → 색조(같은 색의 옅은 값)
    return st


def _corner_radii(curves, r):
    """둥근 네모의 곡선 4개 → 모서리 반지름. 곡선의 가운데가 상자 어느 귀퉁이에 있는지로 자리를 찾는다."""
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    out = [0.0, 0.0, 0.0, 0.0]                                 # 왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래
    for it in curves:
        rad = round(abs(it[1].x - it[4].x) * PT, 2)
        mx, my = (it[1].x + it[4].x) / 2, (it[1].y + it[4].y) / 2
        k = (0 if my < cy else 3) if mx < cx else (1 if my < cy else 2)
        out[k] = rad
    return out[0] if max(out) - min(out) < 0.1 else out


def _image_frame(bx, clips):
    """그림(bx)을 실제로 자르는 클립 — bx 와 겹치되 bx 를 다 담지는 않는 것 중 겹침이 가장 큰 것. 없으면 None."""
    best, best_area = None, 0.0
    for c in clips:
        inter = bx & c
        if inter.is_empty or inter.width < 1 or inter.height < 1:
            continue
        if c.x0 <= bx.x0 + 0.5 and c.y0 <= bx.y0 + 0.5 and c.x1 >= bx.x1 - 0.5 and c.y1 >= bx.y1 - 0.5:
            continue                                            # 그림을 다 담는 클립(면 클립·그룹 클립)은 자르는 게 아니다
        area = inter.width * inter.height
        if area > best_area:
            best, best_area = inter, area
    return best


def _on_box(lines, r, tol=0.05):
    """선들이 모두 축에 나란하고 점이 전부 상자 테두리 위에 있으면 네모(둥근 네모의 변)다."""
    if not lines:
        return False
    for _t, p1, p2 in lines:
        if abs(p1.x - p2.x) > tol and abs(p1.y - p2.y) > tol:
            return False
        for p in (p1, p2):
            on_x = abs(p.x - r.x0) <= tol or abs(p.x - r.x1) <= tol
            on_y = abs(p.y - r.y0) <= tol or abs(p.y - r.y1) <= tol
            if not (on_x or on_y):
                return False
    return True


def _unit_path(items, r, close):
    """PyMuPDF 경로 항목 → 상자 안 0~1 비율의 SVG path (M L C Z). 폭·높이를 바꾸면 따라 늘어난다."""
    W, H = max(r.width, 1e-3), max(r.height, 1e-3)

    def u(p):
        return f"{(p.x - r.x0) / W:.4f} {(p.y - r.y0) / H:.4f}"

    out, cur = [], None
    for it in items:
        k = it[0]
        if k in ("l", "c"):
            p1, p2 = it[1], it[-1]
            if cur is None or abs(cur.x - p1.x) > 0.01 or abs(cur.y - p1.y) > 0.01:
                out.append("M " + u(p1))
            out.append(("L " + u(p2)) if k == "l" else ("C " + u(it[2]) + " " + u(it[3]) + " " + u(p2)))
            cur = p2
        elif k == "re":
            rr = it[1]
            out.append(f"M {u(rr.top_left)} L {u(rr.top_right)} L {u(rr.bottom_right)} L {u(rr.bottom_left)} Z")
            cur = None
        elif k == "qu":
            q = it[1]
            out.append(f"M {u(q.ul)} L {u(q.ur)} L {u(q.lr)} L {u(q.ll)} Z")
            cur = None
    if close and out and not out[-1].endswith("Z"):
        out.append("Z")
    return " ".join(out)


def _top(a):
    return min(a["y1"], a["y2"]) if a["t"] == "line" else a["y"]


def _bottom(a):
    return max(a["y1"], a["y2"]) if a["t"] == "line" else a["y"] + a["h"]


def _box(atoms):
    xs0 = [min(a["x1"], a["x2"]) if a["t"] == "line" else a["x"] for a in atoms]
    xs1 = [max(a["x1"], a["x2"]) if a["t"] == "line" else a["x"] + a["w"] for a in atoms]
    y0, y1 = min(_top(a) for a in atoms), max(_bottom(a) for a in atoms)
    return [round(min(xs0), 2), round(y0, 2), round(max(xs1) - min(xs0), 2), round(y1 - y0, 2)]


def _bx(a):
    if a["t"] == "line":
        return min(a["x1"], a["x2"]), min(a["y1"], a["y2"]), max(a["x1"], a["x2"]), max(a["y1"], a["y2"])
    return a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]


def group(dec, gap=1.5):
    """부품 후보 — 원자에서 부품으로 올라가는 첫 걸음. 세 가지로 묶는다:
    1) 상자(면·도형·그림) 안에 든 것은 그 상자와 한 묶음 (지문 상자 + 안의 글)
    2) 같은 줄(세로로 절반 넘게 겹침, 한쪽은 15mm 이하)에 있는 것은 한 묶음 (문장 + 오른쪽 끝 O/X). 키 큰 것끼리 나란하면 단
    3) 가로로 겹치고 세로로 gap(mm) 안에 쌓인 것은 한 묶음 (발문 + 선지)
    면의 절반 넘는 큰 상자는 바탕으로 보고 뺀다. 두 단(가로로 안 겹침)은 갈라진다."""
    atoms = dec.get("atoms") or []
    W, H = float(dec.get("w") or 210), float(dec.get("h") or 297)
    idx = [i for i, a in enumerate(atoms)
           if not (a["t"] in ("rect", "image", "path") and a["w"] * a["h"] > W * H * 0.5)]
    box = {i: _bx(atoms[i]) for i in idx}
    area = {i: (box[i][2] - box[i][0]) * (box[i][3] - box[i][1]) for i in idx}
    parent = list(range(len(atoms)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    # 1) 상자 안에 든 것 — 가장 작은 상자(자기보다 큰)에 붙인다
    holders = [i for i in idx if atoms[i]["t"] in ("rect", "path", "image") and area[i] >= 40]
    top = []
    for i in idx:
        x0, y0, x1, y1 = box[i]
        best = None
        for c in holders:
            if c == i or area[c] <= area[i]:
                continue
            cx0, cy0, cx1, cy1 = box[c]
            if cx0 - 0.5 <= x0 and cy0 - 0.5 <= y0 and x1 <= cx1 + 0.5 and y1 <= cy1 + 0.5:
                if best is None or area[c] < area[best]:
                    best = c
        if best is None:
            top.append(i)
        else:
            union(best, i)
    # 위 단계 뒤의 덩어리 — 덩어리의 테두리는 맨 바깥 상자(또는 홀로 있는 원자)
    ext = {}
    for i in idx:
        r = find(i)
        x0, y0, x1, y1 = box[i]
        e = ext.get(r)
        ext[r] = (x0, y0, x1, y1) if e is None else (min(e[0], x0), min(e[1], y0), max(e[2], x1), max(e[3], y1))
    # 면 가장자리에 닿은 것(러닝헤드 띠·측면 탭·바탕)은 면의 장식 — 줄·쌓임으로는 안 묶는다
    edge = {r: (e[0] <= 0.5 or e[1] <= 0.5 or e[2] >= W - 0.5 or e[3] >= H - 0.5
                or (atoms[r]["t"] == "line" and e[3] - e[1] > e[2] - e[0]))            # 세로 선(단 나눔 괘선)도 장식
            for r, e in ext.items()}
    roots = sorted((r for r in ext if not edge[r]), key=lambda r: (ext[r][1], ext[r][0]))
    seps = [ext[r] for r in ext if atoms[r]["t"] == "line" and ext[r][3] - ext[r][1] > 30 and ext[r][3] - ext[r][1] > ext[r][2] - ext[r][0]]   # 단 나눔 세로 괘선

    def divided(a, b):
        """두 상자 사이에 세로 괘선이 지나가면 다른 단."""
        lo, hi = min(a[2], b[2]), max(a[0], b[0])
        for sx0, sy0, sx1, sy1 in seps:
            if lo <= sx0 <= hi and sy0 <= max(a[1], b[1]) and sy1 >= min(a[3], b[3]):
                return True
        return False
    # 2) 같은 줄(세로 겹침이 작은 쪽의 절반·큰 쪽의 3할 넘음) · 3) 가까이 쌓임(가로 겹침 + 세로 gap 안)
    for a_i, ra in enumerate(roots):
        ax0, ay0, ax1, ay1 = ext[ra]
        for rb in roots[a_i + 1:]:
            bx0, by0, bx1, by1 = ext[rb]
            over = min(ay1, by1) - max(ay0, by0)
            hgap = max(ax0, bx0) - min(ax1, bx1)
            hs = (ay1 - ay0, by1 - by0)
            same_row = (over > 0.5 * min(hs) and over > 0.3 * max(hs) and hgap < W * 0.5 and min(hs) <= 15   # 키 큰 것끼리 나란하면 단(column)
                        and not divided(ext[ra], ext[rb]))
            stacked = -over <= gap and hgap < 0
            if same_row or stacked:
                union(ra, rb)
    groups = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    ordered = sorted(groups.values(), key=lambda g: min(_top(atoms[i]) for i in g))
    out = []
    for n, g in enumerate(ordered, 1):
        g.sort()
        texts = [_plain(atoms[i]["text"]) for i in g if atoms[i]["t"] == "text" and atoms[i].get("text")]
        hint = (texts[0][:18] + "…") if texts and len(texts[0]) > 18 else (texts[0] if texts else "")
        out.append({"name": f"후보 {n}" + (f" · {hint}" if hint else ""), "atoms": g, "box": _box([atoms[i] for i in g])})
    return out


def _plain(t):
    return t if isinstance(t, str) else "".join(r if isinstance(r, str) else r.get("t", "") for r in (t or []))


def to_part(dec, indices, pid, name):
    """후보 → 부품. 원점을 묶음의 왼쪽 위로 옮긴다."""
    atoms = [json.loads(json.dumps(dec["atoms"][i])) for i in indices]
    if not atoms:
        raise ValueError("원자가 없다")
    x0, y0, w, h = _box(atoms)
    for a in atoms:
        if a["t"] == "line":
            a["x1"], a["x2"] = round(a["x1"] - x0, 2), round(a["x2"] - x0, 2)
            a["y1"], a["y2"] = round(a["y1"] - y0, 2), round(a["y2"] - y0, 2)
        else:
            a["x"], a["y"] = round(a["x"] - x0, 2), round(a["y"] - y0, 2)
    return {"id": pid, "name": name, "w": max(w, 1.0), "h": max(h, 1.0), "atoms": atoms, "from": dec.get("from", "")}


# ── 클로드 — 이미지·프롬프트 ──────────────────────────────────────────
_FLAT_ATOM = {
    "type": "object",
    "properties": {
        "t": {"enum": ["text", "line", "rect", "ellipse", "image", "path"]},
        "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
        "x1": {"type": "number"}, "y1": {"type": "number"}, "x2": {"type": "number"}, "y2": {"type": "number"},
        "font": {"type": "string"}, "size": {"type": "number"}, "color": {"type": "string"},
        "fill": {"type": "string"}, "stroke_color": {"type": "string"}, "stroke_w": {"type": "number"}, "dashed": {"type": "boolean"},
        "align": {"enum": ["left", "center", "right", "justify"]}, "text": {"type": "string"}, "bind": {"type": "string"},
        "radius": {"type": "number"}, "src": {"type": "string"},
        "d": {"type": "string"}, "rotate": {"type": "number"}, "opacity": {"type": "number"},
        "indent": {"type": "number"}, "indent_first": {"type": "number"}, "tracking": {"type": "number"}, "inset": {"type": "number"},
    },
    "required": ["t"], "additionalProperties": False,
}
_NV = {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                                  "required": ["name", "value"], "additionalProperties": False}}
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "w": {"type": "number"}, "h": {"type": "number"},
        "atoms": {"type": "array", "items": _FLAT_ATOM},
        "tokens": {"type": "object", "properties": {"color": _NV, "font": _NV}, "required": ["color", "font"], "additionalProperties": False},
        "parts": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "atoms": {"type": "array", "items": {"type": "integer"}}},
                                             "required": ["name", "atoms"], "additionalProperties": False}},
        "note": {"type": "string"},
    },
    "required": ["w", "h", "atoms", "tokens", "parts", "note"], "additionalProperties": False,
}

AI_SYSTEM = """너는 인쇄 교재 조판 디자이너다. 받은 그림 또는 설명을 **인디자인 오브젝트(원자)** 로 분해해 JSON 으로만 답한다.

원자 6종: text(글상자) · line(선) · rect(면) · ellipse(원) · image(그림) · path(도형). 단위는 mm, 원점은 왼쪽 위. 글자 크기·선 굵기는 pt.
모든 원자에 rotate(°, 시계 방향, 가운데 축)·opacity(0~1)를 붙일 수 있다 — 기울어진 배지, 반투명 상자.
- text: x y w h font size color [align text bind indent indent_first tracking inset]. 밑줄·굵게는 따로 선을 긋지 말고 text 안에서 <u>…</u> <b>…</b> 로 적는다(조각으로 바뀐다). 콘텐츠가 들어갈 자리는 bind 에 필드 이름(영문 소문자: no, prompt, passage, sentence, choices, answer, kr …)을 적고 text 에는 견본 글을 넣는다. 고정 글(라벨 "O", "정답")은 bind 없이 text 만.
- line: x1 y1 x2 y2 stroke_color stroke_w [dashed]
- rect: x y w h [fill stroke_color stroke_w radius]  · ellipse: x y w h [fill stroke_color stroke_w]
- image: x y w h src
- path: x y w h d [fill stroke_color stroke_w] — 화살표·체크·별·말풍선·삼각형처럼 네모·원이 아닌 도형. d 는 SVG path(M L C Q Z 만), 좌표는 x y w h 상자 안의 0~1 비율. 예: 오른쪽 화살표 "M0 0.3 L0.6 0.3 L0.6 0 L1 0.5 L0.6 1 L0.6 0.7 L0 0.7 Z"
색·서체는 값이 아니라 **토큰 이름**으로 적고(color: "ink", font: "body" 처럼) tokens 에 이름→값을 준다(색은 #rrggbb, 서체는 family 이름).
parts 는 원자를 부품(뜻이 있는 묶음: 지문 상자, 발문+선지, O/X 줄, 러닝헤드…)으로 묶은 것 — atoms 는 원자 번호(0부터).
w h 는 전체 캔버스 크기(mm). 그림이면 실제 비율로, 설명이면 기본 폭 170mm 안에서.
지어내지 말고 보이는 것만. 미심쩍은 것은 note 에 한 줄."""


def from_ai(prompt="", image=None, media_type="image/png", name="", tokens=None):
    """tokens(옷의 tokens)를 주면 그 이름만 쓰게 한다 — 새 요소가 지금 옷을 그대로 입는다."""
    import anthropic
    content = []
    sys_extra = ""
    if tokens:
        cs = ", ".join(sorted((tokens.get("color") or {}).keys()))
        fs = ", ".join(sorted((tokens.get("font") or {}).keys()))
        sys_extra = (f"\n\n색 토큰은 이 이름만 쓴다: {cs} (ink=본문 먹, mute=회색 글, rule=괘선, sel=강조 파랑, s1~s3=구간 주색, cream/sky=상자 바탕, white). "
                     f"서체 토큰은 이 이름만: {fs} (body=본문, disp=발문, label=라벨, num=번호). tokens 에는 새로 만든 이름만 넣는다.")
    if image:
        import base64
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image).decode()}})
        content.append({"type": "text", "text": "이 그림을 원자로 분해하라." + (f" 참고: {prompt}" if prompt else "")})
    else:
        content.append({"type": "text", "text": "이 설명대로 원자를 그려라:\n" + prompt})
    # 구조화 출력(json_schema)은 원자 스키마가 "too complex" 로 거절된다 — 글로 받아 JSON 만 잘라 읽는다
    r = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=16000, system=AI_SYSTEM + sys_extra + "\n\n답은 JSON 하나뿐(코드 펜스·설명 없이). 형식:\n" + json.dumps(AI_SCHEMA, ensure_ascii=False),
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in r.content if b.type == "text")
    raw = json.loads(text[text.find("{"):text.rfind("}") + 1])
    atoms = []
    for a in raw.get("atoms") or []:
        t = a.get("t")
        st = None
        if a.get("stroke_color") or a.get("stroke_w"):
            st = {"w": float(a.get("stroke_w") or 0.5), "color": "$" + a["stroke_color"] if a.get("stroke_color") else "$ink"}
            if a.get("dashed"):
                st["dash"] = [1, 1]
        if t == "text":
            o = {"t": "text", "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 50), "h": a.get("h", 5),
                 "font": "$" + (a.get("font") or "body"), "size": float(a.get("size") or 8), "color": "$" + (a.get("color") or "ink")}
            for k in ("align", "bind", "indent", "indent_first", "tracking", "inset"):
                if a.get(k):
                    o[k] = a[k]
            if a.get("text"):
                o["text"] = _tags_to_runs(a["text"])
        elif t == "line":
            o = {"t": "line", "x1": a.get("x1", 0), "y1": a.get("y1", 0), "x2": a.get("x2", 10), "y2": a.get("y2", 0), "stroke": st or {"w": 0.5, "color": "$ink"}}
        elif t in ("rect", "ellipse"):
            o = {"t": t, "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 10), "h": a.get("h", 10)}
            if a.get("fill"):
                o["fill"] = "$" + a["fill"]
            if st:
                o["stroke"] = st
            if t == "rect" and a.get("radius"):
                o["radius"] = a["radius"]
        elif t == "image":
            o = {"t": "image", "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 20), "h": a.get("h", 20), "src": a.get("src") or "img1"}
        elif t == "path" and a.get("d"):
            o = {"t": "path", "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 10), "h": a.get("h", 10), "d": a["d"]}
            if a.get("fill"):
                o["fill"] = "$" + a["fill"]
            if st:
                o["stroke"] = st
        else:
            continue
        if a.get("rotate"):
            o["rotate"] = float(a["rotate"])
        if a.get("opacity") is not None and 0 <= float(a["opacity"]) < 1:
            o["opacity"] = float(a["opacity"])
        atoms.append(o)
    tokens = {"color": {x["name"]: x["value"] for x in raw["tokens"].get("color", [])},
              "font": {x["name"]: x["value"] for x in raw["tokens"].get("font", [])}}
    dec = {"from": f"image:{name}" if image else "prompt", "w": float(raw.get("w") or 170), "h": float(raw.get("h") or 50),
           "atoms": atoms, "tokens": tokens, "note": raw.get("note", "")}
    parts = []
    for p in raw.get("parts") or []:
        ids = [i for i in p.get("atoms", []) if 0 <= i < len(atoms)]
        if ids:
            parts.append({"name": p.get("name") or f"후보 {len(parts) + 1}", "atoms": ids, "box": _box([atoms[i] for i in ids])})
    dec["parts"] = parts or group(dec)
    return dec
