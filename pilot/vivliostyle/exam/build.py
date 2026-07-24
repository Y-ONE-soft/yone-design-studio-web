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
    """원고 글자가 산출물에 전량 살아 있는지.

    조판이 의도적으로 지우는 것(출처 줄·머리번호·묶음마커·배점·빈칸 공백)이
    있으므로 단순 substring 으로는 판정할 수 없다. 문서 전체를 정규화해
    difflib 로 정렬하고, **연속 12자 이상 사라진 구간**만 결손으로 본다.
    """
    import difflib
    src = norm(" ".join(
        re.sub(r"\[\s*\d\s*점\s*\]", "",
               P.RE_LEAD_NUM.sub("", P.RE_GROUP_HEAD.sub("", p["text"])))
        for p in raw_paras if not P.RE_SRC.match(p["text"].strip())))
    # 원고와 같은 문서 순서로 이어붙여야 difflib 정렬이 성립한다.
    seq = []
    for it in doc["items"]:
        seq.append(it["question_text"])
        seq += [P._pull_text(r) for r in it["passage"]]
        seq += it["notes"]
        seq += [c["label"] + "".join(x["t"] for x in c["runs"])
                for c in it["choices"]]
    out = norm(" ".join(seq))
    sm = difflib.SequenceMatcher(None, src, out, autojunk=False)
    gaps = []
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= 12:
            gaps.append({"len": i2 - i1, "text": src[i1:i2][:120]})
    return {"src_chars": len(src), "out_chars": len(out), "gaps": gaps}


def qc_pdf(pdf_path, doc, col_split_pt=420.9):
    """PDF 기하 실측.

    핵심 게이트: **한 문항이 단/쪽 경계를 넘지 않는다.**
    문항의 첫 글자(번호 헤드)와 마지막 글자(마지막 선지 꼬리)가 같은 페이지·
    같은 단에 있어야 통과. 두 지점 사이의 모든 줄도 같은 단이어야 한다.
    """
    import fitz
    d = fitz.open(pdf_path)
    pages = len(d)
    empty = [i + 1 for i, pg in enumerate(d) if not pg.get_text().strip()]

    # (page, col, y, x, text) 로 본문 줄만 수집 — 러닝 헤더/푸터는 제외해야
    # 문항 구간에 섞여 들어가 가짜 '단 분할'로 잡히지 않는다 (실측 y: 헤더 36, 푸터 1161)
    lines = []
    for i, pg in enumerate(d):
        for b in pg.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"])
                y0, x0 = l["bbox"][1], l["bbox"][0]
                if t.strip() and 50 < y0 < 1140:
                    lines.append((i + 1, 0 if x0 < col_split_pt else 1, y0, x0, t))
    lines.sort(key=lambda r: (r[0], r[1], r[2]))

    flat = [(r[0], r[1], r[4]) for r in lines]
    # 정답 섹션은 문항 구간 판정에서 제외 (마지막 문항의 꼬리로 잡히지 않게)
    cut = next((k for k, (_p, _c, t) in enumerate(flat)
                if t.strip() == "정답"), len(flat))
    flat = flat[:cut]
    heads = {}
    splits = []
    for it in doc["items"]:
        n = it["n"]
        # 문항 시작: "N." 로 시작하는 줄 (번호는 문서에서 한 번만 헤드로 등장)
        hi = next((k for k, (_p, _c, t) in enumerate(flat)
                   if re.match(rf"^\s*{n}\.\s", t)), None)
        if hi is None:
            splits.append({"n": n, "why": "번호 헤드를 PDF에서 못 찾음"})
            continue
        # 문항 끝: 다음 문항 헤드 직전
        nj = next((k for k, (_p, _c, t) in enumerate(flat)
                   if k > hi and re.match(rf"^\s*{n + 1}\.\s", t)), len(flat))
        seg = flat[hi:nj]
        heads[n] = {"page": seg[0][0], "col": seg[0][1], "lines": len(seg)}
        zones = {(p, c) for p, c, _t in seg}
        if len(zones) > 1:
            splits.append({"n": n, "why": "단/쪽 분할",
                           "zones": sorted(zones)})
    d.close()
    return {"pages": pages, "empty_pages": empty,
            "heads_found": len(heads), "split_items": splits}


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
            report["qc_pdf"] = qc_pdf(pdf, doc)

    report["steps"]["total_s"] = round(time.time() - t0, 2)
    json.dump(report, open(os.path.join(a.out, "report.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "qc_pdf"},
                     ensure_ascii=False, indent=1)[:2500])
    if "qc_pdf" in report:
        q = report["qc_pdf"]
        print(f"pages={q['pages']} empty={q['empty_pages']} "
              f"heads_found={q['heads_found']} splits={len(q['split_items'])}")


if __name__ == "__main__":
    main()
