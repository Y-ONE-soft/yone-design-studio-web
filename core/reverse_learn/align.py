"""완성 조판본 ↔ 원고(플랜) 단락 단위 정렬 (역학습 인프라 — W44).

완성본(사람 손마무리 최종 .indd)의 덤프(core.inspect.dump_indd)와, 같은 원고로
만든 현행 파이프라인의 플랜(engines.workbook_v2.plan.steps_to_plan)을 단락 단위로
정렬한다. 정렬된 각 쌍은 "이 원고 단락 → 완성본에서 실제로 적용된 스타일"이라는
정답 한 줄이 된다.

정렬 전략 (patience-diff 계열 — 순서 제약을 앵커로 강제):
  1) 양쪽 정규화 키(_norm_key — core.inspect와 같은 의미론) 계산
  2) 양쪽에서 **유일한** 키가 서로 같은 단락 = 앵커. 앵커에 LIS를 걸어
     단조(monotone) 정렬만 남긴다.
  3) 앵커 사이 구간(gap)만 대상으로 (a) 키 완전일치 → (b) 퍼지 매칭
     (core.passage_match — 긴 지문 / difflib — 짧은 단락) 순으로 채운다.
  4) 각 쌍에 신뢰도(conf). 완성본은 사람이 문장을 고치거나 통째로 더/빼기
     때문에 정렬 실패는 정상 — 낮은 신뢰도는 호출자가 버린다.

이 모듈은 InDesign에 의존하지 않는다 (덤프 JSON을 입력으로 받는다).
"""
import difflib
import re
import unicodedata

from core.passage_match.matcher import build_idf, fingerprint, pair_score

# core.inspect._norm_key와 같은 의미론 (JSX 치환·공백 변형 흡수)
_RE_KEEP = re.compile(r"[^0-9a-z가-힣①-⑤ⓐ-ⓔ]")

# 퍼지 매칭 채택 임계 (낮은 쪽은 호출자가 conf로 다시 거른다)
TH_FUZZY = 0.72
TH_LONG_SHINGLE = 0.45      # 긴 단락: 셔글 containment
MIN_KEY_LEN = 4             # 이보다 짧은 키는 앵커로 쓰지 않는다 (흔한 잡음)
GAP_BAND = 400              # 앵커 사이 gap이 이보다 크면 퍼지 탐색 범위 제한


def norm_key(text):
    t = unicodedata.normalize("NFC", text or "").lower()
    return _RE_KEEP.sub("", t)


def flatten_plan(plan):
    """steps_to_plan 결과 → [{"step","unit","idx","text","style","runs"}] (문서 순서)."""
    out = []
    for flow in plan.get("flows", []):
        step = flow.get("step")
        for ui, unit in enumerate(flow.get("units", [])):
            paras = unit if isinstance(unit, list) else (unit.get("paras") or [])
            for pi, p in enumerate(paras):
                if not isinstance(p, dict):
                    continue
                out.append({
                    "step": step,
                    "unit": ui,
                    "idx": pi,
                    "text": p.get("t") or "",
                    "style": p.get("s") or "",
                    "runs": p.get("runs") or [],
                })
    return out


def flatten_dump(dump, skip_empty=True):
    """덤프 JSON → [{"story","idx","text","style","overflow"}] (문서 순서)."""
    out = []
    for story in dump.get("stories", []):
        si = story.get("idx")
        for pi, p in enumerate(story.get("paragraphs", [])):
            text = (p.get("t") or "").replace("\r", "").replace("\n", "").strip()
            if skip_empty and not norm_key(text):
                continue
            out.append({
                "story": si,
                "idx": pi,
                "text": text,
                "style": p.get("s") or "",
                "overflow": bool(story.get("overflow")),
            })
    return out


def _lis(pairs):
    """(a_idx, b_idx) 리스트에서 b가 증가하는 최장 부분수열 (O(n^2) — n은 앵커 수)."""
    if not pairs:
        return []
    n = len(pairs)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if pairs[j][1] < pairs[i][1] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    k = max(range(n), key=lambda i: best[i])
    seq = []
    while k >= 0:
        seq.append(pairs[k])
        k = prev[k]
    return list(reversed(seq))


