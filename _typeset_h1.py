import os,sys,time
os.environ["_REUSE_EXTRACTED"]="1"
BASE="/Users/nhj/dev/yone-design-web"; sys.path.insert(0,BASE)
envp=os.path.join(BASE,".env")
if os.path.exists(envp):
    for line in open(envp,encoding="utf-8"):
        line=line.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
import config, json
from engines.final.engine import FinalEngine
jd=os.path.join(BASE,"jobs","verify_e0ab94a0")
def log(m): print(time.strftime("%H:%M:%S "),str(m),flush=True)
eng=FinalEngine()
try:
    jp=eng.parse({},jd,log); eng.prepare_jsx(jp,jd,log); eng.run_indesign(jd,log)
    r=eng.verify(jd,log); log("RESULT "+json.dumps(r,ensure_ascii=False)[:600]); log("DONE")
except Exception as e:
    import traceback; log("ERROR "+str(e)); log(traceback.format_exc()); sys.exit(1)
