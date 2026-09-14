"""책 1권 빌드 오케스트레이터 — `config.json` 하나로 원고→PDF.

**책은 이름 일부로 가리켜도 된다** — `bin/viv 광문보카 watch` 처럼. 절대경로도,
`--list` 가 찍어 주는 스튜디오 기준 상대경로도 그대로 받는다(목록에 보이는 것을
붙여 넣을 수 없으면 목록이 무슨 소용인가). 이름이 여러 권에 걸리면 후보를 보여 준다.

    bin/viv --list                          교재 트리의 책 목록
    bin/viv 광문보카 knobs                   ★ 만질 수 있는 값
    bin/viv 광문보카 watch                   라이브 미리보기(브라우저)

교재 폴더에서:
    python3 -m core.render_vivlio.book <책폴더> data      원고 → data.json
    python3 -m core.render_vivlio.book <책폴더> theme     팔레트 → 테마 재생성
    python3 -m core.render_vivlio.book <책폴더> knobs     ★ 만질 수 있는 값 목록
        … knobs --set="palette.gold=#c0392b"             값 바꾸기(config.json 에 쓴다)
        … knobs --reset="palette.gold"                   기본값으로 되돌리기
    python3 -m core.render_vivlio.book <책폴더> variants  시안 여러 벌을 한 장에
        … variants --knob=palette.gold --values="#a,#b,#c" [--pages=4]
    python3 -m core.render_vivlio.book <책폴더> render    조판 직전까지(HTML) — 빠름
    python3 -m core.render_vivlio.book <책폴더> watch     라이브 미리보기(브라우저)
    python3 -m core.render_vivlio.book <책폴더> build     조판 → PDF (+마감)
    python3 -m core.render_vivlio.book <책폴더> verify    검수 게이트
    python3 -m core.render_vivlio.book <책폴더> print     인쇄 원고(CMYK) 만들기
    python3 -m core.render_vivlio.book <책폴더> all       data → build → verify
    python3 -m core.render_vivlio.book --list            교재 트리의 책 목록

계열별 옵션은 `--키` / `--키=값` 으로 그대로 흘려보낸다(예: `--sample`, `--nomemo`).
"""
import os
import re
import sys

from core.render_vivlio import config as bookconfig
from core.render_vivlio import series as series_registry
from core.render_vivlio import verify as gate


def _series(cfg):
    return series_registry.get(cfg.series)


def load(path):
    return bookconfig.load(path)


def gen_data(cfg, log=print):
    return _series(cfg).gen_data(cfg, log)


def gen_theme(cfg, log=print):
    return _series(cfg).gen_theme(cfg, log)


def build(cfg, log=print, **opts):
    return _series(cfg).build(cfg, log, **opts)


def show_knobs(cfg, log=print, as_json=False, book=None, **_):
    """이 책에서 **무엇을 만질 수 있는지** 보여 준다.

    선언이 없으면 "아직 안 뚫린 계열"이라고 분명히 말한다 — 조용히 빈 목록을
    내면 '손잡이가 없다'와 '선언을 안 했다'를 구분할 수 없다.
    """
    from core.render_vivlio import knobs as kn
    items = kn.describe(cfg, _series(cfg))
    if as_json:
        import json as _json
        log(_json.dumps(items, ensure_ascii=False, indent=1))
        return items
    if not items:
        log(f"  계열 {cfg.series} 는 아직 손잡이를 선언하지 않았다 "
            f"(series 의 knobs() 를 채울 것)")
        return items
    who = book or cfg.book.get("title") or cfg.series
    log(f"  손잡이 {len(items)}개 — 값을 바꾸려면:")
    log(f"    bin/viv {who} knobs --set=\"{items[0]['key']}=<값>\"")
    for g in kn.GROUPS:
        rows = [d for d in items if d["group"] == g]
        if not rows:
            continue
        log(f"\n  [{g}]")
        for d in rows:
            mark = "●" if d["overridden"] else " "
            val = d["value"]
            unit = d.get("unit", "")
            log("   %s %-22s %-14s %-10s %s"
                % (mark, d["key"], d["label"],
                   f"{val}{unit}" if val is not None else "-",
                   d["affects"]))
    log("\n  ● = config.json 이 기본값을 덮어쓴 것")
    return items


