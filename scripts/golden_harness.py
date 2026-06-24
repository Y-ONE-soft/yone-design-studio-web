#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""골든 아웃풋 회귀 하네스 (final 엔진 parse_extracted 특성화 테스트).

목적: parse_extracted 의 순수 변환(extracted.json + 동결된 시트/어법 데이터 -> content.json)을
hermetic 하게 동결/비교한다. 파서 코드를 고쳤을 때 기존 학교 결과가 바뀌는지 자동 감지.

설계 원칙 (project_root_causes.md #1):
  - production 코드 0줄 수정 (이 파일과 golden_baselines/ 만 추가).
  - capture 는 1회 온라인(Sheets/GDrive). check/accept 는 완전 오프라인 + 결정적.
  - characterization 모드: DIFF 가 떠도 자동 차단(exit!=0) 하지 않는다. 사람이 diff 를 보고 판단.
  - baseline 은 "현행 동작 기록"일 뿐 정답 보증이 아니다 (RC3 silent 폴백으로 현재 산출물에
    틀렸지만 안 들킨 것이 섞여 있을 수 있음 = baseline 오염 주의).

hermetic 보장: parse_extracted 내부 외부호출 2개를 호출순서 기반 카세트로 record/replay.
  - vocab_fetcher.fetch_scope_for_school  (시험범위 시트)
  - mothertongue_grammar_loader.load_mothertongue_grammar_map  (마더텅 어법 Word)
  + 모듈전역 _MT_MAP / _MT_SECTION_LABELS (load_mothertongue_map 이 설정) 동결.

사용:
  python3 scripts/golden_harness.py capture <job_id> [<job_id> ...]
  python3 scripts/golden_harness.py list
  python3 scripts/golden_harness.py check [<label> ...]      # 인자 없으면 전체
  python3 scripts/golden_harness.py accept <label> [...]     # 의도된 변경 수락(golden 갱신)
  python3 scripts/golden_harness.py selftest <job_id>        # capture 후 즉시 check (자기일관성)

job_id 는 jobs/ 아래 final 엔진 job (extracted.json + school/grade/exam_period.txt 보유).
"""
import os
import sys

# 결정성 보장: set/dict 순회 순서를 고정해 capture/check 간 hash-seed 비결정성을 제거한다.
# (마더텅 dedup 등 일부 parse_extracted 경로가 set 순회에 의존 → seed 미고정 시 같은 입력도
#  프로세스마다 블록수가 달라져 golden 이 흔들림. 한영1 70↔71 블록 사례.)
# PYTHONHASHSEED 는 인터프리터 시작 전에 설정돼야 효력이 있으므로, 미설정이면 재실행한다.
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import json
import time
import pickle
import shutil
import tempfile
import inspect
import difflib

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, ROOT)

# .env 수동 로드 (python-dotenv 비의존, _local_final_run.py 와 동일 패턴)
_envp = os.path.join(ROOT, ".env")
if os.path.exists(_envp):
    for _l in open(_envp, encoding="utf-8"):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import config  # noqa: E402
from engines.final import parser as P  # noqa: E402
from engines.final import vocab_fetcher as VF  # noqa: E402
from engines.final import mothertongue_grammar_loader as MGL  # noqa: E402
from engines.final.engine import FinalEngine  # noqa: E402

BASELINES = os.path.join(BASE, "golden_baselines")


def _silent(_m):
    pass


def _logprint(m):
    print(time.strftime("%H:%M:%S "), m, flush=True)


def _norm(content_obj, strip_tokens):
    """content.json -> 결정적 정규화 문자열. 휘발성 경로 토큰을 placeholder 로 치환."""
    s = json.dumps(content_obj, ensure_ascii=False, sort_keys=True, indent=1)
    for t in strip_tokens:
        if t:
            s = s.replace(t, "<JOBDIR>")
    return s


def _all_labels():
    if not os.path.isdir(BASELINES):
        return []
    return sorted(
        d for d in os.listdir(BASELINES)
        if os.path.isfile(os.path.join(BASELINES, d, "golden.json"))
    )


def capture(job_ids):
    os.makedirs(BASELINES, exist_ok=True)
    for jid in job_ids:
        src = os.path.join(config.JOBS_DIR, jid)
        ex = os.path.join(src, "extracted.json")
        if not os.path.isfile(ex):
            print(f"[skip] {jid}: extracted.json 없음")
            continue
        try:
            school = open(os.path.join(src, "school.txt"), encoding="utf-8").read().strip()
            grade = open(os.path.join(src, "grade.txt"), encoding="utf-8").read().strip()
            exam = open(os.path.join(src, "exam_period.txt"), encoding="utf-8").read().strip()
        except FileNotFoundError as e:
            print(f"[skip] {jid}: 파라미터 파일 없음 ({e})")
            continue

        tmp = tempfile.mkdtemp(prefix="golden_cap_")
        os.makedirs(os.path.join(tmp, "uploads"), exist_ok=True)
        shutil.copy(ex, os.path.join(tmp, "extracted.json"))
        for fn, val in (("school.txt", school), ("grade.txt", grade), ("exam_period.txt", exam)):
            open(os.path.join(tmp, fn), "w", encoding="utf-8").write(val)

        holder = {"in_parse": False, "fetch_scope": [], "mt_grammar": []}
        real_pe, real_fs, real_mg = (
            P.parse_extracted, VF.fetch_scope_for_school, MGL.load_mothertongue_grammar_map)
        pe_sig = inspect.signature(real_pe)

        def pe_wrap(*a, **k):
            b = pe_sig.bind(*a, **k)
            b.apply_defaults()
            kw = dict(b.arguments)
            kw.pop("log", None)
            holder["kwargs"] = kw
            holder["mt_map"] = P.get_mothertongue_map()
            holder["mt_labels"] = P.get_mothertongue_section_labels()
            holder["in_parse"] = True
            try:
                result = real_pe(*a, **k)
                # parse_extracted 가 막 쓴 content.json (engine.parse 의 6.5 중요어휘 폴백 등
                # 후처리 전) = replay(parse_extracted 직접호출)와 동일 범위. 이걸 golden 으로.
                with open(result, encoding="utf-8") as _cf:
                    holder["golden_content"] = json.load(_cf)
                return result
            finally:
                holder["in_parse"] = False

        def fs_wrap(*a, **k):
            r = real_fs(*a, **k)
            if holder["in_parse"]:
                holder["fetch_scope"].append(r)
            return r

        def mg_wrap(*a, **k):
            r = real_mg(*a, **k)
            if holder["in_parse"]:
                holder["mt_grammar"].append(r)
            return r

        P.parse_extracted, VF.fetch_scope_for_school, MGL.load_mothertongue_grammar_map = (
            pe_wrap, fs_wrap, mg_wrap)
        os.environ["_REUSE_EXTRACTED"] = "1"
        ok = True
        try:
            FinalEngine().parse({}, tmp, _logprint)
        except Exception as e:
            ok = False
            import traceback
            print(f"[FAIL] {jid}: capture 중 예외: {e}")
            traceback.print_exc()
        finally:
            P.parse_extracted, VF.fetch_scope_for_school, MGL.load_mothertongue_grammar_map = (
                real_pe, real_fs, real_mg)
            os.environ.pop("_REUSE_EXTRACTED", None)

        if not ok or "kwargs" not in holder or "golden_content" not in holder:
            print(f"[FAIL] {jid}: parse_extracted 미실행 또는 content.json 미생성")
            shutil.rmtree(tmp, ignore_errors=True)
            continue

        out = os.path.join(BASELINES, jid)
        os.makedirs(out, exist_ok=True)
        payload = {
            "kwargs": holder["kwargs"],
            "mt_map": holder["mt_map"],
            "mt_labels": holder["mt_labels"],
            "fetch_scope": holder["fetch_scope"],
            "mt_grammar": holder["mt_grammar"],
        }
        with open(os.path.join(out, "inputs.pkl"), "wb") as f:
            pickle.dump(payload, f)
        shutil.copy(ex, os.path.join(out, "extracted.json"))
        with open(os.path.join(out, "golden.json"), "w", encoding="utf-8") as f:
            f.write(_norm(holder["golden_content"], [tmp]))
        json.dump(
            {"school": school, "grade": grade, "exam_period": exam, "source_job": jid,
             "fetch_scope_calls": len(holder["fetch_scope"]),
             "mt_grammar_calls": len(holder["mt_grammar"])},
            open(os.path.join(out, "meta.json"), "w", encoding="utf-8"),
            ensure_ascii=False, indent=2)
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[ok] baseline 저장: {jid}  ({school}/{grade}/{exam})  "
              f"scope호출={len(holder['fetch_scope'])} mt어법={len(holder['mt_grammar'])}")


def _replay(label):
    """동결된 입력으로 parse_extracted 직접 호출 -> 정규화된 content.json 문자열."""
    out = os.path.join(BASELINES, label)
    with open(os.path.join(out, "inputs.pkl"), "rb") as f:
        payload = pickle.load(f)
    P._MT_MAP = payload.get("mt_map")
    P._MT_SECTION_LABELS = payload.get("mt_labels")
    P._MT_REVERSE = None  # lazy 재빌드
    fs_q = list(payload.get("fetch_scope", []))
    mg_q = list(payload.get("mt_grammar", []))
    real_fs, real_mg = VF.fetch_scope_for_school, MGL.load_mothertongue_grammar_map

    def fs_replay(*a, **k):
        return fs_q.pop(0) if fs_q else None

    def mg_replay(*a, **k):
        return mg_q.pop(0) if mg_q else {}

    tmp = tempfile.mkdtemp(prefix="golden_chk_")
    os.makedirs(os.path.join(tmp, "uploads"), exist_ok=True)
    shutil.copy(os.path.join(out, "extracted.json"), os.path.join(tmp, "extracted.json"))
    kw = dict(payload["kwargs"])
    kw["extracted_path"] = os.path.join(tmp, "extracted.json")
    kw["job_dir"] = tmp
    kw["log"] = _silent
    VF.fetch_scope_for_school, MGL.load_mothertongue_grammar_map = fs_replay, mg_replay
    try:
        cpath = P.parse_extracted(**kw)
        cj = json.load(open(cpath, encoding="utf-8"))
        return _norm(cj, [tmp])
    finally:
        VF.fetch_scope_for_school, MGL.load_mothertongue_grammar_map = real_fs, real_mg
        shutil.rmtree(tmp, ignore_errors=True)


def check(labels):
    labels = labels or _all_labels()
    if not labels:
        print("baseline 없음. 먼저 `capture <job_id>`.")
        return
    n_pass = n_diff = 0
    for label in labels:
        try:
            cur = _replay(label)
        except Exception as e:
            import traceback
            print(f"[ERROR] {label}: 재현 중 예외: {e}")
            traceback.print_exc()
            continue
        golden = open(os.path.join(BASELINES, label, "golden.json"), encoding="utf-8").read()
        if cur == golden:
            print(f"[PASS] {label}")
            n_pass += 1
        else:
            n_diff += 1
            diff = list(difflib.unified_diff(
                golden.splitlines(), cur.splitlines(),
                fromfile="golden", tofile="current", lineterm=""))
            add = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
            rem = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
            print(f"[DIFF] {label}: +{add} -{rem} 줄")
            for d in diff[:40]:
                print("    " + d)
            if len(diff) > 40:
                print(f"    ... (총 {len(diff)}줄 diff, 이하 생략)")
    print(f"\n=== 요약: PASS {n_pass} / DIFF {n_diff} / 총 {n_pass + n_diff} ===")
    print("(characterization: DIFF 는 정보용. 의도된 변경이면 `accept <label>`)")


def accept(labels):
    if not labels:
        print("accept 할 label 을 지정하세요.")
        return
    for label in labels:
        cur = _replay(label)
        with open(os.path.join(BASELINES, label, "golden.json"), "w", encoding="utf-8") as f:
            f.write(cur)
        print(f"[accepted] {label}: golden 갱신")


def list_baselines():
    labs = _all_labels()
    if not labs:
        print("baseline 없음. `capture <job_id>` 로 생성.")
        return
    print(f"baseline {len(labs)}개:")
    for label in labs:
        try:
            m = json.load(open(os.path.join(BASELINES, label, "meta.json"), encoding="utf-8"))
            print(f"  {label:26s} {m.get('school', '?')}/{m.get('grade', '?')}/"
                  f"{m.get('exam_period', '?')}  scope={m.get('fetch_scope_calls', '?')} "
                  f"mt어법={m.get('mt_grammar_calls', '?')}")
        except Exception:
            print(f"  {label}")


def selftest(job_ids):
    """capture 후 즉시 check. 같은 코드이므로 반드시 전부 PASS 여야 함(자기일관성)."""
    capture(job_ids)
    print("\n--- 자기일관성 검사 (capture 직후 check, 전부 PASS 여야 정상) ---")
    check([j for j in job_ids if os.path.isdir(os.path.join(BASELINES, j))])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "capture":
        capture(rest)
    elif cmd == "check":
        check(rest)
    elif cmd == "accept":
        accept(rest)
    elif cmd == "list":
        list_baselines()
    elif cmd == "selftest":
        selftest(rest)
    else:
        print(f"알 수 없는 명령: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
