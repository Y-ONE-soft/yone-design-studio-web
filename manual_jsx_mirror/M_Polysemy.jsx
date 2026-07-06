/* ===== InDesign ExtendScript (.jsx) =====
   선택 스토리 기준
   0) 문자스타일 [없음] / 단락스타일 [다의어] 초기화
   1) 빈 줄/공백만 있는 줄 삭제(연속 \r 정리)
   2) 영어 단어 4개 이상 포함 ‘문단’을 어휘>예문 단락스타일로 변경
   3) 특수점(만) 삭제
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
    function getCharStyleNone(){
        // 로캘 무관하게 [없음] 참조
        var candidates = ["$ID/[None]", "[None]", "$ID/[No character style]"];
        for (var i=0;i<candidates.length;i++){
            try{
                var cs = doc.characterStyles.itemByName(candidates[i]);
                if (cs && cs.isValid) return cs;
            }catch(_){}
        }
        // 실패 시 0번(기본) 반환 시도
        try{ return doc.characterStyles[0]; }catch(_){}
        return null;
    }
    function findLabeledItem(lbl){
        try{
            var all = doc.allPageItems;
            for (var i=0;i<all.length;i++){
                try{ if(all[i].label===lbl) return all[i]; }catch(_){ }
            }
        }catch(_){ }
        return null;
    }
    function resetGrep(){
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        try{ app.findChangeGrepOptions = NothingEnum.NOTHING; }catch(_){ }
        try{ app.findChangeTextOptions = NothingEnum.NOTHING; }catch(_){ }
    }

    function getCharStyle(name){
        try{ var cs = doc.characterStyles.itemByName(name); if(cs && cs.isValid) return cs; }catch(_){ }
        return null;
    }
    function escGrep(s){
        return (s+"").replace(/([\\.\\^\\$\\*\\+\\-\\?\\(\\)\\[\\]\\{\\}\\|])/g, "\\$1");
    }
    function makeVariants(base){
        var out = {};
        var b = (base+"").toLowerCase();
        if(!b) return out;
        out[b]=1;
        // irregulars (확장 가능)
        var irr = {
          "be": ["am","is","are","was","were","been","being"],
          "go": ["goes","went","gone","going"],
          "do": ["does","did","done","doing"],
          "have": ["has","had","having"],
          "grow": ["grows","grew","grown","growing"],
          "fall": ["falls","fell","fallen","falling"],
          "bite": ["bites","bit","bitten","biting"],
          "become": ["becomes","became","become","becoming"]
        };
        if(irr[b]) for(var i=0;i<irr[b].length;i++){ out[irr[b][i]] = 1; }
        // phrase special: "be with" → 각 be 변형 + " with"
        if(b === "be with"){
            var beForms = ["be","am","is","are","was","were","been","being"]; 
            for(var j=0;j<beForms.length;j++){ out[beForms[j]+" with"] = 1; }
        }
        // regular variants
        if(/^[a-z]+$/.test(b)){
            out[b+"s"]=1; // plural/3rd person
            out[b+"ed"]=1;
            out[b+"ing"]=1;
            // ES3-safe suffix checks (ExtendScript에는 endsWith가 없음)
            if(b.length>0 && b.charAt(b.length-1)=="e"){
                out[b.substring(0,b.length-1)+"ing"]=1; // make→making
                out[b+"d"]=1;                           // love→loved
            }
            if(b.length>0 && b.charAt(b.length-1)=="y"){
                out[b.substring(0,b.length-1)+"ies"]=1;  // try→tries
                out[b.substring(0,b.length-1)+"ied"]=1;  // try→tried
            }
            if(/[sxz]$/.test(b) || /(?:ch|sh)$/.test(b)){
                out[b+"es"]=1; // fix→fixes
            }
        }
        return out;
    }
    function isGoodBase(b){
        // 허용: 3자 이상 또는 핵심 동사(be/do/go/have)
        if(!b) return false;
        if(b.length >= 3) return true;
        var allowShort = {"be":1,"do":1,"go":1,"am":1,"is":1,"are":1,"was":1,"were":1,"has":1,"had":1,"have":1};
        if(allowShort[b]) return true;
        return false;
    }
    var STOPWORDS = {"a":1,"an":1,"the":1,"to":1,"of":1,"in":1,"on":1,"at":1,"by":1,"for":1,"from":1,"as":1,"or":1,"and":1,"but":1,"so":1,"if":1,"be":0};

    var wordStyle    = getParaStyle("어휘", "다의어");
    var exampleStyle = getParaStyle("어휘", "예문");
    var csNone       = getCharStyleNone();

    if (!wordStyle || !exampleStyle){
        alert("단락스타일 어휘>[다의어] 또는 어휘>[예문]을 찾을 수 없습니다."); return;
    }
    if (!csNone){
        alert("문자스타일 [없음]을 찾을 수 없습니다."); return;
    }

    app.doScript(function(){
        // 0) 문자스타일 [없음] / 단락스타일 [다의어] 초기화
        try{ story.characters.everyItem().appliedCharacterStyle = csNone; }catch(_){}
        try{ story.paragraphs.everyItem().appliedParagraphStyle = wordStyle; }catch(_){}

        // 1) 빈 줄/공백만 있는 줄 삭제 + 연속 개행 정리
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

        // (a) 공백/탭/넓은공백만 있는 줄 -> 단일 개행
        app.findGrepPreferences.findWhat = "(?m)^[ \\t\\u00A0\\u2000-\\u200B]*\\r+";
        app.changeGrepPreferences.changeTo = "\r";
        story.changeGrep();

        // (b) 연속 개행 2개 이상 -> 1개로 축소 (여러 번 나타나도 한 번에 처리)
        app.findGrepPreferences.findWhat = "\\r{2,}";
        app.changeGrepPreferences.changeTo = "\r";
        story.changeGrep();

        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

        // 2) 영어 단어 4개 이상 문단만 어휘>[예문] 적용
        var paras = story.paragraphs.everyItem().getElements();
        for (var i=0; i<paras.length; i++){
            var p = paras[i];
            try{
                var t = p.contents || "";
                // 단어 판정: 알파벳으로 시작하는 토큰(하이픈/어포스트로피 허용)
                var m = t.match(/\b[A-Za-z][A-Za-z'\-]*\b/g);
                var count = m ? m.length : 0;
                if (count >= 4){
                    p.appliedParagraphStyle = exampleStyle;
                }
                // 3) 특수점(만) 삭제 — 문단 내 전체에서 제거
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat = "";
                app.changeGrepPreferences.changeTo = "";
                p.changeGrep();
                app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;

            }catch(_){}
        }

        // [예문] 한정 — 문장 내 "첫 번째 한글" 바로 앞에만 줄바꿈(\r) 삽입 (앵커/아이콘 등 안전 처리)
        ;(function(){
            var arr = story.paragraphs.everyItem().getElements();
            for(var i=0;i<arr.length;i++){
                var p = arr[i];
                try{
                    if(p.appliedParagraphStyle != exampleStyle) continue; // 예문 단락만

                    var firstIdx = -1;
                    // 문자 단위로 안전하게 탐색 (앵커 0xFFFC 등은 건너뜀)
                    var chs = p.characters;
                    for(var c=0; c<chs.length; c++){
                        var s = String(chs[c].contents);
                        if(!s || s.length===0) continue;
                        var code = s.charCodeAt(0);
                        if(code === 0xFFFC) continue; // 앵커 마커(인라인 오브젝트)
                        if(code >= 0xAC00 && code <= 0xD7A3){ firstIdx = chs[c].index; break; }
                    }
                    if(firstIdx <= 0) continue; // 한글이 없거나 맨 앞이면 스킵

                    // 직전이 이미 줄바꿈이면 중복 삽입 금지
                    var prevStr = String(p.characters[firstIdx-1].contents);
                    if(prevStr === "\r" || prevStr === "\n") continue;

                    // 첫 번째 한글 앞에만 \r 삽입
                    p.insertionPoints[firstIdx].contents = "\r";
                }catch(_){ }
            }
        })();

        // 4) [다의어] 단락에서 "한글 뒤에 영어가 이어질" **모든 지점** 앞에 SYN 아이콘(스크립트 레이블) 인라인 삽입
        ;(function(){
            var synSrc = findLabeledItem("SYN");
            if(!synSrc) return; // 아이콘 원본이 숨겨져 있어야 동작
            var wasLocked = synSrc.locked; synSrc.locked = false;
            try{ if(synSrc.itemLayer){ synSrc.itemLayer.locked=false; synSrc.itemLayer.visible=true; } }catch(_){ }

            var HANGUL_RE = /[\uAC00-\uD7A3]/;
            var EN_RE = /[A-Za-z]/;

            var arr2 = story.paragraphs.everyItem().getElements();
            for(var k=0;k<arr2.length;k++){
                var pk = arr2[k];
                try{
                    var st = pk.appliedParagraphStyle;
                    if(st!=wordStyle) continue; // [다의어]만

                    // GREP: (한글) + 공백* + (?=영어) → 매치 끝 지점이 영어 시작 직전
                    resetGrep();
                    app.findGrepPreferences.appliedParagraphStyle = wordStyle;
                    app.findGrepPreferences.findWhat = "([가-힣])\\s*(?=[A-Za-z])";
                    var hits = pk.findGrep();
                    if(!hits || hits.length===0){ resetGrep(); continue; }

                    for(var h=0; h<hits.length; h++){
                        try{
                            var seg = hits[h];
                            var ip  = seg.insertionPoints[-1]; // 영어 시작 바로 앞
                            // 중복 방지: 동일 위치에 이미 SYN 라벨 오브젝트 존재하면 스킵
                            var hasSyn = false;
                            try{
                                var ao = ip.pageItems;
                                for(var a=0;a<ao.length;a++){ if(ao[a].label==="SYN"){ hasSyn=true; break; } }
                            }catch(_){ }
                            if(hasSyn) continue;

                            // (A) 1/4-em 공백 삽입(가능하면 특수문자, 폴백는 \u2005)
                            try{ ip.contents = SpecialCharacters.FOUR_PER_EM_SPACE; }catch(__){ try{ ip.contents = "\u2005"; }catch(___){}}
                            // (B) 동일 위치에 아이콘 인라인 삽입 → 결과: 아이콘 ▶ 1/4-em ▶ 영어
                            var icon = synSrc.duplicate();
                            try{ icon.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION); }catch(__){}
                            try{ icon.label = "SYN"; }catch(__){}
                        }catch(__){ }
                    }
                    resetGrep();

                }catch(_){ }
            }
            // 원본 상태 복구
            try{ synSrc.locked = wasLocked; }catch(_){ }
        })();

        // 5) [다의어]의 영어 단어가 [예문] 문단에 등장하면 해당 영단어(어형변화 포함)를 문자스타일 [볼드] 적용
        ;(function(){
            var boldCS = getCharStyle("볼드");
            if(!boldCS) return; // 문자스타일 [볼드]가 없으면 조용히 종료

            // 5-1. 다의어 문단에서 영단어/구 수집
            var bases = {};
            var arr = story.paragraphs.everyItem().getElements();
            for(var i=0;i<arr.length;i++){
                var p = arr[i];
                try{
                    if(p.appliedParagraphStyle!=wordStyle) continue;
                    var txt = (p.contents||"").toString();
                    // 대표 구문: "be with"가 보이면 추가로 등록
                    var mPhrase = txt.match(/\bbe\s+with\b/i);
                    if(mPhrase){ bases[mPhrase[0].toLowerCase()] = 1; }
                    // 단어 토큰 수집
                    var m = txt.match(/\b[A-Za-z][A-Za-z'\-]*\b/g);
                    if(m){
                        for(var k=0;k<m.length;k++){
                            var tok = m[k].toLowerCase();
                            if(STOPWORDS[tok]) continue;           // 관사/전치사 등 제거
                            if(!isGoodBase(tok)) continue;          // 1~2자 일반 단어 제외(핵심 동사만 허용)
                            bases[tok] = 1;
                        }
                    }
                }catch(_){ }
            }
            // 5-2. 각 base에 대해 변형 세트 구성
            var all = {};
            for(var b in bases){ var vs = makeVariants(b); for(var v in vs){ all[v]=1; } }

            // 5-3. 예문 문단에서 매칭되는 토큰에 [볼드] 적용 (대소문자 무시)
            var exParas = story.paragraphs.everyItem().getElements();
            for(var j=0;j<exParas.length;j++){
                var ep = exParas[j];
                try{
                    if(ep.appliedParagraphStyle!=exampleStyle) continue;
                    for(var key in all){
                        var pat;
                        if(key.indexOf(" ")>=0){
                            pat = "(?i)\\b" + escGrep(key) + "\\b"; // 구문 전체
                        }else{
                            pat = "(?i)\\b" + escGrep(key) + "\\b"; // 단어 경계
                        }
                        resetGrep();
                        app.findGrepPreferences.appliedParagraphStyle = exampleStyle;
                        app.findGrepPreferences.findWhat = pat;
                        app.changeGrepPreferences.appliedCharacterStyle = boldCS;
                        ep.changeGrep();
                    }
                    resetGrep();
                }catch(_){ }
            }
        })();

        // ==== [FINAL STEP] 예문 단락 한정: 문장부호 뒤 공백 + 한글 앞 -> "\r\t"로 교체 ====
        // InDesign Find/Change GREP equivalent of the dialog:
        // Find:    (?<=[\.\?\!~e\)])\s+(?=[가-힣])
        // Change:  \r\t
        (function(){
            resetGrep();
            try{ app.findChangeGrepOptions = NothingEnum.NOTHING; }catch(_){ }
            app.findGrepPreferences.appliedParagraphStyle = exampleStyle; // [어휘>예문]에만 적용
            app.findGrepPreferences.findWhat = "(?<=[\\.\\?\\!~e\\)])\\s+(?=[가-힣])";
            app.changeGrepPreferences.changeTo = "\r\t";
            story.changeGrep();
            resetGrep();
        })();
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "어휘_단어/예문_자동화");

})();