#target indesign
/*
 * ExamScopeFilter.jsx  --  시험범위 외 지문 자동 삭제 엔진
 * --------------------------------------------------------------
 * FINAL EDGE 문제편(.indd)에서 시험범위에 해당하지 않는 지문을
 * 통째로(해당 지문의 모든 문제 블록 + 빈 페이지) 자동 삭제한다.
 *
 * 사용:
 *   1) 문제편 .indd 를 InDesign에 열어둔다.
 *   2) 이 스크립트를 실행한다.
 *   3) 강별 지문 목록 다이얼로그에서 "남길 지문"을 체크하고 실행.
 *      (선택) 분석본을 불러오면 분석본에 있는 지문을 표시해 참고할 수 있다.
 *
 * 범용 설계:
 *   - 발문/지문/머리말 단락 스타일을 이름 패턴으로 탐지 (STYLE_CFG)
 *   - 태그형(예: [18-2], [19-(3~4)])은 태그로 지문 분류
 *   - 수능형(※ 다음 글을 읽고)은 지문 본문 단어겹침으로 분류
 *   - 태그/시그니처 하드코딩 없음 → 다른 회차/교재에도 동작
 *
 * ES3(ExtendScript) 호환: let/const/화살표/JSON 미사용
 */

var ExamScope = (function(){

    // ===== 설정: 단락 스타일 이름 패턴 (다른 템플릿이면 여기만 수정) =====
    var STYLE_CFG = {
        balmun: ["실전문제 번호", "실전 문제 번호"],   // 발문(문제 시작) 스타일
        header: ["다음 글을 읽고"],                   // 수능형 ※ 머리말 스타일
        jimun:  ["실전 문제 지문", "실전문제 지문"],   // 지문 본문 스타일
        ctx:    ["배경", "보기", "조건"]              // 분류 보조용 부가 텍스트
    };
    var OVERLAP_NEW = 0.5;   // 수능형에서 새 지문으로 판정하는 겹침 임계값

    // ---------- 공통 유틸 ----------
    function PS(p){ var n=""; try{ n=p.appliedParagraphStyle.name; }catch(e){} return n; }
    function nameHas(n, arr){ for(var i=0;i<arr.length;i++){ if(n.indexOf(arr[i])>=0) return true; } return false; }
    function isBalmun(n){ return nameHas(n, STYLE_CFG.balmun); }
    function isHeader(n){ return nameHas(n, STYLE_CFG.header); }
    function isJimun(n){ return nameHas(n, STYLE_CFG.jimun); }
    function isCtx(n){ return nameHas(n, STYLE_CFG.ctx); }

    function wordSet(t){
        var s={}, m=t.toLowerCase().replace(/[^a-z ]/g," ").split(/\s+/);
        for(var i=0;i<m.length;i++){ if(m[i].length>=4) s[m[i]]=1; }
        return s;
    }
    function overlap(a,b){
        var ka=0,kb=0,inter=0,k;
        for(k in a){ka++;}
        for(k in b){kb++; if(a[k])inter++;}
        var mn=Math.min(ka,kb); return mn===0?0:inter/mn;
    }
    function clean(s){ return s.replace(/^\s+/,"").replace(/[\r\n\t]+/g," "); }

    // ---------- 태그 파싱 ----------
    // [18-2] / [18강-01] / [19-(3~4)] / [19-3~4]  ->  {gang:"18", pass:"2" | "3~4"}
    function parseTag(t){
        var m=t.match(/\[(\d+)\s*강?\s*[-‐-―]\s*\(?\s*(\d+(?:\s*[~～]\s*\d+)?)/);
        if(!m) return null;
        var spec=m[2].replace(/\s/g,"");
        spec=spec.replace(/(^|~)0+(\d)/g,"$1$2"); // 선행 0 제거
        return { gang:m[1], pass:spec };
    }

    // ---------- 블록 분류용 텍스트 ----------
    function blockText(P,s,e){
        var t="", j, n;
        for(j=s;j<=e;j++){ n=PS(P[j]); if(isJimun(n)||isCtx(n)){ try{t+=P[j].contents+" ";}catch(ee){} } }
        if(t.replace(/\s/g,"").length<20){ for(j=s;j<=e;j++){ try{t+=P[j].contents+" ";}catch(ee2){} } }
        return t;
    }

    // ---------- 콘텐츠 스토리 판정 ----------
    function isContentStory(st){
        var P=st.paragraphs, lim=Math.min(P.length,500), i, n;
        for(i=0;i<lim;i++){ n=PS(P[i]); if(isBalmun(n)||isHeader(n)) return true; }
        return false;
    }

    // ---------- 강 라벨 추출 ----------
    function gangLabel(st, doc){
        var pg=null;
        try{ var tc=st.textContainers; if(tc.length>0) pg=tc[0].parentPage; }catch(e){}
        if(!pg) return "?";
        var pidx=pg.documentOffset, p, items, k, c, m;
        for(p=pidx; p>=0 && p>=pidx-3; p--){
            items=doc.pages[p].allPageItems;
            for(k=0;k<items.length;k++){
                if(items[k].constructor.name==="TextFrame"){
                    c=""; try{c=items[k].contents;}catch(e2){}
                    m=c.match(/(\d+)\s*강/);
                    if(m) return m[1]+"강";
                }
            }
        }
        return "?";
    }
    function firstPageOffset(st){
        try{ var tc=st.textContainers; if(tc.length>0) return tc[0].parentPage.documentOffset; }catch(e){}
        return 99999;
    }

    // ---------- 스토리 분석 -> 지문 목록 ----------
    function analyzeStory(st, doc){
        var P=st.paragraphs, N=P.length, i, n;
        var balmun=[], hdr=[], tagged=0, b;
        for(i=0;i<N;i++){
            n=PS(P[i]);
            if(isBalmun(n)) balmun.push(i);
            if(isHeader(n) && P[i].contents.indexOf("※")>=0) hdr.push(i);
        }
        for(b=0;b<balmun.length;b++){ if(parseTag(P[balmun[b]].contents)) tagged++; }
        var tagMode = (balmun.length>0 && tagged/balmun.length>0.3);

        var blocks=[], k, s, e, tg;
        if(tagMode){
            for(k=0;k<balmun.length;k++){
                s=balmun[k]; e=(k+1<balmun.length)?balmun[k+1]-1:N-1;
                tg=parseTag(P[s].contents);
                blocks.push({ s:s, e:e, pass:(tg?tg.pass:null), txt:blockText(P,s,e) });
            }
        } else {
            for(k=0;k<hdr.length;k++){
                s=hdr[k]; e=(k+1<hdr.length)?hdr[k+1]-1:N-1;
                blocks.push({ s:s, e:e, pass:null, txt:blockText(P,s,e) });
            }
        }

        var passages=[]; // {key, ref, reftxt}
        function passByKey(key){ for(var q=0;q<passages.length;q++){ if(passages[q].key===key) return q; } return -1; }
        function bestOverlapIdx(ws){
            var bi=-1, bo=-1, q;
            for(q=0;q<passages.length;q++){ var o=overlap(passages[q].ref,ws); if(o>bo){bo=o;bi=q;} }
            return { idx:bi, ov:bo };
        }

        // 1차: 명시 태그 블록으로 지문 시드
        var bi;
        for(bi=0;bi<blocks.length;bi++){
            var bl=blocks[bi];
            if(tagMode && bl.pass){
                var f=passByKey(bl.pass);
                if(f<0){ passages.push({ key:bl.pass, ref:wordSet(bl.txt), reftxt:bl.txt }); f=passages.length-1; }
                bl.passIdx=f;
            }
        }
        // 2차: 미배정 블록
        for(bi=0;bi<blocks.length;bi++){
            var bl2=blocks[bi];
            if(bl2.passIdx!==undefined) continue;
            var ws=wordSet(bl2.txt);
            if(tagMode){
                // 태그형: 지문은 이미 확정 -> 무조건 최대겹침 지문에 배정
                var r=bestOverlapIdx(ws);
                bl2.passIdx = (r.idx>=0)?r.idx:0;
            } else {
                var r2=bestOverlapIdx(ws);
                if(r2.idx>=0 && r2.ov>OVERLAP_NEW){ bl2.passIdx=r2.idx; }
                else { passages.push({ key:String(passages.length+1), ref:ws, reftxt:bl2.txt }); bl2.passIdx=passages.length-1; }
            }
        }

        // 지문별 집계 + 단락 인덱스 수집
        var out=[];
        var pi;
        for(pi=0;pi<passages.length;pi++){
            var paraIdx=[], nb=0, bk;
            for(bk=0;bk<blocks.length;bk++){
                if(blocks[bk].passIdx===pi){
                    nb++;
                    for(var jj=blocks[bk].s; jj<=blocks[bk].e; jj++) paraIdx.push(jj);
                }
            }
            out.push({
                key: passages[pi].key,
                preview: clean(passages[pi].reftxt).substr(0,70),
                blocks: nb,
                paraIdx: paraIdx
            });
        }
        return { tagMode:tagMode, passages:out };
    }

    // ---------- 문서 전체 강 탐지 ----------
    function detectGangs(doc){
        var gangs=[], si;
        for(si=0; si<doc.stories.length; si++){
            var st=doc.stories[si];
            if(!isContentStory(st)) continue;
            var r=analyzeStory(st, doc);
            gangs.push({
                storyIndex: si,
                label: gangLabel(st, doc),
                tagMode: r.tagMode,
                passages: r.passages,
                _page: firstPageOffset(st)
            });
        }
        gangs.sort(function(a,b){ return a._page - b._page; });
        return gangs;
    }

    // ---------- 분석본에서 지문 존재 여부 표시 (참고용) ----------
    function markFromAnalysis(gangs, analysisDoc){
        // 분석본 전체 영어 텍스트(정규화)
        var big="", si;
        for(si=0; si<analysisDoc.stories.length; si++){
            try{ big += analysisDoc.stories[si].contents + " "; }catch(e){}
        }
        var norm = big.toLowerCase().replace(/[^a-z]/g," ").replace(/\s+/g," ");
        var gi, pj;
        for(gi=0; gi<gangs.length; gi++){
            for(pj=0; pj<gangs[gi].passages.length; pj++){
                var p=gangs[gi].passages[pj];
                // 미리보기의 앞쪽 영어 단어 6개를 키로 검색
                var key = p.preview.toLowerCase().replace(/[^a-z ]/g," ").replace(/\s+/g," ");
                var words = key.split(" ");
                var probe=[], c=0, w;
                for(w=0; w<words.length && c<6; w++){ if(words[w].length>=4){ probe.push(words[w]); c++; } }
                var phrase = probe.join(" ");
                p.inAnalysis = (phrase.length>0 && norm.indexOf(phrase)>=0);
            }
        }
    }

    // ---------- 적용: keep 목록 외 지문 삭제 + 빈 페이지 정리 ----------
    // plan: { "18강": {"2":true,"4":true}, ... }  (true=남김)
    function applyKeep(doc, gangs, plan){
        var report={ deletedParas:0, deletedPages:0, perGang:[] };
        app.doScript(function(){
            var gi;
            for(gi=0; gi<gangs.length; gi++){
                var g=gangs[gi];
                var keep = plan[g.label] || {};
                var st = doc.stories[g.storyIndex];
                var delIdx=[], pj, dCnt=0, kCnt=0;
                for(pj=0; pj<g.passages.length; pj++){
                    var p=g.passages[pj];
                    if(keep[p.key]===true){ kCnt++; continue; }
                    dCnt++;
                    var m; for(m=0;m<p.paraIdx.length;m++) delIdx.push(p.paraIdx[m]);
                }
                delIdx.sort(function(a,b){ return b-a; });
                var x;
                for(x=0; x<delIdx.length; x++){
                    try{ st.paragraphs[delIdx[x]].remove(); report.deletedParas++; }catch(e){}
                }
                report.perGang.push({ label:g.label, kept:kCnt, deleted:dCnt });
            }
            // 빈 페이지 정리 (텍스트프레임이 1개 이상이고 전부 빈 페이지)
            var p;
            for(p=doc.pages.length-1; p>=0; p--){
                var pg=doc.pages[p], items=pg.allPageItems, tot=0, empty=0, k;
                for(k=0;k<items.length;k++){
                    if(items[k].constructor.name==="TextFrame"){
                        tot++;
                        var c=""; try{c=items[k].contents;}catch(e){}
                        if(typeof c==="string" && c.replace(/\s/g,"").length===0) empty++;
                    }
                }
                if(tot>0 && empty===tot){ try{ pg.remove(); report.deletedPages++; }catch(e2){} }
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "시험범위 외 지문 삭제");
        return report;
    }

    // ---------- 백업 저장 ----------
    function backup(doc){
        try{
            var fn=doc.fullName.fsName, dot=fn.lastIndexOf(".");
            var bak=fn.substring(0,dot)+"_BACKUP_시험범위전"+fn.substring(dot);
            doc.save(new File(bak));
            doc.save(doc.fullName); // 원본으로 복귀 저장
            return bak;
        }catch(e){ return null; }
    }

    return {
        detectGangs: detectGangs,
        analyzeStory: analyzeStory,
        markFromAnalysis: markFromAnalysis,
        applyKeep: applyKeep,
        backup: backup,
        STYLE_CFG: STYLE_CFG
    };
})();

// =====================================================================
//  UI + main  (테스트 드라이버에서 $.global.EXAMSCOPE_NORUN=true 면 미실행)
// =====================================================================
function ExamScope_main(){
    if(app.documents.length===0){ alert("문제편 .indd 파일을 먼저 열어주세요."); return; }
    var doc=app.activeDocument;
    var gangs=ExamScope.detectGangs(doc);
    if(gangs.length===0){ alert("문제 스토리를 찾지 못했습니다. 스타일 이름 설정(STYLE_CFG)을 확인하세요."); return; }

    // ----- 다이얼로그 -----
    var dlg=new Window("dialog","시험범위 지문 선택 (체크=남김)");
    dlg.alignChildren="fill"; dlg.preferredSize.width=620;

    var info=dlg.add("statictext",undefined,"남길 지문을 체크하세요. 체크 안 된 지문은 모두 삭제됩니다.",{multiline:false});

    var sp=dlg.add("panel"); sp.alignChildren="left"; sp.maximumSize.height=420;
    // 스크롤 대용: 강이 많으면 그대로 나열
    var checks=[]; // {label,key,cb}
    var gi,pj;
    for(gi=0; gi<gangs.length; gi++){
        var g=gangs[gi];
        var gp=sp.add("panel",undefined,g.label+"  ("+(g.tagMode?"태그형":"수능형")+", 지문 "+g.passages.length+"개)");
        gp.alignChildren="left"; gp.margins=10;
        for(pj=0; pj<g.passages.length; pj++){
            var p=g.passages[pj];
            var cb=gp.add("checkbox",undefined,"지문 "+p.key+" : "+p.preview);
            cb.value=true;
            checks.push({ label:g.label, key:p.key, cb:cb });
        }
    }

    var btns=dlg.add("group"); btns.alignment="right";
    var bAna=btns.add("button",undefined,"분석본 불러오기(참고)");
    var bAll=btns.add("button",undefined,"전체 선택");
    var bNone=btns.add("button",undefined,"전체 해제");
    var bOk=btns.add("button",undefined,"실행",{name:"ok"});
    var bCancel=btns.add("button",undefined,"취소",{name:"cancel"});

    bAll.onClick=function(){ for(var i=0;i<checks.length;i++) checks[i].cb.value=true; };
    bNone.onClick=function(){ for(var i=0;i<checks.length;i++) checks[i].cb.value=false; };
    bAna.onClick=function(){
        var f=File.openDialog("분석본 .indd 선택");
        if(!f) return;
        var local=f;
        // GDrive 등 스트림 회피: 임시폴더로 복사 후 열기
        try{
            var tmp=new File(Folder.temp.fsName+"/_examscope_analysis.indd");
            if(f.copy(tmp)) local=tmp;
        }catch(e){}
        var adoc=null;
        try{ adoc=app.open(local, false); }catch(e2){ alert("분석본을 열 수 없습니다: "+e2); return; }
        ExamScope.markFromAnalysis(gangs, adoc);
        try{ adoc.close(SaveOptions.NO); }catch(e3){}
        // 분석본에 있는 지문만 체크
        var idx=0, gi2, pj2;
        for(gi2=0; gi2<gangs.length; gi2++){
            for(pj2=0; pj2<gangs[gi2].passages.length; pj2++){
                var pp=gangs[gi2].passages[pj2];
                checks[idx].cb.value = (pp.inAnalysis===true);
                checks[idx].cb.text  = "지문 "+pp.key+" : "+pp.preview+(pp.inAnalysis?"   [분석본에 있음]":"");
                idx++;
            }
        }
        alert("분석본 기준으로 체크했습니다. 필요시 수정 후 실행하세요.");
    };

    if(dlg.show()!==1) return;

    // plan 구성
    var plan={}, i;
    for(i=0;i<checks.length;i++){
        var c=checks[i];
        if(!plan[c.label]) plan[c.label]={};
        if(c.cb.value) plan[c.label][c.key]=true;
    }

    // 백업 후 적용
    var bak=ExamScope.backup(doc);
    var rep=ExamScope.applyKeep(doc, gangs, plan);

    var msg="완료.\n삭제 단락="+rep.deletedParas+"\n삭제 페이지="+rep.deletedPages+"\n현재 페이지="+doc.pages.length+"\n\n";
    var r;
    for(r=0;r<rep.perGang.length;r++){ msg+=rep.perGang[r].label+": 남김 "+rep.perGang[r].kept+" / 삭제 "+rep.perGang[r].deleted+"\n"; }
    if(bak) msg+="\n백업: "+bak;
    alert(msg);
}

if(!$.global.EXAMSCOPE_NORUN){ ExamScope_main(); }
