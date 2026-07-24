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
import scoring            # noqa: E402


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
    d.close()

    lines = _collect(pdf_path, col_split_pt)
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
    return {"pages": pages, "empty_pages": empty,
            "heads_found": len(heads), "split_items": splits}


COL_BOTTOM = 1134.3     # 페이지 1191pt - 아래여백 20mm


def _collect(pdf_path, col_split_pt=420.9):
    """PDF -> 본문 줄 목록 [(page, col, y0, y1, text)] (헤더/푸터 제외)"""
    import fitz
    d = fitz.open(pdf_path)
    lines = []
    for i, pg in enumerate(d):
        for b in pg.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"])
                x0, y0, _x1, y1 = l["bbox"]
                if t.strip() and 50 < y0 < 1140:
                    lines.append((i + 1, 0 if x0 < col_split_pt else 1, y0, y1, t))
    d.close()
    # 표지 머리표는 두 단에 걸쳐 있어(column-span:all) 오른쪽 셀이 우단 줄로
    # 잡힌다. 그러면 1번 문항 구간이 좌/우단에 걸친 것처럼 보여 가짜 '분할'이
    # 난다 -> 1쪽에서 첫 문항 머리 위쪽 줄은 전부 버린다.
    first = min((y0 for pg, _c, y0, _y1, t in lines
                 if pg == 1 and re.match(r"^\s*1\.\s", t)), default=None)
    if first is not None:
        lines = [r for r in lines if not (r[0] == 1 and r[2] < first - 1)]
    lines.sort(key=lambda r: (r[0], r[1], r[2]))
    return lines


def _zones(pdf_path, doc):
    """{(page, col): [(문항번호, top_y, bottom_y), ...]} — 정답 섹션 제외."""
    lines = _collect(pdf_path)
    cut = next((k for k, r in enumerate(lines) if r[4].strip() == "정답"), len(lines))
    lines = lines[:cut]
    order = [it["n"] for it in doc["items"]]
    idx = {}
    for k, r in enumerate(lines):
        for n in order:
            if n not in idx and re.match(rf"^\s*{n}\.\s", r[4]):
                idx[n] = k
    zones = {}
    for pos, n in enumerate(order):
        if n not in idx:
            continue
        a = idx[n]
        b = min((idx[m] for m in order[pos + 1:] if m in idx), default=len(lines))
        seg = lines[a:b]
        if seg:
            zones.setdefault((seg[0][0], seg[0][1]), []).append(
                (n, seg[0][2], max(r[3] for r in seg)))
    for z in zones:
        zones[z].sort(key=lambda t: t[1])
    return zones


def row_align_deltas(pdf_path, doc):
    """좌/우 단의 k번째 문항이 같은 높이에서 시작하도록 필요한 추가 여백(mm).

    같은 페이지 좌단 k번째와 우단 k번째 중 아래에서 시작하는 쪽에 맞춰,
    위에 있는 쪽의 (k-1)번째 문항 뒤 여백을 늘린다. k=0 은 단 머리라 이미 맞다.
    반환: {문항번호: 추가 mm}, 최대 어긋남(pt)
    """
    zones = _zones(pdf_path, doc)
    pages = {p for p, _c in zones}
    add, worst = {}, 0.0
    for p in pages:
        c0, c1 = zones.get((p, 0), []), zones.get((p, 1), [])
        for k in range(1, min(len(c0), len(c1))):
            target = max(c0[k][1], c1[k][1])
            for col in (c0, c1):
                d = target - col[k][1]
                if d > 0.5:
                    worst = max(worst, d)
                    prev = col[k - 1][0]
                    add[prev] = add.get(prev, 0) + d / 72 * 25.4
    return add, worst


