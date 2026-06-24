import os,sys,time
os.environ["_REUSE_EXTRACTED"]="1"
BASE="/Users/nhj/dev/yone-design-web"; sys.path.insert(0,BASE)
envp=os.path.join(BASE,".env")
if os.path.exists(envp):
    for line in open(envp,encoding="utf-8"):
        l=line.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
import config, json
from engines.final.engine import FinalEngine
jd=os.path.join(BASE,"jobs","verify_e0ab94a0")
def log(m): print(time.strftime("%H:%M:%S "),str(m),flush=True)
eng=FinalEngine()
jp=eng.parse({},jd,log); eng.prepare_jsx(jp,jd,log); eng.run_indesign(jd,log)
r=eng.verify(jd,log); log("RESULT_OVERFLOW="+str(r.get('overflow'))); log("ALLDONE")
