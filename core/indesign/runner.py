"""InDesign JSX 실행 — 단계별 소형 JSX 전달 방식.

큰 JSX를 한 번에 보내면 AppleEvents -609 에러 발생.
대신 작은 JSX 조각을 순차적으로 전송하고, 큰 로직은
content.json + state.json으로 InDesign 내부에서 처리.
"""

import json
import os
import shutil
import subprocess
import threading
import time
from core.indesign.lock import acquire as lock_acquire, release as lock_release

INDESIGN_VERSIONS = ["2026", "2025", "2024", "2023", "2022"]


def _is_indesign_running(app_name: str) -> bool:
    """System Events를 통해 InDesign 프로세스 실행 여부 확인.
    tell application "AppName" 방식은 앱을 실제로 론치시키므로 사용 금지."""
    try:
        # 프로세스 이름은 앱 번들 이름과 동일
        r = subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to (name of processes) contains "{app_name}"'],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "true"
    except Exception:
        return False


def find_indesign_app() -> str:
    installed = []
    for ver in INDESIGN_VERSIONS:
        app = f"Adobe InDesign {ver}"
        if os.path.isdir(f"/Applications/{app}"):
            installed.append(app)
    if not installed:
        raise RuntimeError("Adobe InDesign을 찾을 수 없습니다.")
    for app in installed:
        if _is_indesign_running(app):
            return app
    # 실행 중인 InDesign이 없으면 최신 버전을 자동 실행
    app = installed[0]
    subprocess.Popen(
        ["open", "-a", f"/Applications/{app}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # 실행 대기 (최대 120초 — InDesign 콜드 스타트는 느림)
    for _ in range(40):
        time.sleep(3)
        if _is_indesign_running(app):
            return app
    raise RuntimeError(f"{app} 실행 실패 — 수동으로 InDesign을 켜주세요")


def _exec_jsx(app_name: str, code: str, timeout: int = 30) -> str:
    """InDesign에서 작은 JSX 코드 실행 (인라인). 반환값: stdout."""
    escaped = code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def close_open_indd(indd_path: str, log=None) -> None:
    """출력 indd가 InDesign에 이미 열려 있으면 저장 없이 닫는다.

    재실행 시 출력 문서가 열린 상태에서 safe_copy가 그 위에 덮어쓰면
    InDesign 내부 문서가 stale/invalid 되어 app.open 시 'Object is invalid'
    오류가 난다. 반드시 safe_copy(덮어쓰기) '전에', 문서가 유효할 때 호출할 것.

    InDesign 미실행이면 아무것도 하지 않는다(실행시키지 않음).
    """
    app = None
    for ver in INDESIGN_VERSIONS:
        name = f"Adobe InDesign {ver}"
        if _is_indesign_running(name):
            app = name
            break
    if not app:
        return
    import unicodedata
    base = os.path.basename(indd_path)
    # 파일명을 NFC·NFD 두 형태로 전달:
    #   - InDesign 문서 경로(fsName/name)는 NFD, 파이썬 경로는 NFC라 한글이 불일치
    #   - iCloud 경로 이중성(~/Documents vs ~/Library/Mobile Documents/.../Documents)도
    #     basename 비교로 회피
    payload = unicodedata.normalize("NFC", base) + "|" + unicodedata.normalize("NFD", base)
    try:
        with open("/tmp/_indd_close_path.txt", "w", encoding="utf-8") as f:
            f.write(payload)
    except OSError:
        return
    # 한글 경로 osascript 이슈 회피: 파일에서 읽음. 백슬래시 미사용. '|' 구분.
    jsx = ('var pf=new File("/tmp/_indd_close_path.txt");pf.open("r");pf.encoding="UTF-8";'
           'var raw=pf.read();pf.close();var names=raw.split("|");'
           'for(var i=app.documents.length-1;i>=0;i--){try{var nm=app.documents[i].name;'
           'for(var j=0;j<names.length;j++){if(names[j].length>1&&nm===names[j]){'
           'app.documents[i].close(SaveOptions.NO);break;}}}catch(e){}}')
    _exec_jsx(app, jsx, timeout=30)
    if log:
        log(f"[InDesign] 기존 출력 문서 정리: {os.path.basename(indd_path)}")


def run_jsx(jsx_path: str, log, poll_log_path: str = None, timeout: int = 1200,
            cancel_check=None, completion_marker: str = None):
    """JSX 파일을 단계별로 실행.

    큰 JSX 파일 대신, settings.json에서 정보를 읽고
    Python에서 InDesign을 단계별로 제어.

    cancel_check: 콜백 함수. True 반환 시 작업 중단.
    """
    job_name = os.path.basename(jsx_path)

    # InDesign 실행 확인을 락 획득 전에 수행 (대기 중 락 점유 방지)
    log("[InDesign] InDesign 실행 확인 중...")
    app = find_indesign_app()
    log(f"[InDesign] {app} 확인 완료")

    # InDesign 실행 락 획득 (다른 작업 완료까지 대기)
    lock_acquire(job_name)
    log(f"[InDesign] 락 획득 — {job_name}")

    try:
        # settings.json 경로 추출 (JSX 파일에서)
        with open(jsx_path, encoding="utf-8") as f:
            jsx_content = f.read()

        # settingsPath 추출 (camelCase + UPPER_CASE 모두 지원)
        # camelCase: workbook/pocketbook/mockexam/hanyoung 등
        # UPPER_CASE: analysis_merge/mothertongue_merge/mockexam_sero_merge
        import re
        m = re.search(r'var (?:settingsPath|SETTINGS_PATH) = "([^"]+)"', jsx_content)
        if not m:
            log("[오류] settingsPath/SETTINGS_PATH 변수를 찾을 수 없습니다")
            return
        settings_path = m.group(1)

        # JSX를 /tmp에 복사 (한글 경로 회피)
        tmp_jsx = f"/tmp/indesign_run_{os.getpid()}.jsx"
        shutil.copy2(jsx_path, tmp_jsx)

        # 이전 실행의 /tmp 디버그 로그 삭제 (새 실행 감지 정확도 향상)
        for _old in ("/tmp/workbook_debug.txt",):
            try:
                os.remove(_old)
            except OSError:
                pass

        bootstrap = (
            'app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;'
            f'var _f = new File("{tmp_jsx}");'
            'app.doScript(_f, ScriptLanguage.JAVASCRIPT);'
            'app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;'
        )

        log("[InDesign] JSX 실행 시작...")

        escaped = bootstrap.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'with timeout of {timeout} seconds\n'
            f'tell application "{app}" to do script "{escaped}" language javascript\n'
            f'end timeout'
        )

        proc = subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # 로그 파일이 생길 때까지 대기 (= InDesign이 스크립트를 받아서 실행 시작한 증거)
        # iCloud 경로에서는 os.path.exists 반영이 느릴 수 있으므로
        # /tmp 디버그 로그도 함께 체크한다.
        _debug_log = "/tmp/workbook_debug.txt"
        _debug_mtime_before = 0
        try:
            _debug_mtime_before = os.path.getmtime(_debug_log) if os.path.exists(_debug_log) else 0
        except OSError:
            pass

        if poll_log_path:
            delivery_ok = False
            for _ in range(40):
                time.sleep(3)
                # 1) 본래 로그 파일 존재 체크
                if os.path.exists(poll_log_path):
                    delivery_ok = True
                    break
                # 2) /tmp 디버그 로그가 갱신되었으면 JSX가 실행 중인 것
                try:
                    if os.path.exists(_debug_log):
                        cur_mtime = os.path.getmtime(_debug_log)
                        if cur_mtime > _debug_mtime_before:
                            delivery_ok = True
                            break
                except OSError:
                    pass
                # osascript가 에러로 죽었으면 즉시 실패
                if proc.poll() is not None and proc.returncode != 0:
                    stderr = ""
                    try:
                        stderr = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                    except Exception:
                        pass
                    err_msg = stderr[:300] if stderr else f"osascript 종료코드 {proc.returncode}"
                    raise RuntimeError(f"InDesign 스크립트 전달 실패: {err_msg}")

            if delivery_ok:
                # 스크립트 전달 확인 후 osascript 종료 (응답 대기 불필요)
                proc.kill()
                log("[InDesign] 스크립트 전달 확인, 폴링 시작")
                _wait_for_completion(poll_log_path, log, timeout, cancel_check,
                                     completion_marker)
            else:
                proc.kill()
                raise RuntimeError("InDesign 스크립트 시작 안 됨 (120초 대기) — InDesign 상태를 확인하세요")
        else:
            try:
                proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError(f"InDesign 응답 없음 ({timeout}초 대기)")
    finally:
        lock_release()
        log(f"[InDesign] 락 해제 — {job_name}")


def _wait_for_completion(log_path: str, log, timeout: int, cancel_check=None,
                         completion_marker: str = None):
    elapsed = 0
    last_mtime = 0
    stall_seconds = 0
    STALL_LIMIT = 300  # 로그 갱신 없이 5분 경과하면 행(hang) 판정
    _debug_log = "/tmp/workbook_debug.txt"

    def _read_any_log():
        """log_path 또는 /tmp 디버그 로그 중 내용이 있는 쪽을 반환."""
        for p in (log_path, _debug_log):
            try:
                if os.path.exists(p):
                    return open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
        return ""

    while elapsed < timeout:
        time.sleep(3)
        elapsed += 3
        stall_seconds += 3

        # 취소 체크
        if cancel_check and cancel_check():
            log("[InDesign] 사용자 취소 감지 — 대기 중단")
            raise RuntimeError("사용자가 작업을 취소했습니다.")

        # mtime 체크 (둘 중 하나라도 갱신되면 stall 리셋)
        for p in (log_path, _debug_log):
            try:
                if os.path.exists(p):
                    mtime = os.path.getmtime(p)
                    if mtime != last_mtime:
                        last_mtime = mtime
                        stall_seconds = 0
            except OSError:
                pass

        content = _read_any_log()
        if not content:
            continue

        # PDF 내보내기 완료 또는 조판 결과 요약이 있으면 완료
        if completion_marker:
            if completion_marker in content:
                time.sleep(2)
                return
        elif "PDF:" in content or "STEP\uc644\ub8cc:" in content or "\uc870\ud310 \uc644\ub8cc" in content:
            time.sleep(2)
            return
        # JSX 에러 감지 — 조판 시작 이후에 [오류]가 있으면 실패
        if "[오류]" in content:
            after_start = content.split("\uc870\ud310 \uc2dc\uc791")[-1] if "\uc870\ud310 \uc2dc\uc791" in content else content
            if "[오류]" in after_start and len(after_start.strip()) > 20:
                err_msg = after_start.strip().split("[오류]")[-1].strip()[:200]
                log("[InDesign] JSX 에러: " + err_msg)
                raise RuntimeError(err_msg)

        # 행(hang) 감지: 로그 갱신이 STALL_LIMIT 이상 없으면 InDesign 프로세스 강제 종료 후 재시도
        if stall_seconds >= STALL_LIMIT and last_mtime > 0:
            log(f"[InDesign] 로그 갱신 없음 ({stall_seconds}초) — InDesign 행(hang) 감지")
            _kill_indesign(log)
            raise RuntimeError(f"InDesign 응답 없음 (로그 {stall_seconds}초간 미갱신) — 자동 종료됨. 재시도해주세요.")

    raise RuntimeError(f"InDesign 응답 없음 ({timeout}초 대기) — InDesign이 실행 중인지 확인하세요")


def _kill_indesign(log):
    """InDesign 프로세스 강제 종료."""
    try:
        result = subprocess.run(
            ["pkill", "-9", "-f", "Adobe InDesign"],
            capture_output=True, text=True, timeout=10
        )
        log("[InDesign] 프로세스 강제 종료 완료")
    except Exception as e:
        log(f"[InDesign] 프로세스 종료 실패: {e}")
