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
from core.render_vivlio import cli, knobs, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.special import data as data_mod
from core.render_vivlio.series.special import render as render_mod


def _grid_clearance(pdf, report, log, floor=4.0):
    """필기 모눈과 본문이 겹치지 않는지 — **눈으로만 잡히던 결함**을 게이트로.

    모눈은 판면 아래에 못박아 두는 요소라, 위 내용이 길어지면 조판은 아무 소리
    없이 성공하면서 본문 위로 모눈이 겹쳐 인쇄된다(1차 산출물 p.118). 넘침
    검사도 대조 게이트도 이걸 못 잡는다 — 글자는 다 들어가 있기 때문이다.
    모눈 선 색으로 모눈을 찾아 그 위 본문 바닥과의 거리를 잰다.
    """
    import fitz
    GRID = (0.902, 0.878, 0.824)          # 모눈 선 #e6e0d2
    # ⚠ 라벨을 글자 그대로 걸러내지 말 것 — 구문·어법은 '필기노트', 독해는
    #    '필기 노트' 라 띄어쓰기가 다르다. 하나만 걸렀다가 라벨을 본문으로
    #    세어 10면을 거짓 결함으로 올렸다. 공백을 지우고 비교한다.
    label = lambda t: t.replace(" ", "").strip() in ("필기노트",)
    d = fitz.open(pdf)
    worst, n = None, 0
    for i, pg in enumerate(d):
        lines = [dr for dr in pg.get_drawings()
                 if dr.get("color")
                 and all(abs(c - v) < .02 for c, v in zip(dr["color"], GRID))]
        if len(lines) < 20:               # 모눈은 선 다발이다
            continue
        n += 1
        top = min(dr["rect"].y0 for dr in lines) * 25.4 / 72
        # ⚠ 측정창을 모눈 기준(top+n)으로 자르면 **겹쳐 내려간 글자를 스스로
        #    못 본다** — 처음 이렇게 짰다가 p.118 을 -1.5mm 로 과소 보고했다.
        #    자르는 기준은 모눈이 아니라 판면(머리 띠 아래 ~ 꼬리말 위)이다.
        # ⚠ 그리고 **덩어리(block)가 아니라 줄(line)** 로 재야 한다 — 라벨이
        #    바로 아래 붙어 있으면 본문 줄과 한 덩어리로 묶여, 라벨을 걸러도
        #    덩어리 바닥에는 라벨이 남는다(p.118 을 1.7mm 로 과소 보고했다).
        bots = []
        for blk in pg.get_text("dict")["blocks"]:
            for li in blk.get("lines", ()):
                t = "".join(sp["text"] for sp in li["spans"])
                y0, y1 = li["bbox"][1] * 25.4 / 72, li["bbox"][3] * 25.4 / 72
                if label(t) or not (40 < y0 < 284) or y1 > 284:
                    continue
                bots.append(y1)
        gap = top - (max(bots) if bots else 0)
        if worst is None or gap < worst[1]:
            worst = (i + 1, gap)
        if gap < floor:
            report.fail(f"[G-모눈] p.{i + 1} 필기 노트가 본문과 "
                        f"{'겹친다' if gap < 0 else '너무 가깝다'} "
                        f"(여유 {gap:+.1f}mm · 최소 {floor}mm)")
    d.close()
    if worst:
        log(f"  모눈 {n}면 · 최소 여유 {worst[1]:+.1f}mm (p.{worst[0]})")


