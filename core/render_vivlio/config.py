"""책 1권 = `config.json` — 3계층의 ③.

교재 폴더(git 이 아니다)에는 **config.json + 원고**만 둔다. 코드는 전부 리포의
계열(②)과 공용 백엔드(①)에 있다. 다음 책에 automation 폴더를 복사하는 순간
포크가 늘고 롤백이 안 되기 때문이다.

스키마(값이 없으면 계열 기본값):

    series          계열 이름 (`core.render_vivlio.series` 레지스트리 키)
    book            {id, title, brand, school, period, subtitle …} 표시용 메타
    page            {width, height, bleed, margin:[상,밖,아래]} mm — 판형·도련
    output          {dir, stem} 산출 PDF 위치·이름(접미사는 계열이 붙인다)
    fonts           서체 **파일명** 목록(리포에 넣지 않고 로컬 설치본을 복사)
    manuscript      {dir, files:{키:파일명}} 원고(GDrive 원본의 로컬 복사본)
    palette         계열 테마가 쓰는 색 — 섹션별 {main, main_pale, sub}
    metrics         계열 테마 수치 오버라이드(밴드 높이·태그 …)
    finish          bleed.finish() 스펙 — 간지·MEMO·파리티·TrimBox
    verify          검수 게이트 파라미터(판면 프레임 등)
    options         계열 고유 설정(Day 시작 규칙·메모면 유무·묶음 표 …)

경로 값은 `${BOOK}`(config.json 이 있는 폴더)·`${STUDIO}`(스튜디오 루트)·`~` 를
치환한다. 상대경로는 `${BOOK}` 기준.
"""
import copy
import json
import os


def _is_studio(root):
    """스튜디오 루트인가 — 조판/교재 와 디자인 이 **둘 다** 있어야 한다.

    이 기계에는 `~/dev/조판` 같은 부분 사본이 남아 있어서, `조판/교재` 만 보고
    고르면 간지·표지(디자인/)를 못 찾는다.
    """
    return (os.path.isdir(os.path.join(root, "조판", "교재"))
            and os.path.isdir(os.path.join(root, "디자인")))


def _studio_root():
    env = os.environ.get("YONE_STUDIO_ROOT")
    if env:
        return env
    cands = []
    try:
        from config import STUDIO_ROOT
        cands.append(STUDIO_ROOT)
    except Exception:
        pass
    cands += [os.path.expanduser("~/Documents/작업/Y.ONE STUDIO"),
              os.path.expanduser("~/dev")]
    for c in cands:
        if _is_studio(c):
            return c
    for c in cands:                     # 완전 일치가 없으면 조판/교재 라도
        if os.path.isdir(os.path.join(c, "조판", "교재")):
            return c
    return os.path.expanduser("~")


