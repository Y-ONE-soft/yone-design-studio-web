"""조판 파이프라인 실행 (백그라운드 스레드) — app.py에서 분리 (C2-9). 의미론 무변경.

app.py:_run_pipeline → run_pipeline. 호출부는 routes/typeset.py의 /api/run.
"""
import json
import os
import shutil

import config
import core.job_manager as jm
from core.indesign import runner as indesign


def _classify_failure(msg):
    """실패 메시지를 유형으로 분류 — 향후 유형별 집계용."""
    if not msg:
        return "unknown"
    if ("스크립트 전달 실패" in msg) or ("스크립트 시작 안 됨" in msg):
        return "startup_delivery"          # 1단계 자동 재시도 대상
    if ("미갱신" in msg) or ("행(hang)" in msg) or ("응답 없음" in msg):
        return "hang_timeout"
    if ("Errno 11" in msg) or ("Resource deadlock" in msg) or ("EDEADLK" in msg):
        return "file_lock_edeadlk"
    if ("[오류]" in msg) or ("스토리" in msg) or ("찾을 수 없" in msg):
        return "jsx_data_error"
    low = msg.lower()
    if ("폰트" in msg) or ("링크" in msg) or ("font" in low) or ("link" in low):
        return "font_link_missing"
    return "other"


