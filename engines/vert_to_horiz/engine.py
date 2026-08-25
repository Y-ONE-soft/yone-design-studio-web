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
    # 4차 (배치 F): 공백/언더스코어 제거 후 재시도 — '마더텅_7_강' 류
    # 구분자 변형 (기존 3단 폴백 실패 시에만 진입 — 기존 인식 무변경)
    despaced = re.sub(r"[\s_]+", "", filename)
    if despaced != filename:
        for pat in (r"마더텅(\d+)강", r"(\d+)강", r"[Ll]esson(\d+)"):
            m = re.search(pat, despaced)
            if m:
                return f"{int(m.group(1)):02d}"
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
    def completion_marker(self):
        # run.jsx 마지막 줄. 이 표식이 없으면 러너가 로그 무갱신만 보고
        # 판정해, **정상 완료를 스톨로 오보고**한다 (2026-08-18 실측:
        # 00:42:53 저장 완료 → 00:47 "InDesign 스톨" 실패 처리).
        return "=== 작업 완료 ==="

    @property
    def jsx_timeout(self):
        return 1800  # 30분 — 실측 21분 (개발가이드 기록)

    # ─── 후처리 ────────────────────────────────────────────────────────
    # 파이프라인은 run_indesign 이 있으면 그것만 호출한다. 본 변환(run.jsx)을
    # 돌린 뒤 후처리 3종을 이어서 실행한다.
    #   1) 미사용 슬롯 페이지 제거 — 가로 템플릿은 슬롯이 넉넉해 선택 문항이
    #      적으면 빈 페이지가 대량 남는다 (실측 16문항 → 283p 중 54p)
    #   2) STEP3 재스레드 — 프레임 단위 duplicate 로 스레드가 끊겨, 편집 시
    #      리플로우가 안 되고 문항 자동번호가 프레임마다 01 로 재시작한다
    #      (실측: 번호 138개 중 9개 중복 → 재스레드 후 세로 원본과 동일한 129개)
    #   3) 지문번호 프레임 교정 — 본문만 옮기면 템플릿 잔재 번호가 인쇄된다
    # 순서 중요: 페이지를 지운 **뒤에** 번호를 매겨야 순서가 맞는다.
    _POST = [
        ("trim_unused.jsx", "trim_로그.txt",
         "===== 정리 완료 =====", "[정리]"),
        ("rethread_step3.jsx", "rethread_로그.txt",
         "===== 재스레드 완료 =====", "[재스레드]"),
        ("fix_passage_numbers.jsx", "passagenum_로그.txt",
         "===== 지문번호 교정 완료 =====", "[지문번호]"),
    ]

    def run_indesign(self, job_dir, log, cancel_check=None, stall_limit=None):
        from core.indesign import runner as indesign
        import os as _os

        settings_path = _os.path.join(job_dir, ".settings.json")
        jsx_path = _os.path.join(job_dir, "run.jsx")
        out_dir = job_dir
        if _os.path.exists(settings_path):
            try:
                with open(settings_path, encoding="utf-8") as f:
                    out_dir = json.load(f).get("output_dir", job_dir)
            except (OSError, ValueError):
                pass
        log_file = _os.path.join(out_dir, self.log_filename)
        # stall_limit: 본 변환은 저장·PDF 구간에서 로그가 오래 멈춘다
        # (실측 6분 7초). 기본 300초면 정상 작업을 스톨로 오판한다.
        # 인자를 안 주면 종전 기본값 — Flask 경로는 무변경.
        indesign.run_jsx(jsx_path, log, poll_log_path=log_file,
                         timeout=self.jsx_timeout,
                         completion_marker=self.completion_marker,
                         cancel_check=cancel_check, stall_limit=stall_limit)

        for tpl, logname, marker, tag in self._POST:
            src = _os.path.join(_DIR, "jsx", tpl)
            if not _os.path.exists(src):
                log("%s 템플릿 없음 — 건너뜀: %s" % (tag, tpl))
                continue
            with open(src, encoding="utf-8") as f:
                code = f.read().replace("__SETTINGS_PATH__", settings_path)
            dst = _os.path.join(job_dir, tpl)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(code)
            poll = settings_path.replace(".settings.json", logname)
            try:
                _os.remove(poll)
            except OSError:
                pass
            log("%s 시작" % tag)
            indesign.run_jsx(dst, log, poll_log_path=poll, timeout=1800,
                             completion_marker=marker, stall_limit=900,
                             cancel_check=cancel_check)

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
            gang_code = _extract_gang_code(_nfc(os.path.basename(verti_src)))

        # 출처 JSON — **마더텅 job 일 때만** 쓴다.
        # 마더텅 엑셀은 가로 페이지 ↔ 세로 지문 매핑을 "출처 코드"로 정확히
        # 맞추는 용도이고, 없으면 JSX 가 **영역 내 순서 = 세로 지문 순서**로
        # 폴백한다(run.jsx: "fallback: 영역 내 페이지 순서 = 세로 지문 순서").
        # 일반 모의고사 선택 결합은 강이라는 개념 자체가 없고 순서가 곧
        # 사용자가 고른 순서이므로 폴백이 오히려 정확하다.
        #
        # ⚠ 종전엔 강을 못 찾으면 '01' 로 가정하고 엑셀을 뒤져서,
        #   마더텅이 아닌 job 이 "엑셀에 강 '01' 데이터가 없습니다" 로 죽었다
        #   (2026-08-18 실측: 세로결합_고2_25년9월 → 변환 자체가 불가).
        #   강 추정도 하지 않는다 — 엉뚱한 강으로 매핑하면 지문이 뒤섞인다.
        sources_list = []
        if gang_code:
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
        else:
            log("[강] 마더텅 강 미지정 — 출처 엑셀 미사용, "
                "**세로 지문 순서 그대로** 가로에 매핑합니다. "
                "마더텅 교재면 '마더텅 강' 입력란에 번호를 넣으세요.")

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

        # 로그에서 경고/오류 카운트 — job 전용 로그(이번 실행분만) 사용.
        # log_path는 출력 폴더(조판/교재/가로결합/) 전역 convert_log.txt 로
        # 모든 작업의 로그가 영구 누적된다 — 과거 실행 경고(예: 2026-05-22
        # 1차 실행 642건)가 이후 모든 작업 판정에 계상되는 오염 방지.
        log_paths = settings.get("log_paths") or []
        log_path = log_paths[0] if log_paths else settings.get("log_path", "")
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
