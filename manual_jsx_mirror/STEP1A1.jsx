// InDesign ExtendScript (.jsx) — 확정본
(function () {
    if (app.documents.length === 0) { alert("문서 없음"); return; }
    var doc = app.activeDocument;

    // 대상 스토리: 선택이 있으면 그 스토리, 없으면 전체
    var stories = (app.selection.length > 0 && app.selection[0].hasOwnProperty("parentStory"))
        ? [app.selection[0].parentStory]
        : doc.stories.everyItem().getElements();

    // 단락 스타일 참조(없으면 적용만 생략)
    var targetStyle = null;
    try {
        var grp = doc.paragraphStyleGroups.itemByName("STEP 01");
        if (grp.isValid) {
            var st = grp.paragraphStyles.itemByName("A1_어휘 선택");
            if (st.isValid) targetStyle = st;
        }
    } catch (e) {}

    // [기본 단락] 스타일 참조(로케일 안전)
    var basicPara = null;
    try {
        // $ID/NormalParagraphStyle 은 로케일과 무관하게 [기본 단락]/[Basic Paragraph] 를 가리킴
        var byId = doc.paragraphStyles.itemByName("$ID/NormalParagraphStyle");
        if (byId && byId.isValid) basicPara = byId;
    } catch (e1) {}
    if (!basicPara) {
        try {
            var kr = doc.paragraphStyles.itemByName("[기본 단락]");
            if (kr && kr.isValid) basicPara = kr;
        } catch (e2) {}
    }
    if (!basicPara) {
        try {
            var en = doc.paragraphStyles.itemByName("[Basic Paragraph]");
            if (en && en.isValid) basicPara = en;
        } catch (e3) {}
    }

    function parasOf(story){ return story.paragraphs.everyItem().getElements(); }
    function ptext(p){ return (p.contents||"").replace(/\r$/, ""); }
    function isBracketPara(p){ return /^\s*\[[^\]]+\]\s*$/.test(ptext(p)); }
    function isEmptyPara(p){ return /^\s*$/.test(ptext(p)); }

    for (var s = 0; s < stories.length; s++) {
        var story = stories[s];

        // 0) 전체 문단을 [기본 단락]으로 변경
        if (basicPara) {
            try {
                var allParas = parasOf(story);
                for (var ap = 0; ap < allParas.length; ap++) {
                    try { allParas[ap].appliedParagraphStyle = basicPara; } catch(_e){}
                }
            } catch (_e2) {}
        }

        // 1) 특수기호 치환
        app.findTextPreferences = app.changeTextPreferences = NothingEnum.NOTHING;
        app.findTextPreferences.findWhat = "❮";
        app.changeTextPreferences.changeTo = "[";
        story.changeText();
        app.findTextPreferences.findWhat = "❯";
        app.changeTextPreferences.changeTo = "]";
        story.changeText();
        app.findTextPreferences = app.changeTextPreferences = NothingEnum.NOTHING;

        // 2) 빈 줄 정리: 연속 리턴만 축약 (대괄호 '바로 앞'의 정상 줄바꿈은 건드리지 않는다)
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "\\r{2,}";
        app.changeGrepPreferences.changeTo = "\\r";
        story.changeGrep();
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

        // 2.5) "N강 N번 NNNNNN" 형식 헤더를 대괄호로 감싸기
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "^\\s*(\\d+\\s*강\\s*\\d+\\s*번\\s*\\d{6})\\s*$";
        app.changeGrepPreferences.changeTo = "[$1]";
        story.changeGrep();
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

        // 3) 대괄호 문단 목록
        var paras = parasOf(story);
        var idxList = [];
        for (var i=0;i<paras.length;i++) if (isBracketPara(paras[i])) idxList.push(i);

        // 4) 두 번째 대괄호부터 처리
        for (var k=1; k<idxList.length; k++){
            paras = parasOf(story);

            // 인덱스 재수집(앞 단계에서 문단 수 변동 가능)
            idxList = [];
            for (var ii=0; ii<paras.length; ii++) if (isBracketPara(paras[ii])) idxList.push(ii);

            var bi = idxList[k];

            // 4-1) [본문] 바로 위에 '빈 문단'이 끼어 있으면 제거(텍스트 있는 문단은 절대 건드리지 않음)
            while (bi>0 && isEmptyPara(paras[bi-1])) {
                try { paras[bi-1].remove(); } catch(e){}
                paras = parasOf(story);
                idxList = [];
                for (var jj=0; jj<paras.length; jj++) if (isBracketPara(paras[jj])) idxList.push(jj);
                bi = idxList[k];
            }

            // 4-2) 프레임 브레이크를 '대괄호 문단 시작'에 삽입
            try { paras[bi].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e){}
        }

        // 5) 스타일 적용: 각 대괄호 다음 문단
        if (targetStyle) {
            paras = parasOf(story);
            for (var j=0; j<paras.length; j++){
                if (isBracketPara(paras[j]) && j+1<paras.length) {
                    try { paras[j+1].appliedParagraphStyle = targetStyle; } catch(e2){}
                }
            }
        }

        // 6) "2. 어휘2단계_Hard" 문장(단독 문단) 삭제
        var delParas = parasOf(story);
        for (var d = delParas.length - 1; d >= 0; d--) {
            var t = ptext(delParas[d]);
            if (/^\s*2\.\s*어휘2단계_Hard\s*$/.test(t)) {
                try { delParas[d].remove(); } catch(_delE){}
            }
        }
    }

})();