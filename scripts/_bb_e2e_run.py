import os, sys, json, glob, re
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
for line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
from engines.blackbook_v2.parser import parse_files
from engines.blackbook_v2.render import sections_to_plan
from core.base import safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.indesign.runner import run_jsx
from core.inspect import dump_indd, _dump_paragraphs, _norm_typo

case = sys.argv[1] if len(sys.argv) > 1 else "027d750a"
out = os.path.abspath(f"{REPO}/data_corpus/bb_e2e/{case}")
os.makedirs(out, exist_ok=True)
log = lambda m: print(" ", m, flush=True)
sections = parse_files(glob.glob(f"{REPO}/tests/corpus/blackbook/{case}/inputs/*"))
plan = sections_to_plan(sections)
plan_path = f"{out}/render_plan.json"
json.dump(plan, open(plan_path, "w", encoding="utf-8"), ensure_ascii=False)
print("== 조판", flush=True)
tpl = safe_copy_indd(f"{REPO}/data_corpus/template_test/배재1_블랙북.indd", f"{out}/블랙북_v2.indd")
pdf = tpl.replace(".indd", ".pdf")
jsx_log = f"{out}/render.log"
try: os.remove(jsx_log)
except OSError: pass
jsx = build_jsx(f"{REPO}/core/jsx/blackbook_flow.body.jsx",
                {"__TEMPLATE_PATH__": tpl, "__PLAN_PATH__": plan_path,
                 "__OUT_INDD__": tpl, "__OUT_PDF__": pdf}, log_path=jsx_log)
run_jsx(jsx, log, poll_log_path=jsx_log, timeout=1500, completion_marker="블랙북 v2 조판 완료")
print("== 덤프+검수", flush=True)
dump = dump_indd(tpl, f"{out}/typeset_dump.json", log)
_W = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
want = {w.lower() for f in plan["flows"] for u in f["units"] for p in u
        for w in _W.findall(_norm_typo(p["t"]))}
got = set()
for t, s in _dump_paragraphs(dump):
    for w in _W.findall(_norm_typo(t)): got.add(w.lower())
missing = want - got
extra = got - want
rep = {"missing_words": len(missing), "missing_sample": sorted(missing)[:10],
       "extra_words": len(extra), "extra_sample": sorted(extra)[:8],
       "overflow_stories": dump.get("overflow_stories", 0),
       "render_warnings": [l.strip() for l in open(jsx_log, encoding="utf-8") if "[경고]" in l][:10]}
json.dump(rep, open(f"{out}/report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(rep, ensure_ascii=False, indent=1), flush=True)
print("블랙북 v2 E2E:", "✅" if not missing and not rep["overflow_stories"] else "확인 필요", flush=True)
