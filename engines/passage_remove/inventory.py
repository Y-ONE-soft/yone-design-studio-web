# -*- coding: utf-8 -*-
"""조판된 워크북 전체(C) dump → 지문 인벤토리 (W26 2단계).

dump_stories.jsx 산출(dump JSON)을 받아 스토리를 지문 유닛으로 분해하고,
core.passage_match 매처로 섹션 간 같은 지문을 그룹핑한다.

유닛 추출 3모드:
  1. 헤더 스토리: "[20]" / "{20}" / "1. p2-no.20" 구분자 단락으로 분할
  2. step3 스토리: 발문(번호 스타일) 단락에서 문제 블록 분할
  3. 무헤더 흐름 스토리 (C2 빈칸/어법, B1 OX, A1 하단 등): 시드 그룹에
     단락별 배정(assignment) — containment argmax + 마진, 저신호 단락은
     직전 런에 부착

순수 파이썬 (InDesign 무관) — 오프라인 테스트 가능.
"""

from __future__ import annotations

import re

from core.passage_match import (
    fingerprint, build_idf, group_fingerprints,
)

# ── 헤더 패턴 (조판 후 형태 — 원고 세그먼트와 달리 {N} 정규화형 포함) ────────
_RE_HEAD_BRACKET = re.compile(r"^\s*\[(\d+(?:\s*~\s*\d+)?)\]\s*$")
_RE_HEAD_BRACE = re.compile(r"^\s*\{(\d+(?:\s*~\s*\d+)?)\}\s*$")
_RE_HEAD_FULL = re.compile(
    r"^\s*(?:\d+\s*[\.\)]\s*)?"
    r"(?:L\d+(?:\s*[-–—]\s*(?:p\.?\d+|본문\d+))?|p\.?\d+|U\d+)"
    r"\s*[-–—\.]?\s*"
    r"(?:no\.\s*|[A-Za-z]+\.?\s*)?"
    r"(\d+(?:\s*~\s*\d+)?)?"
    r"(?:\s*[가-힣][가-힣0-9A-Za-z\s]{0,30})?"
    r"(?:\s*\([^\)]*\))?\s*$"
)

MIN_STORY_PARAS = 5        # 이보다 작은 스토리는 유닛 추출 제외 (번호 프레임 등)
MIN_ASSIGN_PARAS = 12      # 무헤더 배정 모드 최소 단락 수
ASSIGN_MIN_CONT = 0.5      # 단락 배정 최소 containment
ASSIGN_MIN_MARGIN = 0.15   # 1위-2위 최소 마진


def _txt(p):
    return (p.get("t") or "").replace("\r", "").replace("￼", " ").strip()


def _match_header(text):
    """헤더면 지문번호 문자열(없으면 "") 반환, 아니면 None."""
    for rx in (_RE_HEAD_BRACKET, _RE_HEAD_BRACE):
        m = rx.match(text)
        if m:
            return m.group(1).replace(" ", "")
    m = _RE_HEAD_FULL.match(text)
    if m and m.group(1):
        return m.group(1).replace(" ", "")
    return None


def _style_section(paras):
    """유닛의 대표 스타일 → 섹션 표시명 (예: 'STEP 01 > A1_어휘 선택')."""
    counts = {}
    for p in paras:
        s = p.get("s") or ""
        counts[s] = counts.get(s, 0) + 1
    if not counts:
        return ""
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    return best


def _is_q_start(p):
    """step3 문제 시작 단락 (발문 번호 스타일)."""
    s = p.get("s") or ""
    return "STEP 03" in s and "번호" in s


class Unit(object):
    __slots__ = ("uid", "story", "start", "end", "label", "section",
                 "text", "mode", "p0")

    def __init__(self, uid, story, start, end, label, section, text, mode,
                 p0=""):
        self.uid = uid
        self.story = story      # 스토리 인덱스 (dump 'idx')
        self.start = start      # 시작 단락 인덱스 (스토리 내, 헤더 포함)
        self.end = end          # 끝 단락 인덱스 (inclusive)
        self.label = label      # 지문번호 문자열 ("20", "41~42", "") — 표시용
        self.section = section  # 대표 스타일 (표시용)
        self.text = text
        self.mode = mode        # header | step3 | assign
        self.p0 = p0            # 시작 단락 원문 (JSX 접두 대조 가드용)

    def to_dict(self):
        return {"uid": self.uid, "story": self.story, "start": self.start,
                "end": self.end, "label": self.label,
                "section": self.section, "mode": self.mode,
                "p0": self.p0[:60], "first": self.text[:120]}


