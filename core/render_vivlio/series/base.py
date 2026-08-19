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
