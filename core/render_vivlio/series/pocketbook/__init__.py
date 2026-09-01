# -*- coding: utf-8 -*-
"""포켓북 계열 — 지문 DB → A5 포켓북 내지.

다른 계열과 하나가 다르다. **책이 원고가 아니라 지문 DB(코퍼스)에서 만들어진다.**
그래서 `gen_data` 는 원고를 파는 대신 코퍼스에서 지문을 골라 온다.

지면(실측, 148×210 + 도련 3mm):
    짝(왼쪽)  지문번호 배지 · 구문분석 영어 지문 · PICTURE(삽화) · TRANSLATION
    홀(오른쪽) FLOW NOTE · 주제/요약문 · 동반의어 9칸
    (필요하면) 암기 TEST 문제 · 정답

배치는 **삽화 유무**가 가른다(원본이 마스터 A/C/E 로 나눠 놓은 그대로).
지문이 지면보다 길면 **실측 후 축소**한다 — 추정 공식으로는 안 맞는다.
"""
import json
import re
import os
import shutil

from core.render_vivlio import bleed, cli, knobs, measure, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.pocketbook import data as pdata
from core.render_vivlio.series.pocketbook import memtest as pmemtest
from core.render_vivlio.series.pocketbook import render as prender
from core.render_vivlio.series.pocketbook import theme as ptheme

FONTS = [
    "NotoSansCJKkr-Regular.otf", "NotoSansCJKkr-Medium.otf",
    "NotoSansCJKkr-Bold.otf", "EliceDXNeolliOTF-Bold.otf",
    "EliceDXNeolliOTF-Medium.otf", "HakgyoansimUndongjangOTFL.otf",
    "KCCDodamdodam_OTF.otf", "JalnanOTF.otf",
]

_SPAN_CACHE = {}


def _all_spans(page):
    """한 면의 글자 조각. **면마다 한 번만** 뽑는다.

    ⚠ 검사마다 `get_text("dict")` 를 다시 부르면 그림이 많은 책에서 검수가
      분 단위로 늘어진다(한영1 248면·40MB 에서 18분 넘게 걸렸다).
    ⚠⚠ 열쇠에 `id(문서)` 를 쓰면 안 된다. 앞 책의 문서가 닫히면 파이썬이 그
      **주소를 다음 문서에 다시 준다** — 그러면 앞 책의 글자가 뒤 책 검사에
      쓰여 멀쩡한 책이 "글자 유실 24지문"으로 떨어진다(세종1에서 그렇게 났다).
      파일 경로로 열쇠를 잡고, 검수를 시작할 때 비운다.
    """
    try:
        doc = page.parent.name or ""
    except Exception:
        doc = ""
    key = (doc, page.number)
    got = _SPAN_CACHE.get(key)
    if got is None:
        got = [sp for b in page.get_text("dict")["blocks"] if b["type"] == 0
               for l in b["lines"] for sp in l["spans"]]
        if len(_SPAN_CACHE) > 400:
            _SPAN_CACHE.clear()
        _SPAN_CACHE[key] = got
    return got


def _spans(page, lo, hi):
    for sp in _all_spans(page):
        if lo <= sp["size"] <= hi:
            yield sp


_RE_VER = re.compile(r"(분석본\s*\d+)")


def _dedup_versions(files, log=None):
    """같은 분석본의 판본이 여럿이면 **가장 최근 것 하나만** 쓴다.

    폴더에 `…분석본01(26년6월)_내지.indd` 와 `…분석본01(26년6월)_내지 제목수정.indd`
    가 같이 있다(실제로 있다). 둘 다 읽으면 지문이 **두 배로** 실린다 —
    조판은 성공하고 쪽수만 늘어서 눈으로 잡기 전까지 모른다.
    """
    import unicodedata
    groups = {}
    for f in files:
        base = unicodedata.normalize("NFC", os.path.basename(f))
        m = _RE_VER.search(base)
        school = os.path.basename(os.path.dirname(f))
        key = (school, m.group(1).replace(" ", "") if m else base)
        groups.setdefault(key, []).append(f)
    out, dropped = [], []
    for key, fs in sorted(groups.items()):
        fs.sort(key=lambda x: (os.path.getmtime(x), len(x)))
        out.append(fs[-1])
        dropped += fs[:-1]
    if dropped and log:
        log("  [판본 중복] %d개 제외 — %s"
            % (len(dropped),
               ", ".join(unicodedata.normalize("NFC", os.path.basename(d))
                         for d in dropped[:4])))
    return sorted(out)


_RE_YM = re.compile(r"(\d{2})\s*년\s*(\d{1,2})\s*월")
_RE_NO = re.compile(r"(\d{1,2})\s*[-~]?\s*(\d{1,2})?\s*번")
_RE_GR = re.compile(r"고\s*([123])")
_RE_UNIT = re.compile(r"(\d{1,2})\s*과")
_RE_BODY = re.compile(r"본문\s*(\d{1,2})")


def _derive_pno(p):
    """분석본 지문 → 지문번호 `YYMMNN`·학년.

    분석본은 회차를 **책 머리(chapter)** 에 적고 지문에는 번호만 적는다
    (`chapter='고2 26년 6월'` + `label='20번'`). 삽화는 `<학년>/<YY년 M월>/<번호>.jpg`
    로 찾으므로 여기서 합쳐 두지 않으면 모의고사 삽화가 하나도 안 붙는다.
    """
    if p.get("pno"):
        return p
    ch = p.get("chapter") or ""
    lb = p.get("label") or ""
    m = _RE_YM.search(ch) or _RE_YM.search(lb)
    n = _RE_NO.search(lb) or _RE_NO.search(ch)
    if m and n:
        p["pno"] = "%s%02d%02d" % (m.group(1), int(m.group(2)), int(n.group(1)))
        if n.group(2):
            p["pno_end"] = "%s%02d%02d" % (m.group(1), int(m.group(2)),
                                           int(n.group(2)))
    g = _RE_GR.search(ch)
    if g:
        p["grade"] = "고%s" % g.group(1)

    # 교과서 지문의 배지는 완성본이 `4과 01` 로 찍는다. 분석본은 회차를 머리에,
    # 순번을 지문에 나눠 적으므로(`chapter='1과'` + `label='본문1'`) 합친다.
    # 안 합치면 배지가 `본문1` 로 나가 지금까지 나간 책과 달라 보인다.
    m2 = _RE_UNIT.search(ch)
    n2 = _RE_BODY.search(lb)
    if m2 and n2 and not p.get("pno"):
        p["label"] = "%s과 %02d" % (m2.group(1), int(n2.group(1)))
        p.setdefault("unit", "교과서 %s과" % m2.group(1))
    elif p.get("pno"):
        p.setdefault("unit", "모의고사")
    elif m2:
        p.setdefault("unit", "교과서 %s과" % m2.group(1))
    return p


