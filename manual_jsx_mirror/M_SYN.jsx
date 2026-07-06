/* ===== InDesign ExtendScript (.jsx) =====
   선택 스토리 기준
   1) 특수점() 삭제
   2) 각 문단 맨 앞 공백/탭 삭제
   3) 영단어 4개 이상 포함 ‘문단’을 어휘>예문 단락스타일로 변경
   + 전체 문자스타일 [없음] 적용
*/
(function () {
    if (app.documents.length === 0) { alert("문서 없음"); return; }
    if (app.selection.length === 0 || !app.selection[0].hasOwnProperty("parentStory")) {
        alert("스토리를 선택하세요."); return;
    }
    var doc   = app.activeDocument;
    var story = app.selection[0].parentStory;

    // ---- 스타일 헬퍼 ----
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
    function charNone(){
        // 로컬라이즈 안전하게 [없음] 조회
        try {
            // 보통 index 0이 [없음]
            var s = doc.characterStyles[0];
            if (s && s.isValid) return s;
        } catch(_){}
        try {
            var s2 = doc.characterStyles.itemByName("$ID/[No character style]");
            if (s2 && s2.isValid) return s2;
        } catch(_){}
        try {
            var s3 = doc.characterStyles.itemByName("[None]");
            if (s3 && s3.isValid) return s3;
        } catch(_){}
        try {
            var s4 = doc.characterStyles.itemByName("[없음]");
            if (s4 && s4.isValid) return s4;
        } catch(_){}
        return null;
    }

    var wordStyle    = getParaStyle("어휘", "단어");
    var exampleStyle = getParaStyle("어휘", "예문");
    if(!wordStyle){
        alert("단락스타일 '어휘 > 단어'를 찾을 수 없습니다.");
        return;
    }
    if(!exampleStyle){
        alert("단락스타일 '어휘 > 예문'을 찾을 수 없습니다.");
        return;
    }
    var csNone = charNone();
    if(!csNone){
        alert("문자스타일 [없음]을 찾을 수 없습니다.");
        return;
    }
    // ---- (0-1) 단락스타일 어휘>단어 적용 (시작 조건) ----
    try { story.paragraphs.everyItem().appliedParagraphStyle = exampleStyle; } catch(_){}

    // ---- (0) 문자스타일 [없음] 적용 ----
    try { story.characters.everyItem().appliedCharacterStyle = csNone; } catch(_){}

    // 공통 GREP 옵션 초기화 헬퍼
    function resetGrep(){
        app.findGrepPreferences  = NothingEnum.NOTHING;
        app.changeGrepPreferences= NothingEnum.NOTHING;
        app.findChangeGrepOptions = NothingEnum.NOTHING;
        try{ app.findChangeGrepOptions.includeFootnotes = true; }catch(_){}
        try{ app.findChangeGrepOptions.includeHiddenLayers = false; }catch(_){}
        try{ app.findChangeGrepOptions.includeMasterPages = false; }catch(_){}
        try{ app.findChangeGrepOptions.includeLockedLayersForFind = false; }catch(_){}
        try{ app.findChangeGrepOptions.includeLockedStoriesForFind = false; }catch(_){}
    }


    // ---- (2) 문단 시작부 공백/탭 모두 삭제 ----
    resetGrep();
    app.findGrepPreferences.findWhat = "^[ \\t]+";
    app.changeGrepPreferences.changeTo = "";
    story.changeGrep();



    // ---- (3.1) [예문] 문단 맨 앞에 스크립트 레이블 '영영' 텍스트박스 삽입 (GREP ~c 동작 복제) ----
    // UI에서: Find: ^(?=[A-Za-z])  / Change: ~c  / Paragraph Style: 예문(어휘)
    // 구현 원리: 라벨이 '영영'인 텍스트박스를 선택→복사(app.copy) 후, changeGrep("~c")로 문단 맨 앞에 인라인 삽입
    (function(){
        function findLabeledItem(label){
            var items = doc.allPageItems;
            for(var i=0;i<items.length;i++){
                try{ if(items[i].label===label) return items[i]; }catch(_){ }
            }
            return null;
        }
        var src = findLabeledItem("영영");
        if(!src){ /* 템플릿이 없으면 조용히 패스 (다른 로직 영향 없음) */ return; }

        // 소스 / 레이어 잠금, 가시성 해제 후 복사
        var wasLocked = !!src.locked; src.locked = false;
        var lyr=null, lyrLocked=false, lyrVisible=true;
        try{ lyr = src.itemLayer; lyrLocked = !!lyr.locked; lyrVisible = !!lyr.visible; lyr.locked = false; lyr.visible = true; }catch(_){ }
        try{
            // 클립보드에 소스 복사 (changeTo:"~c"가 이 내용을 삽입)
            app.select(src);
            app.copy();

            // 예문(어휘) 단락이면서 문장 시작이 영문자인 경우에만 맨 앞에 삽입
            resetGrep();
            app.findGrepPreferences.appliedParagraphStyle = exampleStyle;
            app.findGrepPreferences.findWhat = "(?m)^(?=[A-Za-z])";
            app.changeGrepPreferences.changeTo = "~c "; // InDesign: 클립보드 내용 삽입 + 뒤 공백 1칸
            story.changeGrep();
        }catch(_){ }
        // 원상복구
        try{ app.select(null); }catch(_){ }
        try{ src.locked = wasLocked; if(lyr){ lyr.locked = lyrLocked; lyr.visible = lyrVisible; } }catch(_){ }
        resetGrep();
    })();

    // ---- (3.2) 특수점 ""이 포함된 문단을 [단어] 단락스타일로 즉시 지정 (줄바꿈 단계 이전에 처리) ----
    resetGrep();
    app.findGrepPreferences.findWhat = "(?m)^.*.*$"; // 해당 줄 전체 매치
    app.changeGrepPreferences.changeTo = "$0";       // 텍스트 변경 없음
    app.changeGrepPreferences.appliedParagraphStyle = wordStyle;
    story.changeGrep();

    // ---- (4) [예문] 문단 한정: 영어→한글 / 숫자→한글 경계 중 '가장 처음' 1회만 줄바꿈 삽입 ----
    // 요구사항: 한 문단 내에 여러 후보가 있어도 최초 1회만 적용
    (function(){
        var paras = story.paragraphs.everyItem().getElements();
        for(var i=0;i<paras.length;i++){
            var p = paras[i];
            try{ if(p.appliedParagraphStyle!=exampleStyle) continue; }catch(_){ continue; }
            // [요청] '' 포함 문단은 줄바꿈 금지 (SYN 동작 보존)
            try{ if((p.contents+"").indexOf("") !== -1) continue; }catch(_){ }
            // m1: 영어 뒤에(공백 허용) 한글이 오는 경계 — 줄바꿈은 '영어+공백 블록' 뒤에 삽입
            resetGrep();
            app.findGrepPreferences.appliedParagraphStyle = exampleStyle;
            app.findGrepPreferences.findWhat = "([A-Za-z])(?:[ \\t]*[\\.,;:!?\\)\\]\\\"\\'’”…]*)\\s*(?=[가-힣])";
            var m1 = p.findGrep();
            // m2: 숫자 바로 뒤에 한글이 오는 경계 — 줄바꿈은 숫자 앞에 삽입해야 하므로 매치 시작 위치 사용
            resetGrep();
            app.findGrepPreferences.appliedParagraphStyle = exampleStyle;
            app.findGrepPreferences.findWhat = "(\\d+)(?=[가-힣])";
            var m2 = p.findGrep();
            // 각 첫 매치의 오프셋 계산: m1은 경계가 '매치의 끝', m2는 '매치의 시작'
            var has1 = m1 && m1.length>0;
            var has2 = m2 && m2.length>0;
            if(!has1 && !has2) continue;
            // InDesign Text의 index 접근을 위해 insertionPoints 사용
            var chooseM1 = false;
            if(has1 && !has2){ chooseM1 = true; }
            else if(!has1 && has2){ chooseM1 = false; }
            else {
                var end1  = m1[0].insertionPoints[-1].index; // m1 경계: 매치 끝
                var start2= m2[0].insertionPoints[0].index;  // m2 경계: 매치 시작
                chooseM1 = (end1 <= start2); // 더 이른 경계 우선
            }
            if(chooseM1){
                try{ m1[0].contents = m1[0].contents + "\r"; }catch(_){}
            }else{
                try{ m2[0].contents = "\r" + m2[0].contents; }catch(_){}
            }
        }
        resetGrep();
    })();

    // ---- (4.1) [예문] 문단 한정: 문장 시작이 한글이면 맨 앞에 탭 1칸 삽입 ----
    resetGrep();
    app.findGrepPreferences.appliedParagraphStyle = exampleStyle;
    app.findGrepPreferences.findWhat = "(?m)^(?=[가-힣])"; // 문단 시작이 한글인 경우
    app.changeGrepPreferences.changeTo = "\t$0";          // 탭 한 칸 + 원문 유지
    story.changeGrep();

    // ---- (5) [단어] 문단 한정: 한글 뒤에 영어가 올 경우, 영어 바로 앞에 스크립트 레이블 "SYN" 아이콘 삽입 ----
    (function(){
        // 1) 숨겨둔 템플릿(텍스트 프레임/아이콘)을 라벨 "SYN"으로 찾아서 사용
        function getLabeledItem(doc, label){
            var items = doc.allPageItems;
            for(var i=0;i<items.length;i++){ try{ if(items[i].label===label) return items[i]; }catch(_){}} 
            return null;
        }
        var src = getLabeledItem(doc, "SYN");
        if(!src){ /* 소스 없음: 다른 로직에 영향 주지 않고 조용히 종료 */ return; }

        // 2) 대상: [어휘>단어] 문단에서 "한글 뒤에(공백 허용) 영어가 바로 오는" 경계
        var paras = story.paragraphs.everyItem().getElements();
        for(var i=0;i<paras.length;i++){
            var p = paras[i];
            try{ if(p.appliedParagraphStyle!=wordStyle) continue; }catch(_){ continue; }

            // GREP: (한글) + 공백* + (?=영어)  → 매치 끝 지점이 영어 시작 직전
            resetGrep();
            app.findGrepPreferences.appliedParagraphStyle = wordStyle;
            app.findGrepPreferences.findWhat = "([가-힣])\\s*(?=[A-Za-z])";
            var hits = p.findGrep();
            if(!hits || hits.length===0) continue;

            for(var k=0;k<hits.length;k++){
                var h = hits[k];
                try{
                    var ip  = h.insertionPoints[-1]; // 영어 시작 바로 앞 위치
                    var par = ip.parent;             // 삽입점의 부모 텍스트
                    var idx = ip.index;              // 숫자 인덱스 보존
                    // (A) 먼저 1/4-em 공백을 같은 위치에 삽입 (폴백 포함)
                    try{ par.insertionPoints[idx].contents = SpecialCharacters.FOUR_PER_EM_SPACE; }catch(_){ try{ par.insertionPoints[idx].contents = "\u2005"; }catch(__){} }
                    // (B) 같은 인덱스 위치에 아이콘을 인라인으로 삽입 → 결과: 아이콘 ▶ 1/4-em ▶ 영어
                    var icon = src.duplicate();
                    icon.anchoredObjectSettings.insertAnchoredObject(par.insertionPoints[idx], AnchorPosition.INLINE_POSITION);
                }catch(_){ /* 실패해도 다른 부분 영향 없이 무시 */ }
            }
        }
        resetGrep();
    })();


    // ---- (마지막) 특수점 "" 삭제 ----
    resetGrep();
    app.findGrepPreferences.findWhat = "^";
    app.changeGrepPreferences.changeTo = "";
    app.changeGrepPreferences.appliedParagraphStyle = wordStyle; // 단락스타일은 [단어] 유지
    story.changeGrep();

    // ---- (마지막+) 특수점 "" 잔여 전체 삭제 ----
    resetGrep();
    app.findGrepPreferences.findWhat = ""; // 라인 어디에 있든 전부 삭제
    app.changeGrepPreferences.changeTo = "";
    story.changeGrep();

    // 마무리
    resetGrep();
    alert("완료: 특수점 삭제 / 앞공백 삭제 / 영단어 4개 이상 문단 → 어휘>예문 적용");
})();