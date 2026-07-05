# Clean paragraph extractor for hwpx: no nested-run duplication, keeps formatting + table cells
import zipfile, re
from lxml import etree
HP='http://www.hancom.co.kr/hwpml/2011/paragraph'
HH='http://www.hancom.co.kr/hwpml/2011/head'
def q(tag): return '{%s}%s'%(HP,tag)

def load_charpr(z):
    head=etree.fromstring(z.read('Contents/header.xml'))
    cp={}
    def hh(t): return '{%s}%s'%(HH,t)
    for c in head.iter(hh('charPr')):
        u=c.find(hh('underline'))
        col=(c.get('textColor','') or '').upper()
        cp[c.get('id')]={
          'b': c.find(hh('bold')) is not None,
          'i': c.find(hh('italic')) is not None,
          'u': (u is not None and u.get('type','NONE')!='NONE'),
          'r': (col=='#FF0000'),  # red
        }
    return cp

def para_runs(p, cp):
    """Return list of runs [{t,b,i,u}] for a paragraph, NOT descending into nested sub-paragraphs (tables/shapes handled separately)."""
    runs=[]
    for run in p.findall(q('run')):
        fmt=cp.get(run.get('charPrIDRef'),{})
        # collect only direct text/tab/lineBreak of this run, but skip text inside nested tbl/subList
        buf=[]
        for el in run:
            tag=etree.QName(el).localname
            if tag=='t':
                buf.append(el.text or '')
                # t may have children (markpen etc.) - include tails
                for sub in el:
                    if sub.tail: buf.append(sub.tail)
            elif tag=='tab': buf.append('\t')
            elif tag=='lineBreak': buf.append('\n')
            # skip 'tbl','ctrl','pic' here (handled via table walk)
        t=''.join(buf)
        if t:
            runs.append({'t':t,'b':fmt.get('b',False),'i':fmt.get('i',False),'u':fmt.get('u',False),'r':fmt.get('r',False)})
    return runs

def has_table(p):
    return p.find('.//'+q('tbl')) is not None
def has_pic(p):
    return p.find('.//'+q('pic')) is not None or p.find('.//'+q('picture')) is not None

def get_tables(p, cp):
    tbls=[]
    for tbl in p.iter(q('tbl')):
        rows=[]
        for tr in tbl.findall(q('tr')):
            cells=[]
            for tc in tr.findall(q('tc')):
                # each cell has subList with p's
                celltext=[]
                for cp_p in tc.iter(q('p')):
                    r=para_runs(cp_p, cp)
                    txt=''.join(x['t'] for x in r)
                    if txt: celltext.append(txt)
                cells.append(' '.join(celltext))
            rows.append(cells)
        tbls.append(rows)
    return tbls

def paragraphs(path):
    z=zipfile.ZipFile(path); cp=load_charpr(z)
    secs=sorted(n for n in z.namelist() if re.match(r'Contents/section\d+\.xml',n))
    out=[]
    for s in secs:
        root=etree.fromstring(z.read(s))
        # top-level paragraphs only: hp:p that are NOT inside a tc/subList
        body=root
        for p in root.iter(q('p')):
            # skip if ancestor is a tc (table cell) or fieldBegin subList
            anc=p.getparent(); nested=False
            while anc is not None:
                ln=etree.QName(anc).localname
                if ln in ('tc','subList'): nested=True; break
                anc=anc.getparent()
            if nested: continue
            runs=para_runs(p, cp)
            text=''.join(r['t'] for r in runs)
            item={'text':text,'runs':runs}
            if has_table(p): item['tables']=get_tables(p,cp)
            if has_pic(p): item['pic']=True
            out.append(item)
    return out

if __name__=='__main__':
    import sys,json
    ps=paragraphs(sys.argv[1])
    for i,p in enumerate(ps):
        tag=''
        if p.get('tables'): tag+=' [TBL:%s]'%('|'.join(str(len(t)) for t in p['tables']))
        if p.get('pic'): tag+=' [PIC]'
        fmt=''
        if any(r['u'] for r in p['runs']): fmt+='U'
        if any(r['b'] for r in p['runs']): fmt+='B'
        if any(r['i'] for r in p['runs']): fmt+='I'
        print('%3d|%s|%s%s %s'%(i,fmt.ljust(3),tag,'', p['text'][:100]))
