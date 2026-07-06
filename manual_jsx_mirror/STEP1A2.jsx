// InDesign ExtendScript (.jsx)
// 선택한 스토리에만 적용. 시작 시 [기본 단락]으로 변경.
// 수정 범위(요청한 3가지 문제만):
//  1) "❮ T / F ❯" 를 확실히 찾고 → 문단에 A2_OX문제 적용 → 토큰 제거 → 라벨 "TF 버튼" 객체(문서 내 숨김 PNG) 복제/인라인 삽입
//  2) 닫힘 대괄호 뒤 ‘빈 줄 1개 이상’을 건너뛰고 만나는 첫 영어 단락에 A2_본문 박스 적용
//  3) OX 스타일 미적용 이슈(문단 레벨로 확실히 적용)
//  + 완료 후: 해당 스토리의 첫 텍스트 프레임을 선택한 상태로 BridgeTalk을 통해 Samples/JavaScript/SplitStory.jsx 실행(크래시 회피)
(function () {
    if (app.documents.length === 0) { alert("문서 없음"); return; }
    if (app.selection.length === 0 || !app.selection[0].hasOwnProperty("parentStory")) { alert("스토리를 선택하세요."); return; }

    var doc = app.activeDocument;
    var story = app.selection[0].parentStory;

    // ========== 스타일 ==========
    function getBasicPara(doc){
        try { var byId = doc.paragraphStyles.itemByName("$ID/NormalParagraphStyle"); if (byId && byId.isValid) return byId; } catch(_){}
        try { var kr = doc.paragraphStyles.itemByName("[기본 단락]"); if (kr && kr.isValid) return kr; } catch(_){}
        try { var en = doc.paragraphStyles.itemByName("[Basic Paragraph]"); if (en && en.isValid) return en; } catch(_){}
        return null;
    }
    function getParaStyle(groupName, styleName){
        try {
            var g = doc.paragraphStyleGroups.itemByName(groupName);
            if (g && g.isValid) {
                var st = g.paragraphStyles.itemByName(styleName);
                if (st && st.isValid) return st;
            }
        } catch(_){}
        return null;
    }
    var basicPara = getBasicPara(doc);
    var stBodyBox = getParaStyle("STEP 01", "A2_본문 박스");
    var stOX      = getParaStyle("STEP 01", "A2_OX문제");

    // ========== 유틸 ==========
    function parasOf(st){ return st.paragraphs.everyItem().getElements(); }
    function ptext(p){ return (p.contents || "").replace(/\r$/, ""); }
    function isBracketPara(p){ return /^\s*\[[^\]]+\]\s*$/.test(ptext(p)); }
    function isEnglishPara(p){ return /[A-Za-z]/.test(ptext(p)); }
    // 앵커(■, \uFFFC) 및 공백 제거 후 비었으면 true
    function isBlankLikePara(p){
        var t = (p.contents || "");
        t = t.replace(/\r/g,"").replace(/\uFFFC/g,"").replace(/\uFEFF/g,"").replace(/\s/g,"");
        return t.length === 0;
    }
    function findLabeledItem(doc, label){
        var items = doc.allPageItems, it;
        for (var i=0;i<items.length;i++){
            it = items[i];
            try { if (it.label === label) return it; } catch(_){}
        }
        return null;
    }

    // ========== 0) 선택 스토리 전체를 [기본 단락] ==========
    if (basicPara) {
        var allP = parasOf(story);
        for (var i=0;i<allP.length;i++){ try{ allP[i].appliedParagraphStyle = basicPara; }catch(_e){} }
    }

    // ========== 0.5) "N강 N번 NNNNNN" 형식 헤더를 대괄호로 감싸기 ==========
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^\\s*(\\d+\\s*강\\s*\\d+\\s*번\\s*\\d{6})\\s*$";
    app.changeGrepPreferences.changeTo = "[$1]";
    story.changeGrep();
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

    // ========== 1) 대괄호 인덱스 수집 ==========
    var paras = parasOf(story);
    var bracketIdx = [];
    for (var i2=0; i2<paras.length; i2++) if (isBracketPara(paras[i2])) bracketIdx.push(i2);

    // ========== 2) 닫힘 대괄호 → (빈 줄 1개 이상 허용) → 첫 영어 단락에 본문박스 ==========
    if (stBodyBox) {
        for (var k=0; k<bracketIdx.length; k++){
            paras = parasOf(story);
            // 최신 인덱스 재수집
            bracketIdx = [];
            for (var t=0; t<paras.length; t++) if (isBracketPara(paras[t])) bracketIdx.push(t);

            var bi = bracketIdx[k];
            var tIdx = bi + 1;
            while (tIdx < paras.length && isBlankLikePara(paras[tIdx])) tIdx++; // 빈 줄 여러 개도 통과
            if (tIdx < paras.length && isEnglishPara(paras[tIdx])) {
                try { paras[tIdx].appliedParagraphStyle = stBodyBox; } catch(_e1){}
            }
        }
    }

    // ========== 3) 첫 번째 대괄호 제외, 나머지에 프레임 브레이크 ==========
    for (var m=1; m<bracketIdx.length; m++){
        paras = parasOf(story);
        bracketIdx = [];
        for (var u=0; u<paras.length; u++) if (isBracketPara(paras[u])) bracketIdx.push(u);
        var bi2 = bracketIdx[m];
        try { paras[bi2].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(_e2){}
    }

    // ========== 4) "❮ T / F ❯" 처리(토큰 확실 매칭 + OX 스타일 + 라벨 복제 인라인) ==========
    var tfSource = findLabeledItem(doc, "TF 버튼"); // 숨겨둔 PNG(프레임)
    if (tfSource) {
        // 잠금/레이어 잠금이 걸려 있어도 복제 가능하도록 일시 해제
        var wasLocked = tfSource.locked; tfSource.locked = false;
        try { if (tfSource.itemLayer) tfSource.itemLayer.locked = false; } catch(_){}
        try { if (tfSource.itemLayer) tfSource.itemLayer.visible = true; } catch(_){}

        // 4-1) GREP로 토큰 찾기 (유니코드 각괄호, 공백 변형 허용)
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        // \x{276E} = ❮, \x{276F} = ❯
        app.findGrepPreferences.findWhat = "\\x{276E}\\s*T\\s*/\\s*F\\s*\\x{276F}";
        var hits = story.findGrep();

        // 실패 대비: 텍스트 찾기도 한번 더
        if (hits.length === 0) {
            app.findTextPreferences = app.changeTextPreferences = NothingEnum.NOTHING;
            app.findTextPreferences.findWhat = "❮ T / F ❯";
            hits = story.findText();
            app.findTextPreferences = app.changeTextPreferences = NothingEnum.NOTHING;
        }

        // 뒤에서 앞으로
        for (var h = hits.length - 1; h >= 0; h--) {
            var range = hits[h];

            // 문단 스타일(OX) 먼저
            if (stOX) {
                try { range.insertionPoints[0].paragraphs[0].appliedParagraphStyle = stOX; } catch(_e3){}
            }

            try {
                // 소스 복제 → 인라인 삽입 → 토큰 제거
                var ip = range.insertionPoints[0];
                var clone = tfSource.duplicate();
                clone.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
                try { clone.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}
                range.remove();
            } catch(_e4) {}
        }

        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        tfSource.locked = wasLocked;
    } else {
        // 소스가 없으면 토큰 삭제 + OX 스타일만
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "\\x{276E}\\s*T\\s*/\\s*F\\s*\\x{276F}";
        var hits2 = story.findGrep();
        for (var i3 = hits2.length - 1; i3 >= 0; i3--) {
            var r = hits2[i3];
            if (stOX) { try { r.insertionPoints[0].paragraphs[0].appliedParagraphStyle = stOX; } catch(_e5){} }
            try { r.remove(); } catch(_e6){}
        }
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    }
})();