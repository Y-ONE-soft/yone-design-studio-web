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

    # ── 조판 결과가 놓이는 폴더 ──
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
