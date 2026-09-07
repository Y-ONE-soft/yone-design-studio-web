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
from core.render_vivlio import cli, knobs, probe, stage
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

# ── 손잡이 기본값 — 테마에서 읽는다 ────────────────────────────────
# 손으로 옮겨 적으면 테마를 고쳤을 때 여기만 옛값으로 남는다. 그러면 편집기의
# 「되돌리기」가 **지금 테마에 없는 색**으로 돌려놓는다.
_THEME_CACHE = {}


def _theme_defaults():
    """themes/workbook.css 의 :root 값들. 못 읽으면 빈 사전(기본값 없음)."""
    if _THEME_CACHE:
        return _THEME_CACHE
    import re
    path = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                        "themes", "workbook.css")
    try:
        with open(path, encoding="utf-8") as f:
            css = f.read()
    except OSError:
        return {}
    for block in re.findall(r":root\s*\{([\s\S]*?)\n\}", css):
        for name, val in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", block):
            _THEME_CACHE.setdefault(name, val.strip())
    return _THEME_CACHE


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
        # 손잡이(config 가 정한 값)와 책 전용 덮어쓰기. 둘 다 **없으면 빈 파일**이라
        # config 를 안 건드린 책은 지면이 한 획도 안 바뀐다.
        knobs.write(cfg, WorkbookSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)

    # ── 손잡이 ────────────────────────────────────────────────────
    # 고르는 기준은 「실제로 시안 왕복이 났던 자리」다 — 46개를 다 열면 아무도
    # 안 쓴다(knobs.py 의 기준: 계열당 8~15개).
    #
    # ⚠ 기본값은 **테마에서 읽는다.** 손으로 적으면 테마를 고쳤을 때 기본값만
    #   옛것으로 남아, 되돌리기가 엉뚱한 색으로 돌아간다.
    #
    # 연한색(--s1-pale 등)은 열지 않는다 — 주색에서 나오는 짝이라 따로 열면
    # 주색만 바꿨을 때 둘이 어긋난다.
    def knobs(self, cfg):
        T = _theme_defaults()
        K = knobs.Knob

        def c(key, css, label, affects):
            return K("palette." + key, "color", label, css=css,
                     default=T.get(css), affects=affects, group="색")

        out = [
            c("s1", "--s1", "STEP1 주색", "STEP1 간지 · 머리말 배지 · 번호"),
            c("s2", "--s2", "STEP2 주색", "STEP2 간지 · 머리말 배지"),
            c("s3", "--s3", "STEP3 주색", "실전(STEP3) 간지 · 머리말"),
            c("hdr_bg", "--hdr-bg", "머리말 크림 패널", "모든 면 머리말 바탕"),
            c("rule", "--rule", "머리말 경계선", "머리말 아래 선 · 비활성 표시"),
            c("sel", "--sel", "선택지 파랑", "[ⓐ / ⓑ] 고르는 자리"),
            c("blank", "--blank", "빈칸 글자", "빈칸 문항의 첫 글자"),
            c("pnum", "--pnum", "지문 번호", "지문마다 붙는 번호"),
            c("box_body", "--box-body", "본문 상자(크림)", "본문 정리 · 문장 배열"),
            c("box_sky", "--box-sky", "본문 상자(하늘)", "본문 O/X · 내용 종합"),
            c("badge_topic", "--badge-topic", "주제 배지", "본문 정리의 {주제}"),
            c("badge_title", "--badge-title", "제목 배지", "본문 정리의 {제목}"),
        ]
        tr = T.get("--track")
        out.append(K("metrics.track", "number", "자간", css="--track",
                     default=float(tr[:-2]) if tr and tr.endswith("em") else None,
                     min=-0.06, max=0.0, step=0.002, unit="em",
                     affects="본문 전체 글자 사이", group="치수"))

        # ── 치수 ── 테마가 이미 토큰으로 들고 있던 값들이다. 선언이 없어서
        # 여백 하나 옮기려면 사람이 CSS 를 열어야 했다.
        # 판형·도련은 공통 손잡이(page.*)에 이미 있으므로 여기서 또 열지 않는다.
        def mm(key, css, label, affects, lo, hi):
            v = T.get(css)
            return K("metrics." + key, "mm", label, css=css,
                     default=float(v[:-2]) if v and v.endswith("mm") else None,
                     min=lo, max=hi, step=0.1, unit="mm",
                     affects=affects, group="치수")

        out += [
            mm("m_out", "--m-out", "왼쪽 면 여백",
               "짝수 쪽 글이 시작하는 자리", 5, 60),
            mm("m_in", "--m-in", "오른쪽 면 여백",
               "홀수 쪽 글이 시작하는 자리", 5, 60),
            mm("content_w", "--content-w", "판면 가로",
               "한 줄의 길이 — 줄바꿈이 전부 달라진다", 80, 200),
            mm("hdr_h", "--hdr-h", "머리말 높이",
               "크림 패널 아래 경계선 자리", 10, 60),
        ]
        # --body-top · --zone-top · --zone-btm · --folio-y 는 :root 에 적혀만
        # 있고 테마 어디서도 var() 로 읽지 않는다 — 실제 자리는 섹션마다
        # `.zone.z-top{top:…!important}` 로 따로 박혀 있다. 손잡이로 열면
        # 「돌려도 지면이 안 바뀌는 손잡이」가 되므로 열지 않는다.
        # (디자인 화면의 검사가 바로 이걸 잡아냈다.)

        # ── 서체 ── 규칙마다 글꼴 이름이 박혀 있던 40곳을 역할 토큰으로 뺐다.
        # 고를 수 있는 것은 **이 책이 실어 나르는 글꼴**뿐이다 — 안 실린 이름을
        # 적으면 인쇄에서 조용히 대체 글꼴로 떨어지므로 자유 입력을 두지 않는다.
        FACES = [T.get(c) for c in ("--f-kr", "--f-body", "--f-label", "--f-num",
                                    "--f-disp", "--f-sub", "--f-hand",
                                    "--f-pnum", "--f-deco")]
        FACES = [f for f in FACES if f]

        # ⚠ 이름을 `fonts.*` 로 두면 안 된다 — config 의 `fonts` 는 이미
        # **책이 더 실어 나를 글꼴 파일 목록**이라 사전을 넣는 순간 빌드가
        # `[서체 없음] body` 로 죽는다 (실제로 여기서 걸렸다).
        def face(key, css, label, affects):
            return K("typeface." + key, "enum", label, css=css,
                     default=T.get(css), values=FACES,
                     affects=affects, group="서체")

        out += [
            face("kr", "--f-kr", "한글 본문", "본문 한글·해석 전체"),
            face("body", "--f-body", "문항 본문", "문항 본문 · 보기 · 요약"),
            face("label", "--f-label", "번호·배지", "문항 번호 · 배지 · 탭"),
            face("num", "--f-num", "숫자·영문 라벨", "머리말 STEP · 간지 큰 숫자"),
            face("disp", "--f-disp", "발문·지시문", "문제 발문 · 지시문"),
            face("sub", "--f-sub", "간지 STEP 글자", "간지의 STEP 글자"),
            face("hand", "--f-hand", "손글씨 표시", "O/X 예시의 손글씨 느낌 글자"),
            face("pnum", "--f-pnum", "지문 번호", "지문마다 붙는 번호"),
            face("deco", "--f-deco", "머리말 장식", "머리말 장식 글자"),
        ]
        return out

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
        render_mod.FLOWED = set()
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
            for _round in range(10):
                sp = fit_mod.spills(out)
                tn = fit_mod.turns(out)
                # 고정 칸을 넘겨 **잘린** 면 — 내용이 사라지는 사고라 먼저 고친다
                cl = set(fit_mod.clipped(out, build_dir)) - render_mod.FLOWED
                lb = set(fit_mod.leaf_breaks(out))
                pages_now = probe.page_count(out)
                # 잘린 면은 **내용이 사라지는** 사고라 가장 무겁게 센다
                score = (len(cl) * 100 + len(tn) + len(lb), pages_now)
                if first is None:
                    first = score
                if _round == 0:
                    fit_mod.report_clipped(sorted(cl), log)
                if best is None or score < best[0]:
                    best = (score, _round + 1)
                    shutil.copyfile(out, snap)
                if not sp and not tn and not lb and not cl:
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
                        | (lb - render_mod.KEEP) | cl)
                if not grow:
                    break
                render_mod.TIGHT2 |= (ids & render_mod.TIGHT)
                render_mod.TIGHT |= ids
                render_mod.PUSH |= pend
                render_mod.KEEP |= lb
                render_mod.FLOWED |= cl
                html_path = render_mod.write(cfg, d, build_dir, log=lambda *a: None)
                secs += cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            # 마지막 바퀴가 가장 좋은 판이 아니면 되돌린다
            if best and (fit_mod.turns(out), fit_mod.leaf_breaks(out),
                         probe.page_count(out)) != ():
                cur = (len(fit_mod.clipped(out, build_dir)) * 100
                       + len(fit_mod.turns(out)) + len(fit_mod.leaf_breaks(out)),
                       probe.page_count(out))
                if cur > best[0]:
                    shutil.copyfile(snap, out)
                    log(f"  [마감] {best[1]}바퀴 판이 가장 좋아 그것으로 되돌렸다")
            try:
                os.remove(snap)
            except OSError:
                pass
            tn, lb = fit_mod.turns(out), fit_mod.leaf_breaks(out)
            fin = (len(tn) + len(lb), probe.page_count(out))
            if first and first != fin:
                log(f"  [마감] 장 넘김을 없애느라 결함 {first[0]}건 · {first[1]}면 "
                    f"→ 결함 {fin[0]}건 · {fin[1]}면 "
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
            render_mod.FLOWED = set()

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
