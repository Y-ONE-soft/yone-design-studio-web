# -*- coding: utf-8 -*-
import sys,os,unicodedata,re,json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from hwpx_paras import paragraphs

CHO='①②③④⑤'
def rtext(runs): return ''.join(r['t'] for r in runs)
def kratio(t):
    t=t.strip()
    if not t: return 0
    return sum(1 for c in t if '가'<=c<='힣')/len(t)
def aratio(t):
    t=t.strip()
    if not t: return 0
    return sum(1 for c in t if ord(c)<128)/len(t)

def is_type_header(t):
    t=t.strip()
    if not t or len(t)>16: return False
    if t[0] in '[<①②③④⑤ⓐⓑⓒⓓⓔ↓*(': return False
    if not re.search(r'[가-힣]',t): return False
    KNOWN={'대의 파악','대의파악','어법','어휘','빈칸 추론','빈칸추론','무관한 문장','무관한문장',
       '글의 순서','순서 배열','순서배열','순서','문장 삽입','문장삽입','요약문','함축','장문',
       '세부 내용 파악','세부내용파악','지칭 추론','지칭추론'}
    if t in KNOWN: return True
    if re.match(r'^(서술형|함축|장문|복합|영작|어법·?어휘|1지문|밑줄 어휘)', t): return True
    return False

STEM_KW=re.compile(r'(다음|주어진 글|주어진 표현|윗글|위 글|글의 흐름|밑줄 친|필자|다음 내용|다음 밑줄|다음 ⓐ|다음 ⓕ|Molly|Bill|.{0,10}에 관한|^\s*\([A-E]\)|글의 주제|글의 제목|글의 내용|글의 빈칸|^\s*빈칸에|빈칸을|제시문|화자가|질문|아래|골라|According|The underlined|What|Which|Why|How|Where|Who)')
STEM_END=re.compile(r'(것은|것을|고르시오|고르면|무엇인가|몇 개|의 총 개수|의미하는 바|의미로|알 수 없는|답할 수 없는|일치하는|일치하지|쓰시오|완성하시오|영작하시오|서술하시오|설명하시오|해석하시오|배열하여|배열하시오|재배열|답을 서술|바로 가장|들어갈|넷과 다른|어긋나는|관계로|어색한|채우|이유는|\?)')
CONTAINER=re.compile(r'(읽고\s*물음에\s*답하시오|읽고\s*아래|읽고\s*물음에|물음에\s*답하시오|읽고\s*질문에\s*답하시오|질문에\s*답하시오)')
def is_container(t):
    t=t.strip()
    return bool(CONTAINER.search(t)) and len(t)<40
EN_Q=re.compile(r'^(According|The underlined|What|Which|Why|How|Where|Who|In the passage|Choose|Based on)')
# leading bullet/dingbat/arrow chars (e.g. ➔ U+F0E8 wingdings, arrows) — markers, not content-relevant for detection
LEAD_MARK=re.compile('^[\uf000-\uf0ff\u2190-\u21ff\u2794-\u27bf\u25a0-\u25ff\u2022\u00b7 \t]+')
def strip_lead(t):
    return LEAD_MARK.sub('', t.strip())
def is_stem(t):
    t=strip_lead(t)
    if len(t)<5 or len(t)>240: return False
    if is_container(t): return False
    # option line (never a 발문): a choice number at start, OR a SINGLE (A) option (not a "(A),(B),(C)" list stem)
    if re.match(r'^[①②③④⑤⑥⑦⑧⑨]', t): return False
    if re.match(r'^\([A-G]\)\s', t) and not re.match(r'^\([A-G]\)\s*,\s*\(', t): return False
    # English 서술형 question stem (Q-word start; ends with ? or a fill-in pattern)
    if EN_Q.match(t) and len(t)<170 and (t.endswith('?') or re.search(r'(closest in meaning|is closest|best describes|refers to|stands for|means\b|meaning of)', t)): return True
    if kratio(t)<0.15: return False
    if not STEM_KW.search(t): return False
    if not (t.endswith('?') or STEM_END.search(t)): return False
    return True
def is_choice(t): return bool(re.match(r'^\s*[①②③④⑤]\s?\S', t))

def role_of(t):
    s=t.strip()
    if not s: return 'blank'
    if is_choice(s): return 'choice'
    if re.match(r'^\s*<\s*보기\s*>|^\s*\[\s*보기\s*\]', s): return 'bogi_h'
    if re.match(r'^\s*<\s*조건\s*>|^\s*\[\s*조건\s*\]', s): return 'jogeon_h'
    if re.match(r'^\s*<\s*단어\s*>', s): return 'word_h'
    if re.match(r'^\s*<\s*요약\s*>|^\s*\[\s*요약문?\s*\]', s): return 'summary_h'
    if re.match(r'^\s*<\s*조건|보기|해석\s*>', s): return 'marker'
    if s in ('↓','⬇'): return 'arrow'
    # (A)~(E) answer-writing blank ONLY if it actually contains underscores (a blank to fill)
    if re.match(r'^\s*\([A-Ea-e]\)', s) and re.search(r'_{3,}', s): return 'abc'
    # (A)~(G) statement option (full sentence to evaluate) -> keep text as an option line
    if re.match(r'^\s*\([A-G]\)', s) and len(s)<200: return 'optline'
    if aratio(s)>0.55 and len(s)>50: return 'passage'
    return 'note'


