"""부교재 워크북 v2 — 여러 벌 원고(폴더별 세트) 병합 + 지문 범위 선택.

2026-09-08 사용자 지시. 성덕2 EBS 연계 외부지문처럼 원고가 지문 구간별
폴더(`6~10` / `11~15` / `16~20`)로 나뉜 교재를 한 권으로 조판한다.

왜 content 단계에서 병합하나:
  원고 docx를 XML로 이어붙이면 밑줄 런(어법 선택/빈칸 어법이 의존)이
  깨진다. 파서를 세트마다 따로 돌린 뒤 **파싱 결과**(content.json)를
  지문 블록 단위로 합치는 것이 안전하다. 블록 경계 판정은 v1 파서의
  헤더 인식기를 그대로 재사용한다 (형식이 아니라 파서와 같은 눈).

지문 범위:
  '6~17, 19' 같은 자연어를 받아 그 번호만, 적힌 순서가 아니라 **번호
  오름차순**으로 싣는다. 범위를 안 적으면 올라온 지문 전부.
"""
import re
import unicodedata

from engines.workbook.parser import (_RE_BRACKET_NUM, _RE_HEADER_NUM,
                                     _struct_header_extras,
                                     _struct_header_qnum)

_RE_RANGE = re.compile(r"(\d+)\s*(?:~|-|–|—|부터)\s*(\d+)")
_RE_NUM = re.compile(r"\d+")


def parse_passage_range(text):
    """'6~17, 19' / '6번~17번, 19번' / '6-10 12' → [6..17, 19] (오름차순).

    빈 입력이면 None (= 전체). 숫자가 하나도 없으면 None."""
    if not text:
        return None
    t = unicodedata.normalize("NFC", str(text))
    t = t.replace("번", " ")
    nums = set()
    for m in _RE_RANGE.finditer(t):
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        if b - a > 500:          # 오타 방어 (범위 폭주 금지)
            continue
        nums.update(range(a, b + 1))
    # 범위로 소비된 구간을 지운 뒤 남은 낱 숫자
    rest = _RE_RANGE.sub(" ", t)
    for m in _RE_NUM.finditer(rest):
        nums.add(int(m.group(0)))
    return sorted(nums) or None


def header_positions(paragraphs):
    """[(단락 인덱스, 지문번호)] — v1 파서 _extract_question_numbers와 동일 판정."""
    out = []
    extras = _struct_header_extras(paragraphs)
    for i, p in enumerate(paragraphs):
        t = (p.get("text") or "").strip()
        m = _RE_BRACKET_NUM.match(t)
        if m:
            out.append((i, int(m.group(1))))
            continue
        m = _RE_HEADER_NUM.match(t)
        if m:
            cap = m.group(1)
            if cap:
                out.append((i, int(cap.split("~")[0])))
            continue
        if i in extras:
            n = _struct_header_qnum(t)
            if n is not None:
                out.append((i, n))
    return out


def split_units(paragraphs):
    """(첫 헤더 앞 단락들, {지문번호: 블록 단락들})."""
    hp = header_positions(paragraphs)
    if not hp:
        return list(paragraphs), {}
    pre = paragraphs[:hp[0][0]]
    blocks = {}
    for k, (i, num) in enumerate(hp):
        j = hp[k + 1][0] if k + 1 < len(hp) else len(paragraphs)
        blocks.setdefault(num, []).extend(paragraphs[i:j])
    return pre, blocks


def _dedupe_blank_runs(paras):
    out, prev_empty = [], False
    for p in paras:
        empty = not (p.get("text") or "").strip()
        if empty and prev_empty:
            continue
        out.append(p)
        prev_empty = empty
    return out


def _strip_worksheet_head(paras):
    """원고 머리 기입란('이름 __ 반 __ 번호 __ …') 제거.

    세트마다 있어서 이어붙이면 책 중간에 워크시트 머리가 반복된다.
    게다가 이 줄은 발문으로 잡혀 STEP3 실전문제 자동번호 01번을 먹는다
    (원고 1~N번이 책에서 2~N+1번으로 통째로 밀린다)."""
    out = list(paras)
    while out:
        t = (out[0].get("text") or "").strip()
        if not t:
            out.pop(0)
            continue
        if "이름" in t and "번호" in t and "_" in t:
            out.pop(0)
        break
    return out