def _fuzzy(fa, ta, fb, tb, idf):
    """(score) — 긴 단락은 셔글/토큰 containment, 짧은 단락은 difflib."""
    if fa is not None and fb is not None and not (fa.is_tiny() or fb.is_tiny()):
        sc = pair_score(fa, fb, idf)
        if sc.min_shingles >= 4:
            return max(sc.shingle_cont, sc.token_cont * 0.9)
        return sc.token_cont * 0.9
    ka, kb = norm_key(ta), norm_key(tb)
    if not ka or not kb:
        return 0.0
    return difflib.SequenceMatcher(None, ka, kb).ratio()


def align(plan_paras, dump_paras, th_fuzzy=TH_FUZZY):
    """플랜 단락 ↔ 덤프 단락 정렬.

    반환: {"pairs": [{"p": i, "g": j, "conf": float, "how": str}],
           "stats": {...}}  (i = plan_paras 인덱스, j = dump_paras 인덱스)
    """
    pk = [norm_key(p["text"]) for p in plan_paras]
    gk = [norm_key(g["text"]) for g in dump_paras]

    def _uniq(keys):
        cnt = {}
        for k in keys:
            if len(k) >= MIN_KEY_LEN:
                cnt[k] = cnt.get(k, 0) + 1
        return {k for k, c in cnt.items() if c == 1}

    up, ug = _uniq(pk), _uniq(gk)
    gpos = {}
    for j, k in enumerate(gk):
        gpos.setdefault(k, []).append(j)

    cand = []
    for i, k in enumerate(pk):
        if k in up and k in ug:
            cand.append((i, gpos[k][0]))
    anchors = _lis(cand)

    pairs = [{"p": i, "g": j, "conf": 1.0, "how": "anchor"} for i, j in anchors]

    # gap 채우기 ─ 앵커 사이 구간만 (순서 제약 자동 보장)
    bounds = [(-1, -1)] + anchors + [(len(plan_paras), len(dump_paras))]
    idf = None
    fps_p = {}
    fps_g = {}

    def _fp(cache, arr, n):
        if n not in cache:
            try:
                cache[n] = fingerprint(arr[n]["text"])
            except Exception:                                   # noqa: BLE001
                cache[n] = None
        return cache[n]

    for b in range(len(bounds) - 1):
        pi0, gi0 = bounds[b]
        pi1, gi1 = bounds[b + 1]
        p_range = list(range(pi0 + 1, pi1))
        g_range = list(range(gi0 + 1, gi1))
        if not p_range or not g_range:
            continue
        if len(g_range) > GAP_BAND:
            g_range = g_range[:GAP_BAND]
        used = set()
        # (a) 키 완전일치 (구간 안, 순서 유지)
        exact = []
        gi = 0
        for i in p_range:
            k = pk[i]
            if len(k) < MIN_KEY_LEN:
                continue
            for jj in range(gi, len(g_range)):
                j = g_range[jj]
                if gk[j] == k:
                    exact.append((i, j))
                    gi = jj + 1
                    used.add(j)
                    break
        for i, j in exact:
            pairs.append({"p": i, "g": j, "conf": 0.9, "how": "key"})
        # (b) 퍼지 — 남은 자리만, 구간 안 순서 유지
        done_p = {i for i, _ in exact}
        if idf is None:
            sample = [_fp(fps_p, plan_paras, i) for i in p_range[:200]]
            sample += [_fp(fps_g, dump_paras, j) for j in g_range[:200]]
            idf = build_idf([f for f in sample if f is not None]) or None
        sub_bounds = [(pi0, gi0)] + exact + [(pi1, gi1)]
        for sb in range(len(sub_bounds) - 1):
            sp0, sg0 = sub_bounds[sb]
            sp1, sg1 = sub_bounds[sb + 1]
            cands_g = [j for j in range(sg0 + 1, sg1) if j not in used]
            last_j = sg0
            for i in range(sp0 + 1, sp1):
                if i in done_p:
                    continue
                fa = _fp(fps_p, plan_paras, i)
                best, bj = 0.0, -1
                for j in cands_g:
                    if j <= last_j:
                        continue
                    fb = _fp(fps_g, dump_paras, j)
                    s = _fuzzy(fa, plan_paras[i]["text"], fb,
                               dump_paras[j]["text"], idf)
                    if s > best:
                        best, bj = s, j
                    if best >= 0.98:
                        break
                if bj >= 0 and best >= th_fuzzy:
                    pairs.append({"p": i, "g": bj, "conf": round(best, 3),
                                  "how": "fuzzy"})
                    used.add(bj)
                    last_j = bj

    pairs.sort(key=lambda d: d["p"])
    n_p = len(plan_paras)
    stats = _stats(pairs, n_p, len(dump_paras))
    return {"pairs": pairs, "stats": stats}


