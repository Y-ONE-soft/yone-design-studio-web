"""단어장 계열(vocacard) — 이의고2. 낱말 1행 = 카드 1개, 구간(교과서/부교재/모의고사)
3파트로 흐르는 단권 단어장.

`vocabook`(상일·배재보카)은 Day+4섹션+워크북 구조라 원고 형식이 다르다. 여기는
Day 도, Part2 워크북도 없이 원고 표 한 행이 곧 카드 하나다 — 별도 계열로 둔다.

**저수준 함수는 중복하지 않는다.** 낱말 카드 마크업(`.w-top/.w-lead/.w-row`),
품사 배지, 예문·유반의어 서식, 헤더 4면 체계(밴드·마름모·탭·측면 라벨)는 전부
`series.vocabook` 모듈을 그대로 불러 쓴다 — 구조가 같기 때문. **CSS 만 자체
파일**(`themes/vocacard.css`)을 쓰는데, `theme.py` 의 build_css() 가 파일 텍스트를
치환하는 방식이라 계열마다 스타일시트가 한 벌 필요해서다(vocabook.css 를 건드리면
상일보카가 흔들린다 — 파일을 나눠 원천적으로 막는다).

빌드는 vocabook 과 같은 **2패스**지만 하는 일이 하나뿐이다: 1패스로 PART 시작 면
(3개)을 찾아 그 면의 4mm 띠와 작은 마름모 탭을 끈다. 시작면에는 큰 마름모가
인플로우로 들어가는데 마진 박스의 작은 탭이 같이 나오면 **둘이 겹쳐 보인다.**
이어지는 면은 CSS `position: running()` 이 알아서 이어 준다(다음 호출까지 값이
유지되는 GCPM 성질) — vocabook 의 ②밴드(시작면 짝면에 큰 밴드)는 쓰지 않는다.

낱말 카드에는 테두리를 두르지 않는다(머리 괘선으로만 가른다). **구간마다 새 면**
에서 시작한다 — 구간이 3~6낱말이라 면 하나에 딱 맞고, 이어 붙이면 어디서 끊기는지
알 수 없다는 지적을 받았다.
"""
import os
import re

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, paged, probe, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.vocacard import data as data_mod
from core.render_vivlio.series.vocacard import render as render_mod
from core.render_vivlio.series.vocacard import theme as theme_mod


