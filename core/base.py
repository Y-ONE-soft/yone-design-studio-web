import abc
import errno
import os
import shutil
import subprocess
import tempfile
import time


def _exists_nonempty(path):
    """정상 파일(크기 > 0)이 존재하는지. 0바이트 쓰레기는 존재하지 않는 것으로 취급."""
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def safe_copy(src, dst, log=None):
    """모든 엔진의 통합 안전 복사.

    GDrive 경로면 자동으로 로컬 미러 redirect (EDEADLK 회피).
    비 GDrive 경로면 shutil.copy2와 동일하게 동작.

    Returns: 저장된 dst 경로
    Raises: RuntimeError (5회 재시도 후에도 실패 시)
    """
    # 지연 import (engines.final 모듈 의존성 회피)
    from engines.final.extractor import _gdrive_safe_copy
    log_fn = log if log is not None else (lambda x: None)
    ok, err = _gdrive_safe_copy(src, dst, log=log_fn)
    if not ok:
        raise RuntimeError(
            f"복사 실패: {os.path.basename(src)} -> "
            f"{os.path.basename(dst)} ({err[:200]})"
        )
    return dst


def _is_deadlock(err):
    return isinstance(err, OSError) and err.errno == errno.EDEADLK


def _raw_copy(src, dst):
    """저수준 read/write 루프. 청크마다 open-close 하지 않음."""
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            chunk = fsrc.read(256 * 1024)
            if not chunk:
                break
            fdst.write(chunk)


def _cp_shell(src, dst):
    """macOS /bin/cp 폴백. Python 런타임과 다른 시스템콜 경로를 탄다.

    -c 로 APFS clonefile(2) 우선 사용 — read(2)를 거치지 않아 EDEADLK를 회피한다.
    같은 APFS 볼륨이 아니면 cp가 자동으로 일반 read/write 복사로 폴백한다.
    실패 시 stderr를 OSError 메시지에 포함시켜 원인을 로그에 노출한다."""
    res = subprocess.run(
        ["/bin/cp", "-c", src, dst],
        capture_output=True, text=True
    )
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip() or f"rc={res.returncode}"
        raise OSError(errno.EIO, f"/bin/cp -c 실패: {msg}", src)


def _stream_copy(src, dst):
    """Google Drive File Stream / iCloud Drive 교착 회피.

    원본이 클라우드 관리 파일인 경우 read(2) 호출이 간헐적으로 EDEADLK를 던진다.
    전략: (0) 로컬 미러 redirect → (1) 지수백오프 재시도 → (2) /bin/cp 폴백
         → (3) /tmp 경유 폴백.
    .tmp 파일 + os.rename 으로 원자성 확보. 복사 실패 시 .tmp 제거.

    (0) 로컬 미러 — ~/Documents/yone-content-mirror/에 미러가 있으면 GDrive 우회.
    NSFileProvider 데몬을 거치지 않아 EDEADLK 자체가 발생하지 않음.
    safe_copy_indd를 거치는 13개 엔진(blackbook, mockexam, whitebook 등)이 모두 혜택."""
    # 지연 import — engines.final 모듈 순환 의존 회피
    from engines.final.extractor import _resolve_local_mirror
    src = _resolve_local_mirror(src, log=None)

    # [근본 경로] 미러가 없어 src가 여전히 FileProvider(CloudStorage) 경로면
    # NSFileCoordinator 조율 복사를 1차로 시도 (EDEADLK 원천 차단). 실패 시 아래
    # 기존 raw_copy → cp -c → /tmp 폴백으로 진행 (더 나빠지지 않음). W48.
    try:
        from core.gdrive_io import coord_read_to, is_fileprovider_path
        if is_fileprovider_path(src):
            _ok, _err, _m = coord_read_to(src, dst, log=None)
            if _ok and os.path.getsize(dst) == os.path.getsize(src):
                return
    except Exception:
        pass  # 조율 실패는 침묵 폴백 — 아래 기존 사다리가 처리

    tmp = dst + ".tmp"

    def _cleanup_tmp():
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    src_size = os.path.getsize(src)
    last_err = None

    for attempt in range(5):
        _cleanup_tmp()
        try:
            _raw_copy(src, tmp)
            if os.path.getsize(tmp) != src_size:
                raise IOError(f"size mismatch: src={src_size} tmp={os.path.getsize(tmp)}")
            break
        except OSError as e:
            last_err = e
            if not _is_deadlock(e):
                _cleanup_tmp()
                raise
            time.sleep(0.5 * (2 ** attempt))
    else:
        _cleanup_tmp()
        try:
            _cp_shell(src, tmp)
            if os.path.getsize(tmp) != src_size:
                raise IOError("cp size mismatch")
        except Exception:
            _cleanup_tmp()
            fd, local = tempfile.mkstemp(prefix="safe_copy_", suffix=".indd")
            os.close(fd)
            try:
                _cp_shell(src, local)
                _raw_copy(local, tmp)
                if os.path.getsize(tmp) != src_size:
                    raise IOError("tmp-relay size mismatch")
            finally:
                try:
                    os.remove(local)
                except OSError:
                    pass

    try:
        shutil.copystat(src, tmp)
    except OSError:
        pass
    os.rename(tmp, dst)


