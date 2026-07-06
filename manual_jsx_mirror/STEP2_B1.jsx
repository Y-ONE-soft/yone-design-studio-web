// ===== InDesign ExtendScript (JSX) =====
// 순서: (1) 선택 스토리에 STEP 02 / B1_어법 OX 적용
//       (2) 머리말(예: "01. L3-본문1" 또는 "01. p3-no.2") 기준으로 위쪽 비어있지 않은 문단 끝에 FRAME_BREAK 삽입
//           + 사이 빈 단락 삭제 + 머리말 단락/하위 빈 단락 삭제  ← (정규식 강화 + p\d+-no.\d+ 지원)
//       (3) TF 버튼 인라인 부착(+보정, 트래킹 한도 -50)
//       (4) ★ 모든 정리 작업이 끝난 뒤, Samples/JavaScript/SplitStory.jsx 실행으로 스토리 분리

(function(){
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    if (app.selection.length === 0 || !("parentStory" in app.selection[0])) {
        alert("텍스트 프레임(또는 그 안의 텍스트)을 선택하세요.");
        return;
    }

    var doc   = app.activeDocument;
    var story = app.selection[0].parentStory;

    // ---------- 1) 단락 스타일 적용 ----------
    function getParagraphStyleFlexible(groupName, styleName){
        try{
            var grp = doc.paragraphStyleGroups.itemByName(groupName);
            if (grp && grp.isValid){
                var st = grp.paragraphStyles.itemByName(styleName);
                if (st && st.isValid) return st;
            }
        }catch(_){}
        try{
            var st2 = doc.paragraphStyles.itemByName(styleName);
            if (st2 && st2.isValid) return st2;
        }catch(_){}
        return null;
    }
    var targetStyle = getParagraphStyleFlexible("STEP 02", "B1_어법 OX");
    if (targetStyle){
        try { story.paragraphs.everyItem().appliedParagraphStyle = targetStyle; } catch(_){}
    } else {
        alert("단락 스타일을 찾을 수 없습니다: [STEP 02] / B1_어법 OX");
    }

    // ---------- 2) 브레이크/정리 (헤더 정규식 확장) ----------
    (function(){
        function isBlankPara(p){
            var t = (p.contents||"").replace(/[\s\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\r\n\t]+/g,"");
            return t === "";
        }
        // reHeader 확장:
        //  - L\d+-본문\d+ (하이픈 변종/공백 허용)
        //  - p\d+-no.\d+ (대소문자 무시, 하이픈/공백 유연)
        var reHeader = /^\s*(?:\d+\s*[.)]?\s*)?(?:L\s*\d+\s*[-–—﹣−]?\s*(?:p\.?\s*\d+\s*)?(?:[-–—﹣−]?\s*)?(?:본문\s*\d+|p\.?\s*\d+(?:\s+[^\r\n]+)?|[^\r\n]+)?|p\s*\d+\s*[-–—﹣−]?\s*no\.?\s*\d+|p\s*\d+\s*[-–—﹣−]?\s*(?:서술형|논술형)\s*Prac(?:tice|ice)|p\s*\d+\s*[-–—﹣−]+\s*수능\s*대비\s*ANALYSIS)\s*$/i;
        var reSupp   = /^\s*Supplementary\s+Reading\s*$/i;
        var reGangBeon = /^\s*\d+\s*강\s*\d+\s*번\s*\d{6}\s*$/; // "7강 4번 200324"

        app.doScript(function(){
            var paras = story.paragraphs;

            for (var i = paras.length - 1; i >= 0; i--) {
                paras = story.paragraphs;
                if (i >= paras.length) continue;

                var header = paras[i];
                if (header.parentStory !== story) continue;

                var htxt = header.contents || "";
                if (!(reHeader.test(htxt) || reSupp.test(htxt) || reGangBeon.test(htxt))) continue;

                // 위쪽에서 가장 가까운 '비어있지 않은' 문단
                var top = i - 1;
                while (top >= 0 && paras[top].parentStory === story && isBlankPara(paras[top])) top--;

                if (top >= 0) {
                    // 해당 문단 끝의 리턴 '앞'에 FRAME_BREAK (중복 방지)
                    try {
                        var ipBeforeCR = paras[top].insertionPoints[-2];
                        var lastBeforeCR = paras[top].characters.length > 1 ? paras[top].characters[-2] : null;
                        var already = (lastBeforeCR && lastBeforeCR.contents === SpecialCharacters.FRAME_BREAK);
                        if (!already) ipBeforeCR.contents = SpecialCharacters.FRAME_BREAK;
                    } catch(_){}

                    // 사이의 빈 단락들 삭제
                    for (var k = top + 1; k < i; k++) {
                        if (k >= story.paragraphs.length) break;
                        var mid = story.paragraphs[k];
                        if (mid.parentStory !== story) break;
                        if (isBlankPara(mid)) { try { mid.remove(); k--; i--; } catch(__){} }
                    }
                } else {
                    // 스토리 첫 문단이 헤더인 경우도 단락 자체 삭제
                    try { header.remove(); } catch(__){}
                }
                try { header.remove(); } catch(__){}

                // 아래 연속 빈 단락 삭제
                paras = story.paragraphs;
                var down = Math.min(i, paras.length - 1);
                while (down < paras.length && paras[down].parentStory === story) {
                    if (!isBlankPara(paras[down])) break;
                    try { paras[down].remove(); } catch(__){ break; }
                    paras = story.paragraphs;
                }
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Break & cleanup before headers");
    })();

    // ---------- 3) TF 버튼 인라인 부착(+보정) ----------
    function recompose(){ try{ story.recompose(); }catch(_){ } }
    function isAnchorAtLineStart(idx){
        recompose();
        try { var line = story.characters[idx].lines[0]; return story.characters[idx].index === line.characters[0].index; }
        catch(_){ return false; }
    }
    function lastWordRangeBefore(idx){
        var end = idx - 1; if (end < 0) return null;
        var skip = {" ":1,"\u00A0":1,"\u2009":1,"\t":1,".":1,",":1,";":1,":":1,")":1,"]":1,"}":1,"’":1,"”":1,"\"":1,"'":1};
        while (end >= 0 && (story.characters[end].contents in skip)) end--;
        if (end < 0) return null;
        var start = end; while (start >= 0){ var ch = story.characters[start].contents; if (ch===" "||ch==="\u00A0"||ch==="\u2009"||ch==="\t") break; start--; }
        start++; if (start > end) return null;
        return { rng: story.characters.itemByRange(start, end), start: start, end: end };
    }
    function tightenToKeepOnSameLine(anchorIdx){
        var info = lastWordRangeBefore(anchorIdx); if (!info) return false;
        var rng = info.rng;
        var TRACK_STEP=5, TRACK_MAX=80, SCALE_STEP=1, SCALE_MIN=85, startScale=100;
        for (var t=TRACK_STEP; t<=TRACK_MAX; t+=TRACK_STEP){ try{ rng.tracking = -t; }catch(_){ } recompose(); if (!isAnchorAtLineStart(anchorIdx)) return true; }
        try{ startScale = rng.horizontalScale || 100; }catch(_){}
        for (var s=startScale-SCALE_STEP; s>=SCALE_MIN; s-=SCALE_STEP){
            try{ rng.characters.everyItem().horizontalScale = s; }catch(_){}
            recompose(); if (!isAnchorAtLineStart(anchorIdx)) return true;
        }
        return false;
    }
    function bindWithPrevWord(anchorIdx){
        var info = lastWordRangeBefore(anchorIdx); if (!info) return;
        var iSpace = info.start - 1;
        try{ var c = story.characters[iSpace].contents; if (c===" "||c==="\u2009"||c==="\t") story.characters[iSpace].contents = "\u00A0"; }catch(_){}
        try{ story.characters.itemByRange(info.start, anchorIdx).noBreak = true; }catch(_){}
        recompose();
    }

    // 'TF 버튼' 라벨의 이미지 프레임(링크) 찾기 + 기준 너비
    var tfLinkPath=null, tfWidth=null;
    for (var gi = 0; gi < doc.allGraphics.length; gi++) {
        var g = doc.allGraphics[gi];
        try {
            if (g.parent && g.parent.label === "TF 버튼" && g.itemLink) {
                tfLinkPath = g.itemLink.filePath;
                var gb = g.parent.geometricBounds; tfWidth = gb[3] - gb[1];
                break;
            }
        } catch(_){}
    }
    if (!tfLinkPath) {
        alert("라벨이 'TF 버튼'인 '이미지 프레임(링크)'을 문서에 하나 배치하세요.");
        return;
    }

    var ADD_SPACE = true;
    var paras = story.paragraphs;
    for (var pIdx = paras.length - 1; pIdx >= 0; pIdx--) {
        var p = paras[pIdx];
        if (p.contents === "\r" || p.characters.length < 2) continue;

        var hasAnchorAtEnd=false; 
        try{ hasAnchorAtEnd = (p.characters[-2].contents === "\uFFFC"); }catch(_){}
        var ip = p.insertionPoints[-2];

        if (!hasAnchorAtEnd) {
            if (ADD_SPACE) {
                try{
                    if (p.characters[-2].contents !== " ") {
                        ip.contents = " ";
                        ip = p.insertionPoints[-2];
                    }
                }catch(_){}
            }
            var placed = story.insertionPoints[ip.index].place(File(tfLinkPath))[0];
            try { placed.anchoredObjectSettings.anchorType = AnchorPosition.INLINE_POSITION; } catch(_){}
            try {
                placed.fit(FitOptions.FRAME_TO_CONTENT);
                var pgb = placed.geometricBounds, pw = pgb[3]-pgb[1];
                if (pw > 0 && tfWidth) {
                    var scale = (tfWidth/pw)*100;
                    placed.absoluteHorizontalScale = scale;
                    placed.absoluteVerticalScale   = scale;
                }
            } catch(_){}
            try{ story.recompose(); }catch(_){}
        }

        var startIdx = p.insertionPoints[-2].index;
        var anchorIdx = -1;
        for (var probe = 0; probe < 4; probe++){
            var tryIdx = startIdx - probe; if (tryIdx < 0) break;
            try { if (story.characters[tryIdx].contents === "\uFFFC") { anchorIdx = tryIdx; break; } }catch(_){}
            try { if (story.characters[tryIdx+1] && story.characters[tryIdx+1].contents === "\uFFFC") { anchorIdx = tryIdx; break; } }catch(_){}
        }
        if (anchorIdx !== -1 && isAnchorAtLineStart(anchorIdx)) {
            if (!tightenToKeepOnSameLine(anchorIdx)) bindWithPrevWord(anchorIdx);
        }
    }
    try{ story.recompose(); }catch(_){}

})();