def set_select(cfg, log=print, exclude=None, include=None, limits=None,
               order=None, clear=False, backup=True):
    """`config.json` 의 `select` 를 쓴다 — 「무엇을 빼고 몇 문항만 남길지」.

    손잡이(`set_knobs`)가 **값**을 쓴다면 이것은 **구성**을 쓴다.
    학교 프리셋이 정한 것을 그 책에 내려 주는 창구다(docs/25).

    exclude : 뺄 스텝 키. 쉼표로 여럿.
    include : 그중 이 책에서만 되돌릴 키 (exclude 를 이긴다).
    limits  : `step1_c2=4` 처럼 스텝마다 남길 지문 수. 쉼표로 여럿.
    clear   : select 를 통째로 지운다 (원고 그대로로 돌아간다).

    ⚠ 아는 스텝 키인지 먼저 본다 — 오타를 그대로 저장하면 **조용히 아무 일도
      안 일어난다.** 그게 가장 나쁜 실패다.
    """
    import json as _json
    import shutil
    series = _series(cfg)
    fn_sec = getattr(series, "sections", None)
    known = {d["key"] for d in (fn_sec(cfg) or [])} if fn_sec else set()

    def _keys(raw):
        out = [x.strip() for x in str(raw or "").split(",") if x.strip()]
        bad = [k for k in out if known and k not in known]
        if bad:
            raise SystemExit(f"모르는 섹션: {', '.join(bad)}\n"
                             f"  → `sections` 로 목록을 볼 것")
        return out

    sel = dict(cfg.section("select") or {}) if not clear else {}
    if clear:
        sel = None
    else:
        ex = _keys(exclude)
        inc = _keys(include)
        if ex:
            sel["exclude"] = ex
        if inc:
            sel["include"] = inc
        if order:
            sel["order"] = _keys(order)
        if limits:
            lim = dict(sel.get("limits") or {})
            for part in str(limits).split(","):
                if not part.strip():
                    continue
                k, _, n = part.partition("=")
                k = k.strip()
                if known and k not in known:
                    raise SystemExit(f"모르는 섹션: {k}")
                try:
                    lim[k] = {"passages": int(n)}
                except ValueError:
                    raise SystemExit(f"문항 수가 숫자가 아니다: {part}")
            sel["limits"] = lim

    path = cfg.path("config.json")
    with open(path, encoding="utf-8") as f:
        data = _json.loads(f.read())
    if sel is None:
        data.pop("select", None)
    else:
        data["select"] = sel
    if backup:
        shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    if sel is None:
        log("  select 를 지웠다 — 원고 그대로 나온다")
    else:
        log("  select → " + _json.dumps(sel, ensure_ascii=False))
    log("  → 지면에 반영하려면 `data build` (build 만으로는 구성이 안 바뀐다)")
    return sel


def set_css(cfg, log=print, text=None, file=None, clear=False, **_):
    """그 책의 `overrides.css` 를 쓴다 — **뼈대 위에 얹는 모양**이다.

    조판은 이 파일을 **맨 마지막에** 물리므로 무엇이든 이긴다(stage.py).
    뼈대(어떤 요소가 있는지)는 계열 코드가 만들고, 자리·크기·색은 여기서 얹는다.
    디자인 화면이 「지면에서 고르기」로 만든 규칙이 이리로 온다.
    """
    from core.render_vivlio import design_ops as ops
    if clear:
        ops.put(cfg, {"op": "css"}, None)
        log("  overrides.css 를 지웠다")
        return ""
    if file:
        with open(file, encoding="utf-8") as f:
            text = f.read()
    if text is None:
        cur = ops.get(cfg, {"op": "css"})
        log("  overrides.css %s" % ("없음" if cur is None else "%d자" % len(cur)))
        return cur
    ops.put(cfg, {"op": "css"}, text)
    log("  overrides.css ← %d자 · 규칙 %d개"
        % (len(text), text.count("{")))
    log("  → 지면에 반영하려면 `build`")
    return text


