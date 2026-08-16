"""워크북 슬림 변환 엔진 (수동 Slim_Ver / Slim_Merge / Slim_Merge2 웹 흡수).

완성된 워크북 .indd 에서 섹션별로 액션을 적용해 슬림 판을 만든다.
섹션 탐지는 '단원' 스타일(문자 스타일 그룹 '마스터페이지' > '단원' →
문서 문자 스타일 → 단락 스타일 순 폴백)이 적용된 파스트보드 숨김 마커
프레임 — 마스터 러닝헤더 텍스트변수의 소스라 내지 개편에 강건하다.

섹션 액션 3종:
  - delete      (Slim_Ver.jsx)    섹션 페이지 전량 삭제. 범위 끝의
                                  간지/백지([없음]·M·간지 마스터)는 가드로 제외.
  - merge_half  (Slim_Merge.jsx)  전체높이 프레임 1개짜리 섹션을 2p→1p.
                                  host 프레임을 상단 절반으로 축소 +
                                  다음 페이지 개체를 하단 절반으로 이동.
  - merge_stack (Slim_Merge2.jsx) 상단(문제)+하단(부가문제) 2프레임 섹션을
                                  2p→1p. 하단 프레임 삭제 후 다음 페이지
                                  상단 프레임을 host 아래에 적층.

후처리 2종(자동):
  - 섹션 첫 페이지 마스터 좌/우 보정 (A↔B, C↔D — 헤더 탭이 있는 변형 선택)
  - 간지 스프레드 정렬 — 간지 블록([없음] 마스터 연속 런)의 마지막 페이지가
    왼쪽으로 밀리면 블록 앞에 메모 페이지(M 마스터)를 삽입해 (왼쪽,오른쪽)
    2P 구성을 복원. 밀리면 간지 배경이 pasteboard로 나가고 흰 글자 제목이
    흰 배경에 얹혀 통째로 안 보인다 (오버셋·링크·폰트로는 안 잡히는 결함).

입력: .indd 업로드 + 섹션별 액션(또는 학교 프리셋). 출력: 슬림 .indd
(원본 무접촉 — job_dir 사본을 출력 경로로 복사 후 in-place 수정).
PDF export 없음 (슬림본은 후속 작업의 중간 산출물).

구 2모드(merge_mode=ox|arrange)는 하위호환 — config.modes 의 action 으로
액션 목록에 합류시킨다.
"""

import json
import os
import re
import shutil
import unicodedata

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy


def _nfc(s):
    return unicodedata.normalize("NFC", s) if s else s


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["output_base"])