def _stats(pairs, n_p, n_g):
    return {
        "plan_paragraphs": n_p,
        "dump_paragraphs": n_g,
        "aligned": len(pairs),
        "anchor": sum(1 for x in pairs if x["how"] == "anchor"),
        "key": sum(1 for x in pairs if x["how"] == "key"),
        "fuzzy": sum(1 for x in pairs if x["how"] == "fuzzy"),
        "align_rate": round(len(pairs) / n_p, 4) if n_p else 0.0,
    }


def _norm_marker(s):
    return norm_key(s)


def story_scope(dump, step_targets, marker_max_paras=2):
    """플랜 target(stepStoryMap) → 스텝별 허용 스토리 집합 (W46 권고 ④).

    같은 본문이 여러 스텝(step1_a2/b1 등)에 재등장하면 "키 득표"만으로는
    스텝↔스토리 대응이 겹쳐(교차오염) 앞 스텝이 뒤 스텝의 스토리를 선점한다.
    조판 계약(step_map.json)의 target은 각 스텝이 **어느 지면에** 놓이는지를
    이미 알고 있으므로, 그 지면에 속한 스토리로 후보를 먼저 좁힌다.

    - target["marker"] : 그 마커 텍스트만 담은 짧은 스토리가 놓인 페이지들
      (완성본은 페이지가 늘고 줄기 때문에 target["page"] 번호는 쓰지 않는다).
    - target["master"] : 페이지 마스터 이름의 접두("O" → "O-마스터").

    반환: {step: set(story_idx)} — 근거를 못 찾은 스텝은 키를 만들지 않는다
    (호출자는 그런 스텝에서 기존 득표 방식으로 폴백한다).
    """
    page_master = {str(p.get("p")): (p.get("m") or "")
                   for p in (dump.get("pages") or [])}
    st_pages, st_masters = {}, {}
    marker_pages = {}          # norm(marker) → set(page)
    for st in dump.get("stories") or []:
        sidx = st.get("idx")
        pgs = [str(x) for x in (st.get("pg") or [])]
        st_pages[sidx] = set(pgs)
        st_masters[sidx] = {page_master.get(p, "") for p in pgs}
        paras = [p for p in (st.get("paragraphs") or [])
                 if norm_key(p.get("t") or "")]
        if 0 < len(paras) <= marker_max_paras:
            k = norm_key(paras[0].get("t") or "")
            if 2 <= len(k) <= 24:
                marker_pages.setdefault(k, set()).update(pgs)

    def _pages_for(markers):
        # (1) 마커 완전일치 우선 — "어휘 선택 1"/"어휘 선택 2" 구분 보존
        for m in markers:
            k = _norm_marker(m)
            if k and marker_pages.get(k):
                return set(marker_pages[k])
        # (2) 접두 일치 폴백 (계열별 마커 표기 차: "어법 선택"/"어법 수정")
        for m in markers:
            k = _norm_marker(m)
            if not k:
                continue
            hit = set()
            for mk, pgs in marker_pages.items():
                if (mk.startswith(k) or k.startswith(mk)) \
                        and abs(len(mk) - len(k)) <= 2:
                    hit |= pgs
            if hit:
                return hit
        return set()

    scope = {}
    for step, target in (step_targets or {}).items():
        if not isinstance(target, dict):
            continue
        masters = target.get("masters") or (
            [target["master"]] if target.get("master") else [])
        if masters:
            for master in masters:
                allow = {s for s, ms in st_masters.items()
                         if any(m.startswith(master) for m in ms if m)}
                if allow:
                    scope[step] = allow
                    break
            continue
        markers = target.get("markers") or (
            [target["marker"]] if target.get("marker") else [])
        pages = _pages_for(markers)
        if pages:
            scope[step] = {s for s, pg in st_pages.items() if pg & pages}
    return scope


