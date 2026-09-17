# -*- coding: utf-8 -*-
"""조립 — 부품을 담아 구성을 만들고, 구성으로 책을 만든다.

    부품 라이브러리   catalog/<계열>/parts/parts.json + PNG (`book … make --what=thumbs` 가 굽는다)
    구성 캔버스       부품 순서 + 지문 수 + 가로/세로 → 미리보기(견본 원고로, config 안 건드림)
                     → 이름 붙여 저장: catalog/<계열>/compositions.json
    책               구성을 기존 책에 적용(select) 또는 새 책(디자인·이름·원고 → data → 견본)에 적용

지금 부품은 **스텝 단위**(원고 파일 단위와 같다). 면 안 조합은 계열 렌더러에서 부품을
빼낸 뒤에 온다 — 그때도 이 화면과 저장 형식은 그대로다(부품 목록만 잘게 늘어난다).

화면은 얇다 — 모든 일은 `core.render_vivlio.book` CLI 가 한다. 클로드도 터미널에서 같은 일을
할 수 있다: `book <책> make --what=compose --steps=step1_c1,step3 --limits=step1_c1=2 --cycle=on`.
"""
import json
import os
import re
import time

from flask import Blueprint, abort, jsonify, render_template, request, send_from_directory

from routes.book_studio import _bid, _book_dir, _books, _run

bp = Blueprint("make", __name__)

SERIES = "workbook"
_RE_KEY = re.compile(r"^[a-z0-9_]{1,32}$")
_RE_NAME = re.compile(r"^[^/\\\x00-\x1f]{1,40}$")      # 구성 이름 — 경로 글자만 막는다
_RE_PNG = re.compile(r"^[a-z0-9_]{1,40}\.png$")


def _cat(*p):
    from routes.catalog import CATALOG
    return os.path.join(CATALOG, SERIES, *p)


