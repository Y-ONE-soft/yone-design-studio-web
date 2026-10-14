"""옛 편집기 데이터 → 인디자인 맞춤 꼴(2026-10-14, docs/편집기_재현/인디자인_맞춤.md).

한 번만 돈다 — 바꾼 항목에 idv(IDV)를 찍는다. 새로 저장하는 항목은 store.put 이 찍는다(이미 새 꼴).
화면은 그대로 두고 값을 인디자인 기능으로 옮긴다:
- 단락 음영 「여백」(글을 밀던 안쪽 여백) → 음영 오프셋 + 들여쓰기 · 단락 앞뒤 공백, 흰 음영 + 테두리 → 단락 테두리 오프셋.
- 자동 행간 145% · 자동 크기 「높이만」(옛 기본) → 값을 적어 둔다(새 기본은 120% · 끔).
- 첫 줄 자리(크롬 줄 상자) → 첫 번째 기준선 오프셋 「어센트」로 바뀐 만큼 프레임을 옮긴다.
- GREP 규칙의 직접 꾸밈 → 문자 스타일, 문자 스타일 바탕 · 띠 → 밑줄 옵션(pt), 굵게 → 글꼴 스타일(굵기 700).
- 데이터 필드 「앞에 붙이기」 → 같은 단락에 이어 쓰는 필드(번호는 문자 스타일, 자리는 탭 정지), 글머리 글 → 글머리 기호.
- 데이터 필드 고정 개체(문단 끝 · 다음 줄 · 사용자 정의 · 첫 · 끝 문단만) → 인라인 · 줄 위 · 사용자 정의, 필드 앞 · 뒤.
- 글 끝 개체(tail) → 데이터 필드 고정 개체. 윗주 기본값(문자 스타일 · 거리) → 글꼴 · 크기 · 오프셋 Y.
- 표 칸 사이 → 셀 획, 텍스트 감싸기 쪽 · 오프셋, 획 점선 → 유형 파선, 탭 간격 → 탭 정지, 없앤 칸(낱말 최소 · 좌우 반전 …)은 지운다.
"""
import hashlib
import json

IDV = 2
PT = 0.3528
LEGACY_LEAD = 1.45                    # 옛 자동 행간
_DIRECT = ("b", "i", "color", "size", "bshift", "weight", "font", "track", "nobreak", "u", "line", "line_off", "line_color")


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ── 스타일 ──────────────────────────────────────────────────────────
def pstyle(st, metrics=None):
    """단락 스타일(또는 텍스트 프레임 단락 값) 하나를 새 꼴로 — 고친 dict"""
    st = dict(st)
    if any(k in st for k in ("pad", "pad_top", "pad_bottom")):
        pad = _f(st.pop("pad", 0))
        pt, pb = _f(st.pop("pad_top", pad)), _f(st.pop("pad_bottom", pad))
        if st.get("shade"):
            ol, orr = _f(st.get("shade_ol")), _f(st.get("shade_or"))
            if st.get("shade_fit"):
                st["indent"] = round(_f(st.get("indent")) + pad, 3)
                st["indent_right"] = round(_f(st.get("indent_right")) + pad, 3)
                st["shade_ol"] = st["shade_or"] = round(pad, 3)
            else:
                st["indent"] = round(_f(st.get("indent")) + pad - ol, 3)
                st["indent_right"] = round(_f(st.get("indent_right")) + pad - orr, 3)
            st["shade_ot"], st["shade_ob"] = round(pt, 3), round(pb, 3)
            st["space_before"] = round(_f(st.get("space_before")) + pt, 3)
            st["space_after"] = round(_f(st.get("space_after")) + pb, 3)
            st.setdefault("space_same", 0)                            # 옛 그리기는 같은 필드 음영 문단 사이를 0 으로 붙였다
    if st.get("border") and st.get("shade"):                          # 옛 테두리는 음영 둘레 — 단락 테두리 오프셋을 음영과 같게
        for k in ("ot", "ob", "ol", "or"):
            if st.get("shade_" + k) is not None:
                st.setdefault("border_" + k, st["shade_" + k])
        if st.get("shade_fit"):
            st.setdefault("border_fit", True)
        if st.get("shade_r"):
            st.setdefault("border_r", st["shade_r"])
    if st.get("size") and not st.get("leading"):
        st["leading"] = round(_f(st["size"]) * LEGACY_LEAD, 3)
    if st.get("b") and not st.get("weight"):
        st["weight"] = 700
    st.pop("b", None)
    jc = st.get("jc")
    if isinstance(jc, dict) and (jc.get("letter_min") is not None or jc.get("letter_max") is not None):
        sp = (metrics or {}).get("space") or 0.25                     # ‰ em → 공백 폭 %
        jc = dict(jc)
        for k in ("letter_min", "letter_max"):
            if jc.get(k) is not None:
                jc[k] = round(_f(jc[k]) / sp / 10, 2)
        st["jc"] = jc
    for k in ("word_min", "justify_mode", "word_spacing"):
        st.pop(k, None)
    return st


