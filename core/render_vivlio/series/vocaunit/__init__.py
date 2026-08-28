"""UNIT형 단어장 계열(vocaunit) — 광문보카 계보.

`vocabook`(상일·배재보카)과 **디자인 계보도 원고 형식도 다르다**. 여기는
Unit 하나가 표제어 30개짜리 한 흐름이고, 항목은 왼쪽(번호·회독칸·표제어·발음기호·
파생어) / 오른쪽(뜻·예문) 2열이며, 헤더는 모눈·둥근 탭·크레스트 로고다. 공용
백엔드(도련·TrimBox·2패스·검수)만 나눠 쓴다.

빌드는 **2패스**다:
  1패스  전체를 한 번 조판해 Unit 시작 면 번호를 알아낸다(보이지 않는 DAYOPEN 마커).
  2패스  ①(시작 면)과 ②(그 다음 오른쪽 면)에 모눈 헤더 배경을 깔고, ③④의 상단
         띠·탭을 끈다.

⚠ **여기서만 2패스 계약이 한 발 넘어간다.** ②는 배경뿐 아니라 상단 여백도
5mm 내려간다(완성본 실측: 모눈 헤더 면은 본문이 25.09mm 에서 시작). 여백이
바뀌면 페이지 나눔이 바뀔 수 있어, 시작 면 목록이 **고정점에 닿을 때까지**
다시 돌린다(최대 `MAX_PASS`). Unit 마다 `break-before: left` 가 걸려 있어 흔들림이
Unit 경계를 넘지 못하므로 보통 한 번 더 돌면 멎는다. 안 멎으면 **경고**를 남긴다
— 조용히 어긋난 면에 헤더를 그리는 것보다 낫다.
"""
import os
import re
import shutil
import unicodedata

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, paged, probe, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.vocaunit import assets as assets_mod
from core.render_vivlio.series.vocaunit import data as data_mod
from core.render_vivlio.series.vocaunit import render as render_mod
from core.render_vivlio.series.vocaunit import theme as theme_mod

MAX_PASS = 4


