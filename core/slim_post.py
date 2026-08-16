"""조판 후 슬림 변환 후처리 (조판 시점 섹션 선택).

워크북 계열 조판이 끝난 직후, 산출 .indd 에 slim_merge 엔진의 JSX를 그대로
이어 실행해 섹션을 빼거나 두 페이지를 한 페이지로 병합한다.

**공유 실행기(core/jsx/workbook_flow.body.jsx)는 건드리지 않는다** — 병합
로직은 slim_merge 엔진 JSX 한 곳에만 존재하고, 조판 시점/후처리 두 경로가
같은 코드를 쓴다.

동작 조건: job_dir 에 slim_preset.txt / slim_delete.txt / slim_half.txt /
slim_stack.txt 중 하나라도 있을 때만. 없으면 아무 것도 하지 않는다
(전 엔진 무영향 — 기존 조판 흐름과 완전히 동일).

경로 계약: 대상 .indd 는 job_dir/.settings.json 에서 찾는다
(indd_path → output_indd → indd_output 순).
"""

import json
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
_SLIM_DIR = os.path.join(os.path.dirname(_DIR), "engines", "slim_merge")

_INDD_KEYS = ("indd_path", "output_indd", "indd_output", "output_path")

# 조판 시점 UI 가 넘기는 폼 키 (routes/typeset.py 가 job_dir/*.txt 로 저장)
FORM_KEYS = ("slim_preset", "slim_delete", "slim_half", "slim_stack",
             "slim_fix_divider")


def _read(job_dir, key):
    path = os.path.join(job_dir, f"{key}.txt")
    if not os.path.exists(path):
        return ""
    try:
        return open(path, encoding="utf-8").read().strip()
    except OSError:
        return ""


def _split(raw):
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


def _load_slim_config():
    from core.paths import resolve_config
    with open(os.path.join(_SLIM_DIR, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["output_base"])


def _target_indd(job_dir):
    settings_path = os.path.join(job_dir, ".settings.json")
    if not os.path.exists(settings_path):
        return ""
    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError):
        return ""
    for key in _INDD_KEYS:
        val = settings.get(key)
        if val and os.path.exists(val):
            return val
    return ""


def wanted(job_dir):
    """이 job 에 슬림 후처리가 요청됐는지."""
    return any(_read(job_dir, k) for k in FORM_KEYS[:4])


def resolve_actions(job_dir, cfg, log):
    """프리셋 + 개별 지정 → 액션 3종 (slim_merge 엔진과 같은 규칙)."""
    actions = {"delete": [], "merge_half": [], "merge_stack": []}

    preset_key = _read(job_dir, "slim_preset")
    if preset_key:
        preset = cfg.get("presets", {}).get(preset_key)
        if not preset:
            log(f"[슬림] [경고] 알 수 없는 프리셋: {preset_key} — 무시")
        else:
            for key in actions:
                actions[key].extend(preset.get(key, []))
            log(f"[슬림] 프리셋 {preset_key} ({preset.get('label', '')})")

    actions["delete"].extend(_split(_read(job_dir, "slim_delete")))
    actions["merge_half"].extend(_split(_read(job_dir, "slim_half")))
    actions["merge_stack"].extend(_split(_read(job_dir, "slim_stack")))

    seen = set()
    for key in ("delete", "merge_half", "merge_stack"):
        uniq = []
        for m in actions[key]:
            norm = re.sub(r"\s+", "", m)
            if norm in seen:
                continue
            seen.add(norm)
            uniq.append(m)
        actions[key] = uniq
    return actions


def run_slim_postprocess(engine, job_dir, log, cancel_check=None):
    """조판 산출 .indd 에 슬림 변환을 적용. 요청이 없으면 no-op."""
    if not wanted(job_dir):
        return None

    indd_path = _target_indd(job_dir)
    if not indd_path:
        log("[슬림] [경고] 대상 .indd 를 찾지 못했습니다 — 후처리 생략")
        return None

    cfg = _load_slim_config()
    actions = resolve_actions(job_dir, cfg, log)
    if not any(actions.values()):
        log("[슬림] 적용할 섹션 액션이 없습니다 — 후처리 생략")
        return None

    for key, label in (("delete", "삭제"), ("merge_half", "반쪽 병합"),
                       ("merge_stack", "적층 병합")):
        if actions[key]:
            log(f"[슬림] {label}: {', '.join(actions[key])}")

    fix_raw = _read(job_dir, "slim_fix_divider")
    fix_divider = fix_raw not in ("0", "false", "off", "no")
    log(f"[슬림] 간지 정렬 {'ON' if fix_divider else 'OFF'}")

    log_name = "slim_log.txt"
    slim_log = os.path.join(job_dir, log_name)
    settings = {
        "output_indd": indd_path,
        "output_dir": os.path.dirname(indd_path),
        "delete_sections": actions["delete"],
        "merge_half_sections": actions["merge_half"],
        "merge_stack_sections": actions["merge_stack"],
        "fix_divider_spreads": fix_divider,
        "memo_master": cfg.get("memo_master", "M"),
        "unit_style_name": cfg.get("unit_style_name", "단원"),
        "unit_style_group": cfg.get("unit_style_group", "마스터페이지"),
        "stack_drop_y": cfg.get("stack_drop_y", 100),
        "stack_gap": cfg.get("stack_gap", 6.85),
        "master_pairs": cfg.get("master_pairs", [["A", "B"], ["C", "D"]]),
        "protect_masters": cfg.get("protect_masters", ["M", "간지"]),
        "log_path": slim_log,
        "log_paths": [],
    }
    settings_path = os.path.join(job_dir, ".slim_settings.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    jsx_src = os.path.join(_SLIM_DIR, "jsx", "run.jsx")
    with open(jsx_src, encoding="utf-8") as f:
        code = f.read()
    code = code.replace("__SETTINGS_PATH__", settings_path)
    jsx_dst = os.path.join(job_dir, "slim_run.jsx")
    with open(jsx_dst, "w", encoding="utf-8") as f:
        f.write(code)

    log(f"[슬림] 후처리 시작 — {os.path.basename(indd_path)}")
    from core.indesign import runner
    # PDF export 가 없어 runner 기본 완료 휴리스틱에 안 걸린다 →
    # completion_marker 필수. 페이지 삭제는 페이지당 수십 초라 stall 여유 필요.
    runner.run_jsx(jsx_dst, log, poll_log_path=slim_log, timeout=1800,
                   stall_limit=900, completion_marker="===== 완료 =====",
                   cancel_check=cancel_check)

    summary = {"indd_path": indd_path, "actions": actions}
    if os.path.exists(slim_log):
        try:
            content = open(slim_log, encoding="utf-8", errors="ignore").read()
            m = re.search(r"변환 전 페이지: (\d+)", content)
            before = int(m.group(1)) if m else 0
            m = re.search(r"변환 후 페이지: (\d+)", content)
            after = int(m.group(1)) if m else 0
            summary["pages"] = (before, after)
            warns = len(re.findall(r"\[경고\]|\[오류\]", content))
            summary["warnings"] = warns
            log(f"[슬림] 완료 — {before}p → {after}p"
                + (f" (경고 {warns}건)" if warns else ""))
        except OSError:
            pass
    return summary
