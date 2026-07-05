# Table-aware paragraph extractor: top-level paragraphs + reconstructed table content, in order.
import zipfile, re
from lxml import etree
HP='http://www.hancom.co.kr/hwpml/2011/paragraph'
HH='http://www.hancom.co.kr/hwpml/2011/head'
def q(t): return '{%s}%s'%(HP,t)
from hwpx_paras import load_charpr, para_runs

def _cell_runs(tc, cp):
    runs=[]
    for p in tc.iter(q('p')):
        runs.extend(para_runs(p, cp))
    return runs

def paragraphs2(path):
    z=zipfile.ZipFile(path); cp=load_charpr(z)
    secs=sorted(n for n in z.namelist() if re.match(r'Contents/section\d+\.xml',n))
    out=[]
    for s in secs:
        root=etree.fromstring(z.read(s))
        for p in root.iter(q('p')):
            anc=p.getparent(); nested=False
            while anc is not None:
                if etree.QName(anc).localname in ('tc','subList'): nested=True; break
                anc=anc.getparent()
            if nested: continue
            tbl=p.find('.//'+q('tbl'))
            if tbl is not None:
                # reconstruct: iterate cells in row order; each cell -> its own paragraph (runs)
                for tr in tbl.findall(q('tr')):
                    for tc in tr.findall(q('tc')):
                        r=_cell_runs(tc, cp)
                        txt=''.join(x['t'] for x in r)
                        if txt.strip():
                            out.append({'text':txt,'runs':r,'from_table':True})
                # also any direct text of the table-holding paragraph
                dt=para_runs(p, cp)
                if ''.join(x['t'] for x in dt).strip():
                    out.append({'text':''.join(x['t'] for x in dt),'runs':dt})
            else:
                runs=para_runs(p, cp)
                text=''.join(r['t'] for r in runs)
                if text.strip() or True:
                    out.append({'text':text,'runs':runs})
    # merge marker-cell + text-cell pairs: "①" followed by "text" -> "① text"
    merged=[]; i=0
    mk=re.compile(r'^\s*([①②③④⑤ⓐⓑⓒⓓⓔⓕ➀-➄])\s*$')
    while i<len(out):
        cur=out[i]; t=cur['text'].strip()
        if cur.get('from_table') and mk.match(t) and i+1<len(out) and out[i+1].get('from_table'):
            nxt=out[i+1]
            combo_runs=[{'t':t+' ','b':False,'i':False,'u':False,'r':False}]+nxt['runs']
            merged.append({'text':t+' '+nxt['text'],'runs':combo_runs,'from_table':True})
            i+=2
        else:
            merged.append(cur); i+=1
    return merged

if __name__=='__main__':
    import sys
    ps=paragraphs2(sys.argv[1])
    print('paras:',len(ps))
