# -*- coding: utf-8 -*-
"""지문 코퍼스 → 조판용 data.

입력은 `tools/pocket_harvest/idml.py` 가 내는 모양(완성본 수확)이거나 코퍼스
JSON 이다. 둘의 필드 이름을 같게 맞춰 뒀으므로 여기서는 **지면이 바로 쓸 수 있는
꼴**로만 눕힌다(문단 → 런 목록, 링크 → 파일 경로).
"""
import os
import re
import shutil
import unicodedata


def _flatten(paras):
    """문단 목록 → 런 흐름. 이미 런 목록이거나 글자열이면 그대로 받아 준다.

    코퍼스와 수확기의 모양이 조금씩 달라서(문단 목록 / 런 목록 / 글자열) 여기서
    한 번에 눕힌다. 안 그러면 출처가 바뀔 때마다 조판이 죽는다.
    """
    if isinstance(paras, str):
        return [{"t": paras}]
    if paras and isinstance(paras[0], dict) and "runs" not in paras[0]:
        return list(paras)
    return _flatten_paras(paras)


# 분석본에만 있고 포켓북에는 없는 것들 — 옮길 때 버린다.
#   `snum` = 문장 번호(① ② …). 분석본은 문장마다 번호를 달지만 포켓북 지문은
#   한 덩이로 이어지므로 번호가 남으면 본문에 숫자가 섞여 보인다.
_DROP_MARKS = {"snum"}


def _flatten_paras(paras):
    """문단 목록 → 런 하나짜리 흐름. 문단 사이에는 공백을 넣는다.

    포켓북 지문은 한 덩이로 흐른다(분석본처럼 문장마다 끊지 않는다).
    """
    out = []
    for i, p in enumerate(paras or ()):
        if i:
            out.append({"t": " ", "mark": None, "hl": None, "ruby": None})
        out.extend(r for r in p["runs"] if r.get("mark") not in _DROP_MARKS)
    return out


def _plain(paras):
    return " ".join(
        "".join(r["t"] for r in p["runs"]).strip() for p in (paras or ())).strip()


_MT = re.compile(r"(\d+)\s*\[([^\]]*)\]")


def format_memtest(runs, answer):
    """암기테스트 본문 → 번호·정답이 구분된 런.

    ⚠ 원본 스토리에는 **문자 스타일이 없다** — `138[famous]` 라는 글자만 있고
      위첨자·주황색은 로컬 서식이라 IDML 런에 안 남는 책이 있다(실측: 런 2개로
      1,761자). 그래서 서식을 읽지 말고 **표기에서 되만든다**.
      `숫자[낱말]` 은 이 교재의 고정 표기이고, 리뷰테스트 원고도 같은 표기를 쓴다.
    """
    text = "".join(r["t"] for r in runs)
    out, at = [], 0
    for m in _MT.finditer(text):
        if m.start() > at:
            out.append({"t": text[at:m.start()]})
        out.append({"t": m.group(1), "mark": "num"})
        out.append({"t": "["})
        word = m.group(2)
        if word:
            out.append({"t": word, "mark": None if answer else "blank",
                        "color": None} if not answer else
                       {"t": word, "mark": "red"})
        out.append({"t": "]"})
        at = m.end()
    if at < len(text):
        out.append({"t": text[at:]})
    return out or list(runs)


_URI = re.compile(r"^file://")


def _resolve_link(uri, search_dirs):
    """IDML LinkResourceURI → 실제 파일. 없으면 파일명으로 찾아본다."""
    if not uri:
        return None
    path = _URI.sub("", uri)
    path = unicodedata.normalize("NFC", path)
    if os.path.exists(path):
        return path
    base = os.path.basename(path)
    for d in search_dirs or ():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if unicodedata.normalize("NFC", f) == base:
                    return os.path.join(root, f)
    return None


_PNO6 = re.compile(r"^(\d{2})(\d{2})(\d{2})")


# ── 삽화 찾기 ───────────────────────────────────────────────────────
#
# 삽화 폴더는 갈래마다 이름 규칙이 다르다(실측):
#     고1/24년 9월/18.jpg · 41-42.jpg
#     고1/올림포스 영어독해 기본2/올독기2 1강 1.png · 올독기2 1강 분석.png
#     고1/올림포스 영어독해 기본1/11-1.jpg · 11-analysis.jpg
#     교과서/공통영어2 능률(민)/공영2 능률(민) SL과 02.png
#     ebs/수능특강 Light 영어독해연습(개정판)/1강 01.png · 4강 05~06.png
# 규칙을 하나로 못 묶으므로 **파일 이름의 뒤쪽 두 토막**을 열쇠로 삼는다 —
# 교재 이름(앞머리)은 폴더가 이미 말해 주고, 뒤쪽이 `1강 분석`·`SL과 02` 처럼
# 지문을 가리키기 때문이다.
_TOK = re.compile(r"\d+\s*[강과]|SL과|\d+[-~]\d+|\d+|분석|analysis|gateway",
                  re.I)


