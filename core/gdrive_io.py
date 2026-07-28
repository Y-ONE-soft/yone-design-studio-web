"""core/gdrive_io.py — GDrive/iCloud(FileProvider) 파일의 조율(coordinated) 안전 복사.

## 근본 원인 (실측)
macOS의 FileProvider-backed 경로(`~/Library/CloudStorage/GoogleDrive-.../`,
iCloud 등)는 파일 접근 시 **NSFileCoordinator 조율**을 요구한다. 그런데
`shutil.copy2`(fcopyfile) / `/bin/cp -c`(clonefile) / 파이썬 raw `read(2)` 는
전부 **미조율 동기 접근**이라, launchd-spawned Flask 워커 스레드에서 FileProvider
데몬의 락과 충돌해 `EDEADLK`(Errno 11, Resource deadlock avoided)를 낸다.
지금까지의 대응(재시도 백오프·로컬 미러 redirect·Drive 재시작)은 전부 증상 완화라,
조율을 요구하는 파일에서 재발했다.

## 근본 해법
`bin/coord_read`(Swift, `NSFileCoordinator().coordinate(readingItemAt:)` 블록 안에서
복사)로 **정식 조율 접근**을 1차 경로로 쓴다. 조율 하에서는 FileProvider가
materialize·락 해제를 마친 뒤 복사가 실행되므로 데드락이 원천적으로 발생하지 않는다.

## 폴백 사다리 (더 나빠지지 않음 보장)
FileProvider 경로에 대해 순서대로 시도하고, **어느 단계가 성공했는지 항상 로그**한다:
  1. `bin/coord_read` 헬퍼 (조율 복사) — 근본 경로
  2. `swift` 인라인 조율 스크립트 (헬퍼 바이너리가 없을 때)
  3. 로컬 미러 redirect (미러가 있으면 FileProvider 자체를 우회)
  4. `/bin/cp -f`
  5. `shutil.copy2` + 지수 백오프
비-FileProvider(순수 로컬) 경로는 곧장 `shutil.copy2` — 조율 오버헤드 없음.

## 안전 밸브
`YONE_GDRIVE_COORD=0` → 조율 헬퍼/인라인을 건너뛰고 곧장 레거시 폴백(3~5)만 사용.
헬퍼가 문제를 일으킬 때 즉시 끌 수 있다. (기본값은 조율 사용.)
"""

import os
import shutil
import subprocess
import time
import unicodedata


# FileProvider(CloudStorage) 경로 마커. 이 문자열을 포함하면 조율이 필요하다.
_FILEPROVIDER_MARKER = "/Library/CloudStorage/"

# coord_read 헬퍼 바이너리 위치 (리포 루트/bin/coord_read).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COORD_HELPER = os.path.join(_REPO_ROOT, "bin", "coord_read")
_COORD_HELPER_SWIFT = os.path.join(_REPO_ROOT, "bin", "coord_read.swift")


def _log(log, msg):
    if log:
        log(msg)


def _coord_enabled():
    """안전 밸브: YONE_GDRIVE_COORD=0 이면 조율 경로를 끈다."""
    return os.environ.get("YONE_GDRIVE_COORD", "1").strip() not in ("0", "false", "no")


def is_fileprovider_path(path):
    """path가 FileProvider(CloudStorage) 백엔드 경로인가 — 조율 필요 여부."""
    if not path:
        return False
    return _FILEPROVIDER_MARKER in unicodedata.normalize("NFC", path)


def _resolve_src(src):
    """NFC/NFD 후보 중 실제 존재하는 경로를 고른다. 없으면 None."""
    cands = [src]
    for norm in (unicodedata.normalize("NFC", src), unicodedata.normalize("NFD", src)):
        if norm not in cands:
            cands.append(norm)
    for c in cands:
        try:
            if os.path.exists(c):
                return c
        except OSError:
            continue
    return None


def _verify_copy(dst, expected_size):
    try:
        return os.path.exists(dst) and os.path.getsize(dst) == expected_size
    except OSError:
        return False


