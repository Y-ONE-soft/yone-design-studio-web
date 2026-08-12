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

    // ── W53: 발문 인용구 밑줄 ────────────────────────────────────────────
    // "밑줄 친 <영어 인용문>가 …" 형태의 발문은 인용문 자체에 밑줄이 들어가야
    // 한다 (배재1 워크북01 검수 21건 실측 — v1은 마커(ⓐ/(A)) 뒤 영어만 처리해
    // 이 유형이 통째로 빠졌다). 한글 조사 앞에서 끊기므로 조사/구두점은
    // 자연히 제외된다. 이미 밑줄된 인용구는 건드리지 않는다.
    var quoted = 0;
    try {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        // 밑줄 친 + 영문으로 시작하는 인용구 (한글/줄바꿈 앞까지)
        app.findGrepPreferences.findWhat =
            "(?<=밑줄 친 )[A-Za-z][^가-힣\\r]{1,120}";
        var found = doc.findGrep();
        for (var fi = 0; fi < found.length; fi++) {
            var t = found[fi];
            var s = String(t.contents);
            // 뒤쪽 공백만 제거. 여는 큰따옴표가 있으면 닫는 따옴표까지가
            // 인용문이라 남긴다 (the “mother of forensic science.” 실측).
            var keep = s.replace(/\s+$/, "");
            var hasQuote = /[“"]/.test(keep);
            if (!hasQuote) { keep = keep.replace(/[”’']+$/, ""); }
            if (keep.length < 2 || !/[A-Za-z]{2}/.test(keep)) { continue; }
            var rng = t;
            try {
                if (keep.length < s.length) {
                    rng = t.characters.itemByRange(0, keep.length - 1);
                }
            } catch (_e0) { rng = t; }
            var st = null;
            try { st = rng.underline; } catch (_e1) {}
            // 인용부호는 특수문자라 범위 underline 판정에서 빠진다 —
            // 따옴표 인용문은 상태와 무관하게 재적용(idempotent).
            if (st === true && !hasQuote) { continue; }  // 이미 밑줄
            try {
                rng.appliedCharacterStyle = csUL;
                quoted++;
            } catch (_e2) {}
        }
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
    } catch (_e3) {}

    app.scriptPreferences.enableRedraw = true;
    alert("밑줄 적용 완료: 마커 " + count + "개 / 발문 인용구 " + quoted + "개");
})();
