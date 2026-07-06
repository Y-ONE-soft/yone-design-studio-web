// InDesign ExtendScript (JSX) — 선택 스토리 전용 파이프라인
// 0) 문자스타일 [없음] 초기화
// 1) 탭(\t) → 줄바꿈(\r) — 선택 스토리 한정 (커서/텍스트/프레임 모두 OK)
// 2) 머리말 처리(Practice 패턴 포함): 위쪽 비어있지 않은 문단의 '마지막 리턴 앞'에 FRAME_BREAK + 사이 빈 단락/머리말/아래 연속 빈 단락 삭제
// 3) 모든 단락 → STEP 02/C1_빈칸 어법     <-- (요기만 변경)
// 4) 한글 2자 이상 포함 단락만 → STEP 01/C2_빈칸 어휘 한글
// 5) SplitStory.jsx 지연 실행(BridgeTalk)

(function () {
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    if (app.selection.length === 0) { alert("텍스트를 선택하거나 커서를 문단에 두세요."); return; }

    // --- 선택한 '스토리' 안전 확보: 커서/텍스트/텍스트프레임 모두 지원 ---
    var sel = app.selection[0], story = null;
    try {
        if (sel.hasOwnProperty("insertionPoints"))      story = sel.parentStory;   // 커서/텍스트
        else if (sel.hasOwnProperty("parentStory"))     story = sel.parentStory;   // 텍스트 관련 객체
        else if (sel instanceof TextFrame)              story = sel.parentStory;   // 프레임
    } catch (_) {}
    if (!story) { alert("선택에서 스토리를 찾지 못했습니다. 텍스트 안을 클릭하세요."); return; }

    var doc = app.activeDocument;

    // 공백/제로폭 정규화(헤더 매칭 안정화)
    function normHeader(s){
        return (s||"")
            .replace(/\uFEFF/g,"")
            .replace(/[\u00A0\u2000-\u200B\u202F\u205F\u3000]/g," ")
            .replace(/[ \t]+/g," ")
            .replace(/^\s+|\s+$/g,"");
    }

    // ---------- 유틸 ----------
    function isBlankPara(p) {
        var t = (p.contents || "").replace(/[\s\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\r\n\t]+/g, "");
        return t === "";
    }
    function ps(group, name) {
        try {
            var g = doc.paragraphStyleGroups.itemByName(group);
            if (g && g.isValid) {
                var s = g.paragraphStyles.itemByName(name);
                if (s && s.isValid) return s;
            }
        } catch (_) {}
        return null;
    }
    function csNone() { try { return doc.characterStyles[0]; } catch (_) { return null; } } // [없음]
    function resetGrep() {
        app.findGrepPreferences   = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
    }

    // 머리말 패턴 확장:
    // - "2. L3-본문2" / "2. p22-no.01" / "3) p23 - no.02" / "5. p51-서술형 Practice" / "6. p52-논술형 Practice"
    // - "1. p46-수능 대비 ANALYSIS" (첫 단락 헤더도 삭제)
    var reHeader = /^\s*\d+\s*[.)]?\s*(?:L\d+\s*(?:-?\s*p\.?\s*\d+)?\s*(?:[-–—]?\s*(?:본문\s*\d+|p\.?\s*\d+(?:\s+[^\r\n]+)?|[^\r\n]+))?|p\d+\s*-\s*no\.?\s*\d+|p\d+\s*[-–—]?\s*(?:서술형|논술형)\s*Prac(?:tice|ice)|p\d+\s*[-–—]?\s*수능\s*대비\s*ANALYSIS)\b.*$/i;
    var reSupp   = /^\s*Supplementary Reading\s*$/i;
    var reGangBeon = /^\s*\d+\s*강\s*\d+\s*번\s*\d{6}\s*$/; // "7강 4번 200324"

    app.scriptPreferences.enableRedraw = false;

    app.doScript(function () {

        // 실행 결과 카운터
        var cntTabs=0, cntHeaders=0, cntBreaks=0, cntMidBlanks=0, cntBelowBlanks=0;

        // 0) 문자스타일 [없음]으로 스토리 전체 초기화
        try { var none = csNone(); if (none) story.characters.everyItem().appliedCharacterStyle = none; } catch (_cs) {}

        // 2) 머리말 처리
        (function handleHeaders() {
            var paras = story.paragraphs;
            for (var i = paras.length - 1; i >= 0; i--) {
                paras = story.paragraphs;
                if (i >= paras.length) continue;

                var header = paras[i];
                if (header.parentStory !== story) continue;

                var htxt = header.contents || "";
                var hnorm = normHeader(htxt);
                if (!(reHeader.test(hnorm) || reSupp.test(hnorm) || reGangBeon.test(hnorm))) continue;

                // 위쪽으로 비어있지 않은 문단 찾기
                var top = i - 1;
                while (top >= 0 && paras[top].parentStory === story && isBlankPara(paras[top])) top--;

                if (top >= 0) {
                    // 마지막 리턴 '앞'에 프레임브레이크(중복 방지)
                    try {
                        var ipBeforeCR    = paras[top].insertionPoints[-2];
                        var lastBeforeCR  = paras[top].characters.length > 1 ? paras[top].characters[-2] : null;
                        var already       = (lastBeforeCR && lastBeforeCR.contents === SpecialCharacters.FRAME_BREAK);
                        if (!already) { ipBeforeCR.contents = SpecialCharacters.FRAME_BREAK; cntBreaks++; }
                    } catch (_e0) {}

                    // 사이의 빈 단락 제거
                    for (var k = top + 1; k < i; k++) {
                        if (k >= story.paragraphs.length) break;
                        var mid = story.paragraphs[k];
                        if (mid.parentStory !== story) break;
                        if (isBlankPara(mid)) { try { mid.remove(); k--; i--; cntMidBlanks++; } catch (_e1) {} }
                    }
                } else {
                    // 스토리 첫 문단이 머리말이면 맨 앞에 프레임브레이크만
                    try { header.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch (_e0a) {}
                }

                // 머리말 삭제 (첫 단락도 동일하게 삭제)
                try {
                    header.remove();
                } catch (_e2) {}
                cntHeaders++;

                // 아래 연속 빈 단락 삭제
                paras = story.paragraphs;
                var down = Math.min(i, paras.length - 1);
                while (down < paras.length && paras[down].parentStory === story && isBlankPara(paras[down])) {
                    try { paras[down].remove(); cntBelowBlanks++; } catch (_e3) { break; }
                    paras = story.paragraphs;
                }
            }
        })();

        // 2) 탭(\t) → 줄바꿈(\r)
        try {
            resetGrep();
            app.findGrepPreferences.findWhat   = "\\t";
            app.changeGrepPreferences.changeTo = "\\r";
            var changed = story.changeGrep();
            if (changed && changed.length) { cntTabs += changed.length; }
            resetGrep();
        } catch (_grep) {}

        // 3) 모든 단락 → STEP 02 / C1_빈칸 어법   <-- (변경)
        var basePS = ps("STEP 02", "C1_빈칸 어법");
        if (!basePS) { alert("단락스타일 'STEP 02 / C1_빈칸 어법'이 없습니다."); throw Error("Missing style"); }
        try {
            var parasAll = story.paragraphs;
            for (var i2 = 0; i2 < parasAll.length; i2++) {
                try { parasAll[i2].applyParagraphStyle(basePS, true); } catch (_ps0) {}
            }
        } catch (_ap0) {}

        // 4) 한글 2자 이상 포함 단락만 → STEP 01 / C2_빈칸 어휘 한글  (그대로 둠)
        var korPS = ps("STEP 01", "C2_빈칸 어휘 한글");
        if (!korPS) { alert("단락스타일 'STEP 01 / C2_빈칸 어휘 한글'이 없습니다."); throw Error("Missing style"); }
        try {
            var paras2 = story.paragraphs, reKor2 = /[가-힣][\s\S]*[가-힣]/;
            for (var j = 0; j < paras2.length; j++) {
                var txt = paras2[j].contents || "";
                if (reKor2.test(txt)) {
                    try { paras2[j].applyParagraphStyle(korPS, true); } catch (_ps1) {}
                }
            }
        } catch (_ap1) {}

        // === 실행 요약 알림 ===
        // Removed as per instructions

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "C2 파이프라인(머리말정리→탭줄바꿈→스타일적용)");

    app.scriptPreferences.enableRedraw = true;
})();