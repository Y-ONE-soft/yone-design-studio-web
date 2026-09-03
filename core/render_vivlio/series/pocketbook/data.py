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


def prepare(items, build_dir, illust_dirs=(), category="", grade=""):
    """수확 결과 → 지면 항목. 그림은 build 로 복사한다.

    입력은 **지면 순서 목록**이다(지문과 암기테스트가 섞여 있다). 암기테스트를
    직전 지문에 매달면 교과서처럼 여러 지문을 묶는 책에서 어긋난다.
    """
    # 한 지면에 못 담는 지문은 먼저 나눈다 — 그대로 두면 상자 밖으로 밀려
    # 글자가 통째로 사라진다(G-P7 이 배재2에서 3지문 잡았다).
    from core.render_vivlio.series.pocketbook import longsplit
    items = longsplit.split_all(items, log=None)
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
        src = None
        for uri in p.get("links") or ():
            cand = _resolve_link(uri, illust_dirs)
            if cand and os.path.splitext(cand)[1].lower() in (
                    ".jpg", ".jpeg", ".png"):
                src = cand
                break
        if src is None:
            src = find_illust(p.get("pno") or p.get("key"),
                              p.get("grade") or grade, illust_dirs)
        if src:
            dst = os.path.join(assets, "p%03d%s" % (i, os.path.splitext(src)[1]))
            try:
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
