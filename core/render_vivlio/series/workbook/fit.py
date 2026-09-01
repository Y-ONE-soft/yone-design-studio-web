"""넘친 한두 줄을 **당겨 붙이는** 측정 패스.

한 덩어리(지문 묶음·실전 문항)가 면을 넘어가는데 넘어간 쪽이 한두 줄뿐이면,
그 한두 줄 때문에 면이 하나 늘고 지면이 어색해진다. 사용자 규칙:

    "이렇게 애매하게 한 줄만 넘어갈 경우 이전 단락의 프레임 하단을 좀 더 늘리거나
     행간 자간 조정으로 최대한 땡겨야 함 (세 네 줄 이상 넘어가는 경우가 아닌 이상)"

밀어내기(widows/orphans)로는 안 된다 — 그건 더 밀 뿐이다. 당기려면 **조판을 한 번
굽고 실제 자리를 재서** 그 덩어리만 좁혀 다시 굽는 수밖에 없다.

  ① 렌더러가 덩어리 처음·끝에 흰 표식(`.zbeg`/`.zend`)을 심는다
  ② 조판한 PDF 에서 표식의 면·좌표를 읽어 **면을 넘긴 덩어리**를 찾는다
  ③ 넘어간 쪽이 임계(기본 두 줄)보다 짧으면 그 덩어리만 `tight` 로 표시
  ④ 다시 렌더 → 조판. 두 바퀴까지 (수렴 안 하면 그대로 둔다)

⚠ 반복 조판은 **발산할 수 있다**(블랙북에서 겪었다: 10→8→7). 그래서 바퀴 수를
  묶고, 좁히는 폭도 한 단계만 쓴다.
"""

MM = 72 / 25.4

# 표식 구분 — 파랑 채널 값 (크기로 나누면 서로 오인한다)
BEG_B = (0.9823, 0.9863)    # #fffffb (덩어리 시작)
END_B = (0.9745, 0.9785)    # #fffff9 (덩어리 끝)
SBEG_B = (0.9902, 0.9942)   # #fffffd (세트 시작)
SEND_B = (0.9863, 0.9902)   # #fffffc (세트 끝)

BODY_TOP = 28.0
TAIL_LIMIT = 12.0           # 넘어간 쪽이 이보다 짧으면 당긴다 (두 줄 남짓)


def _fitz():
    try:
        import pymupdf as f
    except ImportError:
        import fitz as f
    return f


def _marks(doc):
    """(면, 단, y, 종류) 순으로 정렬된 표식들."""
    out = []
    for i in range(doc.page_count):
        pg = doc[i]
        for dr in pg.get_drawings():
            r = dr["rect"]
            f = dr.get("fill")
            if not f or len(f) < 3:
                continue
            w, h = r.width / MM, r.height / MM
            if not (0.25 < w < 0.6 and 0.25 < h < 0.6):
                continue
            if not (f[0] > 0.99 and f[1] > 0.99):
                continue
            kind = None
            if BEG_B[0] < f[2] < BEG_B[1]:
                kind = "beg"
            elif END_B[0] < f[2] < END_B[1]:
                kind = "end"
            elif SBEG_B[0] < f[2] < SBEG_B[1]:
                kind = "sbeg"
            elif SEND_B[0] < f[2] < SEND_B[1]:
                kind = "send"
            if not kind:
                continue
            x, y = r.x0 / MM, r.y0 / MM
            # ⚠ 같은 자리(y 동일)에 앞 덩어리의 **끝**과 다음 덩어리의 **시작**이
            #   겹친다. 종류 문자열로 정렬하면 'sbeg' < 'send' 라 시작이 앞서고,
            #   짝이 어긋나 세트 하나가 통째로 사라진다(실측: 한영1 p303).
            #   끝(0)을 시작(1)보다 앞에 둔다.
            rank = 0 if kind in ("end", "send") else 1
            out.append((i + 1, 0 if x < 106 else 1, y, rank, kind))
    out.sort()
    return [(p, c, y, k) for p, c, y, _r, k in out]