def safe_copy_indd(src, dst):
    """src를 dst로 복사하되, dst에 같은 이름 파일이 있으면 _2, _3 ... 붙여서 저장.
    실제 저장된 경로를 반환한다.

    0바이트 파일(과거 교착으로 남은 쓰레기)은 존재하지 않는 것으로 간주하고 덮어쓴다."""
    if _exists_nonempty(dst):
        base, ext = os.path.splitext(dst)
        n = 2
        while _exists_nonempty(f"{base}_{n}{ext}"):
            n += 1
        dst = f"{base}_{n}{ext}"
    _stream_copy(src, dst)
    return dst


class BaseEngine(abc.ABC):
    """교재별 조판 엔진 기본 인터페이스.

    새 교재 추가 시 이 클래스를 상속해 4가지를 구현하고,
    engines/registry.py 에 한 줄 추가하면 끝.
    """

    @property
    @abc.abstractmethod
    def material_id(self) -> str:
        """URL slug. 예: 'whitebook'"""

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        """UI 카드 표시명. 예: '화이트북 워크북'"""

    @property
    @abc.abstractmethod
    def upload_spec(self) -> dict:
        """
        업로드 슬롯 명세. UI가 이 값을 읽어 파일 입력 폼을 동적 생성.

        반환 형식:
        {
            "slots": [
                {"key": "week2", "label": "Week2 원고 (.hwpx)", "required": True},
                {"key": "ans2",  "label": "Week2 정답 (.hwpx)", "required": False},
                ...
            ]
        }
        """

    @abc.abstractmethod
    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        """
        업로드된 hwpx 파일들을 content.json 으로 변환.

        Args:
            uploaded_files: {slot_key: 절대경로}
            job_dir: 작업 임시 디렉터리 (content.json 저장 위치)
            log: callable(str) — SSE로 전송될 로그 콜백
        Returns:
            content.json 절대경로
        """

    @abc.abstractmethod
    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        """
        job_dir/.settings.json 작성 + job별 jsx 임시 사본 생성.

        Args:
            json_path: content.json 절대경로
            job_dir: 작업 임시 디렉터리
            log: callable(str)
        Returns:
            실행할 jsx 파일 절대경로
        """

    @abc.abstractmethod
    def verify(self, job_dir: str, log) -> dict:
        """
        조판_로그.txt 파싱 → 검수 결과 반환.

        Returns:
            {
                "ok": bool,
                "overflow": int,
                "stories": {"A어휘": {"actual": 10, "expected": 10}, ...},
                "pdf_path": str | None,
                "warnings": [str]
            }
        """