class BookConfig(object):
    """config.json 을 읽어 경로를 해석한 뷰. dict 처럼 `cfg["page"]["bleed"]`."""

    def __init__(self, data, root):
        self.data = data
        self.root = root            # config.json 이 있는 폴더 = 책 폴더

    # ── 접근 ──
    def __getitem__(self, k):
        return self.data[k]

    def __contains__(self, k):
        return k in self.data

    def get(self, k, default=None):
        return self.data.get(k, default)

    def section(self, name):
        v = self.data.get(name) or {}
        return copy.deepcopy(v) if isinstance(v, (dict, list)) else v

    # ── 경로 ──
    def path(self, *parts):
        """책 폴더 기준 경로."""
        return os.path.join(self.root, *parts)

    def resolve(self, value):
        """문자열/리스트/딕트 안의 경로 토큰을 치환한다."""
        if isinstance(value, str):
            s = (value.replace("${BOOK}", self.root)
                      .replace("${STUDIO}", _studio_root()))
            s = os.path.expanduser(s)
            if s and not os.path.isabs(s):
                s = os.path.normpath(os.path.join(self.root, s))
            return s
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        if isinstance(value, dict):
            return {k: (self.resolve(v) if k in _PATH_KEYS or isinstance(v, (dict, list))
                        else v)
                    for k, v in value.items()}
        return value

    # ── 자주 쓰는 파생값 ──
    @property
    def series(self):
        return self.data["series"]

    @property
    def book(self):
        return self.data.get("book") or {}

    @property
    def page(self):
        p = dict(self.data.get("page") or {})
        p.setdefault("bleed", 0.0)
        p.setdefault("margin", [0, 0, 0])
        p["media_w"] = p["width"] + 2 * p["bleed"]
        p["media_h"] = p["height"] + 2 * p["bleed"]
        return p

    @property
    def build_dir(self):
        return self.path(self.data.get("build_dir", "build"))

    def out_pdf(self, suffix=""):
        o = self.data.get("output") or {}
        d = self.resolve(o.get("dir", ".."))
        stem = o.get("stem") or self.book.get("id", "내지")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{stem}{suffix}.pdf")

    def manuscript(self, key):
        m = self.data.get("manuscript") or {}
        d = self.resolve(m.get("dir", "원고"))
        f = (m.get("files") or {}).get(key)
        if not f:
            raise KeyError(f"원고 항목 없음: {key} (manuscript.files)")
        return os.path.join(d, f)

    def finish_spec(self):
        """finish 스펙의 경로를 해석해서 돌려준다."""
        spec = copy.deepcopy(self.data.get("finish") or {})
        if spec.get("art_pdf"):
            spec["art_pdf"] = self.resolve(spec["art_pdf"])
        for key in ("inserts", "append"):
            for it in spec.get(key) or []:
                if it.get("pdf"):
                    it["pdf"] = self.resolve(it["pdf"])
        for key in ("blank_fill", "end_on_left"):
            if spec.get(key, {}).get("pdf"):
                spec[key]["pdf"] = self.resolve(spec[key]["pdf"])
        if "trim" not in spec and self.page["bleed"]:
            spec["trim"] = {"bleed": self.page["bleed"]}
        return spec


_PATH_KEYS = {"pdf", "art_pdf", "dir", "src", "path", "assets"}


REQUIRED = ("series",)


def resolve_book(path):
    """책을 가리키는 말 → config.json 절대경로.

    받아 주는 것(앞에서부터):
      ① 실제 경로 (절대·상대)
      ② **스튜디오 루트 기준 상대경로** — `--list` 가 찍어 주는 그 형태.
         목록에 보이는 것을 그대로 붙여 넣을 수 없으면 목록이 무슨 소용인가.
      ③ **책 이름 일부** — `광문보카`, `블랙북` 처럼. 하나로 좁혀지면 그 책.

    ③ 은 여러 권에 걸리면 후보를 보여 주고 멈춘다(엉뚱한 책을 조판하는 것보다 낫다).
    """
    raw = path
    p = os.path.abspath(os.path.expanduser(path))
    if os.path.isdir(p) and os.path.exists(os.path.join(p, "config.json")):
        return os.path.join(p, "config.json")
    if os.path.exists(p) and not os.path.isdir(p):
        return p
    # ② 스튜디오 루트 기준
    q = os.path.join(_studio_root(), path)
    if os.path.exists(os.path.join(q, "config.json")):
        return os.path.join(q, "config.json")
    # ③ 이름 일부
    import unicodedata
    def nfc(x):
        return unicodedata.normalize("NFC", x)
    needle = nfc(raw).lower()
    from core.render_vivlio import book as _book
    hits = []
    for cfg in _book.discover():
        hay = nfc(cfg.root + " " + (cfg.book.get("title") or "")
                  + " " + (cfg.book.get("id") or "")).lower()
        if needle in hay:
            hits.append(cfg)
    if len(hits) == 1:
        return os.path.join(hits[0].root, "config.json")
    if len(hits) > 1:
        names = "\n".join(
            "    %s — %s" % (c.book.get("title", "?"),
                             c.root.replace(_studio_root() + os.sep, ""))
            for c in hits)
        raise FileNotFoundError(
            "'%s' 로는 책이 좁혀지지 않는다 (%d권):\n%s" % (raw, len(hits), names))
    raise FileNotFoundError(
        "책을 못 찾았다: %s\n  → `bin/viv --list` 로 이름을 볼 것 "
        "(이름 일부만 적어도 된다: 광문보카)" % raw)


def load(path):
    """config.json 경로·스튜디오 상대경로·책 이름 일부 → BookConfig."""
    p = resolve_book(path)
    if not os.path.exists(p):
        raise FileNotFoundError(f"책 설정 없음: {p}")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{p}: 필수 항목 없음 — {', '.join(missing)}")
    return BookConfig(data, os.path.dirname(p))
