"""정답및해설 원고 -> 해설지 PDF (문제지와 동일 판형/디자인).

    python3 build_solution.py 정답및해설.hwpx --out DIR [--exam 문제.hwpx]

QC:
  - 문항 수 = 문제지 출처 수 (있으면 대조)
  - 원고 글자 전량 반영 (difflib, 12자 이상 결손 나열)
  - 정답 개수/형식
  - 빈 페이지 없음
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import hwpx_rich            # noqa: E402
import parse_solution as S  # noqa: E402
import render_solution as R  # noqa: E402
from build import _today_short, norm  # noqa: E402


def qc_content(doc, raw_paras):
    """원고 글자가 해설지에 전량 반영됐는지 (difflib 12자 이상 결손)."""
    # 출처 줄 `[...] 정답 X` 은 해설지에서 '번호 배지 + 정답 X' 로 바뀐다.
    # 대조 시 접두어([...]와 '정답' 글자)를 떼고 정답 기호만 남긴다.
    def _strip(t):
        t = t.strip()
        if re.match(r"^\s*정답\s*및\s*해설\s*$", t):
            return ""
        return re.sub(r"^\[[^\]]+\]\s*정답\s*", "", t)
    src = norm(" ".join(_strip(p["text"]) for p in raw_paras))
    seq = []
    for it in doc["items"]:
        seq.append(it["answer"])
        for s in it["sections"]:
            seq.append(s["label"])
            seq.append(s["text"])
    out = norm(" ".join(seq))
    sm = difflib.SequenceMatcher(None, src, out, autojunk=False)
    gaps = []
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= 12:
            gaps.append({"len": i2 - i1, "text": src[i1:i2][:120]})
    return {"src_chars": len(src), "out_chars": len(out), "gaps": gaps}


def qc_pdf(pdf_path, n_items):
    import fitz
    d = fitz.open(pdf_path)
    pages = len(d)
    empty = [i + 1 for i, pg in enumerate(d) if not pg.get_text().strip()]
    # 번호 배지 존재 확인: 흰 글자라 텍스트로는 잡히나, 정답 기호 개수로 갈음
    txt = "\n".join(pg.get_text() for pg in d)
    n_ans = len(re.findall(r"정답\s*[①-⑤]", txt))
    d.close()
    return {"pages": pages, "empty_pages": empty, "answers_rendered": n_ans}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manuscript")
    ap.add_argument("--out", required=True)
    ap.add_argument("--exam")
    ap.add_argument("--config")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()

    cfg = {
        "title": "세서특필 모의고사",
        "subtitle": "2026학년도 여름방학 세서특필 모의고사",
        "exam_date_short": _today_short(),
        "logo": "logo.png",
    }
    if a.config:
        cfg.update(json.load(open(a.config, encoding="utf-8")))

    os.makedirs(a.out, exist_ok=True)
    build = os.path.join(a.out, "build")
    os.makedirs(build, exist_ok=True)
    report = {"steps": {}}

    t0 = time.time()
    paras = hwpx_rich.extract(a.manuscript)
    doc = S.parse(paras)
    report["items"] = len(doc["items"])
    report["answers"] = [it["answer"] for it in doc["items"]]

    if a.exam:                       # 문제지와 출처·순서 대조
        import parse_exam as P
        ex = P.parse(hwpx_rich.extract(a.exam))
        ex_src = [it["src"] for it in ex["items"]]
        sol_src = [it["src"] for it in doc["items"]]
        report["match_exam"] = {
            "exam_items": len(ex_src), "sol_items": len(sol_src),
            "order_ok": ex_src == sol_src,
            "missing_in_sol": [s for s in ex_src if s not in sol_src]}

    report["qc_missing_text"] = qc_content(doc, paras)

    html = R.build_html(doc, cfg)
    hp = os.path.join(build, "solution.html")
    open(hp, "w", encoding="utf-8").write(html)
    shutil.copy(os.path.join(HERE, "solution_theme.css"), build)
    logo_src = os.path.join(HERE, "assets", "logo_sehui.png")
    if cfg.get("logo") and os.path.exists(logo_src):
        shutil.copy(logo_src, os.path.join(build, cfg["logo"]))

    pdf = os.path.join(a.out, "solution.pdf")
    if not a.no_pdf:
        t1 = time.time()
        cli = os.path.join(HERE, "..", "node_modules", ".bin", "vivliostyle")
        r = subprocess.run([cli, "build", hp, "-o", pdf, "-f", "pdf"],
                           capture_output=True, text=True)
        report["steps"]["pdf_s"] = round(time.time() - t1, 2)
        if r.returncode != 0:
            report["pdf_error"] = (r.stdout + r.stderr)[-3000:]
        else:
            report["qc_pdf"] = qc_pdf(pdf, len(doc["items"]))

    report["steps"]["total_s"] = round(time.time() - t0, 2)
    json.dump(report, open(os.path.join(a.out, "report.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("answers",)}, ensure_ascii=False, indent=1)[:1800])


if __name__ == "__main__":
    main()