class SlimMergeEngine(BaseEngine):

    @property
    def material_id(self):
        return "slim_merge"

    @property
    def display_name(self):
        return "워크북 슬림 변환"

    @property
    def description(self):
        return ("완성 워크북 .indd에서 섹션을 빼거나 두 페이지를 한 페이지로 "
                "병합해 슬림 판 생성 (간지 스프레드 정렬 포함)")

    @property
    def subject_prefix(self):
        return "슬림변환"

    @property
    def template_name(self):
        return "typeset_slim_merge.html"

    @property
    def log_filename(self):
        return "slim_log.txt"

    @property
    def jsx_timeout(self):
        # 대형 전체(C) 문서: 열기+findText ~3분 + page.remove() 페이지당
        # 수십 초 (256p 실측 총 10분) — 여유 있게 30분
        return 1800

    def run_indesign(self, job_dir, log):
        """전용 실행기 — 대형 문서의 무로그 구간(open/save) 스톨 오탐 방지.

        기본 stall_limit 300초는 27MB 전체(C) 문서의 열기+findText(실측
        175초)나 저장 구간에서 오탐 위험 — workbook_v2 전례(W4)대로 900초.
        """
        import json as _json
        from core.indesign import runner
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = _json.load(f)
        # 폴링 로그 = job 전용 로그 (이번 실행분만) — 출력 폴더 공용 로그는
        # 과거 실행의 완료 마커/[오류]가 누적돼 오판정 (merge 계열 감사 패턴)
        log_paths = settings.get("log_paths") or []
        log_file = (log_paths[0] if log_paths
                    else os.path.join(job_dir, self.log_filename))
        # completion_marker 필수: 이 엔진은 PDF export가 없어 runner의
        # 기본 완료 휴리스틱("PDF:"/"조판 완료")에 걸리지 않는다 (E2E 실측)
        runner.run_jsx(os.path.join(job_dir, "run.jsx"), log,
                       poll_log_path=log_file, timeout=self.jsx_timeout,
                       stall_limit=900,
                       completion_marker="===== 완료 =====")

    # ─── UI 데이터 (템플릿이 engine.* 로 읽음 — config 단일 소스) ───────

    @property
    def ui_sections(self):
        """섹션 체크 목록 — config.sections 그대로."""
        return _load_config().get("sections", [])

    @property
    def ui_presets(self):
        """학교 프리셋 — {key: {label, hint, delete, merge_half, merge_stack}}."""
        return _load_config().get("presets", {})

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "src_indd",
                    "label": "대상 .indd (워크북 전체)",
                    "type": "file",
                    "accept": ".indd",
                    "required": True,
                },
                {
                    "key": "preset",
                    "label": "학교 프리셋 (config.presets 키)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "delete_sections",
                    "label": "삭제할 섹션 (콤마 구분 마커)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "merge_half_sections",
                    "label": "반쪽 병합할 섹션 (콤마 구분 마커)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "merge_stack_sections",
                    "label": "적층 병합할 섹션 (콤마 구분 마커)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "fix_divider",
                    "label": "간지 스프레드 정렬 (0=끄기)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "merge_mode",
                    "label": "[구] 병합 모드 (ox / arrange) — 하위호환",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "result_name",
                    "label": "결과 파일명 (확장자 제외)",
                    "type": "text",
                    "required": False,
                    "placeholder": "비워두면 원본 파일명_슬림 으로 자동",
                },
            ]
        }

    # ─── parse ─────────────────────────────────────────────────────

    @staticmethod
    def _split_markers(raw):
        """콤마 구분 문자열 → 마커 리스트 (NFC 정규화 + 공백 제거)."""
        if not raw:
            return []
        return [_nfc(s).strip() for s in str(raw).split(",") if s.strip()]

    def _resolve_actions(self, uploaded_files, cfg, log):
        """프리셋 → 개별 입력 → 구 merge_mode 순으로 액션 3종을 합성.

        개별 입력은 프리셋 위에 덮어쓰지 않고 **합집합**이다 (프리셋을 고른
        뒤 한 섹션만 더 빼는 흐름이 자연스럽다). 같은 섹션이 두 액션에
        중복되면 delete > merge_half > merge_stack 우선순위로 하나만 남긴다.
        """
        actions = {"delete": [], "merge_half": [], "merge_stack": []}

        preset_key = (uploaded_files.get("preset") or "").strip()
        if preset_key:
            presets = cfg.get("presets", {})
            if preset_key not in presets:
                raise ValueError(
                    f"알 수 없는 프리셋: {preset_key!r} — "
                    f"{', '.join(sorted(presets)) or '(없음)'} 중 선택"
                )
            preset = presets[preset_key]
            for key in actions:
                actions[key].extend(preset.get(key, []))
            log(f"[프리셋] {preset_key} ({preset.get('label', '')})")

        actions["delete"].extend(
            self._split_markers(uploaded_files.get("delete_sections")))
        actions["merge_half"].extend(
            self._split_markers(uploaded_files.get("merge_half_sections")))
        actions["merge_stack"].extend(
            self._split_markers(uploaded_files.get("merge_stack_sections")))

        # 구 2모드 하위호환 — config.modes[mode].action 으로 합류
        mode = (uploaded_files.get("merge_mode") or "").strip().lower()
        if mode:
            modes = cfg.get("modes", {})
            if mode not in modes:
                raise ValueError(
                    f"알 수 없는 모드: {mode!r} — "
                    f"{', '.join(sorted(modes))} 중 선택"
                )
            mode_cfg = modes[mode]
            act = mode_cfg.get("action", "merge_half")
            actions[act].append(mode_cfg["marker"])
            log(f"[구 모드] {mode} → {act} ({mode_cfg['label']})")

        # 중복 제거 + 액션 간 우선순위 (공백 무시 비교)
        seen = set()
        for key in ("delete", "merge_half", "merge_stack"):
            uniq = []
            for m in actions[key]:
                norm = re.sub(r"\s+", "", _nfc(m))
                if norm in seen:
                    log(f"[경고] 섹션 중복 지정 무시: {m} ({key})")
                    continue
                seen.add(norm)
                uniq.append(m)
            actions[key] = uniq

        if not any(actions.values()):
            raise ValueError(
                "적용할 섹션 액션이 없습니다 — 프리셋을 고르거나 "
                "삭제/병합할 섹션을 지정하세요"
            )
        return actions

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()

        src = uploaded_files.get("src_indd")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(".indd 파일이 업로드되지 않았습니다")

        actions = self._resolve_actions(uploaded_files, cfg, log)
        for key, label in (("delete", "삭제"), ("merge_half", "반쪽 병합"),
                           ("merge_stack", "적층 병합")):
            if actions[key]:
                log(f"[{label}] {', '.join(actions[key])}")

        fix_div_raw = (uploaded_files.get("fix_divider") or "").strip()
        fix_divider = fix_div_raw not in ("0", "false", "off", "no")
        log(f"[간지 정렬] {'ON' if fix_divider else 'OFF'}")

        # 업로드 사본 → job_dir (원본 무접촉)
        src_base = _nfc(os.path.basename(src))
        local_path = os.path.join(job_dir, f"src_{src_base}")
        try:
            safe_copy(src, local_path, log=log)
        except Exception as e:
            raise RuntimeError(f".indd 복사 실패: {e}")
        log(f"[복사] {os.path.basename(local_path)}")

        # 결과 파일명 — 사용자 입력 > 원본 파일명 기반 자동
        result_name = (uploaded_files.get("result_name") or "").strip()
        if not result_name:
            base = src_base
            if base.lower().endswith(".indd"):
                base = base[:-5]
            result_name = f"{base}_슬림"
        log(f"[결과 파일명] {result_name}")

        meta = {
            "src_path": local_path,
            "src_original_name": src_base,
            "actions": actions,
            "fix_divider": fix_divider,
            "result_name": result_name,
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

        output_dir = cfg["output_base"]
        os.makedirs(output_dir, exist_ok=True)

        base = meta["result_name"]
        if base.lower().endswith(".indd"):
            base = base[:-5]
        indd_out = os.path.join(output_dir, f"{base}.indd")
        n = 2
        while os.path.exists(indd_out) and n < 1000:
            indd_out = os.path.join(output_dir, f"{base}_{n}.indd")
            n += 1
        log(f"[출력] {indd_out}")

        # 사본을 출력 경로로 미리 복사 — JSX는 output_indd를 열어 in-place 처리
        shutil.copy2(meta["src_path"], indd_out)

        actions = meta.get("actions") or {}
        settings = {
            "output_indd": indd_out,
            "output_dir": output_dir,
            "delete_sections": actions.get("delete", []),
            "merge_half_sections": actions.get("merge_half", []),
            "merge_stack_sections": actions.get("merge_stack", []),
            "fix_divider_spreads": bool(meta.get("fix_divider", True)),
            "memo_master": cfg.get("memo_master", "M"),
            "unit_style_name": cfg.get("unit_style_name", "단원"),
            "unit_style_group": cfg.get("unit_style_group", "마스터페이지"),
            "stack_drop_y": cfg.get("stack_drop_y", 100),
            "stack_gap": cfg.get("stack_gap", 6.85),
            "master_pairs": cfg.get("master_pairs", [["A", "B"], ["C", "D"]]),
            "protect_masters": cfg.get("protect_masters", ["M", "간지"]),
            "log_path": os.path.join(output_dir, self.log_filename),
            "log_paths": [os.path.join(job_dir, self.log_filename)],
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

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

        # job 전용 로그만 판정 — 출력 폴더 공용 로그(log_path)는 과거 실행분
        # 누적으로 다른 작업 경고가 계상된다 (2026-07-17 merge 계열 감사).
        log_paths = settings.get("log_paths") or []
        log_path = log_paths[0] if log_paths else settings.get("log_path", "")
        merged = 0
        overset = 0
        pages_before = pages_after = 0
        memo_inserted = 0
        if log_path and os.path.exists(log_path):
            try:
                content = open(log_path, encoding="utf-8",
                               errors="ignore").read()
                warn_count = len(re.findall(r"\[경고\]|\[오류\]", content))
                if warn_count > 0:
                    warnings.append(f"JSX 경고/오류 {warn_count}건 (로그 확인)")
                m = re.search(r"병합 그룹: (\d+)개", content)
                if m:
                    merged = int(m.group(1))
                    if merged == 0:
                        warnings.append("처리된 섹션 0개 — 마커 미탐지 확인")
                m = re.search(r"오버셋 스토리: (\d+)건", content)
                if m:
                    overset = int(m.group(1))
                m = re.search(r"변환 전 페이지: (\d+)", content)
                if m:
                    pages_before = int(m.group(1))
                m = re.search(r"변환 후 페이지: (\d+)", content)
                if m:
                    pages_after = int(m.group(1))
                m = re.search(r"간지 정렬: 메모 페이지 (\d+)장 삽입", content)
                if m:
                    memo_inserted = int(m.group(1))
                # 간지 블록이 (왼쪽,오른쪽)으로 정렬됐는지 — 어긋나면 간지
                # 배경이 pasteboard로 나가 제목이 통째로 안 보인다.
                if ("간지 정렬" in content
                        and "간지 블록" not in content.split("간지 정렬")[-1]):
                    warnings.append("간지 정렬 결과 미기록 — 로그 확인")
                if pages_before and pages_after and pages_after >= pages_before:
                    warnings.append(
                        f"페이지 수가 줄지 않음 ({pages_before}p → {pages_after}p)"
                        " — 액션이 적용됐는지 확인")
                # 완료 마커가 아예 없으면 JSX가 끝까지 못 간 것
                if "===== 완료 =====" not in content:
                    warnings.append("완료 마커 없음 — JSX 중단 의심")
            except OSError:
                pass
        else:
            warnings.append("job 로그 없음 — JSX 미실행 의심")

        ok = os.path.exists(indd_out) and len(warnings) == 0

        return {
            "ok": ok,
            "overflow": overset,
            "stories": {
                "처리 섹션": merged,
                "페이지": f"{pages_before} → {pages_after}",
                "메모 페이지 삽입": memo_inserted,
            },
            "pdf_path": None,
            "pdf_paths": [],
            "indd_path": indd_out if os.path.exists(indd_out) else None,
            "warnings": warnings,
        }
