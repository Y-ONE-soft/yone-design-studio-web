// 워크북 밑줄 후처리 — run.jsx 실행 후 별도 실행
// STEP3 스토리에서 ⓐ~ⓔ / (A)~(E) 뒤 영어 텍스트에 지문 밑줄 적용
#target indesign

(function() {
    var doc = app.activeDocument;
    if (!doc || !doc.isValid) { alert("열린 문서가 없습니다"); return; }

    app.scriptPreferences.enableRedraw = false;

    var csUL = null;
    try { csUL = doc.characterStyles.itemByName("\uC9C0\uBB38 \uBC11\uC904"); } catch(_){}
    if (!csUL || !csUL.isValid) {
        try { csUL = doc.characterStyles.itemByName("\uBC11\uC904"); } catch(_){}
    }
    if (!csUL || !csUL.isValid) { alert("밑줄 문자스타일을 찾을 수 없습니다"); return; }

    // STEP3 스토리 찾기 (가장 큰 스토리)
    var story = null;
    for (var si = 0; si < doc.stories.length; si++) {
        if (doc.stories[si].characters.length > 50000) {
            story = doc.stories[si];
            break;
        }
    }
    if (!story) { alert("STEP3 스토리를 찾을 수 없습니다"); return; }

    var paras = story.paragraphs;
    var count = 0;
    var reMarker = /[\u24D0-\u24D4]/g;
    var reParens = /\([A-E]\)/g;

    for (var i = 0; i < paras.length; i++) {
        var pTxt = paras[i].contents || "";
        reMarker.lastIndex = 0;
        reParens.lastIndex = 0;
        if (!reMarker.test(pTxt) && !reParens.test(pTxt)) continue;

        // ⓐ~ⓔ
        reMarker.lastIndex = 0;
        var m;
        while ((m = reMarker.exec(pTxt)) !== null) {
            var start = m.index + 1;
            var nextM = reMarker.exec(pTxt);
            var end = nextM ? nextM.index : pTxt.length;
            if (nextM) reMarker.lastIndex = nextM.index;
            var sub = pTxt.substring(start, end);
            var engMatch = sub.match(/^[a-zA-Z][a-zA-Z ',\-]+/);
            if (engMatch) {
                try {
                    paras[i].characters.itemByRange(start, start + engMatch[0].length - 1).appliedCharacterStyle = csUL;
                    count++;
                } catch(_){}
            }
        }

        // (A)~(E)
        reParens.lastIndex = 0;
        while ((m = reParens.exec(pTxt)) !== null) {
            var start2 = m.index + 3;
            var nextP = reParens.exec(pTxt);
            var end2 = nextP ? nextP.index : pTxt.length;
            if (nextP) reParens.lastIndex = nextP.index;
            var sub2 = pTxt.substring(start2, end2);
            var engMatch2 = sub2.match(/^[a-zA-Z][a-zA-Z ',\-]+/);
            if (engMatch2) {
                try {
                    paras[i].characters.itemByRange(start2, start2 + engMatch2[0].length - 1).appliedCharacterStyle = csUL;
                    count++;
                } catch(_){}
            }
        }
    }

    app.scriptPreferences.enableRedraw = true;
    alert("밑줄 적용 완료: " + count + "개 구간");
})();
