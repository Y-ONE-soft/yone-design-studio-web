/* =========================
   InDesign ExtendScript (.jsx)
   대상: "선택한 스토리" 한정
   선처리: 문자스타일 없음([None]), 단락스타일 대화>스크립트
   로직:
   0) \r\r -> \r 로 빈 줄 정리
   0-1) 문장 내 TAB(\t) 모두 삭제 (공백은 유지)
   1) "[Script]" 가 들어간 문단 → 대화>카테고리
   2) 한글(가-힣)을 포함하는 문단 → 대화>[해석]
   2-1) [해석] 단락 내에서 "\r   " → "\r"
   3) 동그라미 숫자 ①~⑨ → 배경(네거티브) 동그라미 ❶~❾
   * 다른 로직에는 영향 없음 (선택 스토리 범위 내에서만 find/change)
   ========================= */

(function(){
    // --- 기본 검증 ---
    if (app.documents.length === 0) { alert("문서 없음"); return; }
    if (app.selection.length === 0 || !app.selection[0].hasOwnProperty("parentStory")) {
        alert("스토리를 선택하세요."); return;
    }

    var doc   = app.activeDocument;
    var story = app.selection[0].parentStory;

    // --- 헬퍼: 단락/문자 스타일 가져오기 ---
    function getParaStyle(groupName, styleName){
        try{
            var g = doc.paragraphStyleGroups.itemByName(groupName);
            if (g && g.isValid){
                var s = g.paragraphStyles.itemByName(styleName);
                if (s && s.isValid) return s;
            }
        }catch(_){}
        return null;
    }
    function getCharStyleNone(){
        // Try locale-agnostic ways to fetch the "None" character style
        try{
            var s0 = doc.characterStyles.itemByName("[None]");
            if (s0 && s0.isValid) return s0;
        }catch(_){}
        try{
            var s1 = doc.characterStyles.itemByName("[없음]");
            if (s1 && s1.isValid) return s1;
        }catch(_){}
        try{
            var s2 = doc.characterStyles.itemByName("없음");
            if (s2 && s2.isValid) return s2;
        }catch(_){}
        try{
            // Index 0 is always the built‑in "None"
            var s3 = doc.characterStyles[0];
            if (s3 && s3.isValid) return s3;
        }catch(_){}
        return null;
    }
    function resetFindChange(){
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findTextPreferences = app.changeTextPreferences = NothingEnum.NOTHING;
        app.findChangeGrepOptions = NothingEnum.NOTHING;
        app.findChangeTextOptions = NothingEnum.NOTHING;
    }

    // --- 대상 스타일 핸들 ---
    var psScript   = getParaStyle("대화", "스크립트");
    var psCategory = getParaStyle("대화", "카테고리");
    var psKorean   = getParaStyle("대화", "해석");
    var csNone     = getCharStyleNone(); // locale-agnostic [None]

    if (!psScript || !psCategory || !psKorean || !csNone){
        var missing = [];
        if(!psScript)   missing.push("단락 스타일 대화>스크립트");
        if(!psCategory) missing.push("단락 스타일 대화>카테고리");
        if(!psKorean)   missing.push("단락 스타일 대화>해석");
        if(!csNone)     missing.push("문자스타일 없음([None])");
        alert("필요한 스타일을 찾지 못했습니다.\n누락: " + missing.join(", "));
        return;
    }

    // --- 선처리: 선택 스토리 전체에 문자스타일 [없음] + 단락스타일 [스트립트] 지정 ---
    try{
        story.characters.everyItem().appliedCharacterStyle = csNone;
    }catch(_){}
    try{
        story.paragraphs.everyItem().appliedParagraphStyle = psScript;
    }catch(_){}

    // --- 0) 빈 줄 정리: \r\r+ → \r (선택 스토리만) ---
    app.findGrepPreferences.findWhat   = "\\r{2,}";
    app.changeGrepPreferences.changeTo = "\\r";
    story.changeGrep();
    resetFindChange();
    // 0-1) 문장 내 TAB(\t) 삭제 (공백은 유지)
    app.findGrepPreferences.findWhat   = "\\t";
    app.changeGrepPreferences.changeTo = "";
    story.changeGrep();
    resetFindChange();
    // 문단 배열 캐시 (Step 1/2에서 사용) — 정리 후 최신 참조로 갱신
    var paras = story.paragraphs.everyItem().getElements();

    // --- 1) 문단 어딘가에 "[Script]" 문자열이 있으면 → 대화>카테고리
    var reTagScript = /\[\s*[Ss]cript\s*\]/;
    for (var i=0; i<paras.length; i++){
        try{
            var p = paras[i];
            if (!p || !p.isValid) continue;
            var t = p.contents || "";
            if (reTagScript.test(t)){
                p.appliedParagraphStyle = psCategory;
            }
        }catch(_){}
    }

    // --- 2) 한글(가-힣)을 포함하는 문단 → [해석]
    //     주의: 이미 [카테고리]로 바뀐 문단이라도 한글 포함이면 [해석]이 이깁니다(요청 순서 준수)
    var reHangul = /[\uAC00-\uD7A3]/;
    for (var j=0; j<paras.length; j++){
        try{
            var pj = paras[j];
            if (!pj || !pj.isValid) continue;
            var t  = pj.contents || "";
            if (reHangul.test(t) && !reTagScript.test(t)){
                pj.appliedParagraphStyle = psKorean;
            }
        }catch(_){}
    }

    // --- 2-1) [해석] 단락 내에서 "\r   " → "\r"
    resetFindChange();
    app.findGrepPreferences.findWhat = "\\r {3}";
    app.changeGrepPreferences.changeTo = "\\r";
    story.changeGrep();
    resetFindChange();

    // --- 3) ①~⑨ → ❶~❾ 치환 (선택 스토리 한정, 안전하게 개별 매핑) ---
    var mapCircled = {
        "①":"❶","②":"❷","③":"❸","④":"❹","⑤":"❺",
        "⑥":"❻","⑦":"❼","⑧":"❽","⑨":"❾"
    };
    for (var k in mapCircled){
        if (!mapCircled.hasOwnProperty(k)) continue;
        resetFindChange();
        app.findTextPreferences.findWhat   = k;
        app.changeTextPreferences.changeTo = mapCircled[k];
        story.changeText();
    }
    resetFindChange();

    // 끝
})();