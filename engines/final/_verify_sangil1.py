"""상일1 파서 검증 하니스 — 저장된 extracted.json으로 parse_extracted만 재실행.
InDesign 불필요. 헤더 라벨링 회귀 검증용. (조사 후 삭제 예정)
"""
import os, sys, json, shutil, tempfile, unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engines.final.parser import parse_extracted

SRC_JOB = sys.argv[1] if len(sys.argv) > 1 else "jobs/1b36f0a8"
SRC_JOB = os.path.join("/Users/nhj/dev/yone-design-web", SRC_JOB)

def nfc(s): return unicodedata.normalize("NFC", s) if s else s

def run():
    tmp = tempfile.mkdtemp(prefix="verify_sangil1_")
    shutil.copy(os.path.join(SRC_JOB, "extracted.json"), os.path.join(tmp, "extracted.json"))
    # meta files
    for fn in ("school.txt", "grade.txt", "exam_period.txt"):
        p = os.path.join(SRC_JOB, fn)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(tmp, fn))
    logs = []
    def log(m): logs.append(str(m))
    content_path = parse_extracted(
        os.path.join(tmp, "extracted.json"),
        [], [],                      # vocab_left, vocab_right
        "상일1", "고1", "26-1-기말",
        tmp, log,
        grammar_word_lines=None,
        textbook_lessons=["3", "4"],
        allowed_olpo_lectures=set(),
        olpo_lecture_map=None,
    )
    data = json.load(open(content_path, encoding="utf-8"))

    def hdrs(lst):
        out = []
        for it in lst:
            if isinstance(it, dict):
                out.append(it.get("header"))
        return out

    print("=" * 70)
    print("VOL1 문장배열 헤더:")
    for h in hdrs(data["vol1"]["문장배열"]):
        print("   ", h)
    print(f"  [count={len(data['vol1']['문장배열'])}]")
    print("-" * 70)
    print("VOL1 문장삽입 헤더:")
    for h in hdrs(data["vol1"]["문장삽입"]):
        print("   ", h)
    print(f"  [count={len(data['vol1']['문장삽입'])}]")
    print("-" * 70)
    print("VOL2 영작_헤더_상세:")
    for it in data["vol2"].get("영작_헤더_상세", []):
        print("   ", it.get("header"))
    print("-" * 70)
    print("VOL2 어법_헤더:")
    for h in data["vol2"].get("어법_헤더", []):
        print("   ", h)
    print("=" * 70)
    # DL / 올포 / 지문 카운트 요약
    allh = hdrs(data["vol1"]["문장배열"]) + hdrs(data["vol1"]["문장삽입"])
    allh += [it.get("header") for it in data["vol2"].get("영작_헤더_상세", [])]
    allh += list(data["vol2"].get("어법_헤더", []))
    import collections
    kinds = collections.Counter()
    for h in allh:
        h = h or ""
        if h.startswith("지문 "): kinds["지문N(제네릭)"] += 1
        elif "딥러닝" in h or "Deep Learning" in h: kinds["딥러닝"] += 1
        elif h.startswith("올포"): kinds["올포"] += 1
        elif h.startswith("교과서"): kinds["교과서"] += 1
        else: kinds["기타"] += 1
    print("헤더 종류 요약:", dict(kinds))
    print("tmp:", tmp)

if __name__ == "__main__":
    run()
