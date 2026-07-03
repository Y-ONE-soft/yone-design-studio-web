#!/usr/bin/env python3
"""jobs/ 이력에서 골든 코퍼스를 선별해 tests/corpus/ 에 고정한다. (Phase 0)

사용:
    python3 scripts/build_corpus.py [--jobs-dir PATH] [--per-engine N] [--dry-run]

동작:
    jobs/<id>/ 중 (a) content.json 존재, (b) uploads/ 에 슬롯 접두사 원본 존재,
    (c) 엔진을 확신 있게 식별 가능한 것만 후보로 삼아, 엔진당 N건(다양성 우선)을
    tests/corpus/<engine>/<job_id>/ 로 복사한다:

        inputs/    업로드 원본 (uploads/ 루트의 "<slot>_*" 파일만 — 파서가 만든
                   무접두사 사본·Step3/ 파생물은 제외. .gitignore의 uploads/ 패턴을
                   피하기 위해 이름을 inputs로 바꾼다)
        meta/      job 루트의 *.txt 메타 (조판_로그.txt 등 출력 로그 제외)
        golden/    content.json (현행 파서 출력 = 스냅샷 기준)
        manifest.json

주의: 골든은 "정답"이 아니라 "현행 출력"이다. 의도된 개선으로 달라질 때는
tests/README.md 의 골든 승격 절차를 따라 diff 검토 후 갱신 커밋한다.
"""
import argparse
import json
import os
import shutil
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "tests", "corpus")

# 출력/파생물 — meta 복사에서 제외
_META_EXCLUDE = {"조판_로그.txt"}

# 엔진별 파일 슬롯 키 (upload_spec 기준. 새 엔진 추가 시 여기와 _classify에 등록)
ENGINE_SLOTS = {
    "workbook": ["manuscripts"],
    "workbook_sero": ["manuscripts"],
    "mockexam": ["manuscripts"],
    "blackbook": ["manuscript", "answers"],
    "seseospecial": ["part1", "part2", "answers"],
}

# 코퍼스 보류 엔진 (parse가 업로드 아닌 외부 소스에 의존 — 오프라인 재실행 불가):
#   final / textbook_workbook / ebs_workbook: GDrive 원고 폴더에서 직접 복사
#   pocketbook: 분석본 .indd 폴더 스캔
#   baenje: content.json 미생성 (RTF 산출 — 별도 스냅샷 방식 필요)


def _classify(settings: dict, content: dict) -> str | None:
    """settings/content 시그니처로 엔진을 식별. 확신 없으면 None."""
    keys = set(settings.keys())
    if keys == {"json_path", "indd_path", "output_dir", "grade", "year",
                "month", "exclude"} and "steps" in content:
        return "workbook"
    if "meta_path" in keys and "workbook_type" in keys:
        return "workbook_sero"
    jobs = settings.get("jobs")
    if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) \
            and "round" in jobs[0] and "data" in jobs[0]:
        return "mockexam"
    if keys == {"indd_path", "issue_num", "json_path", "output_dir"} \
            and "sections" in content:
        return "blackbook"
    if "school_key" in keys and "part1" in content and "part2" in content:
        return "seseospecial"
    return None


def _diversity_key(job_dir: str) -> tuple:
    """(school, grade, year, month) — 같은 조합은 1건만 우선 선별."""
    vals = []
    for name in ("school", "grade", "year", "month"):
        p = os.path.join(job_dir, f"{name}.txt")
        try:
            vals.append(open(p, encoding="utf-8").read().strip())
        except OSError:
            vals.append("")
    return tuple(vals)


def _input_files(job_dir: str, slots: list) -> list:
    """uploads/ 루트에서 슬롯 접두사가 붙은 원본만 수집 (파생물 제외)."""
    up = os.path.join(job_dir, "uploads")
    if not os.path.isdir(up):
        return []
    out = []
    for name in sorted(os.listdir(up)):
        full = os.path.join(up, name)
        if not os.path.isfile(full):
            continue
        if any(name.startswith(f"{slot}_") for slot in slots):
            out.append(full)
    return out


def scan(jobs_dir: str):
    """후보 job 목록: [(engine, job_id, job_dir, input_files, diversity_key)]"""
    cands = []
    for job_id in sorted(os.listdir(jobs_dir)):
        job_dir = os.path.join(jobs_dir, job_id)
        if not os.path.isdir(job_dir) or job_id == "uploads":
            continue
        settings_p = os.path.join(job_dir, ".settings.json")
        content_p = os.path.join(job_dir, "content.json")
        if not (os.path.isfile(settings_p) and os.path.isfile(content_p)):
            continue
        try:
            settings = json.load(open(settings_p, encoding="utf-8"))
            content = json.load(open(content_p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        engine = _classify(settings, content)
        if engine is None:
            continue
        inputs = _input_files(job_dir, ENGINE_SLOTS[engine])
        if not inputs:
            continue
        cands.append((engine, job_id, job_dir, inputs, _diversity_key(job_dir)))
    return cands


def select(cands, per_engine: int):
    """엔진별로 다양성(메타 조합 중복 배제) 우선 N건."""
    picked = []
    by_engine = {}
    for c in cands:
        by_engine.setdefault(c[0], []).append(c)
    for engine, group in sorted(by_engine.items()):
        seen_keys = set()
        chosen = []
        for c in group:                      # 1차: 메타 조합이 새로운 것
            if c[4] not in seen_keys:
                seen_keys.add(c[4])
                chosen.append(c)
            if len(chosen) >= per_engine:
                break
        for c in group:                      # 2차: 모자라면 중복 조합도 허용
            if len(chosen) >= per_engine:
                break
            if c not in chosen:
                chosen.append(c)
        picked.extend(chosen)
    return picked


def copy_case(engine, job_id, job_dir, inputs, dry: bool):
    dst = os.path.join(CORPUS, engine, job_id)
    if os.path.isdir(dst):
        print(f"  = {engine}/{job_id} (이미 존재 — 스킵)")
        return False
    print(f"  + {engine}/{job_id}  inputs={len(inputs)}")
    if dry:
        return True
    os.makedirs(os.path.join(dst, "inputs"))
    os.makedirs(os.path.join(dst, "meta"))
    os.makedirs(os.path.join(dst, "golden"))
    for f in inputs:
        shutil.copy2(f, os.path.join(dst, "inputs", os.path.basename(f)))
    for name in sorted(os.listdir(job_dir)):
        if name.endswith(".txt") \
                and unicodedata.normalize("NFC", name) not in _META_EXCLUDE:
            shutil.copy2(os.path.join(job_dir, name),
                         os.path.join(dst, "meta", name))
    shutil.copy2(os.path.join(job_dir, "content.json"),
                 os.path.join(dst, "golden", "content.json"))
    manifest = {
        "engine": engine,
        "source_job": job_id,
        "note": "golden = 선별 당시 현행 파서 출력 (정답 아님 — tests/README.md 참조)",
    }
    with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs-dir",
                    default=os.path.expanduser("~/dev/yone-design-web/jobs"))
    ap.add_argument("--per-engine", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cands = scan(args.jobs_dir)
    counts = {}
    for c in cands:
        counts[c[0]] = counts.get(c[0], 0) + 1
    print(f"후보: {len(cands)}건 {counts}")

    picked = select(cands, args.per_engine)
    n = 0
    for engine, job_id, job_dir, inputs, _ in picked:
        if copy_case(engine, job_id, job_dir, inputs, args.dry_run):
            n += 1
    print(f"{'(dry-run) ' if args.dry_run else ''}코퍼스 반영: {n}건 → {CORPUS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