def _rich_kept(pdf, data, report, log):
    """원고의 **밑줄이 인쇄면까지 살아남았는지** — 글자만 세는 게이트의 사각지대.

    어법 문제는 '밑줄 친 부분을 고치라'는 문제라 **밑줄이 곧 문제**다. 그런데
    ① `라벨 | 본문` 을 나누던 코드가 본문을 민글자로 내보내 해설 쪽 19곳이,
    ② 테마의 `u { text-decoration: none }` 한 줄이 **나머지 전부**가 사라졌다.
    글자는 하나도 안 틀렸으니 전수 대조 1,978건은 두 번 다 그대로 통과했다.

    ⚠ 그리고 이 게이트를 처음엔 **산출 HTML 의 `<u>` 로** 셌다가 ②를 통과시켰다
    — `<u>` 는 71개 멀쩡히 있는데 CSS 가 지우고 있었으니까. **재는 곳은 언제나
    최종 산출물이다.** 지금은 PDF 에서 글자를 찾아 그 **바로 아래 그어진 선**이
    있는지 본다.
    """
    import fitz
    def segs(o):
        if isinstance(o, dict):
            if o.get("u") and o.get("t", "").strip():
                yield o["t"].strip()
            for v in o.values():
                yield from segs(v)
        elif isinstance(o, list):
            for v in o:
                yield from segs(v)
    want = sorted(set(segs(data)))
    if not want:
        return
    d = fitz.open(pdf)
    pages = [(pg, pg.get_text()) for pg in d]
    lost, seen = [], 0
    for t in want:
        ok = False
        for pg, txt in pages:
            if t not in txt:
                continue
            for rc in pg.search_for(t[:60]):
                ruled = [dr for dr in pg.get_drawings()
                         if rc.y0 < dr["rect"].y0 < rc.y1 + 2.5
                         and dr["rect"].x1 > rc.x0 + 1
                         and dr["rect"].x0 < rc.x1 - 1]
                if ruled:
                    ok = True
                    break
            if ok:
                break
        seen += 1
        if not ok:
            lost.append(t)
    d.close()
    for t in lost[:10]:
        report.fail(f"[G-밑줄] 원고에 밑줄이 있는데 인쇄면에 선이 없다: {t!r}")
    if len(lost) > 10:
        report.fail(f"[G-밑줄] … 그 밖에 {len(lost) - 10}곳")
    log(f"  밑줄 {seen}종 확인" + ("" if not lost else f" · **{len(lost)}종 유실**"))


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
        stage.stage_book_assets(cfg, build_dir)
        # 특강만 손잡이·overrides 를 안 얹고 있었다 — 그래서 작업대에서 색을
        # 바꿔도 이 계열 책만 아무 일도 안 일어났다. 둘 다 비면 빈 파일이라
        # 조판 결과는 그대로다.
        knobs.write(cfg, SpecialSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)

    # ── 손잡이 ──
    # 이 계열은 손잡이가 **하나도 없었다** — 작업대를 열어도 만질 것이 없었다.
    # 색은 `palette.<부>.<역할>` 로 부마다 따로 있고(`palette_css()` 가
    # `.v-vocab{--c-main:…}` 로 내보낸다) 판면은 `metrics` 다.
    #
    # ⚠ `css=` 를 주지 않는다. 손잡이의 `css` 는 `:root` 로 나가는데 이 계열의
    #   색은 **부마다 범위가 다르므로** `:root` 에 부으면 세 부가 한 색이 된다.
    #   대신 config 를 고치고 다시 조판한다(작업대가 저장하면 바로 돈다).
    #
    # ⚠ `resettable` 을 열지 않는다. 이 계열은 **config 가 곧 원본**이라
    #   지우면 돌아갈 기본값이 없다(vocabook·vocaunit 과 같은 이유).
    PARTS = (("vocab", "어휘"), ("grammar", "구문 · 어법"), ("reading", "독해"))
    ROLES = (("main", "주색", "머리 띠 · 제목 · 강조"),
             ("deep", "짙은 주색", "글자 · 선"),
             ("pale", "옅은 바탕", "상자 바탕"),
             ("line", "괘선", "테두리 · 밑줄"),
             ("sub", "보조색(밝은 판)", "머리 띠 바탕처럼 넓은 면"),
             ("subd", "보조색(짙은 판)", "글자 · 선 강조"),
             ("subpl", "보조색 바탕", "보조 상자 바탕"))

    def knobs(self, cfg):
        K = knobs.Knob
        pal = cfg.section("palette") or {}
        out = []
        for pid, pname in self.PARTS:
            have = pal.get(pid) or {}
            for role, rlabel, affects in self.ROLES:
                if role not in have:
                    continue          # 그 부가 안 쓰는 역할은 만들지 않는다
                # 묶음 이름은 정해진 어휘(`knobs.GROUPS`)를 쓴다. 부 이름은
                # 라벨이 이미 지고 있으니 새 묶음을 지어내지 않는다.
                out.append(K(f"palette.{pid}.{role}", "color",
                             f"{pname} · {rlabel}", affects=affects,
                             group="색" if role in ("main", "deep", "sub")
                             else "고급", resettable=False))
        mm = lambda key, label, lo, hi, affects: K(            # noqa: E731
            "metrics." + key, "mm", label,
            default=render_mod.DEFAULT_METRICS.get(key),
            min=lo, max=hi, step=0.5, unit="mm", affects=affects,
            group="치수")
        out += [
            mm("margin_top", "위 여백", 10, 40, "판면 위"),
            mm("margin_bottom", "아래 여백", 10, 40, "판면 아래 · 쪽번호"),
            mm("margin_inner", "안쪽 여백", 10, 40, "제본 쪽"),
            mm("margin_outer", "바깥쪽 여백", 8, 40, "책배 쪽"),
        ]
        return out

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
        _grid_clearance(pdf, report, log)
        _rich_kept(pdf, d, report, log)
        report.note(f"대조 항목 {len(seq):,}건")
        return report