def cstyle(cs):
    """문자 스타일 하나를 새 꼴로"""
    cs = dict(cs)
    if cs.get("b") and not cs.get("weight"):
        cs["weight"] = 700
    cs.pop("b", None)
    if cs.get("u") and any(k in cs for k in ("line", "line_off", "line_color")):
        lw = _f(cs.pop("line", 0.18), 0.18)
        cs["u_w"] = round(lw / PT, 3)
        cs["u_off"] = round((_f(cs.pop("line_off", 0.4), 0.4) - lw / 2) / PT, 3)
        if cs.get("line_color"):
            cs["u_color"] = cs.pop("line_color")
        cs.pop("line_color", None)
    if cs.get("bg"):
        if cs.get("bg_band"):                                         # 띠 — 굵은 밑줄을 위로(인디자인 형광)
            band, off = _f(cs.pop("bg_band")), _f(cs.pop("bg_off", 0))
            if not cs.get("u"):
                cs.update(u=True, u_w=round(band / PT, 3), u_off=round(-(off + band / 2) / PT, 3), u_color=cs["bg"])
        else:                                                         # 바탕 상자 — 글 높이를 덮는 굵은 밑줄(모서리는 인디자인에 없다)
            pad = _f(cs.get("bg_pad"))
            S = _f(cs.get("size"), 9) * PT
            if not cs.get("u"):
                cs.update(u=True, u_w=round((S + 2 * pad) / PT, 3), u_off=round(-(0.88 * S + pad) / PT, 3), u_color=cs["bg"])
        for k in ("bg", "bg_pad", "bg_r", "bg_band", "bg_off"):
            cs.pop(k, None)
    return cs


