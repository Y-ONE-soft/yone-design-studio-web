# -*- coding: utf-8 -*-
"""완성 포켓북 IDML → 새 엔진 재조판 회귀 검증.

**묻는 것은 하나다: 이미 납품된 포켓북을 새 엔진으로 다시 짜면 내용이 새는가.**

원본 IDML 을 `idml.read_sequence()` 로 읽어 그것을 그대로 원고로 삼고
(코퍼스를 거치지 않는다 — 코퍼스 수확 단계의 손실까지 섞이면 어디서 샜는지
못 가린다), 포켓북 계열로 조판한 뒤 계열 게이트(G-P1·P3·P6·P7)를 건다.

원본이 곧 정답이므로 **글자 개수 대조(G-P7)** 가 이 검증의 핵심이다.
거기에 계열 게이트가 못 보는 자리를 하나 더 막는다 — **R1**: 원본 IDML 에서
지문 스프레드 수를 직접 세어, 읽는 쪽이 지문을 흘렸는지 본다(계열 게이트는
행과 면이 함께 줄면 통과한다).

    python3 tools/pocket_harvest/regress.py            # 전권
    python3 tools/pocket_harvest/regress.py --jobs 3   # 병렬
    python3 tools/pocket_harvest/regress.py --only 광문2  # 이름 일부
    python3 tools/pocket_harvest/regress.py --force    # 이미 돈 권도 다시
    python3 tools/pocket_harvest/regress.py --retry --force   # 실패한 권만 다시

⚠ InDesign 은 건드리지 않는다. 다른 프로세스가 IDML 을 계속 내보내는 중이라
  **시작 시점의 목록만** 훑는다(중간에 늘어난 것은 다음 실행에서 잡는다).
⚠ 조판 산출물은 임시 폴더에만 만든다. 교재 폴더의 납품 PDF 를 덮으면 안 된다.
"""
import argparse
import json
import os
import shutil
import sys
import time
import traceback
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import idml  # noqa: E402  (tools/pocket_harvest/idml.py)

from core.render_vivlio import series as vseries  # noqa: E402
from core.render_vivlio import config as vconfig  # noqa: E402
from core.render_vivlio import verify as vverify  # noqa: E402

STUDIO = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북")
IDML_ROOT = os.path.join(STUDIO, "_idml")
REPORT = os.path.join(IDML_ROOT, "_regress.md")
# 임시 작업대 — 교재 폴더가 아니다(납품본을 덮지 않기 위해).
WORK = os.path.expanduser("~/.cache/yone/pocket_regress")
STATE = os.path.join(WORK, "_state.json")

ILLUST_DIRS = [os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
    "콘텐츠 관리/내신대비/포켓북 삽화정리")]


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ── ① 대상 고르기 ────────────────────────────────────────────────────────
def discover(root=IDML_ROOT):
    """완성 포켓북 IDML 목록. **파일명 NFC 정규화가 필수다.**

    macOS 파일 이름은 NFD 로 온다 — `"포켓북" in name` 이 그냥은 안 맞는다.
    (분석본은 원고이지 완성본이 아니므로 제외한다.)
    """
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            n = nfc(f)
            if not n.lower().endswith(".idml"):
                continue
            if "포켓북" not in n:
                continue
            if "분석본" in n:
                continue
            out.append(os.path.join(dirpath, f))
    return sorted(out, key=lambda p: nfc(p))


def source_passage_spreads(src):
    """원본 IDML 에서 **지문 스프레드 수**를 read_sequence 와 무관하게 센다.

    회귀 검증이 `read_sequence` 의 셈을 그대로 믿으면, 읽는 쪽에서 지문을
    통째로 흘렸을 때 게이트가 **다 통과한다** — 행도 면도 똑같이 줄어드니까.
    실제로 그랬다(광문2 25-2-기말 79지문 중 43개가 조용히 빠졌는데 G-P1 통과).

    그래서 여기서는 스토리 하나만 본다: **긴 영어 본문**이 있는 스프레드.
    짤지문 스프레드는 지문이 둘이므로 이 값은 **하한**이다.
    """
    doc = idml.Idml(src)
    n = 0
    for sp in doc.spreads():
        seen = set()
        for fr in sp["frames"]:
            sid = fr["story"]
            if sid in seen:
                continue
            seen.add(sid)
            paras = doc.paragraphs(sid)
            if not paras:
                continue
            if idml._para_role(paras) != "passage":
                continue
            txt = "\n".join(idml.plain(p["runs"]) for p in paras)
            # 한글 비율이 높으면 해석이다(지문과 같은 `본문` 스타일을 쓴다).
            if len(txt.strip()) >= 200 and idml.han_ratio(txt) <= 0.35:
                n += 1
                break
    return n


def _src_chars(src):
    """원본 IDML 의 총 글자 수. `[작업전]` 같은 빈 껍데기를 가리는 데 쓴다."""
    doc = idml.Idml(src)
    seen, n = set(), 0
    for sp in doc.spreads():
        for fr in sp["frames"]:
            if fr["story"] in seen:
                continue
            seen.add(fr["story"])
            n += len(doc.text_of(fr["story"]))
    return n


