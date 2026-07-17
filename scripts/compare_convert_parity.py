#!/usr/bin/env python3
"""세로 변환 파리티 대조 (W27) — 웹 엔진 산출물 vs 수동 ConvertToVertical.jsx 실물.

수동 산출물(GDrive의 고N_YY년_M월_세로(C).indd)을 읽기 전용 사본으로 dump하고,
웹 엔진 E2E 산출물 dump와 구조 대조한다 (v2 전환 교훈: 파리티의 진실은
실물 출력 dump 대조).

대조 항목:
  1. 페이지 수
  2. 지문 코드 블록 시퀀스 (페이지 순서의 코드 등장 순서/그룹화 — 사이클 구조)
  3. 본문 라인셋 (len>=25 정규화) 차집합 양방향

주의: 수동 세로(C)는 변환 후 사람 마무리(간지 문구 입력 등)가 더해졌을 수
있어 완전 일치가 아니라 "구조 일치 + 차이의 설명 가능성"을 판정 기준으로 한다.

사용:
  python3 scripts/compare_convert_parity.py \
      [수동세로.indd GDrive경로] [웹출력 dump json 경로]
  (인자 생략 시 고2_23년_6월 기본 쌍)
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

OUT = os.path.join(REPO, "data_corpus", "tools_onboard", "convert_vert")

_DEFAULT_MANUAL = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
    "콘텐츠 관리/내신대비/인디자인 파일/워크북/모의고사/고2/"
    "고2_23년_6월_세로(C).indd")
_DEFAULT_WEB_DUMP = os.path.join(OUT, "job", "typeset_dump.json")


def _lines(dump, min_len=25):
    from engines.convert_to_vertical.engine import _norm_line
    got = set()
    for st in dump.get("stories", []):
        for para in st.get("paragraphs", []):
            t = _norm_line(para.get("t"))
            if len(t) >= min_len:
                got.add(t)
    return got


def main():
    manual_indd = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_MANUAL
    web_dump_path = sys.argv[2] if len(sys.argv) > 2 else _DEFAULT_WEB_DUMP

    from core.inspect import dump_indd
    from engines.final.extractor import _gdrive_safe_copy
    from engines.convert_to_vertical.engine import (
        page_code_sequence, contiguous_blocks)

    log = lambda m: print(f"  {m}", flush=True)
    ref_dir = os.path.join(OUT, "manual_ref")
    os.makedirs(ref_dir, exist_ok=True)

    # 수동 산출물 읽기 전용 사본 → dump (원본 무접촉)
    local_manual = os.path.join(ref_dir, os.path.basename(manual_indd))
    if not os.path.exists(local_manual):
        _gdrive_safe_copy(manual_indd, local_manual, log=log)
    manual_dump_path = os.path.join(ref_dir, "manual_dump.json")
    if os.path.exists(manual_dump_path):
        manual_dump = json.load(open(manual_dump_path, encoding="utf-8"))
    else:
        manual_dump = dump_indd(local_manual, manual_dump_path, log,
                                timeout=1800)

    web_dump = json.load(open(web_dump_path, encoding="utf-8"))

    report = {"manual_indd": manual_indd, "web_dump": web_dump_path}

    # 1. 페이지 수
    report["pages"] = {"manual": manual_dump.get("page_count"),
                       "web": web_dump.get("page_count")}

    # 2. 코드 블록 시퀀스
    m_seq = page_code_sequence(manual_dump)
    w_seq = page_code_sequence(web_dump)
    m_blocks = contiguous_blocks(m_seq)
    w_blocks = contiguous_blocks(w_seq)
    report["code_blocks"] = {
        "manual": m_blocks, "web": w_blocks,
        "identical": m_blocks == w_blocks,
    }

    # 3. 라인셋 차집합
    m_lines = _lines(manual_dump)
    w_lines = _lines(web_dump)
    only_manual = sorted(m_lines - w_lines)
    only_web = sorted(w_lines - m_lines)
    report["lines"] = {
        "manual_total": len(m_lines), "web_total": len(w_lines),
        "only_manual": len(only_manual), "only_web": len(only_web),
        "only_manual_sample": only_manual[:20],
        "only_web_sample": only_web[:20],
    }

    # 4. 오버플로우
    report["overflow"] = {
        "manual": manual_dump.get("overflow_stories"),
        "web": web_dump.get("overflow_stories"),
    }

    out_path = os.path.join(OUT, "parity_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print("\n===== 파리티 리포트 =====")
    print(f"페이지: manual {report['pages']['manual']} / "
          f"web {report['pages']['web']}")
    print(f"코드 블록 동일: {report['code_blocks']['identical']} "
          f"(manual {len(m_blocks)} / web {len(w_blocks)})")
    print(f"라인: manual-only {len(only_manual)} / web-only {len(only_web)} "
          f"(전체 manual {len(m_lines)} / web {len(w_lines)})")
    print(f"오버플로우: manual {report['overflow']['manual']} / "
          f"web {report['overflow']['web']}")
    print(f"리포트: {out_path}")


if __name__ == "__main__":
    main()
