"""STEP BY STEP 워크북 계열 (A4 가로판 내지).

한 권이 STEP01(FRAME)·STEP02(BUILD UP)·STEP03(TEST) 세 구간이고, 각 구간 앞에
간지 2면이 붙는다. STEP1·2 는 **지문 하나 = 한 면**(어휘 선택만 두 지문)인 고정
지면이고, 영작 배열과 실전 문제는 **흘림**이다.

입력은 기존 파이프라인의 렌더 플랜(`wb-flows-v1`)이라 **원고 파서를 공유한다** —
같은 원고로 InDesign 경로와 이 경로를 둘 다 돌려 대조할 수 있다.

이 계열이 덮는 교재(모두 같은 내지 디자인, 실측 확인):
  모의고사 본가 · 부교재(수능만만·수특라이트·올포기출) · 교과서 · EBS 리딩파워
"""
import os

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, probe, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.workbook import data as data_mod
from core.render_vivlio.series.workbook import render as render_mod
from core.render_vivlio.series.workbook import fit as fit_mod
from core.render_vivlio.series.workbook import memo as memo_mod
from core.render_vivlio.series.workbook import verify as verify_mod

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_FONTS = os.path.join(HERE, "fonts")

# 이 맥에 **설치돼 있지 않은** 서체만 리포 동봉본(완성본 PDF 임베드본)을 쓴다.
# 12롯데마트드림·Cafe24Supermagic 은 설치돼 있으므로 설치본을 쓴다
# (파일명이 한글이라 `ls | grep LotteMart` 로는 안 잡힌다 — 서체 안쪽 이름으로
#  찾을 것). TTMamablock 은 3,559개 설치 서체를 훑어도 없었다.
BUNDLED = ("TTMamablockB.ttf", "TTMamablockL.ttf")


