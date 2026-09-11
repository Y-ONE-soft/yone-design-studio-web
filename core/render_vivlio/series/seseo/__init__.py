"""세서특필(seseo) 계열 — 세희쌤과 함께하는 서술형 특별 필승법(광문고 서술형 특강).

예전에는 인디자인 엔진(`engines/seseospecial`)이 템플릿 .indd 에 원고를 부었다. 이
계열은 같은 디자인(정본 = 26-1 기말 광문1_세서특필02_내지)을 Vivliostyle 로 짠다.

빌드: data.json → HTML → PDF(1패스) → 백면 찾기 → 그 자리에 MEMO 를 넣어 다시(2패스)
      → 정본 면(표지 속·CONTENTS·간지·뒤표지 속) 끼우기(`finish.inserts`) → TrimBox.
"""
import json
import os
import re

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.seseo import data as data_mod
from core.render_vivlio.series.seseo import render as render_mod

# ── 인쇄색 — 정본 PDF 의 k 연산자 값을 그대로(ICC 를 안 탄다) ──────────
GRAY = {"#231f20": 1.0, "#404041": 0.9, "#58595b": 0.8, "#6d6e71": 0.7, "#ffffff": 0.0}
CMYK = {
    # 가을 노을 하늘(2026-09-12) — 화면색은 이 CMYK 를 PyMuPDF 로 변환한 값이다
    "#a4a8d5": [35, 30, 0, 0], "#c2c6e4": [22, 18, 0, 0], "#e3e3f2": [9, 8, 0, 0],
    "#5b579f": [72, 72, 0, 6], "#824f8c": [52, 78, 10, 8],
    "#f58e7d": [0, 55, 45, 0], "#fee5db": [0, 11, 10, 0], "#e35a4d": [0, 78, 68, 6],
    "#fcbb6e": [0, 30, 64, 0], "#ffecce": [0, 7, 20, 0],
    "#f6a0b0": [0, 46, 14, 0], "#fdeaec": [0, 9, 3, 0], "#cb4f70": [12, 82, 35, 6],
    "#ffe9a4": [0, 7, 42, 0], "#fff6e7": [0, 3, 9, 0],
    "#ffe4b9": [0, 10, 30, 0], "#f8a57e": [0, 42, 50, 0], "#dbddef": [12, 10, 0, 0],
    "#959ecf": [42, 34, 0, 0], "#f5dada": [0, 14, 6, 3], "#daa0af": [8, 40, 14, 4],
    "#ffda87": [0, 14, 55, 0],
}

RE_TAG = re.compile(r'§((?:S|T|P|ART)\d+)§')
MAX_FIT = 4
FRAME = {"inner": 23.0, "outer": 26.0, "width": 167.0, "top": 22.0, "bottom": 278.5}


def frag(x, n=40, floor=6):
    """대조용 조각 — 밑줄 빈칸·기호로 끊고 가장 긴 토막."""
    t = data_mod.plain(x) if not isinstance(x, str) else x
    t = re.sub(r'_{2,}', ' ', t)
    pieces = re.split(r'[→|•\[\]<>〈〉⟪⟫《》()~/]| {2,}', t)
    best = max((p.strip() for p in pieces), key=len, default='')
    return best[:n] if len(best) >= floor else ''


