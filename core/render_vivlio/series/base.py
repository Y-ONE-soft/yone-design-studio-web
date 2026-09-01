"""계열(②) 인터페이스 — 3계층의 중간.

계열 = "같은 디자인 계보·같은 원고 형식"의 책 묶음. 단어장(상일·배재·광문·한영보카),
프리미엄북 블랙북, 앞으로 늘어날 계열들. 계열이 갖는 것은 **원고 인식 + 마크업 +
스타일**이고, 판형·팔레트·원고 파일명·간지 경로 같은 '책마다 다른 값'은 전부
config(③)에서 받는다.

계열을 새로 만들 때 채우는 것은 아래 네 훅뿐이다. 조판 실행(CLI·서체 배치·패스
관리)·PDF 마감(도련·간지)·공용 검수는 백엔드(①)가 한다.
"""


class Series(object):

    name = ""              # 레지스트리 키
    display = ""           # 사람이 읽는 이름
    theme = ""             # `themes/<theme>.css` 기본 테마 (계열이 생성하면 빈 값)

    # ── ① 원고 → data.json (인식 게이트 내장, 어긋나면 조판하지 않고 중단) ──
    def gen_data(self, cfg, log):
        raise NotImplementedError

    # ── ② 팔레트/치수 → 테마 CSS (배경 SVG 재생성) ──
    def gen_theme(self, cfg, log):
        """색·치수를 바꾸면 배경 SVG 를 다시 구워야 한다. 필요 없는 계열은 None."""
        return None

    # ── ③ data.json → HTML → PDF ──
    def build(self, cfg, log, **opts):
        raise NotImplementedError

    # ── ④ 계열 고유 검수 (공용 게이트는 백엔드가 돌린다) ──
    def verify(self, cfg, log, report):
        return report

    # 미리보기(render/watch)에서 build() 에 얹을 옵션. 무거운 계측 패스처럼
    # "지면을 보는 데는 필요 없고 느리기만 한" 것을 끄는 자리다.
    render_opts = {}

    # ── 어느 계열에나 있는 문서 설정 ──
    #
    # 판형·도련은 **어느 책에나** 있다(config `page`). 계열이 저마다 선언하게
    # 두면 어떤 책에서는 없고 어떤 책에서는 있어, 인디자인의 「문서 설정」이
    # 책마다 다른 꼴이 된다. 그래서 여기서 한 번 준다.
    #
    # ⚠ 판형을 바꾸면 **책이 통째로 다시 흐른다.** 이미 납품한 책에서는
    #   함부로 만질 것이 아니라, 화면이 그 사실을 말해 준다.
    def base_knobs(self):
        from core.render_vivlio import knobs as _kn
        K = _kn.Knob
        mm = lambda key, label, lo, hi, affects: K(        # noqa: E731
            "page." + key, "mm", label, min=lo, max=hi, step=0.5, unit="mm",
            affects=affects, group="치수", resettable=False)
        return [
            mm("width", "판형 가로", 60, 420, "책 전체가 다시 흐른다"),
            mm("height", "판형 세로", 80, 594, "책 전체가 다시 흐른다"),
            mm("bleed", "도련", 0, 10, "재단선 바깥 여유 — 인쇄소가 정한다"),
        ]

    # ── 스타일 이름표 ──
    # 작업대의 단락 스타일 목록에 `.pbox`·`.vunit` 같은 **CSS 이름**이 그대로
    # 나오면 무엇을 고르는 건지 알 수 없다(실제로 그랬다). 계열이 사람 말을
    # 붙여 준다. 여기 없는 것은 CSS 이름 그대로 나온다.
    style_names = {}

    def name_of_style(self, cls):
        return self.style_names.get(cls, "")

    # ── 조판 결과가 놓이는 폴더 ──
    # 한 면에 하나씩 **재는** 목록의 이름들. 여기에 목차처럼 **면을 넘길 만큼
    # 큰 것**을 넣으면 측정 조판이 통째로 멎는다(항목 수 ≠ 면 수).
    #   실측: 문항 안에 8줄짜리 목차를 넣었더니 `항목 130 vs 측정 면 133`.
    MEASURED = ()

    def measured_keys(self):
        return tuple(self.MEASURED)

    def accepts_text(self, key, lst):
        """`<…>.<key>` 목록에 **글 한 줄**을 끼울 수 있나.

        블록(표·상자)보다 좁다 — 기록을 담는 목록은 글을 못 받는다.
        """
        return text_like(lst)

    def accepts_block(self, key, lst):
        """`<…>.<key>` 목록에 표·상자를 끼울 수 있나 — **계열이 안다.**

        기본은 든 것으로 가른다. 하지만 렌더러가 자리마다 다른 계열은 그걸로
        모자란다: 중등부 문항 목록(`items`)은 글도 블록도 아닌 **문항 기록**이라
        (단어장 낱말과 겉모양이 같다) 끼우면 조판이 깨진다. 그런 계열은 이걸
        좁히고, 작업대는 한 겹 더 올라가 블록 자리에 넣는다.
        """
        return para_like(lst)

    def data_path(self, cfg):
        """이 계열의 `data` 파일 자리 — 책 폴더의 `data.json` 이 기본이다.

        자료를 다른 데 두는 계열(중등부)만 이걸 바꾼다.
        """
        return cfg.path("data.json")

    def build_dir(self, cfg):
        """`build/index.html` 이 놓이는 곳. 대개 책 폴더 안이다.

        중등부처럼 조판 코드가 3계층 밖에 있는 계열은 다른 데 쓴다. 작업대가
        지면을 내줄 때 이 값을 쓰므로, 틀리면 **404 만 나고 원인이 안 보인다**.
        """
        return cfg.build_dir

    # ── 미리보기용: HTML 까지만 ──
    def render_only(self, cfg, log, **opts):
        """`build()` 를 조판 직전까지만 돌려 build/ 를 채우고 HTML 경로를 준다.

        라이브 미리보기(`watch`)는 PDF 가 필요 없다 — 뷰어가 HTML 을 직접
        조판하기 때문이다. 계열마다 build() 앞부분이 다르므로 계열별로 다시
        짜는 대신, 모든 계열이 반드시 지나가는 조판 호출에서 멈춘다.
        더 빠른 길이 있는 계열은 이 메서드를 덮어쓰면 된다.
        """
        from core.render_vivlio import cli
        merged = dict(self.render_opts)
        merged.update(opts)
        with cli.skip_build():
            try:
                self.build(cfg, log, **merged)
            except cli.RenderOnly as e:
                return e.html_path
        raise RuntimeError(
            f"계열 {self.name} 의 build() 가 조판을 호출하지 않았다 — "
            f"render_only() 를 덮어쓸 것")