def show_sections(cfg, log=print, as_json=False, book=None, **_):
    """이 계열에서 **무엇을 넣고 뺄 수 있는지** 보여 준다.

    손잡이(`knobs`)가 「무엇을 만질 수 있는가」라면 이것은 「무엇을 넣고 뺄 수
    있는가」다. 학교 프리셋이 `layout.exclude` 로 고르는 목록이 바로 이것이라,
    화면이 목록을 또 적지 않도록 계열에서 받아 간다.

    선언이 없으면 「아직 안 뚫린 계열」이라고 분명히 말한다 — 조용히 빈 목록을
    내면 '섹션이 없다'와 '선언을 안 했다'를 구분할 수 없다.
    """
    series = _series(cfg)
    fn = getattr(series, "sections", None)
    items = list(fn(cfg) or []) if fn is not None else []
    if as_json:
        import json as _json
        log(_json.dumps(items, ensure_ascii=False, indent=1))
        return items
    if not items:
        log(f"  계열 {cfg.series} 는 아직 섹션을 선언하지 않았다 "
            f"(series 의 sections() 를 채울 것)")
        return items
    who = book or cfg.book.get("title") or cfg.series
    log(f"  섹션 {len(items)}개 — 빼려면 config 의 select.exclude 에 키를 적는다:")
    log(f"    bin/viv {who} select --exclude={items[0]['key']}")
    for it in items:
        tail = f"  ← {it['attach_to']} 에 딸림" if it.get("attach_to") else ""
        log("   %-16s %-12s STEP%s %s%s"
            % (it["key"], it["label"], it.get("step"), it.get("logo") or "", tail))
    return items


def set_knobs(cfg, log=print, assignments=(), reset=(), backup=True):
    """손잡이 값을 config.json 에 쓴다. `reset` 은 기본값으로 되돌린다(키 삭제).

    ⚠ config.json 은 손으로 예쁘게 들여쓴 파일이다(빈 줄 묶음, 한 줄로 쓴 객체,
      주석 구실을 하는 `_note`). 통째로 다시 쓰면 값은 맞지만 **그 서식이 전부
      사라진다** — 색 하나 바꿀 때마다 파일이 뒤집히면 안 되므로 **바뀐 자리만**
      갈아 끼운다(`knobs.patch_text`). 그렇게 못 하는 모양이면 통째 쓰기로
      물러서되 그 사실을 알린다. 어느 쪽이든 쓰기 전에 `.bak` 을 남긴다.
    """
    import json as _json
    import shutil
    from core.render_vivlio import knobs as kn
    known = {k.key: k for k in kn.of(cfg, _series(cfg))}
    changes = {}
    for a in assignments:
        key, _, raw = a.partition("=")
        key = key.strip()
        if key not in known:
            raise SystemExit(f"모르는 손잡이: {key}\n  → `knobs` 로 목록을 볼 것")
        k = known[key]
        v = raw.strip()
        if k.kind in ("mm", "pt", "number"):
            v = float(v) if "." in v else int(v)
        elif k.kind == "bool":
            v = v.lower() in ("1", "true", "yes", "on", "참")
        changes[key] = v
    for key in reset:
        key = key.strip()
        if key not in known:
            raise SystemExit(f"모르는 손잡이: {key}")
        if not known[key].resettable:
            raise SystemExit(
                f"{key} 는 되돌릴 수 없다 — 이 계열은 **config 가 원본**이라\n"
                f"  지우면 계열 코드의 임시 폴백으로 떨어져 디자인이 달라진다.\n"
                f"  원하는 값을 직접 넣을 것(`--set=\"{key}=<값>\"`).")
        changes[key] = None
    if not changes:
        return {}
    path = cfg.path("config.json")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        out = kn.patch_text(raw, changes)
        how = ""
    except Exception as e:                  # 모양이 특이하면 통째로 쓴다
        out = _json.dumps(kn.apply(cfg.data, changes),
                          ensure_ascii=False, indent=2) + "\n"
        how = f"  [알림] 부분 수정 실패({e}) — 통째로 다시 썼다(서식이 바뀐다)"
    if backup:
        shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    if how:
        log(how)
    for key, v in changes.items():
        log(f"  {key} → {'기본값으로 되돌림' if v is None else v}")
    log(f"  {os.path.basename(path)} 갱신 (이전 판은 config.json.bak)")
    log("  → 지면에 반영하려면 `build` (또는 `watch` 를 띄워 두면 바로 보인다)")
    return changes