def _cfg_of(d):
    try:
        with open(os.path.join(d, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _wb_books():
    return [b for b in _books() if b.get("series") == SERIES]


def _parts():
    """워크북의 조판되는 부품(스텝 단위) — `make --what=thumbs` 가 만든 목록."""
    try:
        with open(_cat("parts", "parts.json"), encoding="utf-8") as f:
            return json.load(f).get("parts") or []
    except (OSError, ValueError):
        return []


_RE_CODES = re.compile(r"\b(B1[01]|B[1-9])\b")


def _library():
    """모든 틀의 블록 — 프로젝트 > 틀의 '지면 형태'(기준 PDF 를 구성 단위로 묶은 것) 그대로.

    틀마다 [{id, series, design, label, kind(표지·간지/본문), codes(B1~B11), thumb, pages, key?}].
    워크북은 본문 블록 대신 **조판되는 부품**(스텝 키, `key`)을 쓰고, 표지·간지만 기준 PDF 에서 가져온다.
    다른 틀의 블록은 아직 기준 PDF 그림(참고)이다 — 담을 수는 있고, 조판은 그 틀이 select 를 받게 되면 붙는다.
    """
    from routes.catalog import design_layouts, templates
    out = []
    wb_parts = _parts()
    for t in templates():
        ds = t.get("designs") or []
        if not ds:
            continue
        d = next((x for x in ds if not x.get("draft")), ds[0])
        try:
            L = design_layouts(t["series"], d["id"])
        except Exception:
            L = {"layouts": []}
        blocks = []
        for lay in L.get("layouts") or []:
            label = lay["label"]
            kind = "간지" if lay.get("kind") == "간지" else "본문"
            if kind == "간지" and label.startswith("간지 · 표지") or label.startswith("표지"):
                kind = "표지·간지"
            if t["series"] == SERIES and kind == "본문":
                continue                      # 워크북 본문은 아래 조판 부품으로
            blocks.append({
                "id": f"{t['series']}:{d['id']}:{lay['n']}", "series": t["series"], "design": d["id"],
                "label": label, "kind": kind, "codes": _RE_CODES.findall(label),
                "thumb": f"/catalog/page/{t['series']}/{d['id']}/{lay['n']}.png?dpi=40",
                "page": lay["n"], "pages": lay.get("count", 1), "renderable": False,
            })
        if t["series"] == SERIES:
            for p in wb_parts:
                blocks.append({
                    "id": f"{SERIES}:{p['key']}", "series": SERIES, "design": d["id"], "key": p["key"],
                    "label": f"{p.get('logo') or ''} {p['name']}".strip(), "desc": p.get("desc", ""),
                    "kind": "본문", "codes": _WB_CODES.get(p["key"], []),
                    "thumb": f"/make/parts/{p['thumb']}", "step": p.get("step"), "renderable": True,
                })
        out.append({"series": t["series"], "name": t["name"], "dir": t.get("dir_name") or "",
                    "design": d["id"], "design_name": d.get("name", d["id"]), "blocks": blocks,
                    "renderable": t["series"] == SERIES})
    out.sort(key=lambda t: not t["renderable"])          # 조판되는 틀을 맨 위에
    for t in out:
        for b in t["blocks"]:
            b["item"] = _classify(b)
            b["tpl"] = t["name"]
    return out


def _by_item(library):
    """항목 → 옷(블록) 목록. 조판되는 것이 먼저."""
    by = {i: [] for i in ITEMS}
    for t in library:
        for b in t["blocks"]:
            by.setdefault(b["item"], []).append(b)
    for k in by:
        by[k].sort(key=lambda b: (not b.get("renderable"), b["tpl"]))
    return by


# ── 책과 무관한 공통 항목 — 라이브러리의 「블록별 보기」 ─────────────
# 블록 지도(B1~B11)를 바탕으로 하되 사람이 고르기 쉬운 갈래로 다시 나눴다. 항목 하나에
# 틀마다 다른 '옷'(variant = 그 틀의 지면 형태)이 여럿 달린다. 구성엔 항목 + 옷을 담는다.
TAXONOMY = [
    ("구조", "책 뼈대 — 원고 없음", [
        ("cover", "표지", "앞표지·시작면"),
        ("divider", "구간 간지", "STEP·PART·WEEK·DAY 앞 간지"),
        ("answer_div", "정답지 간지", "정답·해설 앞 간지"),
        ("memo", "MEMO·채움면", "메모 면·빈 면"),
        ("credits", "크레딧·판권", "만든 사람·판권"),
    ]),
    ("지문", "지문이 주인공인 면", [
        ("passage_raw", "원문 지문", "해석·표시 없는 지문 전문"),
        ("passage_analysis", "지문 분석·직독직해", "문장 끊어 해석·문법 표시·스크립트"),
        ("passage_variant", "변형 지문", "어휘 선택·어법 선택·문장 배열·삽입·본문 O/X"),
    ]),
    ("정리", "요약과 개념", [
        ("summary", "요약·정리", "주제·제목·FLOW NOTE·5분 점검"),
        ("concept", "개념·풀이 전략", "문법 개념·유형 전략·배경지식"),
    ]),
    ("어휘", "낱말", [
        ("vocab_list", "어휘 목록", "표제어·뜻·예문"),
        ("vocab_related", "파생·연관 어휘", "지문 부속 어휘·유반의어"),
        ("vocab_drill", "어휘 빈칸·암기 TEST", "어휘 목록의 빈칸본"),
    ]),
    ("문항", "발문이 있는 문제", [
        ("q_set", "문항 세트", "지문 + 객관식 문항"),
        ("q_exam", "실전·모의고사 세트", "회차·시험지 꼴"),
        ("q_short", "서답형·단답", "쓰는 문항·T/F"),
    ]),
    ("드릴", "문장 단위 과제 목록", [
        ("drill_blank", "빈칸 채우기", "빈칸 어휘·빈칸 어법·해석 빈칸"),
        ("drill_ox", "어법 O/X", "문장마다 O/X 표시하고 고치기"),
        ("drill_write", "영작·배열", "청크 영작·단어 배열·대화 순서"),
    ]),
    ("정답", "답과 풀이", [
        ("ans_quick", "빠른 정답", "번호·정답 격자"),
        ("ans_full", "정답·해설", "문항별 풀이"),
    ]),
    ("기타", "아직 못 가른 것", [
        ("misc", "기타", "라벨로 못 가른 면 — 틀별 보기에서 확인"),
    ]),
]
ITEMS = {i[0]: {"id": i[0], "name": i[1], "desc": i[2], "cat": c[0]} for c in TAXONOMY for i in c[2]}

# 워크북 조판 부품 → 항목
_WB_ITEM = {
    "step1_a1": "passage_variant", "step1_a1_2": "passage_variant", "step1_a2": "passage_variant",
    "step1_b1": "summary", "step1_b2": "q_set", "step1_c1": "passage_variant", "step1_c2": "drill_blank",
    "step2_a1": "passage_variant", "step2_b1": "drill_ox", "step2_c1": "drill_blank", "step2_c2": "drill_write",
    "step3": "q_exam", "step3_short": "q_exam",
}

# 기준 PDF 라벨 → 항목. 위에서부터 첫 일치. 구체적인 것이 먼저.
_LABEL_ITEM = [
    (r"정답지|정답.*간지|간지.*정답", "answer_div"),
    (r"^간지 \(", "divider"),
    (r"^표지|간지 · 표지", "cover"),
    (r"MEMO|메모", "memo"),
    (r"크레딧|판권", "credits"),
    (r"빠른\s*정답", "ans_quick"),
    (r"정답\s*및\s*해설|정답 및 풀이|해설", "ans_full"),
    (r"^정답", "ans_quick"),
    (r"서답형|T\s*/\s*F", "q_short"),
    (r"STEP\s*\d\s*(확인|응용)", "q_set"),                   # 중등 'PART 1 어휘 · STEP1 확인' 은 문항
    (r"원문", "passage_raw"),                              # 블랙북 '원문 지문 · 연관어휘' — 지문이 주인공
    (r"분석|직독직해|스크립트", "passage_analysis"),          # 포켓북 '지문 분석 (B2 + B5)' 도 여기
    (r"중요\s*어휘", "drill_blank"),                        # 파이널 중요어휘 = 빈칸 드릴(블록 지도 B8)
    (r"VOCA\s*vs|개념|전략|배경지식", "concept"),
    (r"지문 어휘|암기\s*TEST|빈칸 드릴", None),               # 아래 두 줄에서 가른다
    (r"암기\s*TEST|빈칸 드릴", "vocab_drill"),
    (r"파생|연관어휘|동반의어", "vocab_related"),
    (r"어근|접두사|표제어|어휘|VOCA", "vocab_list"),
    (r"실전문제 세트|모의고사 세트|시험지|회차", "q_exam"),
    (r"연습문제|Exercise|EXERCISE|연습|확인|응용|문항|예제", "q_set"),
    (r"실전|모의", "q_exam"),
    (r"요약|FLOW|점검|정리", "summary"),
    (r"어법\s*O/?X", "drill_ox"),
    (r"영작|단어 배열|대화 순서", "drill_write"),
    (r"빈칸", "drill_blank"),
    (r"문장\s*배열|문장\s*삽입|순서 배열|어법 고르기|어휘 선택|어법 선택|본문\s*O", "passage_variant"),
    (r"지문", "passage_raw"),
]


def _classify(block):
    if block.get("key"):
        return _WB_ITEM.get(block["key"], "misc")
    label = block.get("label") or ""
    for pat, item in _LABEL_ITEM:
        if item and re.search(pat, label, re.I):
            return item
    if block.get("kind") != "본문":
        return "divider"
    return "misc"


# 워크북 부품 → 블록 지도 코드 (docs/참고자료/교재_블록_지도)
_WB_CODES = {
    "step1_a1": ["B7"], "step1_a1_2": ["B7"], "step1_a2": ["B7"], "step1_b1": ["B3", "B6"],
    "step1_b2": ["B6"], "step1_c1": ["B7"], "step1_c2": ["B8"], "step2_a1": ["B7", "B6"],
    "step2_b1": ["B8"], "step2_c1": ["B8"], "step2_c2": ["B8"], "step3": ["B6"], "step3_short": ["B6"],
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


# ── 화면 ────────────────────────────────────────────────────────

@bp.route("/make")
def page():
    from core.render_vivlio.config import _studio_root
    from routes.catalog import template_info
    bs = _wb_books()
    for b in bs:
        cat = _cfg_of(os.path.join(_studio_root(), b["key"])).get("_카탈로그") or {}
        b["design"] = cat.get("design_name") or cat.get("design") or ""
    tpl = template_info(SERIES) or {}
    designs = [{"id": d["id"], "name": d.get("name", d["id"]), "draft": bool(d.get("draft")),
                "preview": (d.get("previews") or [None])[0]} for d in tpl.get("designs") or []]
    lib = _library()
    return render_template("make.html", library=lib, by_item=_by_item(lib), taxonomy=TAXONOMY, items=ITEMS,
                           books=bs, designs=designs,
                           fields=tpl.get("fields") or [], slot_hint=tpl.get("slot_hint", ""),
                           root=tpl.get("root", ""), compositions=_read_json(_cat("compositions.json")),
                           active_nav="조립")


@bp.route("/make/parts/<name>")
def part_png(name):
    if not _RE_PNG.match(name):
        abort(404)
    return send_from_directory(_cat("parts"), name)


# ── 미리보기 — config 안 건드림 ─────────────────────────────────

def _comp_args(p):
    """화면의 구성 → CLI 옵션. `items`(블록 목록, key 있는 것만 조판) 또는 `steps`. limits 는 {키: 지문 수}."""
    if p.get("items"):
        steps = [str(it.get("key")) for it in p["items"]
                 if isinstance(it, dict) and it.get("key") and _RE_KEY.match(str(it["key"]))]
    else:
        steps = [str(k) for k in (p.get("steps") or []) if _RE_KEY.match(str(k))]
    lim = {str(k): int(v) for k, v in (p.get("limits") or {}).items()
           if _RE_KEY.match(str(k)) and str(v).isdigit() and int(v) > 0}
    return steps, lim, bool(p.get("cycle"))


def _clean_items(p):
    """저장용 블록 목록 — 화면이 준 것 중 아는 칸만."""
    out = []
    for it in p.get("items") or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        o = {k: it[k] for k in ("id", "series", "design", "key", "label", "kind", "thumb", "page", "item") if k in it}
        if it.get("n") and str(it["n"]).isdigit():
            o["n"] = int(it["n"])
        out.append(o)
    return out[:200]


@bp.route("/api/make/preview", methods=["POST"])
def api_preview():
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "견본 책을 모른다"}), 404
    steps, lim, cycle = _comp_args(p)
    if not steps:
        return jsonify({"error": "조판되는 부품이 없다 (지금은 워크북 부품만 조판된다)"}), 400
    args = [d, "make", "--what=compose", "--steps=" + ",".join(steps),
            "--n=%d" % max(0, min(int(p.get("n") or 2), 99))]
    if lim:
        args.append("--limits=" + ",".join("%s=%d" % kv for kv in lim.items()))
    if cycle:
        args.append("--cycle=on")
    r = _run(args, timeout=180)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "doc": "/book-studio/doc/%s/make_compose.html" % meta["bid"],
                    "log": r.stdout[-1200:]})


