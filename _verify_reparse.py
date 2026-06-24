import os,sys,time
os.environ["_REUSE_EXTRACTED"]="1"
BASE="/Users/nhj/dev/yone-design-web"; sys.path.insert(0,BASE)
envp=os.path.join(BASE,".env")
if os.path.exists(envp):
    for line in open(envp,encoding="utf-8"):
        line=line.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
import config
from engines.final.engine import FinalEngine
def log(m): print(time.strftime("%H:%M:%S "),str(m),flush=True)
try: FinalEngine().parse({},os.path.join(BASE,"jobs","verify_e0ab94a0"),log)
except Exception as ex:
    import traceback; log("ERR "+str(ex)); log(traceback.format_exc())