def build_dir(cfg):
    """이 책의 조판 결과 폴더 — 계열에게 묻는다(중등부는 3계층 밖에 쓴다)."""
    return _series(cfg).build_dir(cfg)


def render(cfg, log=print, **opts):
    """조판 직전까지 — build/ 를 채우고 HTML 경로를 준다(미리보기용).

    PDF 를 만들지 않으므로 빠르다. `watch` 가 파일이 바뀔 때마다 이걸 부른다.
    """
    return _series(cfg).render_only(cfg, log, **opts)


def _print_section(cfg):
    """`print` 절 = **계열 기본값** 위에 책 config 를 덮은 것.

    ⚠ 책마다 적게 두면 한 곳만 빠져도 그 책은 RGB 로 나간다(포켓북 22곳).
      계열이 `print_defaults(cfg)` 를 주면 그걸 바탕으로 깐다. 색 표
      (`gray_map`·`cmyk_map`)는 통째로 갈지 않고 **칸 단위로** 덮는다.

    **규약(2026-09-11): 별도 말이 없으면 모든 조판은 인쇄 납품용.** 그래서
    `print` 절이 없어도 항상 켜져 있다(계열 기본값 → 없으면 `Series.print_defaults`
    의 바닥값). 끄는 길은 두 가지뿐 — `"print": false` 또는 `{"off": true}`
    (사용자가 "이건 인쇄용 아니야"라고 한 책).
    """
    raw = cfg.get("print")
    if raw is False:
        return {}
    own = dict(raw or {}) if isinstance(raw, dict) else {}
    if own.get("off"):
        return {}
    base = {}
    f = getattr(_series(cfg), "print_defaults", None)
    if f:
        try:
            base = dict(f(cfg) or {})
        except Exception:           # 기본값이 깨져도 책 설정은 살린다
            base = {}
    if not base:
        from core.render_vivlio import prepress
        base = prepress.default_print()
    out = dict(base)
    for k, v in own.items():
        if k in ("gray_map", "cmyk_map") and isinstance(v, dict):
            out[k] = dict(base.get(k) or {}, **v)
        else:
            out[k] = v
    return out