def _grep_cs(rule, skin):
    """GREP 규칙의 직접 꾸밈 → 문자 스타일(이름은 꾸밈 값으로 정한다 — 같은 꾸밈은 같은 스타일)"""
    direct = {k: rule[k] for k in _DIRECT if rule.get(k) not in (None, "", False)}
    if not direct:
        return rule
    base = dict(((skin.get("cstyles") or {}).get(rule.get("cs")) or {})) if rule.get("cs") else {}
    if direct.get("u"):
        direct.setdefault("line", direct.get("line") or 0.18)
    base.update(direct)
    cs = cstyle(base)
    name = "GREP " + hashlib.md5(json.dumps(cs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:6]
    skin.setdefault("cstyles", {})[name] = cs
    out = {k: v for k, v in rule.items() if k not in _DIRECT}
    out["cs"] = name
    return out


# ── 개체 ────────────────────────────────────────────────────────────
def _anc(anc):
    """데이터 필드 고정 개체 옛 꼴 → 인디자인 꼴"""
    if not isinstance(anc, dict) or "pos" in anc and anc.get("pos") in ("inline", "above", "custom"):
        return anc
    a = {k: anc[k] for k in ("part", "text", "w", "h") if k in anc}
    pos = anc.get("pos") or "end"
    if pos == "end":
        a.update(pos="inline", x=_f(anc.get("gap")), y=-_f(anc.get("dy")))
        if anc.get("space"):
            a["space"] = True
    elif pos == "line":
        a.update(pos="above", before=_f(anc.get("gap")))
        if anc.get("x") is not None:
            a["x"] = _f(anc.get("x"))
    else:
        a.update(pos="custom", xref="frame", yref="leading", x=_f(anc.get("x")), y=_f(anc.get("dy")))
    a["at"] = "start" if anc.get("first") else "end"
    return a


def _ruby_defaults(r, size, skin):
    """텍스트 프레임 윗주 기본값 옛 꼴(문자 스타일 · 위 · 아래 거리 기준선에서) → 글꼴 · 크기 · 색상 · 오프셋 Y(글자 상자에서)"""
    r = dict(r)
    S = _f(size, 9) * PT
    if r.get("cs"):
        cs = (skin.get("cstyles") or {}).get(r["cs"]) or {}
        for k in ("font", "size", "color"):
            if cs.get(k) is not None:
                r.setdefault(k, cs[k])
        r.pop("cs")
    r.setdefault("size", round(_f(size, 9) * 0.6, 3))                 # 옛 기본 60%
    if "off_above" in r:
        r["oy_above"] = round(_f(r.pop("off_above")) - 0.88 * S, 3)
    else:
        r["oy_above"] = round(0.4 - 0.88 * S, 3)
    if "off_below" in r:
        r["oy_below"] = round(_f(r.pop("off_below")) - 0.12 * S, 3)
    else:
        r["oy_below"] = round(0.6 - 0.12 * S, 3)
    if r.get("align") not in (None, "", "center"):
        r.pop("align")
    return r


def _ruby_run(rb, size, skin):
    if not isinstance(rb, dict):
        return rb
    rb = dict(rb)
    S = _f(size, 9) * PT
    if rb.get("cs"):
        cs = (skin.get("cstyles") or {}).get(rb["cs"]) or {}
        for k in ("font", "size", "color"):
            if cs.get(k) is not None:
                rb.setdefault(k, cs[k])
        rb.pop("cs")
    if "off" in rb:
        rb["oy"] = round(_f(rb.pop("off")) - (0.12 if rb.get("pos") == "below" else 0.88) * S, 3)
    if "ox" in rb:
        rb["ox"] = _f(rb["ox"])
    return rb


def _runs(v, size, skin):
    if isinstance(v, list):
        return [_runs(x, size, skin) for x in v]
    if isinstance(v, dict) and "ruby" in v:
        rb = v["ruby"]
        v = dict(v, ruby=[_ruby_run(x, size, skin) for x in rb] if isinstance(rb, list) else _ruby_run(rb, size, skin))
    return v


def text_atom(a, skin, ctx=None, notes=None):
    """텍스트 프레임 하나를 새 꼴로 — 고친 dict"""
    a = dict(a)
    size = _f(a.get("size"), 9)
    if not a.get("leading"):
        a["leading"] = round(size * LEGACY_LEAD, 3)
    v = a.get("auto_size")
    a["auto_size"] = "off" if v is False or v == "off" else "both" if v == "both" else "height"
    if a.get("tab") and not a.get("tabs"):                             # 탭 간격 → 탭 정지
        t = _f(a.pop("tab"))
        if t > 0:
            a["tabs"] = [{"at": round(t * k, 3)} for k in range(1, int(_f(a.get("w"), 100) / t) + 1)]
    a.pop("tab", None)
    for k in ("word_min", "justify_mode", "word_spacing", "anchor"):
        a.pop(k, None)
    if a.get("case") == "lower":
        a.pop("case")
    if a.get("b") and not a.get("weight"):
        a["weight"] = 700
    a.pop("b", None)
    bul = a.pop("bullet", None)
    if bul:
        a["list"] = ({"type": "bullet", "char": {"disc": "•", "circle": "○", "square": "■"}[bul], "after": " "} if bul in ("disc", "circle", "square")
                     else {"type": "number", "format": {"decimal": "1.", "decimal-paren": "1)", "upper-alpha": "A.", "lower-alpha": "a."}.get(bul, "1."), "after": " "})
    if a.get("grep"):
        a["grep"] = [_grep_cs(r, skin) for r in a["grep"]]
    if a.get("ruby"):
        a["ruby"] = _ruby_defaults(a["ruby"], size, skin)
    if a.get("text"):
        a["text"] = _runs(a["text"], size, skin)
    st = pstyle({k: a[k] for k in a if k in ("pad", "pad_top", "pad_bottom", "shade", "shade_fit", "shade_ol", "shade_or", "shade_r", "border",
                                             "indent", "indent_right", "space_before", "space_after", "jc")})
    a.update(st)
    for k in ("pad", "pad_top", "pad_bottom"):
        a.pop(k, None)
    fm = {f: dict(x) for f, x in (a.get("slot_fmt") or {}).items() if isinstance(x, dict)}
    order = [f for f in str(a.get("bind") or "").split("+") if f]
    styles = skin.get("styles") or {}
    for f, x in fm.items():
        if x.get("anc"):
            x["anc"] = _anc(x["anc"])
        bt = x.pop("bullet_text", None)
        if bt:
            x["list"] = {"type": "bullet", "char": bt.rstrip(), "after": bt[len(bt.rstrip()):]}
        if x.get("inline") and any(k in x for k in ("inline_w", "inline_gap", "drop")) or (x.get("inline") and x.get("style") and not x.get("cs")):
            src = dict(styles.get(x.get("style")) or {}, **{k: x[k] for k in ("font", "size", "color", "weight", "tracking", "drop") if k in x})
            cs = {k2: src[k] for k, k2 in (("font", "font"), ("size", "size"), ("color", "color"), ("weight", "weight"), ("tracking", "track")) if src.get(k) not in (None, "")}
            if src.get("drop"):
                cs["bshift"] = round(-_f(src["drop"]) / PT, 3)
            name = (x.get("style") or f) + " (번호)"
            skin.setdefault("cstyles", {})[name] = cs
            x["cs"] = name
            w_ = x.pop("inline_w", None)
            x.pop("inline_gap", None)
            x.pop("drop", None)
            if w_:
                x["sep"] = "\t"
                nxt = next((g for g in order[order.index(f) + 1:] if not (fm.get(g) or {}).get("inline")), None) if f in order else None
                if nxt:
                    ns = dict(a, **{k: v2 for k, v2 in styles.get((fm.get(nxt) or {}).get("style"), {}).items()})
                    start = _f(ns.get("indent")) + _f(ns.get("indent_first"))
                    fm.setdefault(nxt, {})["tabs"] = [{"at": round(start + _f(w_), 3)}]
            else:
                x["sep"] = " "
                if notes is not None:
                    notes.append(f"필드 {f} 뒤 간격 → 공백 하나(인디자인에 mm 간격 없음)")
    if fm:
        a["slot_fmt"] = fm
    tail = a.pop("tail", None)
    if tail and tail.get("part"):                                      # 글 끝 개체 → 데이터 필드(하나)의 고정 개체 · 고정 글이면 글 끝 고정 개체
        anc = {"part": tail["part"], "pos": "inline", "at": "end", "x": _f(tail.get("gap")), "y": -_f(tail.get("drop"))}
        if tail.get("space"):
            anc["space"] = True
        if a.get("bind") and "+" not in a["bind"] and not str(a["bind"]).startswith("sys."):
            a.setdefault("slot_fmt", {}).setdefault(a["bind"], {})["anc"] = anc
        else:
            t0 = a.get("text") or ""
            a["text"] = (t0 if isinstance(t0, list) else [t0]) + [{"t": "", "anc": anc}]
    wrap = a.get("wrap")
    if isinstance(wrap, dict) and "side" in wrap:
        wrap = dict(wrap)
        wrap["to"] = {"left": "right", "right": "left"}.get(wrap.pop("side"), "largest")
        a["wrap"] = wrap
    tb = a.get("table")
    if isinstance(tb, dict) and (tb.get("gap_x") or tb.get("gap_y")):
        tb = dict(tb)
        g = max(_f(tb.pop("gap_x", 0)), _f(tb.pop("gap_y", 0)))
        tb.setdefault("stroke", {"w": round(g / PT, 3), "color": "#ffffff"})
        a["table"] = tb
    if ctx is not None and a.get("t") == "text" and a.get("valign") in (None, "", "top"):
        try:                                                           # 첫 번째 기준선 오프셋 「어센트」 — 옛 첫 줄(크롬 줄 상자 + 첫 기준선 mm) 자리를 지키게 프레임을 옮긴다
            from core.units import render
            ctx.skin = skin
            html, _ = render._text_content(ctx, a, {}, {})
            shift = render._first_baseline(a, html, ctx)[0]
            d = -shift + _f(a.pop("first_baseline", 0))
            if abs(d) > 0.001:
                a["y"] = round(_f(a.get("y")) + d, 3)
                if _f(a.get("h")) > d:
                    a["h"] = round(_f(a.get("h")) - d, 3)
        except Exception as e:                                         # 못 재면 그대로
            if notes is not None:
                notes.append(f"첫 기준선 옮기기 못 함 {e}")
    a.pop("first_baseline", None)
    return a


def atom(a, skin, ctx=None, notes=None):
    if not isinstance(a, dict):
        return a
    if a.get("t") == "text":
        return text_atom(a, skin, ctx, notes)
    a = dict(a)
    st = a.get("stroke")
    if isinstance(st, dict) and st.get("dash") and not st.get("type"):
        a["stroke"] = dict(st, type="dashed")
    wrap = a.get("wrap")
    if isinstance(wrap, dict) and "side" in wrap:
        wrap = dict(wrap)
        wrap["to"] = {"left": "right", "right": "left"}.get(wrap.pop("side"), "largest")
        a["wrap"] = wrap
    for k in ("skewy", "overprint"):
        a.pop(k, None)
    return a


# ── 문서 묶음 · 저장소 ────────────────────────────────────────────────
def migrate(lib, notes=None):
    """편집기 데이터(store.library() 꼴 · 문서 묶음 꼴 둘 다) → 새 꼴. idv 가 없는 항목만. 고친 종류 이름 집합"""
    from core.units import render
    changed = set()
    skins = lib.get("skins")
    if skins is None and isinstance(lib.get("skin"), dict):           # 문서 묶음(package)
        skins = [lib["skin"]]
    skins = skins or []
    by = {s.get("id"): s for s in skins if isinstance(s, dict)}
    for sk in skins:
        if not isinstance(sk, dict) or sk.get("idv") == IDV:
            continue
        toks = (sk.get("tokens") or {}).get("font") or {}
        for n, st in list((sk.get("styles") or {}).items()):
            fam = st.get("font") or ""
            fam = toks.get(fam[1:], fam) if str(fam).startswith("$") else fam
            sk["styles"][n] = pstyle(st, render.font_metrics(fam, st.get("weight") or 400) if fam else None)
        for n, cs in list((sk.get("cstyles") or {}).items()):
            sk["cstyles"][n] = cstyle(cs)
        sk["idv"] = IDV
        changed.add("skins")
    plans = lib.get("plans") or ([lib["plan"]] if isinstance(lib.get("plan"), dict) else [])
    skin_of_page = {}
    for pl in plans:
        for sec in ("front", "back"):
            for x in pl.get(sec) or []:
                pid = x.get("page") if isinstance(x, dict) else x
                skin_of_page.setdefault(pid, pl.get("skin"))
        for sec in pl.get("sections") or []:
            for x in sec.get("pages") or []:
                pid = x.get("page") if isinstance(x, dict) else x
                skin_of_page.setdefault(pid, pl.get("skin"))
    base = by.get("base") or (skins[0] if skins else {"id": "base", "styles": {}, "cstyles": {}})
    for kind in ("pages", "parts"):
        for it in lib.get(kind) or []:
            if not isinstance(it, dict) or it.get("idv") == IDV:
                continue
            sk = by.get(skin_of_page.get(it.get("id"))) or base
            ctx = render.Ctx(sk, {"skins": skins, "parts": lib.get("parts") or [], "blocks": lib.get("blocks") or [], "pages": lib.get("pages") or []}, {})
            if kind == "pages":
                it.pop("mirror", None)
                for x in it.get("items") or []:
                    if isinstance(x, dict) and isinstance(x.get("atom"), dict):
                        x["atom"] = atom(x["atom"], sk, ctx, notes)
            else:
                it["atoms"] = [atom(a, sk, ctx, notes) for a in it.get("atoms") or []]
            it["idv"] = IDV
            changed.add(kind)
            if sk in skins:
                changed.add("skins")
    return changed
