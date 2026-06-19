import os,sys,json,time,uuid
BASE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,BASE)
envp=os.path.join(BASE,".env")
for line in open(envp,encoding="utf-8"):
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
import config
from engines.final.engine import FinalEngine
school,grade,exam=sys.argv[1],sys.argv[2],sys.argv[3]
eng=FinalEngine()
jd=os.path.join(config.JOBS_DIR,"parse_"+uuid.uuid4().hex[:8]); os.makedirs(os.path.join(jd,"uploads"),exist_ok=True)
open(jd+"/school.txt","w").write(school);open(jd+"/grade.txt","w").write(grade);open(jd+"/exam_period.txt","w").write(exam)
def log(m):print(time.strftime("%H:%M:%S "),m,flush=True)
jp=eng.parse({},jd,log)
print("JOB_DIR="+jd); print("JSON="+jp)
