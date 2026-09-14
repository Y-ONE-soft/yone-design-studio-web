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

from config import BASE_DIR, MATERIALS_ROOT
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


def work_dir(school, grade, period, vol):
    """한 권의 **작업 폴더**(config·data·build·측정표) — 교재 폴더 밖이다.

    학원 출력이라 교재 폴더에는 `원고/` 와 인쇄본 두 개만 둔다(사용자 요청
    2026-09-14: Vol1·Vol2 폴더를 따로 만들지 말 것, 확인용 내지는 필요 없음).
    """
    from config import JOBS_DIR
    return os.path.join(JOBS_DIR, "final_books", grade, period, school,
                        "Vol%d" % vol)


def book_config(school, grade, period, vol, base=None):
    """책 한 권의 `config.json`. 산출은 교재 폴더(`base`)로, 작업은 `work_dir`."""
    base = base or os.path.join(BOOK_ROOT, grade, period, school)
    return {
        "series": "final",
        "book": {"id": "%s_파이널_Vol%d" % (school, vol),
                 "title": "%s 파이널 직전보충 Vol%d" % (school, vol),
                 "brand": "FINAL STEP", "school": school,
                 "grade": grade, "period": period},
        "page": {"width": 210, "height": 297, "bleed": 3},
        "output": {"dir": base, "stem": "%s_파이널" % school},
        "options": {"vol": vol},
        "manuscript": {"dir": os.path.join(base, "원고"),
                       "files": {"content": "content.json"}},
        "fonts": _fonts(),
        # 학원 출력 — 도련 없이 재단 크기(A4)로. 조판 판면은 그대로 두고 잘라 낸다.
        "print": {"out": "(Vol%d)_내지_인쇄" % vol, "gray_map": GRAY,
                  "trim_bleed": True},
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

    # ── 1단계: **워크북 없이** 원고·시트만으로 content 만들기 ──────────
    def parse(self, uploaded_files, job_dir, log):
        """되수확본을 만들지 않는다 — 시험범위로 원고를 직접 읽는다.

        워크북 `.indd` 업로드가 없어도 책이 선다. 원고에 없는 것(옛 모의 회차의
        하단 문제 등)은 그냥 비고, 빌더가 무엇이 비었는지 말한다.

        범위를 못 읽거나 한 지문도 못 만들면 **부모의 되수확 경로로 돌아간다** —
        새 길이 막혔다고 조판이 멈추면 안 된다.
        """
        import unicodedata
        school = unicodedata.normalize(
            "NFC", self._get_meta(job_dir, "school", ""))
        grade = self._get_meta(job_dir, "grade", "고1")
        period = self._get_meta(job_dir, "exam_period", "")
        try:
            content = self._scratch(school, grade, period, log,
                                    job_dir=job_dir)
            if content and content["vol1"]["문장배열"]:
                out = os.path.join(job_dir, "content.json")
                json.dump(content, open(out, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                log("[원고직독] 워크북 없이 %d지문으로 세웠습니다"
                    % len(content["vol1"]["문장배열"]))
                return out
            log("[원고직독] 원고에서 지문을 못 만들어 되수확 경로로 갑니다")
        except Exception as e:
            log("[원고직독] 실패 — 되수확 경로로 갑니다: %s" % e)
        return FinalEngine.parse(self, uploaded_files, job_dir, log)

    def _scratch(self, school, grade, period, log, job_dir=None):
        """시험범위 → 원고 직독 content.

        정본은 **Y.OS** 다. 읽기 API 가 열리기 전까지는 화면에서 떠 온
        `scope.json` 을 작업 폴더에 두면 그것을 쓴다(`final_scope_fetch.py`).
        없으면 예전처럼 구글시트를 본다.
        """
        from engines.final import scope_source as S
        spath = os.path.join(BASE_DIR, "scripts")
        if spath not in sys.path:
            sys.path.insert(0, spath)
        from final_manuscript_build import build as mbuild, scratch
        g = int("".join(c for c in grade if c.isdigit()) or 0)
        sc = S.resolve(school, period, grade=g, job_dir=job_dir,
                       book_dir=os.path.join(BOOK_ROOT, grade, period, school),
                       log=log)
        if not sc or not sc["tokens"]:
            return None
        self._scope = sc          # 조판이 끝나면 책 폴더에 남긴다(검수가 읽는다)
        return mbuild(scratch(school, grade, period), log=log, yos=sc)

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

        if not content.get("_from_manuscript"):
            content = self._read_manuscripts(content, log)

        base = os.path.join(BOOK_ROOT, grade, period, school)
        src = os.path.join(base, "원고")
        os.makedirs(src, exist_ok=True)
        json.dump(content, open(os.path.join(src, "content.json"), "w",
                                encoding="utf-8"), ensure_ascii=False, indent=1)

        from core.render_vivlio import book as B
        made = []
        for vol in (1, 2):
            d = work_dir(school, grade, period, vol)
            os.makedirs(d, exist_ok=True)
            # ⚠ 이미 있는 config 는 **덮지 않는다** — 손잡이를 손봐 뒀을 수 있다.
            #   다만 산출·원고 자리와 학원 출력 설정은 지금 규칙으로 맞춘다.
            cpath = os.path.join(d, "config.json")
            want = book_config(school, grade, period, vol, base=base)
            if os.path.exists(cpath):
                cur = json.load(open(cpath, encoding="utf-8"))
                for k in ("output", "manuscript", "print"):
                    cur[k] = want[k]
                want = cur
            json.dump(want, open(cpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            cfg = B.load(d)
            log("[Vol%d] 조판 중…" % vol)
            B.gen_data(cfg, log)
            B.build(cfg, log)
            B.print_pdf(cfg, log)
            B.verify(cfg, log)
            # 확인용(RGB) 내지는 검수가 끝나면 지운다 — 인쇄본만 남긴다.
            raw = cfg.out_pdf(cfg.section("verify").get("suffix", ""))
            if os.path.exists(raw) and "인쇄" not in os.path.basename(raw):
                os.remove(raw)
            pr = cfg.out_pdf(cfg.section("print").get("out", "_인쇄"))
            if os.path.exists(pr):
                made.append(pr)
        for p in made:
            try:
                shutil.copy2(p, os.path.join(job_dir, os.path.basename(p)))
            except Exception:
                pass
        log("완성: " + " · ".join(os.path.basename(p) for p in made))

        # 이번 조판이 **실제로 쓴** 범위를 책 폴더에 남긴다 — 검수가 같은
        # 것을 읽는다(조판은 Y.OS, 검수는 시트… 로 갈리던 자리다).
        from engines.final import scope_source as S
        sc = getattr(self, "_scope", None)
        if sc:
            try:
                S.save(sc, base, log=log)
            except Exception as e:                             # noqa: BLE001
                log("[범위] 남기지 못했습니다: %s" % e)

        self._review(base, job_dir, log)
        return made

    # ── 3단계: 조판이 끝나면 바로 검수 ────────────────────────────────
    def _review(self, base, job_dir, log):
        """원고↔PDF 전수 대조(+ 눈 검수)를 조판에 이어 붙인다.

        판정은 **조언**이다 — 검수가 걸렸다고 조판을 없던 일로 하지 않는다.
        대신 무엇이 걸렸는지 로그와 `<책폴더>/review.json` 에 남긴다.
        눈 검수(검수 에이전트)는 느리고 돈이 드니 `YONE_REVIEW_AGENT=1` 일 때만.
        """
        try:
            spath = os.path.join(BASE_DIR, "scripts")
            if spath not in sys.path:
                sys.path.insert(0, spath)
            from final_viv_review import review
            r = review(base, agent=os.environ.get("YONE_REVIEW_AGENT") == "1",
                       log=log)
            try:
                shutil.copy2(os.path.join(base, "review.json"),
                             os.path.join(job_dir, "review.json"))
            except Exception:
                pass
            return r
        except Exception as e:                                 # noqa: BLE001
            log("[검수] 건너뜀 (검수 실패가 조판을 막지 않음): %s" % e)
            return None

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
            sc = S.resolve(content.get("school", ""),
                           content.get("exam_period", ""), grade=g, log=log)
            if not sc or not sc["tokens"]:
                log("[원고직독] 시험범위를 못 읽어 되수확본으로 조판합니다")
                return content
            log("■ 시험범위: "
                + ", ".join(S.token_text(t) for t in sc["tokens"]))
            self._scope = sc
            # 빌더는 `scripts/` 에 있다(명령줄로도 쓰는 자리라 여기 둔다)
            spath = os.path.join(BASE_DIR, "scripts")
            if spath not in sys.path:
                sys.path.insert(0, spath)
            from final_manuscript_build import build as mbuild
            return mbuild(content, log=log, yos=sc)
        except Exception as e:
            log("[원고직독] 실패 — 되수확본으로 조판합니다: %s" % e)
            return content