def is_red_header(p):
    rr=p.get('runs',[])
    if not rr: return False
    txt=''.join(r['t'] for r in rr).strip()
    if not txt or len(txt)>20: return False
    if not re.search(r'[가-힣]', txt): return False
    # all non-space runs are red
    reds=[r for r in rr if r['t'].strip()]
    if reds and all(r.get('r') for r in reds): return True
    return False

# A stem glued to its passage in ONE paragraph (manuscript quirk): split into two.
GLUE=re.compile(r'^(\s*.{5,150}?(?:것은\??|것을\??|고르시오\.?|고르면\??|무엇인가\??|의 개수는\??|\?))(\s{2,})(["“A-Z].{35,})$',re.S)
def _split_runs(runs,boundary):
    left=[]; right=[]; acc=0
    for r in runs:
        tl=len(r['t'])
        if acc>=boundary: right.append(r)
        elif acc+tl<=boundary: left.append(r)
        else:
            cut=boundary-acc
            lr=dict(r); lr['t']=r['t'][:cut]; rr=dict(r); rr['t']=r['t'][cut:]
            if lr['t']: left.append(lr)
            if rr['t']: right.append(rr)
        acc+=tl
    return left,right
def expand_glued(ps):
    out=[]
    for p in ps:
        t=rtext(p['runs'])
        m=GLUE.match(t)
        if m and STEM_KW.search(m.group(1)) and aratio(m.group(3))>0.5 and not is_stem(t.strip()):
            lrun,rrun=_split_runs(p['runs'],m.start(3))
            stem_p={'runs':lrun}
            pass_p={'runs':rrun}
            for k in ('tables','pic'):
                if p.get(k): pass_p[k]=p[k]
            out.append(stem_p); out.append(pass_p)
        else:
            out.append(p)
    return out

# PUA/사제폰트 글리프 정규화(세종1): 발문앞 장식(F0E8)=제거(번호매기기가 대체), 요약화살표(F0EA)=↓, 제시문마커(F02B1/2)=①②
def norm_glyphs(ps):
    for p in ps:
        for r in p['runs']:
            t=r['t']
            if '' in t: t=t.replace(' ','').replace('','')
            if '' in t: t=t.replace('','↓')
            if '\U000f02b1' in t: t=t.replace('\U000f02b1','①')
            if '\U000f02b2' in t: t=t.replace('\U000f02b2','②')
            r['t']=t
    return ps

def parse(path):
    ps=norm_glyphs(expand_glued(paragraphs(path)))
    problems=[]; cur_type=None; num=0
    i=0; n=len(ps); container_passage=None
    # skip leading memo
    while i<n:
        p=ps[i]; t=rtext(p['runs']).strip()
        if (is_type_header(t) or is_red_header(p)) and not is_stem(t):
            cur_type=t; container_passage=None; i+=1; continue
        if is_container(t):
            # gather container passage(s): following passage paras until first stem
            container_passage=[]; i+=1
            while i<n:
                q=ps[i]; qt=rtext(q['runs']).strip()
                if is_stem(qt) or is_type_header(qt) or is_red_header(q) or is_container(qt): break
                if qt: container_passage.append(q)
                i+=1
            continue
        if is_stem(t):
            num+=1
            prob={'num':num,'type':cur_type,'stem':p['runs'],'blocks':[]}
            if container_passage:
                for cp in container_passage:
                    prob['blocks'].append({'role':'passage','runs':cp['runs'],'shared':True,
                                           **({'tables':cp['tables']} if cp.get('tables') else {})})
            i+=1
            while i<n:
                q=ps[i]; qt=rtext(q['runs']).strip()
                if (is_type_header(qt) or is_red_header(q)) and not is_stem(qt): break
                if is_stem(qt):
                    # NOT a new problem if this is the content right after a <질문>/<보기> marker
                    _pv=''
                    for _bb in range(len(prob['blocks'])-1,-1,-1):
                        _pt=rtext(prob['blocks'][_bb]['runs']).strip()
                        if _pt: _pv=_pt; break
                    if not re.match(r'^\s*[<\[]\s*(질문|보기|Question)\s*[>\]]', _pv): break
                if is_container(qt): break
                blk={'role':role_of(qt),'runs':q['runs']}
                if q.get('tables'): blk['tables']=q['tables']
                if q.get('pic'): blk['pic']=True
                prob['blocks'].append(blk)
                i+=1
            refine_roles(prob)
            merge_multiblank_choices(prob)
            problems.append(prob)
            continue
        i+=1
    return ps,problems