def _key_of(stem):
    t = [x.replace(" ", "").lower() for x in _TOK.findall(stem)]
    return tuple(t[-2:]) if len(t) >= 2 else tuple(t)


_IDX = []


def illust_index(bases):
    """삽화 폴더 → [(폴더이름, {열쇠: 경로})]. 한 번만 훑는다."""
    out = []
    for base in bases or ():
        base = os.path.expanduser(base)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            idx = {}
            for f in files:
                if f.startswith(".") or os.path.splitext(f)[1].lower() not in (
                        ".jpg", ".jpeg", ".png"):
                    continue
                stem = unicodedata.normalize("NFC", os.path.splitext(f)[0])
                idx.setdefault(_key_of(stem), os.path.join(root, f))
            if idx:
                out.append((unicodedata.normalize(
                    "NFC", os.path.relpath(root, base)), idx))
    return out


_RE_L_UNIT = re.compile(r"(\d{1,2})\s*강")
_RE_L_NO = re.compile(r"(\d{1,3})")


def illust_for(row, index):
    """지문 → 삽화 경로. 라벨·단원으로 찾는다(지문번호가 없어도 된다)."""
    lab = unicodedata.normalize("NFC", str(row.get("label") or ""))
    unit = unicodedata.normalize(
        "NFC", str(row.get("category") or row.get("unit") or ""))
    ch = unicodedata.normalize("NFC", str(row.get("chapter") or ""))
    keys, want = [], None
    m = _RE_L_UNIT.search(unit) or _RE_L_UNIT.search(lab)
    ym = re.search(r"(\d{2})\s*년\s*(\d{1,2})\s*월", ch or unit)
    if "모의고사" in unit or ym:
        want = "%s년 %d월" % (ym.group(1), int(ym.group(2))) if ym else None
        n = re.match(r"\s*(\d{1,3})(?:\s*[-~]\s*(\d{1,3}))?", lab)
        if n:
            a, b = n.group(1), n.group(2)
            keys = [("%s-%s" % (a, b),), ("%s~%s" % (a, b),)] if b else []
            keys += [(a,), (a.zfill(2),)]
    elif m:                                   # 부교재 — `1강 01` · `1강 분석`
        u = "%s강" % int(m.group(1))
        # ⚠ 꼬리는 **라벨에서** 떼야 한다. 단원(`올림포스 1강`)에서 잰 자리로
        #   라벨을 자르면 엉뚱한 데를 잘라 번호를 통째로 잃는다.
        ml = _RE_L_UNIT.search(lab)
        tail = lab[ml.end():] if ml else lab
        # 라벨이 `7강` 처럼 **강만** 있으면 그 단원의 분석 지문이다(분석본02 실측:
        # `7강, 1번, 2번, 3번, …` 에서 맨 앞이 분석이다).
        if "분석" in lab or "분석" in tail or not tail.strip():
            keys = [(u, "분석"), (u, "analysis")]
        else:
            n = _RE_L_NO.search(tail)
            if n:
                v = int(n.group(1))
                keys = [(u, str(v)), (u, "%02d" % v)]
        want = unit.split()[0] if unit.split() else None
    else:                                     # 교과서 — `본문2` → `SL과 02`
        # ⚠ 라벨의 **첫 숫자**를 쓰면 안 된다. `능률(민) SL2 본문1` 에서는
        #   교재 이름의 `2` 가 먼저 잡혀 본문1 과 본문2 가 같은 그림을 받는다.
        n = re.search(r"(?:본문|RC|Reading)\s*(\d{1,2})", lab) or \
            re.search(r"(\d{1,2})\s*$", lab)
        les = "sl과" if re.search(r"SL", unit, re.I) else None
        if les is None:
            k = re.search(r"(\d{1,2})\s*과", unit + " " + lab)
            les = "%d과" % int(k.group(1)) if k else None
        if les and n:
            v = int(n.group(1))
            keys = [(les, "%02d" % v), (les, str(v))]
        want = "교과서"
    for folder, idx in index:
        if want and want not in folder and want != "교과서":
            continue
        for k in keys:
            if k in idx:
                return idx[k]
    for folder, idx in index:                 # 폴더를 못 좁히면 전체에서
        for k in keys:
            if k in idx:
                return idx[k]
    return None


