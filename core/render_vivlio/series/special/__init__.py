"""특강 합본(special) 계열 — 방학·특강용 A4 합본 교재.

한 권 안에 성격이 다른 부(部)가 여럿 묶인다(어휘 / 구문·어법 / 독해). 부마다
간지·목차·러닝 헤드·강조색이 갈리고, 부 안에서는 **흐름 조판**이다 —
블랙북처럼 항목 높이를 재서 슬롯에 앉히지 않는다. 이 책의 항목(낱말 카드·예제
한 벌·문항 한 벌)은 높이가 제각각이라 슬롯이 맞지 않고, 대신 "덩어리는 쪼개지
않는다"만 지키면 면이 자연스럽게 찬다.

그래서 빌드는 1패스다. 2패스(단어장)·측정 패스(블랙북)는 여기 없다.
"""
import os

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.special import data as data_mod
from core.render_vivlio.series.special import render as render_mod


class SpecialSeries(Series):

    name = "special"
    display = "특강 합본 (방학·특강)"
    theme = "special"

    # ── ① 원고 → data.json ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ③ 조판 ──
    def build(self, cfg, log, sample=False, **_):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        self._stage(cfg, build_dir, log)
        out = cfg.out_pdf("_견본" if sample else "")

        # 제본은 짝수 면으로 끝나야 한다. `break-before: left` 로 밀면 파리티는
        # 맞지만 앞에 백면이 생긴다 → **MEMO 장수를 1↔2 로 골라** 백면 없이
        # 짝수로 맞춘다(면수가 홀수일 때만 한 번 더 조판한다).
        secs = pages = 0
        memos = 1
        for memos in (1, 2):
            html_path = render_mod.write(cfg, d, build_dir, log=log,
                                         memos=memos)
            secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            pages = probe.page_count(out)
            if pages % 2 == 0:
                break
            log(f"  면수 {pages} (홀수) — MEMO 를 한 장 더해 다시 조판한다")

        # 간지 펼침(2면 세트)은 왼쪽 면에서 열어야 해서 앞에 백면이 생길 수 있다.
        # 그 면을 **뒤따르는 부의 옅은 색면**으로 채워 의도된 면으로 만든다.
        blanks = probe.blank_pages(probe.page_texts(out))
        if blanks:
            pal = cfg.section("palette") or {}
            order = [v["id"] for v in d["volumes"]]
            fills = []
            for n in blanks:
                nxt = self._vol_after(out, n, order)
                fills.append((n, (pal.get(nxt) or {}).get("pale", "#faf6ec")))
            log(f"  백면 {blanks} — 색면으로 채워 다시 조판한다")
            html_path = render_mod.write(cfg, d, build_dir, log=log,
                                         memos=memos, fills=fills)
            secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")

        res = {"pdf": out, "pages": pages, "seconds": round(secs, 1)}
        spec = cfg.finish_spec()
        if spec and not sample:
            res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def _vol_after(pdf, pageno, order):
        """그 백면 **다음**에 오는 부 — 색을 그 부에서 가져온다."""
        texts = probe.page_texts(pdf)
        names = {"어휘": "vocab", "구문 · 어법": "grammar", "독해": "reading"}
        for t in texts[pageno:]:
            for k, v in names.items():
                if k in t and "PART" in t:
                    return v
        return order[-1]

    @staticmethod
    def _stage(cfg, build_dir, log):
        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=True)
        theme = cfg.get("theme") or SpecialSeries.theme
        stage.stage_theme(build_dir, cfg.resolve(theme)
                          if str(theme).endswith(".css") else theme, log)
        adir = cfg.resolve((cfg.section("assets") or {}).get("dir", "assets"))
        if os.path.isdir(adir):
            stage.stage_assets(build_dir, adir)

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        """원고 → PDF 전수 대조. 게이트가 세는 것은 '내용'이지 표식이 아니다.

        (교과서 워크북에서 '단락 100% 소비' 게이트를 파서 사고가 두 번 통과한
        적이 있다 — 소비했다는 사실은 옳게 들어갔다는 뜻이 아니다.)
        """
        pdf = cfg.out_pdf(cfg.section("verify").get("suffix", ""))
        d = data_mod.load(cfg)
        texts = probe.page_texts(pdf)

        seq = render_mod.verify_sequence(d)
        gate.check_sequence(texts, seq, report)
        report.note(f"대조 항목 {len(seq):,}건")
        return report
