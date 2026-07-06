// InDesign ExtendScript (JSX)
// 목표: 선택한 스토리에서
//  - "2. L3-본문2" 류 머리말을 만나면, 그 "위쪽에서 가장 가까운 비어있지 않은 문단"의
//    마지막 리턴 '앞'에 FRAME_BREAK 삽입
//  - 그 비어있지 않은 문단과 머리말 사이에 낀 빈 단락들은 모두 삭제
//  - 머리말 단락 삭제 + 머리말 아래 연속 빈 단락 삭제
// → 브레이크가 빈 단락에 들어가서 '빈 ¶'이 남는 문제를 근본적으로 차단
(function(){
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    if (app.selection.length === 0) { alert("텍스트를 선택하거나 커서를 문단에 두세요."); return; }

    var doc = app.activeDocument, sel = app.selection[0], ip;
    try {
        ip = sel.hasOwnProperty("insertionPoints") ? sel.insertionPoints[0]
             : sel.parentTextFrames[0].parentStory.insertionPoints[0];
    } catch(e){ alert("텍스트 안을 선택하세요."); return; }

    var story = ip.parentStory;

    function isBlankPara(p){
        var t = (p.contents||"").replace(/[\s\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\r\n\t]+/g,"");
        return t === "";
    }

    // 머리말 패턴 확장:
    // - "2. L3-본문2" (기존)
    // - "2. p22-no.01", "3) p23 - no.02" 등: 하이픈/공백 유연, 대소문자 무시
    var reHeader = /^\s*\d+\s*[.)]?\s*(?:L\d+\s*-\s*본문\d+|p\d+\s*-\s*no\.?\s*\d+)\b.*$/i;

    var reSupp   = /^\s*Supplementary Reading\s*$/i;

    app.doScript(function(){
        var paras = story.paragraphs;

        // 뒤에서 앞으로(삭제 안전)
        for (var i = paras.length - 1; i >= 0; i--) {
            paras = story.paragraphs;
            if (i >= paras.length) continue;

            var header = paras[i];
            if (header.parentStory !== story) continue;

            var htxt = header.contents || "";
            if (!(reHeader.test(htxt) || reSupp.test(htxt))) continue;

            // 1) 헤더 위에서 가장 가까운 '비어 있지 않은' 문단 찾기
            var top = i - 1;
            while (top >= 0 && paras[top].parentStory === story && isBlankPara(paras[top])) top--;

            if (top >= 0) {
                // 1-a) 찾은 문단 끝 '리턴 앞'에 FRAME_BREAK 삽입(중복 방지)
                try {
                    var ipBeforeCR = paras[top].insertionPoints[-2];
                    var lastBeforeCR = paras[top].characters.length > 1 ? paras[top].characters[-2] : null;
                    var already = (lastBeforeCR && lastBeforeCR.contents === SpecialCharacters.FRAME_BREAK);
                    if (!already) ipBeforeCR.contents = SpecialCharacters.FRAME_BREAK;
                } catch(_e0){}

                // 1-b) 그 문단과 헤더 사이에 낀 빈 단락 전부 삭제
                for (var k = top + 1; k < i; k++) {
                    if (k >= story.paragraphs.length) break;
                    var mid = story.paragraphs[k];
                    if (mid.parentStory !== story) break;
                    if (isBlankPara(mid)) { try { mid.remove(); k--; i--; } catch(_e1){} }
                }
            } else {
                // 스토리 첫 문단이 헤더인 예외: 헤더 맨 앞에 브레이크만 넣고 처리
                try { header.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(_e0a){}
            }

            // 2) 헤더 단락 삭제(첫 단락 예외는 텍스트만 제거)
            try {
                if (top >= 0) {
                    header.remove();
                } else {
                    var len = header.characters.length;
                    if (len > 1) header.characters.itemByRange(1, len-1).remove();
                }
            } catch(_e2){}

            // 3) 헤더가 있던 자리 아래 연속 빈 단락 삭제
            paras = story.paragraphs;
            var down = Math.min(i, paras.length - 1);
            while (down < paras.length && paras[down].parentStory === story && isBlankPara(paras[down])) {
                try { paras[down].remove(); } catch(_e3){ break; }
                paras = story.paragraphs;
            }
        }
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Break at nonblank before headers; remove bridging blanks + header");

})();