// InDesign ExtendScript (.jsx)
// — 통합본 —  (모든 처리 끝난 뒤, 대괄호 문단만 [기본 단락]으로 변경)
(function(){
    if (app.documents.length === 0) { alert("문서 없음"); return; }
    if (app.selection.length === 0 || !app.selection[0].hasOwnProperty("parentStory")) { alert("스토리를 선택하세요."); return; }

    var doc = app.activeDocument;
    var story = app.selection[0].parentStory;

    // ---- 스타일 헬퍼 ----
    function ps(group, name){
        try{
            var g=doc.paragraphStyleGroups.itemByName(group);
            if(g&&g.isValid){
                var s=g.paragraphStyles.itemByName(name);
                if(s&&s.isValid) return s;
            }
        }catch(_){}
        return null;
    }
    function basicPara(){ // 기본 단락 탐지 강화
        try{ var s=doc.paragraphStyles.itemByName("$ID/NormalParagraphStyle"); if(s&&s.isValid) return s; }catch(_){}
        try{ var s2=doc.paragraphStyles.itemByName("[기본 단락]"); if(s2&&s2.isValid) return s2; }catch(_){}
        try{ var s3=doc.paragraphStyles.itemByName("[Basic Paragraph]"); if(s3&&s3.isValid) return s3; }catch(_){}
        try{ var s4=doc.paragraphStyles[0]; if(s4&&s4.isValid) return s4; }catch(_){}
        alert("기본 단락 스타일을 찾을 수 없습니다.");
        return null;
    }
    function csNone(){
        var cands=["[없음]","[None]","$ID/[No character style]"];
        for(var i=0;i<cands.length;i++){ try{ var s=doc.characterStyles.itemByName(cands[i]); if(s&&s.isValid) return s; }catch(_){} }
        try{ return doc.characterStyles[0]; }catch(_){ return null; }
    }

    var ST_START  = ps("STEP 01","B1_내용 정리");
    var ST_AFTER  = ps("STEP 01","B1_본문 박스");
    var ST_HADAN  = ps("STEP 01","하단 문제");
    var ST_JIMUN  = ps("STEP 01","하단 문제_지문");
    var ST_SEONJI = ps("STEP 01","하단 문제_선지");
    var ST_SUBJ   = ps("STEP 01","B1_내용 정리 주제");
    var ST_TITLE  = ps("STEP 01","B1_내용 정리 제목");
    var ST_BASIC  = basicPara();
    var CS_NONE   = csNone();

    // ---- 유틸 ----
    function paras(){ return story.paragraphs.everyItem().getElements(); }
    function ptxt(p){ return (p.contents||"").replace(/\r$/,""); }
    function isBracketPara(p){ return /^\s*\[[^\]]*\]/.test(ptxt(p)); } // 문두 '['
    function idxBeforeBracket(p){ var t=ptxt(p), i=t.indexOf("["); return (i<0?0:i); }
    function startsWithDaeum(p){ return /^(\s*[“”"'']*)다음/.test(ptxt(p)); }
    function idxBeforeD(p){ var m=/^(\s*[“”"'']*)다음/.exec(ptxt(p)); return m?m[1].length:0; }
    function hasCircled(p){ return /[\u2460-\u2473\u24F5-\u24FF\u2776-\u277F]/.test(ptxt(p)); }
    function isEnglishPara(p){ return /[A-Za-z]/.test(ptxt(p)); }
    function firstTextIndex(p){
        var n=p.characters.length, i=0;
        while(i<n){
            var c=""+p.characters[i].contents;
            if(c==="\uFFFC"||c===" "||c==="\u00A0"||/[“”"'’‘]/.test(c)){ i++; continue; }
            break;
        }
        return i;
    }

    // ---- 0) 전체 내용정리 + 문자스타일 [없음]으로 시작 ----
    if (ST_START){ try{ story.paragraphs.everyItem().appliedParagraphStyle = ST_START; }catch(_){ } }
    if (CS_NONE){  try{ story.characters.everyItem().appliedCharacterStyle = CS_NONE; }catch(_){ } }

    // ---- 0.5) "N강 N번 NNNNNN" 형식 헤더를 대괄호로 감싸기 ----
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^\\s*(\\d+\\s*강\\s*\\d+\\s*번\\s*\\d{6})\\s*$";
    app.changeGrepPreferences.changeTo = "[$1]";
    story.changeGrep();
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

    // ---- 1) 기존 ~R 제거 ----
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "~R";
    var old = story.findGrep(); for (var r=0;r<old.length;r++){ try{ old[r].remove(); }catch(_){} }
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

    // ---- 2) {주제}/{제목} 텍스트 정리 ----
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\{\\s*주제\\s*\\}"; app.changeGrepPreferences.changeTo = "주제"; story.changeGrep();
    app.findGrepPreferences.findWhat = "\\{\\s*제목\\s*\\}"; app.changeGrepPreferences.changeTo = "제목"; story.changeGrep();
    app.findGrepPreferences.findWhat = "^(주제|제목)\\s*\\r+"; app.changeGrepPreferences.changeTo = "$1 "; story.changeGrep();
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

    // ---- 3) 타겟 수집 & ~R 삽입 ----
    var P=paras(), bracketIdx=[];
    for (var k=0;k<P.length;k++) if (isBracketPara(P[k])) bracketIdx.push(k);
    var targets=[]; for (var b=1;b<bracketIdx.length;b++) targets.push({idx:bracketIdx[b], type:"br"});
    for (var d=0; d<P.length; d++) if (startsWithDaeum(P[d])) targets.push({idx:d, type:"daum"});
    targets.sort(function(a,b){ return b.idx - a.idx; });
    for (var t=0; t<targets.length; t++){
        P=paras(); var pi=targets[t].idx; if (pi<0||pi>=P.length) continue;
        var p=P[pi], off=(targets[t].type==="br")?idxBeforeBracket(p):idxBeforeD(p);
        try { p.insertionPoints[off].contents = SpecialCharacters.FRAME_BREAK; } catch(_){}
    }

    // ---- 4) 스타일 일괄 ----
    if (ST_SEONJI){ P=paras(); for (var s=0;s<P.length;s++) if (!startsWithDaeum(P[s]) && hasCircled(P[s])){ try{ P[s].appliedParagraphStyle=ST_SEONJI; P[s].keepOptions.keepAllLinesTogether=true; }catch(_){}}}
    if (ST_HADAN){ P=paras(); for (var h=0;h<P.length;h++) if (startsWithDaeum(P[h])){ try{ P[h].appliedParagraphStyle=ST_HADAN; }catch(_){}}}
    if (ST_JIMUN){ P=paras(); for (var m=0;m<P.length-1;m++) if (startsWithDaeum(P[m]) && isEnglishPara(P[m+1])){ try{ P[m+1].appliedParagraphStyle=ST_JIMUN; }catch(_){}}}
    if (ST_AFTER){ P=paras(); for (var j=0;j<P.length-1;j++) if (isBracketPara(P[j])){ try{ P[j+1].appliedParagraphStyle=ST_AFTER; }catch(_){}}}

    try{ story.recompose(); }catch(_){}

    // ---- 5-A) “다음 …” 아이콘 인라인 + 뒤 탭 ----
    function findLabeledItem(label){
        var items = doc.allPageItems, it;
        for (var ii=0; ii<items.length; ii++){ it=items[ii]; try{ if (it.label === label) return it; }catch(_){ } }
        return null;
    }
    (function(){
        var src = findLabeledItem("STEP1 문제아이콘"); if(!src) return;
        var wasLocked = src.locked; src.locked=false;
        try{ if(src.itemLayer){ src.itemLayer.locked=false; src.itemLayer.visible=true; } }catch(_){}
        P=paras();
        for (var i3=0;i3<P.length;i3++){
            if(!startsWithDaeum(P[i3])) continue;
            try{
                app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat="~R";
                var found=P[i3].texts[0].findGrep();
                app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
                var ip=(found&&found.length)?found[0].insertionPoints[-1]:P[i3].insertionPoints[idxBeforeD(P[i3])];

                // 중복 방지
                try{
                    var idx=ip.index, ch=P[i3].characters[idx];
                    if(ch && (""+ch.contents)==="\uFFFC"){
                        var aft=P[i3].characters[idx+1];
                        if(!aft || (""+aft.contents)!=="\t"){ P[i3].insertionPoints[idx+1].contents=SpecialCharacters.TAB; }
                        continue;
                    }
                }catch(_){}

                var icon=src.duplicate();
                try{
                    icon.anchoredObjectSettings.anchoredPosition=AnchorPosition.INLINE_POSITION;
                    icon.textWrapPreferences.textWrapMode=TextWrapModes.NONE;
                }catch(_){}
                icon.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
                try{ icon.fit(FitOptions.FRAME_TO_CONTENT); }catch(_){}
                P[i3].insertionPoints[ip.index+1].contents=SpecialCharacters.TAB;
            }catch(_){}
        }
        src.locked=wasLocked;
    })();

    // ---- 5-B) {주제}/{제목} 라벨 + 전용 스타일 + 아래 영어문단 탭(내용정리 유지) ----
    (function(){
        P=paras();
        for (var a=0;a<P.length;a++){
            var s=ptxt(P[a]);

            if(/^\s*\{?\s*주제\s*\}?(\s|$)/.test(s)){
                try{
                    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
                    app.findGrepPreferences.findWhat="^(\\s*)\\{?\\s*주제\\s*\\}?\\s*";
                    app.changeGrepPreferences.changeTo="{주제} ";
                    P[a].changeGrep();
                    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
                }catch(_){}
                if(ST_SUBJ){ try{ P[a].appliedParagraphStyle=ST_SUBJ; }catch(_){ } }

                var j=a+1;
                while(j<P.length){
                    var p2=P[j], s2=ptxt(p2);
                    if(!isEnglishPara(p2)||startsWithDaeum(p2)||isBracketPara(p2)||/^\s*$/.test(s2)) break;
                    try{
                        var idx=firstTextIndex(p2);
                        var head=p2.characters.length>idx?(""+p2.characters[idx].contents):"";
                        if(head!=="\t"){ p2.insertionPoints[idx].contents=SpecialCharacters.TAB; }
                        if(ST_START) p2.appliedParagraphStyle=ST_START;
                    }catch(_){}
                    j++;
                }
                continue;
            }

            if(/^\s*\{?\s*제목\s*\}?(\s|$)/.test(s)){
                try{
                    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
                    app.findGrepPreferences.findWhat="^(\\s*)\\{?\\s*제목\\s*\\}?\\s*";
                    app.changeGrepPreferences.changeTo="{제목} ";
                    P[a].changeGrep();
                    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
                }catch(_){}
                if(ST_TITLE){ try{ P[a].appliedParagraphStyle=ST_TITLE; }catch(_){ } }

                var j2=a+1;
                while(j2<P.length){
                    var p3=P[j2], s3=ptxt(p3);
                    if(!isEnglishPara(p3)||startsWithDaeum(p3)||isBracketPara(p3)||/^\s*$/.test(s3)) break;
                    try{
                        var idx2=firstTextIndex(p3);
                        var head2=p3.characters.length>idx2?(""+p3.characters[idx2].contents):"";
                        if(head2!=="\t"){ p3.insertionPoints[idx2].contents=SpecialCharacters.TAB; }
                        if(ST_START) p3.appliedParagraphStyle=ST_START;
                    }catch(_){}
                    j2++;
                }
            }
        }
    })();

    // ---- 6) '다음 글의' 앞 탭(없을 때만) + 전각공백 보정 ----
    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat="(?<!\\t)다음\\s*글의";
    app.changeGrepPreferences.changeTo="\t$0"; story.changeGrep();
    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat="(?<!\\u2003)\\t(?=다음\\s*글의)";
    app.changeGrepPreferences.changeTo="\u2003"; story.changeGrep();
    app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;

    // =========================
    // ===== 마지막 단계 ======
    // =========================
    // 7) 모든 처리가 끝난 후, "문단 맨 앞이 대괄호로 시작하는" 문단은 전부 [기본 단락]으로 변경
    (function(){
        if (!ST_BASIC) return;
        var P2 = story.paragraphs.everyItem().getElements();
        for (var i=0;i<P2.length;i++){
            try{
                // 앵커·BOM 제거 + 광범위한 공백 제거 후 검사
                var s = (P2[i].contents || "")
                    .replace(/\r$/,"")
                    .replace(/[\uFFFC\uFEFF]/g,"")
                    .replace(/^[\s\u00A0\u2000-\u200B]+/,"");
                // ASCII '[' 또는 전각 '［' 모두 허용
                if (/^[\[\uFF3B]/.test(s)) {
                    P2[i].appliedParagraphStyle = ST_BASIC;
                }
            }catch(_){}
        }
        try{ story.recompose(); }catch(_){}
    })();

})();