"""범용 파서 검증 하니스 — 임의 job_dir의 extracted.json으로 parse_extracted 재실행.
회귀 검증용: 같은 코드/입력이면 같은 출력. 수정 전후 diff 비교.
사용: python3 engines/final/_verify_job.py <job_dir> [out_label]
(조사 후 삭제 예정)
"""
import os, sys, json, shutil, tempfile, unicodedata, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engines.final.parser import parse_extracted

JOB = os.path.join("/Users/nhj/dev/yone-design-web", sys.argv[1])

def nfc(s): return unicodedata.normalize("NFC", s) if s else s

def meta(name, default=""):
    p = os.path.join(JOB, f"{name}.txt")
    return nfc(open(p, encoding="utf-8").read().strip()) if os.path.exists(p) else default

def run():
    school = meta("school"); grade = meta("grade", "고1"); period = meta("exam_period")
    cfg = json.load(open("/Users/nhj/dev/yone-design-web/engines/final/config.json"))
    info = (cfg.get("school_textbook_map", {}) or {}).get(period, {}).get(school, {})
    tb_lessons = [re.sub(r"과$", "", l).strip() for l in (info.get("lessons", []) or [])]

    tmp = tempfile.mkdtemp(prefix="vjob_")
    shutil.copy(os.path.join(JOB, "extracted.json"), os.path.join(tmp, "extracted.json"))
    for fn in ("school.txt", "grade.txt", "exam_period.txt"):
        if os.path.exists(os.path.join(JOB, fn)):
            shutil.copy(os.path.join(JOB, fn), os.path.join(tmp, fn))
    logs = []
    cp = parse_extracted(os.path.join(tmp, "extracted.json"), [], [],
                         school, grade, period, tmp, lambda m: logs.append(str(m)),
                         textbook_lessons=tb_lessons, allowed_olpo_lectures=set(),
                         olpo_lecture_map=None)
    data = json.load(open(cp, encoding="utf-8"))
    lines = [f"# {school} {grade} {period} tb={tb_lessons}"]
    for vol in ("vol1", "vol2"):
        for sec, lst in (data.get(vol, {}) or {}).items():
            if not isinstance(lst, list):
                continue
            hs = [it.get("header") for it in lst if isinstance(it, dict) and it.get("header") is not None]
            if hs:
                lines.append(f"[{vol}.{sec}] n={len(lst)}")
                for h in hs:
                    lines.append(f"   {h}")
    print("\n".join(lines))

if __name__ == "__main__":
    run()
