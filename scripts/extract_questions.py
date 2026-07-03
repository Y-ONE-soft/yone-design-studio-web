"""
광범위 발문 추출 + 1차 유형 정규화.

대상: 2025/2026 내신대비 폴더 내 모든 hwp/hwpx/docx
출력: /tmp/manuscripts_questions.jsonl  (한 라인 = 한 발문)
"""
import os, re, sys, json, zipfile, shutil, subprocess, unicodedata, hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE = "/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_corpus", "manuscripts_questions.jsonl")
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_corpus", "extract.log")

CATEGORY_KEYWORDS = {
    "동형모의고사": ["동형"],
    "세미모의고사": ["세미", "한세모", "명세모"],
    "4스텝모의고사": ["4스텝"],
    "배N제": ["배N제"],
    "어법총정리": ["어법총정리"],
    "기적의특강": ["기적의 특강"],
    "직전보충": ["직전보충"],
    "워크북": ["워크북"],
    "문제모음": ["문제 모음", "문제모음"],
    "포켓북": ["포켓북"],
    "분석본": ["분석본"],
    "교과서": ["교과서"],
    "올림포스": ["올림포스"],
    "플로우노트": ["플로우노트"],
    "적중내역": ["적중내역"],
    "리테": ["리테"],
    "특강": ["특강"],
    "모의고사_기타": ["모의고사"],
}

def normalize_path(p):
    return unicodedata.normalize("NFC", p)

def category_of(path):
    nfc = normalize_path(path)
    parts = nfc.split("/")
    for cat, kws in CATEGORY_KEYWORDS.items():
        for part in parts:
            for kw in kws:
                if kw in part:
                    return cat
    return None

def extract_hwpx(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            sections = []
            for n in names:
                if "section" in n.lower() and n.endswith(".xml"):
                    xml = z.read(n).decode("utf-8", "replace")
                    sections.append(xml)
            if not sections:
                return ""
            text_chunks = []
            for xml in sections:
                # 문단 단위로 추출
                for para in re.findall(r"<hp:p[^>]*>(.*?)</hp:p>", xml, re.DOTALL):
                    txts = re.findall(r"<hp:t[^>]*>([^<]*)</hp:t>", para)
                    text_chunks.append("".join(txts))
            return "\n".join(text_chunks)
    except Exception as e:
        return f"__ERR__:hwpx:{e}"

def extract_hwp(path):
    local = f"/tmp/_hwp_{hashlib.md5(path.encode()).hexdigest()[:8]}.hwp"
    try:
        shutil.copy2(path, local)
        r = subprocess.run(["hwp5txt", local], capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    except Exception as e:
        return f"__ERR__:hwp:{e}"
    finally:
        try: os.remove(local)
        except: pass

def extract_docx(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
            paras = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.DOTALL)
            lines = []
            for p in paras:
                txts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)
                lines.append("".join(txts))
            return "\n".join(lines)
    except Exception as e:
        return f"__ERR__:docx:{e}"

# 발문 인식 룰: 한국 영어 시험 발문 패턴
QUESTION_KEYWORDS = re.compile(
    r"(다음 (?:글|문장|글의|중)|밑줄 친|글의 (?:흐름|문맥상|제목|주제|요지|내용|순서|빈칸|밑줄|목적|분위기|심경|어조|어휘|어법|괄호|밑줄)|"
    r"윗글|위 글|위의 글|아래 (?:글|문장)|주어진 (?:글|문장|단어)|"
    r"서술형\s*\d|객관식|어휘\s*추론|어법상|문맥상|글의 흐름|"
    r"적절한 것은|적절하지 않은 것은|있는 대로 고른|"
    r"가장 알맞은|쓰시오\s*\.?$|작성하시오|완성하시오|고치시오|"
    r"빈칸\s*\([A-Z]\)|빈칸\s*\[[A-Z]\]|빈칸에 들어갈)"
)

# 길이 제한: 발문은 보통 한 줄 80~250자
def looks_like_question(line):
    s = line.strip()
    if len(s) < 12 or len(s) > 400:
        return False
    if not QUESTION_KEYWORDS.search(s):
        return False
    # 단순 본문(평서문) 제외: 발문은 보통 ?, 시오, 것은 등으로 끝남
    if not re.search(r"(\?|것은|것을|것\?|시오\.?|것\?|기에 가장 적절한 곳은|쓰시오\.?|것끼리)", s[-30:]):
        return False
    return True

def process_file(path):
    nfc_path = normalize_path(path)
    rel = nfc_path[len(BASE)+1:] if nfc_path.startswith(BASE) else nfc_path
    parts = rel.split("/")
    year = parts[0] if len(parts) > 0 else ""
    grade = parts[1] if len(parts) > 1 else ""
    school = parts[2] if len(parts) > 2 else ""
    exam = parts[3] if len(parts) > 3 else ""
    category = category_of(nfc_path)

    ext = path.lower().rsplit(".", 1)[-1]
    if ext == "hwpx":
        text = extract_hwpx(path)
    elif ext == "hwp":
        text = extract_hwp(path)
    elif ext == "docx":
        text = extract_docx(path)
    else:
        return []
    if text.startswith("__ERR__"):
        return [{"error": text, "path": rel}]
    out = []
    for line in text.split("\n"):
        if looks_like_question(line):
            out.append({
                "q": line.strip(),
                "year": year,
                "grade": grade,
                "school": school,
                "exam": exam,
                "category": category,
                "path": rel,
                "ext": ext,
            })
    return out

def walk_files():
    skip_dirs = {".DS_Store", "최종X", "이전버전", "구버전", "백업"}
    for year in ["2025년", "2026년"]:
        yp = os.path.join(BASE, year)
        if not os.path.isdir(yp):
            continue
        for dirpath, dirs, files in os.walk(yp):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for f in files:
                if f.startswith("~$") or f.startswith("."):
                    continue
                fp = os.path.join(dirpath, f)
                ext = f.lower().rsplit(".", 1)[-1]
                if ext in ("hwp", "hwpx", "docx"):
                    yield fp

def main():
    files = list(walk_files())
    print(f"총 파일 수: {len(files)}")
    written = 0
    errors = 0
    with open(OUT, "w") as fout, open(LOG, "w") as flog:
        # 병렬 처리 (8 workers)
        with ProcessPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(process_file, fp): fp for fp in files}
            done = 0
            for fut in as_completed(futs):
                done += 1
                if done % 100 == 0:
                    print(f"  진행: {done}/{len(files)}")
                try:
                    res = fut.result()
                    for item in res:
                        if "error" in item:
                            flog.write(f"ERR {item['path']}: {item['error']}\n")
                            errors += 1
                        else:
                            fout.write(json.dumps(item, ensure_ascii=False) + "\n")
                            written += 1
                except Exception as e:
                    flog.write(f"FATAL {futs[fut]}: {e}\n")
                    errors += 1
    print(f"완료. 발문 {written}건, 에러 {errors}건. OUT={OUT}")

if __name__ == "__main__":
    main()
