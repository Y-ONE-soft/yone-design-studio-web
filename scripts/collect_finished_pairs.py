#!/usr/bin/env python3
"""완성 조판본 ↔ 원고 쌍 수집기 (역학습 파일럿 — W44).

"완성 조판본"은 조판 후 사람이 손마무리해 실제로 납품한 최종 .indd다.
그 파일과 대응 원고(또는 원고를 파싱한 content.json)를 짝지어, 뒤 단계
(core.reverse_learn.align)가 "원고 단락 → 실제 적용 스타일" 정답표를
만들 수 있게 한다.

쌍 소스
  A) jobs 이력  (~/dev/yone-design-web/jobs/<id>) — content.json(파싱된 원고)
     + .settings.json 의 indd_path(=조판/교재/... 최종 산출물, 이후 사람이
     같은 파일을 열어 손마무리). 가장 신뢰도 높은 소스.
  B) 교재 폴더 최종 .indd — A의 indd_path가 가리키는 실물. 존재/수정시각을
     확인해 사람 손질 여부(human_edited)를 표시한다.
  C) GDrive 교과서 작업 폴더 — 단원 폴더의 워크북 원고 폴더 ↔ 엔진 출력
     파일명 규칙({과목}_{출판사}_{단원}_전체(C).indd)으로 최종본을 찾는다.
     (원고 파싱이 아직 없는 쌍 — 후속 확장용으로 목록만 남긴다.)

GDrive는 읽기 전용으로만 접근한다 (여는 것도 복사도 하지 않고 os.stat만).
모든 os.walk/listdir는 숨김 dot-디렉터리를 가지치기한다 (2026-06-26 회고).

출력: data_corpus/reverse_learn/pairs.json
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DEFAULT = os.path.expanduser("~/dev/yone-design-web/jobs")
OUT_DEFAULT = os.path.join(REPO, "data_corpus", "reverse_learn", "pairs.json")


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _read_meta(job_dir, name, default=""):
    p = os.path.join(job_dir, name + ".txt")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return default


# ── 계열 추정 ────────────────────────────────────────────────────────────────
_SERIES_PATTERNS = [
    (re.compile(r"블랙북"), "블랙북"),
    (re.compile(r"화이트북|리테"), "화이트북"),
    (re.compile(r"세서특필|세서스"), "세서스페셜"),
    (re.compile(r"파이널"), "파이널"),
    (re.compile(r"포켓북"), "포켓북"),
    (re.compile(r"수능특강|리딩파워|EBS"), "EBS워크북"),
    (re.compile(r"워크북|전체\(C\)|짤지문"), "워크북"),
    (re.compile(r"모의고사|동형"), "동형모의고사"),
]


def guess_series(content, indd_name):
    wt = (content or {}).get("workbook_type") or ""
    if wt == "교과서":
        return "교과서워크북"
    if wt == "EBS":
        return "EBS워크북"
    if wt == "모의고사":
        return "워크북(모의고사)"
    name = _nfc(indd_name)
    for pat, label in _SERIES_PATTERNS:
        if pat.search(name):
            return label
    return "기타"


def collect_jobs(jobs_dir, out=None):
    """소스 A/B — jobs 이력 + 그 산출물 최종 .indd."""
    out = out if out is not None else []
    try:
        job_ids = sorted(d for d in os.listdir(jobs_dir)
                         if not d.startswith("."))
    except OSError:
        return out
    for jid in job_ids:
        jdir = os.path.join(jobs_dir, jid)
        sp = os.path.join(jdir, ".settings.json")
        cp = os.path.join(jdir, "content.json")
        if not (os.path.isfile(sp) and os.path.isfile(cp)):
            continue
        try:
            with open(sp, encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, ValueError):
            continue
        indd = settings.get("indd_path") or settings.get("output_path") or ""
        if not indd:
            continue
        exists = os.path.isfile(indd)
        try:
            content = json.load(open(cp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        steps = content.get("steps")
        plan_ready = isinstance(steps, dict) and bool(steps)
        c_m = os.path.getmtime(cp)
        i_m = os.path.getmtime(indd) if exists else 0.0
        delta_h = round((i_m - c_m) / 3600.0, 2) if exists else None
        # 신뢰도: 산출물이 존재하고 job 이후에 쓰였는가 (음수 = 다른 job의
        # 산출물이 같은 경로에 먼저 있던 것 → 이 원고의 완성본이 아니다)
        if not exists:
            conf, reason = 0.0, "indd_missing"
        elif delta_h is not None and delta_h < -0.05:
            conf, reason = 0.2, "indd_older_than_job"
        elif not plan_ready:
            conf, reason = 0.4, "no_steps(플랜 불가 계열)"
        elif delta_h is not None and delta_h > 0.5:
            conf, reason = 1.0, "human_edited_after_job"
        else:
            conf, reason = 0.85, "engine_output_intact"
        out.append({
            "source": "jobs",
            "job_id": jid,
            "job_dir": jdir,
            "content_json": cp,
            "manuscript_folder": _read_meta(jdir, "manuscript_folder"),
            "indd_path": indd,
            "indd_exists": exists,
            "indd_mtime_delta_h": delta_h,
            "plan_ready": plan_ready,
            "series": guess_series(content, os.path.basename(indd)),
            "school": settings.get("school") or _read_meta(jdir, "school"),
            "subject": content.get("subject") or "",
            "publisher": content.get("publisher") or "",
            "lesson": content.get("lesson") or "",
            "workbook_type": content.get("workbook_type") or "",
            "human_edited": bool(delta_h is not None and delta_h > 0.5),
            "confidence": conf,
            "confidence_reason": reason,
            "has_dump": os.path.isfile(os.path.join(jdir, "typeset_dump.json")),
        })
    return out


# ── 소스 C: GDrive 교과서 단원 폴더 ─────────────────────────────────────────

def _walk_dirs(base, max_depth=3):
    """dot-디렉터리 가지치기 재귀 (GDrive 읽기 전용 — listdir만)."""
    base_depth = base.rstrip("/").count("/")
    for root, dirs, _files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if root.rstrip("/").count("/") - base_depth >= max_depth:
            dirs[:] = []
        yield root, dirs


def collect_textbook_gdrive(out=None, limit=None):
    """소스 C — 교과서 단원 폴더(원고) ↔ 워크북 출력 폴더의 최종 .indd."""
    out = out if out is not None else []
    try:
        from engines.textbook_workbook.engine import _load_config
        cfg = _load_config()
    except Exception:                                          # noqa: BLE001
        return out
    base = cfg.get("textbook_base") or ""
    outdir = cfg.get("indd_output_dir") or ""
    if not (base and os.path.isdir(base)):
        return out
    finals = []
    if os.path.isdir(outdir):
        finals = [_nfc(n) for n in os.listdir(outdir)
                  if n.lower().endswith(".indd") and not n.startswith(".")]
    excludes = set(cfg.get("exclude_folders") or [])
    lesson_re = re.compile(r'(\d+(?:\s*,\s*\d+)*과|SL\d+|Project\s*\d+)')
    n = 0
    for subj in sorted(os.listdir(base)):
        if subj.startswith(".") or _nfc(subj) in excludes:
            continue
        sdir = os.path.join(base, subj)
        if not os.path.isdir(sdir):
            continue
        for pub in sorted(os.listdir(sdir)):
            if pub.startswith("."):
                continue
            pdir = os.path.join(sdir, pub)
            if not os.path.isdir(pdir):
                continue
            for les in sorted(os.listdir(pdir)):
                if les.startswith("."):
                    continue
                ldir = os.path.join(pdir, les)
                if not os.path.isdir(ldir):
                    continue
                m = lesson_re.search(_nfc(les))
                if not m:
                    continue
                wb = None
                for sub in os.listdir(ldir):
                    if sub.startswith("."):
                        continue
                    if "워크북" in _nfc(sub) and os.path.isdir(
                            os.path.join(ldir, sub)):
                        wb = os.path.join(ldir, sub)
                        break
                if not wb:
                    continue
                pub_nfc = _nfc(pub)
                subj_nfc = _nfc(subj)
                pub_short = pub_nfc[len(subj_nfc):].strip() \
                    if pub_nfc.startswith(subj_nfc) else pub_nfc
                prefix = f"{subj_nfc}_{pub_short}_{m.group(1)}_전체(C)"
                cands = [f for f in finals if f.startswith(prefix)]
                if not cands:
                    continue
                # 가장 최근 수정본 = 손마무리 최종본
                cands.sort(key=lambda f: os.path.getmtime(
                    os.path.join(outdir, f)), reverse=True)
                out.append({
                    "source": "gdrive_textbook",
                    "job_id": None,
                    "job_dir": None,
                    "content_json": None,
                    "manuscript_folder": wb,
                    "indd_path": os.path.join(outdir, cands[0]),
                    "indd_exists": True,
                    "indd_mtime_delta_h": None,
                    "plan_ready": False,
                    "series": "교과서워크북",
                    "school": "",
                    "subject": subj_nfc,
                    "publisher": pub_nfc,
                    "lesson": m.group(1),
                    "workbook_type": "교과서",
                    "human_edited": None,
                    "confidence": 0.6,
                    "confidence_reason": "filename_rule(원고 미파싱)",
                    "has_dump": False,
                    "indd_candidates": cands,
                })
                n += 1
                if limit and n >= limit:
                    return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs-dir", default=JOBS_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--skip-gdrive", action="store_true")
    args = ap.parse_args()

    pairs = collect_jobs(args.jobs_dir)
    if not args.skip_gdrive:
        collect_textbook_gdrive(pairs)

    # 같은 완성본을 가리키는 job이 여럿이면 신뢰도/최신 job 우선 (dedupe)
    best = {}
    for p in pairs:
        k = p["indd_path"]
        cur = best.get(k)
        if cur is None or (p["confidence"], p.get("job_id") or "") > \
                (cur["confidence"], cur.get("job_id") or ""):
            best[k] = p
    deduped = sorted(best.values(),
                     key=lambda p: (-p["confidence"], p["indd_path"]))

    series = {}
    for p in deduped:
        series[p["series"]] = series.get(p["series"], 0) + 1
    summary = {
        "collected": len(pairs),
        "deduped": len(deduped),
        "usable(conf>=0.85, plan_ready)": sum(
            1 for p in deduped if p["confidence"] >= 0.85 and p["plan_ready"]),
        "human_edited": sum(1 for p in deduped if p.get("human_edited")),
        "by_series": dict(sorted(series.items(), key=lambda kv: -kv[1])),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "pairs": deduped}, f,
                  ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("→", args.out)


if __name__ == "__main__":
    main()
