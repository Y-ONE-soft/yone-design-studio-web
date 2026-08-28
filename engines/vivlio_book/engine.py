# -*- coding: utf-8 -*-
"""비블리오(Vivliostyle) 조판 — **원고를 올리면 PDF 가 나온다.**

## 왜 이 카드가 필요했나

작업대(`/book-studio`)는 **이미 조판된 책의 값을 만지는** 화면이라, 새 원고가
왔을 때 넣을 입구가 없었다. 정작 가장 자주 하는 일이 그건데. 인디자인 교재들이
쓰는 카드 체계에 그대로 얹어, 같은 방식으로 쓰게 한다:
**교재 고르고 → 원고 올리고 → 돌리면 PDF.**

## 두 가지 쓰임

    같은 책, 새 원고    다음 학기 같은 교재 → 기준 책을 고르고 원고만 갈아 끼운다
    새 책              학교·시기가 바뀌면 새 폴더를 만들어 준다(설정은 기준 책에서 물려받는다)

**기준 책은 절대 건드리지 않는다.** 언제나 새 폴더를 만들고 거기에 조판한다 —
납품한 책이 조용히 바뀌는 것이 이 판에서 가장 위험한 일이기 때문이다.

## 계열마다 원고를 찾는 방식이 다르다

    vocabook·vocaunit·special   config 의 `manuscript.files` 가 **파일 이름을 딱 집는다**
    blackbook                   `manuscript.pattern` 으로 원고 폴더를 훑는다

그래서 이름을 집는 계열은 **올린 파일 이름으로 config 를 갱신**해 준다(원고 이름은
학기마다 바뀌니 사용자에게 이름을 맞추라고 할 수 없다). 훑는 계열은 그냥 넣으면 된다.

## 조판은 하위 프로세스로 돈다

통합웹은 파이썬 3.9 로 뜨는데 조판 엔진은 3.14 를 쓴다. 게다가 계열 모듈이
전역 상태를 들고 있어 한 요청이 다음 요청에 샐 수 있다(표지 작업대가 같은 이유로
subprocess 를 쓴다). `python3 -m core.render_vivlio.book` 를 부른다.
"""
import json
import os
import shutil
import subprocess
import sys
import unicodedata as u

from core.base import BaseEngine

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_SLOTS = 8          # 지금까지 원고가 가장 많은 책이 3개. 넉넉히.


def _nfc(s):
    return u.normalize("NFC", s or "")


def _python():
    """조판 엔진을 돌릴 파이썬 (통합웹이 뜬 것과 다를 수 있다)."""
    for p in (os.environ.get("YONE_VIV_PYTHON"),
              "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
              "/opt/homebrew/bin/python3", sys.executable):
        if p and os.path.exists(p):
            return p
    return sys.executable


def _viv(args, log=None, timeout=1800):
    """`bin/viv` 와 같은 것을 부른다. 로그는 그대로 흘려보낸다."""
    cmd = [_python(), "-u", "-m", "core.render_vivlio.book"] + args
    p = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    out = []
    for line in p.stdout:
        line = line.rstrip()
        out.append(line)
        if log and line:
            log("  " + line)
    p.wait(timeout=timeout)
    return p.returncode, "\n".join(out)


def books():
    """조판 가능한 비블리오 책 목록 (교재 트리에서 찾는다)."""
    rc, out = _viv(["list", "--json"], timeout=120)
    if rc != 0:
        return []
    try:
        return json.loads(out[out.find("["):]) if "[" in out else []
    except ValueError:
        return []


def book_slots(key):
    """기준 책이 요구하는 원고 슬롯. `[]` 면 '폴더를 훑는 계열'."""
    from core.render_vivlio.config import _studio_root, load as load_cfg
    cfg = load_cfg(os.path.join(_studio_root(), key))
    m = cfg.section("manuscript") or {}
    files = m.get("files") or {}
    return [{"key": k, "label": k, "current": v} for k, v in sorted(files.items())]