def spills(pdf, tail_limit=TAIL_LIMIT):
    """면을 넘긴 덩어리 — [(덩어리 번호, 시작면, 끝면, 넘어간 쪽 길이 mm)]

    덩어리 번호는 **문서 순서**(면 → 단 → y)로 0부터. 렌더러가 붙이는 순서와 같다.
    """
    fitz = _fitz()
    doc = fitz.open(pdf)
    marks = _marks(doc)
    doc.close()
    out = []
    idx = -1
    open_beg = None
    for page, col, y, kind in marks:
        if kind not in ("beg", "end"):
            continue
        if kind == "beg":
            idx += 1
            open_beg = (idx, page, col)
        elif open_beg is not None:
            bidx, bpage, _bcol = open_beg
            # ⚠ **면**을 넘긴 것만 당긴다. 단을 넘는 것은 정상 흐름이다
            #   (완성본도 단의 22%가 선지로 시작한다).
            if page != bpage:
                tail = max(0.0, y - BODY_TOP)
                out.append((bidx, bpage, page, round(tail, 1)))
            open_beg = None
    # 꼬리가 거의 0 이면 **표식만** 넘어간 것이다 — 당길 내용이 없다
    return [s for s in out if 2.0 <= s[3] <= tail_limit]


def report(sp, log):
    if not sp:
        log("  [당겨붙이기] 한두 줄만 넘긴 덩어리 없음")
        return
    log(f"  [당겨붙이기] 한두 줄만 넘긴 덩어리 {len(sp)}개 — "
        + ", ".join(f"#{i}(p{a}→p{b}, {t}mm)" for i, a, b, t in sp[:6]))


def turns(pdf):
    """**장을 넘겨야 보이는** 세트 — [(세트 번호, 시작면, 끝면)]

    펼침면은 (짝수 왼쪽, 홀수 오른쪽). 세트가 홀수(오른쪽) 면에서 시작해 그
    면을 벗어나면 학생이 장을 넘겨 가며 풀어야 한다(사용자 금지 규칙).
    왼쪽 → 오른쪽은 같은 펼침면이라 괜찮다.

    ⚠ 짝은 **문서 순서로** 맺는다. 검수 게이트의 첫 판은 '시작면 이상인 첫 끝면'
      으로 맺어서 표식 하나가 비면 p207→p215 같은 헛값이 나왔다.
    """
    fitz = _fitz()
    doc = fitz.open(pdf)
    marks = [m for m in _marks(doc) if m[3] in ("sbeg", "send")]
    doc.close()
    out = []
    idx = -1
    op = None
    for page, _col, _y, kind in marks:
        if kind == "sbeg":
            if op is not None:      # 끝 표식이 빠졌다 — 짝을 버리고 다시 연다
                op = None
            idx += 1
            op = (idx, page)
        elif op is not None:
            sidx, spage = op
            # 한 펼침면(두 면)에 못 담기는 세트는 밀어도 장 넘김이 안 없어진다 —
            # 오른쪽 면만 통째로 비우는 헛수고라 손대지 않는다.
            if spage % 2 == 1 and spage < page <= spage + 1:
                out.append((sidx, spage, page))
            op = None
    return out


def report_turns(t, log):
    if not t:
        log("  [장넘김] 오른쪽 면에서 장을 넘기는 세트 없음")
        return
    log(f"  [장넘김] 오른쪽 면에서 장을 넘기는 세트 {len(t)}개 — "
        + ", ".join(f"#{i}(p{a}→p{b})" for i, a, b in t[:6]))


def leaf_breaks(pdf):
    """**장을 넘어 갈라진 문항** — 오른쪽 면에서 시작해 다음 왼쪽 면으로 이어진다.

    단(왼→오른쪽 면 포함)을 넘어 갈라지는 것은 완성본도 하는 일이라 그냥 둔다.
    장을 넘어 갈라진 것만 묶어 통째로 다음 자리로 보낸다.
    """
    fitz = _fitz()
    doc = fitz.open(pdf)
    marks = [m for m in _marks(doc) if m[3] in ("beg", "end")]
    doc.close()
    out = []
    idx = -1
    op = None
    for page, col, _y, kind in marks:
        if kind == "beg":
            idx += 1
            op = (idx, page)
        elif op is not None:
            bidx, bpage = op
            if bpage % 2 == 1 and page > bpage:
                out.append(bidx)
            op = None
    return out
