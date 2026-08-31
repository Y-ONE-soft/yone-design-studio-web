"""파이널 직전보충 — `content.json`(파이널 엔진 산출) → `data.json`.

파이널 엔진(`engines/final`)이 만든 content.json 은 **소스 수집의 결과**다.
이 모듈은 그것을 지면이 쓰는 모양으로만 바꾼다 — 내용을 만들지도, 고르지도
않는다. 소스 자체를 원고 직독으로 갈아 끼우는 일(B6)은 여기 **위쪽**에서
일어나고, 이 파일은 그때도 그대로다.

바꾸는 것:
  · 문장배열   {header, items, passage?} → {header, given, items}
  · 문장삽입   paras[{style,text}] → {header, prompt, given, items}
      (스타일 이름 두 가지가 곧 역할이다 — '문장 배열 하단' = 주어진 문장 상자)
  · 중요어휘   한 덩어리 문자열 → 지문별 블록 + `[답]` 조각 분해
      ⚠ 인디자인은 왼(빈칸)·오(정답) **두 스토리를 따로 흘리고** 높이를 재서
        `>>내용요약` 줄을 맞췄다. 여기서는 한 지문이 한 블록이라 짝이 어긋날
        수 없다(명일3 test1 24~25 꼬리 소실 같은 결함이 구조적으로 불가능해진다).
  · 어법수정   [헤더, 본문, 헤더, 본문 …] 평면 리스트 → 블록
  · 서술형영작 pairs + (헤더, start_idx) → 헤더별 묶음

인식 게이트: 블록 수·짝이 어긋나면 **조판하지 않고 멈춘다**(침묵 유실 금지).
"""
import json
import os
import re

# `12[looked]` / `[owe]` — 원고가 붙인 번호는 지면에 찍히지 않는다(완성본 실측).
RE_MARK = re.compile(r"(\d*)\[([^\[\]]*)\]")
# 인디자인에서 되읽은 지문에 남은 **하이픈 넣기 잔재**("lim-ited", "bet-ter").
# 원고에는 없다 — 조판된 지면을 역수확했기 때문에 생긴다. 지우지는 않고 센다.
RE_HYPH = re.compile(r"\b([A-Za-z]{2,})-([a-z]{2,})\b")

SEC_TITLES = {
    "arrange": "문장 배열",
    "insert": "문장 삽입 / 순서 배열",
    "vocab": "중요 어휘 / 요약문",
    "grammar": "어법 수정",
    "writing": "서술형 영작",
}
# 권 → (장 번호, 장 이름, [섹션…]).  완성본 실측: Vol1 = Chapter.01 Frame,
# Vol2 = Chapter.02 Build Up. 섹션 번호는 두 권을 통틀어 1→4 로 이어진다.
VOL_SPEC = {
    1: {"chapter": (1, "Frame"),
        "sections": [("arrange", 1), ("insert", 1), ("vocab", 2)]},
    2: {"chapter": (2, "Build Up"),
        "sections": [("grammar", 3), ("writing", 4)]},
}


# ------------------------------------------------------------------ 조각
def segs(text):
    """`[답]` 이 섞인 줄 → 조각 목록. 문자열 | {"a": 답}."""
    out, i = [], 0
    for m in RE_MARK.finditer(text or ""):
        if m.start() > i:
            out.append(text[i:m.start()])
        out.append({"a": m.group(2)})
        i = m.end()
    if i < len(text or ""):
        out.append(text[i:])
    return out


def plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("a", "")
    if not x:
        return ""
    return "".join(plain(i) for i in x)


# ------------------------------------------------------------------ 섹션별
def _arrange(blocks):
    out = []
    for b in blocks:
        out.append({"header": b["header"],
                    "given": b.get("passage") or "",
                    "items": list(b.get("items") or [])})
    return out