_RE_LEC = re.compile(r"(\d{1,2})\s*강")
_RE_ONLY_NO = re.compile(r"^\s*(\d{1,2})\s*번\s*$")


def _carry_lecture(items):
    """`11강 1번` 다음에 오는 `2번`·`3번` 에 강 번호를 이어 붙인다.

    분석본은 강을 첫 지문에만 적고 그다음은 번호만 적는다. 그대로 두면 배지가
    `11강 1번` 다음에 `2번` 으로 나가 무엇의 2번인지 알 수 없다. 완성본은
    `11강 02` 처럼 강을 매번 적는다.
    """
    lec = ""
    for it in items:
        lb = it.get("label") or ""
        m = _RE_LEC.search(lb) or _RE_LEC.search(it.get("chapter") or "")
        if m:
            lec = m.group(1)
        n = _RE_ONLY_NO.match(lb)
        if n and lec:
            it["label"] = "%s강 %02d" % (lec, int(n.group(1)))
            it.setdefault("unit", "%s강" % lec)
        elif m and _RE_ONLY_NO.match(_RE_LEC.sub("", lb).strip() or "x"):
            k = re.search(r"(\d{1,2})\s*번", lb)
            if k:
                it["label"] = "%s강 %02d" % (lec, int(k.group(1)))
                it.setdefault("unit", "%s강" % lec)
    return items


def _grade_of(school):
    """학교 이름 끝 숫자가 학년이다(`상일2` → 고2). 삽화 폴더가 학년별이라 필요하다."""
    import re as _re
    m = _re.search(r"([123])\s*$", school or "")
    return "고%s" % m.group(1) if m else ""


def _text(runs):
    return "".join(r["t"] for r in runs)


def _bag(s):
    import collections
    import re as _re
    return collections.Counter(
        _re.sub(r"[^0-9A-Za-z가-힣]", "", s).lower())


def _page_bag(page, size, tol=0.6):
    return _bag("".join(sp["text"] for sp in _spans(page, size - tol,
                                                   size + tol)))


def _count_size(page, size, tol=0.4):
    """그 크기의 글자 **덩어리** 수. 주석은 7pt 라 본문과 안 겹친다.

    ⚠ 서체 이름으로 세면 안 된다 — Vivliostyle 출력은 이름이 `Type3` 로 바뀌어
      아무것도 못 찾고 조용히 통과한다.
    """
    return sum(1 for _ in _spans(page, size - tol, size + tol))


def _inks(page):
    """그 면에 쓰인 글자색 모음. 암기 TEST 두 면을 가르는 데 쓴다."""
    return frozenset(sp["color"] for sp in _spans(page, 0, 999))


def _lowest(page, size, tol=0.6):
    """그 크기 글자의 가장 아래 기준선(mm). 없으면 None."""
    ys = [sp["origin"][1] for sp in _spans(page, size - tol, size + tol)]
    return max(ys) / (72 / 25.4) if ys else None


MIN_SCALE = 0.834       # 9pt → 7.5pt. 원본 resolveOverflow 하한과 같다
MIN_LEAD = 14.0         # pt. 원본 하한
SUP_SIZE = 5.5          # pt — theme.css `.n`(위첨자). 지문 배율을 안 따라간다