def _persist_failure(job_id, job_dir, engine, stage, err_msg, tb):
    """실패 이력을 디스크에 영속화 — 유형별 집계 + 1단계 커버리지 측정용.

    jm.fail 은 in-memory 스트림이라 재부팅 시 소실된다. 여기서
    job_dir/failure.json(개별, traceback 포함) + 중앙 JSONL(전체 집계)로 남긴다.
    이 함수는 절대 예외를 밖으로 던지지 않는다(실패 경로를 깨지 않기 위해).
    """
    import time as _t
    material_id = getattr(engine, "material_id", "") or ""
    rec = {
        "ts": _t.strftime("%Y-%m-%d %H:%M:%S"),
        "job_id": job_id,
        "material_id": material_id,
        "stage": stage,
        "error": (err_msg or "")[:500],
        "category": _classify_failure(err_msg or ""),
    }
    try:
        with open(os.path.join(job_dir, "failure.json"), "w", encoding="utf-8") as f:
            json.dump({**rec, "traceback": (tb or "")[-4000:]}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        cpath = os.path.expanduser("~/Library/Logs/yonestudio-failures.jsonl")
        with open(cpath, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def run_pipeline(engine, job_id: str, job_dir: str, uploaded: dict):
    log = lambda m: jm.put_log(job_id, m)
    skip_id = getattr(engine, "skip_indesign", False)
    total = "2" if skip_id else "3"
    stage = "init"   # 실패 시 어느 단계에서 났는지 기록용
    try:
        # ── 1단계: 파싱 ──────────────────────────────────────────────
        stage = "parse"
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log(f"[1/{total}] 원고 파싱 중...")
        json_path = engine.parse(uploaded, job_dir, log)
        log(f"[1/{total}] 파싱 완료 ✓")

        if jm.is_cancelled(job_id):
            return

        # ── 2단계: InDesign 조판 (skip_indesign이면 건너뛰기) ────────
        if not skip_id:
            stage = "indesign"
            log("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            log("[2/3] InDesign 조판 중...")
            jsx_path = engine.prepare_jsx(json_path, job_dir, log)
            # 엔진에 전용 InDesign 실행기가 있으면 사용
            if hasattr(engine, 'run_indesign'):
                engine.run_indesign(job_dir, log)
            else:
                log_filename = getattr(engine, "log_filename", "조판_로그.txt")
                # settings.json의 output_dir에서 로그 경로 결정 (/tmp일 수 있음)
                _settings_path = os.path.join(job_dir, ".settings.json")
                if os.path.exists(_settings_path):
                    with open(_settings_path) as _sf:
                        _sdata = json.load(_sf)
                    log_file = os.path.join(_sdata.get("output_dir", job_dir), log_filename)
                else:
                    log_file = os.path.join(job_dir, log_filename)
                jsx_timeout = getattr(engine, "jsx_timeout", 300)
                indesign.run_jsx(jsx_path, log, poll_log_path=log_file,
                                 timeout=jsx_timeout,
                                 cancel_check=lambda: jm.is_cancelled(job_id))
            log("[2/3] 조판 완료 ✓")

        if jm.is_cancelled(job_id):
            return

        # ── 마지막 단계: 검수 ────────────────────────────────────────
        stage = "verify"
        step = total
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log(f"[{step}/{total}] 검수 중...")
        result = engine.verify(job_dir, log)
        log(f"[{step}/{total}] 검수 완료 ✓")

        # ── 범용 검수 게이트 (opt-in: YONE_INSPECT=1) ────────────────────
        # 조판 산출 .indd를 다시 열어 content.json 단어셋과 대조 — 내용 누락
        # 자동 검출. 엔진 코드/JSX 무수정, 실패해도 조판 결과에 영향 없음.
        # (mockexam_v2는 verify에 자체 게이트 내장 — 중복 덤프 방지 위해 제외)
        if (os.environ.get("YONE_INSPECT") == "1"
                and engine.material_id != "mockexam_v2"):
            try:
                from core.inspect import inspect_generic
                log("[검수+] 내용 보존 대조 중...")
                g = inspect_generic(job_dir, log)
                if g is not None:
                    result["inspect"] = g
                    if g["ok"]:
                        log(f"[검수+] ✅ 내용 보존 확인 "
                            f"({g['content_words']}단어, indd {g['indd_count']}개)")
                    else:
                        result["ok"] = False
                        warn = (f"[검수+] ❌ 내용 누락 의심 {g['missing_words']}단어: "
                                + ", ".join(g["missing_sample"][:8]))
                        result.setdefault("warnings", []).append(warn)
                        log(warn)
                    if g["overflow_stories"]:
                        log(f"[검수+] ⚠️ 오버플로우 스토리 {g['overflow_stories']}개")
            except Exception as _ie:
                log(f"[검수+] 건너뜀 (검수 실패가 조판을 막지 않음): {_ie}")

        # PDF를 목업 IN 폴더에 자동 복사
        pdf_path = result.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            os.makedirs(config.MOCKUP_IN_DIR, exist_ok=True)
            dest = os.path.join(config.MOCKUP_IN_DIR, os.path.basename(pdf_path))
            shutil.copy2(pdf_path, dest)
            result["mockup_file"] = os.path.basename(pdf_path)
            log(f"목업 폴더 복사 완료: {os.path.basename(pdf_path)}")

        jm.done(job_id, result)

        # (C1-4) 조판 완료 macOS 알림 — fail-open, YONE_NOTIFY=0으로 끔
        try:
            from core import notify
            notify.notify_job_finished(
                getattr(engine, "display_name", engine.material_id),
                job_id, ok=True)
        except Exception as _ne:
            log(f"[알림] 실패 (무시): {_ne}")

        # 조교 공유 폴더로 비동기 복사 (ASSISTANT_SHARE_DIR 환경변수 설정 시).
        # 별도 thread라 GDrive 지연/실패가 메인 pipeline에 영향 없음.
        try:
            from core.sharing import share_job_async
            school = ""
            school_path = os.path.join(job_dir, "school.txt")
            if os.path.exists(school_path):
                with open(school_path, encoding="utf-8") as _sf:
                    school = _sf.read().strip()
            # result에서 .indd 경로 힌트 추출 (settings.json fallback보다 정확함)
            _indd_hint = None
            if isinstance(result, dict):
                _indd_hint = result.get("indd_path") or result.get("indd_paths")
            share_job_async(job_id, job_dir, school, log, indd_path=_indd_hint, material_id=getattr(engine, "material_id", None))
        except Exception as _e:
            log(f"[공유] 시작 실패 (무시): {_e}")

    except Exception as e:
        log(f"[오류] {e}")
        import traceback
        tb = traceback.format_exc()
        log(tb)
        jm.fail(job_id, str(e))
        # (C1-4) 조판 실패 macOS 알림 — fail-open, YONE_NOTIFY=0으로 끔
        try:
            from core import notify
            notify.notify_job_finished(
                getattr(engine, "display_name", engine.material_id),
                job_id, ok=False, error=str(e))
        except Exception as _ne:
            log(f"[알림] 실패 (무시): {_ne}")
        # 실패 이력 영속화(분석용). 실패 경로를 절대 깨지 않도록 예외 무시.
        try:
            _persist_failure(job_id, job_dir, engine, stage, str(e), tb)
        except Exception:
            pass