def merge_step_contents(datas, want=None, log=None):
    """세트별 content(dict) 목록 → 한 벌로 병합. want=지문번호 목록(선택).

    반환: (merged_steps, report) — report[step] = {'got','missing','dropped'}
    """
    log = log or (lambda m: None)
    steps_all = []
    for d in datas:
        steps_all.append((d.get("steps") or {}))
    keys = []
    for st in steps_all:
        for k in st:
            if k != "step3" and k not in keys:
                keys.append(k)

    merged, report = {}, {}
    for k in keys:
        pre_first, blocks_all, fname = None, {}, None
        for st in steps_all:
            sd = st.get(k)
            if not isinstance(sd, dict):
                continue
            fname = fname or sd.get("filename")
            pre, blocks = split_units(sd.get("paragraphs") or [])
            if pre_first is None:
                pre_first = pre
            for n, b in blocks.items():
                blocks_all[n] = b            # 같은 번호는 뒤 세트가 이김
        order = [n for n in (want or sorted(blocks_all)) if n in blocks_all]
        paras = list(pre_first or [])
        for n in order:
            paras.extend(blocks_all[n])
        merged[k] = {
            "filename": fname,
            "question_numbers": list(order),
            "paragraphs": _dedupe_blank_runs(paras),
        }
        merged[k]["paragraph_count"] = len(merged[k]["paragraphs"])
        report[k] = {
            "got": list(order),
            "missing": [n for n in (want or []) if n not in blocks_all],
            "dropped": sorted(set(blocks_all) - set(order)),
        }

    # step3 — 세트별 문항 모음을 한 유닛으로 이어 붙인다 (문항 번호가
    # 세트에 걸쳐 연속인 것이 이 계열의 관행: 1~60 / 61~117 / 118~150).
    s3 = []
    for st in steps_all:
        blk = st.get("step3")
        if not isinstance(blk, dict):
            continue
        for grp in ("normal", "short"):
            for item in blk.get(grp) or []:
                s3.extend(_strip_worksheet_head(item.get("paragraphs") or []))
    if s3:
        merged["step3"] = {"normal": [{"question_num": "textbook",
                                       "code": "", "paragraphs": s3}],
                           "short": [], "normal_count": 1, "short_count": 0}
    return merged, report


def group_sets(manifest, staged_names):
    """업로드 매니페스트 → [(세트 이름, {스테이징 파일명})] (폴더 순서 유지).

    manifest: routes/typeset.py 가 남긴 [{saved, rel, name}].
    staged_names: 엔진이 uploads/ 에 실제로 스테이징한 파일명 집합.

    세트 키 = 상대경로에서 파일명을 뺀 마지막 폴더. 원고가
    '<구간>/워크북/파일.docx' 처럼 한 단계 더 들어가는 관행이 있어,
    같은 꼬리 폴더('워크북')만 나오면 그 위 단계를 쓴다.
    """
    rows = []
    for m in manifest or []:
        rel = (m.get("rel") or "").replace("\\", "/")
        if "/" not in rel:
            continue
        parts = [x for x in rel.split("/")[:-1] if x]
        if not parts:
            continue
        rows.append((parts, m))
    if not rows:
        return []
    depth = 1
    while depth < 6:
        keys = {"/".join(p[-depth:]) if len(p) >= depth else "/".join(p)
                for p, _ in rows}
        if len(keys) > 1:
            break
        depth += 1
    groups, order = {}, []
    for parts, m in rows:
        key = "/".join(parts[-depth:]) if len(parts) >= depth else "/".join(parts)
        if key not in groups:
            groups[key] = set()
            order.append(key)
        name = unicodedata.normalize("NFC", m.get("name") or "")
        if name in staged_names:
            groups[key].add(name)
    return [(k, groups[k]) for k in order if groups[k]]
