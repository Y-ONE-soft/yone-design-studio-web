/**
 * FinalVol2.jsx - 파이널 Vol.2 조판 자동화
 * 모드 1: 어법수정 스타일 적용
 * 모드 2: 서술형 영작 스타일 적용
 */
#target indesign
(function(){
    if (app.documents.length === 0) { alert("문서가 없습니다."); return; }
    var doc = app.activeDocument;

    // ── UI ──
    var dlg = new Window("dialog", "파이널 Vol.2 스타일 적용");
    dlg.orientation = "column";
    dlg.alignChildren = ["fill", "top"];
    var rg = dlg.add("group");
    rg.orientation = "column";
    rg.alignChildren = ["left", "top"];
    var rb1 = rg.add("radiobutton", undefined, "어법수정 스타일 적용");
    var rb2 = rg.add("radiobutton", undefined, "서술형 영작 스타일 적용");
    rb1.value = true;
    var bg = dlg.add("group");
    bg.add("button", undefined, "확인", {name: "ok"});
    bg.add("button", undefined, "취소", {name: "cancel"});
    if (dlg.show() !== 1) return;
    var mode = rb1.value ? 1 : 2;

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
    function hasKorean(str){
        for (var i = 0; i < str.length; i++){
            var c = str.charCodeAt(i);
            if (c >= 0xAC00 && c <= 0xD7AF) return true; // 완성형 한글
            if (c >= 0x3131 && c <= 0x318E) return true; // 호환 자모
            if (c >= 0x1100 && c <= 0x11FF) return true; // 첫가끝 자모
        }
        return false;
    }
    function countKorean(str){
        var cnt = 0;
        for (var i = 0; i < str.length; i++){
            var c = str.charCodeAt(i);
            if ((c >= 0xAC00 && c <= 0xD7AF) || (c >= 0x3131 && c <= 0x318E)) cnt++;
        }
        return cnt;
    }

    var PS_BASIC = getBasicPS();
    var CS_NONE = doc.characterStyles[0];

    // ── 모드 1: 어법수정 ──
    if (mode === 1) {
        var PS_GRAMMAR = findPS("3. 어법수정 번호") || ensurePS("Chapter.02", "3. 어법수정 번호");

        app.doScript(function(){
            app.scriptPreferences.enableRedraw = false;

            // 0) 문자 스타일 초기화
            try { story.characters.everyItem().appliedCharacterStyle = CS_NONE; } catch(e){}

            // 1) 전체 스타일 적용
            try { story.paragraphs.everyItem().appliedParagraphStyle = PS_GRAMMAR; } catch(e){}

            // 2) 지문 헤더 감지 + 프레임 브레이크
            var paras = story.paragraphs.everyItem().getElements();
            var headerIdx = [];
            for (var i = 0; i < paras.length; i++){
                var txt = ptext(paras[i]);
                if (txt === "") continue;
                // "X과 본문Y" 형태 또는 6자리 숫자 코드 또는 "X과 본문 Y" (공백 포함)
                if (/^\s*\d+과\s*본문\s*\d+/.test(txt) || /^\s*\d{6}(-\d+)?\s*$/.test(txt)) {
                    headerIdx.push(i);
                }
            }

            // 두 번째 헤더부터 역순 프레임 브레이크
            for (var h = headerIdx.length - 1; h >= 1; h--){
                try { paras[headerIdx[h]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e){}
            }

            // 3) 빈 단락 정리
            grepChange(story, "\\r{2,}", "\\r");

            app.scriptPreferences.enableRedraw = true;
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "파이널 Vol.2 어법수정");

        alert("어법수정 스타일 적용 완료.");
    }

    // ── 모드 2: 서술형 영작 ──
    if (mode === 2) {
        var PS_KOR  = findPS("C_영작 배열 번호") || ensurePS("STEP 02", "C_영작 배열 번호");
        var PS_VIEW = findPS("영작 배열 보기") || ensurePS("STEP 02", "영작 배열 보기");
        var PS_LINE = findPS("밑줄") || ensurePS("STEP 02", "밑줄");

        app.doScript(function(){
            app.scriptPreferences.enableRedraw = false;

            // 0) 문자 스타일 초기화
            try { story.characters.everyItem().appliedCharacterStyle = CS_NONE; } catch(e){}

            // 1) 단락 분류
            var paras = story.paragraphs.everyItem().getElements();
            var headerIdx = [];

            for (var i = 0; i < paras.length; i++){
                var txt = ptext(paras[i]);
                if (txt === "") continue; // 완전 빈줄만 스킵

                // [...]로 시작 → 섹션 헤더
                if (/^\s*\[/.test(txt)){
                    paras[i].appliedParagraphStyle = PS_BASIC;
                    headerIdx.push(i);
                }
                // 공백/점선/밑줄만으로 구성 (5자 이상) → 밑줄 (답안 작성 칸)
                else if (txt.length >= 5 && /^[\s\u00A0\.\u2025\u2026_\-]*$/.test(txt)){
                    paras[i].appliedParagraphStyle = PS_LINE;
                }
                // 한글 2자 이상 + 슬래시 없음 → 한글 문장
                else if (countKorean(txt) >= 2 && txt.indexOf("/") === -1){
                    paras[i].appliedParagraphStyle = PS_KOR;
                }
                // 슬래시 + 괄호 포함 → 영어 보기
                else if (txt.indexOf("/") !== -1 && txt.indexOf("(") !== -1){
                    paras[i].appliedParagraphStyle = PS_VIEW;
                }
                // 괄호만 있고 한글 없음 → 영어 보기
                else if (txt.indexOf("(") !== -1 && !hasKorean(txt)){
                    paras[i].appliedParagraphStyle = PS_VIEW;
                }
                // 한글 2자 이상 (슬래시 포함이라도) → 한글 문장
                else if (countKorean(txt) >= 2){
                    paras[i].appliedParagraphStyle = PS_KOR;
                }
                // 나머지(영문만 등) → 보기
                else {
                    paras[i].appliedParagraphStyle = PS_VIEW;
                }
            }

            // 2) 프레임 브레이크 (섹션 헤더 기준, 첫 헤더 제외)
            // 단락 재취득 (분류 중 변경 없으므로 기존 것 사용 가능하지만 안전하게)
            paras = story.paragraphs.everyItem().getElements();
            headerIdx = [];
            for (var i = 0; i < paras.length; i++){
                var txt2 = ptext(paras[i]);
                if (/^\s*\[/.test(txt2)) headerIdx.push(i);
            }
            for (var h = headerIdx.length - 1; h >= 1; h--){
                try { paras[headerIdx[h]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e){}
            }

            // 3) 빈 단락 정리
            grepChange(story, "\\r{3,}", "\\r\\r");

            // 4) 빈줄은 기본 단락
            paras = story.paragraphs.everyItem().getElements();
            for (var i = 0; i < paras.length; i++){
                if (paras[i].contents === "\r"){
                    try { paras[i].appliedParagraphStyle = PS_BASIC; } catch(e){}
                }
            }

            app.scriptPreferences.enableRedraw = true;
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "파이널 Vol.2 서술형영작");

        alert("서술형 영작 스타일 적용 완료.");
    }
})();
