/* ===== BEGIN ===== */
// InDesign ExtendScript (.jsx)
// M_Words v1.1 — no-trim polyfill + safe GREP
// 선택 스토리 한정 / 문자스타일 [없음] / 어휘>[단어]로 지정 후 시작
// NOTE: 예문 아이콘 뒤 공백을 탭 → THIN SPACE(~<)로 변경하여 문단 탭스톱/들여쓰기와의 충돌을 원천 차단.
(function(){
  // --- safety polyfill: ExtendScript has no String.trim() on some versions ---
  if (typeof String.prototype.trim !== 'function') {
      String.prototype.trim = function(){ return (this+"").replace(/^\s+|\s+$/g, ""); };
  }
    if(app.documents.length===0){ alert("문서 없음"); return; }
    if(app.selection.length===0 || !app.selection[0].hasOwnProperty("parentStory")){
        alert("스토리를 선택하세요."); return;
    }

    var doc   = app.activeDocument;
    var story = app.selection[0].parentStory;

    // --- helpers ---
    function ps(group, name){
        try{
            var g = doc.paragraphStyleGroups.itemByName(group);
            if(g && g.isValid){
                var s = g.paragraphStyles.itemByName(name);
                if(s && s.isValid) return s;
            }
        }catch(_){}
        return null;
    }
    function cstyle(name){ try{ return doc.characterStyles.itemByName(name); }catch(_){ return null; } }
    function trimStr(s){ return String(s).trim(); }
    function getText(obj){ return ("" + obj.contents).trim(); }
    function _stripLead(s){
        return (s||"").replace(/^[\uFFFC\s\u2000-\u200B\u3000]+/, "");
    }
    function isEnglishStart(s){
        s = _stripLead(String(s).trim());
        // 앞쪽 여는 따옴표/괄호류 제거 후 첫 글자 판별
        s = s.replace(/^[\"'“”‘’\(\[\{]+/, "");
        var m = s.match(/[A-Za-z\uAC00-\uD7A3]/); // 최초 영문/한글 글자
        if(!m) return false;
        return /[A-Za-z]/.test(m[0]);
    }
    function isKoreanStart(s){
        s = _stripLead(String(s).trim());
        return (/^[가-힣"'“(]/).test(s);
    }
    // --- labeled pageItem finder (PNG/shape/group) ---
    function findLabeledItem(label){
        var items = doc.allPageItems, it;
        for (var ii=0; ii<items.length; ii++){
            it = items[ii];
            try{
                if (it.label === label) return it;
            }catch(_){}
        }
        return null;
    }
    function findTemplateByLabel(lbl){
        var items = doc.pageItems.everyItem().getElements();
        for(var i=0;i<items.length;i++){
            var it = items[i];
            try{
                var lab = "" + (it.label || "");
                if(lab && (lab == lbl || /예문/.test(lab))){
                    // PNG 아이콘: Image 자체 또는 Image의 부모 Rectangle/Group 모두 허용
                    var ctor = it.constructor && it.constructor.name;
                    if(ctor == "Image"){
                        return it.parent && it.parent.isValid ? it.parent : it;
                    }
                    if(ctor == "Rectangle" || ctor == "Polygon" || ctor == "Group" || ctor == "GraphicLine"){
                        return it;
                    }
                }
            }catch(e){}
        }
        return null;
    }

    var wordStyle    = ps("어휘","단어");
    var exampleStyle = ps("어휘","예문");
    var noneChar     = cstyle("[없음]");

    var _cntSetExample = 0, _cntSplit = 0, _cntMerge = 0, _cntIcon = 0, _cntClean = 0;

    var templateBox = findTemplateByLabel("예문");
    if(!templateBox){
        // 템플릿이 없으면 이후 4단계를 건너뛰되, 나머지는 진행
        // alert("레이블 '예문' 텍스트 박스를 문서(붙임판/붙여넣기보드)에 숨겨두세요.");
    }

    if(!wordStyle || !exampleStyle || !noneChar){
        alert("어휘 폴더의 [단어]/[예문] 단락스타일 또는 문자스타일 [없음]을 확인하세요."); return;
    }

    // 0) 초기화
    story.characters.everyItem().appliedCharacterStyle = noneChar;
    story.paragraphs.everyItem().appliedParagraphStyle = wordStyle;

    // 0.5) 본문에 남아있는 텍스트 "예문" 단독 문단은 삭제 (아이콘으로 대체)
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=arr.length-1; i>=0; i--){
            var t = getText(arr[i]);
            if(/^예문$/.test(t)){
                try{ arr[i].remove(); _cntClean++; }catch(_){}
            }
        }
    })();

    // 0.6) 공백만 있는 빈 문단 삭제 (탭/스페이스/전각공백 등)
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=arr.length-1; i>=0; i--){
            var t = ("" + arr[i].contents).replace(/[\s\u2000-\u200B\u3000]+/g, "");
            if(t === ""){
                try{ arr[i].remove(); _cntClean++; }catch(_){}
            }
        }
    })();

    // 0.7) [단어] 문단 앞의 '' 제거
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=0;i<arr.length;i++){
            var p = arr[i];
            if(p.appliedParagraphStyle == wordStyle){
                try{
                    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                    app.findGrepPreferences.findWhat = "^(\\s*)"; // 선행 공백은 보존, 글리프만 제거
                    app.changeGrepPreferences.changeTo = "$1";
                    p.texts[0].changeGrep();
                    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                }catch(_){}
            }
        }
    })();

    // 1) 영어 단어 4개 이상인 문단 -> [예문]
    var paras = story.paragraphs.everyItem().getElements();
    for(var i=0; i<paras.length; i++){
        var p   = paras[i];
        var txt = getText(p);
        // 영어 단어 토큰: 알파벳으로 시작, 내부의 아포스트로피/하이픈은 허용 (don't, take-care 등 1개로 처리)
        var words = txt.match(/\b[A-Za-z]+(?:['’\-][A-Za-z]+)*\b/g);
        if(words && words.length >= 4){
            p.appliedParagraphStyle = exampleStyle; _cntSetExample++;
        }
    }

    // 2) 문장 앞의 " " 삭제 — [예문] 문단에만 적용
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^(?:\\s*\\s*)";
    app.changeGrepPreferences.changeTo = "";
    (function(){
        var _arr2 = story.paragraphs.everyItem().getElements();
        for(var i2=0;i2<_arr2.length;i2++){
            if(_arr2[i2].appliedParagraphStyle == exampleStyle){
                _arr2[i2].texts[0].changeGrep();
            }
        }
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    })();

    // 3) 문장 앞의 탭만 삭제 — [예문] 문단에만 적용
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^\\t+";
    app.changeGrepPreferences.changeTo = "";
    (function(){
        var _arr3 = story.paragraphs.everyItem().getElements();
        for(var i3=0;i3<_arr3.length;i3++){
            if(_arr3[i3].appliedParagraphStyle == exampleStyle){
                _arr3[i3].texts[0].changeGrep();
            }
        }
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    })();

    // 3.5) 영어 예문 다음에 오는 한국어 번역 문단을 [예문]으로 지정 (현재 [단어]였던 것만)
    var pair = story.paragraphs.everyItem().getElements();
    for(var a=1; a<pair.length; a++){
        var prevP = pair[a-1], curP = pair[a];
        var prevTxt = getText(prevP), curTxt = getText(curP);
        if(prevP.appliedParagraphStyle == exampleStyle &&
           curP.appliedParagraphStyle == wordStyle &&
           isKoreanStart(curTxt)){
            curP.appliedParagraphStyle = exampleStyle;
        }
    }

    // 3.9) [예문] 문단 중 영어+한글이 한 문단에 붙어 있는 경우 → 영어 | (엔터) | 한글 로 분리
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=0;i<arr.length;i++){
            var p = arr[i];
            if(p.appliedParagraphStyle != exampleStyle) continue;
            var s = "" + p.contents;
            if(/\r/.test(s)) continue; // 이미 줄바꿈이 있으면 스킵
            // 한글 첫 글자 위치를 characters 기준으로 찾기 (앵커/공백을 보존)
            var splitIdx = -1;
            for(var ci=0; ci<p.characters.length; ci++){
                var cc = "" + p.characters[ci].contents;
                if(/[가-힣]/.test(cc)){ splitIdx = ci; break; }
            }
            if(splitIdx < 0) continue;
            // 왼쪽이 영어로 시작하는지(앵커/공백 무시) 검사
            if(!isEnglishStart(s)) continue;
            try{
                // 아이콘(~a) 보존: 내용 전체 교체 대신 분리 위치에 줄바꿈만 삽입
                p.insertionPoints[splitIdx].contents = "\r";
                // 경계 공백 정리: 줄바꿈 앞/뒤의 불필요 공백 제거
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = " +\r";
                app.changeGrepPreferences.changeTo = "\r";
                p.texts[0].changeGrep();
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "\r +";
                app.changeGrepPreferences.changeTo = "\r";
                p.texts[0].changeGrep();
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                _cntSplit++;
            }catch(e){}
        }
    })();

    // 4) [예문] 영어 문장 "시작 인덱스"(첫 영문자) 바로 앞에 PNG 아이콘(레이블 '예문') 인라인 + 뒤 THIN SPACE 1개
    (function(){
        // 문장 시작 인덱스(첫 영문자) 계산: 선행 앵커/공백/여는 따옴표·괄호는 스킵
        function sentenceStartIndex(p){
            var len = p.characters.length;
            for(var ci=0; ci<len; ci++){
                var ch = "" + p.characters[ci].contents;
                if(ch === "\uFFFC") continue; // anchor skip
                if(/[\t \u00A0\u2000-\u200B\u202F\u2060\u3000\uFEFF]/.test(ch)) continue; // spaces
                if(/["'“”‘’\(\[\{]/.test(ch)) continue; // opening quotes/brackets
                // 첫 영문자 위치 반환
                if(/[A-Za-z]/.test(ch)) return ci;
                // 영문이 아니면 그대로 종료 (상위 isEnglishStart가 거를 것)
                break;
            }
            return 0;
        }

        var src = findLabeledItem("예문");
        if(!src) return;
        var wasLocked = src.locked; src.locked = false;
        try{ if(src.itemLayer){ src.itemLayer.locked=false; src.itemLayer.visible=true; } }catch(_){ }

        var arr = story.paragraphs.everyItem().getElements();
        for (var i3=0; i3<arr.length; i3++){
            var p = arr[i3];
            if(p.appliedParagraphStyle != exampleStyle) continue;
            var t = getText(p);

            // 잘못 붙은 기존 선두 앵커가 있고, 영문 시작이 아니면 선두 앵커+뒤 탭만 제거
            try{
                var ch0 = "";
                if(p.characters.length>0){ ch0 = ""+p.characters[0].contents; }
                if(ch0 === "\uFFFC" && !isEnglishStart(t)){
                    try{ p.characters[0].remove(); }catch(_){ }
                    try{ if(p.characters.length && (""+p.characters[0].contents)==="\t"){ p.characters[0].remove(); } }catch(_){ }
                    continue; // 이 문단은 스킵
                }
            }catch(_){ }

            // 아이콘 대상 필터: 영문으로 시작 + 문장부호(., ?, !) 포함 + 품사라인 제외
            if(!isEnglishStart(t)) continue;
            if(!/[\.\?\!]/.test(t)) continue;
            if(/^\s*[A-Za-z][A-Za-z'\-]*\s+(v|n|a|adj|adv|prep|conj|pron|int)\./i.test(t)) continue;

            // 선두 정리: **문단 맨앞의** 앵커(~a)/탭/공백만 삭제(중간 앵커 보존)
            try{
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "^(?:~a|[\t \u2000-\u200B\u3000])+";
                app.changeGrepPreferences.changeTo = "";
                p.texts[0].changeGrep();
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            }catch(_){ }

            // 실제 문장 시작 인덱스 계산 (문단 전체가 아니라 첫 줄 기준)
            var idx = 0; // fallback
            try{ idx = sentenceStartIndex(p); }catch(_){ idx = 0; }

            // 첫 줄 객체에서 보이는 첫 영문자의 위치를 우선 적용
            var ip = null;
            try{
                var l0 = p.lines[0];
                var foundOnLine = false;
                for(var jj=0; jj<l0.characters.length; jj++){
                    var cj = ""+l0.characters[jj].contents;
                    if(cj === "\uFFFC") continue; // 기존 앵커 무시
                    if(/[\t \u00A0\u2000-\u200B\u202F\u2060\u3000\uFEFF]/.test(cj)) continue; // 공백류 무시
                    if(/["'“”‘’\(\[\{]/.test(cj)) continue; // 여는 기호 무시
                    if(/[A-Za-z]/.test(cj)){
                        ip = l0.characters[jj].insertionPoints[0];
                        foundOnLine = true;
                        break;
                    }
                    break; // 첫 비공백·비앵커가 영문이 아닐 경우 탈출
                }
                if(!foundOnLine){ ip = p.insertionPoints[idx]; }
            }catch(_){ ip = p.insertionPoints[idx]; }

            // 문장 시작 앞쪽(첫 줄 범위)에 존재하는 앵커 제거 (시각적 앞부분만 정리)
            try{
                var l0 = p.lines[0];
                var upto = l0.characters.length;
                for(var k=0; k<upto; k++){
                    var ck = ""+l0.characters[k].contents;
                    if(ck === "\uFFFC"){ l0.characters[k].remove(); k--; upto--; }
                }
            }catch(_){ }

            // 아이콘 삽입: 문장 첫 영문자 앞에 인라인
            try{
                var icon = src.duplicate();
                if(icon.constructor && icon.constructor.name == "Image" && icon.parent && icon.parent.isValid){ icon = icon.parent; }
                try{
                    icon.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION;
                    icon.textWrapPreferences.textWrapMode = TextWrapModes.NONE;
                }catch(_){ }
                icon.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
                try{ icon.fit(FitOptions.FRAME_TO_CONTENT); }catch(_){ }
                _cntIcon++;

                // 아이콘 직후 얇은 고정폭 공백(THIN SPACE) 1개 강제 — 탭 사용 금지
                try{
                    var afterIP = ip.index + 1;
                    var afterChar = "";
                    if(p.characters.length > afterIP){ afterChar = ""+p.characters[afterIP].contents; }
                    if(afterChar !== SpecialCharacters.THIN_SPACE){ p.insertionPoints[afterIP].contents = SpecialCharacters.THIN_SPACE; }
                    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                    app.findGrepPreferences.findWhat = "(^|\r)~a[\t\u2009\u200A\u2006\u2007\u2008\u2002\u2003\u2004\u2005 ]+";
                    app.changeGrepPreferences.changeTo = "~a~<";
                    p.texts[0].changeGrep();
                    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                }catch(_){ }

                // 앵커 앞 공백 제거(앵커 보존)
                try{
                    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                    app.findGrepPreferences.findWhat = "^ +(~a)";
                    app.changeGrepPreferences.changeTo = "$1";
                    p.texts[0].changeGrep();
                    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                }catch(_){ }
            }catch(_){ }
        }
        src.locked = wasLocked;
    })();

    // 5~6) [예문] 영어 문단 뒤에 오는 (빈 문단 건너뛴) 한글 [예문]을
    //      영어 문단 끝으로 '엔터 + 한글' 형태로 합치기
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=0; i<arr.length; i++){
            var p = arr[i];
            if(p.appliedParagraphStyle != exampleStyle) continue;
            var pt = getText(p);
            if(!isEnglishStart(pt)) continue; // 영어 예문만 기준
            // look ahead
            var j = i + 1;
            while(j < arr.length){
                var cand = arr[j];
                var ct = getText(cand);
                // 공백 문단이면 제거하고 계속 스킵
                if(ct === ""){
                    try{ cand.remove(); _cntClean++; }catch(_){}
                    j++; continue;
                }
                // [예문] & 한글 시작이면 결합
                if(cand.appliedParagraphStyle == exampleStyle && isKoreanStart(ct)){
                    try{
                        // 영어 문단 끝 공백 제거
                        p.characters[-1].contents = ("" + p.characters[-1].contents).replace(/\s+$/,"");
                    }catch(_){}
                    try{
                        var ip = p.insertionPoints[p.insertionPoints.length-1];
                        // 이미 끝이 줄바꿈이면 탭만
                        var lastChar = ("" + p.characters[-1].contents);
                        if(/\r$/.test(lastChar)){ ip.contents = ct; }
                        else { ip.contents = "\r" + ct; }
                        cand.remove(); _cntMerge++;
                    }catch(_){}
                    break;
                }else{
                    // 다른 내용(다른 스타일/다른 언어)이면 중단
                    break;
                }
            }
        }
        // [예문] 문단 앞의 모든 공백 삭제 — (예문 문단 한정, 스토리 전역 금지)
        try{
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = "^[\t \u2000-\u200B\u3000]+";
            app.changeGrepPreferences.changeTo = "";
            var _ex = story.paragraphs.everyItem().getElements();
            for(var k=0; k<_ex.length; k++){
                var pk = _ex[k];
                if(pk.appliedParagraphStyle == exampleStyle){
                    pk.texts[0].changeGrep();
                }
            }
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        }catch(_){ }
    })();

    // 6) 모든 문단 시작부 공백 정리 (아이콘/단어 앞 공백 전부 삭제)
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=0;i<arr.length;i++){
            var p = arr[i];
            try{
                // (a) 앵커(~a) 바로 앞의 시작 공백 제거
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "^[\t \u2000-\u200B\u3000]+(?=~a)";
                app.changeGrepPreferences.changeTo = "";
                p.texts[0].changeGrep();
                // (b) 일반 시작 공백 제거 (단어/숫자/기호 앞)
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "^[\t \u2000-\u200B\u3000]+";
                app.changeGrepPreferences.changeTo = "";
                p.texts[0].changeGrep();
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            }catch(_){ }
        }
    })();

    // 6.z) [예문] 문단: 문장부호(., ?, !) 뒤에 한글이 바로 오면 줄바꿈 삽입
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=0;i<arr.length;i++){
            var p = arr[i];
            if(p.appliedParagraphStyle != exampleStyle) continue;
            try{
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                // 마침표/물음표/느낌표 뒤 공백들을 줄바꿈으로, 단 뒤 문자가 한글일 때만
                app.findGrepPreferences.findWhat = "([\\.\\?\\!])\\s*(?=[\uAC00-\uD7A3])";
                app.changeGrepPreferences.changeTo = "$1\\r";
                p.texts[0].changeGrep();
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            }catch(_){ }
        }
    })();

    // 6.aa) [예문] 문단: 한글로 시작하는 줄 맨 앞에 탭 1개 강제 (아이콘/영문 라인 불변)
    (function(){
        var arr = story.paragraphs.everyItem().getElements();
        for(var i=0;i<arr.length;i++){
            var p = arr[i];
            if(p.appliedParagraphStyle != exampleStyle) continue;
            try{
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                // 1) 문단 첫머리에서 한글 시작 → 탭 1개 강제
                app.findGrepPreferences.findWhat = "^[\t \u2000-\u200B\u3000]*(?=[\uAC00-\uD7A3])";
                app.changeGrepPreferences.changeTo = "\t";
                p.texts[0].changeGrep();

                // 2) 줄바꿈(\r) 직후 한글 시작 → \r 뒤에 탭 1개 강제
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "\r[\t \u2000-\u200B\u3000]*(?=[\uAC00-\uD7A3])";
                app.changeGrepPreferences.changeTo = "\r\t";
                p.texts[0].changeGrep();

                // 3) 보강: 탭이 2개 이상인 경우 1개로 축약 (문단 시작/줄바꿈 직후만)
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "(^|\r)\t{2,}";
                app.changeGrepPreferences.changeTo = "$1\t";
                p.texts[0].changeGrep();

                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            }catch(_){ }
        }
    })();

    // 6.ac) [단어] 표제어가 바로 아래 [예문] 영어줄에 있을 경우, 그 단어만 문자스타일 [볼드] 적용
    //  - 기존 스크립트에는 전혀 영향 없이, 마지막 후처리로만 동작
    (function(){
        // 문서에 존재하는 [볼드] 문자스타일을 유연하게 탐색
        function pickBold(){
            var names = ["[볼드]","볼드","Bold","bold"]; // 우선순위
            for(var i=0;i<names.length;i++){
                try{ var cs = doc.characterStyles.itemByName(names[i]); if(cs && cs.isValid) return cs; }catch(_){ }
            }
            return null;
        }
        var boldCS = pickBold();
        if(!boldCS){ return; } // 문자스타일이 없으면 조용히 종료
        function escGREP(s){ return (s+"").replace(/[\\\^\$\.|?*+()\[\]{}]/g, "\\$&"); }

        // 마지막 토큰의 활용형(단/복수·시제·진행형)까지 허용하는 패턴 생성
        function buildVariantPattern(word){
            var w = (word+"").toLowerCase();
            var irregular = {
                "be":["am","is","are","was","were","been","being"],
                "have":["has","had","having"],
                "do":["does","did","done","doing"],
                "go":["goes","went","gone","going"],
                "come":["came","come","coming"],
                "run":["ran","run","running"],
                "make":["made","making"],
                "take":["took","taken","taking"],
                "give":["gave","given","giving"],
                "get":["got","gotten","getting"],
                "see":["saw","seen","seeing"],
                "write":["wrote","written","writing"],
                "speak":["spoke","spoken","speaking"],
                "eat":["ate","eaten","eating"],
                "fall":["fell","fallen","falling"],
                "find":["found","finding"],
                "think":["thought","thinking"],
                "buy":["bought","buying"],
                "teach":["taught","teaching"],
                "catch":["caught","catching"],
                "feel":["felt","feeling"],
                "keep":["kept","keeping"],
                "leave":["left","leaving"],
                "pay":["paid","paying"],
                "build":["built","building"],
                "send":["sent","sending"],
                "meet":["met","meeting"],
                "say":["said","saying"],
                "tell":["told","telling"],
                "sell":["sold","selling"],
                "bring":["brought","bringing"],
                "read":["read","reading"]
            };
            var forms = [w];
            if(irregular[w]){ forms = forms.concat(irregular[w]); }
            // 규칙 변화 추가
            var vowels = /[aeiou]$/;
            // -y → -ies/-ied
            if(/[^aeiou]y$/.test(w)){
                forms.push(w.slice(0,-1)+"ies");
                forms.push(w.slice(0,-1)+"ied");
            }
            // -e로 끝나면 e-drop ing, +d
            if(/e$/.test(w)){
                forms.push(w+"d");
                forms.push(w.slice(0,-1)+"ing");
            }else{
                forms.push(w+"ed");
                forms.push(w+"ing");
            }
            // 3인칭 단수
            if(/(s|x|z|ch|sh|o)$/.test(w)) forms.push(w+"es"); else forms.push(w+"s");
            // 중복 제거
            var hash = {}; var uniq = [];
            for(var i=0;i<forms.length;i++){ var f=forms[i]; if(!hash[f]){ hash[f]=1; uniq.push(f);} }
            for(var j=0;j<uniq.length;j++){ uniq[j] = escGREP(uniq[j]); }
            return "(?:"+uniq.join("|")+")";
        }

        var paras = story.paragraphs.everyItem().getElements();
        for(var i=0;i<paras.length;i++){
            var p = paras[i];
            if(p.appliedParagraphStyle != wordStyle) continue; // [단어] 라인만 기준
            // 표제어 구(첫 영어 덩어리 전체: in a hurry, clean up 등)
            var m = (""+p.contents).match(/^[\s\u2000-\u200B\u3000]*([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*)*)/);
            if(!m) continue;
            var key = m[1];
            if(!key || key.length===0) continue;

            // 아래로 내려가며 첫 번째 [예문] 문단만 대상
            var j=i+1;
            while(j<paras.length){
                var q = paras[j];
                if(q.appliedParagraphStyle == exampleStyle){
                    try{
                        // 예문 영어 줄(줄바꿈 전까지만) 범위 제한
                        var txt = ""+q.contents; var br = txt.indexOf("\r");
                        var target = q.texts[0];
                        if(br >= 0){ target = q.characters.itemByRange(0, Math.max(0,br-1)); }
                        // key가 여러 단어일 수 있음 (e.g., "in a hurry"). 마지막 단어만 활용형 허용
                        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                        var parts = (key+"").trim().split(/\s+/);
                        var first = parts.shift();
                        var rest  = parts.length ? "\\s+" + escGREP(parts.join(" ")) : "";
                        var head  = "\\b" + buildVariantPattern(first);
                        var pattern = "(?i)" + head + rest + "\\b";
                        app.findGrepPreferences.findWhat = pattern;
                        app.changeGrepPreferences.appliedCharacterStyle = boldCS;
                        target.changeGrep();
                        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                    }catch(_){ }
                    break; // 첫 [예문]만 처리
                }else if(q.appliedParagraphStyle == wordStyle){
                    break; // 다음 [단어] 나오면 중단
                }else{
                    j++;
                }
            }
        }
    })();

    // === POST-ONLY A2. [단어]→[예문] 볼드: 단어줄 앞의 불릿( 등)·앵커(~a) 무시하고 표제어 구 추출 ===
    (function(){
        // 1) 문자스타일 [볼드] 탐색 (없으면 종료)
        function pickBold(){
            var names = ["[볼드]","볼드","Bold","bold"]; for(var i=0;i<names.length;i++){ try{ var cs=doc.characterStyles.itemByName(names[i]); if(cs&&cs.isValid) return cs; }catch(_){ } } return null;
        }
        var boldCS = pickBold(); if(!boldCS) return;
        // 2) 유틸
        function esc(s){ return (s+"").replace(/[\\\^\$\.|?*+()\[\]{}]/g, "\\$&"); }
        function buildVariant(w){
            var w0=(w+"").toLowerCase();
            var irr={"be":["am","is","are","was","were","been","being"],"have":["has","had","having"],"do":["does","did","done","doing"],"go":["goes","went","gone","going"],"come":["came","come","coming"],"run":["ran","run","running"],"make":["made","making"],"take":["took","taken","taking"],"give":["gave","given","giving"],"get":["got","gotten","getting"],"see":["saw","seen","seeing"],"write":["wrote","written","writing"],"speak":["spoke","spoken","speaking"],"eat":["ate","eaten","eating"],"fall":["fell","fallen","falling"],"find":["found","finding"],"think":["thought","thinking"],"buy":["bought","buying"],"teach":["taught","teaching"],"catch":["caught","catching"],"feel":["felt","feeling"],"keep":["kept","keeping"],"leave":["left","leaving"],"pay":["paid","paying"],"build":["built","building"],"send":["sent","sending"],"meet":["met","meeting"],"say":["said","saying"],"tell":["told","telling"],"sell":["sold","selling"],"bring":["brought","bringing"],"read":["read","reading"]};
            var f=[w0]; if(irr[w0]) f=f.concat(irr[w0]);
            if(/[^aeiou]y$/.test(w0)){ f.push(w0.slice(0,-1)+"ies", w0.slice(0,-1)+"ied"); }
            if(/e$/.test(w0)){ f.push(w0+"d", w0.slice(0,-1)+"ing"); } else { f.push(w0+"ed", w0+"ing"); }
            if(/(s|x|z|ch|sh|o)$/.test(w0)) f.push(w0+"es"); else f.push(w0+"s");
            var h={},out=[]; for(var i=0;i<f.length;i++){ if(!h[f[i]]){h[f[i]]=1; out.push(f[i]);} }
            for(var j=0;j<out.length;j++){ out[j]=esc(out[j]); }
            return "(?:"+out.join("|")+")";
        }
        // 3) 처리
        var paras = story.paragraphs.everyItem().getElements();
        var BUL = "\uF0A1\u2022\u00B7\u2219"; //  • · ‧ 등
        for(var i=0;i<paras.length;i++){
            var p = paras[i];
            if(p.appliedParagraphStyle != ps("어휘","단어")) continue;
            // (a) 표제어 구 추출: 선행 공백/앵커(~a)/불릿( 등) 무시 후 영어 구 전체
            var src = ""+p.contents;
            // 표제어는 첫 영어 단어 하나만 (품사표기 v./n./a. 등은 제외)
            var m = src.match(new RegExp("^[\\s\\u00A0\\u2000-\\u200B\\u202F\\u2060\\u3000\\uFEFF]*(?:~a)?["+BUL+"]?\\s*([A-Za-z][A-Za-z'\\-]*)"));
            if(!m) continue; var key = m[1]; if(!key) continue;
            // (b) 아래 첫 [예문]만 대상으로, 영어줄(\r 전까지)에서 구 전체 볼드
            var j=i+1; while(j<paras.length){
                var q=paras[j]; if(q.appliedParagraphStyle==ps("어휘","예문")){
                    var txt = ""+q.contents; var br = txt.indexOf("\r"); var tgt=q.texts[0]; if(br>=0){ tgt=q.characters.itemByRange(0,Math.max(0,br-1)); }
                    var parts = key.trim().split(/\s+/); var first=parts.shift();
                    var restPat=""; for(var ti=0;ti<parts.length;ti++){ var tk=esc(parts[ti]).replace(/['’‘ʼ＇]/g,"['’‘ʼ＇]"); restPat+="[\\s\\u00A0\\u2000-\\u200B\\u202F\\u2060\\u3000\\uFEFF]+"+tk; }
                    var head = "\\b"+buildVariant(first); var patt = "(?i)"+head+restPat+"(?![A-Za-z])";
                    var jsPat=patt.replace(/^\(\?i\)/,""); var re=new RegExp(jsPat,"i"); var line=""+tgt.contents; var hit=re.exec(line);
                    if(hit&&hit[0]){ var sidx=hit.index, elen=hit[0].length; try{ tgt.characters.itemByRange(sidx,sidx+elen-1).appliedCharacterStyle = boldCS; }catch(__){} }
                    break;
                }else if(q.appliedParagraphStyle==ps("어휘","단어")){ break; } else { j++; }
            }
        }
    })();

    // 마무리
    app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    alert("완료\\n예문지정:"+_cntSetExample+" / 분리:"+_cntSplit+" / 결합:"+_cntMerge+" / 아이콘:"+_cntIcon+" / 정리:"+_cntClean);

    // === FINAL GREP: Ensure a space after ~a if not present ===
    try {
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "(?<=~a)(?! )";
        app.changeGrepPreferences.changeTo = " ";
        story.changeGrep();
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    } catch(_){}
    
})();
/* =====  END  ===== */