class VocacardSeries(Series):

    name = "vocacard"
    display = "단어장 카드형 (이의고2)"
    theme = ""          # 계열 테마는 책 팔레트로 매 빌드 생성한다

    style_names = {
        "day-open": "PART 한 벌", "vc": "낱말 카드", "w-word": "표제어",
        "w-mean": "뜻", "sec-head": "구간 소제목", "r-ex": "예문",
        "r-syn": "유반의어", "r-def": "설명 행",
    }

    # ── ① 원고 → data.json ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ② 팔레트/치수 → theme.css ──
    def gen_theme(self, cfg, log):
        return theme_mod.write(cfg, os.path.join(cfg.build_dir, "theme.css"), log)

    # ── 낱말 카드 높이 재기 ──
    @staticmethod
    def _card_heights(pdf, gap=5.4, rough_pad=2.0):
        """조판된 면에서 낱말 카드 높이를 잰다 — {번호: mm}.

        카드 머리의 네 자리 번호(`0001`)가 카드 시작이고, 다음 번호까지가 그
        카드의 높이다. 면의 마지막 카드는 다음 번호가 없으니 **그 면의 잉크 끝**
        까지로 재고 카드 사이 여백(`gap`)을 더한다.

        ⚠ 네 자리 숫자는 예문 속 연도(2026 …)에도 있다 → 판면 **왼쪽 끝**에서
          시작하는 것만 번호로 본다(`w-num` 은 x≈22mm, 예문은 47mm 부터).
        """
        import fitz
        k = 25.4 / 72
        out = {}
        with fitz.open(pdf) as doc:
            for pg in doc:
                marks, ink = [], 0.0
                for b in pg.get_text("dict")["blocks"]:
                    x0, y0, x1, y1 = [v * k for v in b["bbox"]]
                    if x1 > 134 or x0 < 18 or y0 > 203:
                        continue                      # 러닝 요소·꼬리말 제외
                    ink = max(ink, y1)
                    for ln in b.get("lines", []):
                        t = "".join(sp["text"] for sp in ln["spans"]).strip()
                        if re.fullmatch(r"\d{4}", t) and ln["bbox"][0] * k < 30:
                            marks.append((ln["bbox"][1] * k, int(t)))
                marks.sort()
                for i, (y, no) in enumerate(marks):
                    if i + 1 < len(marks):
                        # 다음 카드 머리까지 — 줄 상자까지 포함된 **정확한** 값
                        out[no] = (round(marks[i + 1][0] - y, 2), True)
                    else:
                        # 면의 마지막 카드는 다음 머리가 없어 **잉크 끝**까지만 잰다.
                        # 글자 잉크는 줄 상자보다 작아 3mm 가량 작게 잡히고, 이 값을
                        # 믿고 묶으면 실제로는 면을 넘쳐 한 장이 밀린다(실측).
                        # 그래서 '어림값'으로 표시해 두고, 다음 패스에서 그 카드가
                        # 면 중간으로 가면 정확한 값으로 갈아 끼운다. 끝까지 어림으로
                        # 남는 카드를 위해 `rough_pad` 만큼만 넉넉히 잡는다 — 정확한
                        # 값에는 더하지 않으므로 전체가 부풀지 않는다.
                        out[no] = (round(ink + gap - y + rough_pad, 2), False)
        return out

    @staticmethod
    def _merge_heights(base, more):
        """어림값(정확=False)을 다음 패스의 정확한 값으로 갈아 끼운다."""
        changed = 0
        for no, (h, exact) in more.items():
            old = base.get(no)
            if old is None or (exact and not old[1]):
                base[no] = (h, exact)
                changed += 1
        return changed

    # ── ③ 조판 (3패스) ──
    def build(self, cfg, log, sample=False, **_):
        """3패스.

        1패스  낱말 수로 나눈 판을 한 번 조판해 **낱말 카드 높이를 잰다.**
        2패스  그 높이로 면을 다시 나눠(`_pack`) 조판한다 — 페이지 나눔 확정.
               카드 높이는 놓이는 면과 무관한 값이라 되먹임이 없다(수렴 걱정 없음).
        3패스  PART 시작 면을 찾아 그 면의 4mm 띠와 작은 마름모 탭을 끈다
               (시작면에는 큰 마름모가 인플로우로 들어가 **둘이 겹쳐 보인다**).
               마진 박스 내용과 배경만 바꾸므로 페이지 나눔은 2패스와 같다."""
        sample = bool(sample)
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)

        suffix = "_견본" if sample else ""
        out = cfg.out_pdf(suffix)

        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=False)
        theme_mod.write(cfg, os.path.join(build_dir, "theme.css"), log)

        pages_css = stage.write_css(build_dir, "pages.css")   # 1패스는 빈 파일
        knobs.write(cfg, VocacardSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)
        html_path = render_mod.write(cfg, d, build_dir, sample=sample, log=log)
        t1 = cli.run_build(html_path, out, log=log)

        # ② 잰 높이로 면을 다시 나눈다. 면 마지막 카드는 어림값이라, 한 번 더
        #    조판해 그 카드들이 면 중간으로 간 자리에서 정확한 값을 얻는다.
        meas = self._card_heights(out)
        t2 = 0.0
        for round_no in (1, 2):
            if not meas:
                break
            hs = {no: h for no, (h, _e) in meas.items()}
            rough = sum(1 for _h, e in meas.values() if not e)
            log(f"[계측] 낱말 카드 {len(hs)}장 "
                f"(중앙 {sorted(hs.values())[len(hs) // 2]:.0f}mm · "
                f"최대 {max(hs.values()):.0f}mm · 어림 {rough}장)")
            html_path = render_mod.write(cfg, d, build_dir, sample=sample,
                                         heights=hs, log=log)
            t2 += cli.run_build(html_path, out, log=log)
            if round_no == 2 or not rough:
                break
            if not self._merge_heights(meas, self._card_heights(out)):
                break

        opens = paged.find_open_pages(probe.page_texts(out))
        page_names = [p for _c, p, *_ in theme_mod.sections_of(cfg)]
        rules = paged.PageRules(page_names)
        for p in opens:
            rules.nth(p, "background: none; @top-left { content: none; }")
        rules.write(pages_css)
        t3 = cli.run_build(html_path, out, log=log)

        npages = probe.page_count(out)
        passes = 3 if meas else 2
        log(f"OK  {t1 + t2 + t3:.1f}s ({passes}패스) · {npages}p · "
            f"PART 시작면 {len(opens)}개 → {out}")

        res = {"pdf": out, "pages": npages, "opens": len(opens),
               "seconds": round(t1 + t2 + t3, 1), "passes": passes}
        if not sample:
            spec = cfg.finish_spec()
            if spec:
                res["final"] = bleed_mod.finish(out, spec, log)
        return res

    # ── 손잡이 ──
    def knobs(self, cfg):
        from core.render_vivlio.series.vocabook.theme import DEFAULT_METRICS as D
        K = knobs.Knob
        col = lambda key, label, affects, g="색": K(          # noqa: E731
            "palette.common." + key, "color", label, affects=affects,
            group=g, resettable=False)
        mm = lambda key, label, lo, hi, affects, g="치수": K(  # noqa: E731
            "metrics." + key, "mm", label, default=D[key], min=lo, max=hi,
            step=0.1, unit="mm", affects=affects, group=g)
        out = [
            col("hl", "강조색", "예문 속 낱말 강조"),
            col("label", "라벨 글자", "행 라벨"),
            col("rule", "카드 테두리", "낱말 카드 테두리"),
            col("gray", "보조 먹", "해석 · 설명"),
            col("ink", "본문 먹", "본문 글자", "고급"),
        ]
        for sec, pal in sorted((cfg.section("palette") or {})
                               .get("sections", {}).items()):
            name = (pal or {}).get("label") or sec
            for sub, ko in (("main", "주색"), ("pale", "연한색"),
                            ("sub", "보조색")):
                if sub in (pal or {}):
                    out.append(K(f"palette.sections.{sec}.{sub}", "color",
                                 f"{name} {ko}", affects=f"{name} 파트",
                                 group="섹션", resettable=False))
        out += [
            mm("band_h", "시작면 밴드 높이", 6, 30, "PART 시작면 머리 밴드"),
            mm("strip_h", "이후 면 띠 높이", 2, 14, "이어지는 면 띠"),
            mm("margin_top", "본문 상단 여백", 10, 40, "본문 시작"),
            mm("margin_bottom", "본문 하단 여백", 6, 30, "본문 아래"),
            mm("mgn_x", "좌우 여백", 10, 40, "판면 좌우"),
            mm("lab_w", "라벨 열 폭", 12, 45, "왼쪽 라벨 열", "고급"),
        ]
        return out

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        pdf = cfg.out_pdf(cfg.section("verify").get("suffix", ""))
        n = probe.page_count(pdf)
        report.note(f"{n}p")
        want = (cfg.section("options") or {}).get("expect", {}).get("pages")
        if want is not None and n != want:
            report.fail(f"{n}p (기대 {want}p)")
        return report
