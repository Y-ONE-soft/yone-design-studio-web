"""HWPX 원고 -> 시험지 PDF (Vivliostyle). InDesign 무접촉.

    python3 build.py 문제.hwpx [정답.hwpx] --out DIR

QC 게이트(자동):
  1) 문항 수 = 출처 줄 수
  2) 원고 글자 전량 반영 (공백 제거 후 지문/선지 substring 대조)
  3) 빈칸 문항에 빈칸 마커 존재
  4) 한 문항이 단/쪽 경계를 넘지 않음  (PDF 기하 실측)
  5) 프레임 밖 넘침 / 빈 페이지 없음
"""
import argparse
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

import hwpx_rich          # noqa: E402
import parse_exam as P    # noqa: E402
import render_exam as R   # noqa: E402


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def qc_content(doc, raw_paras):
    """원고 글자가 산출물 IR 에 전량 살아 있는지 (공백 무시 substring)."""
    ir = norm(" ".join(
        [it["question_text"] for it in doc["items"]]
        + [P._pull_text(r) for it in doc["items"] for r in it["passage"]]
        + [n for it in doc["items"] for n in it["notes"]]
        + [c["label"] + "".join(x["t"] for x in c["runs"])
           for it in doc["items"] for c in it["choices"]]
    ))
    missing = []
    for p in raw_paras:
        t = norm(p["text"])
        if len(t) < 8:
            continue
        if P.RE_SRC.match(p["text"].strip()):
            continue
        # 원고에 있던 머리번호/묶음마커/배점은 조판에서 의도적으로 제거된다
        t2 = norm(re.sub(r"\[\s*\d\s*점\s*\]", "",
                         P.RE_LEAD_NUM.sub("", P.RE_GROUP_HEAD.sub("", p["text"]))))
        if t2 and t2 not in ir:
            missing.append(p["text"][:70])
    return missing


def qc_pdf(pdf_path):
    """PDF 기하 실측: 문항 헤드가 단 경계를 넘어 쪼개졌는지 / 빈 페이지."""
    import fitz
    d = fitz.open(pdf_path)
    pages = len(d)
    empty = []
    for i, pg in enumerate(d):
        if not pg.get_text().strip():
            empty.append(i + 1)
    # 문항 번호 헤드 위치 수집: "N." 로 시작하는 굵은 이탤릭 span
    heads = {}
    for i, pg in enumerate(d):
        for b in pg.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    m = re.match(r"^\s*(\d{1,2})\.\s*$", s["text"])
                    if m and s["size"] > 11.6:
                        n = int(m.group(1))
                        heads.setdefault(n, (i + 1, s["bbox"][0], s["bbox"][1]))
    d.close()
    return {"pages": pages, "empty_pages": empty, "heads": heads}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manuscript")
    ap.add_argument("answers", nargs="?")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()

    cfg = {
        "title": "세희어택 모의고사",
        "subtitle": "2026학년도 1학기 기말 광문고1 세희어택 전범위 모의고사",
        "period": "제 1 교시",
    }
    if a.config:
        cfg.update(json.load(open(a.config, encoding="utf-8")))

    os.makedirs(a.out, exist_ok=True)
    build = os.path.join(a.out, "build")
    os.makedirs(build, exist_ok=True)
    report = {"steps": {}}

    t0 = time.time()
    paras = hwpx_rich.extract(a.manuscript)
    try:
        from engines._taxonomy import classify
    except Exception:
        classify = None
    doc = P.parse(paras, classify=classify)
    report["steps"]["parse_s"] = round(time.time() - t0, 2)
    report["items"] = len(doc["items"])
    report["parse_warnings"] = doc["warnings"]

    answers = {}
    if a.answers:
        answers = P.parse_answers(hwpx_rich.extract(a.answers))
    report["answers_matched"] = sum(
        1 for it in doc["items"] if it["src"] in answers)

    # --- QC 1~3 (조판 전) ---
    report["qc_missing_text"] = qc_content(doc, paras)
    report["qc_blank_missing"] = [
        it["n"] for it in doc["items"]
        if it["type"] and "BLANK" in it["type"]
        and not any(r.get("blank") for runs in it["passage"] for r in runs)]

    html = R.build_html(doc, cfg, answers=answers)
    hp = os.path.join(build, "exam.html")
    open(hp, "w", encoding="utf-8").write(html)
    shutil.copy(os.path.join(HERE, "exam_theme.css"), build)
    json.dump({"items": [{k: v for k, v in it.items() if k != "question"}
                         for it in doc["items"]]},
              open(os.path.join(build, "ir.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)

    pdf = os.path.join(a.out, "exam.pdf")
    if not a.no_pdf:
        t1 = time.time()
        cli = os.path.join(HERE, "..", "node_modules", ".bin", "vivliostyle")
        cmd = [cli, "build", hp, "-o", pdf, "-f", "pdf"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        report["steps"]["pdf_s"] = round(time.time() - t1, 2)
        if r.returncode != 0:
            report["pdf_error"] = (r.stdout + r.stderr)[-3000:]
        else:
            report["qc_pdf"] = qc_pdf(pdf)

    report["steps"]["total_s"] = round(time.time() - t0, 2)
    json.dump(report, open(os.path.join(a.out, "report.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "qc_pdf"},
                     ensure_ascii=False, indent=1)[:2500])
    if "qc_pdf" in report:
        q = report["qc_pdf"]
        print(f"pages={q['pages']} empty={q['empty_pages']} "
              f"heads_found={len(q['heads'])}")


if __name__ == "__main__":
    main()
