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
# 모의 41~42 복합문항 — 중요어휘 시트는 `250341` 로만 적어 오는 일이 있다.
# 문장배열·어법은 `250341~42` 라 그대로 두면 같은 지문이 두 라벨로 갈린다
# (지금은 조판 직전 JSX 준비 단계가 고쳐 준다 — 그 규칙을 데이터로 올린다).
RE_LONG42 = re.compile(r"^(\d{4})(?:41|42)$")
# 항목 머리표 — `(A)` `(B)` … 지면에서 굵게 찍힌다.
RE_ITEM = re.compile(r"^\(([A-Z])\)\s*")


# 요약 표제 — 원고/시트가 `>>   내용요약` · `>>내용요약` · `|  내용요약  |` 등
# 네 가지 모양으로 준다(실측: 명일1 한 권 안에서만 세 가지). 글자 그대로
# 찾으면 하나만 걸리고 나머지는 **헤더로 오인**돼 지문이 하나 늘어난다.
def is_summary_mark(line):
    t = (line or "").strip()
    return "내용요약" in t and len(t) <= 24


def norm_header(h):
    h = (h or "").strip()
    m = RE_LONG42.match(h)
    return f"{m.group(1)}41~42" if m else h

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


def _insert(blocks, warn=lambda m: None):
    """하단 문제 = 발문 + 주어진 문장(상자) + 항목들.

    ⚠ 상자를 **스타일 이름으로 가르면 안 된다.** 인디자인에서 되읽은 21블록 중
      상자 줄이 `문장 배열 하단` 스타일인 것은 18개뿐이고, 교과서 지문 셋은
      항목과 같은 스타일이다(완성본은 셋 다 상자로 찍혀 있다). 자리가 규칙이다 —
      **첫 줄 = 발문, 둘째 줄 = 주어진 문장, 나머지 = 항목.**
    """
    out = []
    for b in blocks:
        ps = [p for p in (b.get("paras") or []) if (p.get("text") or "").strip()]
        txt = [(p.get("text") or "").strip() for p in ps]
        prompt = txt[0] if txt else ""
        given = txt[1] if len(txt) > 1 else ""
        items = txt[2:]
        if given and RE_ITEM.match(given):
            warn(f"문장삽입 {b['header']}: 주어진 문장 자리에 항목이 왔다")
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
        if is_summary_mark(g[0]):
            body = [l for l in g[1:] if l.strip()]
            if not out:
                warn("중요어휘: 헤더 없는 요약 묶음")
                continue
            out[-1]["summary"] = [segs(l) for l in body]
        else:
            out.append({"header": norm_header(g[0]),
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
        "insert": _insert(v1.get("문장삽입") or [], warn),
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
        # 빈 섹션은 싣지 않는다 — 고3(EBS)은 문장삽입이 아예 없다(실측:
        # 명일3·광문3 모두 0개). 빈 섹션을 남기면 빈 면이 한 장 나간다.
        secs = [_section(k, n, made[k]) for k, n in spec["sections"]
                if made[k]]
        for k, _n in spec["sections"]:
            if not made[k]:
                warn(f"{SEC_TITLES[k]}: 지문 0개 — 이 권에서 뺀다")
        out["vols"][str(vol)] = {
            "vol": vol,
            "chapter": {"no": cno, "en": cen},
            "sections": secs,
        }
    return out


# ------------------------------------------------------------------ 게이트
def gate(data, content, log):
    """수량이 어긋나면 **조판하지 않고 멈춘다.**"""
    bad = []
    secs = {s["kind"]: s for v in data["vols"].values() for s in v["sections"]}
    empty = {k: {"blocks": []} for k in SEC_TITLES if k not in secs}
    secs.update(empty)
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
    # 요약(`>>내용요약`)은 **고1·고2 만** 있다 — 고3(EBS)은 워크북 빈칸어휘라
    # 요약이 아예 없다(실측: 명일3·광문3 19/53지문 전부 없음). 그래서 "없다"는
    # 결함이 아니고, **일부만 있는 것**이 결함이다(그건 소스가 샌 것이다).
    vb = secs["vocab"]["blocks"]
    nosum = [b["header"] for b in vb if not b["summary"]]
    if nosum and len(nosum) != len(vb):
        bad.append(f"중요어휘 요약이 일부에만 있다 — 없는 지문 {len(nosum)}"
                   f"/{len(vb)}: {nosum[:5]}")
    # 문장배열·중요어휘 헤더 집합 대조 (다르면 어느 한쪽이 샜다)
    # 중요어휘에만 있는 헤더는 **결함이 아닐 수 있다** — 구글시트에는 있는데
    # 워크북에 그 유형이 없는 경우가 실재한다(상일1 올포 12강 본문3 등).
    # 다만 조용히 넘기지는 않는다.
    ha = {b["header"] for b in secs["arrange"]["blocks"]}
    hv = {b["header"] for b in vb}
    if hv - ha:
        log(f"  [알림] 중요어휘에만 있는 지문 {len(hv - ha)}개: "
            f"{sorted(hv - ha)[:5]}")
    if bad:
        for m in bad:
            log(f"  [게이트] {m}")
        raise SystemExit("원고 인식 게이트 실패 — 조판을 멈춘다")
    log(f"  [게이트] 통과 — 배열 {len(secs['arrange']['blocks'])} · "
        f"삽입 {len(secs['insert']['blocks'])} · 어휘 {len(vb)}"
        f"{'(요약 없음)' if nosum else ''} · "
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