def slug(path):
    """작업 폴더 이름 — 학기 폴더까지 넣어야 같은 학교가 안 겹친다."""
    rel = os.path.relpath(nfc(path), nfc(IDML_ROOT))
    rel = os.path.splitext(rel)[0]
    return rel.replace(os.sep, "__").replace(" ", "_")


# ── ② 한 권 돌리기 ───────────────────────────────────────────────────────
CONFIG = {
    "series": "pocketbook",
    "page": {"width": 148, "height": 210, "bleed": 3},
    "output": {"dir": ".", "stem": "내지"},
    "options": {"category": "", "folio_start": 2,
                "illust_dirs": ILLUST_DIRS},
    # finish 는 비운다 — 표지 .ai 는 회귀 검증과 무관하고, 없으면 검수가
    # `_body.pdf` 만 보게 되어 면 번호가 밀리지 않는다.
}


def _mkbook(src, work):
    """임시 책 폴더 + data.json. 원고는 IDML 원본 그대로다."""
    build = os.path.join(work, "build")
    os.makedirs(build, exist_ok=True)
    items = idml.read_sequence(src)
    cfg = dict(CONFIG)
    cfg["book"] = {"id": slug(src), "title": nfc(os.path.basename(src))}
    with open(os.path.join(work, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    with open(os.path.join(build, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"passages": items}, f, ensure_ascii=False)
    return items


def run_one(src, force=False, log=print):
    """한 권 조판 + 검수 → 결과 dict. 예외는 삼키고 결함으로 적는다."""
    t0 = time.time()
    work = os.path.join(WORK, slug(src))
    if force and os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    row = {"src": nfc(src), "name": nfc(os.path.basename(src)),
           "slug": slug(src), "work": work}
    try:
        items = _mkbook(src, work)
        row["n_passage"] = sum(1 for x in items if x.get("kind") != "memtest")
        row["n_memtest"] = sum(1 for x in items if x.get("kind") == "memtest")
        # R1 — 읽는 쪽이 지문을 흘렸는가. 계열 게이트로는 절대 안 잡힌다.
        row["n_src"] = source_passage_spreads(src)
        if not row["n_passage"]:
            # 왜 0인지까지 적는다 — "원본이 비었다"와 "읽는 쪽이 흘렸다"는
            # 대응이 정반대다. 원본 글자 수가 그 자리에서 가른다.
            row["status"] = "SKIP"
            row["fails"] = [
                "지문 0개 · 원본 지문 스프레드 %d개 — %s"
                % (row["n_src"],
                   "원본이 빈 껍데기다(글자 %d자)" % _src_chars(src)
                   if row["n_src"] == 0 else "읽는 쪽이 흘렸다 — 엔진 결함")]
            row["secs"] = round(time.time() - t0, 1)
            return row
        cfg = vconfig.load(work)
        rep = vverify.Report(row["name"])
        vseries.get("pocketbook").build(cfg, log)
        vseries.get("pocketbook").verify(cfg, log, rep)
        if row["n_passage"] < row["n_src"]:
            rep.fail("R1 원본 지문 유실 — 지면 %d개 < 원본 지문 스프레드 %d개"
                     % (row["n_passage"], row["n_src"]))
        row["fails"] = list(rep.fails)
        row["warns"] = list(rep.warns)
        row["notes"] = list(rep.notes)
        row["status"] = "PASS" if rep.ok else "FAIL"
        from core.render_vivlio import probe
        body = os.path.join(work, "build", "_body.pdf")
        row["n_pages"] = probe.page_count(body) if os.path.exists(body) else 0
    except Exception as e:            # 한 권이 죽어도 전권은 계속 돈다
        row["status"] = "ERROR"
        row["fails"] = ["%s: %s" % (type(e).__name__, e)]
        row["trace"] = traceback.format_exc()[-1500:]
    row["secs"] = round(time.time() - t0, 1)
    return row


# ── ③ 이어돌리기 ─────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE):
        try:
            with open(STATE, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            pass
    return {}


def save_state(st):
    os.makedirs(WORK, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)          # 중간에 끊겨도 상태 파일은 안 깨진다


# ── ④ 보고서 ─────────────────────────────────────────────────────────────
def _label(r):
    """표에 적을 이름 — **학기·학교까지** 적는다.

    파일 이름만 적으면 `강동1_포켓북_내지` 가 학기마다 있어 같은 줄로 보인다.
    """
    src = r.get("src") or ""
    if src.startswith(nfc(IDML_ROOT)):
        return os.path.splitext(os.path.relpath(src, nfc(IDML_ROOT)))[0]
    return r.get("name", "?")


def write_report(st, total, path=REPORT):
    rows = [st[k] for k in sorted(st, key=lambda k: nfc(k))]
    ok = [r for r in rows if r.get("status") == "PASS"]
    bad = [r for r in rows if r.get("status") in ("FAIL", "ERROR")]
    skip = [r for r in rows if r.get("status") == "SKIP"]
    L = []
    L.append("# 포켓북 회귀 검증 — 완성본 IDML 재조판\n")
    L.append("")
    L.append("완성 포켓북을 새 엔진으로 다시 조판해 **내용이 새는지** 본다. "
             "원고는 IDML 원본 그대로다(코퍼스를 거치지 않는다).")
    L.append("")
    # ⚠ IDML 내보내기가 **돌아가는 중**이라 대상 수가 실행 중에도 는다.
    #   그래서 "지금 몇 권 있나"와 "이번에 몇 권 돌렸나"를 따로 적는다.
    L.append("- 지금 내보내진 완성 포켓북 %d권 · 이 표에 담긴 것 %d권"
             % (total, len(rows)))
    if total > len(rows):
        L.append("  (나머지 %d권은 검증 시작 뒤에 내보내진 것 — "
                 "`regress.py` 를 다시 돌리면 이어서 한다)" % (total - len(rows)))
    L.append("- 통과 %d · 실패 %d · 건너뜀 %d"
             % (len(ok), len(bad), len(skip)))
    L.append("- 생성 %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("")
    L.append("| 권 | 지문 | 원본지문면 | 암기 | 면 | 결함 | 초 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        mark = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥",
                "SKIP": "—"}.get(r.get("status"), "?")
        L.append("| %s %s | %s | %s | %s | %s | %d | %s |" % (
            mark, _label(r),
            r.get("n_passage", "-"), r.get("n_src", "-"),
            r.get("n_memtest", "-"),
            r.get("n_pages", "-"), len(r.get("fails") or []),
            r.get("secs", "-")))
    if bad:
        L.append("")
        L.append("## 새는 곳")
        L.append("")
        for r in bad:
            L.append("### %s" % _label(r))
            L.append("")
            for f in r.get("fails") or []:
                L.append("- %s" % f)
            if r.get("trace"):
                L.append("")
                L.append("```")
                L.append(r["trace"].strip())
                L.append("```")
            L.append("")
    if skip:
        # 건너뛴 것은 엔진 결함이 아니다 — 원본이 비어 있다(`[작업전]` 등).
        L.append("")
        L.append("## 건너뛴 것 (원본 문제)")
        L.append("")
        for r in skip:
            L.append("- **%s** — %s" % (_label(r),
                                        "; ".join(r.get("fails") or [])))
    warned = [r for r in rows if r.get("warns")]
    if warned:
        L.append("")
        L.append("## 경고 (게이트는 통과 — 원고 자체가 빈 것)")
        L.append("")
        for r in warned:
            L.append("- **%s** — %s" % (_label(r),
                                        "; ".join(r["warns"])[:400]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


# ── ⑤ 몰이 ───────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="이름 일부로 좁힌다")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--force", action="store_true", help="이미 돈 권도 다시")
    ap.add_argument("--retry", action="store_true",
                    help="지난번 실패한 권만 다시 (엔진을 고친 뒤에 쓴다)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)

    targets = discover()
    total = len(targets)
    if a.only:
        needle = nfc(a.only).lower()
        targets = [p for p in targets if needle in nfc(p).lower()]
    if a.limit:
        targets = targets[:a.limit]
    if a.list:
        for p in targets:
            print(nfc(p))
        print("— %d권" % len(targets))
        return 0

    st = load_state()
    if a.retry:
        todo = [p for p in targets
                if st.get(slug(p), {}).get("status") in ("FAIL", "ERROR")]
    else:
        todo = [p for p in targets
                if a.force or st.get(slug(p), {}).get("status") not in
                ("PASS", "FAIL", "SKIP")]
    print("■ 대상 %d권(시작 시점 %d권) · 이번에 돌릴 것 %d권"
          % (len(targets), total, len(todo)))

    def quiet(*_a, **_k):
        pass

    if a.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(run_one, p, a.force, quiet): p for p in todo}
            for i, fu in enumerate(as_completed(futs), 1):
                r = fu.result()
                st[r["slug"]] = r
                save_state(st)
                print("[%3d/%3d] %-5s %-52s %5.1fs %s" % (
                    i, len(todo), r["status"], r["name"][:52], r["secs"],
                    (r.get("fails") or [""])[0][:70]))
    else:
        for i, p in enumerate(todo, 1):
            r = run_one(p, a.force, quiet)
            st[r["slug"]] = r
            save_state(st)
            print("[%3d/%3d] %-5s %-52s %5.1fs %s" % (
                i, len(todo), r["status"], r["name"][:52], r["secs"],
                (r.get("fails") or [""])[0][:70]))

    # ⚠ 보고서는 **늘 전권**이다. `--only` 로 한 권만 돌렸다고 표가 한 줄로
    #   줄어들면 앞서 돌린 129권의 결과를 통째로 잃는다(그렇게 됐다).
    #   빠진 것은 이제 없는 파일뿐이다.
    all_targets = discover()
    keep = {slug(p) for p in all_targets}
    view = {k: v for k, v in st.items() if k in keep}
    path = write_report(view, len(all_targets))
    ok = sum(1 for v in view.values() if v.get("status") == "PASS")
    bad = sum(1 for v in view.values() if v.get("status") in ("FAIL", "ERROR"))
    print("■ 통과 %d · 실패 %d → %s" % (ok, bad, path))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
