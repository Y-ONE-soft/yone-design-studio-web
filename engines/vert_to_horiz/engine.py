"""세로 → 가로 본문 복제 엔진.

세로버전 InDesign(.indd)의 본문 텍스트프레임을 가로버전(.indd)으로 옮김.
마더텅 출처 엑셀(JSON)을 기준으로 지문 순서를 검증하고,
영역(어휘선택 1/2, 본문 OX, 본문 정리, 내용 종합, 문장 배열, 빈칸 어휘,
어법 선택, 어법 OX, 빈칸 어법, 영작 배열, S 실전 문제)별로 매핑.

입력:
  - 가로 .indd (업로드 또는 GDrive 경로)
  - 세로 .indd (업로드 또는 GDrive 경로)
  - 강 번호 (자동 추출, 변경 가능)

처리:
  1. 두 파일을 InDesign 에서 열고
  2. 사이드 라벨로 가로 영역 자동 감지
  3. 세로 지문 식별(A-마스터 첫 페이지 = 새 지문)
  4. 엑셀 출처 코드로 순서 검증
  5. 영역별로 세로 마스터 페이지를 가로 페이지에 복제

출력: 수정된 가로 .indd (in-place 저장)
"""

import json
import os
import re
import shutil

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy


def _nfc(s):
    import unicodedata
    return unicodedata.normalize("NFC", s) if s else s


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


def _load_config():
    """엔진 디렉토리 기준 상대경로를 절대경로로 변환."""
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["output_base"])


def _extract_gang_code(filename):
    """파일명에서 마더텅 강 코드 추출. '마더텅7강' / '7강' / 'Lesson 07' 모두 처리."""
    if not filename:
        return None
    m = re.search(r"마더텅\s*(\d+)\s*강", filename)
    if m:
        n = int(m.group(1))
        return f"{n:02d}"
    m = re.search(r"(\d+)\s*강", filename)
    if m:
        n = int(m.group(1))
        return f"{n:02d}"
    m = re.search(r"[Ll]esson\s*(\d+)", filename)
    if m:
        n = int(m.group(1))
        return f"{n:02d}"
    return None