class WorkbookSeries(Series):

    name = "workbook"
    display = "STEP BY STEP 워크북 (내지)"
    theme = "workbook"

    style_names = {
        "en": "본문(영어)", "sel": "선택지", "bl": "빈칸",
        "box-body": "본문 박스", "box-q": "문제 지문 박스",
        "box-arr": "문장 배열 박스", "box-given": "주어진 문장",
        "box-write": "영작 보기", "q-head": "발문", "choices": "선지",
        "blk": "빈칸 문항", "blk-kr": "해석", "pnum": "지문 번호",
        "q3": "실전 발문", "p3": "실전 지문", "ch3": "실전 선지",
    }

    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── 서체: 로컬 설치본 + 리포 동봉본 ──
    def _fonts(self, cfg):
        """설치본을 먼저 쓰고, 없는 것만 리포 동봉본으로 채운다."""
        from core.render_vivlio import stage as _stage
        names = []
        for _fam, fname, _w in render_mod.FONTS:
            if fname not in BUNDLED and _stage.find_font(fname):
                names.append(fname)                       # 설치본
            else:
                names.append(os.path.join(REPO_FONTS, os.path.basename(fname)))
        extra = cfg.section("fonts") or []
        return names + list(extra)

    def _stage(self, cfg, build_dir, log):
        stage.stage_fonts(build_dir, self._fonts(cfg), log=log, required=True)
        stage.stage_theme(build_dir, self.theme, log=log)
        stage.stage_book_assets(cfg, build_dir)

    def build(self, cfg, log, sample=False, **_):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        if sample:
            d = dict(d, steps=[dict(s, groups=s["groups"][:2])
                               for s in d["steps"]])
            log(f"[견본] 스텝마다 지문 2개")
        render_mod.TIGHT = set()
        render_mod.TIGHT2 = set()
        render_mod.PUSH = set()
        html_path = render_mod.write(cfg, d, build_dir, log=log)
        self._stage(cfg, build_dir, log)

        out = cfg.out_pdf("_견본" if sample else "")
        secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])

        # ── 당겨붙이기 측정 패스 ──
        # 한두 줄만 넘긴 덩어리를 찾아 그것만 좁혀 다시 굽는다. 두 바퀴까지.
        if (cfg.section("options") or {}).get("fit", True) and not sample:
            # 조판을 한 번 굽고 **실제 자리를 재서** 두 가지를 고친다.
            #   ① 한두 줄만 넘긴 덩어리 → 그 덩어리만 좁혀 당겨 붙인다
            #   ② 오른쪽 면에서 시작해 장을 넘기는 세트 → 통째로 다음 면으로 민다
            # 둘은 서로 지면을 밀고 당기므로 **한 루프에서** 같이 돌린다.
            # ⚠ 되풀이 조판은 발산할 수 있다(블랙북에서 10→8→7 을 겪었다).
            #   그래서 세 바퀴로 묶고, 표시는 **쌓기만** 한다(빼면 진동한다).
            seen_turns = set()
            for _round in range(3):
                sp = fit_mod.spills(out)
                tn = fit_mod.turns(out)
                if _round == 0:
                    fit_mod.report(sp, log)
                    fit_mod.report_turns(tn, log)
                ids = {i for i, _a, _b, _t in sp}
                # 미는 것은 면을 늘린다 — **먼저 당겨 보고**, 그러고도 남은
                # 세트만 민다(한 바퀴 기다렸다 민다는 뜻).
                pids = {i for i, _a, _b in tn} & seen_turns
                seen_turns |= {i for i, _a, _b in tn}
                if not sp and not tn:
                    break
                grow = (ids - render_mod.TIGHT2) | (pids - render_mod.PUSH)
                if not grow:
                    if not tn:
                        break
                    continue   # 이번 바퀴는 표시만 — 다음 바퀴에 민다
                # 한 바퀴 돌고도 남은 덩어리는 **한 단계 더** 좁힌다
                render_mod.TIGHT2 |= (ids & render_mod.TIGHT)
                render_mod.TIGHT |= ids
                render_mod.PUSH |= pids
                html_path = render_mod.write(cfg, d, build_dir, log=lambda *a: None)
                secs += cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            sp, tn = fit_mod.spills(out), fit_mod.turns(out)
            log("  [당겨붙이기] 모두 당겨 붙였다" if not sp else
                f"  [당겨붙이기] 세 바퀴로도 안 당겨진 덩어리 {len(sp)}개 — "
                f"그대로 둔다 {[i for i, *_ in sp]}")
            log("  [장넘김] 장을 넘기는 세트 없음" if not tn else
                f"  [장넘김] 세 바퀴로도 못 없앤 세트 {len(tn)}개 — "
                + ", ".join(f"p{a}→p{b}" for _i, a, b in tn[:6]))
            render_mod.TIGHT = set()
            render_mod.TIGHT2 = set()
            render_mod.PUSH = set()

        # 인쇄물은 짝수 면으로 끝나야 한다 — 세트를 밀면서 홀수가 될 수 있다.
        # 늘어난 빈 면은 바로 아래에서 MEMO 면이 된다.
        pages = probe.page_count(out)
        if pages % 2 and not sample:
            probe.pad_even(out)
            pages = probe.page_count(out)
            log(f"  [면 수] 홀수로 끝나 한 면을 보충했다 → {pages}p")
        log(f"OK  {secs:.1f}s · {pages}p → {out}")

        # 빈 지면 → MEMO 면 (면 수는 조판이 끝나야 알 수 있어 여기서 한다)
        if (cfg.section("finish") or {}).get("memo", True) and not sample:
            blanks = [p for p in memo_mod.empty_body_pages(out) if p > 3]
            if blanks:
                fpath = os.path.join(cfg.build_dir, "fonts",
                                     "Montserrat-Bold.otf")
                memo_mod.apply(out, blanks, font=fpath, log=log)
                pages = probe.page_count(out)

        res = {"pdf": out, "pages": pages, "seconds": round(secs, 1)}
        spec = cfg.finish_spec()
        if spec and not sample:
            res["final"] = bleed_mod.finish(out, spec, log)
        return res

    def verify(self, cfg, log, report):
        return verify_mod.check(cfg, log, report)


def _factory():
    return WorkbookSeries()
