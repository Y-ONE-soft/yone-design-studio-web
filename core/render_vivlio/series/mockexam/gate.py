# -*- coding: utf-8 -*-
"""동형모의고사 자동 검수 게이트 — 원고 32부를 한 명령으로 훑는다.

    python3 -m core.render_vivlio.series.mockexam.gate            # 전 학교 전 회차
    python3 -m core.render_vivlio.series.mockexam.gate 배재1 한영3  # 골라서
    python3 -m core.render_vivlio.series.mockexam.gate --json      # 기계용

여태 회차마다 즉석 스크립트로 세던 것을 고정한다. 게이트는 **렌더까지 직접
돌린다** — 남이 만들어 둔 PDF 를 믿지 않는다. 산출물(PDF·HTML)과 입력(원고
단락·프로파일)을 나란히 놓고 아래 아홉을 본다.

  1 배점 합    PDF 에 실제로 찍힌 배점의 합 == 프로파일 총점
  2 발문 누락   발문이 빈 문항 중 묶음 구성원이 아닌 것
  3 문항 수    원고 머리 선언 vs 파싱 결과
  4 출처 누출   교재명·기출 출처가 시험지에 남았는가
  5 머리표     `exam-head` 가 있는가
  6 묶음 크기   6문항 넘는 묶음(대개 오탐)
  7 원고 그림   원고에 도표가 있는데 PDF 에 그림이 없는가
  8 밑줄       원고 run 의 밑줄이 HTML 로 넘어왔는가
  9 오버플로우  본문이 지면 밖으로 나갔는가 / 마지막 쪽이 비었는가

판정은 **실패(✘)** 와 **경고(⚠)** 를 가른다. 경고는 원고 자체가 틀린 경우처럼
조판이 고칠 수 없는 것들이다 — 실패로 세면 게이트가 늘 빨개서 아무도 안 본다.
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from core.render_vivlio.series.mockexam import build, markup, profile as P

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
BOOK_DIR = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/동형모의고사")
MS_DIR = os.path.join(BOOK_DIR, "원고")
OUT_DIR = os.path.join(BOOK_DIR, "_비블리오_시안", "_게이트")

OK, WARN, FAIL = "✔", "⚠", "✘"


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ── 원고 찾기 ───────────────────────────────────────────────────────────────
# 프로파일이 파일 이름을 적어 뒀다(`manuscript.files`). 이름은 NFD 로 저장돼
# 있어서 그냥 비교하면 안 맞는다. 세종1 은 원고 폴더에 없고 업로드 job 폴더에만
# 있다 — 이름으로 찾되, 없다고 조용히 건너뛰지 않고 사유를 남긴다.

_RE_ROUND = re.compile(r"(\d+)\s*회")


def _index(dirpath):
    try:
        return {nfc(f): os.path.join(dirpath, f) for f in os.listdir(dirpath)}
    except OSError:
        return {}


_ms_index = None
_job_index = None


def _lookup(name):
    global _ms_index, _job_index
    if _ms_index is None:
        _ms_index = _index(MS_DIR)
    hit = _ms_index.get(nfc(name))
    if hit:
        return hit
    if _job_index is None:
        _job_index = {}
        for up in glob.glob(os.path.join(WEB_ROOT, "jobs", "*", "uploads")):
            for k, v in _index(up).items():
                _job_index.setdefault(k, v)
    return _job_index.get(nfc(name))


def manuscripts(key):
    """[(회차, 경로 또는 None, 원고이름), …] — 회차 순."""
    files = ((P.raw(key).get("manuscript") or {}).get("files")) or []
    if isinstance(files, str):
        files = [files]
    out = []
    for name in files:
        if not isinstance(name, str) or not name.strip():
            continue
        m = _RE_ROUND.search(nfc(name))
        rnd = int(m.group(1)) if m else len(out) + 1
        out.append((rnd, _lookup(name), name))
    return sorted(out, key=lambda t: t[0])


# ── 1. 배점 ─────────────────────────────────────────────────────────────────
# 학교마다 괄호가 다르다([] 〔〕 () （）). 형식을 나열하지 않고 **괄호로 감싼
# `숫자 + 점`** 이라는 모양으로 잡는다. `각 … 씩` 이 붙은 것은 묶음 머리라
# 구성원 수만큼 곱해야 한다.
_RE_SCORE = re.compile(
    r"[\[\(（〔【]\s*(각)?\s*(\d+(?:\.\d+)?)\s*점\s*(?:씩)?\s*[\]\)）〕】]")
# 배점표(세종 계열)는 표 칸에 숫자만 적는다 — `점` 이 없어 위 정규식에 안 걸린다.

# 성덕2 는 정본 배점표 합이 100.2 다. 학교 시험지 자체 오식이라 고치지 않기로
# 했다(브리프 '알려진 미결'). 기대값을 학교 실물에 맞추고 사유를 찍는다.
SCORE_EXPECT = {
    "성덕2": (100.2, "학교 시험지 자체 오식(정본 합 100.2) — 고치지 않기로 했다"),
}


def _profile_total(key):
    a = ((P.raw(key).get("score") or {}).get("allocation") or {})
    tot = a.get("총점") or {}
    v = tot.get("합계")
    if isinstance(v, (int, float)):
        return float(v)
    sel, ess = tot.get("선택형"), tot.get("서답형")
    if isinstance(sel, (int, float)):
        return float(sel) + (float(ess) if isinstance(ess, (int, float)) else 0.0)
    return None


_RE_HTML_GROUP = re.compile(r'<p class="group">(.*?)</p>', re.S)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_HEAD_RANGE = re.compile(r"(\d+)\s*[~\-–—]\s*(\d+)")


def _group_multipliers(html, plan):
    """묶음 머리 `[각 N점씩]` 하나가 문항 몇 개 몫인가.

    구성원 수는 조판이 만든 plan 이 정답이다(HTML 머리에 범위가 안 찍히는
    학교가 있다). 순서대로 짝지어 준다. 짝이 안 맞으면 머리에 적힌 범위로
    되짚고, 그것도 없으면 1 로 둔다 — 지어내지 않고 근거를 같이 돌려준다.
    """
    heads = [_RE_TAG.sub("", h) for h in _RE_HTML_GROUP.findall(html)]
    heads = [h for h in heads if _RE_SCORE.search(h)
             and _RE_SCORE.search(h).group(1)]
    counts = [len(r["group"]["members"]) for r in plan
              if r.get("group") and r["group"].get("members")
              and any(m.get("no_stem") for m in r["group"]["members"])]
    notes = []
    if len(counts) != len(heads):
        notes.append(f"묶음 머리 {len(heads)}개 vs plan 공통발문 묶음 "
                     f"{len(counts)}개 — 머리에 적힌 범위로 되짚었다")
        counts = []
        for h in heads:
            m = _RE_HEAD_RANGE.search(h)
            counts.append(int(m.group(2)) - int(m.group(1)) + 1 if m else 1)
    out = []
    for h, n in zip(heads, counts):
        m = _RE_SCORE.search(h)
        out.append((float(m.group(2)), n))
    return out, notes


_RE_TABLE_CELL = re.compile(r"<td[^>]*>\s*([\d]+(?:\.\d+)?)\s*</td>")
_RE_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_RE_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S)


def _score_table_sum(html, spec):
    """배점표(세종 계열) 칸 값의 합. 표가 없으면 None.

    표는 (번호행, 배점행) 이 한 쌍이라 **행을 가리지 않으면 문항 번호까지
    더해진다**(세종1 이 400.0 으로 나왔다). 행 머리를 프로파일이 적어 둔
    배점 라벨과 맞춰 고르고, 못 맞추면 짝수번째(배점) 행으로 되짚는다.
    """
    m = re.search(r'<table class="score-table".*?</table>', html, re.S)
    if not m:
        return None
    rows = _RE_TR.findall(m.group(0))
    if not rows:
        return None
    label = (spec.score_table_heads or ("번호", "배점"))[1]
    picked = [r for r in rows
              if any(_RE_TAG.sub("", h).strip() == str(label).strip()
                     for h in _RE_TH.findall(r))]
    if not picked:
        picked = rows[1::2]
    vals = [float(x) for r in picked for x in _RE_TABLE_CELL.findall(r)]
    return round(sum(vals), 2) if vals else None


def check_score(key, spec, html, pdf_text, plan):
    want = _profile_total(key)
    note = None
    if key in SCORE_EXPECT:
        want, note = SCORE_EXPECT[key]
    detail = {"기대": want}

    table = _score_table_sum(html, spec)
    if spec.fmt_score(3.0) is None:
        # 문항 옆에 배점을 안 찍는 학교(세종1) — 마지막 쪽 배점표가 근거다
        got = table
        detail["방식"] = "배점표"
        if got is None:
            return FAIL, "배점표도 문항 배점도 없다", detail
    else:
        singles = [float(m.group(2)) for m in _RE_SCORE.finditer(pdf_text)
                   if not m.group(1)]
        mults, notes = _group_multipliers(html, plan)
        got = round(sum(singles) + sum(v * n for v, n in mults), 2)
        detail.update({"방식": "문항 배점", "낱개": len(singles),
                       "묶음머리": [[v, n] for v, n in mults]})
        if notes:
            detail["주의"] = notes
        # 배점표까지 있는 학교(강동 계열)는 두 곳이 같은 값을 말해야 한다
        if table is not None:
            detail["배점표"] = table
            if abs(table - got) >= 0.05:
                return (FAIL, f"문항 배점 합 {got} vs 배점표 합 {table} 불일치",
                        detail)
    detail["합"] = got
    if want is None:
        return WARN, f"프로파일에 총점이 없다 (PDF 합 {got})", detail
    if abs(got - want) < 0.05:
        return (OK, f"{got}/{want}" + (f" — {note}" if note else ""), detail)
    return FAIL, f"{got} ≠ {want}" + (f" ({note})" if note else ""), detail


# ── 2. 발문 누락 ────────────────────────────────────────────────────────────

def check_stems(plan):
    bad = []
    for row in plan:
        it = row["item"]
        if (it.get("question") or "").strip():
            continue
        if row.get("no_stem"):
            continue          # 공통발문형 묶음 구성원 — 발문이 머리에 있다
        bad.append(f"{'서답형' if row['essay'] else ''}{row['no']}번"
                   f"({it.get('id')})")
    if not bad:
        return OK, "0개", {"빈발문": []}
    return FAIL, f"{len(bad)}개: {', '.join(bad[:6])}", {"빈발문": bad}


# ── 3. 문항 수 ──────────────────────────────────────────────────────────────

def check_counts(paras, ir):
    from engines.mockexam_v2.parser import declared_counts
    d_sel, d_srv = declared_counts(paras)
    items = ir.get("items", [])
    n_srv = sum(1 for it in items if it.get("kind") == "서술형")
    n_sel = len(items) - n_srv
    detail = {"선언": [d_sel, d_srv], "파싱": [n_sel, n_srv]}
    if d_sel is None and d_srv is None:
        return WARN, f"원고에 선언이 없다 (파싱 {n_sel}+{n_srv})", detail
    diff = []
    if d_sel is not None and d_sel != n_sel:
        diff.append(f"선택형 선언 {d_sel} vs 파싱 {n_sel}")
    if d_srv is not None and d_srv != n_srv:
        diff.append(f"서답형 선언 {d_srv} vs 파싱 {n_srv}")
    if diff:
        # 원고 선언 자체가 틀린 원고가 있다(명일3·한영1) — 실패가 아니라 경고다
        return WARN, "; ".join(diff), detail
    return OK, f"{n_sel}+{n_srv}", detail


# ── 4. 출처 누출 ────────────────────────────────────────────────────────────
# 시험지에 남으면 안 되는 것: 원고가 지문 옆에 적어 둔 교재·기출 출처.
_LEAKS = [
    ("리딩파워", re.compile(r"리딩\s*파워")),
    ("유형편", re.compile(r"유형편")),
    ("Further Reading", re.compile(r"Further\s+Reading", re.I)),
    ("[TED]", re.compile(r"\[\s*TED\s*\]", re.I)),
    ("교과서 N과", re.compile(r"교과서\s*\d+\s*과")),
    ("올림포스", re.compile(r"올림포스")),
    ("수능특강", re.compile(r"수능\s*특강")),
]


def check_leak(pdf_text):
    hits = []
    for name, rx in _LEAKS:
        n = len(rx.findall(pdf_text))
        if n:
            hits.append(f"{name}×{n}")
    if hits:
        return FAIL, ", ".join(hits), {"누출": hits}
    return OK, "0건", {"누출": []}


# ── 5. 머리표 ───────────────────────────────────────────────────────────────

def check_head(html):
    n = html.count('class="exam-head"')
    if n:
        return OK, "있다", {"exam_head": n}
    return FAIL, "exam-head 없다", {"exam_head": 0}


# ── 6. 묶음 크기 ────────────────────────────────────────────────────────────
_GROUP_MAX = 6


def check_groups(plan):
    sizes = [len(r["group"]["members"]) for r in plan if r.get("group")]
    big = [n for n in sizes if n > _GROUP_MAX]
    detail = {"묶음": sizes}
    if big:
        return WARN, f"{len(big)}개가 {_GROUP_MAX}문항 초과 ({big}) — 대개 오탐", detail
    return OK, f"{len(sizes)}개", detail


# ── 7. 원고 그림 ────────────────────────────────────────────────────────────

def check_images(paras, ir, page_images):
    anchored = sum(1 for p in paras if isinstance(p, dict) and p.get("image"))
    in_ir = sum(1 for it in ir.get("items", [])
                for b in ((it.get("stimulus") or {}).get("blocks") or [])
                if b.get("kind") == "image")
    detail = {"원고": anchored, "IR": in_ir, "PDF": page_images}
    if not anchored:
        return OK, "원고에 그림 없음", detail
    if not page_images:
        return FAIL, f"원고 그림 {anchored}개인데 PDF 에 0개", detail
    if in_ir < anchored:
        return WARN, f"원고 {anchored} → IR {in_ir} → PDF {page_images}", detail
    return OK, f"{page_images}개", detail


# ── 8. 밑줄 ─────────────────────────────────────────────────────────────────

def check_underline(paras, html):
    src = sum(1 for p in paras if isinstance(p, dict)
              for r in (p.get("runs") or [])
              if r.get("ul") and (r.get("t") or "").strip())
    got = html.count("<u>")
    detail = {"원고run": src, "html_u": got}
    if not src:
        return OK, "원고에 밑줄 없음", detail
    if not got:
        return FAIL, f"원고 밑줄 {src}개인데 HTML 에 0개", detail
    return OK, f"{got}개(원고 run {src})", detail


# ── 9. 오버플로우 / 빈 쪽 ───────────────────────────────────────────────────
_EMPTY_LAST = 60       # 마지막 쪽 글자 수가 이보다 적으면 '거의 빈 쪽'
_BLEED = 1.0           # pt — 반올림 오차


def check_overflow(doc):
    over = []
    for i, page in enumerate(doc, 1):
        r = page.rect
        for b in page.get_text("blocks"):
            x0, y0, x1, y1 = b[:4]
            if (x0 < r.x0 - _BLEED or y0 < r.y0 - _BLEED
                    or x1 > r.x1 + _BLEED or y1 > r.y1 + _BLEED):
                over.append(f"{i}쪽 ({round(x0)},{round(y0)})-"
                            f"({round(x1)},{round(y1)})")
                break
    last = len(doc[-1].get_text().strip()) if len(doc) else 0
    detail = {"쪽수": len(doc), "지면밖": over, "마지막쪽_글자": last}
    if over:
        return FAIL, f"지면 밖 {len(over)}쪽: {', '.join(over[:3])}", detail
    if last < _EMPTY_LAST:
        return WARN, f"마지막 {len(doc)}쪽이 거의 비었다({last}자)", detail
    return OK, f"{len(doc)}쪽", detail


# ── 한 부 검사 ──────────────────────────────────────────────────────────────
CHECKS = ["배점", "발문", "문항수", "출처", "머리표", "묶음", "그림", "밑줄", "지면"]


def inspect(key, rnd, path, out_dir=OUT_DIR, keep=True):
    """원고 한 부 → 검사 결과 dict."""
    import fitz
    from engines.mockexam_v2.parser import build_ir, extract_file_paragraphs

    res = {"key": key, "round": rnd, "manuscript": path, "checks": {},
           "error": None, "pages": None, "warnings": []}
    try:
        paras = extract_file_paragraphs(path)
        ir = build_ir(paras)
        out_pdf = os.path.join(out_dir, f"{key}_{rnd}회.pdf")
        r = build.render(ir, key, out_pdf, log=lambda *a: None,
                         build_dir=os.path.join(out_dir, f"_build_{key}_{rnd}"))
        res["pages"] = r["pages"]
        res["warnings"] = list(r["warnings"])
        res["pdf"] = out_pdf
        with open(os.path.join(r["build_dir"], "index.html"),
                  encoding="utf-8") as f:
            html = f.read()
        doc = fitz.open(out_pdf)
        pdf_text = nfc("\n".join(p.get_text() for p in doc))
        n_img = sum(len(p.get_images()) for p in doc)
        plan = markup._number_items(ir)
        spec = P.get(key)

        c = res["checks"]
        c["배점"] = check_score(key, spec, html, pdf_text, plan)
        c["발문"] = check_stems(plan)
        c["문항수"] = check_counts(paras, ir)
        c["출처"] = check_leak(pdf_text)
        c["머리표"] = check_head(html)
        c["묶음"] = check_groups(plan)
        c["그림"] = check_images(paras, ir, n_img)
        c["밑줄"] = check_underline(paras, html)
        c["지면"] = check_overflow(doc)
        doc.close()
    except Exception as e:       # 렌더 실패도 결과다 — 죽지 않고 보고한다
        res["error"] = f"{type(e).__name__}: {e}"
    return res


def verdict(res):
    if res["error"]:
        return FAIL
    marks = [v[0] for v in res["checks"].values()]
    if FAIL in marks:
        return FAIL
    if WARN in marks:
        return WARN
    return OK


def line(res):
    v = verdict(res)
    head = f"{res['key']:5s} {res['round']}회 {v}"
    if res["error"]:
        return f"{head}  렌더 실패 — {res['error']}"
    c = res["checks"]
    bits = []
    for name in CHECKS:
        mark, msg, _d = c[name]
        if mark == OK and name in ("발문", "출처", "머리표", "묶음"):
            continue          # 통과가 당연한 항목은 줄을 아끼고 실패만 적는다
        bits.append(f"{name} {msg}" if mark == OK else f"{mark}{name} {msg}")
    return f"{head}  " + " · ".join(bits)


# ── 실행 ────────────────────────────────────────────────────────────────────

def run(keys=None, jobs=4, out_dir=OUT_DIR):
    keys = keys or P.available()
    os.makedirs(out_dir, exist_ok=True)
    tasks = []
    missing = []
    for key in keys:
        for rnd, path, name in manuscripts(key):
            if path:
                tasks.append((key, rnd, path))
            else:
                missing.append((key, rnd, name))
    if jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(
                lambda t: inspect(t[0], t[1], t[2], out_dir), tasks))
    else:
        results = [inspect(*t, out_dir=out_dir) for t in tasks]
    results.sort(key=lambda r: (keys.index(r["key"]), r["round"]))
    return results, missing


def report(results, missing, stream=sys.stdout):
    p = lambda *a: print(*a, file=stream)
    p(f"동형모의고사 검수 게이트 — {len({r['key'] for r in results})}개 학교 "
      f"{len(results)}부")
    p("─" * 78)
    for r in results:
        p(line(r))
    for key, rnd, name in missing:
        p(f"{key:5s} {rnd}회 {FAIL}  원고를 못 찾았다 — {name}")

    fails = []
    warns = []
    for r in results:
        if r["error"]:
            fails.append((r["key"], r["round"], "렌더", r["error"]))
            continue
        for name in CHECKS:
            mark, msg, _d = r["checks"][name]
            (fails if mark == FAIL else warns if mark == WARN else []).append(
                (r["key"], r["round"], name, msg))
    for key, rnd, name in missing:
        fails.append((key, rnd, "원고", f"파일 없음 — {name}"))

    p("─" * 78)
    n_ok = sum(1 for r in results if verdict(r) == OK)
    n_warn = sum(1 for r in results if verdict(r) == WARN)
    n_fail = len(results) - n_ok - n_warn + len(missing)
    p(f"{OK} {n_ok}부  {WARN} {n_warn}부  {FAIL} {n_fail}부   "
      f"· 실패 {len(fails)}건 · 경고 {len(warns)}건")
    if fails:
        p(f"\n{FAIL} 실패 {len(fails)}건")
        for key, rnd, name, msg in fails:
            p(f"   {key} {rnd}회 [{name}] {msg}")
    if warns:
        p(f"\n{WARN} 경고 {len(warns)}건")
        for key, rnd, name, msg in warns:
            p(f"   {key} {rnd}회 [{name}] {msg}")
    return len(fails)


def to_json(results, missing):
    out = {"부": [], "누락원고": [{"key": k, "round": r, "file": n}
                              for k, r, n in missing],
           "요약": {}}
    n_fail = 0
    for r in results:
        row = {"key": r["key"], "round": r["round"], "verdict": verdict(r),
               "pages": r["pages"], "error": r["error"],
               "warnings": r["warnings"], "checks": {}}
        for name, (mark, msg, detail) in r["checks"].items():
            row["checks"][name] = {"verdict": mark, "message": msg,
                                   "detail": detail}
            if mark == FAIL:
                n_fail += 1
        if r["error"]:
            n_fail += 1
        out["부"].append(row)
    out["요약"] = {
        "부": len(results),
        "통과": sum(1 for r in results if verdict(r) == OK),
        "경고": sum(1 for r in results if verdict(r) == WARN),
        "실패": sum(1 for r in results if verdict(r) == FAIL) + len(missing),
        "실패항목": n_fail + len(missing),
    }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python3 -m core.render_vivlio.series.mockexam.gate",
        description="동형모의고사 조판 자동 검수 게이트")
    ap.add_argument("keys", nargs="*", help="학교키 (없으면 전 학교)")
    ap.add_argument("--json", action="store_true", help="JSON 으로 낸다")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="동시 렌더 수")
    ap.add_argument("-o", "--out", default=OUT_DIR, help="산출 폴더")
    a = ap.parse_args(argv)

    keys = a.keys or P.available()
    unknown = [k for k in keys if k not in P.available()]
    if unknown:
        ap.error(f"모르는 학교키: {', '.join(unknown)} "
                 f"(있는 학교: {', '.join(P.available())})")

    results, missing = run(keys, jobs=a.jobs, out_dir=a.out)
    if a.json:
        json.dump(to_json(results, missing), sys.stdout,
                  ensure_ascii=False, indent=1)
        print()
        n_fail = to_json(results, missing)["요약"]["실패항목"]
    else:
        n_fail = report(results, missing)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
