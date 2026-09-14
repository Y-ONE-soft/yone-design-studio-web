# -*- coding: utf-8 -*-
"""포켓북 게이트 G-P15~G-P17 — **있는가**가 아니라 **맞는가**를 본다.

광문2 연구원 검수(2026-09-14)에서 지적된 것들은 전 게이트를 통과한 판에서
나왔다. 게이트가 암기 TEST 면은 원문과 안 견줬고, 삽화는 붙었는지만 봤고,
분석본은 폴더에 있는 IDML 만 셌기 때문이다.

  G-P15  암기 TEST 끝이 지문 끝과 같은가 (`comp|any`, `17|5 million`)
  G-P16  삽화 파일 이름·폴더가 그 지문 것인가 (수특 Light 에 올림포스·고3 그림)
  G-P17  드라이브 분석본 .indd 마다 IDML(또는 PDF)이 있는가·옛것은 아닌가
         (26년 6월 분석본을 안 뽑아 6지문이 조용히 빠졌다)
"""
import os
import re
import unicodedata

from core.render_vivlio.series.pocketbook import data as pdata
from core.render_vivlio.series.pocketbook import memtest as pmemtest

DRIVE_ANALYSIS = ("~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
                  "콘텐츠 관리/내신대비/인디자인 파일/분석본")


def _nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


# ══════════════════════════════════════════════════════════════════
# G-P15 암기 TEST 끝
# ══════════════════════════════════════════════════════════════════
TAIL = 20          # 끝 글자 몇 개를 견주나(알파벳만)


def memtest_tail(rows, report, log):
    """암기 TEST 문제면 글이 **지문 끝까지** 가는가.

    알파벳만 견준다(빈칸 번호·괄호·따옴표 모양이 달라도 같아진다). 암기 TEST
    끝 글자들이 지문 **안에서** 발견되면 그 뒤가 잘린 것이다. 지문 어디에도
    없으면 원고 판이 다른 것이라 알리기만 한다.
    """
    body = {}
    for r in rows:
        if r.get("kind") == "memtest":
            continue
        k = r.get("key") or r.get("label")
        body[k] = body.get(k, "") + " " + pdata.plain_passage(r)
    cut, odd, n = [], [], 0
    for r in rows:
        if r.get("kind") != "memtest" or r.get("answer"):
            continue
        k = r.get("key")
        if k not in body:
            continue
        P = pmemtest.letters(body[k])
        T = pmemtest.letters("".join(x.get("t", "") for x in r.get("runs") or []))
        if len(P) < TAIL or len(T) < TAIL:
            continue
        n += 1
        if T[-TAIL:] == P[-TAIL:]:
            continue
        # ⚠ 거리로 가르면 안 된다 — 빈칸 번호가 세 자리면 수백 글자 앞에서
        #   멈춘다(옛 `cut` 을 광문2 전 지문에 돌려 58지문이 「판이 다름」 으로
        #   빠져나갔다). 암기 TEST 끝이 **지문 안 어딘가**에 있으면 잘린 것이다.
        at = P.rfind(T[-TAIL:])
        if at >= 0:
            words = re.sub(r"\s+", " ", body[k]).strip().split(" ")
            cut.append("%s(끝 「…%s」)" % (k, " ".join(words[-4:])))
        else:
            odd.append(k)
    if cut:
        report.fail("G-P15 암기 TEST 끝이 지문보다 짧다 %d지문 — 낱말 가운데서 "
                    "잘렸다: %s" % (len(cut), ", ".join(cut[:6])))
    if odd:
        report.warn("G-P15 암기 TEST 끝이 지문 끝과 다르다(원고 판이 다를 수 있다) "
                    "%d지문 — %s" % (len(odd), ", ".join(odd[:8])))
    if n and not cut and not odd:
        log("  G-P15 암기 TEST 끝 대조 %d지문 — 잘린 것 없음" % n)


# ══════════════════════════════════════════════════════════════════
# G-P16 삽화 이름
# ══════════════════════════════════════════════════════════════════
_MOCK = re.compile(r"^(\d{2})(\d{2})(\d{2})(?:[-~](\d{1,3}))?$")
_BOOKS = (("수특", "수능특강"), ("수능특강", "수능특강"), ("올포", "올림포스"),
          ("올림포스", "올림포스"), ("리딩파워", "리딩파워"), ("마더텅", "마더텅"),
          ("수능만만", "수능만만"))


_PUB = re.compile(r"(YBM|NE능률|능률|비상|미래엔|천재|동아|지학사|금성|다락원|좋은책)"
                  r"\(?([가-힣])\)?(?=\s*[\d,]*\s*(?:과|SL|L\d|$|\)))")