def print_pdf(cfg, log=print, **opts):
    """RGB 조판본 → CMYK 인쇄 원고. 계열과 무관해 백엔드가 직접 한다.

    config 의 `print` 절:
      suffix   원본 PDF 접미사(어느 산출을 변환할지) / out  결과 접미사
      profile  ICC 이름 또는 절대경로 / gray_map  화면색 → K 비율 표
      cmyk_map 화면색 → 고정 CMYK(이전 판과 색을 정확히 맞춰야 하는 것만)
    """
    from core.render_vivlio import prepress
    pc = _print_section(cfg)
    src = cfg.out_pdf(pc.get("suffix", cfg.section("verify").get("suffix", "")))
    if not os.path.exists(src):
        raise FileNotFoundError(f"조판본 없음: {src} — 먼저 build")
    dst = cfg.out_pdf(pc.get("out", "_인쇄"))
    res = prepress.make(src, dst, bleed=cfg.page["bleed"],
                        profile=pc.get("profile"),
                        gray_map=pc.get("gray_map"),
                        cmyk_map=pc.get("cmyk_map"), log=log)
    if pc.get("trim_bleed"):
        # 학원 출력 — 재단하지 않으므로 도련이 필요 없다. 조판은 검증된 판면
        # (도련 포함 판)으로 그대로 하고 **인쇄본만 재단선에서 자른다** —
        # 테마의 여백·띠·괘선이 전부 도련 포함 판 기준이라 판을 바꾸면 흐른다.
        n = _crop_to_trim(dst)
        log(f"  [학원 출력] 도련을 잘라 재단 크기로 — {n}면")
    a = prepress.audit(dst)
    # 판형은 **크기**로 적는다 — MediaBox 모서리 값은 원점이 0 이 아니면(잘라 낸
    # 학원 출력판) 213×300 처럼 틀린 크기로 읽힌다.
    mb = a["media_mm"]
    log(f"  판형 {round(mb[2] - mb[0], 1)}×{round(mb[3] - mb[1], 1)}mm · "
        f"재단 {a['trim_mm']} · 색연산자 {a['ops']}")
    if a["rgb_left"]:
        log(f"  [경고] DeviceRGB 연산자가 {a['rgb_left']}개 남았다")
    res["audit"] = a
    return res


def _crop_to_trim(path):
    """MediaBox·CropBox·BleedBox 를 TrimBox 로 — 도련 없는 재단 크기 PDF.

    ⚠ PyMuPDF 의 `set_mediabox`/`set_trimbox` 는 좌표를 서로 다른 기준으로
      옮겨 받아 "not in MediaBox" 로 멈춘다. 면 사전의 **원래 PDF 좌표**를
      그대로 읽어 네 상자에 똑같이 적는다(내용 스트림은 손대지 않는다).
    """
    import fitz
    doc = fitz.open(path)
    for pg in doc:
        kind, val = doc.xref_get_key(pg.xref, "TrimBox")
        if kind != "array":
            raise ValueError(f"{pg.number + 1}면에 TrimBox 가 없다 — 자를 기준이 없다")
        for key in ("MediaBox", "CropBox", "BleedBox", "TrimBox"):
            doc.xref_set_key(pg.xref, key, val)
    n = doc.page_count
    tmp = path + ".tmp"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, path)
    return n


def verify(cfg, log=print, pdf=None, **opts):
    """공용 게이트 + 계열 게이트. Report 를 돌려준다."""
    s = _series(cfg)
    vcfg = cfg.section("verify") or {}
    pdf = pdf or cfg.out_pdf(vcfg.get("suffix", ""))
    report = gate.Report(f"{cfg.book.get('title', cfg.series)} — {os.path.basename(pdf)}")
    if not os.path.exists(pdf):
        return report.fail(f"PDF 없음: {pdf}")

    from core.render_vivlio import probe
    texts = probe.page_texts(pdf)
    report.note(f"쪽수 {len(texts)}")

    # 뒤에 붙인 원본 아트워크(간지·MEMO)는 우리가 조판한 면이 아니다 →
    # 판면·도련 검사에서 뺀다. `skip_last` 는 "마지막 N 면".
    skip = list(vcfg.get("skip_pages") or ())
    n_last = vcfg.get("skip_last") or 0
    skip += [len(texts) - k for k in range(n_last)]
    skip = tuple(sorted(set(p for p in skip if 1 <= p <= len(texts))))
    if vcfg.get("frame"):
        gate.check_overflow(pdf, vcfg["frame"], report, skip_pages=skip)
    if cfg.page["bleed"]:
        gate.check_trimbox(pdf, report, bleed=cfg.page["bleed"])
        gate.check_bleed_coverage(pdf, report, bleed=cfg.page["bleed"],
                                  skip_pages=skip)
    gate.check_blanks(texts, report, ignore_chars=vcfg.get("blank_ignore", ""))
    _check_print_fresh(cfg, pdf, report)
    s.verify(cfg, log, report)

    # 디자인 게이트 — 기본은 경고(납품 중인 책의 지면을 바꾸지 않기 위해).
    # `verify.design.off: true` 로 아예 끌 수 있고, `strict: true` 면 결함이 된다.
    if not (vcfg.get("design") or {}).get("off"):
        from core.render_vivlio import design_gate
        try:
            design_gate.run(cfg, pdf, report, log=log, skip_pages=skip)
        except Exception as e:      # 디자인 게이트가 본 게이트를 막지 않게
            report.note(f"[디자인] 검사 실패(건너뜀): {e}")
    return report