class VivlioBookEngine(BaseEngine):

    material_id = "vivlio_book"
    display_name = "비블리오 조판 (코드 조판)"
    description = ("원고를 올리면 Vivliostyle 로 조판해 PDF 까지. "
                   "블랙북·단어장·특강 등 코드 조판 교재.")
    template_name = "typeset_vivlio_book.html"
    render_backend = "vivliostyle"
    log_filename = "조판_로그.txt"

    @property
    def upload_spec(self):
        """슬롯은 **책마다 다르다** — 여기서는 넉넉한 칸만 열어 두고, 화면이
        고른 책에 맞춰 필요한 칸만 보여 준다. 어느 칸이 어느 원고인지는
        `slotmap` 이 알려 준다(화면이 채운다)."""
        slots = [
            {"key": "base_book", "label": "기준 책", "type": "text",
             "required": True},
            {"key": "new_folder", "label": "새 폴더 이름 (예: 27-1-중간)",
             "type": "text", "required": True},
            {"key": "new_name", "label": "새 교재 이름 (비우면 기준 책과 같은 교재)",
             "type": "text", "required": False},
            {"key": "new_title", "label": "책 표시 이름", "type": "text",
             "required": False},
            {"key": "new_school", "label": "학교", "type": "text",
             "required": False},
            {"key": "slotmap", "label": "슬롯 지정", "type": "text",
             "required": False},
        ]
        for i in range(1, MAX_SLOTS + 1):
            slots.append({"key": f"m{i}", "label": f"원고 {i}",
                          "required": i == 1})
        return {"slots": slots}

    # ── ① 새 책 폴더를 만들고 원고를 넣는다 ──────────────────────
    def parse(self, uploaded, job_dir, log):
        from core.render_vivlio import knobs as kn
        from core.render_vivlio.config import _studio_root

        base_key = _nfc(self._meta(job_dir, "base_book"))
        if not base_key:
            raise ValueError("기준 책을 고르지 않았다")
        known = {_nfc(b["key"]): b for b in books()}
        if base_key not in known:
            raise ValueError(f"모르는 기준 책: {base_key}")
        studio = _studio_root()
        base_dir = os.path.join(studio, known[base_key]["key"])

        folder = self._meta(job_dir, "new_folder").strip()
        if not folder or any(c in folder for c in "/\\.."):
            raise ValueError("새 폴더 이름이 이상하다 (예: 27-1-중간)")
        new_name = self._meta(job_dir, "new_name").strip()
        # 기준 책이 `…/단어장/광문보카/26-2-중간` 이면
        #   교재 이름 그대로 → `…/광문보카/<folder>`
        #   새 교재 이름     → `…/단어장/<new_name>/<folder>`
        parent = os.path.dirname(base_dir)                  # …/광문보카
        if new_name:
            parent = os.path.join(os.path.dirname(parent), new_name)
        out_dir = os.path.join(parent, folder)
        if os.path.exists(out_dir) and os.listdir(out_dir):
            raise ValueError(
                f"이미 있는 폴더다: {out_dir.replace(studio + os.sep, '')}\n"
                f"  → 덮어쓰지 않는다. 다른 이름을 쓰거나 그 폴더를 치울 것")
        os.makedirs(os.path.join(out_dir, "원고"), exist_ok=True)
        log(f"[새 책] {out_dir.replace(studio + os.sep, '')}")

        # 설정은 기준 책에서 물려받는다 (원고·산출물은 안 가져온다)
        raw = open(os.path.join(base_dir, "config.json"), encoding="utf-8").read()

        # 원고 넣기 — 올린 이름 그대로 (이름을 맞추라고 하지 않는다)
        smap = [s for s in self._meta(job_dir, "slotmap").split(",") if s.strip()]
        changes, n = {}, 0
        for i in range(1, MAX_SLOTS + 1):
            src = uploaded.get(f"m{i}")
            if not src or not os.path.exists(str(src)):
                continue
            name = os.path.basename(str(src))
            shutil.copy2(src, os.path.join(out_dir, "원고", name))
            n += 1
            log(f"  원고 {i}: {name}")
            if i - 1 < len(smap):
                changes[f"manuscript.files.{smap[i - 1].strip()}"] = name
        if not n:
            raise ValueError("원고를 하나도 올리지 않았다")

        # 이름을 딱 집는 계열은 config 를 올린 파일 이름으로 갱신
        meta = {"book.id": folder, "output.stem": None}
        for k, v in (("book.title", self._meta(job_dir, "new_title")),
                     ("book.school", self._meta(job_dir, "new_school")),
                     ("book.period", folder)):
            if v:
                changes[k] = v
        stem = self._meta(job_dir, "new_title") or folder
        changes["output.stem"] = f"{stem}_내지"
        try:
            raw = kn.patch_text(raw, changes)
        except Exception as e:                     # 모양이 특이하면 통째로
            log(f"  [알림] 설정 부분 수정 실패({e}) — 통째로 쓴다")
            d = kn.apply(json.loads(raw), changes)
            raw = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
        with open(os.path.join(out_dir, "config.json"), "w",
                  encoding="utf-8") as f:
            f.write(raw)
        if changes:
            log(f"  설정 {len(changes)}곳 갱신 (원고 이름·책 정보)")

        # 원고 → data.json (계열의 인식 게이트가 여기서 돈다)
        log("[원고 인식] …")
        rc, out = _viv([out_dir, "data"], log)
        if rc != 0:
            raise RuntimeError("원고를 인식하지 못했다 — 위 로그를 볼 것")

        content = {"book_dir": out_dir, "base": base_key,
                   "title": stem, "manuscripts": n}
        p = os.path.join(job_dir, "content.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=1)
        return p

    # ── ② 조판 ──────────────────────────────────────────────────
    def render_vivlio(self, json_path, job_dir, log):
        content = json.load(open(json_path, encoding="utf-8"))
        book_dir = content["book_dir"]
        rc, out = _viv([book_dir, "build"], log)
        if rc != 0:
            raise RuntimeError("조판 실패 — 위 로그를 볼 것")
        # 인쇄 원고 절이 있는 책은 같이 만든다 (안 하면 조용히 옛 색으로 남는다)
        cfg = json.load(open(os.path.join(book_dir, "config.json"),
                             encoding="utf-8"))
        if cfg.get("print"):
            log("[인쇄 원고] CMYK 변환 …")
            _viv([book_dir, "print"], log)
        pdf = self._find_pdf(book_dir, cfg)
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"output_dir": book_dir, "pdf_path": pdf}, f,
                      ensure_ascii=False)
        if pdf:
            log(f"[산출] {os.path.basename(pdf)}")

    @staticmethod
    def _find_pdf(book_dir, cfg):
        stem = ((cfg.get("output") or {}).get("stem")
                or (cfg.get("book") or {}).get("id") or "내지")
        p = os.path.join(book_dir, stem + ".pdf")
        return p if os.path.exists(p) else None

    def prepare_jsx(self, json_path, job_dir, log):
        raise NotImplementedError("이 교재는 인디자인을 쓰지 않는다")

    # ── ③ 검수 ──────────────────────────────────────────────────
    def verify(self, job_dir, log):
        s = os.path.join(job_dir, ".settings.json")
        if not os.path.exists(s):
            return {"ok": False, "overflow": 0, "stories": {},
                    "pdf_path": None, "warnings": ["조판 결과를 찾지 못했다"]}
        d = json.load(open(s, encoding="utf-8"))
        rc, out = _viv([d["output_dir"], "verify"], log)
        warns = [ln.strip(" -!") for ln in out.splitlines()
                 if ln.strip().startswith(("-", "!"))]
        return {"ok": rc == 0, "overflow": 0, "stories": {},
                "pdf_path": d.get("pdf_path"), "warnings": warns[:40]}

    # ── 도우미 ──────────────────────────────────────────────────
    @staticmethod
    def _meta(job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(p):
            return open(p, encoding="utf-8").read().strip()
        return default
