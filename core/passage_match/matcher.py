"""지문 fingerprint 매처 — 정규화/시퀀스/셔글 containment.

설계 (2026-07 W26):
  1. 정규화: 원문자(①ⓐ 등)·번호 라벨·(A)류 접두 제거, 빈칸(`__`)과
     선택지 괄호(`1[a / b]`, `❮ ⓐ a / ⓑ b ❯`, `(a / b / c)` 낱말은행)를
     갭으로 치환. 한글은 시퀀스에서 투명(silent skip — 번역 삽입 원고에서
     영어 원문 시퀀스가 이어지도록), 토큰 백에는 포함.
  2. 영어 단어 시퀀스에서 w=3 셔글 집합을 만들고 (갭을 넘지 않음),
     비대칭 containment(작은 쪽 ⊂ 큰 쪽)로 변형 ⊂ 원문을 잡는다.
     첫 문장 생략(suffix)도 containment라 자동 커버.
  3. 셔글이 부족한 극단 변형(전 단어 괄호, 한글 번역+낱말은행 스크램블)은
     IDF 가중 토큰 containment + 희귀 토큰 앵커로 보조.

ES3/JSX와 무관한 순수 파이썬 (python3.9 호환).
"""

from __future__ import annotations

import math
import re
import unicodedata


# ── 정규화 패턴 ──────────────────────────────────────────────────────────────

# 원문자: ①-⑳(2460-2473), ⑴-⒇(2474-2487), ⒜-⒵(249C-24B5),
#         Ⓐ-Ⓩ(24B6-24CF), ⓐ-ⓩ(24D0-24E9), ㉑-㉟(3251-325F), ㊱-㊿(32B1-32BF)
_RE_CIRCLED = re.compile("[①-ⓩ㉑-㉟㊱-㊿]")

# 번호 선택지 괄호: "1[learned]", "3[driving / to drive]" (번호는 갭 밖)
_RE_NUM_BRACKET = re.compile(r"\d{1,2}\s*\[([^\[\]]{0,200})\]")
# ❮ ⓐ x / ⓑ y ❯ 어휘 선택 괄호 (❮❯는 항상, <>/〈〉는 " / " 구분이 있을 때만)
_RE_ANGLE = re.compile(r"❮([^❮❯]{0,300})❯")
_RE_ANGLE_GENERIC = re.compile(r"[〈<]([^〈〉<>]{0,300}/[^〈〉<>]{0,300})[〉>]")
# 빈칸: 언더스코어 2+ (박스문자·전각 포함)
_RE_BLANK = re.compile(r"[_＿▁]{2,}")
# 낱말은행/선택 괄호: 괄호 안에 " / " 구분이 있으면 갭 취급
_RE_PAREN_BANK = re.compile(r"\(([^()]{0,400}/[^()]{0,400})\)")
# 문두 라벨 접두: "(A) ", "(a) ", "1. ", "23) ", "[3] " 등 — 줄 시작 기준
_RE_LINE_LABEL = re.compile(
    r"^\s*(?:\(\s*[A-Ea-e]\s*\)|\[[^\]]{1,12}\]|\d{1,2}\s*[.)])\s*",
    re.MULTILINE,
)

_GAP_CH = "\x00"  # 내부 갭 마커

_RE_EN_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_RE_KO_RUN = re.compile(r"[가-힣]+")

# 시퀀스/셔글 파라미터
SHINGLE_W = 3


def _pre_normalize(text):
    """유니코드/타이포 정규화 + 변형 마커의 갭 치환."""
    t = unicodedata.normalize("NFC", text or "")
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("￼", " ")  # 앵커 오브젝트 문자
    # 문두 라벨 접두 제거 ((A)/번호 등)
    t = _RE_LINE_LABEL.sub(" ", t)
    # 원문자 제거 (선지/보기 마커)
    t = _RE_CIRCLED.sub(" ", t)
    return t


def _gap_out(t):
    """선택지 괄호·빈칸을 갭 마커로 치환. 갭 안 내용은 별도 회수용으로 반환."""
    inner_parts = []

    def _keep(m):
        inner_parts.append(m.group(1))
        return " %s " % _GAP_CH

    t = _RE_NUM_BRACKET.sub(_keep, t)
    t = _RE_ANGLE.sub(_keep, t)
    t = _RE_ANGLE_GENERIC.sub(_keep, t)
    t = _RE_PAREN_BANK.sub(_keep, t)
    t = _RE_BLANK.sub(" %s " % _GAP_CH, t)
    return t, inner_parts


def normalize_tokens(text):
    """(seq, en_tokens, ko_tokens) — seq는 갭 경계 리스트[list[str]]."""
    t = _pre_normalize(text)
    t, inner = _gap_out(t)

    # 시퀀스: 갭으로 분할된 각 조각에서 영어 토큰 (한글은 투명 스킵)
    segments = []
    for chunk in t.split(_GAP_CH):
        words = [w.lower() for w in _RE_EN_WORD.findall(chunk)]
        if words:
            segments.append(words)

    # 토큰 백: 본문 + 갭 안 내용 전부
    bag_src = t.replace(_GAP_CH, " ") + " " + " ".join(inner)
    en_tokens = [w.lower() for w in _RE_EN_WORD.findall(bag_src)]
    ko_tokens = _RE_KO_RUN.findall(bag_src)
    return segments, en_tokens, ko_tokens