class VertToHorizEngine(BaseEngine):

    @property
    def material_id(self):
        return "vert_to_horiz"

    @property
    def display_name(self):
        return "세로→가로 본문 복제"

    @property
    def description(self):
        return "세로 .indd 본문을 가로 .indd 로 1:1 매핑 복제. 마더텅 출처 엑셀 기준 지문 순서 검증."

    @property
    def subject_prefix(self):
        return "가로결합"

    @property
    def template_name(self):
        return "typeset_vert_to_horiz.html"

    @property
    def log_filename(self):
        return "convert_log.txt"

    @property
    def jsx_timeout(self):
        return 900  # 15분

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "verti_indd",
                    "label": "세로버전 .indd (소스)",
                    "type": "file",
                    "accept": ".indd",
                    "required": True,
                },
                {
                    "key": "result_name",
                    "label": "결과 파일명 (확장자 제외)",
                    "type": "text",
                    "required": False,
                    "placeholder": "비워두면 세로 파일명 기반으로 자동",
                },
                {
                    "key": "gang_code",
                    "label": "마더텅 강 (파일명에서 자동 추출, 비워두면 자동)",
                    "type": "text",
                    "required": False,
                    "placeholder": "예: 07 (자동 인식되면 빈칸)",
                },
                {
                    "key": "do_label",
                    "label": "라벨링 자동 수행 (지문번호 NN 형식 + A_지문 번호B 문자스타일)",
                    "type": "text",
                    "required": False,
                    "placeholder": "on/off (기본 on)",
                },
            ]
        }

    # ─── 헬퍼 ───────────────────────────────────────────────────────

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        """세로 .indd 업로드 + 가로 원본 자동 복사, 강 코드 결정, metadata 저장."""
        cfg = _load_config()
        sources_json = os.path.join(_DIR, os.path.basename(cfg["sources_json"]))
        if not os.path.exists(sources_json):
            raise FileNotFoundError(f"출처 JSON 없음: {sources_json}")

        # 가로 원본 (GDrive) - 자동 복사
        horiz_template = os.path.expanduser(cfg["horiz_template_path"])
        if not os.path.exists(horiz_template):
            raise FileNotFoundError(
                f"가로 원본 파일을 찾을 수 없습니다: {horiz_template}\n"
                f"config.json 의 horiz_template_path 확인 필요"
            )
        log(f"[가로 원본] {os.path.basename(horiz_template)}")

        verti_src = uploaded_files.get("verti_indd")
        if not verti_src or not os.path.exists(verti_src):
            raise FileNotFoundError("세로 .indd 가 업로드되지 않았습니다")

        # 강 코드 - 사용자 입력 > 세로 파일명 > 01
        gang_input = (uploaded_files.get("gang_code") or "").strip()
        if gang_input:
            # "7" → "07", "07" → "07"
            m = re.search(r"(\d+)", gang_input)
            gang_code = f"{int(m.group(1)):02d}" if m else None
        else:
            gang_code = (
                _extract_gang_code(_nfc(os.path.basename(verti_src)))
                or "01"
            )

        # 출처 JSON 검증
        with open(sources_json, encoding="utf-8") as f:
            sources_data = json.load(f)
        if gang_code not in sources_data:
            available = ", ".join(sorted(sources_data.keys()))
            raise ValueError(
                f"엑셀에 강 '{gang_code}' 데이터가 없습니다. "
                f"등록된 강: {available}"
            )
        sources_list = sources_data[gang_code]
        log(f"[강] {gang_code} ({len(sources_list)}개 지문)")

        # 가로 원본 + 세로 .indd 를 job_dir 로 복사 (cross-document duplicate 시 원본 영향 방지)
        horiz_local = os.path.join(job_dir, f"horiz_{_nfc(os.path.basename(horiz_template))}")
        verti_local = os.path.join(job_dir, f"verti_{_nfc(os.path.basename(verti_src))}")
        try:
            safe_copy(horiz_template, horiz_local, log=log)
        except Exception as e:
            raise RuntimeError(f"가로 원본 복사 실패: {e}")
        try:
            safe_copy(verti_src, verti_local, log=log)
        except Exception as e:
            raise RuntimeError(f"세로 .indd 복사 실패: {e}")
        log(f"[복사] 가로 원본 → {os.path.basename(horiz_local)}")
        log(f"[복사] 세로 → {os.path.basename(verti_local)}")

        # 결과 파일명 - 사용자 입력 > 세로 파일명 기반 자동
        result_name = (uploaded_files.get("result_name") or "").strip()
        if not result_name:
            verti_base = _nfc(os.path.basename(verti_src))
            if verti_base.lower().endswith(".indd"):
                verti_base = verti_base[:-5]
            # "세로", "(세로)" 제거 후 "_가로" 추가
            result_name = re.sub(r"\s*\(?세로\)?\s*", "", verti_base) + "_가로"
        log(f"[결과 파일명] {result_name}")

        # 라벨링 옵션 (체크박스 — 폼에서 "on" 또는 미포함)
        do_label_raw = (uploaded_files.get("do_label") or "").strip().lower()
        do_label = do_label_raw in ("on", "true", "1", "yes")
        log(f"[라벨링] {'ON' if do_label else 'OFF'}")

        # metadata.json
        meta = {
            "horiz_path": horiz_local,
            "verti_path": verti_local,
            "verti_original_name": _nfc(os.path.basename(verti_src)),
            "result_name": result_name,
            "gang_code": gang_code,
            "sources_list": sources_list,
            "do_label": do_label,
        }
        meta_path = os.path.join(job_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta_path

    # ─── prepare_jsx ───────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()

        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)

        # 출력 경로 결정 — 가로 파일을 in-place 수정 후 결과 폴더로도 복사
        output_dir = os.path.join(STUDIO_ROOT, cfg["output_base"])
        os.makedirs(output_dir, exist_ok=True)

        # 결과 .indd 경로 (사용자 입력 또는 세로 파일명 기반)
        base = meta.get("result_name") or meta.get("verti_original_name", "결과")
        if base.lower().endswith(".indd"):
            base = base[:-5]
        indd_out = os.path.join(output_dir, f"{base}.indd")
        n = 2
        while os.path.exists(indd_out) and n < 1000:
            indd_out = os.path.join(output_dir, f"{base}_{n}.indd")
            n += 1

        log(f"[출력] {indd_out}")

        # 가로 사본을 출력 경로로 미리 복사 (JSX는 output_indd 를 열어 in-place 처리)
        shutil.copy2(meta["horiz_path"], indd_out)
        log(f"[가로 사본 → 출력 경로]")

        # settings.json
        settings = {
            "verti_path": meta["verti_path"],
            "output_indd": indd_out,
            "gang_code": meta["gang_code"],
            "sources_list": meta["sources_list"],
            "do_label": meta.get("do_label", False),
            "log_path": os.path.join(output_dir, self.log_filename),
            "log_paths": [os.path.join(job_dir, self.log_filename)],
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        # JSX 사본 + 토큰 치환
        jsx_src = os.path.join(_DIR, "jsx", "run.jsx")
        jsx_dst = os.path.join(job_dir, "run.jsx")
        with open(jsx_src, encoding="utf-8") as f:
            jsx_code = f.read()
        jsx_code = jsx_code.replace("__SETTINGS_PATH__", settings_path)
        with open(jsx_dst, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        return jsx_dst

    # ─── verify ────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        indd_out = settings["output_indd"]
        warnings = []
        if not os.path.exists(indd_out):
            warnings.append(f".indd 미생성: {os.path.basename(indd_out)}")

        # 로그에서 경고/오류 카운트
        log_path = settings.get("log_path", "")
        warn_count = 0
        if log_path and os.path.exists(log_path):
            try:
                content = open(log_path, encoding="utf-8", errors="ignore").read()
                warn_count = len(re.findall(r"\[경고\]|\[오류\]|FAIL", content))
                if warn_count > 0:
                    warnings.append(f"JSX 경고/오류 {warn_count}건 (로그 확인)")
            except OSError:
                pass

        ok = os.path.exists(indd_out) and len([w for w in warnings if "미생성" in w]) == 0

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": None,
            "pdf_paths": [],
            "indd_path": indd_out if os.path.exists(indd_out) else None,
            "warnings": warnings,
        }