def find_illust(pno, grade, bases):
    """지문번호(YYMMNN) → 삽화 파일.

    분석본에는 삽화가 없다(포켓북에만 있는 요소다). 그래서 **번호로 찾아야** 한다.
    폴더는 `<학년>/<YY년 M월…>/<번호>.jpg` 인데 회차 폴더 이름에 `(수정완)`·`(X)`
    같은 꼬리가 붙어 있어 정확히 일치하지 않는다 — 앞부분만 본다.
    묶음 지문(`41-42`)은 파일명도 묶음으로 되어 있다.
    """
    m = _PNO6.match(str(pno or ""))
    if not m or not grade:
        return None
    yy, mm, nn = m.group(1), int(m.group(2)), m.group(3)
    want = "%s년 %d월" % (yy, mm)
    nums = [nn.lstrip("0") or "0", nn]
    for base in bases or ():
        gdir = os.path.join(base, grade)
        if not os.path.isdir(gdir):
            continue
        for d in sorted(os.listdir(gdir)):
            if not unicodedata.normalize("NFC", d).startswith(want):
                continue
            full = os.path.join(gdir, d)
            if not os.path.isdir(full):
                continue
            files = {unicodedata.normalize("NFC", f): f
                     for f in os.listdir(full)}
            for n in nums:
                for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG"):
                    if n + ext in files:
                        return os.path.join(full, files[n + ext])
            # 묶음 지문 — `41-42.jpg` 처럼 번호가 범위로 들어 있는 파일
            for nfc, real in files.items():
                stem = os.path.splitext(nfc)[0]
                if "-" in stem or "~" in stem:
                    parts = re.split(r"[-~]", stem)
                    if any(p.strip() == (nn.lstrip("0") or "0")
                           for p in parts):
                        return os.path.join(full, real)
    return None


