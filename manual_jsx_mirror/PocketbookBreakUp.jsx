/* ===== PocketbookBreakUp.jsx (KR InDesign / iMac) =====
   요구사항
   - 문자스타일 "챕터", "챕터_숫자":
     · BreakUp(복제/이동/삭제)에는 절대 포함 X → 해당 스토리는 통째로 스킵
     · GREP 정리에는 스토리를 스킵하지 않음(본문은 처리), 단 매치가 두 스타일과 겹치면 그 매치만 스킵
*/

(function(){
    if (app.documents.length === 0){ alert("문서 없음"); return; }

    // ---------- 유틸 ----------
    function resetFC(){ try{ app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING; }catch(_){ } }
    function mm(v){ return v * 2.834645669; }
    function getStartPage(story){
        try{ var c=story.textContainers[0]; if(c && c.parentPage) return c.parentPage; }catch(_){}
        try{ return story.parent.parent.pages[0]; }catch(_){ return app.activeDocument.pages[0]; }
    }
    function getBounds(tf){ try{ return tf.geometricBounds; }catch(_){ return [20,20,200,200]; } }
    function isOnMaster(tf){
        try{ var pg=tf.parentPage; if(!pg) return false; var par=pg.parent; return (par && par.constructor && par.constructor.name==="MasterSpread"); }
        catch(_){ return false; }
    }
    function isMasterStory(story){
        try{ if(!story || !story.textContainers || story.textContainers.length===0) return false; return isOnMaster(story.textContainers[0]); }
        catch(_){ return false; }
    }
    function isLeftPage(pg){ try{ return (pg && pg.side===PageSideOptions.LEFT_HAND); }catch(_){ return false; } }
    // 기준 좌표: X=20mm, Y=29.5mm, 허용 ±10mm
    function isTargetFrame(tf){
        if(!tf || !tf.isValid) return false;
        try{
            var gb=tf.geometricBounds, x1=gb[1], y1=gb[0];
            var TX=mm(20), TY=mm(29.5), TOL=mm(10);
            return Math.abs(x1-TX)<=TOL && Math.abs(y1-TY)<=TOL;
        }catch(_){ return false; }
    }

    // 문자스타일 찾기(그룹 포함)
    function findCharStyle(doc, name){
        function scanGroup(g){
            try{ var cs=g.characterStyles.itemByName(name); if(cs && cs.isValid) return cs; }catch(_){}
            try{
                var gs=g.characterStyleGroups;
                for (var i=0;i<gs.length;i++){ var hit=scanGroup(gs[i]); if(hit) return hit; }
            }catch(_){}
            return null;
        }
        try{ var cs0=doc.characterStyles.itemByName(name); if(cs0 && cs0.isValid) return cs0; }catch(_){}
        try{
            var roots=doc.characterStyleGroups;
            for (var j=0;j<roots.length;j++){ var h=scanGroup(roots[j]); if(h) return h; }
        }catch(_){}
        return null;
    }

    var doc = app.activeDocument;
    var CS_EX1 = findCharStyle(doc, "챕터");
    var CS_EX2 = findCharStyle(doc, "챕터_숫자");
    var EXCLUDES = [];
    if (CS_EX1 && CS_EX1.isValid) EXCLUDES.push(CS_EX1);
    if (CS_EX2 && CS_EX2.isValid) EXCLUDES.push(CS_EX2);

    // 스토리에 제외 스타일이 "하나라도" 있으면 true (BreakUp 단계에서만 사용)
    function storyHasExcludedStyle(story){
        try{
            if (!EXCLUDES.length) return false;
            resetFC();
            for (var i=0;i<EXCLUDES.length;i++){
                try{
                    app.findGrepPreferences.appliedCharacterStyle = EXCLUDES[i];
                    app.findGrepPreferences.findWhat = ".+";
                    var hits = story.findGrep();
                    resetFC();
                    if (hits && hits.length>0) return true;
                }catch(_){ resetFC(); }
            }
        }catch(_){ resetFC(); }
        return false;
    }

    // GREP 치환(마스터 제외) — "스토리 스킵 없음", 매치 단위로 제외 스타일 교차 시 스킵
    function changeGrepPerStoryCurrentPrefs(doc){
        var exId = {};
        for (var e=0;e<EXCLUDES.length;e++){ try{ exId[EXCLUDES[e].id] = true; }catch(_){} }

        var sts = doc.stories.everyItem().getElements();
        for (var i=0;i<sts.length;i++){
            var st = sts[i];
            if (!st || !st.isValid) continue;
            if (isMasterStory(st)) continue;

            try{
                var matches = st.findGrep(); // 현재 findGrepPreferences 기준
                if (!matches || !matches.length) continue;

                for (var m=0;m<matches.length;m++){
                    var t = matches[m];
                    var skip=false;
                    if (EXCLUDES.length){
                        try{
                            var chs=t.characters.everyItem().getElements();
                            for (var c=0;c<chs.length;c++){
                                var cs=null; try{ cs=chs[c].appliedCharacterStyle; }catch(_){}
                                if (cs && cs.isValid && exId[cs.id]){ skip=true; break; }
                            }
                        }catch(_){}
                    }
                    if (!skip){ try{ t.changeGrep(); }catch(_){ } }
                }
            }catch(_){}
        }
        resetFC();
    }

    // --------- 행 필터 / 흐름 ---------
    function filterParagraphs(astrStory, keepFn){
        var paras = astrStory.paragraphs.everyItem().getElements();
        for (var i=paras.length-1;i>=0;i--){
            var p=paras[i], raw=(p&&p.contents)?(p.contents+""):"";
            var t=raw.replace(/[\r\n]+$/,'').replace(/^\s+|\s+$/g,"");
            if(!keepFn(t)){ try{ p.remove(); }catch(_){ } }
        }
        // 새 스토리 내부의 빈문단 정리
        resetFC();
        app.findGrepPreferences.findWhat = "^(?:[\\t \\x{00A0}\\x{2000}-\\x{200B}\\x{3000}]*)(?=\\r)";
        app.changeGrepPreferences.changeTo = "";
        try{ astrStory.changeGrep(); }catch(_){}
        resetFC();
    }
    function isKoreanLine(t){ return /[가-힣]/.test(t); }
    function isEnglishLine(t){ return !/[가-힣]/.test(t) && /[A-Za-z]/.test(t); }

    function flowOverset(tf, bringFront){
        var gb0=tf.geometricBounds;
        var _doc=tf.parent.parent;
        if (bringFront){ try{ tf.bringToFront(); }catch(_){} }
        while (tf.overflows){
            var last=_doc.pages[-1];
            var np=_doc.pages.add(LocationOptions.AFTER,last);
            var nt=np.textFrames.add({ geometricBounds: gb0 });
            tf.nextTextFrame=nt; tf=nt;
            if (bringFront){ try{ tf.bringToFront(); }catch(_){} }
        }
    }

    // --------- 본 처리: BreakUp (챕터/숫자 포함 스토리는 통째로 스킵) ---------
    var stories = doc.stories.everyItem().getElements();
    for (var s=0; s<stories.length; s++){
        var story = stories[s];
        try{
            if (!story || !story.isValid) continue;
            if (!story.textContainers || story.textContainers.length===0) continue;
            if (isMasterStory(story)) continue;

            // ★ 이동/복제/삭제가 발생하는 BreakUp 단계에서는 제외 스토리 완전 스킵
            if (storyHasExcludedStyle(story)) continue;

            // 기준 프레임 선택
            var baseTF=null;
            try{
                var tcs=story.textContainers;
                for (var ti=0; ti<tcs.length; ti++){
                    var _tf=tcs[ti]; if(!_tf||!_tf.isValid) continue;
                    if (isOnMaster(_tf)) continue;
                    if (isLeftPage(_tf.parentPage) && isTargetFrame(_tf)){ baseTF=_tf; break; }
                }
                if(!baseTF){
                    for (var tj=0; tj<tcs.length; tj++){
                        var _tf2=tcs[tj]; if(!_tf2||!_tf2.isValid) continue;
                        if (isOnMaster(_tf2)) continue;
                        if (isLeftPage(_tf2.parentPage)){ baseTF=_tf2; break; }
                    }
                }
                if(!baseTF){
                    for (var tk=0; tk<tcs.length; tk++){
                        var _tf3=tcs[tk]; if(!_tf3||!_tf3.isValid) continue;
                        if (isOnMaster(_tf3)) continue;
                        baseTF=_tf3; break;
                    }
                }
            }catch(_){}
            if(!baseTF) continue;

            var startPage=getStartPage(story);
            var gb=getBounds(baseTF);
            var gap=10, height=gb[2]-gb[0];
            var engGb=[gb[0],gb[1],gb[2],gb[3]];
            var korGb=[gb[0]+height+gap,gb[1],gb[2]+height+gap,gb[3]];

            var engTF=startPage.textFrames.add({ geometricBounds: engGb });
            var korTF=startPage.textFrames.add({ geometricBounds: korGb });
            try{ korTF.bringToFront(); }catch(_){}

            // 자동 번호 해제(원본 스토리)
            try{
                var _pps=story.paragraphs.everyItem().getElements();
                for (var _pi=0; _pi<_pps.length; _pi++){
                    var _p=_pps[_pi];
                    try{
                        if (_p.bulletsAndNumberingListType && _p.bulletsAndNumberingListType != ListType.NO_LIST){
                            _p.bulletsAndNumberingListType = ListType.NO_LIST;
                        }
                    }catch(_){}
                }
            }catch(_){}

            // 서식 유지 복제
            story.texts[0].duplicate(LocationOptions.AT_BEGINNING, engTF.insertionPoints[0]);
            story.texts[0].duplicate(LocationOptions.AT_BEGINNING, korTF.insertionPoints[0]);

            // 필터링
            filterParagraphs(engTF.parentStory, isEnglishLine);
            filterParagraphs(korTF.parentStory, isKoreanLine);

            // 흘리기
            flowOverset(engTF,false);
            flowOverset(korTF,true);

            // 원본 프레임 삭제
            try{
                var tcs2=story.textContainers;
                for (var i0=0;i0<tcs2.length;i0++){ try{ tcs2[i0].remove(); }catch(_){} }
            }catch(_){}
        }catch(_){}
    }

    // --------- Pocketbook 정리(스토리 스킵 없음 / 매치 단위 제외) ---------
    // 1) 문자스타일 "지문 번호" 숫자 삭제
    (function deletePassageNumbers(){
        var targetCS = findCharStyle(doc, "지문 번호");
        if (!(targetCS && targetCS.isValid)) return;
        resetFC();
        app.findGrepPreferences.appliedCharacterStyle = targetCS;
        app.findGrepPreferences.findWhat = "[0-9\\x{FF10}-\\x{FF19}]+";
        app.changeGrepPreferences.changeTo = "";
        changeGrepPerStoryCurrentPrefs(doc);  // ← 스토리 스킵 없음
        resetFC();
    })();

    // 2) "~+" + 한 칸 제거
    (function removeTildePlus(){
        resetFC();
        app.findGrepPreferences.findWhat = "~+ ?";
        app.changeGrepPreferences.changeTo = "";
        changeGrepPerStoryCurrentPrefs(doc);
        resetFC();
    })();

    // 3) \r → 공백
    (function returnToSpace(){
        resetFC();
        app.findGrepPreferences.findWhat = "\\r";
        app.changeGrepPreferences.changeTo = " ";
        changeGrepPerStoryCurrentPrefs(doc);
        resetFC();
    })();

    // 4) \t → 공백
    (function tabToSpace(){
        resetFC();
        app.findGrepPreferences.findWhat = "\\t";
        app.changeGrepPreferences.changeTo = " ";
        changeGrepPerStoryCurrentPrefs(doc);
        resetFC();
    })();

    // 5) 연속 공백 2칸+ → 1칸
    (function squeezeSpaces(){
        resetFC();
        app.findGrepPreferences.findWhat = "[ \\x{00A0}\\x{2000}-\\x{200B}\\x{3000}]{2,}";
        app.changeGrepPreferences.changeTo = " ";
        changeGrepPerStoryCurrentPrefs(doc);
        resetFC();
    })();

    alert("완료: BreakUp은 '챕터/챕터_숫자' 스토리를 완전 제외, GREP 정리는 본문만 골라 정상 적용했습니다.");
})();