class SeseoSeries(Series):
    name = "seseo"
    display = "세서특필 (서술형 특강)"
    theme = "seseo"

    style_names = {
        "grp": "묶음 띠", "src": "출처 막대", "en": "영어 문장", "ko": "해석",
        "wbox": "필기 칸", "plab": "문법 라벨", "pat": "구문", "pexp": "설명",
        "tbar": "유형 띠", "step-h": "STEP 머리", "cham": "STEP 상자", "tip": "필승법",
        "prob-h": "연습 발문", "pbox2": "연습 지문", "pbox": "지문 상자", "qs": "발문",
        "qn": "문항 번호", "ql": "소문항", "bogi": "<보기>", "cbox": "요약·어법 상자",
        "diag": "도식", "ahead": "정답 세트 머리", "aexp": "해설", "trans": "지문 해석",
    }

    def print_defaults(self, cfg):
        from core.render_vivlio import prepress
        return prepress.default_print(gray_map=GRAY, cmyk_map=CMYK)

    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    def _stage(self, cfg, bd, log):
        stage.stage_fonts(bd, [f["file"] for f in cfg.get("fonts") or []], log,
                          required=True)
        theme = cfg.get("theme") or self.theme
        stage.stage_theme(bd, cfg.resolve(theme) if str(theme).endswith(".css") else theme,
                          log)
        stage.stage_book_assets(cfg, bd)
        stage.write_css(bd, "knobs.css")
        stage.stage_overrides(cfg, bd)

    # ── 조판 ──
    def build(self, cfg, log, sample=False, **_):
        bd = cfg.build_dir
        os.makedirs(bd, exist_ok=True)
        d = data_mod.load(cfg)
        self._stage(cfg, bd, log)
        out = cfg.out_pdf("")

        # 면 계획 — 단계마다 다시 조판한다.
        #   ① 조임: 한 면을 넘는 세트는 간격→행간→글자 순으로 최대 3단계 조여 한 면에
        #      넣는다("묶인 문제는 최대한 한 면에" — 사용자 지시). 3단계로도 안 들어가면
        #      원래 간격으로 되돌려 두 면으로 둔다.
        #   ② 펼침: 두 면 세트는 왼쪽 면에서 연다(앞에 MEMO) — 쪽을 넘기지 않게.
        #   ③ 백면: 왼쪽 면에서 여는 절 앞의 백면은 MEMO 로(어느 단계에서든).
        #   ④ 여백: 한 면 세트의 아래 빈자리를 문항 사이에 나눈다(면 수는 안 바뀐다).
        memos, fit, gaps = set(), {}, {}
        phase, secs, texts, longs = "fit", 0.0, [], set()
        for _try in range(16):
            html_path = render_mod.write(cfg, d, bd, log=log, memos=memos, fit=fit, gaps=gaps)
            secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            texts = probe.page_texts(out)
            blanks = probe.blank_pages(texts)
            if blanks:
                new = set()
                for n in blanks:
                    m = RE_TAG.search(texts[n]) if n < len(texts) else None
                    if not m:
                        raise RuntimeError(f"백면 {n}쪽 다음 면에 절 표식이 없다 — 원인 불명의 백면")
                    new.add(m.group(1))
                # 이미 MEMO 가 있는 자리 앞이 비었다면 그 MEMO 가 오히려 면을 밀었다
                # (앞 단계에서 면 수가 바뀌어 짝이 뒤집힌 것) — 빼면 풀린다.
                log(f"  백면 {blanks} → MEMO 넣음 {sorted(new - memos)} · 뺌 {sorted(new & memos)}")
                memos ^= new
                continue
            over = [lo for lo, b, z in self._set_spans(texts, d) if z > b]
            if phase == "fit":
                grow = [lo for lo in over if fit.get(lo, 0) < MAX_FIT]
                if grow:
                    for lo in grow:
                        fit[lo] = fit.get(lo, 0) + 1
                    memos = {m for m in memos if m.startswith("B")}   # 면 수가 바뀐다 → 백면 MEMO 다시
                    log(f"  한 면을 넘는 세트 {grow} → 조임 {[fit[lo] for lo in grow]}단계")
                    continue
                phase = "spread"
                if over:
                    for lo in over:
                        fit.pop(lo, None)
                    memos = {m for m in memos if m.startswith("B")}
                    log(f"  {MAX_FIT}단계로도 넘는 세트 {over} → 원래 간격으로 두 면(펼침면)")
                    continue
            if phase == "spread":
                new = self._spread_memos(texts, d)
                if new:
                    if new <= memos:
                        raise RuntimeError(f"MEMO 를 넣어도 풀리지 않는다: {sorted(new)}")
                    log(f"  두 면 세트 {sorted(new)} → 앞에 MEMO(펼침면으로 연다)")
                    memos = {m for m in memos if m.startswith("B")} | new
                    continue
                phase, longs = "gap", set(over)
                gaps = self._gap_plan(out, d, longs)
                if gaps:
                    qs = [g["q"] for g in gaps.values()]
                    log(f"  아래 여백을 문항 사이에 나눔 {len(gaps)}세트 "
                        f"(문항 사이 +{min(qs)}~{max(qs)}mm · 소문항 줄 사이 최대 "
                        f"+{max(g['l'] for g in gaps.values())}mm)")
                    continue
                break
            bad = [lo for lo in over if lo not in longs]
            if not bad:
                break
            for lo in bad:
                gaps.pop(lo, None)
            log(f"  여백 때문에 넘친 세트 {bad} → 그 세트는 여백 없이")
        else:
            raise RuntimeError("면 계획 16회 실패")

        pages = len(texts)
        art = self._marks(texts, r'§(ART\d)§')
        errs = [f"{k} {p}쪽" for k, p in art.items()
                if (int(k[3:]) % 2 == 0) != (p % 2 == 0)]
        if art.get("ART8") != pages or pages % 2:
            errs.append(f"뒤표지 속 {art.get('ART8')}쪽 / 전체 {pages}쪽")
        if len(art) != 8 or errs:
            raise RuntimeError(f"정본 면 자리가 어긋났다: {art} {errs}")

        res = bleed_mod.finish(out, cfg.finish_spec(), log)
        self._label_art(out, art, log)
        with open(os.path.join(bd, "pages.json"), "w", encoding="utf-8") as f:
            json.dump({"art": art, "memos": sorted(memos), "pages": pages}, f,
                      ensure_ascii=False)
        log(f"OK  {secs:.1f}s · {pages}p (MEMO {len(memos)}) → {out}")
        return {"pdf": out, "pages": pages, "seconds": round(secs, 1), "final": res}

    @staticmethod
    def _set_spans(texts, d):
        """세트마다 (첫 문항 번호, 시작 면, 끝 면) — §B첫§ 와 §Z끝§ 표식으로."""
        where = {}
        for i, t in enumerate(texts):
            for m in re.finditer(r'§([BZ]\d+)§', t):
                where.setdefault(m.group(1), i + 1)
        out = []
        for s in d["part2"]["sets"]:
            b, z = where.get(f"B{s['lo']}"), where.get(f"Z{s['hi']}")
            if b is not None and z is not None:
                out.append((s["lo"], b, z))
        return out

    @staticmethod
    def _gap_plan(pdf, d, longs, safety=4.0, cap_q=22.0, cap_l=6.0):
        """한 면 세트의 아래 빈자리(마지막 문항 끝 §Z§ ~ 판면 아래)를 나눈다.

        사용자 지시 "면 아래 공간이 남으면 문제끼리 간격을 넓혀라". 먼저 문항 사이
        (지문→1번, 1→2, 2→3)에 최대 22mm 씩, 그래도 남으면 소문항 (a)(b)(c) 줄 사이에
        최대 6mm 씩(답 쓸 자리). 처음엔 문항당 12mm 로 막아서 60mm 넘게 빈 면이
        19면 남았다(검수 FAIL).
        """
        import fitz
        pos = {}
        doc = fitz.open(pdf)
        for i, pg in enumerate(doc):
            for w in pg.get_text("words"):
                m = re.search(r'§Z(\d+)§', w[4])
                if m:
                    pos.setdefault(int(m.group(1)), (i + 1, w[3] * 25.4 / 72))
        doc.close()
        out = {}
        for s in d["part2"]["sets"]:
            z = pos.get(s["hi"])
            if s["lo"] in longs or not z:
                continue
            free = FRAME["bottom"] - z[1] - safety
            if free < 3:
                continue
            nq = len(s["qs"])
            per_q = min(free / nq, cap_q)
            rest = free - per_q * nq
            nl = sum(max(0, sum(1 for b in q["blocks"] if b["t"] == "line") - 1)
                     for q in s["qs"])
            per_l = min(rest / nl, cap_l) if nl and rest > 1 else 0.0
            out[s["lo"]] = {"q": round(per_q, 1), "l": round(per_l, 1)}
        return out

    @classmethod
    def _spread_memos(cls, texts, d):
        """오른쪽 면에서 시작해 쪽을 넘기는 세트 → 앞에 MEMO 를 넣을 세트 표식들.

        MEMO 한 장은 뒤 세트를 모두 한 면씩 민다. 그래서 앞에서부터 밀린 양을
        더해 가며 한 번에 계획한다(한 장씩 고치며 다시 조판하지 않는다).
        """
        out, off = set(), 0
        for lo, b, z in cls._set_spans(texts, d):
            if z > b and (b + off) % 2 == 1:
                out.add(f"B{lo}")
                off += 1
        return out

    @staticmethod
    def _marks(texts, pat):
        out = {}
        for i, t in enumerate(texts):
            for m in re.finditer(pat, t):
                out.setdefault(m.group(1), i + 1)
        return out

    @staticmethod
    def _label_art(pdf, art, log):
        """글자 없는 정본 면(표지 속·뒤표지 속)에 보이지 않는 표식을 남긴다.

        빈 면 게이트는 **글자**로 빈 면을 가린다. 그림뿐인 정본 면이 백면으로 잡히지
        않도록, 그 면이 어느 자리인지 알려 주는 투명 글자(렌더 모드 3)를 얹는다.
        """
        import fitz
        doc = fitz.open(pdf)
        n = 0
        for tag, p in art.items():
            pg = doc[p - 1]
            if not pg.get_text().strip():
                pg.insert_text((20, 20), f"§{tag}§", fontsize=2, render_mode=3)
                n += 1
        if n:
            tmp = pdf + ".tmp"
            doc.save(tmp, garbage=3, deflate=True)
            doc.close()
            os.replace(tmp, pdf)
        else:
            doc.close()
        log(f"  정본 면 표식 {n}면")

    # ── 검수 ──
    def verify(self, cfg, log, report):
        pdf = cfg.out_pdf((cfg.section("verify") or {}).get("suffix", ""))
        d = data_mod.load(cfg)
        texts = probe.page_texts(pdf)

        # 대조는 **머리·꼬리를 걷어낸 본문**으로 — 쪽·단이 바뀌는 자리에서 러닝 글자가
        # 끼어들어 한 문장이 끊긴다(실측: 182번 해설이 "…자리라 세/서/특/필 필승법 …").
        body = [self._strip_running(cfg, t) for t in texts]
        seq = self._sequence(d)
        gate.check_sequence(body, seq, report)
        report.note(f"대조 항목 {len(seq):,}건")

        self._check_pages(cfg, texts, report)
        self._check_questions(texts, d, report)
        spans = self._set_spans(texts, d)
        turn = [(lo, b, z) for lo, b, z in spans if z > b and b % 2 == 1]
        long_ = [x for x in spans if x[2] > x[1]]
        if len(spans) != len(d["part2"]["sets"]):
            report.fail(f"세트 표식 {len(spans)} ≠ 세트 {len(d['part2']['sets'])}")
        if turn:
            report.fail(f"쪽을 넘겨야 이어지는 세트 {len(turn)}건(오른쪽 면 시작): {turn[:10]}")
        report.note(f"세트 {len(spans)} · 두 면 세트 {len(long_)} (전부 펼침면)"
                    if not turn else f"세트 {len(spans)} · 두 면 세트 {len(long_)}")
        self._check_underlines(pdf, d, report, log)

        info = {}
        pj = os.path.join(cfg.build_dir, "pages.json")
        if os.path.exists(pj):
            with open(pj, encoding="utf-8") as f:
                info = json.load(f)
        skip = sorted(set(info.get("art", {}).values()))
        gate.check_overflow(pdf, FRAME, report, skip_pages=skip)
        return report

    @staticmethod
    def _sequence(d):
        seq = []
        for it in d["part1"]:
            if it["t"] == "src":
                seq.append(("P1 출처", frag(it["r"])))
            elif it["t"] == "sent":
                seq += [("P1 문장", frag(it["en"])), ("P1 해석", frag(it["ko"]))]
            elif it["t"] == "pt":
                seq.append(("P1 구문", frag(it["pat"])))
                seq += [("P1 설명", frag(e)) for e in it["exp"]]
        p2 = d["part2"]
        seq += [("4줄 요약", frag(s)) for s in p2["summary"]["items"]]

        def blocks(bs, lab):
            out = []
            for b in bs:
                if b["t"] == "diagram":
                    out.append((f"{lab} 도식", frag(b["title"])))
                    out += [(f"{lab} 도식칸", frag(s, 30)) for s in b["steps"]]
                else:
                    out.append((f"{lab} {b['t']}", frag(b["r"])))
            return out

        for ty in p2["types"]:
            lab = f"대표유형{ty['no']:02d}"
            seq.append((lab + " 유형", frag(ty["kind"], floor=3)))
            seq += [(lab + " 설명", frag(x)) for x in ty["desc"]]
            for s in ty["steps"]:
                seq.append((f"{lab} STEP{s['no']}", frag(s["title"])))
                seq += [(f"{lab} STEP{s['no']} 본문", frag(x)) for x in s["body"]]
            seq += [(lab + " 필승법", frag(x)) for x in ty["tip"]]
            seq.append((lab + " 발문", frag(ty["stem"])))
            seq += blocks(ty["blocks"], lab)
            seq += [(lab + " 해설", frag(x)) for x in ty["exp"]]
            seq += [(lab + " 오답", frag(x)) for x in ty["wrong"]]
            seq.append((lab + " 정답", frag(ty["answer"], floor=3)))
        for s in p2["sets"]:
            lab = f"[{s['lo']}~{s['hi']}]"
            seq.append((lab + " 출처", frag(s["src"])))
            seq += [(lab + " 이력", frag(h)) for h in s["hist"]]
            seq += [(lab + " 지문", frag(p["r"])) for p in s["passages"]]
            for q in s["qs"]:
                seq.append((f"{q['no']}번 발문", frag(q["stem"])))
                seq += blocks(q["blocks"], f"{q['no']}번")
        for s in d["answers"]:
            for x in s["items"]:
                seq.append((f"{x['no']}번 정답", frag(x["ans"], floor=3)))
                seq.append((f"{x['no']}번 해설", frag(x["exp"])))
            seq.append((f"[{s['lo']}~{s['hi']}] 지문 해석", frag(s["trans"])))
        return [(k, v) for k, v in seq if v]

    @staticmethod
    def _check_pages(cfg, texts, report):
        n = len(texts)
        errs = []
        if n % 2:
            errs.append(f"총 {n}면 — 짝수가 아니다(마지막 면은 왼쪽)")
        where = {}
        for i, t in enumerate(texts):
            for m in re.finditer(r'§((?:S|T|P|ART)\d+)§', t):
                where.setdefault(m.group(1), i + 1)
        for k, p in where.items():
            want_left = k.startswith(("S", "T")) or (k.startswith("ART") and int(k[3:]) % 2 == 0)
            if k.startswith("P"):
                want_left = False
            if (p % 2 == 0) != want_left:
                errs.append(f"{k} 가 {'왼' if want_left else '오른'}쪽 면이 아니다({p}쪽)")
        if where.get("ART8") != n:
            errs.append(f"뒤표지 속이 마지막 면이 아니다({where.get('ART8')}/{n})")
        for e in errs:
            report.fail(e)
        report.note(f"면 구성 {n}면 · 절 머리 {len([k for k in where if not k.startswith('ART')])}")

    @staticmethod
    def _strip_running(cfg, t):
        b = cfg.book
        drop = {b.get("wordmark", "세/서/특/필"), "MEMO", "PA", "RT", "|",
                b.get("running", ""), b.get("part1", ""), b.get("part2", ""),
                b.get("answers", "")}
        out = []
        for ln in t.split("\n"):
            s = ln.strip()
            if (not s or s in drop or re.match(r'^0\d$', s) or s.startswith("필승법 PART.")
                    or re.match(r'^\d{1,3}$', s) or re.match(r'^대표유형 \d+ : ', s)
                    or re.match(r'^§\w+§$', s)):
                continue
            out.append(s)
        return "\n".join(out)

    @staticmethod
    def _check_questions(texts, d, report):
        """문항은 쪽을 넘기지 않는다 — 문항 머리(§Qn§)와 끝(§Zn§) 표식이 같은 면인가."""
        head, tail = {}, {}
        for i, t in enumerate(texts):
            for m in re.finditer(r'§([QZ])(\d+)§', t):
                (head if m.group(1) == "Q" else tail).setdefault(int(m.group(2)), i + 1)
        nos = [q["no"] for s in d["part2"]["sets"] for q in s["qs"]]
        miss = [n for n in nos if n not in head or n not in tail]
        split = [(n, head[n], tail[n]) for n in nos
                 if n in head and n in tail and head[n] != tail[n]]
        if miss:
            report.fail(f"문항 표식 없음 {len(miss)}건: {miss[:10]}")
        if split:
            report.fail(f"문항이 쪽을 넘어간다 {len(split)}건: {split[:10]}")
        report.note(f"문항 쪽넘김 검사 {len(nos)}문항 · 넘김 {len(split)}")

    @staticmethod
    def _check_underlines(pdf, d, report, log):
        """어법 밑줄이 **인쇄면에** 그어졌는가 — HTML 이 아니라 PDF 에서 잰다."""
        import fitz
        want = []

        def segs(o):
            if isinstance(o, dict):
                if o.get("u") and o.get("t", "").strip():
                    yield o["t"].strip()
                for v in o.values():
                    yield from segs(v)
            elif isinstance(o, list):
                for v in o:
                    yield from segs(v)
        want = sorted(set(segs(d["part2"])))
        doc = fitz.open(pdf)
        lines = []
        for pg in doc:
            lines.append([dr["rect"] for dr in pg.get_drawings()
                          if dr["rect"].height < 2.5 and dr["rect"].width > 2])
        lost = []
        for t in want:
            ok = False
            for i, pg in enumerate(doc):
                for rc in pg.search_for(t[:60]):
                    if any(rc.y1 - 1 < r.y0 < rc.y1 + 3 and r.x1 > rc.x0 + 1
                           and r.x0 < rc.x1 - 1 for r in lines[i]):
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                lost.append(t)
        doc.close()
        if lost:
            report.fail(f"[밑줄] 인쇄면에 선이 없다 {len(lost)}종: {lost[:10]}")
        log(f"  어법 밑줄 {len(want)}종 확인" + (f" · 유실 {len(lost)}" if lost else ""))
