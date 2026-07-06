/**
 * FinalVol1.jsx - 파이널 Vol.1 조판 자동화
 * 모드 1: 문장배열 스타일 적용 (메인 스토리)
 * 모드 2: 중요어휘(왼) 스타일 적용
 * 모드 3: 중요어휘(오) 스타일 적용
 */
#target indesign
(function(){
    if (app.documents.length === 0) { alert("문서가 없습니다."); return; }
    var doc = app.activeDocument;

    // ── UI ──
    var dlg = new Window("dialog", "파이널 Vol.1 스타일 적용");
    dlg.orientation = "column";
    dlg.alignChildren = ["fill", "top"];
    var rg = dlg.add("group");
    rg.orientation = "column";
    rg.alignChildren = ["left", "top"];
    var rb1 = rg.add("radiobutton", undefined, "문장배열 스타일 적용");
    var rb2 = rg.add("radiobutton", undefined, "중요어휘(왼) 스타일 적용");
    var rb3 = rg.add("radiobutton", undefined, "중요어휘(오) 스타일 적용");
    rb1.value = true;
    var bg = dlg.add("group");
    bg.add("button", undefined, "확인", {name: "ok"});
    bg.add("button", undefined, "취소", {name: "cancel"});
    if (dlg.show() !== 1) return;
    var mode = rb1.value ? 1 : (rb2.value ? 2 : 3);

    // ── 스토리 확보 ──
    if (app.selection.length === 0) { alert("텍스트를 선택하세요."); return; }
    var story = null;
    try {
        var s = app.selection[0];
        if (s && s.hasOwnProperty("parentStory")) story = s.parentStory;
        else if (s && s.constructor && s.constructor.name === "Story") story = s;
        else if (s && s.constructor && s.constructor.name === "TextFrame") story = s.parentStory;
    } catch(e){}
    if (!story) { alert("텍스트를 선택한 후 실행하세요."); return; }

    // ── 헬퍼 ──
    function getBasicPS(){
        var names = ["[Basic Paragraph]", "[기본 단락]", "$ID/NormalParagraphStyle"];
        for (var i = 0; i < names.length; i++){
            try { var c = doc.paragraphStyles.itemByName(names[i]); if (c && c.isValid) return c; } catch(e){}
        }
        return doc.paragraphStyles[0];
    }
    function findPS(name){
        var all = doc.allParagraphStyles;
        for (var i = 0; i < all.length; i++){
            if (all[i].name === name) return all[i];
        }
        return null;
    }
    function ensurePS(groupName, styleName){
        var g = doc.paragraphStyleGroups.itemByName(groupName);
        if (!g.isValid) g = doc.paragraphStyleGroups.add({name: groupName});
        var ps = g.paragraphStyles.itemByName(styleName);
        if (!ps.isValid) ps = g.paragraphStyles.add({name: styleName});
        return ps;
    }
    function resetGrep(){
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        try { app.findChangeGrepOptions = NothingEnum.NOTHING; } catch(e){}
    }
    function grepChange(scope, findWhat, changeTo){
        resetGrep();
        app.findGrepPreferences.findWhat = findWhat;
        app.changeGrepPreferences.changeTo = changeTo;
        scope.changeGrep();
        resetGrep();
    }
    function ptext(p){ return (p.contents || "").replace(/\r$/, ""); }
    function findLabeledItem(label){
        var items = doc.allPageItems;
        for (var i = 0; i < items.length; i++){
            try { if (items[i].label === label) return items[i]; } catch(e){}
        }
        return null;
    }

    var PS_BASIC = getBasicPS();
    var CS_NONE = doc.characterStyles[0];

    // ── 모드 1: 문장배열 ──
    if (mode === 1) {
        var PS_HEADER = findPS("1. 문장 배열 번호") || ensurePS("STEP 01", "1. 문장 배열 번호");
        var PS_GREP   = findPS("문장 배열 그랩") || ensurePS("STEP 01", "문장 배열 그랩");
        var PS_GREP2  = findPS("1. 문장 배열 그랩"); // 블록 구분 빈줄용 (없으면 기본 단락)

        app.doScript(function(){
            app.scriptPreferences.enableRedraw = false;

            // 0) 문자 스타일 초기화
            try { story.characters.everyItem().appliedCharacterStyle = CS_NONE; } catch(e){}

            // 1) 단락 분류: 헤더 vs (A)~(Z) 선택지 vs 빈줄
            var paras = story.paragraphs.everyItem().getElements();
            for (var i = 0; i < paras.length; i++){
                var txt = ptext(paras[i]);
                if (txt === "" || /^[\s\u00A0]*$/.test(txt)) continue;
                if (/^\s*\([A-Z]\)/.test(txt)){
                    paras[i].appliedParagraphStyle = PS_GREP;
                } else {
                    paras[i].appliedParagraphStyle = PS_HEADER;
                }
            }

            // 2) 화살표 아이콘 삽입 (각 선택지 블록 끝)
            var srcArrow = findLabeledItem("화살표 답지");
            var srcWasLocked = null, srcLayerWasLocked = null;
            if (srcArrow) {
                try { srcWasLocked = srcArrow.locked; srcArrow.locked = false; } catch(e){}
                try {
                    if (srcArrow.itemLayer){
                        srcLayerWasLocked = srcArrow.itemLayer.locked;
                        srcArrow.itemLayer.locked = false;
                        srcArrow.itemLayer.visible = true;
                    }
                } catch(e){}
            }

            paras = story.paragraphs.everyItem().getElements();
            for (var i = 0; i < paras.length; i++){
                // 현재가 선택지 스타일이고 다음이 선택지가 아닌 경우 = 블록 끝
                var isGrepStyle = (paras[i].appliedParagraphStyle === PS_GREP ||
                    (paras[i].appliedParagraphStyle && paras[i].appliedParagraphStyle.name === PS_GREP.name));
                if (!isGrepStyle) continue;
                if (i + 1 < paras.length) {
                    var nextIsGrep = (paras[i+1].appliedParagraphStyle === PS_GREP ||
                        (paras[i+1].appliedParagraphStyle && paras[i+1].appliedParagraphStyle.name === PS_GREP.name));
                    if (nextIsGrep) continue;
                }

                // 블록 끝에 빈줄 + 화살표 삽입
                try {
                    var ip = paras[i].insertionPoints[-1];
                    ip.contents = "\r\r";
                    paras = story.paragraphs.everyItem().getElements();

                    // 첫 번째 빈줄
                    if (PS_GREP2) {
                        try { paras[i+1].appliedParagraphStyle = PS_GREP2; } catch(e){}
                    } else {
                        try { paras[i+1].appliedParagraphStyle = PS_BASIC; } catch(e){}
                    }

                    // 두 번째 빈줄에 화살표
                    var arrowPara = paras[i+2];
                    if (srcArrow) {
                        // 아이콘이 있으면 인라인 삽입
                        arrowPara.insertionPoints[0].contents = "\uFF1E "; // ＞
                        var icon = srcArrow.duplicate();
                        try {
                            icon.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION;
                            icon.textWrapPreferences.textWrapMode = TextWrapModes.NONE;
                        } catch(e){}
                        icon.anchoredObjectSettings.insertAnchoredObject(
                            arrowPara.insertionPoints[-1], AnchorPosition.INLINE_POSITION);
                        try { icon.fit(FitOptions.FRAME_TO_CONTENT); } catch(e){}
                    } else {
                        // 아이콘이 없으면 텍스트만 삽입
                        arrowPara.insertionPoints[0].contents = "\uFF1E"; // ＞
                    }
                    try { arrowPara.appliedParagraphStyle = PS_BASIC; } catch(e){}
                    i += 2; // 삽입된 단락 건너뛰기
                } catch(e){}
            }

            // 3) 프레임 브레이크 (헤더 기준, 첫 헤더 제외)
            paras = story.paragraphs.everyItem().getElements();
            var headerIdx = [];
            for (var i = 0; i < paras.length; i++){
                if (paras[i].appliedParagraphStyle === PS_HEADER ||
                    (paras[i].appliedParagraphStyle && paras[i].appliedParagraphStyle.name === PS_HEADER.name)){
                    headerIdx.push(i);
                }
            }
            for (var h = headerIdx.length - 1; h >= 1; h--){
                try { paras[headerIdx[h]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e){}
            }

            // 4) 빈 단락 정리 (연속 3줄 이상 → 2줄로)
            grepChange(story, "\\r{3,}", "\\r\\r");

            // 5) 엔터만 있는 단락은 기본 단락으로
            paras = story.paragraphs.everyItem().getElements();
            for (var i = 0; i < paras.length; i++){
                if (paras[i].contents === "\r"){
                    try { paras[i].appliedParagraphStyle = PS_BASIC; } catch(e){}
                }
            }

            // 잠금 복구
            if (srcArrow) {
                try { srcArrow.locked = (srcWasLocked !== null ? srcWasLocked : false); } catch(e){}
                try { if (srcArrow.itemLayer && srcLayerWasLocked !== null) srcArrow.itemLayer.locked = srcLayerWasLocked; } catch(e){}
            }

            app.scriptPreferences.enableRedraw = true;
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "파이널 Vol.1 문장배열");

        alert("문장배열 스타일 적용 완료.");
    }

    // ── 모드 2/3: 중요어휘 ──
    if (mode === 2 || mode === 3) {
        var targetStyleName = (mode === 2) ? "2. 중요어휘(왼)" : "2. 중요어휘_원문(오)";
        var PS_VOCAB = findPS(targetStyleName);
        if (!PS_VOCAB) {
            alert("단락 스타일 '" + targetStyleName + "'을(를) 찾을 수 없습니다.\n문서에 해당 스타일이 존재하는지 확인하세요.");
            return;
        }

        app.doScript(function(){
            app.scriptPreferences.enableRedraw = false;

            // 문자 스타일 초기화
            try { story.characters.everyItem().appliedCharacterStyle = CS_NONE; } catch(e){}

            // 전체 단락에 스타일 적용
            try { story.paragraphs.everyItem().appliedParagraphStyle = PS_VOCAB; } catch(e){}

            app.scriptPreferences.enableRedraw = true;
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "파이널 Vol.1 중요어휘");

        alert("중요어휘 스타일 적용 완료 (" + targetStyleName + ")");
    }
})();
