# -*- coding: utf-8 -*-
"""기존 완성 .indd 에서 (섹션, 코드) 칸 내용을 뽑아 보충 데이터(fill)로 만든다.

원고가 아예 없는 칸(옛 기출의 어법하단, 유실된 어휘선택 등)을 이전 산출물에서
조달하는 표준 경로. 결과는 `merge_select.load_fill` 이 읽는 형식으로 저장된다.

스펙 파일(JSON) 예:
    {
      "out": "engines/workbook_select/fill/hanyoung1_gang11.json",
      "sources": [
        {"indd": "/…/한영1_워크북01_신규3_v2.indd",
         "mode": "marker",
         "items": [{"step": "step1_a1", "pages": [4,5],
                    "marker_map": {"20":"161131","30":"190633","40":"210632"}},
                   {"step": "step1_a1_2", "pages": [6,7],
                    "marker_map": {"20":"161131","30":"190633","40":"210632"}}]},
        {"indd": "/…/세로중간본.indd",
         "mode": "region",
         "items": [{"step": "step2_a1_btm", "page": 52,  "code": "220632"},
                   {"step": "step2_a1_btm", "page": 137, "code": "220932"},
                   {"step": "step2_a1_btm", "page": 196, "code": "220633"}]}
      ]
    }

mode
    marker : 프레임 첫 단락이 "[NN]" 마커인 것을 지문 1개로 본다 (가로판)
    region : 페이지 하단 영역(y1>=150) 프레임을 모아 1개 칸으로 본다 (세로판)

⚠ 밑줄은 직접 서식이 아니라 **문자스타일**로 걸려 있는 경우가 많다.
   문자 단위로 appliedCharacterStyle 이름까지 봐야 한다 (이 도구는 그렇게 한다).
⚠ 소스 .indd 는 열기만 하고 저장하지 않는다.

사용:
    python3 scripts/wbsel_extract_fill.py <spec.json>
    python3 scripts/wbsel_extract_fill.py <spec.json> --dry   (스펙 검증만)
"""
import argparse
import json
import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JSX = os.path.join(_ROOT, "engines", "workbook_select", "jsx",
                    "extract_fill.jsx")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    out = spec.get("out")
    if not out:
        print("spec 에 out 경로가 없습니다")
        return 2

    n = 0
    for src in spec.get("sources") or []:
        if not os.path.exists(src.get("indd", "")):
            print("소스 없음: %s" % src.get("indd"))
            return 2
        for it in src.get("items") or []:
            n += len(it.get("marker_map") or {}) or 1
    print("스펙 OK — 소스 %d개 / 칸 %d개 → %s"
          % (len(spec.get("sources") or []), n, out))
    if args.dry:
        return 0

    log_path = os.path.join(_ROOT, "jobs", "extract_fill_로그.txt")
    spec_path = os.path.abspath(args.spec)
    src = open(_JSX, encoding="utf-8").read()
    src = src.replace("__SPEC_PATH__", spec_path)
    src = src.replace("__LOG_PATH__", log_path)
    run_jsx = os.path.join(_ROOT, "jobs", "extract_fill_run.jsx")
    with open(run_jsx, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        os.remove(log_path)
    except OSError:
        pass

    print("InDesign 실행 중… (소스 문서 크기에 따라 수 분)")
    subprocess.Popen([
        "osascript", "-e",
        'tell application id "com.adobe.InDesign" to do script '
        '(POSIX file "%s") language javascript' % run_jsx,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # AppleEvent 는 먼저 타임아웃될 수 있다 — 로그 파일로 완료를 판정한다
    deadline = time.time() + 1800
    seen = 0
    while time.time() < deadline:
        time.sleep(5)
        if not os.path.exists(log_path):
            continue
        txt = open(log_path, encoding="utf-8", errors="ignore").read()
        lines = txt.split("\n")
        for ln in lines[seen:]:
            if ln.strip():
                print("  " + ln)
        seen = len(lines)
        if "===== 추출 완료 =====" in txt:
            break
        if "[오류]" in txt:
            return 1
    if os.path.exists(out):
        d = json.load(open(out, encoding="utf-8"))
        total = sum(len(v) for v in d.values())
        print("\n보충 데이터 저장: %s (%d칸)" % (out, total))
        for step in sorted(d):
            for code in sorted(d[step]):
                e = d[step][code]
                uls = sum(1 for p in e["paras"] for r in p["runs"]
                          if r.get("ul"))
                print("  %-14s %s  단락%d 밑줄%d %s"
                      % (step, code, len(e["paras"]), uls,
                         ("발문: " + e["prompt"][:40]) if e.get("prompt")
                         else ""))
        return 0
    print("출력 파일이 생기지 않았습니다 — 로그 확인: %s" % log_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
