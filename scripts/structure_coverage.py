"""헤더 형식 클러스터링 + 현행 파서 인식률 리포트.

입력: data_corpus/manuscript_structure/inventory.jsonl (extract_structure.py 산출)
출력:
  - docs/원고_구조_인벤토리.md            — 형식 변형 표 + 인식률 baseline + 다양성 후보
  - docs/원고_구조_인식률_baseline.json   — 리그레션 지표 (분류율 87.57% 스타일)

판정 경로 (engines/workbook/parser.py 를 import — 코드 복사·수정 없음):
  regex 경로  : _RE_BRACKET_NUM / _RE_HEADER_NUM / _RE_KOREAN_BRACKET
                (+ 옛 마더텅 정규화 경로 _RE_OLD_WB_NUM / _RE_OLD_WB_SOURCE)
  struct 경로 : _strip_manuscript_headers의 2차 구조 판정과 동일 조건
                (len≤40, 숫자 포함, 영단어<4, 다음 비빈줄이 본문)

핵심 지표 = regex 경로 인식률. 오늘(2026-07-06) 실조판 실패("1. p1-no.3과 추가지문")가
regex 경로 미인식이었으므로, 이 값이 파서 룰 보강 루프의 리그레션 지표다.

사용: python3 scripts/structure_coverage.py
"""
import datetime
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from engines.workbook.parser import (  # noqa: E402 — 현행 파서 판정 경로 그대로 사용
    _RE_BRACKET_NUM,
    _RE_HEADER_NUM,
    _RE_KOREAN_BRACKET,
    _RE_OLD_WB_NUM,
    _RE_OLD_WB_SOURCE,
)
from core.structure.header_detect import detect_from_candidates  # noqa: E402 — W31 구조 우선 인식기
from scripts.extract_structure import classify_line  # noqa: E402 — 후보 재검증 (규칙 단일화)

INV = os.path.join(_REPO, "data_corpus", "manuscript_structure", "inventory.jsonl")
DOC = os.path.join(_REPO, "docs", "원고_구조_인벤토리.md")
BASELINE = os.path.join(_REPO, "docs", "원고_구조_인식률_baseline.json")

_RE_ENG_WORD = re.compile(r"[A-Za-z]+")

# 발문(question stem) 라인 — "다음 글을 읽고 물음에 답하시오. [3과]" 류.
# 추출기(classify_line)의 넓은 그물이 잡지만, 이는 지문번호 '헤더'가 아니라
# 발문+출처 표기이므로 헤더 인식률 계산에서 분리한다 (별도 집계).
_RE_STEM = re.compile(
    r"(다음 글|다음 중|윗글|위 글|물음에 답|적절한 것|적절하지 않은|알맞은|"
    r"고르시오|고른 것|밑줄 친|어법상|문맥상|들어갈 말|일치하|주어진 글)"
)


def _eng_words(s):
    return len(_RE_ENG_WORD.findall(s))


def is_stem(t):
    return bool(_RE_STEM.search(t))


# ── 인식 판정 ───────────────────────────────────────────────────────────────

def recognize_regex(t):
    """현행 파서의 정규식 헤더 인식 경로 (형식 기반)."""
    if _RE_BRACKET_NUM.match(t) or _RE_HEADER_NUM.match(t) or _RE_KOREAN_BRACKET.match(t):
        return True
    # 옛 마더텅 형식은 _normalize_old_workbook_headers가 표준형으로 변환 → 인식 취급
    if _RE_OLD_WB_NUM.match(t) or _RE_OLD_WB_SOURCE.match(t):
        return True
    return False


def recognize_struct(t, body_next):
    """_is_passage_marker_struct와 동일 조건 (구조 기반 2차 판정)."""
    if not t or len(t) > 40:
        return False
    if not re.search(r"\d", t):
        return False
    if _eng_words(t) >= 4:
        return False
    return bool(body_next)


# ── 셰이프 정규화 ───────────────────────────────────────────────────────────

def shape_of(t):
    """헤더 원문 → 정규화 셰이프. 숫자→N, 공백 접기. (클러스터 키)"""
    s = re.sub(r"\d+", "N", t)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ── 메인 ────────────────────────────────────────────────────────────────────