def _insert(blocks):
    """하단 문제 = 발문 + (주어진 문장 상자) + 항목들.

    스타일 이름이 역할이다: `문장 배열 하단` = 상자에 들어가는 주어진 문장,
    `문장 배열 하단 문제` = 발문과 항목. 첫 줄은 늘 발문이다(완성본 실측).
    """
    out = []
    for b in blocks:
        ps = b.get("paras") or []
        prompt, given, items = "", "", []
        for k, p in enumerate(ps):
            t = (p.get("text") or "").strip()
            if not t:
                continue
            if p.get("style") == "문장 배열 하단":
                given = (given + " " + t).strip() if given else t
            elif not prompt and k == 0:
                prompt = t
            else:
                items.append(t)
        out.append({"header": b["header"], "prompt": prompt,
                    "given": given, "items": items})
    return out


def _vocab(text, warn):
    """한 덩어리 문자열 → 지문 블록.

    모양(실측): `헤더 / 지문…` · 빈 줄 · `>> 내용요약 / 요약…` · 빈 줄 · 반복.
    빈 줄로 끊어 묶음을 만들고 `>>` 로 시작하면 요약 묶음으로 본다 — 헤더
    글자꼴(모의 6자리·"리딩파워 N강 01")에 기대지 않는다.
    """
    groups, cur = [], []
    for ln in (text or "").split("\n"):
        if ln.strip():
            cur.append(ln.rstrip())
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        if g[0].lstrip().startswith(">>"):
            body = [l for l in g[1:] if l.strip()]
            if not out:
                warn("중요어휘: 헤더 없는 요약 묶음")
                continue
            out[-1]["summary"] = [segs(l) for l in body]
        else:
            out.append({"header": g[0].strip(),
                        "passage": [segs(l) for l in g[1:] if l.strip()],
                        "summary": []})
    for b in out:
        if not b["passage"]:
            warn(f"중요어휘 {b['header']}: 지문 없음")
    return out


def _grammar(flat, headers, warn):
    """[헤더, 본문, 헤더, 본문 …] — 파이널 파서가 이 모양으로 준다."""
    out = []
    if len(flat) != 2 * len(headers):
        warn(f"어법수정: 줄 {len(flat)} ≠ 헤더 {len(headers)}×2")
    for i, h in enumerate(headers):
        if 2 * i + 1 >= len(flat):
            break
        if flat[2 * i] != h:
            warn(f"어법수정 {h}: 헤더 자리에 '{flat[2 * i][:20]}'")
        out.append({"header": h, "body": segs(flat[2 * i + 1])})
    return out


def _writing(pairs, detail, warn):
    """헤더 목록의 start_idx 로 pairs 를 자른다.

    ⚠ 경계는 **start_idx 오름차순**으로 잡는다 — 입력 순서가 단조가 아니면
      다음 헤더의 start_idx 가 블록 끝이 아니어서 옆 강의 영작이 섞인다
      (광문3 26-1-기말 실증: 8헤더 16쌍이 회전 변위).
    """
    idx = sorted({d["start_idx"] for d in detail})
    nxt = {}
    for k, s in enumerate(idx):
        nxt[s] = idx[k + 1] if k + 1 < len(idx) else len(pairs)
    out = []
    for d in detail:
        s = d["start_idx"]
        chunk = pairs[s:nxt.get(s, len(pairs))]
        if not chunk:
            warn(f"서술형영작 {d['header']}: 빈 블록")
        out.append({"header": d["header"],
                    "pairs": [{"korean": p.get("korean", ""),
                               "choices": p.get("choices", "")}
                              for p in chunk]})
    return out


# ------------------------------------------------------------------ 진입
def _section(kind, no, blocks):
    return {"kind": kind, "no": no, "title": SEC_TITLES[kind], "blocks": blocks}


def from_content(content, warn=lambda m: None):
    """content.json(dict) → data.json(dict). 두 권을 한 번에 만든다."""
    v1, v2 = content.get("vol1") or {}, content.get("vol2") or {}
    made = {
        "arrange": _arrange(v1.get("문장배열") or []),
        "insert": _insert(v1.get("문장삽입") or []),
        "vocab": _vocab(v1.get("중요어휘_왼") or "", warn),
        "grammar": _grammar(v2.get("어법수정") or [],
                            v2.get("어법_헤더") or [], warn),
        "writing": _writing(v2.get("서술형영작") or [],
                            v2.get("영작_헤더_상세") or [], warn),
    }
    out = {"school": content.get("school", ""),
           "grade": content.get("grade", ""),
           "period": content.get("exam_period", ""),
           "vols": {}}
    for vol, spec in VOL_SPEC.items():
        cno, cen = spec["chapter"]
        out["vols"][str(vol)] = {
            "vol": vol,
            "chapter": {"no": cno, "en": cen},
            "sections": [_section(k, n, made[k]) for k, n in spec["sections"]],
        }
    return out