def _shingles(segments, w=SHINGLE_W):
    out = set()
    for seg in segments:
        if len(seg) >= w:
            for i in range(len(seg) - w + 1):
                out.add(tuple(seg[i:i + w]))
    return out


class Fingerprint(object):
    __slots__ = ("shingles", "en_set", "ko_set", "bag", "n_en", "n_seq")

    def __init__(self, shingles, en_set, ko_set, bag, n_en, n_seq):
        self.shingles = shingles
        self.en_set = en_set
        self.ko_set = ko_set
        self.bag = bag          # en+ko 통합 토큰 집합 (IDF 가중용)
        self.n_en = n_en        # 영어 토큰 수 (중복 포함)
        self.n_seq = n_seq      # 시퀀스(갭 밖) 영어 토큰 수

    def is_tiny(self):
        return self.n_en < 4 and len(self.ko_set) < 4


def fingerprint(text):
    segments, en_tokens, ko_tokens = normalize_tokens(text)
    en_set = set(en_tokens)
    ko_set = set(ko_tokens)
    return Fingerprint(
        shingles=_shingles(segments),
        en_set=en_set,
        ko_set=ko_set,
        bag=en_set | ko_set,
        n_en=len(en_tokens),
        n_seq=sum(len(s) for s in segments),
    )


# ── 페어 스코어 ──────────────────────────────────────────────────────────────

class PairScore(object):
    __slots__ = ("shingle_cont", "token_cont", "anchors", "min_shingles")

    def __init__(self, shingle_cont, token_cont, anchors, min_shingles):
        self.shingle_cont = shingle_cont
        self.token_cont = token_cont
        self.anchors = anchors
        self.min_shingles = min_shingles

    def __repr__(self):
        return "PairScore(sh=%.3f/%d, tok=%.3f, anc=%d)" % (
            self.shingle_cont, self.min_shingles, self.token_cont, self.anchors)


def build_idf(fps):
    """컬렉션(fingerprint 리스트)에서 토큰 df → idf 가중치 사전."""
    df = {}
    for fp in fps:
        for t in fp.bag:
            df[t] = df.get(t, 0) + 1
    n = max(len(fps), 2)
    idf = {}
    for t, c in df.items():
        idf[t] = math.log(1.0 + float(n) / c)
    return idf


_MIN_CHANNEL_TOKENS = 4   # 채널 유효 최소 토큰 수 (작은 쪽) — is_tiny 경계와 정렬
_MIN_DISC_TOKENS = 4      # 채널 유효 최소 판별 토큰 수 (idf 하한 이상)
IDF_DISC = 1.0            # 판별 토큰 idf 하한 — df가 컬렉션 절반 이하일 때 통과.
                          # 발문/보기류 보일러플레이트(df≈N, idf≈0.69)는 배제된다.


def _channel_containment(sa, sb, idf):
    """단일 채널 토큰 집합 containment — 작은 쪽 기준 (변형 ⊂ 원문).

    idf가 있으면 판별 토큰(idf >= IDF_DISC)만으로 계산한다. 보일러플레이트만
    공유하는 쌍은 '전부 일치'여도 판별 토큰이 없어 채널 무효(None)가 된다.
    """
    small, large = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if len(small) < _MIN_CHANNEL_TOKENS:
        return None
    if idf is None:
        return float(len(small & large)) / len(small)
    w_small = 0.0
    w_inter = 0.0
    n_disc = 0
    for t in small:
        w = idf.get(t, IDF_DISC)
        if w < IDF_DISC:
            continue
        n_disc += 1
        w_small += w
        if t in large:
            w_inter += w
    if n_disc < _MIN_DISC_TOKENS:
        return None
    return (w_inter / w_small) if w_small > 0 else 0.0


def _weighted_containment(fa, fb, idf):
    """EN 채널 토큰 containment.

    한글 번역+영어 낱말은행 변형(step2_c2류)도 은행 안 영단어가 원문 단어
    그대로라 EN 채널로 원문과 붙는다. 통합(EN+KO) 백은 한글이 희석시켜
    recall이 떨어지고, KO 채널 단독은 같은 발문 유형의 보일러플레이트가
    컬렉션 수준에선 희귀해 IDF 필터를 뚫는 FP를 만든다 (W26 실측 — 둘 다
    기각, EN 단독 채택)."""
    ch = _channel_containment(fa.en_set, fb.en_set, idf)
    return 0.0 if ch is None else ch


def _anchor_count(fa, fb, idf, idf_floor):
    """희귀(고IDF) 영어 토큰 앵커 수 — 길이 5+ 저빈도 토큰의 공유 수."""
    shared = fa.en_set & fb.en_set
    n = 0
    for t in shared:
        if len(t) >= 5 and (idf is None or idf.get(t, 99.0) >= idf_floor):
            n += 1
    return n