def _segment_headered(story_idx, paras, uid0):
    """헤더 구분자 스토리 → 유닛 리스트 (헤더 단락 포함 범위)."""
    units = []
    cur = None  # [start, label]
    texts = []
    for i, p in enumerate(paras):
        t = _txt(p)
        lab = _match_header(t)
        if lab is not None:
            if cur is not None:
                units.append(Unit(uid0 + len(units), story_idx, cur[0], i - 1,
                                  cur[1], _style_section(paras[cur[0]:i]),
                                  "\n".join(texts), "header",
                                  p0=(paras[cur[0]].get("t") or "")))
            cur = [i, lab]
            texts = []
            continue
        if cur is not None and t:
            texts.append(t)
    if cur is not None:
        units.append(Unit(uid0 + len(units), story_idx, cur[0],
                          len(paras) - 1, cur[1],
                          _style_section(paras[cur[0]:]),
                          "\n".join(texts), "header",
                          p0=(paras[cur[0]].get("t") or "")))
    return units


def _segment_step3(story_idx, paras, uid0):
    """step3 스토리 → 문제 블록 유닛 (발문 시작 단락 기준)."""
    starts = [i for i, p in enumerate(paras) if _is_q_start(p)]
    if not starts:
        return []
    units = []
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 1) if k + 1 < len(starts) else len(paras) - 1
        body = "\n".join(_txt(p) for p in paras[s:e + 1] if _txt(p))
        units.append(Unit(uid0 + len(units), story_idx, s, e, "",
                          _style_section(paras[s:e + 1]), body, "step3",
                          p0=(paras[s].get("t") or "")))
    return units


def _has_headers(paras):
    n = 0
    for p in paras:
        if _match_header(_txt(p)) is not None:
            n += 1
    return n >= 2


def _is_step3_story(paras):
    q = sum(1 for p in paras if _is_q_start(p))
    return q >= 2


def _group_token_sets(units_by_gid, fps_by_uid):
    """그룹별 EN/KO 토큰 합집합 (배정용)."""
    out = {}
    for gid, uids in units_by_gid.items():
        en = set()
        ko = set()
        for u in uids:
            fp = fps_by_uid[u]
            en |= fp.en_set
            ko |= fp.ko_set
        out[gid] = (en, ko)
    return out


def _assign_paragraph(fp, group_sets):
    """단락 fingerprint → (best_gid, best, margin). 배정 불가면 (None,0,0)."""
    scores = []
    for gid, (en, ko) in group_sets.items():
        best_ch = 0.0
        if len(fp.en_set) >= 3 and en:
            c = len(fp.en_set & en) / float(len(fp.en_set))
            best_ch = max(best_ch, c)
        if len(fp.ko_set) >= 3 and ko:
            c = len(fp.ko_set & ko) / float(len(fp.ko_set))
            best_ch = max(best_ch, c)
        scores.append((best_ch, gid))
    if not scores:
        return None, 0.0, 0.0
    scores.sort(reverse=True)
    best, gid = scores[0]
    second = scores[1][0] if len(scores) > 1 else 0.0
    if best < ASSIGN_MIN_CONT or (best - second) < ASSIGN_MIN_MARGIN:
        return None, best, best - second
    return gid, best, best - second


def _segment_assign(story_idx, paras, uid0, group_sets):
    """무헤더 흐름 스토리 → 시드 그룹 배정 런 유닛.

    반환: (units, gid_by_unit_index) — 각 유닛은 이미 그룹이 정해져 있다.
    """
    assigns = []
    for p in paras:
        t = _txt(p)
        if len(t) < 8:
            assigns.append("_prev")     # 저신호 → 직전 런 부착
            continue
        fp = fingerprint(t)
        gid, _, _ = _assign_paragraph(fp, group_sets)
        assigns.append(gid if gid is not None else "_prev")
    # 선두의 _prev는 첫 실제 배정으로 당김
    first = next((a for a in assigns if a != "_prev"), None)
    if first is None:
        return [], []
    for i in range(len(assigns)):
        if assigns[i] == "_prev":
            assigns[i] = assigns[i - 1] if i > 0 else first
        else:
            break
    for i in range(len(assigns)):
        if assigns[i] == "_prev":
            assigns[i] = assigns[i - 1]
    # 런 병합
    units = []
    gids = []
    run_start = 0
    for i in range(1, len(assigns) + 1):
        if i == len(assigns) or assigns[i] != assigns[run_start]:
            body = "\n".join(_txt(p) for p in paras[run_start:i] if _txt(p))
            units.append(Unit(uid0 + len(units), story_idx, run_start, i - 1,
                              "", _style_section(paras[run_start:i]),
                              body, "assign",
                              p0=(paras[run_start].get("t") or "")))
            gids.append(assigns[run_start])
            run_start = i
    return units, gids


