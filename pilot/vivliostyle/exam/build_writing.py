"""서답형 워크시트 원고(docx) -> PDF (문제지와 동일 판형/디자인).

    python3 build_writing.py 서답형.docx --out DIR
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import parse_writing as W       # noqa: E402
import render_writing as R      # noqa: E402
from build import _today_short, norm  # noqa: E402
from core.extract import _docx_extract_paragraphs  # noqa: E402


def qc_content(doc, raw_paras):
    src = norm(" ".join(p["text"] for p in raw_paras))
    seq = []
    for s in doc["sets"]:
        if s.get("passage"):
            seq.append(s["passage"]["text"])
        for sub in s["subs"]:
            seq.append(sub["label"])
            seq.append(sub["question"])
            for x in ([sub.get("summary")] + sub.get("boxes", [])
                      + [sub.get("passage")] + sub.get("answer_lines", [])
                      + sub.get("extra", [])):
                if x:
                    seq.append(x["text"])
    out = norm(" ".join(seq))
    sm = difflib.SequenceMatcher(None, src, out, autojunk=False)
    gaps = []
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= 12:
            chunk = src[i1:i2]
            if chunk.strip("_"):        # 답란 언더스코어는 결손 아님
                gaps.append({"len": i2 - i1, "text": chunk[:120]})
    return {"src_chars": len(src), "out_chars": len(out), "gaps": gaps}


def qc_pdf(pdf_path, doc):
    """지문/하위문항이 단·쪽 경계에서 안 쪼개졌는지 (subq 텍스트 완결)."""
    import fitz
    d = fitz.open(pdf_path)
    pages = len(d)
    empty = [i + 1 for i, pg in enumerate(d) if not pg.get_text().strip()]
    txt = "\n".join(pg.get_text() for pg in d)
    labels = [sub["label"] for s in doc["sets"] for sub in s["subs"]]
    missing = [lab for lab in labels if lab not in txt.replace(" ", "")]
    d.close()
    return {"pages": pages, "empty_pages": empty,
            "subq_total": len(labels), "subq_missing": missing}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manuscript")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()

    paras = _docx_extract_paragraphs(a.manuscript, extract_underline=True)
    doc = W.parse(paras)

    cfg = {
        "title": doc["title"].replace("· 서답형 WEEK1", "").strip() or "서답형",
        "subtitle": doc["subtitle"],
        "exam_date_short": _today_short(),
        "logo": "logo.png",
    }
    # 제목: 원고 첫 줄이 "광문고 고1 대비 · 서답형 WEEK1" -> 제목/부제 분리
    m = re.match(r"(.*?)\s*·\s*(서답형.*)$", doc["title"])
    if m:
        cfg["subtitle"] = doc["title"]
        cfg["title"] = m.group(2).strip()
    if a.config:
        cfg.update(json.load(open(a.config, encoding="utf-8")))

    os.makedirs(a.out, exist_ok=True)
    build = os.path.join(a.out, "build")
    os.makedirs(build, exist_ok=True)
    report = {"steps": {}, "sets": len(doc["sets"]),
              "subqs": sum(len(s["subs"]) for s in doc["sets"])}

    t0 = time.time()
    report["qc_missing_text"] = qc_content(doc, paras)

    html = R.build_html(doc, cfg)
    hp = os.path.join(build, "writing.html")
    open(hp, "w", encoding="utf-8").write(html)
    shutil.copy(os.path.join(HERE, "writing_theme.css"), build)
    logo_src = os.path.join(HERE, "assets", "logo_sehui.png")
    if cfg.get("logo") and os.path.exists(logo_src):
        shutil.copy(logo_src, os.path.join(build, cfg["logo"]))

    pdf = os.path.join(a.out, "writing.pdf")
    if not a.no_pdf:
        t1 = time.time()
        cli = os.path.join(HERE, "..", "node_modules", ".bin", "vivliostyle")
        r = subprocess.run([cli, "build", hp, "-o", pdf, "-f", "pdf"],
                           capture_output=True, text=True)
        report["steps"]["pdf_s"] = round(time.time() - t1, 2)
        if r.returncode != 0:
            report["pdf_error"] = (r.stdout + r.stderr)[-3000:]
        else:
            report["qc_pdf"] = qc_pdf(pdf, doc)

    report["steps"]["total_s"] = round(time.time() - t0, 2)
    json.dump(report, open(os.path.join(a.out, "report.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1)[:1800])


if __name__ == "__main__":
    main()