def _nums(s):
    return {int(x) for x in re.findall(r"\d+", s)}


def illust_mismatch(row, rel):
    """삽화정리 안 상대경로 `rel` 이 이 지문 그림이 아니면 그 까닭, 맞으면 ''.

    매처(`data.illust_for`)와 **따로** 이름만 읽어 판정한다 — 매처가 틀리면
    같이 틀리지 않게.
    """
    rel = _nfc(rel).replace("\\", "/")
    parts = rel.split("/")
    folder, stem = "/".join(parts[:-1]), os.path.splitext(parts[-1])[0]
    lab = _nfc(row.get("label") or row.get("key"))
    cat = _nfc(row.get("category"))
    src = _nfc((row.get("source") or {}).get("file")).replace(" ", "")

    pno = _nfc(row.get("no")) or lab
    m = _MOCK.match(pno) or _MOCK.match(lab)
    if m:
        want = "%s년 %d월" % (m.group(1), int(m.group(2)))
        if not any(p.startswith(want) for p in parts[:-1]):
            return "회차 폴더가 %s 아님" % want
        g = _nfc(row.get("grade"))
        if g and re.match(r"고\d$", parts[0]) and parts[0] != g:
            return "학년 폴더가 %s 아님" % g
        if int(m.group(3)) not in _nums(stem):
            return "번호가 %d 아님" % int(m.group(3))
        return ""

    lu = re.search(r"(\d{1,2})\s*강", lab) or re.search(r"(\d{1,2})\s*강", cat)
    if lu:
        su = re.search(r"(\d{1,2})\s*강|Unit\s*(\d{1,2})", stem, re.I)
        if not su or int(su.group(1) or su.group(2)) != int(lu.group(1)):
            return "강이 %d강 아님" % int(lu.group(1))
        if src:
            light = "라이트" in src or "light" in src.lower()
            if light != ("light" in folder.lower() or "라이트" in folder):
                return "수특 Light 여부가 분석본과 다름"
            for a, b in _BOOKS:
                if a in src:
                    if b not in folder.replace(" ", ""):
                        return "교재 폴더가 %s 아님" % b
                    break
        ltail = lab[lab.find("강") + 1:] if "강" in lab else ""
        stail = stem[su.end():]
        if "분석" in lab or not ltail.strip():
            if not re.search(r"분석|analysis", stail, re.I):
                return "분석 그림 아님"
        elif _nums(ltail) != _nums(stail):
            return "번호가 %s 아님" % ltail.strip()
        return ""

    ls = re.search(r"(\d{1,2})\s*과", lab) or re.search(r"(\d{1,2})\s*과", cat)
    ln = re.search(r"(본문|RC|Reading|MR)\s*(\d{1,2})", lab)
    if ls and ln and not re.search(r"SL", lab + cat, re.I):
        # 교재(출판사+저자) — 분석본 파일 괄호 `YBM박1,2,3과` ↔ 폴더 `… YBM(박)`.
        # ⚠ 과·번호만 보면 **다른 교과서의 같은 과** 그림이 통과한다(배재2
        #   YBM박 3과 본문에 비상(황) 3과 MR 그림, 이 게이트 첫 실행에서 잡힘).
        pub = _PUB.search(src)
        if pub:
            want = pub.group(1) + pub.group(2)
            if want not in re.sub(r"[\s()]", "", folder):
                return "교과서 폴더가 %s 아님" % want
        ss = re.search(r"(\d{1,2})\s*과", stem)
        if not ss or int(ss.group(1)) != int(ls.group(1)):
            return "과가 %d과 아님" % int(ls.group(1))
        stail = stem[ss.end():]
        if (ln.group(1) == "MR") != ("MR" in stail.upper()):
            return "MR 여부 다름"
        if int(ln.group(2)) not in _nums(stail):
            return "번호가 %s%s 아님" % (ln.group(1), ln.group(2))
    return ""


def illust_names(rows, illust_dirs, report, log):
    roots = [_nfc(os.path.realpath(os.path.expanduser(d))) for d in illust_dirs or ()]
    outside, bad, n, unknown = [], [], 0, 0
    for r in rows:
        if r.get("kind") == "memtest" or not r.get("illust"):
            continue
        src = r.get("illust_src")
        if not src:
            unknown += 1
            continue
        n += 1
        real = _nfc(os.path.realpath(src))
        rel = next((real[len(t) + 1:] for t in roots
                    if real.startswith(t + os.sep)), None)
        lab = r.get("label") or r.get("key") or "?"
        if rel is None:
            outside.append(lab)
            continue
        why = illust_mismatch(r, rel)
        if why:
            bad.append("%s ← %s (%s)" % (lab, rel, why))
    if bad:
        report.fail("G-P16 삽화가 그 지문 것이 아니다 %d지문 — %s"
                    % (len(bad), " / ".join(bad[:6])))
    if outside:
        report.warn("G-P16 삽화정리 폴더 밖 그림(분석본·옛 책 링크) %d지문 — 맞는 "
                    "그림인지 볼 것: %s" % (len(outside), ", ".join(outside[:10])))
    if unknown:
        log("  G-P16 삽화 원본 기록 없는 지문 %d개 — build 를 다시 돌리면 대조한다"
            % unknown)
    if n and not bad:
        log("  G-P16 삽화 이름 대조 %d지문 — 어긋난 것 없음" % n)