class VocaunitSeries(Series):

    name = "vocaunit"
    display = "단어장 UNIT형 (광문보카)"
    theme = ""          # 계열 테마는 책 팔레트로 매 빌드 생성한다

    # ── ① 원고 → data.json ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ② 팔레트/치수 → theme.css ──
    def gen_theme(self, cfg, log):
        return theme_mod.write(cfg, os.path.join(cfg.build_dir, "theme.css"), log)

    # ── ③ 조판 ──
    def build(self, cfg, log, sample=False, **_):
        sample = bool(sample)
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        out = cfg.out_pdf("_견본" if sample else "")

        _stage_fonts(build_dir, cfg, log)
        # 자산 PNG 는 배경 SVG 와 달리 색이 파일에 박혀 있다 → 팔레트 색으로 다시 굽는다
        assets_mod.retint(cfg, build_dir, theme_mod.ASSETS_SRC, log)
        theme_mod.write(cfg, os.path.join(build_dir, "theme.css"), log)

        pages_css = stage.write_css(build_dir, "pages.css")
        knobs.write(cfg, VocaunitSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        html_path = render_mod.write(cfg, d, build_dir, sample=sample, log=log)
        secs = cli.run_build(html_path, out, log=log)

        texts = probe.page_texts(out)
        opens = paged.find_open_pages(texts)
        pstarts = paged.find_open_pages(texts, "PARTOPEN")
        passes = 1
        while passes < MAX_PASS:
            self._write_pages_css(cfg, opens, texts, pages_css, pstarts)
            secs += cli.run_build(html_path, out, log=log)
            passes += 1
            texts = probe.page_texts(out)
            now = paged.find_open_pages(texts)
            now_p = paged.find_open_pages(texts, "PARTOPEN")
            if now == opens and now_p == pstarts:
                break
            log(f"[2패스] 시작 면이 움직였다 {opens} → {now} — 다시 조판")
            opens, pstarts = now, now_p
        else:
            log(f"[경고] 시작 면이 {MAX_PASS}패스 안에 멎지 않았다 — "
                f"헤더 면 지정을 눈으로 확인할 것")

        npages = len(texts)
        log(f"OK  {secs:.1f}s ({passes}패스) · {npages}p · "
            f"Unit 시작면 {len(opens)}개 → {out}")

        res = {"pdf": out, "pages": npages, "opens": len(opens),
               "seconds": round(secs, 1), "passes": passes}
        if not sample:
            spec = cfg.finish_spec()
            if spec:
                res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def _write_pages_css(cfg, opens, texts, path, pstarts=()):
        """①②(모눈 헤더 면)에 배경을 깔고 ②의 상단 여백을 내린다.
        대단원이 여럿이면 **면마다 그 대단원 색**으로 띠·모눈·MEMO 배경을 깐다.

        ⚠ 이름 없는 `@page :nth()` 는 `@page p-body` 같은 이름 규칙에 명시도로
        밀린다 → **이름과 함께** 지정해야 상단 띠가 실제로 꺼진다.
        ⚠ 배경 SVG 는 색이 파일에 구워져 들어간다 → CSS 변수로는 못 바꾼다.
        대단원 색을 바꾸려면 **면마다 규칙을 내는 수밖에 없다**.
        """
        npages = len(texts)
        pals = theme_mod.part_palettes(cfg)
        part_of = _part_map(pstarts, npages)
        css = {n: theme_mod.open_page_css(cfg, pals[n]) for n in pals}
        rules = paged.PageRules(("p-body",))
        multi = len(pals) > 1

        opens = set(opens)
        for p in range(1, npages + 1):
            n = part_of.get(p, 1)
            bg_l, bg_r, mtop, bands, memo = css[n]
            left = (p % 2 == 0)             # 짝수 쪽번호 = 왼쪽(verso) 면
            if p in opens:
                rules.nth(p, f"background: {bg_l if left else bg_r}; "
                             f"@top-left {{ content: none; }}")
            elif p - 1 in opens:
                rules.nth(p, f"background: {bg_r if left else bg_l}; "
                             f"margin-top: {mtop}mm;")
            elif multi and n > 1:
                # 빈 면(MEMO)인지는 조판 결과로만 안다 — 글자가 없으면 MEMO 면
                blank = not (texts[p - 1] or "").strip()
                rules.nth(p, f"background: {memo if blank else bands};")
        return rules.write(path)

    # ── 손잡이 ──
    # 이 계열은 `theme.py` 가 config 팔레트를 읽어 테마를 **생성**한다 → CSS 로
    # 따로 내보낼 것이 없고(css=None) 선언만 붙인다.
    # ⚠ 팔레트는 **config 가 원본**이라 되돌리기(키 삭제)를 막는다 — 지우면
    #   theme.py 의 임시 폴백으로 떨어져 디자인이 달라진다.
    def knobs(self, cfg):
        K = knobs.Knob
        from core.render_vivlio.series.vocaunit.theme import DEFAULT_METRICS as D
        col = lambda key, label, affects, g="색": K(          # noqa: E731
            "palette." + key, "color", label, affects=affects, group=g,
            resettable=False)
        mm = lambda key, label, lo, hi, affects, g="치수": K(  # noqa: E731
            "metrics." + key, "mm", label, default=D[key], min=lo, max=hi,
            step=0.1, unit="mm", affects=affects, group=g)
        return [
            col("accent", "강조색", "표제어 강조 · 뜻 · Unit 번호"),
            col("hl", "예문 강조", "예문 안 표제어"),
            col("pron", "발음기호", "발음기호 회색"),
            col("rule", "항목 괘선", "항목 사이 가로선"),
            col("band", "위·아래 띠", "판면 위아래 색 띠"),
            col("grid", "모눈", "Unit 시작면 모눈 헤더"),
            col("tab", "둥근 탭", "Unit 이름표"),
            col("circle", "간지 원", "대단원 간지 큰 원"),
            col("unitnum", "Unit 번호", "헤더 Unit 번호"),
            col("crest", "크레스트", "머리 로고"),
            col("cover_bg", "간지 바탕", "대단원 간지 지면색"),
            col("chk", "회독 칸", "표제어 옆 회독 네모", "고급"),
            col("ink", "본문 먹", "본문 글자", "고급"),
            mm("band_h", "위·아래 띠 높이", 0, 12, "판면 위아래 띠"),
            mm("grid_h", "모눈 헤더 높이", 8, 40, "Unit 시작면 헤더"),
            mm("margin_top", "본문 상단 여백", 10, 40, "③④ 면 본문 시작"),
            mm("margin_bottom", "본문 하단 여백", 8, 30, "본문 아래"),
            mm("mgn_out", "바깥 여백", 8, 30, "책배 쪽", "고급"),
            mm("mgn_in", "안쪽 여백", 8, 30, "책등 쪽", "고급"),
            mm("col_w", "표제어 열 폭", 25, 70, "왼쪽 열", "고급"),
        ]

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        vcfg = cfg.section("verify") or {}
        pdf = cfg.out_pdf(vcfg.get("suffix", ""))
        texts = probe.page_texts(pdf)
        opens = paged.find_open_pages(texts)
        report.note(f"Unit 시작면 {len(opens)}개")

        exp = (cfg.section("options") or {}).get("expect") or {}
        if exp.get("units") and len(opens) != exp["units"]:
            report.fail(f"Unit 시작면 {len(opens)}개 (기대 {exp['units']})")
        # Unit 은 왼쪽 면에서 시작해야 한다(오른쪽 면이면 펼침면 규칙이 깨진다)
        odd = [p for p in opens if p % 2]
        if odd and not (cfg.section("options") or {}).get("allow_right_open"):
            report.fail(f"오른쪽 면에서 시작한 Unit: {odd}")
        # 보이지 않아야 할 2패스 마커가 눈에 보이면 사고다
        if any("DAYOPEN" in t for t in texts) and not opens:
            report.fail("DAYOPEN 마커가 조판면에 보인다")
        # 유의어·반의어 주석을 빼기로 했으면 한 톨도 남으면 안 된다
        # (중첩 괄호 `(= judg(e)ment)` 때문에 실제로 3건이 남았던 자리다)
        if (cfg.section("options") or {}).get("notes") == "drop":
            hit = [i + 1 for i, t in enumerate(texts)
                   if re.search(r"\(\s*[=↔≠]", t)]
            if hit:
                report.fail(f"빼기로 한 유의어·반의어 주석이 남은 면: {hit[:10]}")
        return report


def _part_map(pstarts, npages):
    """면 번호 → 대단원 번호. 대단원 간지가 시작한 면부터 그 대단원이다."""
    out, n = {}, 1
    starts = list(pstarts)
    for p in range(1, npages + 1):
        if starts and p == starts[0]:
            n = len(pstarts) - len(starts) + 1
            starts.pop(0)
        out[p] = n
    return out


def _stage_fonts(build_dir, cfg, log):
    """서체 배치 — 파일명이 한글이면 ASCII 별칭으로 복사한다.

    `비트로 코어 OTF.otf` 처럼 한글·공백이 든 이름은 macOS(NFD)와 config(NFC)의
    표기가 어긋나 `os.path.exists` 가 조용히 실패한다. 찾을 때는 정규화해서 찾고,
    빌드 디렉터리에는 config 의 `as` 이름(ASCII)으로 둔다.
    """
    fdir = os.path.join(build_dir, "fonts")
    os.makedirs(fdir, exist_ok=True)
    missing = []
    for f in cfg.get("fonts") or []:
        src = _find_font(f["file"])
        if src is None:
            missing.append(f["file"])
            continue
        dst = os.path.join(fdir, f.get("as") or os.path.basename(f["file"]))
        if (not os.path.exists(dst)
                or os.path.getmtime(src) > os.path.getmtime(dst)):
            shutil.copy2(src, dst)
    if missing:
        raise FileNotFoundError(
            "[서체 없음] " + ", ".join(missing)
            + f"\n  탐색 경로: {', '.join(stage.FONT_DIRS)}")
    return missing


def _find_font(name):
    p = stage.find_font(name)
    if p:
        return p
    want = unicodedata.normalize("NFC", os.path.basename(name))
    for d in stage.FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if unicodedata.normalize("NFC", fn) == want:
                return os.path.join(d, fn)
    return None
