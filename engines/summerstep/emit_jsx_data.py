import json,sys
def conv(school,base):
    d=json.load(open(f"{base}/p3_{school}.json",encoding='utf-8'))
    probs=[]
    for p in d['problems']:
        # stem runs
        def runs(rr): return [[r['t'], (('u' if r['u'] else '')+('b' if r['b'] else '')+('i' if r['i'] else '')+('r' if r.get('r') else ''))] for r in rr if r['t']!='' ]
        blocks=[]
        for b in p['blocks']:
            txt=''.join(r['t'] for r in b['runs'])
            if not txt.strip() and b['role']=='blank': continue
            blk={'r':b['role'],'x':runs(b['runs'])}
            if b.get('tables'): blk['tbl']=b['tables']
            blocks.append(blk)
        probs.append({'n':p['num'],'t':p['type'] or '','stem':runs(p['stem']),'b':blocks})
    return probs
if __name__=='__main__':
    base=sys.argv[1]; school=sys.argv[2]
    probs=conv(school,base)
    out="var P3DATA = "+json.dumps(probs,ensure_ascii=False)+";"
    open(f"{base}/p3data_{school}.jsx.txt","w",encoding='utf-8').write(out)
    print(f"{school}: {len(probs)} problems, {len(out)} bytes")
