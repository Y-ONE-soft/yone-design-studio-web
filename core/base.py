import abc
import os
import shutil


def safe_copy_indd(src, dst):
    """src를 dst로 복사하되, dst에 같은 이름 파일이 있으면 _2, _3 ... 붙여서 저장.
    실제 저장된 경로를 반환한다."""
    if not os.path.exists(dst):
        shutil.copy(src, dst)
        return dst
    base, ext = os.path.splitext(dst)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    dst = f"{base}_{n}{ext}"
    shutil.copy(src, dst)
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
