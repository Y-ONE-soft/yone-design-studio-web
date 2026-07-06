// InDesign ExtendScript (JSX)
(function () {
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    var doc = app.activeDocument;
    if (app.selection.length === 0) { alert("텍스트를 선택하거나 커서를 문단에 두세요."); return; }

    function getParagraphStyleByGroupPath(groupName, styleName) {
        try {
            var g = doc.paragraphStyleGroups.itemByName(groupName);
            if (!g.isValid) return null;
            var s = g.paragraphStyles.itemByName(styleName);
            return s.isValid ? s : null;
        } catch (e) { return null; }
    }
    function getBasicParagraphStyle() {
        // 지역화 대응: [기본 단락] / [Basic Paragraph] 순으로 탐색, 실패 시 index 0 확인
        var names = ["[기본 단락]", "[Basic Paragraph]"];
        for (var i=0;i<names.length;i++){
            try{
                var s = doc.paragraphStyles.itemByName(names[i]);
                if (s && s.isValid) return s;
            }catch(_){}
        }
        try {
            var s0 = doc.paragraphStyles[0];
            if (s0 && s0.isValid && /^\[(기본 단락|Basic Paragraph)\]$/.test(s0.name)) return s0;
        } catch(_){}
        return null;
    }

    // 스타일 (STEP 01)
    var styleA2     = getParagraphStyleByGroupPath("STEP 01", "A2_본문 박스");
    var styleNum    = getParagraphStyleByGroupPath("STEP 01", "B2_내용 종합 번호");
    var styleChoice = getParagraphStyleByGroupPath("STEP 01", "B2_내용 종합 선지");
    var styleBasic  = getBasicParagraphStyle();

    if (!styleA2 || !styleNum || !styleChoice) {
        alert("단락 스타일 확인:\n- STEP 01 / A2_본문 박스\n- STEP 01 / B2_내용 종합 번호\n- STEP 01 / B2_내용 종합 선지");
        return;
    }

    var sel = app.selection[0], ip;
    try {
        ip = sel.hasOwnProperty("insertionPoints") ? sel.insertionPoints[0] : sel.parentTextFrames[0].parentStory.insertionPoints[0];
    } catch (e) { alert("텍스트 안을 선택하세요."); return; }

    var basePara  = ip.paragraphs[0];
    var baseStyle = basePara.appliedParagraphStyle;
    var story     = basePara.parentStory;

    // 패턴
    var reNumStart     = /^\s*\((\d+)\)/;           // (1)~(무제한)
    var reCircledStart = /^(?:\s*[\u2460-\u2473])/; // ①~⑳

    // ========== 0) 시작 시 선택한 스토리의 모든 문단을 [기본 단락]으로 리셋 ==========
    if (styleBasic) {
        var allParas = story.paragraphs;
        for (var r=0; r<allParas.length; r++) {
            try { allParas[r].appliedParagraphStyle = styleBasic; } catch(_){}
        }
    }

    // ========== 0.5) "N강 N번 NNNNNN" 형식 헤더를 대괄호로 감싸기 ==========
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^\\s*(\\d+\\s*강\\s*\\d+\\s*번\\s*\\d{6})\\s*$";
    app.changeGrepPreferences.changeTo = "[$1]";
    story.changeGrep();
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

    // 1) '[' 앞에 프레임브레이크 삽입(중복 방지)
    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;
    app.findGrepPreferences.findWhat = "\\[";
    var opens = story.findGrep();
    for (var i=0;i<opens.length;i++){
        var idx = opens[i].index;
        if (idx>0){
            var prevCh = story.characters[idx-1];
            if (prevCh.contents !== SpecialCharacters.FRAME_BREAK){
                story.characters[idx].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
            }
        }
    }

    // 2) 닫힘 ']' 뒤 첫 단락 포함 → 다음 '['/번호/선지 전까지 전부 A2 적용
    var paras = story.paragraphs;
    for (var pIdx = 0; pIdx < paras.length; pIdx++) {
        var p = paras[pIdx];
        var t = p.contents || "";
        if (t.indexOf("[") === -1) continue;                 // 여는 괄호가 있는 문단만 처리

        // 같은 섹션 내 닫힘 ']' 문단 찾기 (없으면 같은 문단으로 간주)
        var closeIdx = pIdx;
        for (var s = pIdx; s < paras.length; s++) {
            var q = paras[s], qt = q.contents || "";
            if (qt.indexOf("]") !== -1) { closeIdx = s; break; }
            if (s > pIdx && qt.indexOf("[") !== -1) { break; } // 다음 섹션 시작되면 중단
        }

        // 시작점: 닫힘 대괄호 문단 다음 (빈 줄 여러 개 스킵)
        var start = closeIdx + 1;
        while (start < paras.length) {
            var st = (paras[start].contents||"").replace(/[\s\u00A0\r\n]+/g, "");
            if (st === "") { start++; } else { break; }
        }

        // 블록 적용: 다음 '[' 또는 번호/선지 시작 전까지 전체 A2
        var z = start;
        for (; z < paras.length; z++) {
            var r = paras[z], rt = r.contents || "";
            if (rt.indexOf("[") !== -1) break;                       // 다음 섹션
            if (reNumStart.test(rt) || reCircledStart.test(rt)) break; // 번호/선지 시작
            try { r.appliedParagraphStyle = styleA2; } catch(_){}
        }

        // 다음 섹션으로 점프
        pIdx = z - 1;
    }

    // 3) 번호 문단(B2_내용 종합 번호)
    paras = story.paragraphs;
    for (var j=0; j<paras.length; j++){
        var pj = paras[j], txt = pj.contents || "";
        if (reNumStart.test(txt)) pj.appliedParagraphStyle = styleNum;
    }

    // 4) 동그라미 숫자 문단(B2_내용 종합 선지)
    for (var m=0; m<paras.length; m++){
        var pk = paras[m], t2 = pk.contents || "";
        if (reCircledStart.test(t2)) pk.appliedParagraphStyle = styleChoice;
    }

    // 5) 문서 마지막 \r\r\r → \r\r (GREP find/change 방식)
    try {
        app.findGrepPreferences = NothingEnum.nothing;
        app.changeGrepPreferences = NothingEnum.nothing;

        app.findGrepPreferences.findWhat = "\\r{2,}\\s*$";
        app.changeGrepPreferences.changeTo = "\\r";

        story.changeGrep();

    } catch(_){ }

    // GREP 리셋
    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

})();