def _check_print_fresh(cfg, src, report):
    """인쇄 원고가 조판본보다 오래됐는가 — 조용히 뒤처지면 옛 색으로 납품된다."""
    pc = _print_section(cfg)
    if not pc:
        return
    out = cfg.out_pdf(pc.get("out", "_인쇄"))
    if not os.path.exists(out):
        return report.fail(f"인쇄 원고 없음: {os.path.basename(out)} — `print` 를 돌릴 것")
    if os.path.getmtime(out) < os.path.getmtime(src) - 1:
        return report.fail(
            f"인쇄 원고가 조판본보다 오래됐다 "
            f"({os.path.basename(out)}) — `print` 를 다시 돌릴 것")
    report.note(f"인쇄 원고 최신 ({os.path.basename(out)})")


# ── 책 목록 ─────────────────────────────────────────────────────────────
def discover(root=None, max_depth=6):
    """교재 트리에서 `config.json`(series 키가 있는 것)을 찾는다.

    책 목록을 따로 관리하는 표를 두지 않는다 — 표와 실제 폴더가 어긋나는 순간
    쓸모가 없어지기 때문이다. 진실은 교재 폴더에 있는 config.json 이다.
    """
    root = root or os.path.join(bookconfig._studio_root(), "조판", "교재")
    out = []
    if not os.path.isdir(root):
        return out
    base = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - base >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(("_", ".")) and d != "build"]
        if "config.json" not in filenames:
            continue
        try:
            cfg = bookconfig.load(os.path.join(dirpath, "config.json"))
        except Exception:
            continue
        out.append(cfg)
    return sorted(out, key=lambda c: (c.series, c.root))


def books_json(root=None):
    """책 목록을 기계가 읽을 형태로. 웹 작업대가 subprocess 로 부른다.

    `key` 는 **스튜디오 루트 기준 상대경로**다 — 웹이 절대경로를 주고받으면
    경로 넘나들기를 막을 방법이 없다. 키로 받아 서버가 다시 붙인다.
    """
    out = []
    for c in discover(root):
        rel = c.root.replace(bookconfig._studio_root() + os.sep, "")
        out.append({"key": rel, "series": c.series,
                    "title": c.book.get("title") or c.series,
                    "id": c.book.get("id") or "",
                    "school": c.book.get("school") or "",
                    "period": c.book.get("period") or "",
                    "page": {"width": c.page["width"], "height": c.page["height"],
                             "bleed": c.page["bleed"]}})
    return out


def print_books(log=print, root=None, as_json=False):
    if as_json:
        import json as _json
        log(_json.dumps(books_json(root), ensure_ascii=False, indent=1))
        return []
    books = discover(root)
    log(f"■ Vivliostyle 책 {len(books)}권 "
        f"(계열: {', '.join(series_registry.names())})")
    for c in books:
        rel = c.root.replace(bookconfig._studio_root() + os.sep, "")
        log(f"  [{c.series}] {c.book.get('title', '?')} — {rel}")
    return books


