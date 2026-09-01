# -*- coding: utf-8 -*-
"""포켓북 (Vivliostyle) — **학교·학기를 고르면 PDF 가 나온다.**

## 왜 전용 카드인가

`vivlio_book` 카드는 "원고를 올리면 새 책 폴더를 만들어 조판한다"는 계열용이다.
포켓북은 입력이 다르다 — 지문이 **원고가 아니라 코퍼스·분석본**에서 오고,
교재팀 원고(hwpx)는 플로우노트·동반의어만 얹는다. 그래서 그 카드에 억지로
얹으면 슬롯 뜻이 어긋난다.

## 무엇을 받나

    학교·학기        코퍼스에서 이미 있는 지문을 고른다
    분석본           이번 학기 **새 지문**(IDML). 폴더째 준다
    교재팀 원고      플로우노트 + 동반의어 (hwpx). 없으면 그 자리가 빈다
    리뷰테스트       암기 TEST 원고. 기본값은 `리테 모음` 폴더 전체

## 책 폴더는 만들되, 있으면 그대로 쓴다

조판 설정(`config.json`)은 `조판/교재/포켓북/<학기>/<학교>/` 에 산다. 없으면
`_템플릿` 에서 만들고, **있으면 손대지 않는다** — 작업대에서 만진 색·치수가
카드를 한 번 돌렸다고 날아가면 안 되기 때문이다. 원고 경로만 갱신한다.

## 조판은 하위 프로세스로 돈다

통합웹은 파이썬 3.9 로 뜨는데 조판 엔진은 3.14 를 쓴다. `vivlio_book` 과 같은
이유·같은 방식이다(`python3 -m core.render_vivlio.book`).

## InDesign 은 기본으로 안 쓴다

분석본 `.indd` → `.idml` 내보내기만 InDesign 이 필요하다. 그건 **미리 돌려 두는
일**로 보고, 카드는 이미 나와 있는 IDML 만 쓴다. 없으면 무엇을 돌려야 하는지
알려 준다(자동으로 열지 않는다 — 남의 문서가 열려 있을 수 있다).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import unicodedata as u

from core.base import BaseEngine

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _nfc(s):
    return u.normalize("NFC", s or "")


def _studio():
    from core.render_vivlio.config import _studio_root
    return _studio_root()


def _pocket_root():
    return os.path.join(_studio(), "조판", "교재", "포켓북")


def schools_for(term):
    """그 학기에 **분석본 IDML 이 나와 있는** 학교 목록."""
    base = os.path.join(_pocket_root(), "_idml", "analysis")
    out = set()
    if not os.path.isdir(base):
        return []
    for dirpath, dirnames, _f in os.walk(base):
        if _nfc(os.path.basename(dirpath)) == _nfc(term):
            for d in dirnames:
                if not d.startswith("."):
                    out.add(_nfc(d))
            dirnames[:] = []
    return sorted(out)


def terms():
    """분석본 IDML 이 있는 학기 목록 + 이미 만든 책 폴더의 학기."""
    out = set()
    base = os.path.join(_pocket_root(), "_idml", "analysis")
    for dirpath, dirnames, _f in os.walk(base if os.path.isdir(base) else "."):
        for d in dirnames:
            n = _nfc(d)
            if n[:2].isdigit() and "-" in n:
                out.add(n)
    for d in glob.glob(os.path.join(_pocket_root(), "*")):
        n = _nfc(os.path.basename(d))
        if os.path.isdir(d) and n[:2].isdigit() and "-" in n:
            out.add(n)
    return sorted(out, reverse=True)


class PocketbookVivEngine(BaseEngine):

    render_backend = "vivliostyle"

    @property
    def material_id(self):
        return "pocketbook_viv"

    @property
    def display_name(self):
        return "포켓북 (Vivliostyle)"

    @property
    def description(self):
        return ("포켓북 조판 — 지문 코퍼스·분석본 → CSS Paged Media → PDF "
                "(InDesign 없이 조판)")

    @property
    def subject_prefix(self):
        return "포켓북"

    @property
    def template_name(self):
        return "typeset_pocketbook_viv.html"

    @property
    def upload_spec(self):
        return {"slots": [
            {"key": "school", "label": "학교", "type": "text", "required": True},
            {"key": "term", "label": "학기 (예: 26-2-중간)", "type": "text",
             "required": True},
            {"key": "use_corpus", "label": "기존 지문도 넣기(코퍼스)",
             "type": "text", "required": False},
            {"key": "m1", "label": "교재팀 원고 (hwpx · 플로우노트+동반의어)",
             "required": False},
            {"key": "m2", "label": "교재팀 원고 2", "required": False},
        ]}

    # ── 1단계: 책 폴더를 세우고 무엇으로 조판할지 적는다 ──────────
    def parse(self, uploaded, job_dir, log):
        school = _nfc(self._meta(job_dir, "school")).strip()
        term = _nfc(self._meta(job_dir, "term")).strip()
        if not school or not term:
            raise ValueError("학교와 학기를 골라야 한다")
        if any(c in school + term for c in "/\\.."):
            raise ValueError("학교·학기 이름이 이상하다")

        root = _pocket_root()
        book_dir = os.path.join(root, term, school)
        tmpl = os.path.join(root, "_템플릿", "config.json")
        cfg_path = os.path.join(book_dir, "config.json")

        analysis = self._analysis_dir(root, term, school)
        if not analysis and not self._meta(job_dir, "use_corpus"):
            raise ValueError(
                "이 학교의 분석본 IDML 이 없다: %s/%s\n"
                "  → 먼저 내보내기를 돌릴 것 (InDesign 필요):\n"
                "     python3 tools/pocket_harvest/export_idml.py analysis "
                "--only=%s\n"
                "  → 또는 '기존 지문도 넣기'를 켜서 코퍼스만으로 조판할 것"
                % (term, school, term))

        created = False
        if not os.path.exists(cfg_path):
            if not os.path.exists(tmpl):
                raise ValueError("템플릿이 없다: %s" % tmpl)
            os.makedirs(book_dir, exist_ok=True)
            shutil.copy2(tmpl, cfg_path)
            created = True
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)

        # ⚠ 색·치수(palette·metrics)는 **건드리지 않는다** — 작업대에서 만진
        #   값이 카드를 한 번 돌렸다고 날아가면 안 된다. 원고 경로만 갱신한다.
        cfg["book"] = {"id": "%s_포켓북" % school,
                       "title": "%s 포켓북 %s" % (school, term)}
        cfg["output"] = {"dir": ".",
                         "stem": "%s_포켓북(%s)_내지" % (school, term)}
        opt = cfg.setdefault("options", {})
        opt["school"] = school
        opt["grade"] = self._grade_of(school)
        opt["analysis"] = [analysis] if analysis else []
        if self._meta(job_dir, "use_corpus"):
            opt["term"] = term
        else:
            opt.pop("term", None)
        opt["manuscript"] = self._save_manuscripts(uploaded, job_dir, book_dir,
                                                   log)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)

        log("■ 책 폴더 %s (%s)"
            % (os.path.relpath(book_dir, _studio()),
               "새로 만듦" if created else "기존 설정 유지"))
        log("■ 분석본 %s" % (os.path.relpath(analysis, root) if analysis
                             else "없음 — 코퍼스만"))
        log("■ 교재팀 원고 %d개" % len(opt["manuscript"]))

        out = os.path.join(job_dir, "content.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"book_dir": book_dir, "school": school, "term": term},
                      f, ensure_ascii=False)
        return out

    def prepare_jsx(self, json_path, job_dir, log):
        """InDesign 경로는 쓰지 않는다 — 파이프라인이 백엔드를 보고 갈라간다."""
        raise RuntimeError("이 카드는 Vivliostyle 로만 조판한다 (InDesign 경로 없음)")

    # ── 2단계: 조판 (하위 프로세스) ────────────────────────────────
    def render_vivlio(self, json_path, job_dir, log):
        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)
        book_dir = meta["book_dir"]
        cmd = [sys.executable if sys.version_info >= (3, 12) else "python3",
               "-m", "core.render_vivlio.book", book_dir, "all"]
        log("$ %s" % " ".join(cmd[-3:]))
        p = subprocess.Popen(cmd, cwd=_REPO, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1,
                             env=dict(os.environ, PYTHONUNBUFFERED="1"))
        tail = []
        for line in p.stdout:
            line = line.rstrip()
            if line:
                log(line)
                tail.append(line)
                del tail[:-40]
        rc = p.wait()
        if rc != 0:
            raise RuntimeError("조판 실패 (exit %d)\n%s"
                               % (rc, "\n".join(tail[-12:])))

        pdf = self._out_pdf(book_dir)
        empty = os.path.join(book_dir, "build", "빈항목.md")
        settings = {"engine": self.material_id, "backend": "vivliostyle",
                    "book_dir": book_dir, "output_dir": os.path.dirname(pdf)
                    if pdf else book_dir, "pdf_path": pdf,
                    "empty_report": empty if os.path.exists(empty) else None,
                    "school": meta["school"], "term": meta["term"]}
        sp = os.path.join(job_dir, ".settings.json")
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return sp

    # ── 3단계: 검수 — 계열 게이트 결과를 그대로 옮긴다 ─────────────
    def verify(self, job_dir, log):
        sp = os.path.join(job_dir, ".settings.json")
        if not os.path.exists(sp):
            return {"ok": False, "warnings": ["조판 기록이 없다"]}
        with open(sp, encoding="utf-8") as f:
            st = json.load(f)
        pdf = st.get("pdf_path")
        ok = bool(pdf and os.path.exists(pdf))
        warns = []
        if not ok:
            warns.append("산출 PDF 가 없다: %s" % pdf)
        rep = st.get("empty_report")
        if rep and os.path.exists(rep):
            with open(rep, encoding="utf-8") as f:
                txt = f.read()
            n_syn = self._count(txt, "동반의어 0개")
            n_flow = self._count(txt, "플로우노트 0개")
            if n_syn or n_flow:
                warns.append("교재팀 원고가 필요한 지문 — 동반의어 %d · "
                             "플로우노트 %d (build/빈항목.md)" % (n_syn, n_flow))
        if ok:
            try:
                import fitz
                with fitz.open(pdf) as d:
                    log("■ 산출 %s (%d면)" % (os.path.basename(pdf), len(d)))
            except Exception:
                log("■ 산출 %s" % os.path.basename(pdf))
        return {"ok": ok, "warnings": warns,
                "files": [p for p in (pdf, rep) if p and os.path.exists(p)]}

    # ── 도구 ───────────────────────────────────────────────────────
    @staticmethod
    def _count(text, head):
        import re
        m = re.search(re.escape(head) + r"\D*(\d+)", text)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _grade_of(school):
        import re
        m = re.search(r"([123])\s*$", school or "")
        return "고%s" % m.group(1) if m else ""

    @staticmethod
    def _analysis_dir(root, term, school):
        base = os.path.join(root, "_idml", "analysis")
        for dirpath, dirnames, _f in os.walk(base if os.path.isdir(base) else "."):
            if _nfc(os.path.basename(dirpath)) != _nfc(term):
                continue
            for d in dirnames:
                if _nfc(d) == _nfc(school):
                    return os.path.join(dirpath, d)
        return None

    @staticmethod
    def _save_manuscripts(uploaded, job_dir, book_dir, log):
        """올린 hwpx 를 책 폴더 `원고/` 로 옮긴다. 업로드가 없으면 이미 있는 것."""
        dst_dir = os.path.join(book_dir, "원고")
        os.makedirs(dst_dir, exist_ok=True)
        n = 0
        for key in ("m1", "m2"):
            src = (uploaded or {}).get(key)
            if not src or not os.path.exists(src):
                continue
            dst = os.path.join(dst_dir, _nfc(os.path.basename(src)))
            shutil.copy2(src, dst)
            n += 1
        if n:
            log("■ 원고 %d개 저장 → %s" % (n, os.path.relpath(dst_dir, book_dir)))
        got = sorted(glob.glob(os.path.join(dst_dir, "*.hwpx")))
        return got

    @staticmethod
    def _out_pdf(book_dir):
        try:
            from core.render_vivlio import config as bookcfg
            cfg = bookcfg.load(book_dir)
            p = cfg.out_pdf()
            return p if os.path.exists(p) else None
        except Exception:
            cands = sorted(glob.glob(os.path.join(book_dir, "*.pdf")),
                           key=os.path.getmtime)
            return cands[-1] if cands else None

    @staticmethod
    def _meta(job_dir, key, default=""):
        p = os.path.join(job_dir, "%s.txt" % key)
        if os.path.exists(p):
            return open(p, encoding="utf-8").read().strip()
        return default