def load_inventory():
    """path 기준 dedupe — 재시도로 중복 기록된 경우 성공(최신) 레코드 우선."""
    by_path = {}
    with open(INV) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            prev = by_path.get(rec["path"])
            if prev is None or (prev.get("error") and not rec.get("error")):
                by_path[rec["path"]] = rec
    return list(by_path.values())


def cluster(recs):
    """shape → {count, files, samples, regex_ok, struct_ok, v2_ok}

    v2_ok = W31 구조 우선 인식기(core/structure/header_detect)의 문서 단위
    판정 — 레코드의 헤더 후보 리스트를 문서 순으로 detect_from_candidates에
    넣어 발생(occurrence) 단위로 집계한다 (측정과 실전이 같은 코어).

    Returns: (clusters, stem_clusters, stem_fp) — 발문+출처 라인은 별도
    집계, stem_fp = 발문이 구조 신호만으로 헤더 승격된 오탐 발생 수.
    """
    clusters = {}
    stem_clusters = Counter()
    stem_fp = 0
    for r in recs:
        # 문서 단위 재구성: 후보 재검증(최신 규칙 통일) 후 문서 순 유지
        doc = []
        for h in r.get("headers", []):
            t, body_next = h["t"], h.get("body_next", False)
            if classify_line(t) != "header":
                continue
            doc.append((t, body_next, is_stem(t)))
        if not doc:
            continue
        det = detect_from_candidates(
            [{"t": t, "body_next": bn} for t, bn, _s in doc],
            legacy=recognize_regex)
        for idx, (t, body_next, stem) in enumerate(doc):
            v2_ok = idx in det.header_idx
            if stem:
                stem_clusters[shape_of(t)] += 1
                if v2_ok and not recognize_regex(t):
                    stem_fp += 1
                continue
            sh = shape_of(t)
            c = clusters.setdefault(sh, {
                "count": 0, "files": set(), "samples": [],
                "regex_ok": recognize_regex(t),
                "struct_ok": 0,
                "v2_ok": 0,
            })
            c["count"] += 1
            c["files"].add(r["path"])
            if len(c["samples"]) < 3 and t not in c["samples"]:
                c["samples"].append(t)
            if recognize_struct(t, body_next):
                c["struct_ok"] += 1
            if v2_ok:
                c["v2_ok"] += 1
    return clusters, stem_clusters, stem_fp


def _feature_set(r):
    """다양성 선정용 구조 시그니처 피처 집합."""
    feats = set()
    feats.add("ext:%s" % r.get("ext"))
    feats.add("table:%s" % r.get("has_table"))
    feats.add("ul:%s" % r.get("has_underline"))
    for h in r.get("headers", [])[:60]:
        if classify_line(h["t"]) != "header" or is_stem(h["t"]):
            continue
        feats.add("h:" + shape_of(h["t"]))
    for s in r.get("section_markers", [])[:20]:
        feats.add("s:" + shape_of(s))
    return feats


def pick_diverse(recs, n=15):
    """워크북 계열 중 구조 시그니처가 최대한 다른 파일 n개 — greedy farthest-first.

    시드 = 오늘 실패한 부교재 원고(jobs_06f4b2c2)의 대표 파일 (반드시 포함).
    """
    def _valid_headers(r):
        return [h for h in r.get("headers", [])
                if classify_line(h["t"]) == "header" and not is_stem(h["t"])]

    pool = [r for r in recs
            if r.get("wb_family") and not r.get("error")
            and (_valid_headers(r) or r.get("section_markers"))]
    feats = {r["path"]: _feature_set(r) for r in pool}

    def jdist(a, b):
        u = len(a | b)
        return 1.0 if not u else 1.0 - len(a & b) / u

    picked = []
    seed = [r for r in pool if r.get("root") == "jobs_06f4b2c2_부교재"]
    if seed:
        # 실패 헤더("N. pN-no.N과 추가지문")를 실제로 가진 파일 우선
        def has_fail_shape(r):
            return any("과 추가지문" in h["t"] for h in r.get("headers", []))
        seed.sort(key=lambda r: (not has_fail_shape(r), -len(feats[r["path"]])))
        picked.append(seed[0])
    while len(picked) < n and len(picked) < len(pool):
        best, best_d = None, -1.0
        for r in pool:
            if any(p["path"] == r["path"] for p in picked):
                continue
            d = min(jdist(feats[r["path"]], feats[p["path"]]) for p in picked) \
                if picked else 1.0
            # 동률이면 헤더 수 많은(정보량 큰) 파일
            if d > best_d or (d == best_d and best is not None
                              and len(feats[r["path"]]) > len(feats[best["path"]])):
                best, best_d = r, d
        if best is None:
            break
        picked.append(best)
    return picked, feats


