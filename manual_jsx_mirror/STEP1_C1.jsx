/**
 * STEP1C1.jsx — 선택한 스토리 전용(지정 순서 고정)
 * 0) 문자스타일 [없음], 단락스타일 [기본 단락] 재설정
 * 1) 패턴 정규화: 본문n→{본문n}, ANALYSIS→{분석}, no.01→{01}, 선행 잡텍스트 제거
 * 2) 프레임 브레이크: 두 번째 {부터 모두, 그리고 "공백≥3" 단락 앞에도 삽입
 *    + {…} 시작 단락은 [기본 단락]/[없음] 유지
 * 3) {…} 헤더 다음 블록에서 (A~Z) 시작 단락 → STEP 01/C1_문장 배열
 * 4) 공백 3개 이상 포함 단락 → STEP 01/C1_문장 배열 하단
 * 5) 4번 단락 ‘다음’ 실제 내용 단락이 (A|B|C) → STEP 01/C1_문장 배열 하단 지문
 * 6) (삭제) — (C) 이후 엔터/레이블 추가 기능 제거
 * 7) 동그라미 숫자 포함 단락 → STEP 01/C1_문장 배열 하단 지문
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

        // 4) 공백≥3 → C1_문장 배열 하단
        paras2 = story.paragraphs.everyItem().getElements();
        for (var i3=0;i3<paras2.length;i3++){
            var pt = (paras2[i3].contents||"").replace(/\r$/, "");
            if (has3PlusGaps(pt)) { try { paras2[i3].appliedParagraphStyle = PS_C1_ARR_BTM; } catch(e){} }
        }

        // 5) 하단 다음 (A|B|C) → 하단 지문
        paras2 = story.paragraphs.everyItem().getElements();
        for (var i4=0;i4<paras2.length;i4++){
            try{
                var pStyle = paras2[i4].appliedParagraphStyle;
                var isArrBtm = (pStyle === PS_C1_ARR_BTM) || (pStyle && pStyle.name === PS_C1_ARR_BTM.name);
                if (!isArrBtm) continue;
                // 다음 실내용 단락(공백-only 단락은 스킵)
                var j=i4+1; while (j<paras2.length && isOnlySpaces(paras2[j].contents)) j++;
                if (j>=paras2.length) continue;
                var nextP = paras2[j];
                var nt = (nextP.contents||"").replace(/\r$/, "");
                var m = nt.match(/^\s*\(([ABC])\)/);
                if (m){
                    var k = j;
                    while (k < paras2.length) {
                        var cand = paras2[k];
                        var ct = (cand.contents||"").replace(/\r$/, "");
                        if (/\{/.test(ct)) break;                // 헤더 오면 종료
                        var m2 = ct.match(/^\s*\(([ABC])\)/);
                        if (!m2) break;
                        cand.appliedParagraphStyle = PS_C1_ARR_BTM_T;
                        try { cand.characters.everyItem().noBreak = false; } catch(e){}
                        try { cand.clearOverrides(OverrideType.CHARACTER_ONLY); } catch(e){}
                        k++;
                    }
                }
            }catch(e){}
        }

        // 7) 동그라미 숫자 → 하단 지문
        var hits7 = grepFind(story, "[\\x{2460}-\\x{2473}\\x{2474}-\\x{247D}\\x{24EA}\\x{24F5}-\\x{24FF}\\x{2776}-\\x{2793}\\x{3251}-\\x{325F}]");
        for (var i5=0;i5<hits7.length;i5++){
            try { hits7[i5].paragraphs[0].appliedParagraphStyle = PS_C1_ARR_BTM_T; } catch(e){}
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


        // 10) 후처리: C1_문장 배열 블록 뒤에 \r\r 보장 후 **두 번째 빈 문단**에 '화살표 답지' 아이콘 인라인 삽입
        (function(){
            function findLabeledItem(label){
                var items = doc.allPageItems, it;
                for (var ii=0; ii<items.length; ii++){ it=items[ii]; try{ if (it.label === label) return it; }catch(_){ } }
                return null;
            }
            function psEq(p, ps){ try{ var a=p.appliedParagraphStyle; return (a===ps)||(a&&ps&&a.name===ps.name);}catch(_){ return false; } }

            var src = findLabeledItem("화살표 답지");
            if (!src) return; // 아이콘이 문서에 없으면 무동작

            // 소스 아이콘/레이어 잠금 상태 저장 및 해제
            var srcWasLocked = null, srcLayerWasLocked = null;
            try { srcWasLocked = src.locked; src.locked = false; } catch(_){ }
            try { if (src.itemLayer) { srcLayerWasLocked = src.itemLayer.locked; src.itemLayer.locked = false; src.itemLayer.visible = true; } } catch(_){ }

            function blanksFrom(idx, arr){
                var c=0; for (var k=idx; k<arr.length; k++){ if (""+arr[k].contents === "\r") c++; else break; } return c;
            }

            var paras = story.paragraphs.everyItem().getElements();
            for (var i=0; i<paras.length; i++){
                // C1_문장 배열 블록의 시작만 집계
                if (!psEq(paras[i], PS_C1_ARR)) continue;
                if (i>0 && psEq(paras[i-1], PS_C1_ARR)) continue;

                // 블록의 끝 찾기
                var j=i; while (j<paras.length && psEq(paras[j], PS_C1_ARR)) j++;

                // 블록 바로 뒤에 \r\r 보장(부족하면 앞에 삽입)
                var all = story.paragraphs.everyItem().getElements();
                var need = 2 - blanksFrom(j, all);
                if (need > 0){
                    // j는 블록 바로 다음 문단. 그 문단의 시작에 \r를 need 만큼 삽입하면 블록 뒤에 빈 줄이 생김
                    for (var n=0; n<need; n++){
                        try { all[j].insertionPoints[0].contents = "\r"; } catch(_){ }
                    }
                }

                // 재취득 후 타겟 빈 문단(두 번째 빈 문단) 계산
                paras = story.paragraphs.everyItem().getElements();
                var jj=i; while (jj<paras.length && psEq(paras[jj], PS_C1_ARR)) jj++;
                var targetIdx = jj + 1; // 두 번째 빈 단락
                if (targetIdx >= paras.length) { i = jj - 1; continue; }
                var targetP = paras[targetIdx];
                if (""+targetP.contents !== "\r") { i = jj - 1; continue; }

                // 위에 엔터 한 칸 추가: 이미 위가 \r가 아니면 한 번만 삽입
                try {
                    var prevIdx = targetIdx - 1;
                    var parasNow = story.paragraphs.everyItem().getElements();
                    if (prevIdx >= 0 && (""+parasNow[prevIdx].contents) !== "\r") {
                        // targetP의 시작에 \r 삽입 → targetP가 한 칸 아래로 밀림
                        targetP.insertionPoints[0].contents = "\r";
                        // 재취득: 원래 target은 한 칸 뒤로 밀렸으므로 +1
                        paras = story.paragraphs.everyItem().getElements();
                        if (targetIdx + 1 < paras.length) {
                            targetP = paras[targetIdx + 1];
                        }
                    }
                } catch(_){ }

                // 중복 방지: 이미 동일 아이콘이 있으면 스킵
                var hasIcon=false;
                try{
                    var chs = targetP.characters;
                    for (var c=0;c<chs.length;c++){
                        if (chs[c].contents === SpecialCharacters.ANCHOR_MARKER){
                            var pi = chs[c].pageItems[0];
                            if (pi && (pi.label==="화살표 답지" || pi.extractLabel("화살표 답지")!=="")) { hasIcon=true; break; }
                        }
                    }
                }catch(_){ }
                if (!hasIcon){
                    try{
                        var dup = src.duplicate();
                        try { dup.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION; } catch(_){ }
                        try { dup.textWrapPreferences.textWrapMode = TextWrapModes.NONE; } catch(_){ }
                        dup.anchoredObjectSettings.insertAnchoredObject(targetP.insertionPoints[0], AnchorPosition.INLINE_POSITION);
                        try { dup.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){ }
                    }catch(_){ }
                }

                // 다음 블록으로 점프
                i = jj - 1;
            }

            // 원상 복구
            try { src.locked = (srcWasLocked===null?src.locked:srcWasLocked); } catch(_){ }
            try { if (src.itemLayer && srcLayerWasLocked!==null) src.itemLayer.locked = srcLayerWasLocked; } catch(_){ }
        })();

        // 11) 후처리: '문장 배열 하단'과 '문장 배열 하단 지문' 사이의 빈 엔터 삭제 (다른 것은 건드리지 않음)
        (function(){
            function psEq(p, ps){ try{ var a=p.appliedParagraphStyle; return (a===ps)||(a&&ps&&a.name===ps.name);}catch(_){ return false; } }
            var paras = story.paragraphs.everyItem().getElements();
            for (var i=0; i<paras.length-1; i++){
                if (!psEq(paras[i], PS_C1_ARR_BTM)) continue; // '문장 배열 하단'만 대상
                var j = i + 1;
                var emptyIdx = [];
                // 사이에 낀 빈 단락 수집 (공백/탭/넓은공백만 → isOnlySpaces 사용)
                while (j < paras.length && isOnlySpaces(paras[j].contents)) { emptyIdx.push(j); j++; }
                if (emptyIdx.length === 0) continue;
                // 다음 실내용이 '문장 배열 하단 지문'일 때만 제거
                if (j < paras.length && psEq(paras[j], PS_C1_ARR_BTM_T)){
                    for (var k = emptyIdx.length - 1; k >= 0; k--){
                        try { paras[emptyIdx[k]].remove(); } catch(_){ try { paras[emptyIdx[k]].contents = ""; } catch(__){} }
                    }
                    // 삭제 후 참조 갱신
                    paras = story.paragraphs.everyItem().getElements();
                }
                // i는 그대로 진행 (갱신된 배열 기준)
            }
        })();
        // 12-아이콘) "아래 주어진"으로 시작하는 발문 앞에 아이콘 1개만 인라인 삽입 (다른 흐름 영향 없음)
        (function(){
            // psEq helper
            function psEq(p, ps){ try{ var a=p.appliedParagraphStyle; return (a===ps)||(a&&ps&&a.name===ps.name);}catch(_){ return false; } }

            // stricter: "아래 주어진"으로 시작하며, 반드시 하단 문제 스타일일 때만 true
            function startsWithPrompt(p){
                try {
                    if (!psEq(p, PS_C1_BOTTOM_Q)) return false; // 반드시 하단 문제 스타일일 때만
                    var t = (""+(p.contents||"")).replace(/\r$/, "");
                    return /^\s*아래\s*주어진/.test(t);
                } catch(_){ return false; }
            }

            var PROMPT_CIRC = "아래 주어진 문장이 들어갈 위치로 알맞은 곳을 고르시오.";
            var PROMPT_ORDER = "아래 주어진 문장 다음에 이어질 문장들의 적절한 순서를 쓰시오.";

            function getText(p){ try{ return (""+(p.contents||"")).replace(/\r$/, ""); }catch(_){ return ""; } }
            function hasCircledNum(t){ return /[\u2460-\u2473\u2474-\u247D\u24EA\u24F5-\u24FF\u2776-\u2793\u3251-\u325F]/.test(t); }
            function startsWithA(t){ return /^\s*\(A\)/.test(t); }

            var paras = story.paragraphs.everyItem().getElements();
            for (var i=0; i<paras.length; i++){
                var p = paras[i];
                if (!psEq(p, PS_C1_ARR_BTM_T)) continue; // 문장 배열 하단 지문만 검사

                var txt = getText(p);
                var promptToInsert = null;
                if (hasCircledNum(txt)) {
                    promptToInsert = PROMPT_CIRC; // 동그라미 숫자 유형
                } else if (startsWithA(txt)) {
                    promptToInsert = PROMPT_ORDER; // (A)로 시작하는 배열 유형
                } else {
                    continue; // 해당 없음
                }

                // 바로 위쪽에서 실제로 문장 배열 하단(PS_C1_ARR_BTM)을 찾되, 빈 단락은 건너뜀
                var j = i - 1;
                while (j >= 0 && isOnlySpaces(paras[j].contents)) j--;
                if (j < 0) continue;
                if (!psEq(paras[j], PS_C1_ARR_BTM)) continue; // 조건 불충족 시 스킵

                // 중복 방지: 하단 단락 '바로 위'가 이미 동일 발문이면 삽입하지 않음
                var insertBeforeIdx = j; // 이 단락 '위'에 넣음
                var alreadyIdx = insertBeforeIdx - 1;
                if (alreadyIdx >= 0){
                    var prevTxt = getText(paras[alreadyIdx]);
                    if (prevTxt === PROMPT_CIRC || prevTxt === PROMPT_ORDER) continue;
                }

                // 삽입 (주변 로직/배열 참조 불변, 새로 삽입된 단락에만 스타일 적용)
                try {
                    var ip0 = paras[insertBeforeIdx].insertionPoints[0];
                    ip0.contents = promptToInsert + "\r";
                    try { ip0.paragraphs[0].appliedParagraphStyle = PS_C1_BOTTOM_Q; } catch(__){}
                } catch(_){ }

                // 배열이 바뀌었으니 최신 참조 재취득
                paras = story.paragraphs.everyItem().getElements();
                // i는 지문 단락을 기준으로 유지 (변경 불필요)
            }
        })();
        // 12b) "아래 주어진" 발문 단락 맨 앞에 STEP1 문제아이콘 인라인 + 바로 뒤에 탭(\t) 1개 삽입
        (function(){
            function findLabeledItem(label){
                var items = doc.allPageItems, it;
                for (var ii=0; ii<items.length; ii++){ it=items[ii]; try{ if (it.label === label) return it; }catch(_){ } }
                return null;
            }
            function psEq(p, ps){ try{ var a=p.appliedParagraphStyle; return (a===ps)||(a&&ps&&a.name===ps.name);}catch(_){ return false; } }
            function ptxt(p){ return (p.contents||"").replace(/\r$/,''); }
            function startsWithArae(p){ return /^\s*[“”'"\uFEFF]*아래\s*주어진/.test(ptxt(p)); }
            function idxBeforeA(p){ var m=/^(\s*)[“”'"\uFEFF]*아래\s*주어진/.exec(ptxt(p)); return m?m[1].length:0; }

            var src = findLabeledItem("STEP1 문제아이콘");
            if (!src) return; // 아이콘이 문서에 없으면 무동작

            // 소스 아이콘/레이어 잠금 상태 저장 및 해제
            var srcWasLocked = null, srcLayerWasLocked = null;
            try { srcWasLocked = src.locked; src.locked = false; } catch(_){ }
            try { if (src.itemLayer) { srcLayerWasLocked = src.itemLayer.locked; src.itemLayer.locked = false; src.itemLayer.visible = true; } } catch(_){ }

            var P = story.paragraphs.everyItem().getElements();
            for (var i=0; i<P.length; i++){
                var p = P[i];
                // 반드시 하단 문제 스타일 + 텍스트가 '아래 주어진'으로 시작할 때만
                if (!psEq(p, PS_C1_BOTTOM_Q)) continue;
                if (!startsWithArae(p)) continue;
                try{
                    // 5-A 방식: 먼저 현재 문단 범위에서 GREP으로 '아'를 정확히 찾음
                    resetGrep();
                    try { app.findChangeGrepOptions = NothingEnum.NOTHING; } catch(_){ }
                    app.findGrepPreferences.findWhat = "^[\\uFEFF\\u0009\\u0020\\u00A0\\u2000-\\u200B\\u202F\\u205F\\u3000]*[“”'\"]*아(?=래\\s*주어진)";
                    var found = p.texts[0].findGrep();
                    resetGrep();

                    // GREP으로 못 잡으면 공백 길이로 보정
                    var ip = (found && found.length) ? found[0].insertionPoints[0] : p.insertionPoints[idxBeforeA(p)];

                    // 중복 방지: 해당 위치가 이미 앵커면 탭만 보장
                    try{
                        var idx = ip.index, ch = p.characters[idx];
                        if (ch && (""+ch.contents) === "\uFFFC") {
                            var after = p.characters[idx+1];
                            if (!after || (""+after.contents) !== "\t") {
                                p.insertionPoints[idx+1].contents = SpecialCharacters.TAB;
                            }
                            continue; // 아이콘은 이미 있으므로 다음 항목으로
                        }
                    }catch(_){ }

                    // 라벨 오브젝트 복제 → INLINE_POSITION으로 꽂기 (탭 추가 없음)
                    var icon = src.duplicate();
                    try{
                        icon.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION;
                        icon.textWrapPreferences.textWrapMode = TextWrapModes.NONE;
                    }catch(_){ }
                    icon.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
                    try { icon.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){ }
                    // 아이콘 뒤에 탭 1개 삽입(중복 방지)
                    try {
                        var afterIdx = ip.index + 1;
                        var afterChar = p.characters[afterIdx];
                        if (!afterChar || (""+afterChar.contents) !== "\t") {
                            p.insertionPoints[afterIdx].contents = SpecialCharacters.TAB;
                        }
                    } catch(_){ }
                    // 탭 스탑 보정: 스타일에 탭 스탑이 없으면 문단 로컬 탭스탑(약 10mm) 추가
                    try {
                        var tStops = p.tabStops; // TabStops collection
                        var hasAny = false; try { hasAny = (tStops && tStops.length > 0); } catch(__){}
                        if (!hasAny) {
                            // 10mm ≈ 28.3465pt
                            var posPt = 28.3465;
                            p.tabStops.add({ alignment: TabStopAlignment.LEFT_ALIGN, position: posPt });
                        }
                    } catch(___){ }
                }catch(_){ }
            }

            // 원상복구
            try { src.locked = (srcWasLocked===null?src.locked:srcWasLocked); } catch(_){ }
            try { if (src.itemLayer && srcLayerWasLocked!==null) src.itemLayer.locked = srcLayerWasLocked; } catch(_){ }
        })();
        // ---- 13) '아래 주어진' 앞 탭(없을 때만) + 전각공백 보정 ----
        app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat="(?<!\\t)아래\\s*주어진";
        app.changeGrepPreferences.changeTo="\t$0"; story.changeGrep();
        app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat="(?<!\\u2003)\\t(?=아래\\s*주어진)";
        app.changeGrepPreferences.changeTo="\u2003"; story.changeGrep();
        app.findGrepPreferences=app.changeGrepPreferences=NothingEnum.NOTHING;

        // 13b) 최종 단계: "본문1(p.17)" 형태가 남아 있으면 괄호 포함 삭제 (모든 로직 이후 실행)
        grepChange(story, "(\\{본문\\d+\\})\\([^\\)]*\\)", "$1");
        // 13c) 최종 단계: "{Read More}(p.14)", "{Further Reading}(p.xx)" 등 영문 헤더 뒤 괄호 삭제
        grepChange(story, "(\\{[A-Za-z][A-Za-z\\s]+\\})\\([^\\)]*\\)", "$1");
        // (삭제됨) 14) 프레임 공백 정리: 선택 스토리의 텍스트프레임을 내용 높이에 맞춰 축소(FRAME_TO_CONTENT)
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP 01 자동정리");
})();