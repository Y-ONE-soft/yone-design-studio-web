// InDesign ExtendScript (JSX)
// L3-본문 헤더를 기준으로 프레임 분리
// - 헤더 위쪽에서 가장 가까운 '비어있지 않은' 문단 끝(리턴 앞)에 FRAME_BREAK
// - 사이의 빈 단락 삭제
// - 헤더 삭제(첫 단락이 헤더여도 브레이크만 남기고 전부 삭제)
// - 헤더 아래 연속 빈 단락 삭제

(function(){
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    if (app.selection.length === 0) { alert("텍스트를 선택하거나 커서를 문단에 두세요."); return; }

    var doc = app.activeDocument, sel = app.selection[0];
    // 선택 대상에 상관없이 안전하게 parentStory 찾기
    var story = (function(s){
        try {
            if (!s) return null;
            // 텍스트 관련 객체(문자/단락/텍스트 등)인 경우
            if (s.hasOwnProperty("parentStory") && s.parentStory && s.parentStory.isValid) return s.parentStory;
            // 삽입점이 있는 경우
            if (s.hasOwnProperty("insertionPoints") && s.insertionPoints.length > 0) {
                var ip0 = s.insertionPoints[0];
                if (ip0 && ip0.parentStory && ip0.parentStory.isValid) return ip0.parentStory;
            }
            // 텍스트 프레임 직접 선택된 경우
            if (s.constructor && s.constructor.name === "TextFrame") {
                if (s.parentStory && s.parentStory.isValid) return s.parentStory;
            }
            // 텍스트 프레임의 자식이 선택된 경우
            if (s.parentTextFrames && s.parentTextFrames.length > 0) {
                var tf = s.parentTextFrames[0];
                if (tf && tf.parentStory && tf.parentStory.isValid) return tf.parentStory;
            }
        } catch(_){}
        return null;
    })(sel);
    if (!story){ alert("텍스트 안을 선택하세요."); return; }

    // 실행 전: 스토리 전체 문자 스타일 [없음]/[None] 적용
    try {
        var noneCharStyle = (function(){
            var cands = ["[None]", "[없음]"];
            for (var i=0;i<cands.length;i++){
                try {
                    var s = doc.characterStyles.itemByName(cands[i]);
                    if (s && s.isValid) return s;
                } catch(_){}
            }
            try { var s0 = doc.characterStyles[0]; if (s0 && s0.isValid) return s0; } catch(_){}
            return null;
        })();
        if (noneCharStyle && story && story.isValid) {
            try {
                // STEP2A1과 동일: 전체 문자에 [없음]/[None] 적용
                story.characters.everyItem().appliedCharacterStyle = noneCharStyle;
            } catch(__cs){}
        }
    } catch(__none){}

    // 실행 전: 단락 오버라이드(+) 제거 — 단락 스타일 유지
    try {
        var _paras = story.paragraphs.everyItem().getElements();
        for (var pi = 0; pi < _paras.length; pi++) {
            var p = _paras[pi];
            if (!p || !p.isValid) continue;
            var ps = p.appliedParagraphStyle;
            if (ps && ps.isValid) {
                // 같은 스타일을 오버라이드 제거 옵션으로 재적용
                try { p.applyParagraphStyle(ps, true); } catch(_aps){}
            }
        }
    } catch(__paraClean) {}

    function isBlankPara(p){
        // 공백, NBSP, 제로폭류 제거 후 비었으면 빈 단락
        var t = (p.contents||"")
            .replace(/[\u0009\u0020\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\uFEFF]+/g,"")
            .replace(/\r|\n/g,"");
        return t === "";
    }

    // 헤더 패턴 확장:
    // - 기존: L\d+-본문\d+
    // - 추가: p\d+-no.\d+ (대소문자 무시, 하이픈/공백 유연)
    //   → p\d+\s*[-\s]\s*no\.\s*\d+
    // - 변경: 1. p46-수능 대비 ANALYSIS (정답 1개) 같은 헤더도 매치 및 삭제
    var reHeader = /^\s*(?:\d+\s*[.)]?\s*)?(?:L\d+\s*-\s*본문\d+|p\d+\s*[-–—\s\.]*[^\r\n]*|[A-Z]\d+\s*[-–—\s\.]*[^\r\n]*)(?:\s*\([^)]*\))?\s*$/i;
    var reSupp   = /^\s*Supplementary Reading\s*$/i;
    var reGangBeon = /^\s*\d+\s*강\s*\d+\s*번\s*\d{6}\s*$/; // "7강 4번 200324"

    app.doScript(function(){
        var paras = story.paragraphs;

        for (var i = paras.length - 1; i >= 0; i--) {
            paras = story.paragraphs;
            if (i >= paras.length) continue;

            var header = paras[i];
            if (!header || header.parentStory !== story) continue;

            var htxt = header.contents || "";
            if (!(reHeader.test(htxt) || reSupp.test(htxt) || reGangBeon.test(htxt))) continue;

            // 1) 헤더 위에서 가장 가까운 '비어있지 않은' 문단
            var top = i - 1;
            while (top >= 0 && paras[top].parentStory === story && isBlankPara(paras[top])) top--;

            if (top >= 0) {
                // 1-a) top 문단 끝 '리턴 앞'에 FRAME_BREAK(중복 방지)
                try {
                    var ipBeforeCR = paras[top].insertionPoints[-2];
                    var chBeforeCR = (paras[top].characters.length > 1) ? paras[top].characters[-2] : null;
                    if (!(chBeforeCR && chBeforeCR.contents === SpecialCharacters.FRAME_BREAK)) {
                        ipBeforeCR.contents = SpecialCharacters.FRAME_BREAK;
                    }
                } catch(_){}

                // 1-b) top~header 사이의 빈 단락 전부 삭제
                for (var k = top + 1; k < i; k++) {
                    if (k >= story.paragraphs.length) break;
                    var mid = story.paragraphs[k];
                    if (mid.parentStory !== story) break;
                    if (isBlankPara(mid)) { try { mid.remove(); k--; i--; } catch(__){} }
                }

                // 2) 헤더 삭제
                try { header.remove(); } catch(_){}
            } else {
                // 스토리 첫 문단이 헤더인 경우 — 단락 자체 삭제 (다른 것 건드리지 않음)
                try { header.remove(); } catch(_) {}
            }

            // 3) 헤더 자리 아래 연속 빈 단락 삭제
            paras = story.paragraphs;
            var down = Math.min(i, paras.length - 1);
            while (down < paras.length && paras[down].parentStory === story && isBlankPara(paras[down])) {
                try { paras[down].remove(); } catch(__){ break; }
                paras = story.paragraphs;
            }
        }

        // 추가: 첫 단락이 헤더인데 루프에서 누락되는 케이스 보강 — 단락 자체 삭제
        try {
            var _p0 = story.paragraphs[0];
            if (_p0 && (_p0.parentStory === story)) {
                var _t0 = _p0.contents || "";
                if (reHeader.test(_t0) || reSupp.test(_t0) || reGangBeon.test(_t0)) {
                    try { _p0.remove(); } catch(__r) {}
                }
            }
        } catch(__firstFix) {}

        try { story.recompose(); } catch(_){}

        // 추가: 단락스타일 STEP 02 폴더의 "A1_어법 선택 하단" 적용
        try {
            var targetParaStyle = null;
            try {
                var step02Group = doc.paragraphStyleGroups.itemByName("STEP 02");
                if (step02Group && step02Group.isValid) {
                    var ps = step02Group.paragraphStyles.itemByName("A1_어법 선택 하단");
                    if (ps && ps.isValid) {
                        targetParaStyle = ps;
                    }
                }
            } catch(_psg){}

            if (targetParaStyle) {
                var allParas = story.paragraphs.everyItem().getElements();
                for (var si = 0; si < allParas.length; si++) {
                    var sp = allParas[si];
                    if (sp && sp.isValid) {
                        try { sp.appliedParagraphStyle = targetParaStyle; } catch(_ap){}
                    }
                }
            }
        } catch(_styleApply){}

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "L3 header split + robust first-para deletion");

})();