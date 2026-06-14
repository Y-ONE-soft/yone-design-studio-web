// 화이트북 실전문제(문제형) 조판 자동화
// - 원본(샘플) 복사 → 본문/정답 단일 스토리를 새 원고로 교체 → 분량 초과 시 페이지 자동확장
// - 본문 thread: 좌상→좌하→우상→우하 (컬럼 우선). 정답: 페이지당 1프레임.
// - Day 사이 [단락 스타일 없음] 빈줄 2개, 문항 사이 빈 '선지' 1줄
// - 밑줄 <u>..</u> → GREP → '밑줄' 문자스타일
#target indesign
(function(){
    try{ app.scriptPreferences.userInteractionLevel=UserInteractionLevels.NEVER_INTERACT; }catch(_e){}
__SETTINGS_PATH__

    try{
    var sf=new File(settingsPath); sf.encoding='UTF-8'; sf.open('r'); var settings=eval("("+sf.read()+")"); sf.close();
    var cf=new File(settings.json_path); cf.encoding='UTF-8'; cf.open('r'); var data=eval("("+cf.read()+")"); cf.close();
    var outputDir=settings.output_dir;
    var inddPath=settings.indd_path;

    // ── 작업본 확보: 열려있으면 닫고, 원본에서 복사 후 열기 ──
    var fp=new File(inddPath);
    for(var i=app.documents.length-1;i>=0;i--){
        try{ if(app.documents[i].fullName.fsName===fp.fsName){ app.documents[i].close(SaveOptions.NO);} }catch(e){}
    }
    if(settings.indd_original){
        try{ var orig=new File(settings.indd_original); if(orig.exists) orig.copy(fp.fsName); }catch(e){}
    }
    var doc=app.open(fp);
    if(!doc||!doc.isValid) return "NO_DOC";
    app.activeDocument=doc;

    var _pCache={};
    function getStyle(name){
        if(_pCache[name]!==undefined) return _pCache[name];
        var r=doc.paragraphStyles.itemByName(name);
        if(!r.isValid){
            r=null;
            for(var g=0;g<doc.paragraphStyleGroups.length;g++){var gs=doc.paragraphStyleGroups[g].paragraphStyles.itemByName(name);if(gs.isValid){r=gs;break;}}
        }
        if(!r) r=doc.paragraphStyles[0];
        _pCache[name]=r; return r;
    }
    function getCharStyle(name){
        var s=doc.characterStyles.itemByName(name); if(s.isValid)return s;
        for(var g=0;g<doc.characterStyleGroups.length;g++){var gs=doc.characterStyleGroups[g].characterStyles.itemByName(name);if(gs.isValid)return gs;}
        return null;
    }
    var PMAP={'문제':'문제','보기':'보기','선지':'선지','지문':'선지','빈':'[단락 스타일 없음]','정답_문제 번호':'정답_문제 번호','해설_시작':'해설_시작','해설_':'해설_'};

    function findStoryByFirstStyle(name){
        for(var i=0;i<doc.stories.length;i++){var st=doc.stories[i];if(st.paragraphs.length>10){if(st.paragraphs[0].appliedParagraphStyle.name===name)return st;}}
        return null;
    }
    function fillStory(story,items){
        if(!story||!story.isValid||items.length===0)return 0;
        var arr=[];for(var i=0;i<items.length;i++)arr.push(items[i].text);
        story.contents=arr.join('\r');
        try{ story.texts[0].appliedCharacterStyle=doc.characterStyles[0]; }catch(e){}
        var paras=story.paragraphs; var n=Math.min(items.length,paras.length);
        for(var i=0;i<n;i++){ var sn=PMAP[items[i].sty]||items[i].sty; try{paras[i].appliedParagraphStyle=getStyle(sn);}catch(e){} }
        return n;
    }
    function applyUnderline(story){
        var cs=getCharStyle('밑줄'); if(!cs)return;
        app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat='<u>(.+?)</u>';
        app.changeGrepPreferences.changeTo='$1';
        app.changeGrepPreferences.appliedCharacterStyle=cs;
        try{ story.changeGrep(); }catch(e){}
        app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
    }
    function clonePageFrames(srcPage,dstPage){
        var s=srcPage.textFrames;
        for(var i=0;i<s.length;i++){ try{ dstPage.textFrames.add({geometricBounds:s[i].geometricBounds}); }catch(e){} }
    }
    // 마지막 프레임이 넘치면 페이지 추가 + 프레임 복제 + thread 연결 (sortMode: 'colfirst'=본문 좌상→좌하→우상→우하, 'rowfirst'=정답)
    function expandStory(story,sortMode){
        var safety=300, added=0;
        function last(){var tc=story.textContainers;return tc.length?tc[tc.length-1]:null;}
        var lf=last();
        while(lf&&lf.overflows&&added<safety){
            var lp=lf.parentPage; if(!lp)break;
            var np;
            try{ np=doc.pages.add(LocationOptions.AFTER,lp); if(lp.appliedMaster)np.appliedMaster=lp.appliedMaster; clonePageFrames(lp,np); }catch(e){break;}
            var nfs=[]; var tfs=np.textFrames;
            for(var t=0;t<tfs.length;t++){var b=tfs[t].geometricBounds;nfs.push({tf:tfs[t],y:b[0],x:b[1]});}
            if(sortMode==='colfirst') nfs.sort(function(a,b){ if(Math.abs(a.x-b.x)>5)return a.x-b.x; return a.y-b.y; });
            else nfs.sort(function(a,b){ if(Math.abs(a.y-b.y)>5)return a.y-b.y; return a.x-b.x; });
            if(nfs.length===0)break;
            for(var n=0;n<nfs.length;n++){var nf=nfs[n].tf;try{nf.contents='';}catch(e){}try{lf.nextTextFrame=nf;lf=nf;}catch(e){break;}}
            added++; lf=last();
        }
        return added;
    }

    // 긴 문제(프레임 초과) 처리: 한 컬럼의 상단 칸이 넘치면 하단 칸 삭제 + 상단 칸을 텍스트 양만큼 아래로 늘림(세로 2칸)
    var _HEIGHT_ONLY=1751476583;
    function processCol(col){
        if(col.length<2) return;
        var top=col[0].tf, bot=col[1].tf;
        try{
            if(top.overflows){
                try{ bot.remove(); }catch(e){}
                try{ top.textFramePreferences.autoSizingType=_HEIGHT_ONLY; }catch(e){}
            }
        }catch(e){}
    }
    function processLongQuestions(){
        for(var p=0;p<doc.pages.length;p++){
            var pg=doc.pages[p]; var mn=''; try{mn=pg.appliedMaster?pg.appliedMaster.name:'';}catch(e){}
            if(mn.indexOf('C')===0) continue;   // 정답(C-마스터) 영역 제외
            var tfs=pg.textFrames; var fr=[];
            for(var t=0;t<tfs.length;t++){ try{var b=tfs[t].geometricBounds; if(b[1]>=19 && (b[3]-b[1])>40 && (b[2]-b[0])>30) fr.push({tf:tfs[t],y:b[0],x:b[1]});}catch(e){} }
            if(fr.length!==4) continue;
            var left=[],right=[];
            for(var k=0;k<fr.length;k++){ if(fr[k].x<100)left.push(fr[k]); else right.push(fr[k]); }
            left.sort(function(a,b){return a.y-b.y;}); right.sort(function(a,b){return a.y-b.y;});
            processCol(left); processCol(right);
        }
    }

    // ── items 빌드 ──
    var bodyItems=[]; var pd=data.problem_days;
    for(var d=0;d<pd.length;d++){
        var ln=pd[d].lines; var firstQ=true;
        for(var i=0;i<ln.length;i++){
            var it=ln[i];
            if(it.sty==='문제'){
                // Day 첫 문제=페이지 break(첫 Day 제외), 그 외 문제=프레임 break → 1프레임 1문제
                var brk = firstQ ? (d===0 ? null : 'page') : 'frame';
                it={sty:it.sty, text:it.text, brk:brk, dayStart:firstQ, dayNum:pd[d].day};
                firstQ=false;
            }
            bodyItems.push(it);
        }
    }
    var ansItems=[]; var ad=data.answer_days;
    for(var d=0;d<ad.length;d++){ var ln2=ad[d].lines; for(var i=0;i<ln2.length;i++)ansItems.push(ln2[i]); }

    var log=['=== 화이트북 실전문제 조판 ==='];
    log.push(new Date().toString());
    var bodyStory=findStoryByFirstStyle('문제');
    var ansStory=findStoryByFirstStyle('정답_문제 번호');
    log.push('본문:'+(bodyStory?'O':'X')+' 정답:'+(ansStory?'O':'X')+' | 본문items '+bodyItems.length+' 정답items '+ansItems.length);

    app.doScript(function(){
        if(bodyStory){
            var n=fillStory(bodyStory,bodyItems);
            // 문제별 break(1프레임 1문제) + Day별 페이지 break + 번호 리셋 — 문제 단락만 직접 접근
            var qIdx=[];
            for(var k=0;k<bodyItems.length;k++){ if(bodyItems[k].sty==='문제') qIdx.push(k); }
            var bp=bodyStory.paragraphs; var bpLen=bp.length;
            for(var j=0;j<qIdx.length;j++){
                var ki=qIdx[j]; if(ki>=bpLen) continue;
                var bi=bodyItems[ki];
                try{
                    if(bi.brk==='page') bp[ki].startParagraph=StartParagraph.NEXT_PAGE;
                    else if(bi.brk==='frame') bp[ki].startParagraph=StartParagraph.NEXT_FRAME;
                    if(bi.dayStart){ bp[ki].numberingContinue=false; bp[ki].numberingStartAt=1; }
                }catch(e){}
            }
            applyUnderline(bodyStory);
            var a=expandStory(bodyStory,'colfirst');
            log.push('본문조판완료 '+n+'단락, 페이지추가 '+a);
        }
        if(ansStory){ var n2=fillStory(ansStory,ansItems); applyUnderline(ansStory); var a2=expandStory(ansStory,'rowfirst'); log.push('정답조판완료 '+n2+'단락, 페이지추가 '+a2); }
        processLongQuestions();
        log.push('긴문제 처리 완료');
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '화이트북실전조판');

    var bo=0, ao=0;
    try{ var btc=bodyStory.textContainers; bo=btc[btc.length-1].overflows?1:0; }catch(e){}
    try{ var atc=ansStory.textContainers; ao=atc[atc.length-1].overflows?1:0; }catch(e){}
    log.push('페이지수:'+doc.pages.length);
    log.push('오버플로우:'+(bo+ao)+'개 (본문 '+bo+', 정답 '+ao+')');

    doc.save();
    log.push('저장 완료');
    var lf2=new File(outputDir+'/조판_로그.txt'); lf2.encoding='UTF-8'; lf2.open('w'); lf2.write(log.join('\n')); lf2.close();
    return "OK pages="+doc.pages.length;
    }catch(__e){ var ef=new File("/tmp/wb_err.txt"); ef.encoding="UTF-8"; ef.open("w"); ef.write("ERR: "+__e.message+" | line:"+(__e.line||"?")); ef.close(); return "ERROR:"+__e.message; }
})();
