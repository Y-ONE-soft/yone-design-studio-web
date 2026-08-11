# -*- coding: utf-8 -*-
"""선택 워크북 파서/병합 골든 회귀 하네스 — InDesign 무접촉.

목적: 파서·병합 코드를 고칠 때 **다른 회차/다른 섹션이 조용히 깨지는 것**을
막는다. 2026-08-08 세션에서 수정 9건마다 수동으로 대조표를 만들어야 했는데,
그 대조를 스크립트로 굳힌 것이다.

동작
    capture <label> --gang 11    로컬 원고 사본 + content.json 을 baseline 으로 동결
    check   [label]              현 코드로 다시 파싱해 섹션별 해시 대조
    list                         baseline 목록

hermetic 보장: capture 시 회차 원고를 baseline 폴더로 복사해 두고, check 는
그 사본만 읽는다(GDrive 접근 없음 → 원고가 바뀌어도 결과가 흔들리지 않는다).

⚠ baseline 오염 주의 — 지금 산출물에는 "틀렸지만 안 들킨" 것이 섞여 있을 수
   있다. baseline 은 정답이 아니라 **현행 기록(characterization)** 이다.
   의도한 수정으로 DIFF 가 나면 내용을 눈으로 확인한 뒤 accept 한다.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from engines.workbook.engine import _load_config as _wb_config  # noqa: E402
from engines.workbook.parser import parse_manuscript_folder  # noqa: E402

_BASE = os.path.join(_ROOT, "scripts", "wbsel_baselines")


def _h(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]


def _parse_dir(d):
    cfg = _wb_config()
    return parse_manuscript_folder(d, cfg, 1, 0, 0, log=lambda m: None)


def _sig(content):
    """섹션별 해시 + 단락 수 — 비교용 요약."""
    out = {}
    for k, st in (content.get("steps") or {}).items():
        paras = st.get("paragraphs") if isinstance(st, dict) else st
        if not isinstance(paras, list):
            paras = []
        out[k] = {"hash": _h(st), "paras": len(paras)}
    return out


def cmd_capture(args):
    """현 job 의 ms_* 원고 폴더를 baseline 으로 동결."""
    src_job = args.job
    if not os.path.isdir(src_job):
        src_job = os.path.join(_ROOT, "jobs", args.job)
    if not os.path.isdir(src_job):
        print("job 폴더 없음: %s" % args.job)
        return 2
    dst = os.path.join(_BASE, args.label)
    if os.path.exists(dst) and not args.force:
        print("이미 있음: %s (--force 로 덮어쓰기)" % dst)
        return 2
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)

    sigs, n = {}, 0
    for name in sorted(os.listdir(src_job)):
        if not name.startswith("ms_"):
            continue
        s = os.path.join(src_job, name)
        if not os.path.isdir(s):
            continue
        shutil.copytree(s, os.path.join(dst, name))
        sigs[name] = _sig(_parse_dir(os.path.join(dst, name)))
        n += 1
        print("  %s 동결 (%d섹션)" % (name, len(sigs[name])))
    if not n:
        print("ms_* 원고 폴더가 없습니다 — parse 를 먼저 돌리세요")
        shutil.rmtree(dst, ignore_errors=True)
        return 2
    with open(os.path.join(dst, "baseline.json"), "w", encoding="utf-8") as f:
        json.dump(sigs, f, ensure_ascii=False, indent=1)
    print("baseline 저장: %s (원고 폴더 %d개)" % (dst, n))
    return 0


def cmd_check(args):
    labels = [args.label] if args.label else sorted(
        d for d in os.listdir(_BASE) if os.path.isdir(os.path.join(_BASE, d))
    ) if os.path.isdir(_BASE) else []
    if not labels:
        print("baseline 이 없습니다 — capture 를 먼저 하세요")
        return 2
    bad = 0
    for label in labels:
        d = os.path.join(_BASE, label)
        bfile = os.path.join(d, "baseline.json")
        if not os.path.exists(bfile):
            continue
        base = json.load(open(bfile, encoding="utf-8"))
        print("===== %s =====" % label)
        for ms, expect in sorted(base.items()):
            got = _sig(_parse_dir(os.path.join(d, ms)))
            diffs = []
            for step in sorted(set(expect) | set(got)):
                e, g = expect.get(step), got.get(step)
                if e is None:
                    diffs.append("+%s(신규 %d단락)" % (step, g["paras"]))
                elif g is None:
                    diffs.append("-%s(사라짐)" % step)
                elif e["hash"] != g["hash"]:
                    diffs.append("%s(%d→%d단락)"
                                 % (step, e["paras"], g["paras"]))
            if diffs:
                bad += 1
                print("  %-14s **DIFF** %s" % (ms, ", ".join(diffs)))
            else:
                print("  %-14s 동일 (%d섹션)" % (ms, len(got)))
    print("\n%s" % ("회귀 감지 — 위 DIFF 내용을 확인하고, 의도한 변경이면 "
                   "accept 하세요" if bad else "전부 동일 — 회귀 없음"))
    return 1 if bad else 0


def cmd_accept(args):
    d = os.path.join(_BASE, args.label)
    if not os.path.isdir(d):
        print("baseline 없음: %s" % args.label)
        return 2
    sigs = {}
    for name in sorted(os.listdir(d)):
        if name.startswith("ms_") and os.path.isdir(os.path.join(d, name)):
            sigs[name] = _sig(_parse_dir(os.path.join(d, name)))
    with open(os.path.join(d, "baseline.json"), "w", encoding="utf-8") as f:
        json.dump(sigs, f, ensure_ascii=False, indent=1)
    print("현행을 baseline 으로 갱신: %s" % args.label)
    return 0


def cmd_list(_args):
    if not os.path.isdir(_BASE):
        print("baseline 없음")
        return 0
    for d in sorted(os.listdir(_BASE)):
        p = os.path.join(_BASE, d, "baseline.json")
        if os.path.exists(p):
            b = json.load(open(p, encoding="utf-8"))
            print("  %-20s 원고폴더 %d개" % (d, len(b)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture"); c.add_argument("label")
    c.add_argument("--job", required=True); c.add_argument("--force",
                                                           action="store_true")
    c.set_defaults(fn=cmd_capture)
    c = sub.add_parser("check"); c.add_argument("label", nargs="?")
    c.set_defaults(fn=cmd_check)
    c = sub.add_parser("accept"); c.add_argument("label")
    c.set_defaults(fn=cmd_accept)
    c = sub.add_parser("list"); c.set_defaults(fn=cmd_list)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
