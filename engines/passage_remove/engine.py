# -*- coding: utf-8 -*-
"""지문 제거 엔진 (W26) — 조판된 워크북 전체(C)에서 선택 지문 제거.

흐름:
  1. (엔진 밖) /api/passage-remove/inventory — .indd 사본 → dump →
     build_inventory(매처 그룹핑) → inventory_id 발급
  2. parse: inventory_id + 선택 그룹(gid CSV) → content.json
  3. prepare_jsx: 작업 사본 복사 + 제거 스펙 + passage_remove.body.jsx 빌드
  4. run_indesign: 러너 (stall_limit 2700 — 대형 C 문서 save/export)
  5. verify: 출력 재덤프 — 제거 지문 판별 라인 잔존 0 + 잔존 유닛 라인
     전량 보존 + 오버플로우/페이지/PDF/[경고]
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid

from config import JOBS_DIR
from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from core.indesign.jsxbuild import build_jsx

_DIR = os.path.dirname(os.path.abspath(__file__))
_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                     "core", "jsx", "passage_remove.body.jsx")

# 인벤토리 저장소 (dump/원본 사본/inventory.json)
INVENTORY_BASE = os.path.join(JOBS_DIR, "passage_remove_inventory")


def _load_config():
    with open(os.path.join(_DIR, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["output_base"])


def inventory_dir(inventory_id):
    """인벤토리 ID → 디렉터리 경로 (경로 탈출 방지)."""
    inv_id = re.sub(r"[^0-9a-f]", "", str(inventory_id))[:32]
    if not inv_id:
        raise ValueError("잘못된 inventory_id")
    return os.path.join(INVENTORY_BASE, inv_id)


def new_inventory_id():
    return uuid.uuid4().hex[:12]


def create_inventory(src_indd, log, base_dir=None):
    """소스 .indd → 사본 복사 + dump + 인벤토리 생성.

    반환: (inventory_id, inventory dict). InDesign 필요 (dump).
    원본은 절대 수정하지 않는다 — 사본에서 dump하고, 제거도 사본의
    또 다른 사본에서 실행된다.
    """
    from core.inspect import dump_indd
    from engines.passage_remove.inventory import build_inventory

    inv_id = new_inventory_id()
    d = os.path.join(base_dir or INVENTORY_BASE, inv_id)
    os.makedirs(d, exist_ok=True)
    work = safe_copy_indd(src_indd, os.path.join(d, "source.indd"))
    log(f"[인벤토리] 사본 복사: {os.path.basename(src_indd)}")
    dump_path = os.path.join(d, "dump.json")
    dump = dump_indd(work, dump_path, log, timeout=1200)
    inv = build_inventory(dump, log)
    inv["source_indd"] = work
    inv["source_name"] = os.path.basename(src_indd)
    inv["dump_path"] = dump_path
    inv["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(d, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False)
    return inv_id, inv


def load_inventory(inventory_id, base_dir=None):
    d = (os.path.join(base_dir, re.sub(r"[^0-9a-f]", "", str(inventory_id))[:32])
         if base_dir else inventory_dir(inventory_id))
    path = os.path.join(d, "inventory.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            "인벤토리가 없습니다 — 지문 목록 추출을 먼저 실행하세요")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class PassageRemoveEngine(BaseEngine):
    """워크북 전체(C) 지문 제거 — [가공] > 편집."""

    @property
    def material_id(self):
        return "passage_remove"

    @property
    def display_name(self):
        return "워크북 지문 제거"

    @property
    def template_name(self):
        return "typeset_passage_remove.html"

    @property
    def jsx_timeout(self):
        return 3600

    @property
    def upload_spec(self):
        return {
            "slots": [
                {"key": "inventory_id", "label": "인벤토리 ID",
                 "type": "text", "required": True},
                {"key": "selected", "label": "제거할 지문 그룹 (gid CSV)",
                 "type": "text", "required": True},
                {"key": "result_name", "label": "결과 파일명 (선택)",
                 "type": "text", "required": False},
            ]
        }

    def _config(self):
        return _load_config()

    # ── 1단계: parse ────────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        inv_id = (uploaded_files.get("inventory_id") or "").strip()
        selected_raw = (uploaded_files.get("selected") or "").strip()
        inv = load_inventory(inv_id)
        if not os.path.exists(inv["source_indd"]):
            raise FileNotFoundError(
                "인벤토리 원본 사본이 없습니다: " + inv["source_indd"])
        selected = sorted({int(tok) for tok in
                           re.split(r"[,\s]+", selected_raw) if tok.strip()})
        if not selected:
            raise ValueError("제거할 지문 그룹이 선택되지 않았습니다")
        by_gid = {g["gid"]: g for g in inv["groups"]}
        unknown = [g for g in selected if g not in by_gid]
        if unknown:
            raise ValueError("존재하지 않는 그룹: %s" % unknown)
        labels = [by_gid[g].get("label") or ("(그룹 %d)" % g)
                  for g in selected]
        log(f"[지문제거] {inv['source_name']} — 제거 대상 {len(selected)}개 지문: "
            + ", ".join(labels))

        content = {
            "inventory_id": inv_id,
            "selected": selected,
            "source_name": inv["source_name"],
        }
        path = os.path.join(job_dir, "content.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        return path

    # ── 2단계: prepare_jsx ──────────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.passage_remove.inventory import build_removal_spec

        cfg = self._config()
        content = json.load(open(json_path, encoding="utf-8"))
        inv = load_inventory(content["inventory_id"])
        spec = build_removal_spec(inv, content["selected"])
        n_units = sum(len(s["remove"]) for s in spec["stories"])
        log(f"[지문제거] 제거 유닛 {n_units}개 / 영향 스토리 "
            f"{len(spec['stories'])}개 / 번호 정리 {spec['clear_numbers']}")
        if n_units == 0:
            raise ValueError("제거할 유닛이 0개입니다 — 선택 그룹 확인")

        spec_path = os.path.abspath(os.path.join(job_dir, "removal_spec.json"))
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)

        # 출력 파일명
        result_name = self._read_meta_str(job_dir, "result_name", "")
        base = os.path.splitext(inv["source_name"])[0]
        out_name = (result_name or (base + "_지문제거")) + ".indd"
        out_dir = cfg["output_base"]
        os.makedirs(out_dir, exist_ok=True)
        # 작업 사본 = 인벤토리 사본의 사본 (스토리 순서 보존 — dump와 동일 파일)
        indd_path = safe_copy_indd(inv["source_indd"],
                                   os.path.join(out_dir, out_name))
        log(f"[지문제거] 작업 사본: {os.path.basename(indd_path)}")
        pdf_path = indd_path[:-5] + ".pdf"

        jsx_log = os.path.abspath(os.path.join(job_dir, "조판_로그.txt"))
        jsx_path = build_jsx(
            _BODY,
            {"__DOC_PATH__": indd_path, "__SPEC_PATH__": spec_path,
             "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))

        settings = {"engine": self.material_id,
                    "inventory_id": content["inventory_id"],
                    "indd_path": indd_path, "pdf_path": pdf_path,
                    "jsx_path": jsx_path, "log_path": jsx_log,
                    "json_path": json_path, "spec_path": spec_path,
                    "output_dir": job_dir}
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return os.path.join(job_dir, ".settings.json")

    def _read_meta_str(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    # ── 3단계: run_indesign ─────────────────────────────────────────────────

    def run_indesign(self, job_dir, log):
        from core.indesign.runner import run_jsx
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        # 재실행 안전 (W7 stale 완료마커 교훈)
        try:
            os.remove(settings["log_path"])
        except OSError:
            pass
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="지문 제거 완료",
                stall_limit=2700)

    # ── 4단계: verify ───────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        from engines.passage_remove.inventory import (
            verify_line_sets, norm_line)

        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        content = json.load(open(settings["json_path"], encoding="utf-8"))
        spec = json.load(open(settings["spec_path"], encoding="utf-8"))
        inv = load_inventory(settings["inventory_id"])
        with open(inv["dump_path"], encoding="utf-8") as f:
            src_dump = json.load(f)

        out_dump = dump_indd(settings["indd_path"],
                             os.path.join(job_dir, "typeset_dump.json"), log)
        got_lines = set()
        overflow = 0
        for st in out_dump["stories"]:
            for p in st["paragraphs"]:
                t = norm_line(p["t"])
                if len(t) >= 25:
                    got_lines.add(t)
            if st.get("overflow"):
                overflow += 1

        removed_only, kept_lines = verify_line_sets(
            inv, src_dump, spec["removed_uids"])

        warnings = []
        ok = True

        # (a) 제거 지문 잔존 0
        leftover = removed_only & got_lines
        if leftover:
            ok = False
            warnings.append(
                f"❌ 제거 지문 잔존 {len(leftover)}라인: "
                + " | ".join(sorted(leftover)[:3]))

        # (b) 잔존 유닛 보존 (과잉 삭제 감지 — 배정 경계 오류 방어)
        missing = kept_lines - got_lines
        if missing:
            ok = False
            warnings.append(
                f"❌ 잔존 유닛 내용 누락 {len(missing)}라인: "
                + " | ".join(sorted(missing)[:3]))

        # (c) 오버플로우 — 원본 대비 증가만 문제
        src_overflow = src_dump.get("overflow_stories", 0)
        if overflow > src_overflow:
            ok = False
            warnings.append(f"❌ 오버플로우 증가: {src_overflow} → {overflow}")
        elif overflow:
            warnings.append(f"⚠️ 오버플로우 스토리 {overflow}개 (원본에도 존재)")

        # (d) 페이지 정리 리포트
        src_pages = src_dump.get("page_count") or 0
        out_pages = out_dump.get("page_count") or 0
        log(f"[검수] 페이지 {src_pages} → {out_pages}")
        empty_pages = [p["p"] for p in (out_dump.get("pages") or [])
                       if p.get("empty")]
        if empty_pages:
            warnings.append("⚠️ 빈 페이지 잔존: " + ", ".join(empty_pages[:8]))
        stale = [p["p"] for p in (out_dump.get("stale_pages") or [])]
        if stale:
            warnings.append("⚠️ 본문 없는 잔여 페이지(장식만): "
                            + ", ".join(stale[:8]))

        # (e) PDF
        pdf_ok = os.path.exists(settings["pdf_path"])
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")

        # (f) 실행 로그 [경고] — 접두 불일치 보류 등은 검수 실패로 승격
        render_warns = []
        try:
            with open(settings["log_path"], encoding="utf-8") as f:
                render_warns = [l.strip() for l in f if "[경고]" in l]
        except OSError:
            pass
        for w in render_warns[:8]:
            warnings.append(f"⚠️ {w}")
        if any("접두 불일치" in w or "범위 밖" in w for w in render_warns):
            ok = False
            warnings.append("❌ 제거 범위 보류 발생 — 인벤토리 재추출 필요")

        log(f"[검수] 제거 {len(content['selected'])}그룹 / 잔존 {len(leftover)} / "
            f"누락 {len(missing)} / 오버플로우 {overflow} / "
            f"PDF {'OK' if pdf_ok else '실패'}")
        return {
            "ok": ok,
            "overflow": overflow,
            "stories": {},
            "pdf_path": settings["pdf_path"] if pdf_ok else None,
            "indd_path": settings["indd_path"],
            "warnings": warnings,
        }
