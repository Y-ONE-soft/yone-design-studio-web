/**
 * STEP1C1.jsx — 선택한 스토리 전용(지정 순서 고정)
 * 0) 문자스타일 [없음], 단락스타일 [기본 단락] 재설정
 * 1) 패턴 정규화: 본문n→{본문n}, ANALYSIS→{분석}, no.01→{01}, 선행 잡텍스트 제거
 * 2) 프레임 브레이크: 두 번째 {부터 모두, 그리고 "공백≥3" 단락 앞에도 삽입
 *    + {…} 시작 단락은 [기본 단락]/[없음] 유지
 * 3) {…} 헤더 다음 블록에서 (A~Z) 시작 단락 → STEP 01/C1_문장 배열
 * 8) {…} 단락은 [기본 단락] 강제
 * 9) 정확히 \r\r(두 줄짜리 빈 문단) 위치 중, 다음 문단이 ‘공백≥3’이면 그 빈 문단에만 스크립트 레이블 ‘STEP1 화살표’ 부여
 *    + 문서에 레이블 'STEP1 화살표'인 아이콘이 있으면 그 아이콘을 인라인으로 한 번만 삽입
 */
(function(){
    if (app.documents.length === 0) { alert("문서가 없습니다."); return; }
    var doc = app.activeDocument;
    if (app.selection.length === 0) { alert("텍스트/텍스트프레임을 선택하세요."); return; }

    // 스토리 확보(선택 우선)
    var story = null;
    try {
        var s = app.selection[0];
        if (s && s.hasOwnProperty("parentStory")) story = s.parentStory;
        else if (s && s.constructor && s.constructor.name === "Story") story = s;
    } catch(e){}
    if (!story && doc.stories.length) story = doc.stories[0];
    if (!story) { alert("선택한 객체에서 스토리를 찾을 수 없습니다."); return; }

    // 단락 스타일 보장(지정 이름만 생성)
    function ensurePS(groupName, styleName){
        var g = doc.paragraphStyleGroups.itemByName(groupName);
        if (!g.isValid) g = doc.paragraphStyleGroups.add({name: groupName});
        var ps = g.paragraphStyles.itemByName(styleName);
        if (!ps.isValid) ps = g.paragraphStyles.add({name: styleName});
        return ps;
    }
    function getBasicParagraphStyle(){
        var names = ["[Basic Paragraph]", "[기본 단락]", "$ID/NormalParagraphStyle", "$ID/[Basic Paragraph]"]; 
        for (var i=0;i<names.length;i++){
            try {
                var cand = doc.paragraphStyles.itemByName(names[i]);
                if (cand && cand.isValid) return cand;
            } catch(e){}
        }
        // fallback: first non-"No" style in the list
        try {
            var all = doc.paragraphStyles;
            for (var j=0;j<all.length; j++){
                var nm = all[j].name || "";
                if (!/(\[?No\s*Paragraph\s*Style\]?|스타일\s*없음)/i.test(nm)) return all[j];
            }
        } catch(e){}
        // last resort
        try { return doc.paragraphStyles.add({name: "[Basic Paragraph]"}); } catch(e){}
        return doc.paragraphStyles[0];
    }
    var PS_BASIC = getBasicParagraphStyle();        // [기본 단락]/[Basic Paragraph]
    var CS_NONE  = doc.characterStyles[0];          // [None]
    var PS_C1_ARR       = ensurePS("STEP 01", "C1_문장 배열");
    var PS_C1_ARR_BTM   = ensurePS("STEP 01", "C1_문장 배열 하단");
    var PS_C1_ARR_BTM_T = ensurePS("STEP 01", "C1_문장 배열 하단 지문");
    var PS_C1_BOTTOM_Q  = ensurePS("STEP 01", "하단 문제");

    // GREP 헬퍼
    function resetGrep(){
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findChangeGrepOptions = NothingEnum.NOTHING;
        try { app.findChangeGrepOptions.caseSensitive = false; } catch(e){}
    }
    function grepChange(scope, findWhat, changeTo){
        resetGrep();
        app.findGrepPreferences.findWhat = findWhat;
        app.changeGrepPreferences.changeTo = changeTo;
        scope.changeGrep();
        resetGrep();
    }
    function grepFind(scope, findWhat){
        resetGrep();
        app.findGrepPreferences.findWhat = findWhat;
        var r = scope.findGrep();
        resetGrep();
        return r;
    }

    // 공백 유형 도우미
    function has3PlusGaps(str){
        if (!str) return false;
        var run=0,c;
        for (var i=0;i<str.length;i++){
            c = str.charCodeAt(i);
            if (c===0x20||c===0x09||c===0x00A0|| (c>=0x2000 && c<=0x200B) || c===0x202F || c===0x205F || c===0x3000){
                if (++run>=3) return true;
            } else { run=0; }
        }
        return false;
    }
    function isOnlySpaces(t){
        t = (t||"").replace(/\r$/, "");
        return /^[\u0009\u0020\u00A0\u2000-\u200B\u202F\u205F\u3000]*$/.test(t);
    }
    function isLoneBraceOrPair(t){
        t = (t||"").replace(/\r$/, "");
        return /^[ \t\u00A0\u2000-\u200B\u202F\u205F\u3000]*(\{[ \t\u00A0\u2000-\u200B\u202F\u205F\u3000]*\}|[\{\}])[ \t\u00A0\u2000-\u200B\u202F\u205F\u3000]*$/.test(t);
    }

    app.doScript(function(){
        // 0) 초기화: 문자 [없음]만
        try { story.characters.everyItem().appliedCharacterStyle = CS_NONE; } catch(e){}

        // 1) 패턴 정규화
        // "7강 4번 200324" 형식 → "{7강 4번 200324}" (다른 규칙들이 부분 매칭하지 않도록 가장 먼저)
        grepChange(story, "^(\\d+\\s*강\\s*\\d+\\s*번\\s*\\d{6})\\s*$", "{$1}");
        grepChange(story, "\\bno\\.\\s*(\\d{1,3})\\b", "{$1}"); // no.xx → {xx}
        grepChange(story, "\\bANALYSIS\\b", "{분석}");           // ANALYSIS → {분석}
        // 예: "1. L2-p.40 본문 1" → "{본문1}"
        grepChange(story,
          "\\b\\d+\\.\\s*L\\d+\\s*[-–—\\.]?\\s*p\\.?\\s*\\d+[^\\r\\n]*?본문\\s*(\\d+)\\b",
          "{본문$1}");
        // 변형 케이스 보강: "L2 p40 본문 3", "L3-p 7 본문 2" 등
        grepChange(story,
          "L\\d+\\s*[-–—\\.]?\\s*p\\.?\\s*\\d+[^\\r\\n]*?본문\\s*(\\d+)\\b",
          "{본문$1}");
        // "6. L1-Read More", "7. L2-Further Reading" 등 → "{영문헤더}" (본문 형식 제외)
        grepChange(story,
          "\\b\\d+\\.\\s*L\\d+\\s*[-–—]?\\s*([A-Za-z][A-Za-z\\s]+)\\b",
          "{$1}");
        grepChange(story, "(본문)\\s*(\\d+)", "{$1$2}");             // 본문n → {본문n}

        // ① "1. L1-p.17" → {본문1}
        grepChange(story,
          "\\b(\\d+)\\.\\s*L\\d+\\s*[-–—\\.]?\\s*p\\.?\\s*\\d+\\b",
          "{본문$1}");

        // ② 단독 "L1-p.18" (앞에 번호 없음) → 순차 본문 번호는 기존 번호 유지 (예: 2번째면 {본문2})
        //   → 단독 Lx-p.xx 는 일단 제거만 처리 (이미 위에서 번호 패턴이 처리됨)
        grepChange(story,
          "\\bL\\d+\\s*[-–—\\.]?\\s*p\\.?\\s*\\d+\\b",
          "");

        // ③ "8. L1-p.26 Further Reading" → {Further Reading}
        grepChange(story,
          "\\b\\d+\\.\\s*L\\d+\\s*[-–—\\.]?\\s*p\\.?\\s*\\d+\\s+([^\\r\\n]+)",
          "{$1}");
        // p51/p52 등 페이지 마커 기반 Practice 헤더 정규화 → {서술형 Practice}, {논술형 Practice}
        // 예: "5. p51-서술형 Practice" → "{서술형 Practice}"
        //     "6. p52-논술형 Practice" → "{논술형 Practice}"
        grepChange(story, "\\b\\d+\\.\\s*p\\d+\\s*[-–—]?\\s*서술형\\s*Practice\\b", "{서술형 Practice}");
        grepChange(story, "\\b\\d+\\.\\s*p\\d+\\s*[-–—]?\\s*논술형\\s*Prac(?:tice|ice)\\b", "{논술형 Practice}");
        for (var r=0;r<3;r++){
            grepChange(story, "((?:^|,)\\s*)[^\\{\\r\\n]*?(\\{[^\\}]+\\})", "$1$2");
            grepChange(story, "\\-\\s*(\\{)", "$1");
            grepChange(story, "(^|,)\\s+(\\{)", "$1$2");
        }

        // ★ 수정: 패턴 정규화 이후, 모든 {헤더} 다음 실제 단락을 C1_문장 배열 하단으로 지정
        try {
            var firstParas = story.paragraphs.everyItem().getElements();
            for (var fp = 0; fp < firstParas.length - 1; fp++) {
                var headerTxt = (firstParas[fp].contents || "").replace(/\r$/, "");
                if (/^\s*\{[^}]+\}/.test(headerTxt)) {
                    // 다음 실제 내용 단락 찾기 (빈 단락은 건너뜀)
                    var nx = fp + 1;
                    while (nx < firstParas.length && isOnlySpaces(firstParas[nx].contents)) nx++;
                    if (nx < firstParas.length) {
                        firstParas[nx].appliedParagraphStyle = PS_C1_ARR_BTM;
                    }
                }
            }
        } catch(e){}


        // 2) 프레임 브레이크 — {…}로 시작하는 '헤더 단락' 기준 + 공백≥3 단락
        //    ※ 문장 중간의 { 에는 절대 반응하지 않음. 첫 헤더는 스토리 시작으로 간주(분리 안 함).
        //    2-1) {…}로 시작하는 '헤더 단락' 인덱스 수집 → 두 번째부터 프레임 브레이크 삽입
        var parasAll = story.paragraphs.everyItem().getElements();
        var headerIdx = [];
        for (var i=0; i<parasAll.length; i++){
            var t = (parasAll[i].contents||"").replace(/\r$/, "");
            if (/^\s*\{[^}]+\}/.test(t)) headerIdx.push(i);
        }
        for (var h=headerIdx.length-1; h>=1; h--){ // 첫 헤더는 스토리 시작으로 간주하여 분리하지 않음
            try { parasAll[ headerIdx[h] ].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e){}
        }

        //    2-2) 공백≥3 단락 앞에서도 프레임 브레이크 (헤더 분할 지점과 중복 삽입 방지, 스토리 첫 단락 금지)
        parasAll = story.paragraphs.everyItem().getElements();
        var isHeaderMark = {};
        for (var _i=0; _i<headerIdx.length; _i++){ isHeaderMark[ headerIdx[_i] ] = true; }

        var idxsFB = [];
        for (var iFB=0; iFB<parasAll.length; iFB++){
            var tFB = (parasAll[iFB].contents||"").replace(/\r$/, "");
            if (has3PlusGaps(tFB)){
                if (!isHeaderMark[iFB] && iFB>0){ idxsFB.push(iFB); }
            }
        }
        for (var k=idxsFB.length-1; k>=0; k--){
            try { parasAll[ idxsFB[k] ].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e){}
        }

        // {…} 헤더는 [기본 단락]/문자[없음] 유지
        var parasFix = story.paragraphs.everyItem().getElements();
        for (var iFx=0;iFx<parasFix.length;iFx++){
            var tt = (parasFix[iFx].contents||"").replace(/\r$/, "");
            if (/^\s*\{[^}]+\}/.test(tt)){
                try { parasFix[iFx].appliedParagraphStyle = PS_BASIC; } catch(e){}
                try { parasFix[iFx].characters.everyItem().appliedCharacterStyle = CS_NONE; } catch(e){}
            }
        }

        // 3) 블록 내 (A~Z) 시작 → C1_문장 배열
        function isBraceHeader(p){ var t=(p.contents||"").replace(/\r$/, ""); return /^\s*\{[^}]+\}/.test(t); }
        function isWideIndent(p){ var t=(p.contents||"").replace(/\r$/, ""); return /^[ \t\u00A0\u2000-\u200B]{10,}\S/.test(t); }
        function startsWithAZ(p){ var t=(p.contents||"").replace(/\r$/, ""); return /^\s*\([A-Z]\)/.test(t); }
        var paras2 = story.paragraphs.everyItem().getElements();
        var inBlock=false;
        for (var i2=0;i2<paras2.length;i2++){
            var p=paras2[i2];
            if (i2>0 && isBraceHeader(paras2[i2-1])) inBlock=true;
            if (isWideIndent(p)) inBlock=false;
            if (inBlock && startsWithAZ(p)) { try { p.appliedParagraphStyle = PS_C1_ARR; } catch(e){} }
        }



        // 8) 마무리: {…} 단락은 [기본 단락] 강제
        var parasEnd = story.paragraphs.everyItem().getElements();
        for (var e1=0; e1<parasEnd.length; e1++){
            var tEnd = (parasEnd[e1].contents||"").replace(/\r$/, "");
            if (isLoneBraceOrPair(tEnd)) {
                try { parasEnd[e1].appliedParagraphStyle = PS_BASIC; } catch(e){}
            }
        }
        // 보강 GREP
        var loneBraceHits = grepFind(story, "^[\\x{0020}\\x{0009}\\x{00A0}\\x{2000}-\\x{200B}\\x{202F}\\x{205F}\\x{3000}]*\\{[\\x{0020}\\x{0009}\\x{00A0}\\x{2000}-\\x{200B}\\x{202F}\\x{205F}\\x{3000}]*$");
        for (var lb=0; lb<loneBraceHits.length; lb++) {
            try { loneBraceHits[lb].paragraphs[0].appliedParagraphStyle = PS_BASIC; } catch(e){}
        }
        var anyBraceHits = grepFind(story, "\\{");
        for (var ab=0; ab<anyBraceHits.length; ab++) {
            try { anyBraceHits[ab].paragraphs[0].appliedParagraphStyle = PS_BASIC; } catch(e){}
        }

        // ★ 최종 정리(위치 무관): C1_문장 배열 스타일인데 눈에 보이는 내용이 없으면 무조건 기본 단락으로 변경
        (function(){
            function psEq(p, ps){ try{ var a=p.appliedParagraphStyle; return (a===ps)||(a&&ps&&a.name===ps.name);}catch(_){ return false; } }
            function isVisuallyEmpty(p){
                var raw = "" + p.contents;            // 항상 끝에 \r 포함
                var txt = raw.replace(/\r$/,'');      // 마지막 엔터 제거
                // 앵커 제거
                txt = txt.replace(/\uFFFC/g, "");
                // 공백류 제거
                txt = txt.replace(/[\u0009\u0020\u00A0\u2000-\u200B\u202F\u205F\u3000]/g, "");
                return txt === "";
            }

            var paras = story.paragraphs.everyItem().getElements();
            for (var i=0; i<paras.length; i++){
                var p = paras[i];
                if (!psEq(p, PS_C1_ARR)) continue;
                if (isVisuallyEmpty(p)){
                    try { p.appliedParagraphStyle = PS_BASIC; } catch(_){ }
                }
            }
        })();

        // ★ 최종 안정판: C1_문장 배열 스타일인데 '엔터만 있는 문단'이면 기본 단락으로 변경 (UI와 동일 동작)
        (function(){
            var paras = story.paragraphs.everyItem().getElements();
            for (var i = 0; i < paras.length; i++) {
                var p = paras[i];

                // C1_문장 배열 스타일일 때만
                if (!(p.appliedParagraphStyle === PS_C1_ARR || 
                     (p.appliedParagraphStyle && p.appliedParagraphStyle.name === PS_C1_ARR.name))) continue;

                // 문단 내용이 정확히 엔터 하나뿐인 경우
                if (p.contents === "\r") {
                    try { p.appliedParagraphStyle = PS_BASIC; } catch(_){ }
                }
            }
        })();

        // ★ 추가: C1 블록 종료 후 다음 번호 헤더 직전까지의 빈 단락은 모두 기본 단락으로 변경
        (function(){
            function psEq(p, ps){ try{ var a=p.appliedParagraphStyle; return (a===ps)||(a&&ps&&a.name===ps.name);}catch(_){ return false; } }
            function isNextHeader(p){
                var t = (p.contents||"").replace(/\r$/,"");
                return /^\d+\.\s*p\d+-no\.\d+/i.test(t);
            }

            var paras = story.paragraphs.everyItem().getElements();
            for (var i=0; i<paras.length; i++){
                // C1 블록의 끝 찾기
                if (!psEq(paras[i], PS_C1_ARR)) continue;
                if (i+1 < paras.length && psEq(paras[i+1], PS_C1_ARR)) continue;

                var j = i + 1;
                while (j < paras.length){
                    if (isNextHeader(paras[j])) break; // 다음 번호 시작 만나면 중단

                    // 빈 단락이면 기본 단락으로 변경
                    var txt = paras[j].contents;
                    if (txt === "\r"){
                        try { paras[j].appliedParagraphStyle = PS_BASIC; } catch(_){ }
                    }
                    j++;
                }
            }
        })();


        // 10) C1 블록 마지막 문단 끝에 직접 화살표 삽입 (공백 비의존 고정 방식)
        (function(){

            function psEq(p, ps){
                try{
                    var a = p.appliedParagraphStyle;
                    return (a === ps) || (a && ps && a.name === ps.name);
                }catch(_){ return false; }
            }

            function findLabeledItem(label){
                var items = doc.allPageItems, it;
                for (var ii=0; ii<items.length; ii++){
                    it = items[ii];
                    try{ if (it.label === label) return it; }catch(_){}
                }
                return null;
            }

            var srcArrow = findLabeledItem("화살표 답지");
            if (!srcArrow) return;

            var srcWasLocked = null, srcLayerWasLocked = null;
            try { srcWasLocked = srcArrow.locked; srcArrow.locked = false; } catch(_){}
            try {
                if (srcArrow.itemLayer){
                    srcLayerWasLocked = srcArrow.itemLayer.locked;
                    srcArrow.itemLayer.locked = false;
                    srcArrow.itemLayer.visible = true;
                }
            } catch(_){}

            var paras = story.paragraphs.everyItem().getElements();

            for (var i=0; i<paras.length; i++){

                // C1 계열 스타일인지 확인
                var isC1 =
                    psEq(paras[i], PS_C1_ARR) ||
                    psEq(paras[i], PS_C1_ARR_BTM) ||
                    psEq(paras[i], PS_C1_ARR_BTM_T);

                if (!isC1) continue;

                // 다음 문단도 C1 계열이면 아직 블록 내부 → continue
                if (i+1 < paras.length){
                    var nextIsC1 =
                        psEq(paras[i+1], PS_C1_ARR) ||
                        psEq(paras[i+1], PS_C1_ARR_BTM) ||
                        psEq(paras[i+1], PS_C1_ARR_BTM_T);
                    if (nextIsC1) continue;
                }

                var lastPara = paras[i];

                // 이미 화살표가 있으면 건너뜀
                var hasArrow = false;
                try{
                    var chs = lastPara.characters;
                    for (var cc=0; cc<chs.length; cc++){
                        if (chs[cc].contents === SpecialCharacters.ANCHOR_MARKER){
                            var pi = chs[cc].pageItems[0];
                            if (pi && pi.label === "화살표 답지"){
                                hasArrow = true;
                                break;
                            }
                        }
                    }
                }catch(_){}

                if (!hasArrow){
                    try{
                        var ip = lastPara.insertionPoints[-1];
                        ip.contents = "\r\r";   // 화살표 위에 엔터 1칸 추가 (총 2줄 생성)

                        // 문단 구조 다시 계산 (삽입 후 인덱스 안정화)
                        paras = story.paragraphs.everyItem().getElements();

                        // 첫 번째 빈 줄도 기본 단락으로 변경
                        try { paras[i+1].appliedParagraphStyle = PS_BASIC; } catch(_){}

                        var newPara = paras[i+2];  // 두 번째 빈 줄에 화살표 삽입

                        var icon = srcArrow.duplicate();

                        try{
                            icon.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION;
                            icon.textWrapPreferences.textWrapMode = TextWrapModes.NONE;
                        }catch(_){}

                        icon.anchoredObjectSettings.insertAnchoredObject(newPara.insertionPoints[0], AnchorPosition.INLINE_POSITION);
                        try { newPara.appliedParagraphStyle = PS_BASIC; } catch(_){}

                        try { icon.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}

                        // 방금 생성한 공백 문단과 화살표를 건너뜀
                        i++;
                    }catch(_){}
                }
            }

            try { srcArrow.locked = (srcWasLocked===null?srcArrow.locked:srcWasLocked); } catch(_){}
            try {
                if (srcArrow.itemLayer && srcLayerWasLocked !== null)
                    srcArrow.itemLayer.locked = srcLayerWasLocked;
            } catch(_){}

        })();



        // (삭제됨) 14) 프레임 공백 정리: 선택 스토리의 텍스트프레임을 내용 높이에 맞춰 축소(FRAME_TO_CONTENT)
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP 01 자동정리");
})();