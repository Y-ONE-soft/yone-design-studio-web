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
import shutil

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
        render_mod.KEEP = set()
        html_path = render_mod.write(cfg, d, build_dir, log=log)
        self._stage(cfg, build_dir, log)

        out = cfg.out_pdf("_견본" if sample else "")
        secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])

        # ── 당겨붙이기 측정 패스 ──
        # 한두 줄만 넘긴 덩어리를 찾아 그것만 좁혀 다시 굽는다. 두 바퀴까지.
        if (cfg.section("options") or {}).get("fit", True) and not sample:
            # 조판을 한 번 굽고 **실제 자리를 재서** 세 가지를 고친다.
            #   ① 한두 줄만 면을 넘긴 덩어리 → 그 덩어리만 좁혀 당겨 붙인다
            #   ② 오른쪽 면에서 시작해 장을 넘기는 세트 → 통째로 왼쪽 면부터
            #   ③ 장을 넘어 갈라진 문항 → 그 문항만 묶어 통째로 다음 자리로
            # (단을 넘어 갈라지는 것은 손대지 않는다 — 완성본도 단의 22%가 선지로
            #  시작한다. 다 묶으면 단이 40% 더 나온다.)
            #
            # ⚠ 셋은 서로 지면을 밀고 당겨 **한 방향으로 수렴하지 않는다**. 표시를
            #   쌓기만 하면 지나간 바퀴의 군더더기가 남아 78면 책이 88면이 됐다.
            #   그래서 바퀴마다 점수를 매겨 **가장 좋은 판을 남긴다**(결함 수가
            #   먼저, 같으면 면 수가 적은 쪽).
            # 규칙을 다 지키면 면이 는다 — 수능만만 10강 실측 77면 → 86면.
            # 학교·교재 사정에 따라 끌 수 있게 손잡이를 뒀다.
            opt = cfg.section("options") or {}
            do_push = opt.get("turn_push", True)
            do_keep = opt.get("leaf_keep", True)
            snap = os.path.join(build_dir, "_fit_best.pdf")
            best = None
            first = None
            for _round in range(6):
                sp = fit_mod.spills(out)
                tn = fit_mod.turns(out)
                lb = set(fit_mod.leaf_breaks(out))
                pages_now = probe.page_count(out)
                score = (len(tn) + len(lb), pages_now)
                if first is None:
                    first = score
                if best is None or score < best[0]:
                    best = (score, _round + 1)
                    shutil.copyfile(out, snap)
                if not sp and not tn and not lb:
                    break
                ids = {i for i, _a, _b, _t in sp}
                # 면 머리에서 시작하는 세트를 밀면 그 오른쪽 면이 통째로 빈다
                pend = ({i for i, _a, _b, c, y in tn if not (c == 0 and y < 45.0)}
                        if do_push else set())
                if not do_keep:
                    lb = set()
                # 한두 줄이면 먼저 당겨 보고, 두 바퀴 안에 안 되면 문항을 묶는다
                if _round < 2:
                    lb -= ids
                grow = ((ids - render_mod.TIGHT2) | (pend - render_mod.PUSH)
                        | (lb - render_mod.KEEP))
                if not grow:
                    break
                render_mod.TIGHT2 |= (ids & render_mod.TIGHT)
                render_mod.TIGHT |= ids
                render_mod.PUSH |= pend
                render_mod.KEEP |= lb
                html_path = render_mod.write(cfg, d, build_dir, log=lambda *a: None)
                secs += cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            # 마지막 바퀴가 가장 좋은 판이 아니면 되돌린다
            if best and (fit_mod.turns(out), fit_mod.leaf_breaks(out),
                         probe.page_count(out)) != ():
                cur = (len(fit_mod.turns(out)) + len(fit_mod.leaf_breaks(out)),
                       probe.page_count(out))
                if cur > best[0]:
                    shutil.copyfile(snap, out)
                    log(f"  [마감] {best[1]}바퀴 판이 가장 좋아 그것으로 되돌렸다")
            try:
                os.remove(snap)
            except OSError:
                pass
            tn, lb = fit_mod.turns(out), fit_mod.leaf_breaks(out)
            if first and best and first != best[0]:
                log(f"  [마감] 장 넘김을 없애느라 결함 {first[0]}건 · {first[1]}면 "
                    f"→ 결함 {best[0][0]}건 · {best[0][1]}면 "
                    f"(끄려면 config options.turn_push / leaf_keep = false)")
            log("  [장넘김] 장을 넘기는 세트 없음" if not tn else
                f"  [장넘김] 못 없앤 세트 {len(tn)}개 — "
                + ", ".join(f"p{a}→p{b}" for _i, a, b, _c, _y in tn[:6]))
            if lb:
                log(f"  [장넘김] 장을 넘어 갈라진 문항 {len(lb)}개 남음 — {lb[:6]}")
            render_mod.TIGHT = set()
            render_mod.TIGHT2 = set()
            render_mod.PUSH = set()
            render_mod.KEEP = set()

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