def column_fill(pdf_path, doc, safety=0.94, cap_mm=22.0):
    """단 하단에 죽는 여백을 그 단 안 문항 사이로 재분배.

    다단 흘림에서는 세로 균등정렬(vertical justification)이 CSS 에 없다.
    그래서 1패스로 조판해 단별 잔여 높이를 실측하고, 그 단에 든 문항 사이
    간격에 나눠 얹는 2패스를 돈다. 마지막 문항 뒤 간격은 눈에 안 보이므로
    (k-1)개 간격에만 배분하면 단이 정확히 채워진다.

    반환: {문항번호: 추가 padding mm}
    """
    lines = _collect(pdf_path)
    cut = next((k for k, r in enumerate(lines) if r[4].strip() == "정답"), len(lines))
    lines = lines[:cut]

    # 문항 -> 그 문항이 속한 (page, col) 및 마지막 줄 bottom
    zones = {}
    order = [it["n"] for it in doc["items"]]
    idx = {}
    for k, r in enumerate(lines):
        for n in order:
            if n not in idx and re.match(rf"^\s*{n}\.\s", r[4]):
                idx[n] = k
    for pos, n in enumerate(order):
        if n not in idx:
            continue
        a = idx[n]
        b = min((idx[m] for m in order[pos + 1:] if m in idx), default=len(lines))
        seg = lines[a:b]
        if not seg:
            continue
        zones.setdefault((seg[0][0], seg[0][1]), []).append((n, max(r[3] for r in seg)))

    last_zone = max(zones) if zones else None
    out = {}
    for z, qs in zones.items():
        if z == last_zone or len(qs) < 2:
            continue                       # 흐름 마지막 단은 자연스러운 여백 유지
        leftover = COL_BOTTOM - max(y for _n, y in qs)
        if leftover <= 4:
            continue
        # 간격 추가에는 상한을 둔다. 잔여를 전부 한두 개 간격에 몰아넣으면
        # 문항 사이가 텅 비어 오히려 더 나빠 보인다 (단 하단 여백이 자연스럽다).
        add_mm = min(leftover * safety / (len(qs) - 1) / 72 * 25.4, cap_mm)
        if add_mm < 1:
            continue
        for n, _y in sorted(qs)[:-1]:
            out[n] = round(add_mm, 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manuscript")
    ap.add_argument("answers", nargs="?")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()

    cfg = {
        "title": "세서특필 모의고사",
        "subtitle": "2026학년도 여름방학",
        "period": "제 1 교시",
        "total_score": 100,
        "subject_code": "08",
        "exam_date": "(   )월 (   )일 ( 1 )교시",
        "target": "( 1 )학년",
        "teachers": "",
        "subjective_count": 0,
        "subjective_score": 0,
        "copyright": "이 시험 문제의 저작권은 Y.ONE STUDIO 에 있습니다. "
                     "저작권법에 의해 보호받는 저작물이므로 무단 전재와 복제는 "
                     "금지되며, 이를 어길 시 저작권법에 의거 처벌될 수 있습니다.",
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

    # 배점 분배 (합 = 총점 보장). 원고의 원 [3점]은 난이도 보조 신호로만 쓴다.
    report["scoring"] = scoring.assign(doc["items"], cfg.get("total_score", 100))

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
        def emit(pads):
            extra = "".join(f"#q{n}{{padding-bottom:calc(8mm + {v:.2f}mm)}}"
                            for n, v in sorted(pads.items()) if v > 0.05)
            open(hp, "w", encoding="utf-8").write(
                html.replace("</head>", f"<style>{extra}</style></head>")
                if extra else html)
            return subprocess.run(cmd, capture_output=True, text=True)

        r = emit({})
        if r.returncode != 0:
            report["pdf_error"] = (r.stdout + r.stderr)[-3000:]
        else:
            # 좌/우 단의 같은 순번 문항이 같은 높이에서 시작하도록 반복 정렬한다.
            # 여백을 늘리면 흐름이 바뀌므로 매 회 재조판 후 실측하고, 페이지 수가
            # 늘거나 문항이 쪼개지면 직전 상태로 되돌린다(퇴행 금지).
            base = qc_pdf(pdf, doc)
            best, best_q = {}, base
            pads = {}
            hist = []
            for _ in range(4):
                add, worst = row_align_deltas(pdf, doc)
                hist.append(round(worst, 1))
                if worst < 2.0 or not add:
                    break
                cand = dict(pads)
                for n, v in add.items():
                    cand[n] = cand.get(n, 0) + v
                if emit(cand).returncode != 0:
                    emit(best)
                    break
                q2 = qc_pdf(pdf, doc)
                if q2["pages"] > base["pages"] or q2["split_items"]:
                    emit(best)          # 퇴행 -> 마지막 정상 상태 복원
                    break
                pads, best, best_q = cand, cand, q2
            else:
                pass
            report["row_align"] = {"adjusted": len(best),
                                   "worst_misalign_pt": hist}
            report["steps"]["pdf_s"] = round(time.time() - t1, 2)
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
