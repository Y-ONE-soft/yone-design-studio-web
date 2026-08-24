# -*- coding: utf-8 -*-
"""마더텅 N강 워크북 — 강 번호 하나로 끝내는 전 파이프라인.

    강 번호 → 엑셀에서 코드 조달 → 코드별 세로 완성본 유무 판정
      → 있는 것: 세로결합 / 없는 것: 원고로 세로 조판 → 세로중간본
      → 가로 변환 + 후처리(정리·재스레드·지문번호)
      → 세로↔가로 전문 대조 → 손실 0 아니면 실패로 중단

부품(엔진)은 전부 있었지만 묶는 곳이 없어서, 2026-08-24 13강은 임시
스크립트 10여 개를 손으로 이어 붙여 돌렸다. 그 절차를 그대로 코드로 옮긴
것이 이 파일이다. 각 단계는 state.json 에 기록되고 **완료된 단계는 건너뛴다**
— 한 단계가 20~40분씩 걸리므로 중간에 죽어도 이어서 갈 수 있어야 한다.

사용:
    # 먼저 계획만 본다 (InDesign 무접촉, 30초)
    python3 scripts/mt_pipeline.py --gang 13 --school 한영1 \
        --exam-period 26-2-중간 --plan-only

    # 전 과정 실행 (16문항씩 분권, 워크북02부터)
    python3 scripts/mt_pipeline.py --gang 13 --school 한영1 \
        --exam-period 26-2-중간 --split 16 --workbook-start 2

    # 죽은 지점부터 이어서
    python3 scripts/mt_pipeline.py --run mt13_a1b2c3

⚠ 실행 중 InDesign 을 건드리지 말 것. 파이썬을 죽여도 InDesign 안의 JSX 는
   계속 돈다 — CPU 가 내려간 뒤에 재개할 것(2026-08-20 실측: -2741 syntax
   error 로 다음 조판이 죽는다).
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
import unicodedata
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import config                                                # noqa: E402
from core.indesign.runner import run_jsx                     # noqa: E402
from engines.workbook_select import motherteng as _mt        # noqa: E402
from engines.workbook_select.engine import WorkbookSelectEngine  # noqa: E402
from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine  # noqa: E402
from engines.workbook_sero.engine import WorkbookSeroEngine  # noqa: E402
from engines.vert_to_horiz.engine import VertToHorizEngine   # noqa: E402

STAGES = ["codes", "survey", "sero_new", "sero_merge", "v2h", "verify"]
_MS_EXTS = (".docx", ".hwp", ".hwpx")


def _nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


# ── 로그 ────────────────────────────────────────────────────────────

class Log(object):
    def __init__(self, path):
        self.t0 = time.time()
        self.path = path
        self.fh = open(path, "a", encoding="utf-8")

    def __call__(self, msg):
        line = "[%7.1fs] %s" % (time.time() - self.t0, msg)
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()

    def head(self, title):
        self("")
        self("=" * 68)
        self("  " + title)
        self("=" * 68)


# ── state ───────────────────────────────────────────────────────────

def _state_path(run_dir):
    return os.path.join(run_dir, "state.json")


def _save(st, run_dir):
    with open(_state_path(run_dir), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def _load(run_dir):
    with open(_state_path(run_dir), encoding="utf-8") as f:
        return json.load(f)


def _job(prefix, meta):
    """엔진용 job 폴더 생성 — 메타는 {key}.txt 로 떨어뜨린다(엔진 계약)."""
    jd = os.path.join(config.JOBS_DIR, "%s_%s" % (prefix, uuid.uuid4().hex[:6]))
    os.makedirs(os.path.join(jd, "uploads"), exist_ok=True)
    for k, v in meta.items():
        with open(os.path.join(jd, "%s.txt" % k), "w", encoding="utf-8") as f:
            f.write(str(v))
    return jd


# ── 1) 코드 조달 ────────────────────────────────────────────────────

def stage_codes(st, log):
    cfg_path = os.path.join(_ROOT, "engines", "workbook_select", "config.json")
    with open(cfg_path, encoding="utf-8") as f:
        xlsx = os.path.expanduser(json.load(f).get("motherteng_xlsx", ""))
    if not os.path.exists(xlsx):
        raise RuntimeError("지문 출처 엑셀 없음: %s" % xlsx)
    log("[엑셀] %s" % os.path.basename(xlsx))

    if st.get("codes_input"):
        codes = [c.strip() for c in re.split(r"[,\s]+", st["codes_input"]) if c.strip()]
        numbers = dict((c, i + 1) for i, c in enumerate(codes))
        log("[코드] 직접 지정 %d개" % len(codes))
    else:
        codes, numbers, col = _mt.codes_for_gang(xlsx, st["gang"], log=log)
        if not codes:
            raise RuntimeError("엑셀에서 %s강을 찾지 못했습니다: %s"
                               % (st["gang"], xlsx))
    st["codes"] = [{"code": c, "no": numbers.get(c)} for c in codes]
    log("[코드] %d개 — %s" % (len(codes), ", ".join(codes)))

    # vert_to_horiz 는 별도 JSON(madertung_sources.json)으로 가로↔세로 지문
    # 순서를 맞춘다. 강이 등록돼 있지 않으면 변환 자체가 "엑셀에 강 데이터가
    # 없습니다" 로 죽으므로, **엑셀을 정본으로** 여기서 동기화한다.
    _sync_v2h_sources(st["gang"], codes, log)
    return st


def _sync_v2h_sources(gang, codes, log):
    p = os.path.join(_ROOT, "engines", "vert_to_horiz", "madertung_sources.json")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    key = "%02d" % int(gang)
    old = data.get(key)
    if old == codes:
        log("[출처JSON] %s강 %d개 — 엑셀과 일치" % (key, len(codes)))
        return
    if old is None:
        log("[출처JSON] %s강 신규 등록 (%d개)" % (key, len(codes)))
    else:
        log("[출처JSON] %s강 갱신: %d개 → %d개 (엑셀 기준)"
            % (key, len(old), len(codes)))
        bak = p + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
        with open(bak, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log("[출처JSON] 백업: %s" % os.path.basename(bak))
    data[key] = codes
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 2) 세로 완성본 유무 판정 ────────────────────────────────────────

def stage_survey(st, log):
    codes = [c["code"] for c in st["codes"]]
    eng = MockexamSeroMergeEngine()
    rows = eng.probe_sources("\n".join(codes), st["grade"], log=log)
    have, missing = {}, []
    for r in rows:
        if r["path"]:
            have[r["code"]] = r["path"]
        else:
            missing.append(r)
    st["survey"] = {
        "have": have,
        "missing": [{"code": r["code"], "year": r["year"],
                     "month": r["month"], "qNum": r["qNum"],
                     "display": r["display"]} for r in missing],
    }
    log("")
    log("[판정] 세로 완성본 있음 %d개 / 없음 %d개 (전체 %d)"
        % (len(have), len(missing), len(rows)))
    for r in missing:
        log("   신규 조판 필요: %s (%s)" % (r["display"], r["code"]))
    return st


# ── 3) 없는 것: 원고로 세로 조판 ────────────────────────────────────

def _manuscripts_in(folder):
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            n = _nfc(f)
            if n.lower().endswith(_MS_EXTS) and not n.startswith("~"):
                out.append(os.path.join(root, f))
    out.sort()
    return out


def sero_new_plan(st, log):
    """신규 세로 조판 계획 — [(원고폴더, year, month, [코드…], 라벨)].

    조판을 시작하기 전에 이것만 따로 볼 수 있어야 한다(--plan-only). 원고
    폴더를 못 찾는 건 실행 40분 뒤가 아니라 착수 전에 알아야 하는 사실이다.
    회차 폴더가 있으면 그 회차 원고로, 없는 옛 기출은 마더텅 N강 보충 폴더로
    몰아 한 번에 조판한다(그 폴더에 옛 기출 원고가 모여 있다).
    """
    missing = st["survey"]["missing"]
    if not missing:
        return []
    grade_num = st["grade"].replace("고", "")
    ws_cfg_path = os.path.join(_ROOT, "engines", "workbook_select", "config.json")
    with open(ws_cfg_path, encoding="utf-8") as f:
        ms_base = os.path.expanduser(json.load(f)["manuscript_base"])

    # 회차(년,월)별로 묶는다 — 한 번 조판하면 그 회차 문항이 다 들어간다
    groups = {}
    for m in missing:
        groups.setdefault((m["year"], m["month"]), []).append(m["code"])

    plan = []
    orphan = []     # 회차 폴더가 없는 옛 기출 — 마더텅 N강 보충 폴더로
    for (yy, mm), codes in sorted(groups.items()):
        d, err = WorkbookSelectEngine._find_manuscript_dir(
            ms_base, grade_num, int(yy), int(mm))
        if d:
            plan.append((d, int(yy), int(mm), codes,
                         "%s년 %s월" % (yy, int(mm))))
        else:
            log("[신규조판] %s년 %s월 회차 폴더 없음 (%s) — 보충 원고로 넘김"
                % (yy, int(mm), err))
            orphan.extend(codes)

    if orphan:
        dirs, err = WorkbookSelectEngine._find_gang_manuscript_dirs(
            ms_base, grade_num, st["gang"])
        if not dirs:
            raise RuntimeError(
                "보충 원고 폴더를 찾지 못했습니다 (%s강): %s\n대상 코드: %s"
                % (st["gang"], err, ", ".join(orphan)))
        plan.append((dirs[0], 0, 0, orphan, "%s강 보충" % st["gang"]))
    return plan


def stage_sero_new(st, log, run_dir):
    st.setdefault("sero_new", {"jobs": [], "by_code": {}})
    plan = sero_new_plan(st, log)
    if not plan:
        log("[신규조판] 없음 — 전 코드가 세로 완성본을 가지고 있다")
        return st
    grade_num = st["grade"].replace("고", "")

    done_jobs = dict((j["label"], j) for j in st["sero_new"]["jobs"])
    for folder, yy, mm, codes, label in plan:
        prev = done_jobs.get(label)
        if prev and os.path.exists(prev.get("indd", "")):
            log("[신규조판] %s — 완료본 재사용: %s"
                % (label, os.path.basename(prev["indd"])))
            continue
        files = _manuscripts_in(folder)
        if not files:
            raise RuntimeError("원고가 없습니다: %s" % folder)
        log("")
        log("[신규조판] %s — 원고 %d개, 대상 코드 %s"
            % (label, len(files), ", ".join(codes)))
        log("           %s" % folder)

        jd = _job("mtsero", {
            "grade": st["grade"], "school": st["school"],
            "exam_period": st["exam_period"], "year": yy, "month": mm,
            "workbook_type": "모의고사",
            "result_name": "고%s_%s_세로" % (grade_num, label.replace(" ", "")),
        })
        eng = WorkbookSeroEngine()
        jp = eng.parse({"manuscripts": files}, jd, log)
        jsx = eng.prepare_jsx(jp, jd, log)
        stt = json.load(open(os.path.join(jd, ".settings.json"), encoding="utf-8"))
        run_jsx(jsx, log, poll_log_path=os.path.join(jd, "조판_로그.txt"),
                timeout=getattr(eng, "jsx_timeout", 1800))
        try:
            eng.verify(jd, log)
        except Exception as e:                               # noqa: BLE001
            log("[신규조판] 검수 예외(계속): %s" % e)

        indd = stt["indd_path"]
        if not os.path.exists(indd):
            raise RuntimeError("세로 조판 결과가 없습니다: %s" % indd)

        # 이 파일이 실제로 어떤 코드를 담았는지 — 원고 파서가 뽑은 사이클의
        # code 가 정본이다. 요청한 코드가 빠졌으면 조용히 넘기지 않는다.
        meta = json.load(open(os.path.join(jd, "content_meta.json"),
                              encoding="utf-8"))
        got = set(c.get("code") for c in meta.get("cycle_files", []))
        lack = [c for c in codes if c not in got]
        if lack:
            raise RuntimeError(
                "신규 세로 조판이 코드를 담지 못했습니다: %s\n"
                "  원고 폴더: %s\n  조판된 코드: %s"
                % (", ".join(lack), folder, ", ".join(sorted(x for x in got if x))))
        log("[신규조판] 완료: %s (코드 %s)"
            % (os.path.basename(indd), ", ".join(sorted(got))))

        st["sero_new"]["jobs"].append(
            {"label": label, "job": jd, "indd": indd, "codes": codes})
        for c in codes:
            st["sero_new"]["by_code"][c] = indd
        _save(st, run_dir)
    # 재사용분도 매핑에 반영
    for j in st["sero_new"]["jobs"]:
        for c in j["codes"]:
            st["sero_new"]["by_code"][c] = j["indd"]
    return st


# ── 권 나누기 ───────────────────────────────────────────────────────

def _volumes(st):
    codes = [c["code"] for c in st["codes"]]
    nos = dict((c["code"], c["no"]) for c in st["codes"])
    split = int(st.get("split") or 0)
    chunks = ([codes[i:i + split] for i in range(0, len(codes), split)]
              if split > 0 else [codes])
    out = []
    for i, ch in enumerate(chunks):
        wb = int(st.get("workbook_start", 2)) + i
        if len(chunks) > 1:
            tag = "마더텅%s강_%s~%s" % (st["gang"], nos[ch[0]], nos[ch[-1]])
        else:
            tag = "마더텅%s강" % st["gang"]
        base = "%s_워크북%02d(%s)" % (st["school"], wb, tag)
        out.append({
            "idx": i, "codes": ch,
            "sero_name": base + "_세로중간본",
            "horiz_name": base + "_내지",
        })
    return out


# ── 4) 세로결합 → 세로중간본 ────────────────────────────────────────

def stage_sero_merge(st, log, run_dir):
    st.setdefault("volumes", _volumes(st))
    override = st.get("sero_new", {}).get("by_code", {})
    for vol in st["volumes"]:
        if vol.get("sero_indd") and os.path.exists(vol["sero_indd"]):
            log("[세로결합] %s — 완료본 재사용" % vol["sero_name"])
            continue
        log.head("세로결합: %s (%d문항)" % (vol["sero_name"], len(vol["codes"])))
        jd = _job("mtmerge", {
            "grade": st["grade"], "school": st["school"],
            "exam_period": st["exam_period"], "result_name": vol["sero_name"],
        })
        eng = MockexamSeroMergeEngine()
        sub = dict((c, p) for c, p in override.items() if c in vol["codes"])
        if sub:
            log("[세로결합] 신규 조판본 사용 %d코드" % len(sub))
        jp = eng.parse({"codes": "\n".join(vol["codes"]),
                        "source_override": sub}, jd, log)
        jsx = eng.prepare_jsx(jp, jd, log)
        stt = json.load(open(os.path.join(jd, ".settings.json"), encoding="utf-8"))
        run_jsx(jsx, log, poll_log_path=stt["log_paths"][0],
                timeout=getattr(eng, "jsx_timeout", 1800),
                completion_marker=getattr(eng, "completion_marker", None))
        res = eng.verify(jd, log)
        if res.get("warnings"):
            log("[세로결합] 경고: %s" % "; ".join(res["warnings"]))
        out = stt["output_indd"]
        if not os.path.exists(out):
            raise RuntimeError("세로중간본이 생성되지 않았습니다: %s" % out)
        vol["sero_job"] = jd
        vol["sero_indd"] = out
        log("[세로결합] 완료: %s" % out)
        _save(st, run_dir)
    return st


# ── 5) 가로 변환 + 후처리 ───────────────────────────────────────────

def stage_v2h(st, log, run_dir):
    for vol in st["volumes"]:
        if vol.get("horiz_indd") and os.path.exists(vol["horiz_indd"]):
            log("[가로변환] %s — 완료본 재사용" % vol["horiz_name"])
            continue
        log.head("가로변환: %s" % vol["horiz_name"])
        jd = _job("mtv2h", {
            "grade": st["grade"], "school": st["school"],
            "exam_period": st["exam_period"],
        })
        eng = VertToHorizEngine()
        jp = eng.parse({"verti_indd": vol["sero_indd"],
                        "gang_code": str(st["gang"]),
                        "result_name": vol["horiz_name"]}, jd, log)
        eng.prepare_jsx(jp, jd, log)
        # run_indesign 이 본 변환 + 후처리 3종(정리·재스레드·지문번호)을 순서대로
        eng.run_indesign(jd, log)
        try:
            eng.verify(jd, log)
        except Exception as e:                               # noqa: BLE001
            log("[가로변환] 검수 예외(계속): %s" % e)
        stt = json.load(open(os.path.join(jd, ".settings.json"), encoding="utf-8"))
        out = stt["output_indd"]
        if not os.path.exists(out):
            raise RuntimeError("가로 결과물이 생성되지 않았습니다: %s" % out)
        vol["v2h_job"] = jd
        vol["horiz_indd"] = out
        log("[가로변환] 완료: %s" % out)
        _save(st, run_dir)
    return st


# ── 6) 세로↔가로 전문 대조 ──────────────────────────────────────────

def _repair(vol, log, run_dir):
    """유실 페이지 복구 — 세로 페이지를 가로에 페이지째 다시 넣는다.

    최후 수단이다(repage_recover.jsx 헤더 참조). 넣은 페이지는 세로판
    레이아웃 그대로이므로 눈으로 확인해야 한다. --repair 일 때만 돈다.
    """
    src = os.path.join(_ROOT, "engines", "vert_to_horiz", "jsx",
                       "repage_recover.jsx")
    jlog = os.path.join(run_dir, "repair_%d.log" % vol["idx"])
    dst = os.path.join(run_dir, "repair_%d.jsx" % vol["idx"])
    code = (open(src, encoding="utf-8").read()
            .replace("__LOG__", jlog)
            .replace("__VERTI__", vol["sero_indd"])
            .replace("__HORIZ__", vol["horiz_indd"])
            .replace("__DRY__", "false"))
    with open(dst, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        os.remove(jlog)
    except OSError:
        pass
    log("[복구] 시작 — 세로 페이지를 가로에 페이지째 삽입한다")
    run_jsx(dst, log, poll_log_path=jlog, timeout=1800,
            completion_marker="===== 페이지 복구 완료 =====")
    if os.path.exists(jlog):
        for line in open(jlog, encoding="utf-8", errors="ignore"):
            log("   " + line.rstrip())


def stage_verify(st, log, run_dir):
    from scripts.v2h_content_diff import compare
    failed = []
    for vol in st["volumes"]:
        log.head("대조검수: %s" % vol["horiz_name"])
        total, missing = compare(vol["sero_indd"], vol["horiz_indd"], log=log)
        log("[대조] 세로 문단 %d개 중 가로에서 못 찾음 %d개" % (total, len(missing)))
        for page, t in missing[:40]:
            log("   세로 p%-4s %s" % (page, t[:80]))
        if len(missing) > 40:
            log("   … 외 %d개" % (len(missing) - 40))

        if missing and st.get("repair"):
            _repair(vol, log, run_dir)
            log("[대조] 복구 후 재대조")
            total, missing = compare(vol["sero_indd"], vol["horiz_indd"],
                                     log=log)
            log("[대조] 재대조 결과 — 유실 %d개" % len(missing))
            for page, t in missing[:40]:
                log("   세로 p%-4s %s" % (page, t[:80]))
            vol["repaired"] = True
            if not missing:
                log("[복구] 손실 0 도달 — ⚠ 교체된 페이지는 세로판 레이아웃"
                    "이다. 납품 전 반드시 눈으로 확인할 것")

        vol["verify"] = {"total": total, "missing": len(missing)}
        if missing:
            failed.append(vol["horiz_name"])
        _save(st, run_dir)
    if failed:
        raise RuntimeError(
            "세로↔가로 대조 실패 — 내용 유실이 있습니다: %s\n"
            "가로 결과물을 납품하지 말 것. 위 유실 목록을 먼저 해결해야 한다."
            % ", ".join(failed))
    log("[대조] 전 권 손실 0 — 통과")
    return st


# ── 리포트 ──────────────────────────────────────────────────────────

def report(st, log):
    log.head("계획")
    nos = dict((c["code"], c["no"]) for c in st["codes"])
    have = st.get("survey", {}).get("have", {})
    miss = [m["code"] for m in st.get("survey", {}).get("missing", [])]
    log("강 %s / %s / %s / %s" % (st["gang"], st["grade"], st["school"],
                                  st["exam_period"]))
    log("문항 %d개 — 세로 완성본 있음 %d, 신규 조판 %d"
        % (len(st["codes"]), len(have), len(miss)))
    for vol in _volumes(st):
        rng = "%s~%s" % (nos[vol["codes"][0]], nos[vol["codes"][-1]])
        n_new = len([c for c in vol["codes"] if c in miss])
        log("  · %s — %d문항(마더텅 %s), 신규조판 %d"
            % (vol["horiz_name"], len(vol["codes"]), rng, n_new))
    if miss:
        log("")
        log("신규 조판 (%d코드) — 원고 폴더 확인:" % len(miss))
        for folder, yy, mm, codes, label in sero_new_plan(st, log):
            n = len(_manuscripts_in(folder))
            log("  · %s ← %s" % (", ".join(codes), label))
            log("      원고 %d개  %s" % (n, folder))
            if not n:
                log("      ⚠ 원고가 없습니다 — 이대로면 이 단계에서 중단된다")


# ── main ────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gang", help="마더텅 강 번호 (예: 13)")
    ap.add_argument("--grade", default="고1")
    ap.add_argument("--school", default="")
    ap.add_argument("--exam-period", default="")
    ap.add_argument("--split", type=int, default=16,
                    help="권당 문항 수 (0=분권 없음, 기본 16)")
    ap.add_argument("--workbook-start", type=int, default=2,
                    help="워크북 번호 시작 (기본 2 → 워크북02)")
    ap.add_argument("--codes", default="",
                    help="엑셀 대신 코드 직접 지정 (디버그용)")
    ap.add_argument("--run", default="", help="기존 run 이어서 (run 폴더명)")
    ap.add_argument("--from", dest="from_stage", default="",
                    choices=[""] + STAGES, help="이 단계부터 강제 재실행")
    ap.add_argument("--repair", action="store_true",
                    help="대조에서 유실이 나오면 세로 페이지를 페이지째 넣어 "
                         "복구 시도 (최후 수단 — 그 페이지는 세로판 레이아웃이 "
                         "되므로 눈으로 확인 필요)")
    ap.add_argument("--plan-only", action="store_true",
                    help="코드 조달·세로 유무 판정까지만 (InDesign 무접촉)")
    args = ap.parse_args()

    if args.run:
        run_dir = os.path.join(config.JOBS_DIR, args.run)
        if not os.path.exists(_state_path(run_dir)):
            ap.error("state.json 없음: %s" % run_dir)
        st = _load(run_dir)
        if args.repair:
            st["repair"] = True
    else:
        if not args.gang:
            ap.error("--gang 또는 --run 이 필요합니다")
        if not args.school or not args.exam_period:
            ap.error("--school 과 --exam-period 는 필수입니다 "
                     "(출력 폴더 경로에 들어갑니다)")
        run_dir = os.path.join(
            config.JOBS_DIR, "mt%s_%s" % (args.gang, uuid.uuid4().hex[:6]))
        os.makedirs(run_dir, exist_ok=True)
        st = {
            "gang": int(args.gang), "grade": args.grade,
            "school": args.school, "exam_period": args.exam_period,
            "split": args.split, "workbook_start": args.workbook_start,
            "codes_input": args.codes, "done": [],
            "repair": args.repair, "run_dir": run_dir,
        }
        _save(st, run_dir)

    log = Log(os.path.join(run_dir, "pipeline.log"))
    log.head("마더텅 %s강 워크북 파이프라인 — run %s"
             % (st["gang"], os.path.basename(run_dir)))
    log("run 폴더: %s" % run_dir)

    if args.from_stage:
        i = STAGES.index(args.from_stage)
        st["done"] = [s for s in st.get("done", []) if STAGES.index(s) < i]
        for vol in st.get("volumes", []):
            if i <= STAGES.index("sero_merge"):
                vol.pop("sero_indd", None)
            if i <= STAGES.index("v2h"):
                vol.pop("horiz_indd", None)
        log("[재실행] %s 단계부터" % args.from_stage)

    todo = STAGES[:2] if args.plan_only else STAGES
    fns = {
        "codes": lambda: stage_codes(st, log),
        "survey": lambda: stage_survey(st, log),
        "sero_new": lambda: stage_sero_new(st, log, run_dir),
        "sero_merge": lambda: stage_sero_merge(st, log, run_dir),
        "v2h": lambda: stage_v2h(st, log, run_dir),
        "verify": lambda: stage_verify(st, log, run_dir),
    }
    try:
        for s in todo:
            if s in st.get("done", []):
                log("[단계] %s — 완료됨, 건너뜀" % s)
                continue
            log.head("단계 %d/%d: %s" % (STAGES.index(s) + 1, len(STAGES), s))
            fns[s]()
            st.setdefault("done", []).append(s)
            _save(st, run_dir)
    except Exception as e:                                   # noqa: BLE001
        log("")
        log("!!! 중단: %s" % e)
        log(traceback.format_exc())
        log("이어서 하려면: python3 scripts/mt_pipeline.py --run %s"
            % os.path.basename(run_dir))
        return 1

    if args.plan_only:
        report(st, log)
        log("")
        log("계획만 실행했습니다. 전 과정 실행:")
        log("  python3 scripts/mt_pipeline.py --run %s"
            % os.path.basename(run_dir))
        return 0

    log.head("완료")
    for vol in st["volumes"]:
        log("· %s" % vol["horiz_name"])
        log("    세로중간본: %s" % vol["sero_indd"])
        log("    가로 결과물: %s" % vol["horiz_indd"])
        log("    대조: 세로 문단 %d개 / 유실 %d개%s"
            % (vol["verify"]["total"], vol["verify"]["missing"],
               "  (페이지 복구 수행 — 눈으로 확인 필요)"
               if vol.get("repaired") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
