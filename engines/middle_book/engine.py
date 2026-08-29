# -*- coding: utf-8 -*-
"""중등 내신 정규 교재 (같이새김·홀로새김) — 원고를 올리면 PDF.

## 왜 따로인가

이 교재만 조판 코드가 **3계층 엔진 밖**에 있다
(`조판/교재/중등부/내신 정규 교재/automation/`). 그래서 `bin/viv` 도, 내지 작업대도
이 여섯 권을 못 본다. 코드를 옮기는 것이 옳지만 그건 6권을 다시 검증해야 하는
큰 일이라, **지금 있는 automation 을 그대로 부르는 얇은 껍데기**를 먼저 씌운다.
적어도 "원고 올리면 PDF" 는 다른 교재와 같은 자리에서 되게.

    python3 extract.py  <교재키> <권>   원고 docx → raw.json
    python3 gen_data.py <교재키> <권>   raw → data (구조 파싱 + 3중 게이트)
    python3 build.py    <교재키> <권>   렌더 → Vivliostyle → 면 패리티 → TrimBox
    python3 verify.py   <교재키> <권>   원고 ↔ PDF 전수 대조

## ⚠ 이 카드는 **기존 책 폴더에 다시 조판한다**

3계층 교재(비블리오 조판 카드)는 언제나 새 폴더를 만들지만, 여기는 교재 표
(`automation/book.py` 의 `BOOKS`)가 폴더를 쥐고 있어서 새 교재를 web 에서 만들 수
없다 — 그건 코드를 고치는 일이다. 그래서 **덮어쓰기 전에 원고와 산출 PDF 를
`_backup/<날짜>/` 로 통째 옮겨 둔다.** 이 교재들은 실제로 수정·수정2·최종으로
여러 번 다시 조판하는 흐름이라 그 편이 실제 작업과도 맞는다.

## ⚠ 원고 이름에 권 표시가 있어야 한다

`book.py::manuscript()` 가 `원고/` 안에서 **`1권`/`2권` 이 이름에 든 docx** 를
찾는다. 올린 파일 이름에 그게 없으면 못 찾으므로, 없을 때만 앞에 붙여 준다.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

from core.base import BaseEngine

VOLS = {"1": "1권", "2": "2권"}


def _auto_dir():
    from core.render_vivlio.config import _studio_root
    return os.path.join(_studio_root(), "조판", "교재", "중등부",
                        "내신 정규 교재", "automation")


def _python():
    for p in (os.environ.get("YONE_VIV_PYTHON"),
              "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
              "/opt/homebrew/bin/python3", sys.executable):
        if p and os.path.exists(p):
            return p
    return sys.executable


def _run(script, args, log=None, timeout=1800):
    cmd = [_python(), "-u", os.path.join(_auto_dir(), script)] + args
    p = subprocess.Popen(cmd, cwd=_auto_dir(), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    out = []
    for line in p.stdout:
        line = line.rstrip()
        out.append(line)
        if log and line:
            log("  " + line)
    p.wait(timeout=timeout)
    return p.returncode, "\n".join(out)


def catalog():
    """`automation/book.py` 의 교재 표를 그대로 읽는다 — 표를 두 벌 두지 않는다."""
    code = ("import json,sys;sys.path.insert(0,%r);import book;"
            "print(json.dumps([{'key':k,'label':v['label'],"
            "'dir':v['dir'],'vols':sorted(v['out'])} "
            "for k,v in book.BOOKS.items()],ensure_ascii=False))"
            % _auto_dir())
    try:
        r = subprocess.run([_python(), "-c", code], capture_output=True,
                           text=True, timeout=60)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return []


class MiddleBookEngine(BaseEngine):

    material_id = "middle_book"
    display_name = "중등 내신 정규 교재"
    description = ("같이새김(1권)·홀로새김(2권). 원고 docx 를 올리면 "
                   "인식 → 조판 → 전수 대조까지.")
    template_name = "typeset_middle_book.html"
    render_backend = "vivliostyle"
    log_filename = "조판_로그.txt"

    @property
    def upload_spec(self):
        return {"slots": [
            {"key": "mb_book", "label": "교재", "type": "text", "required": True},
            {"key": "mb_vol", "label": "권", "type": "text", "required": True},
            {"key": "manuscript", "label": "원고 (.docx)", "required": True},
        ]}

    # ── ① 원고를 넣고 인식 ──────────────────────────────────────
    def parse(self, uploaded, job_dir, log):
        from core.render_vivlio.config import _studio_root
        bk = self._meta(job_dir, "mb_book").strip()
        vol = self._meta(job_dir, "mb_vol").strip()
        known = {c["key"]: c for c in catalog()}
        if bk not in known:
            raise ValueError(f"모르는 교재: {bk} — {', '.join(known)}")
        if vol not in VOLS:
            raise ValueError(f"권은 1 또는 2 여야 한다: {vol}")
        info = known[bk]
        root = os.path.join(_studio_root(), "조판", "교재", "중등부",
                            "내신 정규 교재", info["dir"])
        src = uploaded.get("manuscript")
        if not src or not os.path.exists(str(src)):
            raise ValueError("원고를 올리지 않았다")

        # 덮어쓰기 전에 통째로 백업 — 이 카드는 기존 폴더에 다시 조판한다
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = os.path.join(root, "_backup", stamp)
        os.makedirs(bdir, exist_ok=True)
        moved = 0
        mdir = os.path.join(root, "원고")
        if os.path.isdir(mdir):
            shutil.copytree(mdir, os.path.join(bdir, "원고"))
            moved += 1
        for f in os.listdir(root):
            if f.lower().endswith(".pdf"):
                shutil.copy2(os.path.join(root, f), os.path.join(bdir, f))
                moved += 1
        log(f"[백업] 이전 원고·PDF {moved}건 → _backup/{stamp}/")

        # 원고 넣기 — 이름에 권 표시가 없으면 붙인다(그게 없으면 못 찾는다)
        os.makedirs(mdir, exist_ok=True)
        name = os.path.basename(str(src))
        for pre in ("manuscript_",):
            if name.startswith(pre):
                name = name[len(pre):]
        if VOLS[vol] not in name:
            name = f"{VOLS[vol]} {name}"
            log(f"  이름에 '{VOLS[vol]}' 이 없어 붙였다 (원고 찾기 규칙)")
        # 같은 권의 묵은 원고는 치운다 — 두 벌이면 이름 순으로 골라져 사고가 난다
        old = os.path.join(mdir, "_이전본")
        for f in list(os.listdir(mdir)):
            if f.endswith(".docx") and VOLS[vol] in f and f != name:
                os.makedirs(old, exist_ok=True)
                shutil.move(os.path.join(mdir, f), os.path.join(old, f))
                log(f"  묵은 원고를 _이전본/ 으로: {f}")
        shutil.copy2(src, os.path.join(mdir, name))
        log(f"[원고] {name}")

        log("[원고 인식] extract …")
        rc, _ = _run("extract.py", [bk, vol], log)
        if rc != 0:
            raise RuntimeError("원고를 읽지 못했다")
        log("[구조 파싱] gen_data …")
        rc, _ = _run("gen_data.py", [bk, vol], log)
        if rc != 0:
            raise RuntimeError("구조 파싱 게이트를 통과하지 못했다")

        content = {"book": bk, "vol": vol, "root": root,
                   "label": info["label"], "backup": bdir}
        p = os.path.join(job_dir, "content.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=1)
        return p

    # ── ② 조판 ──────────────────────────────────────────────────
    def render_vivlio(self, json_path, job_dir, log):
        c = json.load(open(json_path, encoding="utf-8"))
        rc, _ = _run("build.py", [c["book"], c["vol"]], log)
        if rc != 0:
            raise RuntimeError("조판 실패 — 위 로그를 볼 것")
        pdf = self._newest_pdf(c["root"])
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"output_dir": c["root"], "pdf_path": pdf}, f,
                      ensure_ascii=False)
        if pdf:
            log(f"[산출] {os.path.basename(pdf)}")

    @staticmethod
    def _newest_pdf(root):
        ps = [os.path.join(root, f) for f in os.listdir(root)
              if f.lower().endswith(".pdf")]
        return max(ps, key=os.path.getmtime) if ps else None

    def prepare_jsx(self, json_path, job_dir, log):
        raise NotImplementedError("이 교재는 인디자인을 쓰지 않는다")

    # ── ③ 검수 — 원고 ↔ PDF 전수 대조 ───────────────────────────
    def verify(self, job_dir, log):
        cp = os.path.join(job_dir, "content.json")
        sp = os.path.join(job_dir, ".settings.json")
        if not (os.path.exists(cp) and os.path.exists(sp)):
            return {"ok": False, "overflow": 0, "stories": {},
                    "pdf_path": None, "warnings": ["조판 결과를 찾지 못했다"]}
        c = json.load(open(cp, encoding="utf-8"))
        s = json.load(open(sp, encoding="utf-8"))
        rc, out = _run("verify.py", [c["book"], c["vol"]], log)
        warns = [ln.strip(" -!✗") for ln in out.splitlines()
                 if ln.strip().startswith(("-", "!", "✗"))]
        return {"ok": rc == 0, "overflow": 0, "stories": {},
                "pdf_path": s.get("pdf_path"), "warnings": warns[:40]}

    @staticmethod
    def _meta(job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(p):
            return open(p, encoding="utf-8").read().strip()
        return default