def _tabrun(): return {'t':'\t','b':False,'i':False,'u':False,'r':False}
def merge_multiblank_choices(prob):
    # (A)(B)[(C)] 빈칸 선지가 원고 표 flatten으로 "① while"/"…"/"whereas" 3조각으로 쪼개진 것을
    # 탭 정렬된 한 줄 선지로 병합. mbhead=(A)(B)헤더행, mbchoice=①..선지행.
    bl=prob['blocks']
    heads=[b for b in bl if b['role']=='optline' and re.match(r'^\([A-C]\)$', rtext(b['runs']).strip())]
    if len(heads)<2: return
    def is_ch(b): return b['role']=='choice' and re.match(r'^[①②③④⑤]', rtext(b['runs']).strip())
    new=[]; i=0
    while i<len(bl):
        b=bl[i]; txt=rtext(b['runs']).strip()
        if b['role']=='optline' and re.match(r'^\([A-C]\)$', txt):
            hdr=[]
            while i<len(bl) and bl[i]['role']=='optline' and re.match(r'^\([A-C]\)$', rtext(bl[i]['runs']).strip()):
                hdr.append(bl[i]); i+=1
            hr=[]
            for k,h in enumerate(hdr):
                hr.append(_tabrun())  # 각 열머리 앞 탭(마커열/A열 건너뜀)
                if k>0: hr.append(_tabrun())
                hr.extend(h['runs'])
            new.append({'role':'mbhead','runs':hr}); continue
        if is_ch(b):
            # 마커(①)를 A답과 분리: "① while" -> "①" \t "while" (헤더 (A)(B) 열정렬용)
            f0=dict(b['runs'][0]); m=re.match(r'^([①②③④⑤])\s*(.*)$', f0['t'])
            if m:
                mk=dict(f0); mk['t']=m.group(1); runs=[mk, _tabrun()]
                rst=dict(f0); rst['t']=m.group(2)
                if rst['t']: runs.append(rst)
                runs.extend([dict(r) for r in b['runs'][1:]])
            else:
                runs=[dict(r) for r in b['runs']]
            j=i+1
            while j<len(bl) and not is_ch(bl[j]):
                nt=rtext(bl[j]['runs']).strip()
                if nt: runs.append(_tabrun()); runs.extend(bl[j]['runs'])
                j+=1
            new.append({'role':'mbchoice','runs':runs}); i=j; continue
        new.append(b); i+=1
    prob['blocks']=new

def refine_roles(prob):
    mode=None
    for b in prob['blocks']:
        r=b['role']
        if r in ('bogi_h','word_h'): mode='bogi'; continue
        if r=='jogeon_h': mode='jogeon'; continue
        if r=='summary_h': mode='summary'; continue
        if r=='choice': mode=None; continue
        if r=='passage' and b.get('shared'): mode=None; continue
        # (A) e____ / (A) ________ answer-blank lines are 선지(choice) answers, NOT 조건/보기 content
        if r=='abc' and re.search(r'\([A-Ea-e]\)\s*[A-Za-z]?\s*_{2,}', rtext(b['runs'])):
            mode=None; continue
        if r in ('note','passage','abc','marker'):
            if mode=='bogi': b['role']='bogi'
            elif mode=='jogeon': b['role']='jogeon'
    for b in prob['blocks']:
        t=rtext(b['runs']).strip()
        if re.match(r'^\s*(답|정답)\s*[:：]', t) or re.match(r'^_{5,}', t):
            b['role']='answerline'

def emit(base):
    out={}
    for school in ['상일1','명일1']:
        d=f"{base}/src/{school}"
        fn=[f for f in os.listdir(d) if unicodedata.normalize('NFC',f).startswith('Part3_원고')][0]
        ps,probs=parse(os.path.join(d,fn))
        # content conservation: count non-blank source paras vs captured
        src_nonblank=sum(1 for p in ps if rtext(p['runs']).strip())
        cap=0
        for pr in probs:
            cap+=1  # stem
            cap+=sum(1 for b in pr['blocks'] if not b.get('shared') and rtext(b['runs']).strip())
        out[school]={'n':len(probs),'src_nonblank':src_nonblank,'captured':cap}
        json.dump({'school':school,'problems':probs},open(f"{base}/p3_{school}.json",'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        from collections import Counter
        byt=Counter(p['type'] for p in probs)
        print(f"===== {school}: 문제={len(probs)} | 원본비어있지않은단락={src_nonblank} 캡처(발문+블록)={cap} =====")
        print("  유형:",dict(byt))
        # blocks role histogram
        roles=Counter(b['role'] for pr in probs for b in pr['blocks'])
        print("  블록역할:",dict(roles))
    return out

if __name__=='__main__':
    emit(sys.argv[1])