def coord_read_to(src, dst, log=None):
    """NSFileCoordinator 조율 하에 src를 dst로 복사 — 근본 경로 단독 시도.

    Returns: (ok: bool, err: str, method: str)
      method ∈ {"coord_helper", "coord_swift_inline", ""}
    실패/비활성 시 ok=False (호출측이 폴백 사다리로 진행).
    """
    if not _coord_enabled():
        return False, "coord disabled (YONE_GDRIVE_COORD=0)", ""

    src_resolved = _resolve_src(src)
    if src_resolved is None:
        return False, f"소스 없음: {src}", ""
    try:
        expected = os.path.getsize(src_resolved)
    except OSError as e:
        return False, f"getsize 실패: {e}", ""

    # 1) 빌드된 헬퍼 바이너리
    if os.path.exists(_COORD_HELPER) and os.access(_COORD_HELPER, os.X_OK):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            res = subprocess.run(
                [_COORD_HELPER, src_resolved, dst],
                capture_output=True, text=True, timeout=300,
            )
            if res.returncode == 0 and _verify_copy(dst, expected):
                _log(log, f"  [조율복사] coord_read 헬퍼 성공 ({expected}B)")
                return True, "", "coord_helper"
            err = (res.stderr or res.stdout or "").strip() or f"rc={res.returncode}"
            _log(log, f"  [조율복사] coord_read 헬퍼 실패 → 다음 단계: {err}")
        except (OSError, subprocess.SubprocessError) as e:
            _log(log, f"  [조율복사] coord_read 헬퍼 예외 → 다음 단계: "
                      f"{type(e).__name__}: {e}")
    else:
        _log(log, "  [조율복사] coord_read 헬퍼 없음/미실행권한 → 인라인 swift 시도")

    # 2) swift 인라인 (헬퍼 바이너리 부재/실패 시). swiftc 빌드 없이 조율 접근.
    swift_bin = shutil.which("swift") or "/usr/bin/swift"
    if os.path.exists(swift_bin):
        script = _SWIFT_INLINE
        try:
            if os.path.exists(dst):
                os.remove(dst)
            res = subprocess.run(
                [swift_bin, "-", src_resolved, dst],
                input=script, capture_output=True, text=True, timeout=300,
            )
            if res.returncode == 0 and _verify_copy(dst, expected):
                _log(log, f"  [조율복사] swift 인라인 조율 성공 ({expected}B)")
                return True, "", "coord_swift_inline"
            err = (res.stderr or res.stdout or "").strip() or f"rc={res.returncode}"
            _log(log, f"  [조율복사] swift 인라인 실패 → 폴백: {err}")
            return False, f"swift 인라인 실패: {err}", ""
        except (OSError, subprocess.SubprocessError) as e:
            _log(log, f"  [조율복사] swift 인라인 예외 → 폴백: {type(e).__name__}: {e}")
            return False, f"swift 인라인 예외: {e}", ""

    return False, "조율 경로 사용 불가 (헬퍼·swift 모두 부재)", ""