# 이 열쇠들이 있으면 **덩어리**다 — 그 목록에 표·상자를 끼우면 조판이 깨진다
CHUNK_KEYS = ("stem", "blocks", "problems", "vocab", "answers", "sections",
              "lessons", "units", "parts")


def text_like(lst):
    """이 목록에 **글 한 줄**을 끼워도 되나 — 블록(표·상자)과는 다른 질문이다.

    ⚠ 낱말 목록·문항 목록은 **블록은 받아도 글은 못 받는다.** 계열 렌더러가
      그 자리에서 `it["en"]`·`unit["label"]` 처럼 **기록으로** 읽기 때문이다.
      실측: `lessons.0.vocab` 에 빈칸 한 글자를 넣었더니 조판이 통째로 멎었다.

    받는 것은 **글 목록**뿐이다 — 글자열, 서식 조각 목록, `{"t": …}` 조각.
    """
    for x in lst[:8]:
        if isinstance(x, str):
            return True
        if isinstance(x, list):
            return True                     # 서식 조각 목록
        if isinstance(x, dict):
            return "t" in x                 # 서식 조각이면 글이다
    return not lst


def para_like(lst):
    """이 목록에 표·상자를 끼워도 되나 — **이름이 아니라 든 것으로** 가른다.

    `…problems.0.stem` 을 고르면 위로 올라가다 `problems` 를 만나는데, 거기
    끼우면 문항 자리에 상자가 들어가 조판이 깨진다.

    낱말 목록(단어장)은 **된다** — 계열 렌더러가 낱말 자리에서 표·상자를
    갈라 받도록 해 두었다.
    """
    for x in lst[:8]:
        if isinstance(x, (str, list)):
            return True
        if isinstance(x, dict):
            if "t" in x:
                return True
            return not any(k in x for k in CHUNK_KEYS)
    return not lst