class PocketbookSeries(Series):
    name = "pocketbook"
    display = "포켓북"
    theme = ""              # 계열이 CSS 를 생성한다

    # 미리보기(작업대)는 **지면을 보는 자리**다. 실측 패스(면마다 한 번씩 조판)는
    # 디자인을 보는 데 필요 없고 느리기만 하다 — 껐다.
    render_opts = {"measure_pass": False}

    # ── 손잡이 — 실제로 시안 왕복이 났던 자리만 ──
    def knobs(self, cfg):
        K = knobs.Knob
        P, M = ptheme.PALETTE, ptheme.METRICS
        col = lambda key, label, affects, g="색": K(          # noqa: E731
            "palette." + key, "color", label, default=P[key],
            affects=affects, group=g)
        num = lambda key, label, lo, hi, unit, affects, step=0.1, g="치수": K(
            "metrics." + key, "mm" if unit == "mm" else "pt", label,
            default=M[key], min=lo, max=hi, step=step, unit=unit,
            affects=affects, group=g)                          # noqa: E731
        return [
            col("navy", "지문번호 배지", "왼쪽 면 배지 · 쪽번호"),
            col("band", "위·아래 띠", "모든 면 머리·발치 띠"),
            col("chip", "PICTURE·TRANSLATION 칩", "왼쪽 면 칩 · 괘선"),
            col("blue", "강조 파랑", "구문분석 파란 낱말"),
            col("red", "강조 빨강", "구문분석 빨간 낱말"),
            col("anno", "구문분석 주석", "낱말 위·아래 작은 글씨"),
            col("trans", "한글 해석", "왼쪽 면 번역"),
            col("card1", "동반의어 1열", "오른쪽 면 카드", "동반의어"),
            col("card2", "동반의어 2열", "오른쪽 면 카드", "동반의어"),
            col("card3", "동반의어 3열", "오른쪽 면 카드", "동반의어"),
            col("syn_syn", "유의어 글자", "카드 `=` 줄", "동반의어"),
            col("syn_ant", "반의어 글자", "카드 `↔` 줄", "동반의어"),
            col("flow_arrow", "플로우 화살표 줄", "오른쪽 면 플로우노트", "플로우"),
            num("passage_size", "지문 글자", 7.5, 10.5, "pt",
                "구문분석 영어 지문", 0.25),
            num("passage_lead", "지문 행간", 14, 30, "pt",
                "지문 줄 간격 (주석 자리)", 0.5),
            num("passage_track", "지문 자간", -0.05, 0.01, "em",
                "지문 낱말 사이 · 행바꿈", 0.002),
            num("trans_size", "번역 글자", 5, 8, "pt", "왼쪽 면 번역", 0.1),
            num("card_size", "동반의어 글자", 6, 8, "pt",
                "카드 글자", 0.1, "동반의어"),
            num("flow_size", "플로우노트 글자", 6, 9, "pt",
                "오른쪽 면 플로우노트", 0.1, "플로우"),
        ]

    style_names = {
        "passage": "구문분석 영어 지문",
        "translation": "한글 해석",
        "flow": "플로우노트",
        "card": "동반의어 카드",
        "badge": "지문번호 배지",
        "memtest": "암기 TEST",
    }

    # ── ① 코퍼스 → data.json ──
    def gen_data(self, cfg, log):
        """코퍼스에서 수록 지문을 고른다.

        키를 손으로 나열해도 되고(`options.passages`), 학교·학기로 골라도 된다
        (`options.school`·`options.term`). 뒤쪽이 실제 작업에 가깝다 —
        "상일2 26-2 중간 포켓북" 이라고 말하지 지문 키를 외우지 않는다.
        """
        opt = cfg.section("options") or {}
        corpus = cfg.resolve(opt.get("corpus")
                             or "${STUDIO}/조판/교재/포켓북/_corpus")
        keys = list(opt.get("passages") or [])
        # ⚠ `school` 만으로 코퍼스를 고르면 **모든 학기**가 딸려 온다.
        #   학교 이름은 학년(삽화 폴더)에도 쓰이므로, 코퍼스 선택은 `term` 이
        #   있을 때만 한다. 신규 지문만 조판하는 책은 term 을 비워 두면 된다.
        if not keys and (opt.get("term") or opt.get("units")):
            keys = self._pick(corpus, opt, log)
        rows, missing = [], []
        rows += self._from_analysis(cfg, opt, log)
        for k in keys:
            # 인덱스 키(`강동1:25-2:3과-04`)와 파일명(`강동1__25-2__3과-04.json`)이
            # 다르다 — 인덱스가 알려 주는 파일명을 쓴다.
            f = k if k.endswith(".json") else os.path.join(corpus, "%s.json" % k)
            if not os.path.isabs(f):
                f = os.path.join(corpus, os.path.basename(f))
            if not os.path.exists(f):
                missing.append(k)
                continue
            with open(f, encoding="utf-8") as fh:
                rows.append(json.load(fh))
        if missing:
            raise ValueError(
                "코퍼스에 없는 지문 %d개: %s\n"
                "  → 분석본에서 먼저 수확하거나 키를 확인할 것"
                % (len(missing), ", ".join(missing[:10])))
        if not rows:
            raise ValueError(
                "수록할 지문이 없다 — options 에 passages·school/term·analysis "
                "중 하나는 있어야 한다")
        self._apply_manuscript(cfg, opt, rows, log)
        rows = self._apply_memtest(cfg, opt, rows, log)
        out = os.path.join(cfg.build_dir, "data.json")
        os.makedirs(cfg.build_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"passages": rows}, fh, ensure_ascii=False)
        log("■ 지문 %d개" % sum(1 for r in rows if r.get("kind") != "memtest"))
        return out

    # ── 새 지문: 분석본에서 ──
    @staticmethod
    def _tools():
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(here))))
        t = os.path.join(repo, "tools", "pocket_harvest")
        if t not in sys.path:
            sys.path.insert(0, t)
        return t

    def _from_analysis(self, cfg, opt, log):
        """`options.analysis` 의 분석본 IDML → 새 지문.

        코퍼스에 없는 **이번 학기 신규 지문**이 들어오는 자리다. 분석본에는
        플로우노트·동반의어가 없으므로 비어서 들어오고, 원고(hwpx)가 채운다.
        둘 다 없으면 G-P2 가 목록으로 알려 준다.
        """
        srcs = cfg.resolve(opt.get("analysis") or [])
        if isinstance(srcs, str):
            srcs = [srcs]
        files = []
        for sfile in srcs:
            if os.path.isdir(sfile):
                for root, _d, fs in os.walk(sfile):
                    files += [os.path.join(root, f) for f in sorted(fs)
                              if f.lower().endswith(".idml")]
            elif os.path.exists(sfile):
                files.append(sfile)
        if not files:
            return []
        files = _dedup_versions(files, log)
        self._tools()
        import analysis
        out = []
        for f in files:
            got = analysis.read_book(f)
            for g in got:
                _derive_pno(g)
            _carry_lecture(got)
            out += got
            log("■ 분석본 %s — 지문 %d" % (os.path.basename(f), len(got)))
        return out

    # ── 플로우노트·동반의어: 교재팀 원고에서 ──
    def _apply_manuscript(self, cfg, opt, rows, log):
        """`options.manuscript` 의 hwpx → 지문에 플로우·주제·동반의어를 얹는다.

        원고 키(`24-9 21번 Flow`·`명일2 4과 본문2`)와 지문 키를 **느슨하게** 맞춘다
        — 표기가 학교마다 다르므로 숫자만 남긴 형태로도 한 번 더 본다.
        """
        srcs = cfg.resolve(opt.get("manuscript") or [])
        if isinstance(srcs, str):
            srcs = [srcs]
        files = [f for f in srcs if os.path.exists(f)
                 and f.lower().endswith((".hwpx", ".hwp"))]
        for d in [x for x in srcs if os.path.isdir(x)]:
            files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                      if f.lower().endswith(".hwpx")]
        if not files:
            return
        self._tools()
        import unicodedata
        import manuscript
        frags = []
        for f in files:
            got = manuscript.parse(f)
            frags += got
            log("■ 원고 %s — 블록 %d" % (os.path.basename(f), len(got)))

        def canon(text):
            """지문 키를 **구조**로 정규화한다.

            원고와 지문이 같은 것을 다르게 부른다:
              `24-9 21번 Flow` · `25년 9월 23번` · `250923`  → 모의고사 (yy,mm,nn)
              `1과 본문1` · `미래엔김 1과 본문1` · `1과 01`   → 교과서 (과,순번)
            글자를 맞추려 하면 학교마다 깨진다 — 무엇을 가리키는지로 맞춘다.
            """
            t = unicodedata.normalize("NFC", str(text or ""))
            m = re.search(r"(\d{2})\s*[-년]\s*(\d{1,2})\s*월?\s*"
                          r"(\d{1,2})\s*번", t)
            if m:
                return "M%s%02d%02d" % (m.group(1), int(m.group(2)),
                                        int(m.group(3)))
            m = re.fullmatch(r"\s*(\d{6})\s*", re.sub(r"[^0-9]", "", t)[:6]
                             if re.fullmatch(r"[0-9]{6,8}", re.sub(r"\s", "", t))
                             else "")
            if m:
                return "M" + m.group(1)
            u = re.search(r"(\d{1,2})\s*과", t)
            n = re.search(r"본문\s*(\d{1,2})", t) or re.search(
                r"과\s*(\d{1,2})\b", t)
            if u and n:
                return "T%s-%02d" % (u.group(1), int(n.group(1)))
            return "X" + re.sub(r"[^0-9a-z가-힣]", "", t.lower())

        by_key = {}
        for fr in frags:
            by_key.setdefault(canon(fr["key_raw"]), fr)

        used, hit = set(), 0
        for r in rows:
            fr = None
            for c in (r.get("pno"), r.get("label"), r.get("key")):
                if not c:
                    continue
                fr = by_key.get(canon(c))
                if fr:
                    break
            if fr is None:
                continue
            used.add(id(fr))
            hit += 1
            if fr.get("flow") and not r.get("flownote"):
                r["flownote"] = fr["flow"]
            if fr.get("synonyms") and not r.get("synonyms"):
                r["synonyms"] = fr["synonyms"]
            if fr.get("topic") and not r.get("topic"):
                r["topic"] = fr["topic"]
            if fr.get("summary") and not r.get("summary"):
                r["summary"] = fr["summary"]
        orphan = [f["key_raw"] for f in frags if id(f) not in used]
        log("■ 원고 %d블록 중 %d개가 지문에 붙었다" % (len(frags), hit))
        if orphan:
            # 조용히 버리면 원고를 쓴 사람이 영영 모른다.
            log("  [원고 미사용] %d개 — %s"
                % (len(orphan), ", ".join(orphan[:8])))

    # ── 암기 TEST: 리뷰테스트 원고에서 ──
    @staticmethod
    def _apply_memtest(cfg, opt, rows, log):
        """`options.review_tests` 의 리뷰테스트 원고 → 암기 TEST 문제·정답 면.

        수확한 책은 이미 암기테스트를 갖고 있다(`kind == "memtest"` 항목).
        그때는 원고를 다시 파지 않는다 — 완성본에 사람이 손댄 판이 있으면
        그쪽이 정본이기 때문이다.
        """
        srcs = cfg.resolve(opt.get("review_tests") or [])
        if isinstance(srcs, str):
            srcs = [srcs]
        if not srcs:
            return rows
        if any(r.get("kind") == "memtest" for r in rows):
            log("■ 암기 TEST 는 수확본에 이미 있다 — 리뷰테스트 원고는 건너뛴다")
            return rows
        return pmemtest.attach(rows, srcs, log,
                               place=opt.get("memtest_place", "auto"),
                               cache=PocketbookSeries._memtest_cache(cfg, opt))

    @staticmethod
    def _memtest_cache(cfg, opt):
        """리뷰테스트 원고를 다시 안 읽기 위한 캐시 자리.

        **책 폴더가 아니라 교재 폴더에 둔다.** 아침에 학교를 연달아 돌리는데
        권마다 따로 캐시하면 매번 10초를 다시 낸다 — 원고는 학교와 무관하게
        같은 폴더 하나다. `_corpus` 안에 두면 코퍼스 스캔에 섞이므로 옆에 둔다.
        """
        p = cfg.resolve(opt.get("memtest_cache") or "")
        if p:
            return p
        corpus = cfg.resolve(opt.get("corpus")
                             or "${STUDIO}/조판/교재/포켓북/_corpus")
        return os.path.join(os.path.dirname(os.path.normpath(corpus)),
                            "_cache", "memtest.json")

    @staticmethod
    def _pick(corpus, opt, log):
        """학교·학기(·단원)로 코퍼스에서 지문 키를 고른다. 순서는 인덱스 순."""
        idx_path = os.path.join(corpus, "_index.json")
        if not os.path.exists(idx_path):
            raise ValueError("코퍼스 인덱스가 없다: %s\n"
                             "  → tools/pocket_harvest/corpus.py build" % idx_path)
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        rows = idx.get("passages") if isinstance(idx, dict) else idx
        if isinstance(rows, dict):
            rows = [dict(v, key=k) for k, v in rows.items()]
        # ⚠ 쪽 번호를 **글자로** 정렬하면 `"10-11" < "12-13" < "2-3" < "26-27"` 이
        #   되어 지문 차례가 통째로 뒤섞인다(교과서와 모의고사가 섞여 나온다).
        #   숫자로 정렬한다. 쪽을 모르면 맨 뒤로.
        school = opt.get("school")
        term = opt.get("term")
        units = set(opt.get("units") or [])

        # ⚠ 같은 지문이 여러 학교에 나오면 코퍼스는 **하나로 병합**한다(원문 동일
        #   병합 402건). 그런데 `school`·`term` 은 **먼저 만난 책 것만** 남는다 —
        #   그것만 보면 뒤에 나온 학교에서 지문이 통째로 빠진다(세종1 47→31).
        #   지문이 실렸던 **모든 책 경로**(`books`/`where`)로도 본다.
        def places(r):
            out = set()
            if r.get("school"):
                out.add((r.get("term") or "", r["school"]))
            for w in (r.get("where") or []):
                f = w.get("file") or ""
                parts = f.split("/")
                if len(parts) >= 2:
                    out.add((parts[0], parts[1]))
            for f in (r.get("books") or []):
                parts = f.split("/")
                if len(parts) >= 2:
                    out.add((parts[0], parts[1]))
            return out

        def page_of(r):
            """이 책에서의 쪽 번호. 병합본은 학교마다 쪽이 다르다."""
            best = None
            for w in (r.get("where") or []):
                f = w.get("file") or ""
                parts = f.split("/")
                hit = (len(parts) >= 2
                       and (not school or parts[1] == school)
                       and (not term or parts[0] == term))
                m = re.match(r"\s*(\d+)", str(w.get("pages", "")))
                if not m:
                    continue
                v = int(m.group(1))
                if hit:
                    return v
                if best is None:
                    best = v
            return best if best is not None else 10 ** 6

        out = []
        for r in rows:
            if school or term:
                ok = False
                for t, sc in places(r):
                    if school and sc != school:
                        continue
                    if term and t != term:
                        continue
                    ok = True
                    break
                if not ok:
                    continue
            if units and r.get("unit") not in units:
                continue
            out.append(r)
        out.sort(key=page_of)
        out = [r.get("file") or (r["key"] + ".json") for r in out]
        if not out:
            raise ValueError(
                "고른 지문이 없다 (school=%s term=%s units=%s)"
                % (school, term, sorted(units)))
        log("■ 코퍼스에서 %d지문 선택" % len(out))
        return out

    # ── 작업대가 읽을 자료 ──
    STUDIO_DATA = "_studio_data.json"

    def data_path(self, cfg):
        """작업대가 글을 읽고 고칠 **자료 파일**.

        이 계열은 원고(코퍼스)에서 바로 지면을 만들어 책 폴더에 `data.json` 이
        없었다 — 그래서 작업대에서 글을 클릭하면 "원고에서 바로 조판해 글을
        여기서 못 고칩니다" 였다.

        조판할 때 **자리표가 가리키는 그 목록**(`prepare()` 를 지난 것)을
        `build/_studio_data.json` 으로 남긴다. 자리표(`passages.3.…`)와 자리가
        정확히 같으므로 그대로 고칠 수 있다.

        ⚠ 이 파일은 **편집을 얹기 전** 것이다. 얹은 뒤를 남기면 다음 조판에서
          또 얹혀 두 번 먹는다(넣기·지우기는 특히 티가 크다).
        """
        return os.path.join(cfg.build_dir, self.STUDIO_DATA)

    # ── ② 테마 ──
    def gen_theme(self, cfg, log):
        css = ptheme.build_css(cfg.section("palette"),
                               cfg.section("metrics"),
                               (cfg.section("palette") or {}).get("highlight"))
        os.makedirs(cfg.build_dir, exist_ok=True)
        p = os.path.join(cfg.build_dir, "pocket.css")
        with open(p, "w", encoding="utf-8") as f:
            f.write(css)
        return p

    # ── ③ 조판 ──
    def build(self, cfg, log, measure_pass=True, **opts):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        stage.stage_fonts(build_dir, cfg.get("fonts") or FONTS, required=True)
        self._stage_assets(build_dir)
        self.gen_theme(cfg, log)

        data_path = os.path.join(build_dir, "data.json")
        if not os.path.exists(data_path):
            self.gen_data(cfg, log)
        with open(data_path, encoding="utf-8") as f:
            raw = json.load(f)["passages"]

        opt = cfg.section("options") or {}
        rows = pdata.prepare(
            raw, build_dir,
            illust_dirs=cfg.resolve(opt.get("illust_dirs") or []),
            category=opt.get("category", ""),
            grade=opt.get("grade") or _grade_of(opt.get("school", "")))
        # 작업대가 볼 자료 = **자리표가 가리키는 그 목록**. 편집을 얹기 전에
        # 남기고, 얹은 것으로 조판한다.
        from core.render_vivlio import edits as _ed
        with open(self.data_path(cfg), "w", encoding="utf-8") as f:
            json.dump({"passages": rows}, f, ensure_ascii=False)
        _st = _ed.read(cfg)
        if _st["head"]:
            # ⚠ 같은 목록 객체를 그대로 고친다(사본을 만들면 조판이 옛 글을 본다)
            _ed.apply_all({"passages": rows}, _st, log)
        from core.render_vivlio import refs as _refs2
        _refs2.set_classes(_ed.classes(_st))     # 단락 스타일도 이 계열에서

        M = dict(ptheme.METRICS)
        M.update(cfg.section("metrics") or {})

        if measure_pass:
            self._fit(rows, M, build_dir, log)
            self._fit_memtest(rows, M, build_dir, log)
            self._fit_right(rows, M, build_dir, log)

        html = os.path.join(build_dir, "index.html")
        with open(html, "w", encoding="utf-8") as f:
            f.write(prender.build_html({
                "title": (cfg.book or {}).get("title", "포켓북"),
                "passages": rows, "metrics": cfg.section("metrics"),
                "folio_start": opt.get("folio_start", 2),
                "cover": None}))
        # ⚠ 자리표를 **파일로 내지 않으면** 지면에 표가 찍혀도 작업대는 그것을
        #   못 되짚는다 — 눌러도 조용히 아무 일이 안 난다(실제로 그랬다).
        try:
            from core.render_vivlio import refs as _refs3
            _refs3.dump(build_dir)
        except Exception:
            pass
        # 검수가 다시 계산하지 않도록 조판에 쓴 값을 그대로 남긴다.
        with open(os.path.join(build_dir, "_rows.json"), "w",
                  encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        out = cfg.out_pdf()
        cli.run_build(html, out, log=log)
        # 마감(표지 삽입) 전 상태를 남긴다 — 검수는 **우리가 조판한 면만** 본다.
        # 표지를 끼우면 면 번호가 밀려 지문면 검사가 통째로 어긋난다(그렇게 됐다).
        body_pdf = os.path.join(build_dir, "_body.pdf")
        shutil.copyfile(out, body_pdf)
        spec = cfg.finish_spec()
        if spec:
            bleed.finish(out, spec, log=log)
        log("■ 산출 %s" % out)
        return out

    @staticmethod
    def _stage_assets(build_dir):
        """계열 자산(플로우노트 모눈)을 build/img 로."""
        import shutil
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "assets", "pocketbook")
        dst = os.path.join(build_dir, "img")
        os.makedirs(dst, exist_ok=True)
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.startswith("."):
                    continue
                d = os.path.join(dst, f)
                if not os.path.exists(d):
                    shutil.copy2(os.path.join(src, f), d)

    # ── 실측 후 맞춤 ──
    def _probe_html(self, rows, M, build_dir, name):
        """한 면에 지문 하나만 — 바닥 잉크를 재기 위한 조판용 HTML."""
        pages = []
        for r in rows:
            st = ""
            if r.get("lead") or r.get("scale"):
                st = ";font-size:%gpt;line-height:%gpt" % (
                    M["passage_size"] * r.get("scale", 1.0),
                    r.get("lead", M["passage_lead"]))
            lead = r.get("lead") or M["passage_lead"]
            pages.append(
                '<section class="pg"><div class="trim">'
                '<div class="passage" style="left:%gmm;top:%s;width:%gmm%s">'
                '%s</div></div></section>'
                % (M["passage"][0], prender.passage_top(M, lead),
                   M["passage"][2], st,
                   prender.runs_html(r["passage_runs"])))
        path = os.path.join(build_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!doctype html><html><head><meta charset="utf-8">'
                    '<link rel="stylesheet" href="pocket.css">'
                    '<style>@page{size:%gmm 900mm}.pg{height:900mm}</style>'
                    '</head><body>%s</body></html>'
                    % (M["page_w"] + 2 * M["bleed"], "".join(pages)))
        return path

    def _fit(self, rows, M, build_dir, log):
        """지문이 지면보다 길면 줄인다 — **행간 먼저, 그다음 글자**.

        순서를 지키는 이유가 있다. 행간만 줄이면 줄 수가 그대로라 줄바꿈이 안 변하고,
        글자를 줄이면 줄바꿈이 통째로 달라진다. 원본 InDesign 도 같은 순서로 했다
        (`run.jsx resolveOverflow`: 행간 24→14 하한, 글자 9→7.5 하한).

        추정 공식으로 하면 서체 대체·줄바꿈 때문에 반드시 어긋난다. 한 면에 하나씩
        조판해 **재고**, 그 값으로 정한다.
        """
        top = M["passage"][1]
        lead0 = M["passage_lead"]
        # ⚠ 측정 조판에는 지문면만 넣는다. 전체 목록으로 인덱스를 매기면
        #   암기테스트 면 때문에 **높이가 엉뚱한 지문에 붙는다**.
        rows = [r for r in rows if r.get("kind") != "memtest"]
        keys = [str(i) for i in range(len(rows))]

        html = self._probe_html(rows, M, build_dir, "_measure.html")
        h = measure.measure(html, os.path.join(build_dir, "_measure.pdf"),
                            keys, top, 890.0, log=log)

        PT = 25.4 / 72.0
        # ⚠ 첫 추정은 반드시 어긋난다 — 첫 줄 높이가 행간에 안 따라오기 때문에
        #   `높이 ∝ 행간` 이 아니다. 그래서 **줄인 뒤 다시 재고**, 남은 차이는
        #   두 실측점을 잇는 직선으로 푼다(추정 한 번으로 끝내면 0.5mm 씩 샌다 —
        #   광문2 250343-45 · 성덕2 210943-45 실측).
        need_2nd = []
        for i, r in enumerate(rows):
            avail = ptheme.LAYOUTS[ptheme.layout_for(r)]["passage_h"]
            got = h.get(str(i), 0.0)
            if got <= avail:
                continue
            lines = max(1, int(round(got / (lead0 * PT))))
            lead = avail / lines / PT                    # 이 행간이면 딱 맞는다
            lead = max(MIN_LEAD, (int(lead * 2)) / 2.0)  # 0.5pt 단위로 내린다
            r["lead"] = lead
            # 실측점 (행간, 높이) 두 개를 들고 다닌다 — 직선 보간에 쓴다.
            r["_pts"] = [(lead0, got)]
            if lead <= MIN_LEAD + 1e-6:
                # 행간을 하한까지 줄여도 모자라면 글자를 줄인다 → 줄 수가 변하니
                # 다시 재야 한다.
                # ⚠ 1.0 으로 상한을 안 걸면 **글자가 커진다**(성덕2 에서 1.012 가
                #   나왔다). 이 단계는 줄이는 단계다.
                r["scale"] = min(1.0, max(
                    MIN_SCALE,
                    round((avail / (got * lead / lead0)) ** 0.5, 3)))
            need_2nd.append(i)

        # 조정한 지문은 **모두** 다시 잰다. 예전에는 글자까지 줄인 것만 다시
        # 쟀는데, 행간만 줄인 지문이 조용히 0.5mm 넘쳤다.
        for rnd in range(4):
            if not need_2nd:
                break
            sub = [rows[i] for i in need_2nd]
            name = "_measure2" if rnd == 0 else "_measure2_%d" % (rnd + 1)
            html2 = self._probe_html(sub, M, build_dir, name + ".html")
            h2 = measure.measure(html2,
                                 os.path.join(build_dir, name + ".pdf"),
                                 [str(k) for k in range(len(sub))], top, 890.0,
                                 log=log)
            still = []
            for k, i in enumerate(need_2nd):
                r = rows[i]
                avail = ptheme.LAYOUTS[ptheme.layout_for(r)]["passage_h"]
                got = h2.get(str(k), 0.0)
                lead = r.get("lead", lead0)
                r["_pts"].append((lead, got))
                if got <= avail:
                    continue
                # ① 아직 행간 여유가 있으면 두 실측점으로 필요한 행간을 푼다.
                #    보간이 안 되면(기울기가 이상하면) 한 눈금만 내린다 —
                #    행간이 남았는데 글자부터 줄이면 줄바꿈이 통째로 바뀐다.
                target = avail - 0.2          # 반올림·비선형 여유
                if lead > MIN_LEAD + 1e-6:
                    step = lead - 0.25
                    pts = [p for p in r["_pts"] if abs(p[0] - lead) > 1e-6]
                    if pts:
                        L0, H0 = pts[-1]
                        k_slope = (got - H0) / (lead - L0)
                        if k_slope > 1e-6:
                            solved = lead + (target - got) / k_slope
                            step = int(solved * 4) / 4.0    # 0.25pt 단위로 내림
                    r["lead"] = max(MIN_LEAD, min(step, lead - 0.25))
                    still.append(i)
                    continue
                # ② 행간이 하한이면 글자를 줄인다. 높이는 대략 배율의 제곱에
                #    비례한다(줄 길이·줄 수가 함께 준다).
                sc = r.get("scale", 1.0)
                new_sc = min(1.0, max(MIN_SCALE,
                                      round(sc * (target / got) ** 0.5, 3)))
                if new_sc < sc - 1e-6:
                    r["scale"] = new_sc
                    still.append(i)
                    continue
                # ③ 하한까지 갔는데도 넘친다 — 원본에서도 넘쳤던 지문이다.
                log("  [넘침] 지문 %s — %.1fmm > %.1fmm (글자 %d%%·행간 %gpt)"
                    % (r.get("key") or r.get("label") or i, got, avail,
                       sc * 100, lead))
                r["overflow"] = round(got - avail, 1)
            need_2nd = still
        for r in rows:
            r.pop("_pts", None)

        n_lead = sum(1 for r in rows if r.get("lead"))
        n_sc = sum(1 for r in rows if r.get("scale"))
        log("■ 지문 실측 %d개 · 행간 조정 %d · 글자 축소 %d"
            % (len(rows), n_lead, n_sc))

    def _fit_right(self, rows, M, build_dir, log):
        """오른쪽 면 — 플로우노트와 주제/요약이 상자를 넘지 않게 줄인다.

        둘 다 상자가 작고(41mm · 23mm) 원고 길이가 들쭉날쭉해서 자주 넘친다.
        지문과 달리 **줄 수가 적어** 행간만 줄이면 티가 나므로 글자와 함께 줄인다.
        """
        pas = [r for r in rows if r.get("kind") != "memtest"]
        if not pas:
            return
        fl, tb = M["flow"], M["topic"]
        for kind, box_h, mk in (("flow", fl[3], self._flow_probe),
                                ("topic", tb[3], self._topic_probe)):
            # ⚠ 빈 항목은 잉크가 없어 측정에서 **면이 통째로 건너뛰어진다**.
            #   전체 목록으로 인덱스를 매기면 높이가 밀려 엉뚱한 지문에 붙는다.
            if kind == "flow":
                subset = [r for r in pas if r.get("flownote")]
            else:
                subset = [r for r in pas if r.get("topic") or r.get("summary")]
            if not subset:
                continue
            pages = [mk(r, M) for r in subset]
            path = os.path.join(build_dir, "_measure_%s.html" % kind)
            with open(path, "w", encoding="utf-8") as f:
                f.write('<!doctype html><html><head><meta charset="utf-8">'
                        '<link rel="stylesheet" href="pocket.css">'
                        '<style>@page{size:%gmm 700mm}.pg{height:700mm}</style>'
                        '</head><body>%s</body></html>'
                        % (M["page_w"] + 2 * M["bleed"], "".join(pages)))
            h = measure.measure(path,
                                os.path.join(build_dir, "_measure_%s.pdf" % kind),
                                [str(i) for i in range(len(subset))], 10.0,
                                690.0, log=log)
            n = 0
            for i, r in enumerate(subset):
                got = h.get(str(i), 0.0)
                if got > box_h - 1.0:
                    r[kind + "_scale"] = max(0.72,
                                             round((box_h - 1.0) / got, 3))
                    n += 1
            log("■ %s 조정 %d/%d" % ("플로우노트" if kind == "flow" else "주제/요약",
                                     n, len(subset)))

    @staticmethod
    def _flow_probe(r, M):
        rows = []
        for line in r.get("flownote") or []:
            cls = ' class="arrow"' if line.lstrip().startswith(("→", "⇒", "▶")) else ""
            rows.append("<p%s>%s</p>" % (cls, prender.ESC(line)))
        return ('<section class="pg"><div class="trim">'
                '<div class="flow" style="left:%gmm;top:10mm;width:%gmm;'
                'background:none">%s</div></div></section>'
                % (M["flow"][0], M["flow"][2], "".join(rows)))

    @staticmethod
    def _topic_probe(r, M):
        tt = ""
        if r.get("topic"):
            tt += "<p>%s</p>" % prender.ESC(r["topic"])
        if r.get("summary"):
            tt += "<p>%s</p>" % prender.ESC(r["summary"])
        return ('<section class="pg"><div class="trim">'
                '<div class="topictext" style="left:%gmm;top:10mm;width:%gmm">'
                '%s</div></div></section>'
                % (M["topic_text_x"],
                   M["topic"][0] + M["topic"][2] - M["topic_text_x"] - 2.0, tt))

    def _fit_memtest(self, rows, M, build_dir, log):
        """암기 TEST 는 지문 여러 개를 한 면에 담아 자주 넘친다 — 행간부터 줄인다."""
        mts = [r for r in rows if r.get("kind") == "memtest"]
        if not mts:
            return
        box_h = M["memtest"][3] - 6.0
        lead0 = M["memtest_lead"]
        pages = []
        for r in mts:
            pages.append(
                '<section class="pg"><div class="trim">'
                '<div class="memtest" style="left:%gmm;top:%gmm;width:%gmm">'
                '%s</div></div></section>'
                % (M["memtest"][0] + 3.0, M["memtest"][1] + 3.0,
                   M["memtest"][2] - 6.0, prender.runs_html(r["runs"])))
        path = os.path.join(build_dir, "_measure_mt.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!doctype html><html><head><meta charset="utf-8">'
                    '<link rel="stylesheet" href="pocket.css">'
                    '<style>@page{size:%gmm 1400mm}.pg{height:1400mm}</style>'
                    '</head><body>%s</body></html>'
                    % (M["page_w"] + 2 * M["bleed"], "".join(pages)))
        h = measure.measure(path, os.path.join(build_dir, "_measure_mt.pdf"),
                            [str(i) for i in range(len(mts))],
                            M["memtest"][1] + 3.0, 1390.0, log=log)
        PT = 25.4 / 72.0
        n = 0
        for i, r in enumerate(mts):
            got = h.get(str(i), 0.0)
            if got <= box_h:
                continue
            lines = max(1, int(round(got / (lead0 * PT))))
            lead = max(11.0, (int(box_h / lines / PT * 2)) / 2.0)
            r["mt_lead"] = lead
            if lead <= 11.0 + 1e-6:
                r["mt_scale"] = max(0.8, round(box_h / (got * lead / lead0), 3))
            n += 1
        log("■ 암기테스트 %d면 · 조정 %d" % (len(mts), n))

    # ── ④ 검수 ──
    def verify(self, cfg, log, report):
        """포켓북 게이트.

        사람이 손대지 않아도 되게 만드는 것은 디자인이 아니라 **게이트**다.
        특히 G-P2 는 사용자가 직접 요구한 것 — "칸이 덜 찬 건 정상이고,
        **한 개도 없는 것만** 목록으로 뽑아라".
        """
        from core.render_vivlio import probe
        rows_path = os.path.join(cfg.build_dir, "_rows.json")
        if not os.path.exists(rows_path):
            return report.fail("검수할 조판 기록이 없다 — 먼저 build 할 것")
        with open(rows_path, encoding="utf-8") as f:
            rows = json.load(f)
        body = os.path.join(cfg.build_dir, "_body.pdf")
        pdf = body if os.path.exists(body) else cfg.out_pdf()
        M = dict(ptheme.METRICS)
        M.update(cfg.section("metrics") or {})
        opt = cfg.section("options") or {}
        start = 0        # `_body.pdf` 는 표지 전이라 첫 면이 곧 첫 지문면이다

        _SPAN_CACHE.clear()          # 앞 책의 계측이 남아 있으면 안 된다
        with probe.open_pdf(pdf) as doc:
            n_pages = len(doc)
            per = [1 if r.get("kind") == "memtest" else 2 for r in rows]
            want = start + sum(per)
            if n_pages != want:
                report.fail("G-P1 면 수 %d ≠ 예상 %d (지문 %d개)"
                            % (n_pages, want, len(rows)))

            # G-P3 주석 보존 · G-P6 넘침
            idx, lost, over, wrong = start, [], [], []
            mt_ink = []             # (키, 정답면인가, 그 면에 쓰인 글자색들)
            for r, step in zip(rows, per):
                if idx >= n_pages:
                    break
                if r.get("kind") == "memtest":
                    mt_ink.append((r.get("key"), bool(r.get("answer")),
                                   _inks(doc[idx])))
                    idx += step
                    continue
                page = doc[idx]
                want_ruby = sum(1 for x in r["passage_runs"] if x.get("ruby"))
                got_ruby = _count_size(page, M["anno_size"])
                if want_ruby and got_ruby < want_ruby:
                    lost.append((r.get("key") or r.get("label"),
                                 want_ruby, got_ruby))
                # G-P7 — 원고 글자가 지면에 다 있는가.
                #   순서로 비교하면 안 된다: 루비 낱말이 inline-block 이라 PDF
                #   추출 순서가 뒤섞이고, 인접 span 이 붙어 낱말이 엉킨다.
                #   **글자 개수**로 보면 순서·붙임과 무관하게 유실만 잡힌다.
                #   ⚠ 위첨자(`1.49597 x 10⁸km`)는 CSS 가 5.5pt 로 **고정**해서
                #     지문 크기 띠에 안 걸린다 — 지면에 멀쩡히 있는 글자를
                #     '유실'로 잡았다(강동1 250933 외 6권 실측). 위첨자 띠를
                #     같이 센다. 좁게(±0.25) 잡아야 해석 5.9pt 가 안 섞인다.
                sc = r.get("scale", 1.0)
                got_bag = _page_bag(page, M["passage_size"] * sc)
                got_bag += _page_bag(page, SUP_SIZE, tol=0.25)
                miss = _bag(_text(r["passage_runs"])) - got_bag
                if sum(miss.values()):
                    wrong.append((r.get("key") or r.get("label"),
                                  sum(miss.values())))
                lay = ptheme.LAYOUTS[ptheme.layout_for(r)]
                bottom = M["passage"][1] + lay["passage_h"]
                low = _lowest(page, M["passage_size"] * r.get("scale", 1.0))
                if low and low > bottom + 0.5:
                    over.append((r.get("key") or r.get("label"),
                                 round(low - bottom, 1)))
                idx += step

            if wrong:
                report.fail("G-P7 원문 글자 유실 %d지문 — %s"
                            % (len(wrong), ", ".join(
                                "%s(%d자)" % x for x in wrong[:5])))
            if lost:
                report.fail("G-P3 구문분석 주석 유실 %d지문 — %s"
                            % (len(lost), ", ".join(
                                "%s(%d→%d)" % x for x in lost[:5])))
            if over:
                report.fail("G-P6 지문 넘침 %d지문 — %s"
                            % (len(over), ", ".join(
                                "%s +%.1fmm" % x for x in over[:5])))

            # G-P8 — 암기 TEST 문제면과 정답면이 **정말 다른가**.
            #   글자는 두 면이 똑같다(문제면은 정답을 투명하게 두어 자리를 남긴다).
            #   그래서 글자로는 못 잡는다 — **쓰인 색**으로 본다. 예전에 두 면 다
            #   정답이 보이는 사고가 있었고, 그때 이 게이트가 없었다.
            twins = []
            for i in range(len(mt_ink) - 1):
                # ⚠ `answer` 값이 다른지로 거르면 안 된다 — 사고는 **두 면 다
                #   정답으로 찍히는 것**이라 그때 두 값이 같아져 검사가 통째로
                #   비껴간다(실측). 같은 지문의 이웃한 두 면이면 무조건 본다.
                (k0, _a0, c0), (k1, _a1, c1) = mt_ink[i], mt_ink[i + 1]
                if k0 == k1 and c0 == c1:
                    twins.append(k0 or "?")
            if twins:
                report.fail("G-P8 암기 TEST 문제면과 정답면이 같다 %d지문 — %s"
                            % (len(twins), ", ".join(twins[:5])))

        # G-P9 원본 대비 지문 수 — **읽는 쪽이 흘린 것**을 잡는다.
        #   ⚠ 계열 게이트만으로는 절대 못 잡는다: 지문이 빠지면 행도 면도 같이
        #     줄어 G-P1 이 "맞다"고 한다(완성본 광문2 에서 79 중 43이 조용히
        #     빠진 채 전 게이트를 통과했다). 그래서 파서와 **무관하게** 원본
        #     IDML 에서 '긴 영어 본문이 있는 스프레드'를 따로 센다.
        #   소제목이 지문 머리로 옮겨지거나 지문이 스프레드를 넘으면 원본 쪽이
        #   조금 더 세어진다 → 작은 차이는 알리기만 하고, **크게 빌 때만** 막는다.
        # G-P2 0개 항목 — 막지 않고 목록으로
        pas = [r for r in rows if r.get("kind") != "memtest"]
        self._check_source_count(cfg, opt, len(pas), report, log)
        no_syn = [r.get("key") or r.get("label") or "?" for r in pas
                  if not r.get("synonyms")]
        no_flow = [r.get("key") or r.get("label") or "?" for r in pas
                   if not r.get("flownote")]
        no_ill = [r.get("key") or r.get("label") or "?" for r in pas
                  if not r.get("illust")]
        if no_syn:
            report.warn("G-P2 동반의어 0개 %d지문 — %s"
                        % (len(no_syn), ", ".join(no_syn[:12])))
        if no_flow:
            report.warn("G-P2 플로우노트 0개 %d지문 — %s"
                        % (len(no_flow), ", ".join(no_flow[:12])))
        if no_ill:
            report.note("G-P5 삽화 없음 %d지문(모의고사만 필요)" % len(no_ill))
        self._write_empty_report(cfg, no_syn, no_flow, pas)
        report.note("지문 %d개 · 암기테스트 %d면 · 본문 %d면"
                    % (len(pas), len(rows) - len(pas), n_pages))
        final = cfg.out_pdf()
        if os.path.exists(final) and final != pdf:
            from core.render_vivlio import probe as _pb
            n_final = _pb.page_count(final)
            spec = cfg.finish_spec()
            add = len(spec.get("inserts") or []) + len(spec.get("append") or [])
            if n_final is not None and n_final < n_pages:
                report.fail("G-P1 최종 %d면 < 본문 %d면" % (n_final, n_pages))
            else:
                report.note("표지·마감 포함 최종 %d면 (추가 %d)"
                            % (n_final, (n_final or 0) - n_pages))
        return report

    def _check_source_count(self, cfg, opt, n_rendered, report, log):
        srcs = cfg.resolve(opt.get("analysis") or [])
        if isinstance(srcs, str):
            srcs = [srcs]
        files = []
        for sfile in srcs:
            if os.path.isdir(sfile):
                for root, _d, fs in os.walk(sfile):
                    files += [os.path.join(root, f) for f in sorted(fs)
                              if f.lower().endswith(".idml")]
            elif os.path.exists(sfile):
                files.append(sfile)
        if not files:
            return
        files = _dedup_versions(files)
        self._tools()
        try:
            import regress
        except ImportError:
            return
        try:
            n_src = sum(regress.source_passage_spreads(f) for f in files)
        except Exception as e:
            log("  [G-P9 건너뜀] 원본 계수 실패: %s" % str(e)[:80])
            return
        if not n_src:
            return
        if n_rendered < n_src * 0.85:
            report.fail("G-P9 지문이 크게 빈다 — 원본 %d · 지면 %d (%.0f%%)"
                        % (n_src, n_rendered, 100.0 * n_rendered / n_src))
        elif n_rendered < n_src:
            report.note("G-P9 원본 %d · 지면 %d (소제목 이동·스프레드 걸침이면 정상)"
                        % (n_src, n_rendered))

    @staticmethod
    def _write_empty_report(cfg, no_syn, no_flow, rows=()):
        """교재팀에 그대로 넘길 목록.

        동반의어가 빈 지문에는 **분석본 VOCA 표의 낱말을 함께 적는다** — 채울 때
        지문을 다시 열어 단어를 고르지 않아도 되게. 지면에는 안 나간다.
        """
        by_key = {}
        for r in rows:
            by_key[r.get("key") or r.get("label") or "?"] = r
        p = os.path.join(cfg.build_dir, "빈항목.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 채워야 할 지문\n\n")
            f.write("칸이 덜 찬 것은 정상이다. **하나도 없는 것만** 적는다.\n")
            f.write("원고 양식은 `조판/교재/포켓북/_원고양식/` 참고.\n\n")
            f.write("## 동반의어 0개 (%d)\n\n" % len(no_syn))
            for k in no_syn:
                r = by_key.get(k) or {}
                voca = r.get("voca") or []
                if voca:
                    ws = ", ".join(
                        ("%s %s" % (v.get("w", ""), v.get("ko", ""))).strip()
                        for v in voca[:12] if isinstance(v, dict))
                    f.write("- **%s** — 분석본 어휘: %s\n" % (k, ws))
                else:
                    f.write("- **%s**\n" % k)
            f.write("\n## 플로우노트 0개 (%d)\n\n" % len(no_flow))
            for k in no_flow:
                r = by_key.get(k) or {}
                t = (r.get("topic") or "").strip()
                f.write("- **%s**%s\n" % (k, ("  · 주제: " + t[:60]) if t else ""))
        return p