def _copy_wo_credit(src, dst):
    """삽화의 **그린이 표기**를 잘라 낸다. 잘랐으면 True.

    삽화 아래에는 캡션(주제 한 줄)이 구워져 있고 그건 지면에 나와야 한다.
    그런데 어떤 삽화에는 그 **아래에 또 한 줄**, 그린이 표기가 들어 있다
    (`위메북 X 바카 (인스타 bakahodu)` — 강동1 28면). 그건 나오면 안 된다.

    둘은 생김새가 다르다(실측):

        캡션      가운데 정렬(잉크 중심 x≈0.48) · 진함(밝기 98)
        그린이    오른쪽 정렬(x≈0.80)          · 연함(밝기 170) · 맨 아래(0.96↑)

    그래서 **맨 아래 잉크 덩이가 오른쪽으로 몰리고 연하면** 그 위에서 자른다.
    가운데 있거나 진하면 캡션이므로 손대지 않는다 — 캡션을 자르는 쪽이 훨씬 나쁘다.
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return False
    try:
        im = Image.open(src)
    except Exception:
        return False
    a = np.asarray(im.convert("L").resize((400, 400))).astype(float)
    mask = a < 215
    rows = [i for i in range(300, 400) if mask[i].sum() > 3]
    if not rows:
        return False
    groups, cur = [], [rows[0]]
    for i in rows[1:]:
        if i - cur[-1] <= 2:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    if len(groups) < 2:
        return False
    g = groups[-1]
    if g[0] < 380:                       # 맨 아래가 아니면 캡션이다
        return False
    sub = mask[g[0]:g[-1] + 1]
    if not sub.any():
        return False
    xc = np.where(sub)[1].mean() / 400.0
    dark = a[g[0]:g[-1] + 1][sub].mean()
    if xc < 0.62 or dark < 140:          # 가운데거나 진하면 캡션
        return False
    cut = int(im.height * (groups[-2][-1] + g[0]) / 2.0 / 400.0)
    im.crop((0, 0, im.width, cut)).save(dst, quality=95)
    return True


def prepare(items, build_dir, illust_dirs=(), category="", grade=""):
    """수확 결과 → 지면 항목. 그림은 build 로 복사한다.

    입력은 **지면 순서 목록**이다(지문과 암기테스트가 섞여 있다). 암기테스트를
    직전 지문에 매달면 교과서처럼 여러 지문을 묶는 책에서 어긋난다.
    """
    # 한 지면에 못 담는 지문은 먼저 나눈다 — 그대로 두면 상자 밖으로 밀려
    # 글자가 통째로 사라진다(G-P7 이 배재2에서 3지문 잡았다).
    from core.render_vivlio.series.pocketbook import longsplit
    items = longsplit.split_all(items, log=None)
    global _IDX
    _IDX = illust_index(illust_dirs)
    assets = os.path.join(build_dir, "img")
    os.makedirs(assets, exist_ok=True)
    out = []
    last_cat = ""          # 암기 TEST 는 그 지문 뒤에 오므로 단원을 물려받는다
    for i, p in enumerate(items):
        if p.get("kind") == "memtest":
            ans = bool(p.get("answer"))
            src = p.get("body_runs") or _flatten(p.get("body"))
            # ⚠ 암기 TEST 항목에는 `unit` 이 없다. 그대로 두면 정답면 꼬리말에
            #   쪽번호만 나가고 **단원이 빈다**(사용자 지적). 앞 지문 것을 쓴다.
            out.append({"kind": "memtest", "answer": ans,
                        "key": p.get("key") or "",
                        "runs": format_memtest(src, ans),
                        "category": (p.get("category") or p.get("unit")
                                     or last_cat or category)})
            continue
        illust = None
        # ① 완성본에서 수확한 지문은 링크가 있다.
        # ② 분석본에서 온 새 지문은 링크가 없다 → 지문번호로 찾는다.
        # ⚠ 모의고사는 **삽화정리 폴더가 정본**이다(`고1/24년 9월/21.jpg`).
        #   분석본에 링크된 그림은 그 분석본 것이라 포켓북에 쓸 그림과 다르다 —
        #   링크를 먼저 보다가 18지문이 전부 엉뚱한 그림으로 나갔다(연구원 지적).
        src = None if p.get("short") else find_illust(
            p.get("pno") or p.get("key"), p.get("grade") or grade, illust_dirs)
        if src is None:
            for uri in p.get("links") or ():
                cand = _resolve_link(uri, illust_dirs)
                if cand and os.path.splitext(cand)[1].lower() in (
                        ".jpg", ".jpeg", ".png"):
                    src = cand
                    break
        if src is None:
            # ⚠ 지문번호로만 찾으면 **모의고사 말고는 하나도 안 붙는다**. 부교재·
            #   교과서는 번호가 없고 라벨(`1강 01`·`본문2`)뿐이다 — 라벨로 찾는다.
            # ⚠ 짤지문(안내문·도표)은 삽화가 **없다**. 붙이면 그 뒤 지문의
            #   그림이 한 칸씩 밀린 것처럼 보인다(18·19번 실측, 사용자 지적).
            src = None if p.get("short") else illust_for(p, _IDX)
        if src:
            dst = os.path.join(assets, "p%03d%s" % (i, os.path.splitext(src)[1]))
            try:
                if not _copy_wo_credit(src, dst):
                    shutil.copyfile(src, dst)
                illust = "img/" + os.path.basename(dst)
            except OSError:
                illust = None
        mt = p.get("memtest") or {}
        last_cat = p.get("category") or p.get("unit") or category
        out.append({
            "kind": "passage",
            "key": p.get("key") or p.get("pno") or p.get("label") or "",
            "no": p.get("pno") or "",
            "label": p.get("label") or "",
            # 오른쪽 면 꼬리말은 단원 이름이다(`모의고사`·`교과서 4과`).
            # 코퍼스가 `unit` 으로 들고 있으므로 config 기본값보다 먼저 본다.
            "category": last_cat,
            # ⚠ 여기서 항목을 **새로 만들기** 때문에 적어 두지 않은 열쇠는
            #   조용히 사라진다. 배지 표시 지시가 그렇게 한 번 사라졌다.
            "_badge_raw": bool(p.get("_badge_raw")),
            # 기존 포켓북에서 온 지문인가 — 신규 검수 표시가 이걸 본다
            "_from_book": p.get("_from_book") or "",
            # 모의고사 짤지문 — 오른쪽 면을 만들지 않는다
            "short": bool(p.get("short")),
            # 장문 — 지문을 반으로 갈라 두 면에 나눈다
            "split": bool(p.get("split")),
            # 연구원이 이미 손본 자리 — 검수 표시를 다시 달지 않는다
            "_fixed": p.get("_fixed") or [],
            # 이 책에서 검수를 한 바퀴 돈 지문 — 마찬가지로 다시 달지 않는다
            "_reviewed": bool(p.get("_reviewed")),
            "passage_runs": _flatten(p.get("passage")),
            "translation": _plain(p.get("translation")),
            "flownote": p.get("flownote") or [],
            "topic": p.get("topic") or "",
            "summary": p.get("summary") or "",
            "synonyms": p.get("synonyms") or [],
            # 분석본 VOCA 표(중요어휘/뜻). 지면에는 안 나가지만 빈 동반의어를
            # 채울 때 후보로 쓰라고 들고 간다.
            "voca": p.get("voca") or [],
            "illust": illust,
            "memtest": {k: _flatten(v) for k, v in mt.items() if v} or None,
        })
    return out


def plain_passage(row):
    """지문 원문 한 덩이 — 수확기·조판 어느 모양이든 받는다."""
    for key in ("passage_text", "passage_runs", "passage"):
        v = row.get(key)
        if not v:
            continue
        if isinstance(v, str):
            return v
        out = []
        for x in v:
            if isinstance(x, dict) and "runs" in x:
                out.append("".join(r.get("t", "") for r in x["runs"]))
            elif isinstance(x, dict):
                out.append(x.get("t", ""))
        return " ".join(out)
    return ""
