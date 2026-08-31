"""프리미엄북 화이트북 계열 — 어휘 실전문제집(A4).

블랙북과 대비되는 점이 이 계열의 성격이다:
  · 블랙북은 문항 높이를 재서 **가변 배치**하지만, 화이트북은 **사분면 고정**이다
    (한 칸 122.5mm · 한 면 4문항 · Day 하나 = 정확히 5면).
    높이 측정은 배치가 아니라 **넘침 검사**에만 쓴다.
  · 정답은 뒤에 몰아서 Day 마다 새 면 · 2단.

빌드: (선택) 문항 높이 측정 → 본 조판 → 마감(TrimBox·파리티).
`--nomeasure` 는 높이 재측정 없이 본 조판만.
"""
import os
import re

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, measure, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.whitebook import assets as assets_mod
from core.render_vivlio.series.whitebook import data as data_mod
from core.render_vivlio.series.whitebook import render as render_mod


class WhitebookSeries(Series):

    name = "whitebook"
    display = "프리미엄북 화이트북 (어휘 실전문제)"
    theme = "whitebook"

    # 미리보기는 높이 측정을 건너뛴다 — 배치가 고정이라 지면이 달라지지 않는다.
    render_opts = {"nomeasure": True}

    SAMPLE_DAYS = 1

    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    def gen_theme(self, cfg, log):
        return assets_mod.build(cfg, log)

    @classmethod
    def _sample(cls, d):
        out = dict(d)
        out["days"] = (d.get("days") or [])[:cls.SAMPLE_DAYS]
        return out

    def build(self, cfg, log, sample=False, nomeasure=False, **_):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        if sample:
            d = self._sample(d)
            log(f"[견본] Day {len(d['days'])}")
        m = render_mod.metrics_of(cfg)

        # 높이 측정 — 배치가 아니라 **넘침 검사**에 쓴다(사분면은 고정이다).
        sfx = "_견본" if sample else ""
        hp = cfg.path(f"heights{sfx}.json")
        if not nomeasure:
            keys = [f"{D['day']}-{it['no']}"
                    for D in d["days"] for it in D["problems"]]
            html_m = render_mod.write(cfg, d, build_dir, mode="measure",
                                      log=log)
            self._stage(cfg, build_dir, log)
            h = measure.measure(html_m, os.path.join(build_dir, "measure.pdf"),
                                keys, m["body_top"],
                                m["body_top"] + m["body_h"], pad=0.0, log=log)
            measure.save(h, hp, log, "문항 높이")

        html_path = render_mod.write(cfg, d, build_dir, log=log)
        self._stage(cfg, build_dir, log)
        out = cfg.out_pdf(sfx)
        secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
        pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")

        res = {"pdf": out, "pages": pages, "seconds": round(secs, 1)}
        spec = cfg.finish_spec()
        if spec and not sample:
            res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def _stage(cfg, build_dir, log):
        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=True)
        theme = cfg.get("theme") or WhitebookSeries.theme
        stage.stage_theme(build_dir, cfg.resolve(theme)
                          if theme.endswith(".css") else theme, log)
        stage.stage_assets(build_dir,
                           cfg.resolve((cfg.section("assets") or {}).get(
                               "dir", "assets")))
        knobs.write(cfg, WhitebookSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)

    # ── 손잡이 ──
    def knobs(self, cfg):
        K = knobs.Knob
        c = lambda key, css, label, default, affects: K(       # noqa: E731
            "palette." + key, "color", label, css=css, default=default,
            affects=affects, group="색")
        return [
            c("teal", "--teal", "강조색", "#18a6c0", "문항 번호 · 탭 · 상표"),
            c("green", "--green", "탭 라벨", "#bfdb7f", "DAY 글자"),
            c("band", "--band", "머리 띠(문제)", "#d4deed", "문제면 머리 띠"),
            c("band_a", "--band-a", "머리 띠(정답)", "#dcdcd1", "정답면 머리 띠"),
            c("boxline", "--boxline", "상자 선", "#dcdcd1", "보기 · 지문 상자"),
            c("ans_no", "--ans-no", "정답 번호", "#00559f", "정답 항목 번호"),
            c("ans_nt", "--ans-nt", "정답 부연", "#58595b", "선지 해석 · 뜻"),
            c("pgnum", "--pgnum", "쪽번호", "#074481", "쪽번호"),
            K("metrics.slot", "mm", "사분면 한 칸", default=122.5, min=80,
              max=160, step=0.5, unit="mm", affects="문항 한 칸 높이",
              group="치수"),
            K("metrics.col_gap", "mm", "문제 단 사이", default=3.65, min=0,
              max=20, step=0.5, unit="mm", affects="두 단 간격", group="치수"),
            K("metrics.ans_gap", "mm", "정답 단 사이", default=6.25, min=0,
              max=20, step=0.5, unit="mm", affects="정답 두 단", group="치수"),
        ]

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        """Day 단위로 본다 — 이 교재는 **같은 발문이 400번 되풀이**된다.

        ⚠ 공용 `check_sequence`/`check_gaps` 는 전권을 한 줄로 이어 놓고 찾는다.
          발문이 겹치는 순간 위치가 뒤로 튀어 **순서 어긋남 3,692건** 같은 거짓
          경보가 쏟아진다. 그래서 면 범위를 Day 로 좁혀 대조한다.
        """
        pdf = cfg.out_pdf((cfg.section("verify") or {}).get("suffix", ""))
        d = data_mod.load(cfg)
        texts = probe.page_texts(pdf)
        m = render_mod.metrics_of(cfg)

        qpages, apages = self._day_pages(d, texts)
        self._check_day_pages(d, qpages, report)
        self._check_content(d, texts, qpages, apages, report)
        self._check_blanks(d, texts, qpages, report)
        self._check_slots(cfg, d, m, report)
        return report

    # ── Day 별 면 범위 ──
    @staticmethod
    def _day_pages(d, texts):
        """{day: [면번호…]} 두 벌 — 문제 / 정답. 머리 라벨로 구간을 가른다."""
        qs, ans = {}, {}
        for i, t in enumerate(texts):
            nt = probe.norm(t)
            for D in d["days"]:
                key = f"DAY{D['day']:02d}"
                if key not in nt:
                    continue
                if "EXERCISE" in nt and D["day"] not in qs:
                    qs[D["day"]] = i
                elif "정답" in nt and D["day"] not in ans:
                    ans[D["day"]] = i
                break

        def spans(starts, end):
            out, ks = {}, sorted(starts, key=lambda k: starts[k])
            for j, k in enumerate(ks):
                nxt = starts[ks[j + 1]] if j + 1 < len(ks) else end
                out[k] = list(range(starts[k] + 1, nxt + 1))
            return out
        first_ans = min(ans.values()) if ans else len(texts)
        return spans(qs, first_ans), spans(ans, len(texts))

    @staticmethod
    def _check_day_pages(d, qpages, report):
        """Day 하나 = 20문항 = 5면(사분면 고정). 어긋나면 계약이 깨진 것이다."""
        want = -(-len(d["days"][0]["problems"]) // 4) if d["days"] else 0
        bad = [(D["label"], len(qpages.get(D["day"], [])))
               for D in d["days"] if len(qpages.get(D["day"], [])) != want]
        if bad:
            report.fail(f"Day 면수 이상(기대 {want}면): {bad[:6]}")
        else:
            report.note(f"Day {len(qpages)}개 · 각 {want}면 (사분면 고정)")
        return bad

    # ── 누락 / 자리 ──
    @staticmethod
    def _check_content(d, texts, qpages, apages, report):
        """모든 글이 **제 Day, 제 면**에 있는가.

        ⚠ 한 면 안의 순서는 보지 않는다 — PDF 글자 추출 순서는 조판 흐름이 아니라
          좌표 순서(왼쪽 위 → 오른쪽 위 → …)라 사분면 배치에서는 늘 어긋나 보인다.
          대신 **문항 N 은 그 Day 의 (N-1)//4 번째 면** 이라는 계약을 직접 본다.
        """
        miss, wrong, n = [], [], 0
        for D in d["days"]:
            pages = qpages.get(D["day"], [])
            if not pages:
                report.fail(f"{D['label']} 문제 면을 못 찾았다")
                continue
            blobs = [probe.norm(texts[p - 1]) for p in pages]
            whole = "".join(blobs)
            for it in D["problems"]:
                want = (it["no"] - 1) // 4
                for lab, t in _item_seq(it):
                    q = probe.norm(t)
                    if not q:
                        continue
                    n += 1
                    if q not in whole:
                        miss.append(f"{D['label']} {it['no']}번 {lab}")
                    elif want < len(blobs) and q not in blobs[want]:
                        wrong.append(f"{D['label']} {it['no']}번 {lab}")
            # 정답
            ap = apages.get(D["day"], [])
            if not ap:
                report.fail(f"{D['label']} 정답 면을 못 찾았다")
                continue
            ablob = [probe.norm(texts[p - 1]) for p in ap]
            awhole = "".join(ablob)
            last = 0
            for a in D["answers"]:
                for lab, t in _ans_seq(a):
                    q = probe.norm(t)
                    if not q:
                        continue
                    n += 1
                    if q not in awhole:
                        miss.append(f"{D['label']} 정답 {a['no']}번 {lab}")
                        continue
                    pg = next((k for k, s in enumerate(ablob) if q in s), None)
                    if pg is not None and pg < last:
                        wrong.append(f"{D['label']} 정답 {a['no']}번 {lab}")
                    elif pg is not None:
                        last = pg
        report.note(f"대조 항목 {n:,}건 (Day·면 단위)")
        if miss:
            report.fail(f"누락 {len(miss)}건: {miss[:10]}")
        if wrong:
            report.fail(f"자리 어긋남 {len(wrong)}건: {wrong[:10]}")
        return miss, wrong

    # ── 빈칸 유실 ──
    @staticmethod
    def _check_blanks(d, texts, qpages, report):
        """Day 별 빈칸 개수 — 원고와 조판이 같아야 한다."""
        bad = []
        for D in d["days"]:
            pages = qpages.get(D["day"], [])
            if not pages:
                continue
            src = " ".join(t for _l, t in _q_seq(D))
            want = gate.count_gaps(src)
            got = sum(gate.count_gaps(texts[p - 1]) for p in pages)
            if got < want:
                bad.append((D["label"], want, got))
        if bad:
            report.fail(f"빈칸 유실 {len(bad)}건(Day, 원고, PDF): {bad[:8]}")
        else:
            report.note("빈칸 유실 없음")
        return bad

    # ── 사분면 넘침 ──
    @staticmethod
    def _check_slots(cfg, d, m, report):
        """문항 자연 높이가 사분면 한 칸을 넘는가 — 넘으면 아랫칸을 침범한다."""
        h = measure.load(cfg.path("heights.json"))
        if not h:
            return report.warn("문항 높이 표 없음 — `build` 로 한 번 재 둘 것")
        slot = m["slot"]
        over = [(D["label"], it["no"], h[f"{D['day']}-{it['no']}"])
                for D in d["days"] for it in D["problems"]
                if h.get(f"{D['day']}-{it['no']}", 0) > slot]
        if over:
            report.fail(f"사분면 넘침 {len(over)}건 (칸 {slot}mm): {over[:6]}")
        else:
            report.note(f"사분면 여유 최대 {max(h.values()):.1f}mm / {slot}mm")
        return over


RE_LEADMARK = re.compile(r"^\s*[∙•·]\s*")


def _item_seq(it):
    """문항 하나의 글 — (라벨, 글). 머리기호는 뗀다(조판이 `•` 로 바꾼다)."""
    seq = [("발문", _plain(it["stem"]))]
    for b in it["blocks"]:
        if b["t"] == "passage":
            for k, x in enumerate(b["paras"]):
                seq.append((f"지문{k + 1}", _plain(x)))
        elif b["t"] == "bogi":
            for k, x in enumerate(b["items"]):
                seq.append((f"보기{k + 1}", RE_LEADMARK.sub("", _plain(x))))
        elif b["t"] == "choice":
            seq.append((b["mark"], _plain(b["body"])))
        elif b["t"] == "trans":
            seq.append(("영작", _plain(b["body"])))
    return seq


def _ans_seq(a):
    seq = [("정답", _plain(a["answer"]))]
    for k, x in enumerate(a["notes"]):
        seq.append((f"부연{k + 1}", RE_LEADMARK.sub("", _plain(x))))
    return seq


def _q_seq(D):
    """Day 하나의 문제 글 전부(빈칸 세기용)."""
    return [(f"{it['no']}번 {lab}", t)
            for it in D["problems"] for lab, t in _item_seq(it)]


def _plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("t", "")
    if x is None:
        return ""
    return "".join(_plain(i) for i in x)