def align_document(plan_paras, dump_paras, th_fuzzy=TH_FUZZY,
                   min_story_hits=3, step_stories=None):
    """문서 전체 정렬 — 스텝(플로우)별로 대응 스토리를 먼저 고르고 정렬.

    조판 결과의 스토리 순서(문서 배치 순서)와 플랜의 스텝 순서는 다르므로
    전역 단조 정렬을 그대로 걸면 대부분의 스텝이 버려진다. 스텝 ↔ 스토리
    대응(키 완전일치 득표)을 먼저 잡고, 그 안에서만 단조 정렬한다.

    step_stories: {step: set(story_idx)} — story_scope()가 플랜 target으로
        만든 스텝별 허용 스토리. 주어지면 득표 후보를 여기로 **먼저 좁힌다**
        (교차오염 차단). 교집합이 비면 기존 득표 결과로 폴백한다.
    """
    gk = [norm_key(g["text"]) for g in dump_paras]
    by_story = {}
    for j, g in enumerate(dump_paras):
        by_story.setdefault(g["story"], []).append(j)
    key_story = {}
    for j, k in enumerate(gk):
        if len(k) >= MIN_KEY_LEN:
            key_story.setdefault(k, set()).add(dump_paras[j]["story"])

    steps = []
    order = []
    for i, p in enumerate(plan_paras):
        if not order or order[-1] != p["step"]:
            order.append(p["step"])
            steps.append((p["step"], []))
        steps[-1][1].append(i)

    pairs = []
    step_stats = []
    taken = set()
    for step, idxs in steps:
        votes = {}
        for i in idxs:
            k = norm_key(plan_paras[i]["text"])
            if len(k) < MIN_KEY_LEN:
                continue
            for s in key_story.get(k, ()):
                votes[s] = votes.get(s, 0) + 1
        cand = sorted([s for s, v in votes.items() if v >= min_story_hits],
                      key=lambda s: -votes[s])
        # 상위 득표 스토리들(같은 스텝이 여러 스토리에 흐르는 경우 포함).
        # 임계: 최다 득표의 15% 이상 — 잡음 스토리 배제.
        # W46: 플랜 target으로 지면이 특정되면 그 스토리로 먼저 좁힌다.
        scope_used = ""
        allow = (step_stories or {}).get(step)
        if allow:
            narrowed = [s for s in cand if s in allow]
            if narrowed:
                cand, scope_used = narrowed, "target"
            else:
                scope_used = "target_empty"
        if not cand:
            step_stats.append({"step": step, "stories": [], "aligned": 0,
                               "plan_paragraphs": len(idxs),
                               "scope": scope_used})
            continue
        top = votes[cand[0]]
        chosen = [s for s in cand if votes[s] >= max(min_story_hits,
                                                     int(top * 0.15))]
        gidx = sorted(j for s in chosen for j in by_story.get(s, [])
                      if j not in taken)
        sub_p = [plan_paras[i] for i in idxs]
        sub_g = [dump_paras[j] for j in gidx]
        res = align(sub_p, sub_g, th_fuzzy=th_fuzzy)
        for x in res["pairs"]:
            gj = gidx[x["g"]]
            taken.add(gj)
            pairs.append({"p": idxs[x["p"]], "g": gj, "conf": x["conf"],
                          "how": x["how"]})
        st = dict(res["stats"])
        st["step"] = step
        st["stories"] = chosen
        st["scope"] = scope_used
        step_stats.append(st)

    pairs.sort(key=lambda d: d["p"])
    stats = _stats(pairs, len(plan_paras), len(dump_paras))
    stats["steps"] = step_stats
    return {"pairs": pairs, "stats": stats}