def build_inventory(dump, log=None):
    """dump JSON → 인벤토리 dict.

    반환: {
      "units": [unit.to_dict() ...],
      "groups": [{"gid", "label", "title", "unit_uids", "sections",
                  "hub": bool} ...],
      "unassigned_stories": [...],
    }
    """
    def _log(msg):
        if log:
            log(msg)

    stories = dump.get("stories") or []
    seed_units = []
    assign_stories = []
    for st in stories:
        paras = st.get("paragraphs") or []
        if len(paras) < MIN_STORY_PARAS:
            continue
        idx = st["idx"]
        if _has_headers(paras):
            seed_units.extend(_segment_headered(idx, paras, len(seed_units)))
        elif _is_step3_story(paras):
            seed_units.extend(_segment_step3(idx, paras, len(seed_units)))
        elif len(paras) >= MIN_ASSIGN_PARAS:
            assign_stories.append(st)

    _log("[인벤토리] 시드 유닛 %d개 (헤더/step3), 배정 대상 스토리 %d개"
         % (len(seed_units), len(assign_stories)))

    # 시드 그룹핑 (매처)
    fps = [fingerprint(u.text) for u in seed_units]
    idf = build_idf(fps)
    groups_idx, hubs = group_fingerprints(fps, idf)

    # gid 부여 (그룹 리스트 순서)
    gid_of_unit = {}
    for gi, g in enumerate(groups_idx):
        for i in g:
            gid_of_unit[seed_units[i].uid] = gi

    units_by_gid = {}
    fps_by_uid = {}
    for i, u in enumerate(seed_units):
        fps_by_uid[u.uid] = fps[i]
        units_by_gid.setdefault(gid_of_unit[u.uid], []).append(u.uid)

    # 라벨 기반 보정 (실측 — 0a5da924 story 69 후반: 한글 요약 전용 짧은
    # 변형 유닛은 매처 텍스트 신호가 약해 단독 그룹으로 남는다): 헤더
    # 라벨이 정확히 하나의 멀티 그룹에만 존재하면 그 라벨의 단독 유닛을
    # 해당 그룹에 부착한다. EBS류 유닛별 재시작 번호(같은 라벨이 서로 다른
    # 지문 그룹에 존재)는 매핑이 모호해 자동으로 배제된다.
    hub_uids = {seed_units[i].uid for i in hubs}
    seed_by_uid = {u.uid: u for u in seed_units}
    label_to_gids = {}
    for gid, uids in units_by_gid.items():
        if len(uids) < 2:
            continue
        for uid in uids:
            lb = seed_by_uid[uid].label
            if lb:
                label_to_gids.setdefault(lb, set()).add(gid)
    attach = {lb: next(iter(gs)) for lb, gs in label_to_gids.items()
              if len(gs) == 1}
    attached = 0
    attached_uids = set()
    for gid in list(units_by_gid.keys()):
        uids = units_by_gid[gid]
        if len(uids) != 1:
            continue
        uid = uids[0]
        lb = seed_by_uid[uid].label
        if uid in hub_uids or not lb or lb not in attach:
            continue
        target = attach[lb]
        if target == gid:
            continue
        units_by_gid[target].append(uid)
        gid_of_unit[uid] = target
        del units_by_gid[gid]
        attached_uids.add(uid)
        attached += 1
    if attached:
        _log("[인벤토리] 라벨 보정 부착: %d유닛" % attached)

    # 배정 모드: 멀티 유닛 그룹(진짜 지문 그룹)만 대상.
    # 토큰 집합은 매처가 직접 묶은 유닛만으로 구성 — 라벨 보정으로 부착된
    # 한글 요약 유닛을 섞으면 배정 경계가 오염된다 (0a5da924 실측 회귀).
    multi_gids = {g for g, us in units_by_gid.items()
                  if len(us) > 1 and not (set(us) & hub_uids)}
    group_sets = _group_token_sets(
        {g: [u for u in us if u not in attached_uids]
         for g, us in units_by_gid.items() if g in multi_gids},
        fps_by_uid)

    all_units = list(seed_units)
    for st in assign_stories:
        units, gids = _segment_assign(st["idx"], st["paragraphs"],
                                      len(all_units), group_sets)
        for u, g in zip(units, gids):
            gid_of_unit[u.uid] = g
            units_by_gid.setdefault(g, []).append(u.uid)
            all_units.append(u)

    # 그룹 요약
    by_uid = {u.uid: u for u in all_units}
    groups = []
    for gid in sorted(units_by_gid.keys()):
        uids = units_by_gid[gid]
        labels = [by_uid[u].label for u in uids if by_uid[u].label]
        label = ""
        if labels:
            # 최빈 라벨
            cnt = {}
            for lb in labels:
                cnt[lb] = cnt.get(lb, 0) + 1
            label = max(cnt.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
        # 제목: 가장 긴 유닛의 첫 줄
        longest = max(uids, key=lambda u: len(by_uid[u].text))
        title = by_uid[longest].text.split("\n", 1)[0][:100]
        sections = sorted({by_uid[u].section for u in uids if by_uid[u].section})
        groups.append({
            "gid": gid,
            "label": label,
            "title": title,
            "unit_uids": sorted(uids),
            "sections": sections,
            "hub": bool(set(uids) & hub_uids),
            "multi": len(uids) > 1,
        })

    _log("[인벤토리] 그룹 %d개 (멀티 %d, 허브 %d)" % (
        len(groups), sum(1 for g in groups if g["multi"]),
        sum(1 for g in groups if g["hub"])))
    return {
        "units": [u.to_dict() for u in all_units],
        "groups": groups,
    }


# ── 제거 스펙 빌더 (JSX 입력) ───────────────────────────────────────────────

def build_removal_spec(inventory, selected_gids):
    """인벤토리 + 선택 그룹 → JSX 제거 스펙.

    반환: {"stories": [{"story", "remove": [...], "renumber": [...]}],
           "clear_numbers": [...], "removed_uids": [...]}
    허브 그룹은 선택 불가 (ValueError) — 여러 지문이 섞인 blob은 자동 제거가
    다른 지문을 훼손한다.
    """
    selected = {int(g) for g in selected_gids}
    groups = inventory["groups"]
    units = inventory["units"]
    by_gid = {g["gid"]: g for g in groups}
    for gid in selected:
        if gid not in by_gid:
            raise ValueError("존재하지 않는 그룹: %d" % gid)
        if by_gid[gid].get("hub"):
            raise ValueError(
                "그룹 %d는 여러 지문이 섞인 블록(허브) — 자동 제거 불가" % gid)

    gid_of = {}
    for g in groups:
        for u in g["unit_uids"]:
            gid_of[u] = g["gid"]
    removed_uids = {u["uid"] for u in units
                    if gid_of.get(u["uid"]) in selected}

    stories = {}
    for u in units:
        if u["uid"] in removed_uids:
            st = stories.setdefault(
                u["story"], {"story": u["story"], "remove": [],
                             "renumber": []})
            st["remove"].append({"start": u["start"], "end": u["end"],
                                 "p0": u["p0"]})
    # 잔존 유닛 번호 갱신 목록 (영향 스토리만, 시작 순서)
    group_label = {g["gid"]: g.get("label") or "" for g in groups}
    for u in sorted(units, key=lambda x: (x["story"], x["start"])):
        st = stories.get(u["story"])
        if not st or u["uid"] in removed_uids:
            continue
        label = u.get("label") or group_label.get(gid_of.get(u["uid"]), "")
        if label:
            st["renumber"].append({"p0": u["p0"], "label": label})

    clear_numbers = sorted({
        lb for lb in (
            [by_gid[g].get("label") or "" for g in selected]
            + [u.get("label") or "" for u in units
               if u["uid"] in removed_uids])
        if lb})
    story_list = [stories[k] for k in sorted(stories.keys())]
    for st in story_list:
        st["remove"].sort(key=lambda r: r["start"])
    return {"stories": story_list, "clear_numbers": clear_numbers,
            "removed_uids": sorted(removed_uids)}


def verify_line_sets(inventory, dump, removed_uids):
    """검수용 라인 집합 — (removed_only_lines, kept_lines).

    원본 dump에서 유닛 단락 텍스트를 복원해, 제거 유닛에만 존재하는
    판별 라인(정규화, 25자+)과 잔존 유닛의 전체 판별 라인을 계산한다.
    """
    removed_uids = set(removed_uids)
    by_story = {st["idx"]: st.get("paragraphs") or []
                for st in dump.get("stories") or []}

    def _lines(u):
        paras = by_story.get(u["story"]) or []
        out = []
        for p in paras[u["start"]:u["end"] + 1]:
            t = norm_line(p.get("t") or "")
            if len(t) >= 25:
                out.append(t)
        return out

    removed_lines = set()
    kept_lines = set()
    for u in inventory["units"]:
        if u["uid"] in removed_uids:
            removed_lines.update(_lines(u))
        else:
            kept_lines.update(_lines(u))
    return removed_lines - kept_lines, kept_lines


def norm_line(t):
    """라인 정규화 — 검수 대조용 (공백/앵커 정리)."""
    t = t.replace("\r", " ").replace("\n", " ").replace("￼", " ")
    return " ".join(t.split())