# ------------------------------------------------------------------ 게이트
def gate(data, content, log):
    """수량이 어긋나면 **조판하지 않고 멈춘다.**"""
    bad = []
    secs = {s["kind"]: s for v in data["vols"].values() for s in v["sections"]}
    want = {
        "arrange": len(content["vol1"].get("문장배열") or []),
        "insert": len(content["vol1"].get("문장삽입") or []),
        "grammar": len(content["vol2"].get("어법_헤더") or []),
        "writing": len(content["vol2"].get("영작_헤더_상세") or []),
    }
    for k, n in want.items():
        got = len(secs[k]["blocks"])
        if got != n:
            bad.append(f"{SEC_TITLES[k]} 블록 {got} ≠ 원본 {n}")
    # 중요어휘는 원본이 문자열이라 개수를 셀 수 없다 → 지문·요약 짝만 본다
    vb = secs["vocab"]["blocks"]
    nosum = [b["header"] for b in vb if not b["summary"]]
    if nosum:
        bad.append(f"중요어휘 요약 없는 지문 {len(nosum)}개: {nosum[:5]}")
    # 문장배열·중요어휘 헤더 집합 대조 (다르면 어느 한쪽이 샜다)
    ha = {b["header"] for b in secs["arrange"]["blocks"]}
    hv = {b["header"] for b in vb}
    if hv - ha:
        bad.append(f"중요어휘에만 있는 헤더: {sorted(hv - ha)[:5]}")
    if bad:
        for m in bad:
            log(f"  [게이트] {m}")
        raise SystemExit("원고 인식 게이트 실패 — 조판을 멈춘다")
    log(f"  [게이트] 통과 — 배열 {len(secs['arrange']['blocks'])} · "
        f"삽입 {len(secs['insert']['blocks'])} · 어휘 {len(vb)} · "
        f"어법 {len(secs['grammar']['blocks'])} · "
        f"영작 {len(secs['writing']['blocks'])}")


def hyphen_artifacts(data):
    """되읽기 잔재(하이픈 넣기) 후보 — 붙인 형태가 문서 안에 따로 있으면 의심.

    조용히 고치지 않는다. 원고 직독으로 바꾸면 사라질 것이라, **지금 몇 개인지**
    가 전환의 근거가 된다.
    """
    blob = json.dumps(data, ensure_ascii=False)
    words = {w.lower() for w in re.findall(r"[A-Za-z]{2,}", blob)}
    hits = {}
    for m in RE_HYPH.finditer(blob):
        if (m.group(1) + m.group(2)).lower() in words:
            hits[m.group(0)] = hits.get(m.group(0), 0) + 1
    return hits


# ------------------------------------------------------------------ 파일
def _content_path(cfg):
    m = cfg.section("manuscript") or {}
    d = cfg.resolve(m.get("dir", "원고"))
    f = (m.get("files") or {}).get("content", "content.json")
    return os.path.join(d, f)


def build(cfg, log):
    src = _content_path(cfg)
    if not os.path.exists(src):
        raise FileNotFoundError(f"content.json 없음: {src}")
    with open(src, encoding="utf-8") as f:
        content = json.load(f)
    warns = []
    data = from_content(content, warns.append)
    for w in warns:
        log(f"  [경고] {w}")
    gate(data, content, log)
    hy = hyphen_artifacts(data)
    if hy:
        log(f"  [되읽기 잔재] 하이픈 의심 {sum(hy.values())}건 "
            f"{sorted(hy)[:8]} — 원고 직독으로 바꾸면 사라진다")
    data["_hyphen_suspects"] = hy
    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"[원고] {os.path.basename(src)} → data.json")
    return out


def load(cfg):
    with open(cfg.path("data.json"), encoding="utf-8") as f:
        return json.load(f)
