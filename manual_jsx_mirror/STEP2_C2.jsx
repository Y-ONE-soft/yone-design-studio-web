// InDesign ExtendScript (JSX) — STEP02 영작 배열 파이프라인 (슬래시 전용·아이콘 단순·빈칸 정리)
(function(){
    if (app.documents.length === 0){ alert("열린 문서가 없습니다."); return; }
    if (app.selection.length === 0){ alert("텍스트를 선택하거나 커서를 문단에 두세요."); return; }

    // --- 선택 스토리 확보 ---
    var sel = app.selection[0], story = null;
    try{
        if (sel.hasOwnProperty("insertionPoints")) story = sel.parentStory;
        else if (sel instanceof TextFrame)          story = sel.parentStory;
        else if (sel.hasOwnProperty("parentStory")) story = sel.parentStory;
    }catch(_){}
    if(!story){ alert("선택에서 스토리를 찾지 못했습니다. 텍스트 안을 클릭하세요."); return; }

    var doc = app.activeDocument;

    // ---------- 헬퍼 ----------
    function csNone(){ try{ return doc.characterStyles[0]; }catch(_){ return null; } } // [없음]
    function basicPara(){
        try{ var s = doc.paragraphStyles.itemByName("$ID/NormalParagraphStyle"); if (s && s.isValid) return s; }catch(_){}
        try{ return doc.paragraphStyles[0]; }catch(_){ return null; }
    }
    function ps(group, name){
        try{
            var g = doc.paragraphStyleGroups.itemByName(group);
            if (g && g.isValid){
                var s = g.paragraphStyles.itemByName(name);
                if (s && s.isValid) return s;
            }
        }catch(_){}
        return null;
    }
    function findTemplateItemByLabel(label){
        try{
            var items = doc.pageItems.everyItem().getElements();
            for (var i=0;i<items.length;i++){
                var L = (items[i].label||"").replace(/^\s+|\s+$/g,"");
                if (L === label) return items[i];
            }
        }catch(_){}
        return null;
    }
    function resetGrep(){ app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING; }

    app.scriptPreferences.enableRedraw = false;

    app.doScript(function(){

        // 0) 문자/단락 초기화
        try{ var none = csNone();  if(none)  story.characters.everyItem().appliedCharacterStyle = none; }catch(_){}
        try{ var basic = basicPara(); if(basic) story.paragraphs.everyItem().appliedParagraphStyle = basic; }catch(_){}

        // 대상 스타일
        var PS_NUM  = ps("STEP 02", "C2_영작 배열 번호");
        var PS_VIEW = ps("STEP 02", "C2_영작 배열 보기");
        if(!PS_NUM){  alert("단락스타일 'STEP 02 / C2_영작 배열 번호'가 없습니다."); throw Error("Missing style"); }
        if(!PS_VIEW){ alert("단락스타일 'STEP 02 / C2_영작 배열 보기'가 없습니다."); throw Error("Missing style"); }

        // 1) 한글≥2 포함 → 번호
        var reKor2 = /[가-힣][\s\S]*[가-힣]/;
        var paras = story.paragraphs;
        for (var i=0; i<paras.length; i++){
            var p = paras[i], txt = p.contents || "";
            if (reKor2.test(txt)){ try{ p.applyParagraphStyle(PS_NUM, true); }catch(_){} }
        }

        // 2) 슬래시 포함 “단락만” → 보기 (그 외에 보기 섞여 있으면 기본으로 원복)
        var viewIdx = [];
        var BPAR = basicPara();
        for (var j=0; j<paras.length; j++){
            var p2 = paras[j], raw = p2.contents || "";
            var hasSlash = raw.indexOf("/") !== -1;
            var cur = p2.appliedParagraphStyle;
            var isViewNow = (cur===PS_VIEW)||(cur&&PS_VIEW&&cur.name===PS_VIEW.name);

            if (hasSlash){
                try{ p2.applyParagraphStyle(PS_VIEW, true); viewIdx.push(j); }catch(_){}
            } else if (isViewNow){
                // 잘못 붙어 있던 '보기' 제거
                try{ if (BPAR) p2.applyParagraphStyle(BPAR, true); }catch(_){}
            }
        }

        // 3) 슬래시로 '보기'가 된 단락 “바로 아래”에만 아이콘 인라인 삽입
        (function(){
            var src = findTemplateItemByLabel("STEP2 영작 답지");
            if (!src) return;

            // 원본/레이어 잠금 해제
            var srcLocked=null, srcLayerLocked=null;
            try{ srcLocked = src.locked; src.locked=false; }catch(_){}
            try{ if (src.itemLayer){ srcLayerLocked = src.itemLayer.locked; src.itemLayer.locked=false; src.itemLayer.visible=true; } }catch(_){ }

            try{
                for (var t=0; t<viewIdx.length; t++){
                    var vi = viewIdx[t];

                    // 다음 문단이 없으면 생성
                    if (vi >= story.paragraphs.length-1){
                        try{ story.paragraphs[vi].insertionPoints[-1].contents = "\r"; }catch(_){}
                    }
                    // 재취득
                    var nextP = story.paragraphs[vi+1];
                    if (!nextP) continue;

                    // 중복 앵커 있으면 스킵
                    var already=false;
                    try{
                        var chs=nextP.characters;
                        for (var c=0;c<chs.length;c++){
                            if (chs[c].contents===SpecialCharacters.ANCHOR_MARKER){
                                var pi = chs[c].pageItems[0];
                                if (pi && (pi.label==="STEP2 영작 답지" || pi.extractLabel("STEP2 영작 답지")!=="")) { already=true; break; }
                            }
                        }
                    }catch(_){}
                    if (already) continue;

                    // 인라인 삽입
                    try{
                        var dup = src.duplicate();
                        try { dup.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION; } catch(_){}
                        try { dup.textWrapPreferences.textWrapMode = TextWrapModes.NONE; } catch(_){}
                        try { dup.anchoredObjectSettings.insertAnchoredObject(nextP.insertionPoints[0], AnchorPosition.INLINE_POSITION); }
                        catch(_ins){
                            try{
                                nextP.insertionPoints[0].contents = SpecialCharacters.ANCHOR_MARKER;
                                var mark = nextP.characters[0];
                                dup.move(LocationOptions.AFTER, mark);
                            }catch(_mv){}
                        }
                        try { dup.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}
                        try { dup.label = "STEP2 영작 답지"; } catch(_){}
                    }catch(_place){}
                }
            }finally{
                try{ if (src && srcLocked!==null) src.locked = srcLocked; }catch(_){}
                try{ if (src && src.itemLayer && srcLayerLocked!==null) src.itemLayer.locked = srcLayerLocked; }catch(_){}
            }
        })();

        // 3x) 잔여 빈칸 정리: 앵커 없는 순수 빈 단락(공백/CR만) 삭제
        try{
            for (var zz = story.paragraphs.length - 1; zz >= 0; zz--){
                var zp = story.paragraphs[zz], zs = zp.contents || "";
                // 앵커 있으면 유지
                var hasAnchor=false;
                try{ var zc=zp.characters; for (var z=0; z<zc.length; z++){ if (zc[z].contents===SpecialCharacters.ANCHOR_MARKER){ hasAnchor=true; break; } } }catch(_){}
                if (hasAnchor) continue;
                if (zs.replace(/[\\s\\u00A0]+/g,"")===""){ try{ zp.remove(); }catch(_rm){} }
            }
        }catch(_clean){}

        // 4) '[' 앞 FRAME_BREAK (첫 '[' 스킵) + 대괄호 문단 [기본 단락]
        try{
            var basicB = basicPara();
            resetGrep();
            app.findGrepPreferences.findWhat = "\\[";
            var hits = story.findGrep();
            if (hits && hits.length){
                for (var h = hits.length - 1; h >= 1; h--){
                    try{
                        var ip = hits[h].insertionPoints[0];
                        var idx = ip.index;
                        if (idx > 0){
                            var prev = ip.parent.characters[idx-1];
                            if (!(prev && prev.contents === SpecialCharacters.FRAME_BREAK)){
                                ip.contents = SpecialCharacters.FRAME_BREAK;
                            }
                        }
                        if (basicB){ try { ip.paragraphs[0].applyParagraphStyle(basicB, true); } catch(__){} }
                    }catch(_one){}
                }
            }
            resetGrep();
            for (var m=0; m<story.paragraphs.length; m++){
                var tt = story.paragraphs[m].contents || "";
                if (tt.indexOf("[") !== -1 || tt.indexOf("]") !== -1){
                    try{ story.paragraphs[m].applyParagraphStyle(basicB, true); }catch(_p){}
                }
            }
        }catch(_br){}

        // 5) 슬래시 없는 영어 전용 단락 삭제 (앵커/정답 보호)
        try{
            for (var r = story.paragraphs.length - 1; r >= 0; r--){
                var pr = story.paragraphs[r], s = pr.contents || "";

                // 앵커 있으면 금지
                var hasAnchor=false;
                try{ var ch=pr.characters; for (var c=0;c<ch.length;c++){ if (ch[c].contents===SpecialCharacters.ANCHOR_MARKER){ hasAnchor=true; break; } } }catch(_){}
                if (hasAnchor) continue;

                // 완전 빈 줄은 이미 3x에서 정리했으므로 여기선 패스
                var plain = (s+"").replace(/[\\s\\u00A0]+/g,"");
                if (plain.length===0) continue;

                var isEnglishOnly = /[A-Za-z]/.test(s) && !/[가-힣]/.test(s) && s.indexOf('/') === -1;

                // 대괄호 제목([Further Reading], [Reading More] 등)은 보호
                var hasBracket = (s.indexOf("[") !== -1 && s.indexOf("]") !== -1);
                if (hasBracket) continue;

                if (isEnglishOnly){
                    // 직전 문단이 '보기'면 정답이므로 보호
                    try{
                        var prevP = (r>0) ? story.paragraphs[r-1] : null;
                        if (prevP){
                            var a = prevP.appliedParagraphStyle;
                            var isView = (a===PS_VIEW)||(a&&PS_VIEW&&a.name===PS_VIEW.name);
                            if (isView) continue;
                        }
                    }catch(_chk){}
                    try{ pr.remove(); }catch(_rm){}
                }
            }
        }catch(_del){}

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP02 영작 배열(슬래시전용/아이콘단순/빈칸정리)");

    app.scriptPreferences.enableRedraw = true;
})();