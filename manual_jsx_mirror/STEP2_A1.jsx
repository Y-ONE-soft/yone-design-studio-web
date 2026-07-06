// InDesign ExtendScript (JSX)
// 순서:
//  1) 헤더 위/아래 빈 단락 제거 (맨 처음 헤더는 그대로 첫 줄로 유지)
//  2) 헤더 텍스트를 "{…}\r" 로 교체
//  3) 맨 첫 헤더만 프레임브레이크 생략, 나머지는 헤더 "맨 앞"에 FRAME_BREAK
//  4) 단락 스타일: STEP 02 / A1_어법 선택, 문자 스타일: [None]

(function () {
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    if (app.selection.length === 0) { alert("텍스트를 선택하거나 커서를 문단에 두세요."); return; }

    var doc = app.activeDocument, sel = app.selection[0], ip;
    try {
        ip = sel.hasOwnProperty("insertionPoints") ? sel.insertionPoints[0]
             : sel.parentTextFrames[0].parentStory.insertionPoints[0];
    } catch (e) { alert("텍스트 안을 선택하세요."); return; }

    var story = ip.parentStory;

    // 실행 전에 전체 문자 스타일 [없음]으로 초기화
    try {
        var noneCharStyle = (function(){
            var cands = ["[None]", "[없음]"];
            for (var i=0;i<cands.length;i++){
                try { var s = doc.characterStyles.itemByName(cands[i]); if (s && s.isValid) return s; } catch(_){}
            }
            try { var s0 = doc.characterStyles[0]; if (s0 && s0.isValid) return s0; } catch(_){}
            return null;
        })();
        if (noneCharStyle) {
            story.characters.everyItem().appliedCharacterStyle = noneCharStyle;
        }
    } catch(_){}

    // ---- styles ----
    function getParaStyle(groupName, styleName){
        try {
            var g = doc.paragraphStyleGroups.itemByName(groupName);
            if (!g.isValid) return null;
            var s = g.paragraphStyles.itemByName(styleName);
            return (s && s.isValid) ? s : null;
        } catch(_) { return null; }
    }
    function getNoneCharStyle(){
        var cands = ["[None]", "[없음]"];
        for (var i=0;i<cands.length;i++){
            try { var s = doc.characterStyles.itemByName(cands[i]); if (s && s.isValid) return s; } catch(_){}
        }
        try { var s0 = doc.characterStyles[0]; if (s0 && s0.isValid) return s0; } catch(_){}
        return null;
    }
    var stHeader   = getParaStyle("STEP 02", "A1_어법 선택");
    var stCharNone = getNoneCharStyle();
    if (!stHeader) { alert("단락 스타일을 찾을 수 없습니다: STEP 02 / A1_어법 선택"); return; }

    // ---- utils ----
    function extractTail(txt){
        var s = (txt||"").replace(/^\s+|\s+$/g, "");
        var m;
        // "7강 4번 200324" 형식 → 전체 문자열 그대로 반환
        m = s.match(/^(\d+\s*강\s*\d+\s*번\s*\d{6})$/);
        if (m) return m[1];
        // Lx(-p.xx) 본문 n  → capture only "본문 n"
        m = s.match(/^\s*\d+[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)?\s*[-–—]?\s*(본문\s*\d+)\b/i);
        if (m) return m[1];
        // "1. L1-p.17" → generate "본문1"
        m = s.match(/^\s*(\d+)[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)\s*$/i);
        if (m) return "본문" + m[1];
        m = s.match(/^\s*\d+[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)?\s*[-–—]?\s*(.+)$/i);
        if (m){
            var tail = m[1].replace(/^\s*p\.?\s*\d+\s*[-–—]?\s*/i, "");
            if (/^Further\s+Reading$/i.test(tail)) return "Further Reading";
            return tail;
        }
        m = s.match(/^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*(\d+)(?:[\s-]*(.+))?$/i);
        if (m) return (m[2] ? m[2] : m[1]);
        if (/수능\s*대비\s*analysis/i.test(s)) return "분석";
        m = s.match(/^\s*\d+[\s.)-]*p\.?\s*\d+\s*(?:[-–—]|\s)+\s*(.+)$/i);
        if (m) return m[1];
        return "";
    }
    function isBlankPara(p){
        var t = (p.contents||"").replace(/[\s\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\r\n\t]+/g,"");
        return t === "";
    }
    function findHeaderTexts(_story){
        var result = [];
        var paras = _story.paragraphs.everyItem().getElements();
        // 허용 대시들
        var DASH = "-–—﹣－";
        // 패턴들 (JS RegExp)
        var reL = new RegExp(/^\s*\d+\s*[.)]?\s*L\d+\s*[-–—﹣－]\s*.+/i);
        var rePNo = new RegExp(/^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-–—﹣－]|\s)*no\.?\s*\d+\b.*$/i);
        var rePDesc = new RegExp(/^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-–—﹣－]|\s)+\s*.+$/i); // e.g., 6. p38-논술형 Practice
        var reAnalysis = new RegExp(/^\s*\d+.*수능\s*대비\s*analysis.*$/i);
        var reGangBeon = new RegExp(/^\s*\d+\s*강\s*\d+\s*번\s*\d{6}\s*$/); // "7강 4번 200324"

        for (var i = 0; i < paras.length; i++) {
            var p = paras[i];
            if (!p || !p.isValid) continue;
            var t = (p.contents||"").replace(/\r|\n/g, "");
            if (reL.test(t) || rePNo.test(t) || rePDesc.test(t) || reAnalysis.test(t) || reGangBeon.test(t)) {
                result.push(p); // Paragraph 객체를 직접 반환
            }
        }
        return result;
    }

    app.doScript(function () {
        var _prevRedraw = app.scriptPreferences.enableRedraw;
        app.scriptPreferences.enableRedraw = false;
        try {
            var skippedFirstBreak = false; // 첫 매칭만 브레이크 생략
            var parasArr = story.paragraphs.everyItem().getElements();
            var toRemove = [];
            var headerTexts = findHeaderTexts(story);

            // 문서 상단(가장 먼저 나오는) 헤더의 인덱스 계산 — 이 헤더만 프레임브레이크 생략
            var topHeaderIndex = null;
            for (var ti = 0; ti < headerTexts.length; ti++) {
                var ph = headerTexts[ti];
                if (!ph || !ph.isValid) continue;
                if (topHeaderIndex === null || ph.index < topHeaderIndex) topHeaderIndex = ph.index;
            }

            var seen = {};

            for (var h = headerTexts.length - 1; h >= 0; h--) {
                var header = headerTexts[h];
                if (!header || !header.isValid || header.parentStory !== story) continue;
                var pid = header.index;
                if (seen[pid]) continue;
                seen[pid] = true;

                // 1) 위/아래 빈 단락 제거
                var i = header.index;
                var up = i - 1;
                while (up >= 0) {
                    var pUp = parasArr[up];
                    if (!pUp || !pUp.isValid || pUp.parentStory !== story) break;
                    if (!isBlankPara(pUp)) break;
                    toRemove.push(pUp);
                    up--;
                }
                var down = i + 1;
                while (down < parasArr.length) {
                    var pDown = parasArr[down];
                    if (!pDown || !pDown.isValid || pDown.parentStory !== story) break;
                    if (!isBlankPara(pDown)) break;
                    toRemove.push(pDown);
                    down++;
                }

                // 2) 텍스트 {…}\r 변환
                try {
                    var tail = extractTail(header.contents||"");
                    if (tail !== "") {
                        var newText = "{" + tail.replace(/^\s+|\s+$/g, "") + "}\r";
                        if (header.contents !== newText) header.contents = newText;
                    }
                } catch(_){ }

                // 3) 프레임브레이크: 문서 상단(가장 먼저 나오는) 헤더만 생략, 나머지는 적용
                try {
                    if (header.index !== topHeaderIndex) {
                        header.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; // 중복이어도 강제 삽입
                    }
                } catch(_){ }

                // 4) 스타일 적용
                try { header.appliedParagraphStyle = stHeader; } catch(_){ }
                if (stCharNone) { try { header.characters.everyItem().appliedCharacterStyle = stCharNone; } catch(_){ } }
            }

            if (toRemove.length) {
                for (var r = 0; r < toRemove.length; r++) {
                    try { if (toRemove[r] && toRemove[r].isValid) toRemove[r].remove(); } catch(_) {}
                }
            }

            // 5) 전체 스토리 단락 스타일 일괄 적용 (요청사항)
            try {
                story.paragraphs.everyItem().appliedParagraphStyle = stHeader;
            } catch(_) {}

            // 6) 전체 문자 스타일 [None] 초기화
            if (stCharNone) {
                try {
                    story.characters.everyItem().appliedCharacterStyle = stCharNone;
                } catch(_) {}
            }

        } finally {
            app.scriptPreferences.enableRedraw = _prevRedraw;
        }
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT,
       "Headers-> {...}+CR; clean blanks; frame-break after cleaning (skip only very first match)");

})();