def pair_score(fa, fb, idf=None, idf_floor=1.0):
    sa, sb = fa.shingles, fb.shingles
    m = min(len(sa), len(sb))
    sh = (float(len(sa & sb)) / m) if m > 0 else 0.0
    tok = _weighted_containment(fa, fb, idf)
    anc = _anchor_count(fa, fb, idf, idf_floor)
    return PairScore(sh, tok, anc, m)


# ── 판정 임계 (코퍼스 실측 튜닝 결과 — tests/test_passage_match.py 가드) ────

TH_SHINGLE = 0.30        # 셔글 containment 단독 판정 (클린 음성 최대 0.090 — 3.3x 마진)
MIN_SHINGLES = 5         # 셔글 판정에 필요한 최소 셔글 수 (작은 쪽)
TH_TOKEN = 0.45          # IDF 가중 EN 토큰 containment 판정 (클린 음성 최대 0.393)
MIN_ANCHORS = 5          # 토큰 판정에 요구하는 희귀 앵커 수
TH_TOKEN_TINY = 0.80     # 셔글이 거의 없는 극소 지문의 토큰 판정


def is_same_passage(fa, fb, idf=None, th_shingle=TH_SHINGLE,
                    th_token=TH_TOKEN, min_anchors=MIN_ANCHORS):
    if fa.is_tiny() or fb.is_tiny():
        return False
    sc = pair_score(fa, fb, idf)
    if sc.min_shingles >= MIN_SHINGLES and sc.shingle_cont >= th_shingle:
        return True
    if sc.token_cont >= th_token and sc.anchors >= min_anchors:
        return True
    # 극소 텍스트(셔글 부족)는 토큰 상향 임계 + 앵커 1+
    if sc.min_shingles < MIN_SHINGLES and sc.token_cont >= TH_TOKEN_TINY \
            and sc.anchors >= 1:
        return True
    return False


# ── 그룹핑 (매치 그래프 + 허브 배제 + union-find) ───────────────────────────

HUB_MIN_DEGREE = 4        # 허브 판정 최소 이웃 수
HUB_CONNECTIVITY = 0.5    # 이웃 간 연결율이 이 미만이면 허브

def build_match_graph(fps, idf=None, **kw):
    """fingerprint 리스트의 페어와이즈 매치 그래프 → 인접 집합 리스트."""
    if idf is None:
        idf = build_idf(fps)
    n = len(fps)
    adj = [set() for _ in range(n)]
    for i in range(n):
        if fps[i].is_tiny():
            continue
        for j in range(i + 1, n):
            if fps[j].is_tiny():
                continue
            if is_same_passage(fps[i], fps[j], idf, **kw):
                adj[i].add(j)
                adj[j].add(i)
    return adj


def detect_hubs(adj):
    """여러 지문을 통째로 담은 '허브' 노드 감지 → 인덱스 집합.

    허브(전체 정답해설 blob 등)는 서로 다른 지문 유닛 다수와 containment로
    붙어 추이적 그룹핑을 한 덩어리로 붕괴시킨다. 판정: 이웃이 4+개인데
    이웃끼리는 대부분 연결돼 있지 않으면(연결율 < 0.5) 허브.
    정상 유닛의 이웃(같은 지문의 다른 변형들)은 서로도 붙어 연결율이 높다.
    """
    hubs = set()
    for v, nb in enumerate(adj):
        deg = len(nb)
        if deg < HUB_MIN_DEGREE:
            continue
        possible = deg * (deg - 1) // 2
        connected = 0
        nb_list = sorted(nb)
        for ai in range(len(nb_list)):
            a = nb_list[ai]
            connected += len(adj[a] & nb)
        connected //= 2
        if float(connected) / possible < HUB_CONNECTIVITY:
            hubs.add(v)
    return hubs


def group_fingerprints(fps, idf=None, **kw):
    """fingerprint 리스트 그룹핑 → (groups, hubs).

    groups: 인덱스 그룹 리스트 (첫 등장 순, 그룹 내 오름차순).
    hubs: 허브로 배제된 인덱스 집합 — 각자 단독 그룹으로도 포함된다.
    """
    if idf is None:
        idf = build_idf(fps)
    adj = build_match_graph(fps, idf, **kw)
    hubs = detect_hubs(adj)
    n = len(fps)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        if i in hubs:
            continue
        for j in adj[i]:
            if j <= i or j in hubs:
                continue
            ra, rb = find(i), find(j)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

    groups = {}
    order = []
    for i in range(n):
        r = find(i)
        if r not in groups:
            groups[r] = []
            order.append(r)
        groups[r].append(i)
    return [groups[r] for r in order], hubs


def group_items(texts, idf=None, **kw):
    """텍스트 리스트를 같은 지문 그룹으로 묶는다 → 인덱스 그룹 리스트.

    idf 미지정 시 입력 컬렉션에서 자동 계산. 허브(여러 지문 포함 blob)는
    단독 그룹으로 남는다. tiny 항목도 단독 그룹.
    """
    groups, _hubs = group_fingerprints(
        [fingerprint(t) for t in texts], idf, **kw)
    return groups
