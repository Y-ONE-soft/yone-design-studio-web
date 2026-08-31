"""단어장 계열(vocabook) — 상일·배재·광문·한영보카.

계열이 갖는 것: 헤더 4면 체계, 단어 블록 표 구조, 도형 생성기, 워크북 A~D 렌더러,
정답 렌더러, 원고(xlsx+hwpx) 인식.
책이 갖는 것(config): 판형·도련 · 팔레트 · 섹션 구성 · 간지 PDF · Day 범위 · 메모면 유무.

빌드는 **2패스**다:
  1패스  전체를 한 번 조판해 Day 시작 면 번호를 알아낸다(보이지 않는 DAYOPEN 마커).
  2패스  그 면들에만 `@page :nth()` 로 4mm 띠를 끄고, 짝 오른쪽 면에 큰 밴드를 켠다.
         **마진 박스 내용과 배경만 바꾸므로 페이지 나눔은 1패스와 같다** — 재조판이
         아니라 덧칠이라 수렴을 걱정하지 않아도 된다.

`--nomemo` 는 Day 를 왼쪽 면으로 강제하지 않아 MEMO 면이 사라진다. 대신 Day 가
오른쪽 면에서 시작할 수 있어, 2패스가 오른쪽 시작면을 찾아 헤더를 좌우 반전한다
(태그·제목이 바깥쪽으로).
"""
import os
import re

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, paged, probe, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.vocabook import data as data_mod
from core.render_vivlio.series.vocabook import render as render_mod
from core.render_vivlio.series.vocabook import theme as theme_mod

# ② 오른쪽 면 밴드를 페이지 배경으로 깔 때 쓰는, theme.py 가 주석으로 흘려둔 값
_RE_BAND2 = re.compile(r"/\* (p-[\w-]+) ②밴드: (url\(.*?\) no-repeat) \*/")