# ── 구성 저장소 ────────────────────────────────────────────────

@bp.route("/api/make/compositions")
def api_compositions():
    return jsonify({"series": SERIES, "compositions": _read_json(_cat("compositions.json"))})


@bp.route("/api/make/compositions", methods=["POST"])
def api_composition_save():
    p = request.get_json(silent=True) or {}
    name = str(p.get("name") or "").strip()
    if not _RE_NAME.match(name):
        return jsonify({"error": "이름은 1~40자, 슬래시 없이"}), 400
    steps, lim, cycle = _comp_args(p)
    items = _clean_items(p)
    if not items and not steps:
        return jsonify({"error": "부품이 하나도 없다"}), 400
    path = _cat("compositions.json")
    comps = _read_json(path)
    rules = p.get("rules") if isinstance(p.get("rules"), dict) else {}
    rules = {k: str(v)[:40] for k, v in rules.items() if k in ("repeat", "answers", "mode")}
    comps[name] = {"items": items, "steps": steps, "limits": lim, "cycle": cycle, "rules": rules,
                   "note": str(p.get("note") or "")[:200], "made": time.strftime("%Y-%m-%d %H:%M")}
    _write_json(path, comps)
    return jsonify({"ok": True, "compositions": comps})


@bp.route("/api/make/compositions", methods=["DELETE"])
def api_composition_delete():
    p = request.get_json(silent=True) or {}
    name = str(p.get("name") or "")
    path = _cat("compositions.json")
    comps = _read_json(path)
    if name not in comps:
        return jsonify({"error": "없는 구성"}), 404
    comps.pop(name)
    _write_json(path, comps)
    return jsonify({"ok": True, "compositions": comps})