def coordinated_copy(src, dst, log=None, retries=5):
    """GDrive/iCloud 파일을 dst로 안전 복사 — 조율 우선 + 폴백 사다리.

    - FileProvider 경로: coord_read 헬퍼 → swift 인라인 → 미러 redirect → cp -f
      → shutil.copy2+백오프.
    - 비-FileProvider 경로: 곧장 shutil.copy2 (오버헤드 없음).

    각 단계 성공/실패를 로그로 남긴다 (침묵 금지).

    Returns: (ok: bool, err: str)
    """
    src_resolved = _resolve_src(src)
    if src_resolved is None:
        return False, f"소스 파일 없음: {src}"
    try:
        expected = os.path.getsize(src_resolved)
    except OSError as e:
        return False, f"getsize 실패: {e}"

    # 비-FileProvider(순수 로컬): 조율 불필요 — 기존 동작 그대로.
    if not is_fileprovider_path(src_resolved):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.copy2(src_resolved, dst)
            if _verify_copy(dst, expected):
                return True, ""
            return False, f"부분 복사: src={expected}B dst={os.path.getsize(dst)}B"
        except OSError as e:
            return False, f"{type(e).__name__}: {e}"

    # ── FileProvider 경로: 조율 우선 ──────────────────────────────────────
    ok, err, method = coord_read_to(src_resolved, dst, log=log)
    if ok:
        return True, ""
    last_err = err or "조율 실패"

    # 3) 로컬 미러 redirect — 미러가 있으면 FileProvider 자체를 우회.
    try:
        from engines.final.extractor import _resolve_local_mirror
        mirror = _resolve_local_mirror(src_resolved, log=None)
    except Exception:
        mirror = src_resolved
    if mirror and mirror != src_resolved and os.path.exists(mirror):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.copy2(mirror, dst)
            if _verify_copy(dst, os.path.getsize(mirror)):
                _log(log, f"  [조율복사] 로컬 미러 redirect 성공")
                return True, ""
        except OSError as e:
            last_err = f"{last_err} / 미러 실패: {e}"
            _log(log, f"  [조율복사] 미러 redirect 실패 → 다음: {e}")

    # 4) /bin/cp -f (별도 프로세스 syscall 경로)
    try:
        if os.path.exists(dst):
            os.remove(dst)
        res = subprocess.run(["/bin/cp", "-f", src_resolved, dst],
                             capture_output=True, text=True, timeout=300)
        if res.returncode == 0 and _verify_copy(dst, expected):
            _log(log, "  [조율복사] /bin/cp -f 성공")
            return True, ""
        cperr = (res.stderr or res.stdout or "").strip() or f"rc={res.returncode}"
        last_err = f"{last_err} / cp -f 실패: {cperr}"
        _log(log, f"  [조율복사] /bin/cp -f 실패 → 다음: {cperr}")
    except (OSError, subprocess.SubprocessError) as e:
        last_err = f"{last_err} / cp -f 예외: {e}"
        _log(log, f"  [조율복사] /bin/cp -f 예외 → 다음: {e}")

    # 5) shutil.copy2 + 지수 백오프 (최후)
    backoffs = [1, 3, 8, 15, 30]
    for attempt in range(retries):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.copy2(src_resolved, dst)
            if _verify_copy(dst, expected):
                if attempt > 0:
                    _log(log, f"  [조율복사] shutil.copy2 백오프 성공 ({attempt+1}회차)")
                return True, ""
            last_err = f"부분 복사: src={expected}B dst={os.path.getsize(dst)}B"
        except OSError as e:
            last_err = f"{last_err} / copy2: {type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(backoffs[min(attempt, len(backoffs) - 1)])

    _log(log, f"  [조율복사] 모든 경로 실패: {last_err}")
    return False, last_err


# swift 인라인 스크립트 — 헬퍼 바이너리가 없을 때 `swift -` 로 stdin 실행.
# coord_read.swift와 동일한 조율 로직의 축약본.
_SWIFT_INLINE = r"""
import Foundation
let a = CommandLine.arguments
guard a.count >= 3 else { FileHandle.standardError.write("usage\n".data(using:.utf8)!); exit(2) }
let s = URL(fileURLWithPath: a[1]); let d = URL(fileURLWithPath: a[2])
let c = NSFileCoordinator(filePresenter: nil)
var ce: NSError?; var ie: NSError?; var n = -1
c.coordinate(readingItemAt: s, options: .withoutChanges, error: &ce) { u in
    if FileManager.default.fileExists(atPath: a[2]) { try? FileManager.default.removeItem(at: d) }
    do { let data = try Data(contentsOf: u, options: []); try data.write(to: d, options: [.atomic]); n = data.count }
    catch let e as NSError { ie = e }
}
if let e = ce { FileHandle.standardError.write("coord: \(e)\n".data(using:.utf8)!); exit(3) }
if let e = ie { FileHandle.standardError.write("copy: \(e)\n".data(using:.utf8)!); exit(4) }
if n < 0 { exit(5) }
FileHandle.standardError.write("OK \(n)\n".data(using:.utf8)!)
"""