# ── CLI ─────────────────────────────────────────────────────────────────
def _parse_opts(argv):
    opts = {}
    for a in argv:
        if not a.startswith("--"):
            continue
        k, _, v = a[2:].partition("=")
        opts[k.replace("-", "_")] = v if v else True
    return opts


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    if argv[0] in ("--list", "-l", "list"):
        print_books(as_json="--json" in argv)
        return 0
    book = argv[0]
    steps = [a for a in argv[1:] if not a.startswith("--")] or ["build"]
    opts = _parse_opts(argv[1:])
    try:
        cfg = load(book)
    except FileNotFoundError as e:
        # 역추적은 여기서 아무것도 알려 주지 않는다 — 쓸 말만 남긴다
        print(f"[오류] {e}")
        return 2
    log = print
    log(f"■ {cfg.book.get('title', '')} · 계열 {cfg.series} · {cfg.root}")

    if "all" in steps:
        # ⚠ 인쇄본을 빼면 조판본만 갱신돼 **인쇄 원고가 조용히 뒤처진다**
        #    (실제로 겪음). 규약상 인쇄본은 **항상** 만든다 — `print: false` 인
        #    책(화면용이라고 따로 말한 것)만 빠진다.
        steps = ["data", "build"] + (["print"] if _print_section(cfg) else []) + ["verify"]
    if "watch" in steps:
        # 미리보기는 다른 단계와 섞지 않는다 — 끝나지 않는 명령이다.
        from core.render_vivlio import watch as watch_mod
        port = int(opts.pop("port", 13000) or 13000)
        host = str(opts.pop("host", "127.0.0.1") or "127.0.0.1")
        if opts.pop("data", False):
            gen_data(cfg, log)
        return watch_mod.run(cfg, book, log, port=port, host=host, **opts)

    rc = 0
    for st in steps:
        if st == "data":
            gen_data(cfg, log)
        elif st == "theme":
            gen_theme(cfg, log)
        elif st == "render":
            html = render(cfg, log, **opts)
            # watch 가 자식 프로세스의 출력에서 이 줄을 읽는다
            log(f"RENDER_HTML={html}")
        elif st == "variants":
            from core.render_vivlio import variants as var_mod
            kkey = opts.get("knob")
            vals = [x.strip() for x in str(opts.get("values", "")).split(",")
                    if x.strip()]
            if not kkey or len(vals) < 2:
                log("[오류] --knob=<손잡이> --values=\"값1,값2,…\" 가 필요하다")
                rc = 2
            else:
                var_mod.run(cfg, _series(cfg), kkey, vals, log,
                            pages=int(opts.get("pages", 4)))
        elif st == "knobs":
            # ⚠ 그냥 콤마로 자르면 **값 안의 콤마가 잘린다.** 서체 손잡이 값은
            #   `"Gmarket Sans", sans-serif` 라 `sans-serif` 가 따로 떨어져
            #   「모르는 손잡이: sans-serif」로 죽었다(실측). 다음 `키=` 가
            #   시작되는 콤마에서만 자른다.
            sets = [x for x in re.split(r",(?=\s*[a-z_]+\.[a-z0-9_]+\s*=)",
                                        str(opts.get("set", ""))) if x.strip()]
            resets = [x for x in str(opts.get("reset", "")).split(",") if x.strip()]
            if sets or resets:
                set_knobs(cfg, log, sets, resets)
                cfg = load(book)                    # 바꾼 값으로 다시 읽어 보여 준다
            show_knobs(cfg, log, as_json=bool(opts.get("json")), book=book)
        elif st == "select":
            set_select(cfg, log,
                       exclude=opts.get("exclude"), include=opts.get("include"),
                       limits=opts.get("limits"), order=opts.get("order"),
                       clear=bool(opts.get("clear")))
        elif st == "css":
            set_css(cfg, log, text=(opts.get("text") if isinstance(opts.get("text"), str) else None),
                    file=opts.get("file"), clear=bool(opts.get("clear")))
        elif st == "sections":
            show_sections(cfg, log, as_json=bool(opts.get("json")), book=book)
        elif st == "build":
            build(cfg, log, **opts)
        elif st == "print":
            print_pdf(cfg, log, **opts)
        elif st == "verify":
            if not verify(cfg, log, **opts).print(log):
                rc = 1
        else:
            log(f"[오류] 알 수 없는 단계: {st}")
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