# ── 구성을 책에 적용 (config 의 select 를 쓴다) ──────────────────

@bp.route("/api/make/apply", methods=["POST"])
def api_apply():
    """구성 → 그 책의 select(넣을 스텝·순서·지문 수)·세로 → data → 견본."""
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    steps, lim, cycle = _comp_args(p)
    if not steps:
        return jsonify({"error": "부품이 하나도 없다"}), 400
    from core.render_vivlio.series.workbook.data import STEP_META
    known = [k for k, m in STEP_META.items() if not m.get("attach_to")]
    exclude = [k for k in known if k not in steps]
    r = _run([d, "select", "--clear"], timeout=60)       # 지난 구성을 깨끗이 지우고 새로 쓴다
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    args = [d, "select", "--order=" + ",".join(steps), "--cycle=" + ("on" if cycle else "off")]
    if exclude:
        args.append("--exclude=" + ",".join(exclude))
    if lim:
        args.append("--limits=" + ",".join("%s=%d" % kv for kv in lim.items()))
    args += ["data", "render", "--sample"]
    r = _run(args, timeout=600)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "key": meta["key"], "bid": meta["bid"],
                    "doc": "/book-studio/doc/%s/index.html" % meta["bid"], "log": r.stdout[-1500:]})


@bp.route("/api/make/book-info")
def api_book_info():
    """책 하나의 현황 — 구성(select)·PDF 목록·지문 수."""
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = _cfg_of(d)
    stats = {}
    try:
        with open(os.path.join(d, "data.json"), encoding="utf-8") as f:
            stats = json.load(f).get("stats") or {}
    except (OSError, ValueError):
        pass
    pdfs = sorted((n for n in os.listdir(d) if n.lower().endswith(".pdf") and "_견본" not in n),
                  key=lambda n: os.path.getmtime(os.path.join(d, n)), reverse=True)
    return jsonify({"key": meta["key"], "bid": meta["bid"], "select": cfg.get("select") or {},
                    "cycle": (cfg.get("options") or {}).get("order") == "cycle",
                    "book": cfg.get("book") or {}, "stats": stats, "pdfs": pdfs[:4],
                    "has_build": os.path.exists(os.path.join(d, "build", "index.html"))})


# ── 해부도 (부품·틀·스텝) — 역할별 조각 보기 ─────────────────────

@bp.route("/api/make/level", methods=["POST"])
def api_level():
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    what = p.get("what") or "parts"
    if what not in ("parts", "frames", "step"):
        return jsonify({"error": "모르는 칸: " + str(what)}), 400
    args = [d, "make", "--what=" + what]
    if what == "step":
        key = str(p.get("key") or "")
        if not _RE_KEY.match(key):
            return jsonify({"error": "스텝 키가 이상하다"}), 400
        args += ["--key=" + key, "--n=%d" % max(1, min(int(p.get("n") or 2), 20))]
    r = _run(args, timeout=180)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    m = re.search(r"^MAKE_HTML=(.+)$", r.stdout, re.M)
    if not m:
        return jsonify({"error": "산출 경로가 없다", "log": r.stdout[-800:]}), 500
    name = m.group(1).strip().rsplit("/", 1)[-1]
    return jsonify({"ok": True, "doc": "/book-studio/doc/%s/%s" % (meta["bid"], name),
                    "log": r.stdout[-1200:]})
