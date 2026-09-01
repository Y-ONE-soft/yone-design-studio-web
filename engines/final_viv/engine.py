"""파이널 직전보충 (Vivliostyle 백엔드).

`final` 과 **같은 파싱**을 쓰되, 조판을 InDesign JSX 가 아니라
`core.render_vivlio`(CSS Paged Media → PDF)로 한다. 그리고 그 사이에 한 겹을
더 둔다 — **시험범위로 원고를 직접 읽어 content 를 갈아 끼운다**
(`scripts/final_manuscript_build.py`).

즉 이 카드는 세 가지가 한꺼번에 바뀐다:
  · 시험범위의 정본이 워크북 파일 이름이 아니라 **시트(→ 곧 Y.OS)**
  · 문장배열·문장삽입·영작·어법·어휘가 **원고와 시트에서 직접**
  · 조판이 InDesign 이 아니라 **Vivliostyle** (두 권 6초, 오버플로우 0)

무회귀: 부모의 InDesign 경로(prepare_jsx/run_indesign)는 호출되지 않는다.
파이프라인이 `render_backend == "vivliostyle"` 를 보고 갈라진다.
원고를 못 읽으면 **되수확본을 그대로 조판한다** — 멈추지 않고, 대신 말한다.
"""
import json
import os
import shutil
import sys

from config import MATERIALS_ROOT
from engines.final.engine import FinalEngine

BOOK_ROOT = os.path.join(MATERIALS_ROOT, "파이널 직전보충")
FONTS = ["NotoSansCJKkr-Regular.otf", "NotoSansCJKkr-Medium.otf",
         "NotoSansCJKkr-Bold.otf", "NotoSansCJKkr-Black.otf",
         "EliceDXNeolliOTF-Light.otf", "EliceDXNeolliOTF-Medium.otf",
         "EliceDXNeolliOTF-Bold.otf", "JalnanOTF.otf"]
FAMILY = {"Noto": "NotoSansCJKkr", "Neolli": "EliceDXNeolli", "Jalnan": "Jalnan"}
GRAY = {"#231f20": 1.0, "#6d6e71": 0.66, "#a7a9ac": 0.4, "#e2e3e4": 0.13,
        "#e6e7e8": 0.11, "#f2f2f3": 0.06, "#ffffff": 0.0}


def _fonts():
    out = []
    for f in FONTS:
        fam = next((k for k, v in FAMILY.items() if f.startswith(v)), "Noto")
        out.append({"family": fam, "file": f})
    return out


def book_config(school, grade, period, vol):
    """책 한 권의 `config.json` — 교재 폴더엔 이것과 원고만 둔다."""
    return {
        "series": "final",
        "book": {"id": "%s_파이널_Vol%d" % (school, vol),
                 "title": "%s 파이널 직전보충 Vol%d" % (school, vol),
                 "brand": "FINAL STEP", "school": school,
                 "grade": grade, "period": period},
        "page": {"width": 210, "height": 297, "bleed": 3},
        "output": {"dir": ".", "stem": "%s_파이널" % school},
        "options": {"vol": vol},
        "manuscript": {"dir": "../원고", "files": {"content": "content.json"}},
        "fonts": _fonts(),
        "print": {"out": "(Vol%d)_내지_인쇄" % vol, "gray_map": GRAY},
        "verify": {
            "suffix": "(Vol%d)_내지" % vol,
            "frame": {"inner": 21, "outer": 25, "width": 170.7,
                      "top": 25, "bottom": 283},
            "blank_ignore": "0123456789|FINALSTEPCHAPTER.",
            "skip_pages": [1], "skip_last": 1, "design": {"off": True},
        },
        "finish": {"trim": {"bleed": 3}},
    }


class FinalVivEngine(FinalEngine):

    # 파이프라인이 이 값으로 2단계를 Vivliostyle 로 분기(base 기본은 indesign)
    render_backend = "vivliostyle"

    @property
    def material_id(self):
        return "final_viv"

    @property
    def display_name(self):
        return "파이널 직전보충 (Vivliostyle)"

    @property
    def description(self):
        return ("파이널 Vol1/Vol2 — 시험범위로 원고를 직접 읽어 "
                "CSS Paged Media 로 조판 (InDesign 없이 두 권 6초)")

    @property
    def template_name(self):
        return "typeset_final_viv.html"

    # parse()/upload_spec 는 부모 그대로 — 같은 원고, 같은 content.json.

    # ── 2단계: 원고 직독 + Vivliostyle 조판 ────────────────────────────
    def render_vivlio(self, json_path, job_dir, log):
        from core.render_vivlio.build import cli_available, CLI_BIN, PILOT_DIR
        if not cli_available():
            raise RuntimeError(
                "Vivliostyle CLI 미설치: %s\n→ `cd %s && npm ci` 후 재시도"
                % (CLI_BIN, PILOT_DIR))

        content = json.load(open(json_path, encoding="utf-8"))
        school = content.get("school", "")
        grade = content.get("grade", "")
        period = content.get("exam_period", "")

        content = self._read_manuscripts(content, log)

        base = os.path.join(BOOK_ROOT, grade, period, school)
        src = os.path.join(base, "원고")
        os.makedirs(src, exist_ok=True)
        json.dump(content, open(os.path.join(src, "content.json"), "w",
                                encoding="utf-8"), ensure_ascii=False, indent=1)

        from core.render_vivlio import book as B
        made = []
        for vol in (1, 2):
            d = os.path.join(base, "Vol%d" % vol)
            os.makedirs(d, exist_ok=True)
            # ⚠ 이미 있는 config 는 **덮지 않는다** — 손잡이를 손봐 뒀을 수 있다.
            cpath = os.path.join(d, "config.json")
            if not os.path.exists(cpath):
                json.dump(book_config(school, grade, period, vol),
                          open(cpath, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
            cfg = B.load(d)
            log("[Vol%d] 조판 중…" % vol)
            B.gen_data(cfg, log)
            B.build(cfg, log)
            if cfg.get("print"):
                B.print_pdf(cfg, log)
            B.verify(cfg, log)
            for f in sorted(os.listdir(d)):
                if f.endswith(".pdf") and "내지" in f:
                    made.append(os.path.join(d, f))
        for p in made:
            try:
                shutil.copy2(p, os.path.join(job_dir, os.path.basename(p)))
            except Exception:
                pass
        log("완성: " + " · ".join(os.path.basename(p) for p in made))
        return made

    # ── 시험범위 → 원고 직독 ──────────────────────────────────────────
    def _read_manuscripts(self, content, log):
        """시트(→ 곧 Y.OS)의 시험범위로 원고를 읽어 content 를 갈아 끼운다.

        실패하면 **되수확본 그대로** 조판한다. 조용히 넘어가지 않고 말한다 —
        원고를 못 읽은 채 조판된 책은 겉으로 멀쩡해 보이기 때문이다.
        """
        from engines.final import scope_source as S
        try:
            g = int("".join(c for c in content.get("grade", "") if c.isdigit())
                    or 0)
            sc = S.from_sheet(content.get("school", ""),
                              content.get("exam_period", ""), grade=g, log=log)
            if not sc or not sc["tokens"]:
                log("[원고직독] 시험범위를 못 읽어 되수확본으로 조판합니다")
                return content
            log("■ 시험범위: "
                + ", ".join(S.token_text(t) for t in sc["tokens"]))
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, os.path.join(root, "scripts"))
            from final_manuscript_build import build as mbuild
            return mbuild(content, log=log, yos=sc)
        except Exception as e:
            log("[원고직독] 실패 — 되수확본으로 조판합니다: %s" % e)
            return content