def _why_different(r, picked_before, feats):
    """이 파일이 왜 다른지 한 줄 설명."""
    mine = feats[r["path"]]
    prev = set()
    for p in picked_before:
        prev |= feats[p["path"]]
    uniq = mine - prev
    h_shapes = sorted(s[2:] for s in uniq if s.startswith("h:"))[:2]
    s_shapes = sorted(s[2:] for s in uniq if s.startswith("s:"))[:1]
    bits = []
    if h_shapes:
        bits.append("헤더 셰이프 " + " / ".join("`%s`" % x for x in h_shapes))
    if s_shapes:
        bits.append("섹션 " + " / ".join("`%s`" % x for x in s_shapes))
    for tag, label in (("ext:", "확장자"), ("table:True", "표 포함"),
                       ("ul:True", "밑줄 포함")):
        for u in uniq:
            if u.startswith(tag) if tag.endswith(":") else u == tag:
                bits.append(label + (" " + u.split(":")[1] if tag.endswith(":") else ""))
                break
    return ", ".join(bits) if bits else "잔여 조합 중 기존 선정과 최대 거리"


def main():
    recs = load_inventory()
    ok_recs = [r for r in recs if not r.get("error")]
    err_recs = [r for r in recs if r.get("error")]

    clusters, stem_clusters, stem_fp = cluster(ok_recs)
    total_occ = sum(c["count"] for c in clusters.values())
    regex_occ = sum(c["count"] for c in clusters.values() if c["regex_ok"])
    struct_extra_occ = sum(
        c["struct_ok"] for c in clusters.values() if not c["regex_ok"]
    )
    regex_rate = 100.0 * regex_occ / total_occ if total_occ else 0.0
    combined_rate = (100.0 * (regex_occ + struct_extra_occ) / total_occ
                     if total_occ else 0.0)
    # W31 구조 우선 인식기 (문서 단위 발생 집계)
    v2_occ = sum(c["v2_ok"] for c in clusters.values())
    v2_rate = 100.0 * v2_occ / total_occ if total_occ else 0.0

    unrecognized = sorted(
        ((sh, c) for sh, c in clusters.items() if not c["regex_ok"]),
        key=lambda x: -x[1]["count"],
    )
    # 구조 인식기가 새로 잡은 셰이프 (정규식 미인식 → v2 인식)
    v2_newly = sorted(
        ((sh, c) for sh, c in clusters.items()
         if not c["regex_ok"] and c["v2_ok"] > 0),
        key=lambda x: -x[1]["v2_ok"],
    )
    # v2 기준 잔여 미인식 (발생 단위)
    v2_unrec = sorted(
        ((sh, c) for sh, c in clusters.items() if c["v2_ok"] < c["count"]),
        key=lambda x: -(x[1]["count"] - x[1]["v2_ok"]),
    )

    # 계열별 인식률
    by_series = defaultdict(lambda: [0, 0])  # series -> [ok, total]
    for r in ok_recs:
        for h in r.get("headers", []):
            if classify_line(h["t"]) != "header" or is_stem(h["t"]):
                continue
            s = r.get("series") or "?"
            by_series[s][1] += 1
            if recognize_regex(h["t"]):
                by_series[s][0] += 1

    # 루트별 파일 분포
    by_root = Counter(r.get("root") for r in recs)
    by_ext = Counter(r.get("ext") for r in recs)

    diverse, feats = pick_diverse(ok_recs, n=15)

    # 파서 상태 기록 — 인식률은 '측정 시점 워킹트리의 파서'에 대한 값.
    # (2026-07-06: W11 수리 트랙이 _RE_HEADER_NUM에 한글 꼬리 허용을 미커밋 상태로
    #  반영 → 오늘 실패 헤더가 워킹트리 기준으로는 인식됨. 커밋 전후 수치 차이 가능.)
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO,
                              capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "engines/workbook/parser.py"],
            cwd=_REPO, capture_output=True, text=True).stdout.strip())
    except Exception:
        head, dirty = "?", None
    fail_example = "1. p1-no.3과 추가지문"  # 2026-07-06 실조판 실패 실물 헤더
    fail_recognized = recognize_regex(fail_example)
    # 2026-07-19 실조판 실패(job 376b34d0) 실물 헤더 — 파서 정규식은
    # 매치했으나 플랜 계층(_HEADER_PATTERNS)이 미인식(계층별 다른 눈).
    # 구조 인식기는 문서 문맥(직후 영어 본문)으로 계층 무관 인식해야 한다.
    fail_0719 = "1. L1-p. 13 본문 1"
    fail_0719_regex = recognize_regex(fail_0719)
    det_0719 = detect_from_candidates(
        [{"t": "1. L1-p. 13 본문 1", "body_next": True},
         {"t": "2. L1-p. 14 본문 2", "body_next": True}],
        legacy=recognize_regex)
    fail_0719_v2 = 0 in det_0719.header_idx and 1 in det_0719.header_idx

    # ── baseline JSON ──
    baseline = {
        "generated": datetime.date.today().isoformat(),
        "parser_git_head": head,
        "parser_worktree_dirty": dirty,
        "fail_20260706_header": fail_example,
        "fail_20260706_recognized": fail_recognized,
        "inventory_files": len(recs),
        "inventory_errors": len(err_recs),
        "header_occurrences": total_occ,
        "unique_shapes": len(clusters),
        "regex_recognition_rate_pct": round(regex_rate, 2),
        "regex_plus_struct_rate_pct": round(combined_rate, 2),
        "unrecognized_shapes": len(unrecognized),
        # ── W31 구조 우선 인식기 (문서 단위) — 리그레션 지표 ──
        "struct_v2_rate_pct": round(v2_rate, 2),
        "struct_v2_recognized_occ": v2_occ,
        "struct_v2_stem_fp": stem_fp,
        "struct_v2_unrecognized_occ": total_occ - v2_occ,
        "fail_20260719_header": fail_0719,
        "fail_20260719_regex_recognized": fail_0719_regex,
        "fail_20260719_v2_recognized": fail_0719_v2,
        "struct_v2_top_newly_recognized": [
            {"shape": sh, "v2_ok": c["v2_ok"], "count": c["count"],
             "sample": c["samples"][0]}
            for sh, c in v2_newly[:20]
        ],
        "struct_v2_top_unrecognized": [
            {"shape": sh, "missed": c["count"] - c["v2_ok"],
             "count": c["count"], "sample": c["samples"][0]}
            for sh, c in v2_unrec[:20]
        ],
        "stem_occurrences": sum(stem_clusters.values()),
        "stem_shapes": len(stem_clusters),
        "top_unrecognized": [
            {"shape": sh, "count": c["count"], "files": len(c["files"]),
             "sample": c["samples"][0]}
            for sh, c in unrecognized[:20]
        ],
        "by_series_regex_rate_pct": {
            s: round(100.0 * ok / tot, 2)
            for s, (ok, tot) in sorted(by_series.items()) if tot
        },
    }
    with open(BASELINE, "w") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)

    # ── Markdown 리포트 ──
    top_shapes = sorted(clusters.items(), key=lambda x: -x[1]["count"])
    lines = []
    w = lines.append
    w("# 원고 구조 인벤토리 — 헤더 형식 변형 + 파서 인식률 baseline")
    w("")
    w("생성: %s / `scripts/extract_structure.py` → `scripts/structure_coverage.py`"
      % baseline["generated"])
    w("")
    w("원본 데이터: `data_corpus/manuscript_structure/inventory.jsonl` (gitignore, "
      "문서당 1레코드). 재생성: `python3 scripts/extract_structure.py` (재개 가능) → "
      "`python3 scripts/structure_coverage.py`.")
    w("")
    w("## 스캔 규모")
    w("")
    w("| 항목 | 값 |")
    w("|---|---|")
    w("| 스캔 문서 수 | %d (에러 %d) |" % (len(recs), len(err_recs)))
    w("| 지문 헤더 후보 발생 수 | %d |" % total_occ)
    w("| 헤더 형식 변형(셰이프) 수 | %d |" % len(clusters))
    w("| (참고) 발문+출처 라인 — 헤더 아님, 별도 집계 | %d건 / %d셰이프 |"
      % (sum(stem_clusters.values()), len(stem_clusters)))
    for root, n in by_root.most_common():
        w("| — %s | %d |" % (root, n))
    w("| 확장자 | %s |" % ", ".join("%s %d" % (e, n) for e, n in by_ext.most_common()))
    w("")
    w("## 인식률 baseline (리그레션 지표)")
    w("")
    w("| 지표 | 값 |")
    w("|---|---|")
    w("| **정규식 경로 인식률** (`_RE_HEADER_NUM` 계열) | **%.2f%%** |" % regex_rate)
    w("| 정규식+구조 판정 결합 인식률 | %.2f%% |" % combined_rate)
    w("| **구조 우선 인식기(W31) 인식률** (문서 단위, `core/structure/"
      "header_detect`) | **%.2f%%** |" % v2_rate)
    w("| 구조 인식기 발문 오탐 (stem→헤더 승격) | %d건 / 발문 %d건 |"
      % (stem_fp, sum(stem_clusters.values())))
    w("| 미인식 셰이프 수 | %d |" % len(unrecognized))
    w("")
    w("### 구조 우선 인식기가 새로 잡은 셰이프 (정규식 미인식 → v2 인식)")
    w("")
    w("| 셰이프 | v2 인식/전체 | 예시 원문 |")
    w("|---|---|---|")
    for sh, c in v2_newly[:25]:
        w("| `%s` | %d/%d | `%s` |"
          % (sh.replace("|", "\\|"), c["v2_ok"], c["count"],
             c["samples"][0].replace("|", "\\|")))
    w("")
    w("### 구조 우선 인식기 기준 잔여 미인식 톱")
    w("")
    w("| 셰이프 | 미인식/전체 | 예시 원문 |")
    w("|---|---|---|")
    for sh, c in v2_unrec[:25]:
        w("| `%s` | %d/%d | `%s` |"
          % (sh.replace("|", "\\|"), c["count"] - c["v2_ok"], c["count"],
             c["samples"][0].replace("|", "\\|")))
    w("")
    w("정규식 경로 = `_RE_BRACKET_NUM` / `_RE_HEADER_NUM` / `_RE_KOREAN_BRACKET` "
      "(+옛 마더텅 `N번`/`YY년 M월 K번` 정규화). 구조 판정 = "
      "`_is_passage_marker_struct` 동일 조건. baseline JSON: "
      "`docs/원고_구조_인식률_baseline.json` — 파서 룰 보강 후 이 스크립트를 재실행해 "
      "인식률이 오르는지(그리고 기존 인식 셰이프가 깨지지 않는지) 확인한다.")
    w("")
    w("측정 시점 파서 상태: HEAD `%s`%s. 오늘(2026-07-06) 실조판 실패 헤더 `%s` → "
      "현재 파서 기준 **%s**."
      % (head, " + parser.py 워킹트리 수정 있음 (W11 수리 트랙)" if dirty else "",
         fail_example,
         "인식됨 (수리 트랙 보강 반영)" if fail_recognized else "미인식 (보강 필요)"))
    w("")
    w("### 교재 계열별 정규식 인식률")
    w("")
    w("| 계열 | 인식/전체 | 인식률 |")
    w("|---|---|---|")
    for s, (ok, tot) in sorted(by_series.items(), key=lambda x: -x[1][1]):
        if tot:
            w("| %s | %d/%d | %.1f%% |" % (s, ok, tot, 100.0 * ok / tot))
    w("")
    w("## 헤더 형식 변형 (빈도순 상위)")
    w("")
    w("숫자→`N`, 공백 접기로 정규화한 셰이프. ✅=정규식 인식, 🟡=구조 판정만 인식, "
      "❌=미인식.")
    w("")
    w("| 셰이프 | 빈도 | 파일수 | 판정 | 예시 원문 |")
    w("|---|---|---|---|---|")
    for sh, c in top_shapes[:60]:
        if c["regex_ok"]:
            mark = "✅"
        elif c["struct_ok"] > 0:
            mark = "🟡"
        else:
            mark = "❌"
        w("| `%s` | %d | %d | %s | `%s` |"
          % (sh.replace("|", "\\|"), c["count"], len(c["files"]), mark,
             c["samples"][0].replace("|", "\\|")))
    w("")
    w("## 미인식 형식 톱 목록 (= 파서 룰 보강 로드맵)")
    w("")
    w("| # | 셰이프 | 빈도 | 파일수 | 구조판정 구제 | 예시 원문 |")
    w("|---|---|---|---|---|---|")
    for i, (sh, c) in enumerate(unrecognized[:30], 1):
        w("| %d | `%s` | %d | %d | %d/%d | `%s` |"
          % (i, sh.replace("|", "\\|"), c["count"], len(c["files"]),
             c["struct_ok"], c["count"], c["samples"][0].replace("|", "\\|")))
    w("")
    w("오늘(2026-07-06) 실조판 실패 형식 `N. pN-no.N과 추가지문` "
      "(`1. p1-no.3과 추가지문`, jobs/06f4b2c2 부교재)은 이 baseline의 대표 실패 "
      "사례다 — 현재 파서 기준 %s. (전수 인벤토리에서 이 계열 셰이프는 "
      "`N. pN-no.N과 추가지문` %d건 + `[N과 추가지문]` 등 총 %d건 발견.)"
      % ("**인식됨** (W11 수리 트랙 보강이 워킹트리에 반영됨)"
         if fail_recognized else "**미인식** (룰 보강 필요)",
         clusters.get("N. pN-no.N과 추가지문", {}).get("count", 0),
         sum(c["count"] for sh, c in clusters.items() if "추가지문" in sh)))
    w("")
    w("## 반복 루프용 다양성 후보 (%d개)" % len(diverse))
    w("")
    w("구조 시그니처(헤더 셰이프 + 섹션 마커 + 확장자/표/밑줄) Jaccard 거리 기준 "
      "greedy farthest-first 선정. 1번(오늘 실패한 부교재 형식)부터 순서대로 "
      "\"다양한 원고 반복 루프\"에 투입한다.")
    w("")
    for i, r in enumerate(diverse, 1):
        why = ("**오늘 실패한 부교재 원고** — 미인식 헤더 `N. pN-no.N과 추가지문` 실물"
               if i == 1 and r.get("root") == "jobs_06f4b2c2_부교재"
               else _why_different(r, diverse[:i - 1], feats))
        w("%d. `%s`" % (i, r["path"]))
        w("   - %s | %s | %s" % (r.get("series"), r.get("ext"), why))
    w("")
    with open(DOC, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("문서: %s" % DOC)
    print("baseline: %s" % BASELINE)
    print("파일 %d / 헤더 %d / 셰이프 %d / 정규식 인식률 %.2f%% / 결합 %.2f%%"
          % (len(recs), total_occ, len(clusters), regex_rate, combined_rate))
    print("구조 우선 인식기(W31): %.2f%% (%d/%d) / 발문 오탐 %d / "
          "0719 실패 헤더 인식 %s"
          % (v2_rate, v2_occ, total_occ, stem_fp, fail_0719_v2))
    print("미인식 톱5 (정규식):")
    for sh, c in unrecognized[:5]:
        print("  %-40s %5d  예) %s" % (sh, c["count"], c["samples"][0]))
    print("미인식 톱5 (구조 인식기):")
    for sh, c in v2_unrec[:5]:
        print("  %-40s %5d  예) %s"
              % (sh, c["count"] - c["v2_ok"], c["samples"][0]))


if __name__ == "__main__":
    main()