# ══════════════════════════════════════════════════════════════════
# G-P17 분석본 원본(.indd) ↔ IDML
# ══════════════════════════════════════════════════════════════════
_AKEY = re.compile(r"분석본\s*(\d{1,2})\s*\(([^)]*)\)")
STALE_S = 3600


def _akey(name):
    m = _AKEY.search(_nfc(name))
    return (int(m.group(1)), re.sub(r"\s+", "", m.group(2))) if m else None


def _files(d, exts):
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return [os.path.join(d, f) for f in names
            if not f.startswith(".") and f.lower().endswith(exts)
            and os.path.isfile(os.path.join(d, f))]


def drive_dir_of(local):
    """`…/_idml/analysis/<학년대>/<학기>/<학교>` → 드라이브 분석본 같은 자리."""
    parts = _nfc(os.path.realpath(local)).split(os.sep)
    for i in range(len(parts) - 1):
        if parts[i] == "_idml" and parts[i + 1] == "analysis":
            return os.path.join(os.path.expanduser(DRIVE_ANALYSIS), *parts[i + 2:])
    return None


def compare_sources(local_dirs, indd_dirs, skip=()):
    """(빠진 원본 이름들, 옛 IDML 이름들)."""
    have = {}
    for d in local_dirs:
        for f in _files(d, (".idml", ".pdf")):
            k = _akey(os.path.basename(f))
            if k:
                have[k] = max(have.get(k, 0), os.stat(f).st_mtime)
    missing, stale = [], []
    for d in indd_dirs:
        for f in _files(d, (".indd",)):
            name = _nfc(os.path.basename(f))
            k = _akey(name)
            if not k or any(_nfc(s) in name for s in skip or ()):
                continue
            if k not in have:
                missing.append(name)
            elif os.stat(f).st_mtime > have[k] + STALE_S:
                stale.append(name)
    return sorted(missing), sorted(stale)


def analysis_sources(cfg, report, log):
    opt = cfg.section("options") or {}
    local = [d for d in (cfg.resolve(opt.get("analysis") or []) or [])
             if d and os.path.isdir(d)]
    indd = cfg.resolve(opt.get("analysis_indd") or [])
    if isinstance(indd, str):
        indd = [indd]
    if not indd:
        indd = [x for x in (drive_dir_of(d) for d in local) if x]
    # ⚠ 드라이브 폴더 이름은 NFD 로 올 수 있다 — 한 단계씩 NFC 로 맞춰 찾는다
    found = []
    for d in indd:
        real = _find_nfc(d)
        if real:
            found.append(real)
    if not local or not found:
        log("  G-P17 분석본 원본(.indd) 폴더를 못 찾아 대조 못 했다: %s"
            % ", ".join(indd) if indd else "  G-P17 분석본 폴더 설정 없음")
        return
    missing, stale = compare_sources(local, found, opt.get("analysis_skip") or ())
    if missing:
        report.fail("G-P17 드라이브에 있는 분석본이 IDML·PDF 로 안 뽑혔다 %d개 — "
                    "이 분석본 지문이 책에서 빠진다(쓰지 않는 것이면 config "
                    "`analysis_skip` 에 적을 것): %s" % (len(missing), ", ".join(missing)))
    if stale:
        report.warn("G-P17 원본 .indd 가 IDML 보다 나중에 고쳐졌다 %d개 — 다시 "
                    "뽑을 것: %s" % (len(stale), ", ".join(stale)))
    if not missing and not stale:
        log("  G-P17 분석본 원본 대조 — 빠진 것·옛것 없음")


def _find_nfc(path):
    if os.path.isdir(path):
        return path
    cur = os.sep
    for p in _nfc(path).split(os.sep)[1:]:
        try:
            hit = next((x for x in os.listdir(cur) if _nfc(x) == p), None)
        except OSError:
            return None
        if hit is None:
            return None
        cur = os.path.join(cur, hit)
    return cur if os.path.isdir(cur) else None