class VocabookSeries(Series):

    name = "vocabook"
    display = "단어장 (상일·배재·광문·한영보카)"
    theme = ""          # 계열 테마는 책 팔레트로 매 빌드 생성한다

    # 작업대에 나오는 사람 이름 — 무엇을 고르는지 알아야 손을 댄다.
    style_names = {
        "day-open": "DAY 한 벌", "s-wb": "워크북", "s-ans": "정답",
        "s-mw": "more with", "s-vs": "VOCA vs. VOCA",
        "w-word": "표제어", "w-mean": "뜻", "w-block": "표제어 한 줄",
        "en": "예문(영어)", "kr": "예문(뜻)",
        "sec": "워크북 구역", "sec-head": "구역 머리", "sec-badge": "구역 배지",
        "sec-prompt": "구역 발문", "q": "문항 한 개", "no": "문항 번호",
        "wd": "낱말", "df": "빈칸 문항", "bogi": "<보기> 상자",
        "ansbox": "답 칸", "rule": "답 줄",
        "ans": "정답 묶음", "a-sec": "정답 구역", "a-it": "정답 한 개",
        "mw": "어근 묶음", "mw-root": "어근", "mw-items": "어근 낱말",
        "vs": "비교 묶음", "vs-word": "비교 낱말", "vs-mean": "비교 뜻",
    }

    # ── ① 원고 → data.json ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ② 팔레트/치수 → theme.css ──
    def gen_theme(self, cfg, log):
        return theme_mod.write(cfg, os.path.join(cfg.build_dir, "theme.css"), log)

    # ── ③ 조판 ──
    def build(self, cfg, log, sample=False, nomemo=False, **_):
        sample, nomemo = bool(sample), bool(nomemo)
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)

        suffix = ("_견본" if sample else "") + ("_메모없음" if nomemo else "")
        out = cfg.out_pdf(suffix)

        # 서체·테마 배치 — 색을 바꾸면 배경 SVG 를 다시 구워야 하므로 매 빌드 생성
        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=False)
        theme_css = theme_mod.write(cfg, os.path.join(build_dir, "theme.css"), log)
        page_names = [p for _c, p, *_ in theme_mod.sections_of(cfg)]

        # 1패스 — pages.css 는 빈 파일
        pages_css = stage.write_css(build_dir, "pages.css")
        knobs.write(cfg, VocabookSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)
        html_path = render_mod.write(cfg, d, build_dir, nomemo=nomemo,
                                     sample=sample, log=log)
        t1 = cli.run_build(html_path, out, log=log)

        texts = probe.page_texts(out)
        npages = len(texts)
        opens = paged.find_open_pages(texts)
        self._write_pages_css(theme_css, opens, npages, page_names, pages_css)

        if nomemo:
            # 오른쪽(홀수) 면에서 시작하는 시작면 → 헤더를 좌우 반전해 다시 렌더
            mirror = paged.right_start_indices(opens)
            html_path = render_mod.write(cfg, d, build_dir, mirror=mirror,
                                         nomemo=nomemo, sample=sample)
            log(f"[nomemo] 오른쪽 시작면 {len(mirror)}/{len(opens)} → 헤더 반전")

        t2 = cli.run_build(html_path, out, log=log)
        npages = probe.page_count(out)
        log(f"OK  {t1 + t2:.1f}s (2패스) · {npages}p · "
            f"Day 시작면 {len(opens)}개 → {out}")

        res = {"pdf": out, "pages": npages, "opens": len(opens),
               "seconds": round(t1 + t2, 1), "passes": 2}
        # 견본은 간지를 붙이지 않는다(내용 확인용)
        if not sample:
            spec = cfg.finish_spec()
            if spec:
                res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def _write_pages_css(theme_css, opens, npages, page_names, path):
        """2패스 — ①에서는 마름모 탭을 끄고, ②(그 다음 오른쪽 면)에 밴드를 켠다.

        ⚠ 이름 없는 `@page :nth()` 는 `@page p-head` 같은 이름 규칙에 명시도로
        밀린다 → **이름과 함께** 지정해야 4mm 띠가 실제로 꺼진다(빠뜨리면 헤더
        밴드의 둥근 모서리로 배경이 비쳐 보인다).
        """
        css = open(theme_css, encoding="utf-8").read()
        band2 = dict(_RE_BAND2.findall(css))
        rules = paged.PageRules(page_names)
        for p in opens:
            rules.nth(p, "background: none; @top-left { content: none; }")
            # ② 큰 밴드는 '왼쪽에서 시작한' 면의 짝(오른쪽 면)에만. 오른쪽에서
            # 시작한 경우 다음 장은 왼쪽 면이므로 기본 4mm 띠 헤더가 와야 한다.
            if p % 2 == 0 and p + 1 <= npages:
                rules.raw(f"@page :nth({p + 1}) "
                          f"{{ @top-center {{ content: element(hdrBig); }} }}")
                for n in page_names:
                    if n in band2:
                        rules.raw(f"@page {n}:nth({p + 1}) "
                                  f"{{ background: {band2[n]}; }}")
        return rules.write(path)

    # ── ④ 계열 검수 ──
    # ── 손잡이 ──
    # `theme.py` 가 config 팔레트로 테마를 생성하는 계열 → css=None.
    # 색은 **공통색**(common)과 **섹션색**(sections)으로 나뉘는데, 섹션은 책마다
    # 개수·이름이 달라 **config 에서 읽어 손잡이를 만든다**(고정 목록을 두면
    # 책이 섹션을 늘릴 때마다 코드를 고쳐야 한다).
    # ⚠ 팔레트는 config 가 원본이라 되돌리기는 막는다.
    def knobs(self, cfg):
        K = knobs.Knob
        from core.render_vivlio.series.vocabook.theme import DEFAULT_METRICS as D
        col = lambda key, label, affects, g="색": K(          # noqa: E731
            "palette.common." + key, "color", label, affects=affects,
            group=g, resettable=False)
        mm = lambda key, label, lo, hi, affects, g="치수": K(  # noqa: E731
            "metrics." + key, "mm", label, default=D[key], min=lo, max=hi,
            step=0.1, unit="mm", affects=affects, group=g)
        out = [
            col("hl", "강조색", "표제어 강조 · 포인트"),
            col("band", "머리 띠 바탕", "면 머리 띠"),
            col("rule", "항목 괘선", "항목 사이 가로선"),
            col("label", "라벨 글자", "왼쪽 라벨 열"),
            col("ans", "정답 바탕", "정답란 바탕"),
            col("line", "정답 괘선", "정답란 선"),
            col("blank", "빈칸 표시", "빈칸 밑줄·표시"),
            col("gray", "보조 먹", "부가 설명", "고급"),
            col("ink", "본문 먹", "본문 글자", "고급"),
        ]
        # 섹션 색(파트마다 주색·연한색·보조색) — 있는 만큼만 연다
        for sec, pal in sorted((cfg.section("palette") or {})
                               .get("sections", {}).items()):
            name = (pal or {}).get("label") or sec
            for sub, ko in (("main", "주색"), ("pale", "연한색"),
                            ("sub", "보조색")):
                if sub in (pal or {}):
                    out.append(K(f"palette.sections.{sec}.{sub}", "color",
                                 f"{name} {ko}", affects=f"{name} 섹션",
                                 group="섹션", resettable=False))
        out += [
            mm("band_h", "시작면 밴드 높이", 6, 30, "Day 시작면 머리 밴드"),
            mm("strip_h", "이후 면 띠 높이", 2, 14, "③④ 면 띠"),
            mm("margin_top", "본문 상단 여백", 10, 40, "본문 시작"),
            mm("margin_bottom", "본문 하단 여백", 6, 30, "본문 아래"),
            mm("mgn_x", "좌우 여백", 10, 40, "판면 좌우"),
            mm("lab_w", "라벨 열 폭", 12, 45, "왼쪽 라벨 열", "고급"),
            mm("tint_w", "밴드 보조색 길이", 10, 90, "시작면 밴드", "고급"),
        ]
        return out

    def verify(self, cfg, log, report):
        pdf = cfg.out_pdf(cfg.section("verify").get("suffix", ""))
        texts = probe.page_texts(pdf)
        opens = paged.find_open_pages(texts)
        report.note(f"Day 시작면 {len(opens)}개")
        # 보이지 않아야 할 마커가 눈에 보이면(=색이 안 먹었으면) 사고다 →
        # 존재 자체는 정상이므로 개수만 기록하고, 기대 Day 수와 대조한다.
        want = (cfg.section("options") or {}).get("expect", {}).get("day_opens")
        if want is not None and len(opens) != want:
            report.fail(f"Day 시작면 {len(opens)}개 (기대 {want})")
        return report
