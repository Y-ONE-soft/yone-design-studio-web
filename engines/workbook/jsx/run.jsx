// 워크북 조판 자동화 — run.jsx  [ENGINE TEMPLATE — DO NOT COPY FROM JOBS FOLDER]
// content.json -> InDesign 스타일 적용 통합 엔진
// ExtendScript ES3 호환 (var only, no arrow functions, no template literals)
#target indesign

(function() {

    // ========================================================================
    // 1. SETTINGS & DATA LOAD
    // ========================================================================
    var settingsPath = "__SETTINGS_PATH__";

    var sf = new File(settingsPath);
    sf.encoding = 'UTF-8'; sf.open('r');
    var settings = eval("(" + sf.read() + ")");
    sf.close();

    var jsonPath  = settings.json_path;
    var outputDir = settings.output_dir;
    var inddPath  = settings.indd_path;
    var grade     = settings.grade || 1;
    var year      = settings.year  || 25;
    var month     = settings.month || 10;
    var workbookType = settings.workbook_type || "";  // "교과서" or ""
    var tbSubject   = settings.subject   || "";
    var tbPublisher = settings.publisher || "";
    var tbLesson    = settings.lesson    || "";

    // 사용자가 UI에서 체크한 제외 섹션 (예: ["step1_b2", "step2_a1", "step2_a1_btm"])
    var excludeSet = {};
    if (settings.exclude && settings.exclude.length) {
        for (var ex = 0; ex < settings.exclude.length; ex++) {
            excludeSet[settings.exclude[ex]] = true;
        }
    }

    // content_meta.json (lightweight) + lazy-load per step
    function loadJSON(path) {
        var f = new File(path);
        f.encoding = 'UTF-8'; f.open('r');
        var obj = eval("(" + f.read() + ")");
        f.close();
        return obj;
    }

    // Try meta file first (split mode), fallback to monolithic content.json
    var data = null;
    var metaPath = outputDir + "/content_meta.json";
    var metaFile = new File(metaPath);
    if (metaFile.exists) {
        data = loadJSON(metaPath);
        data._splitMode = true;
    } else {
        data = loadJSON(jsonPath);
        data._splitMode = false;
    }

    if (!data) {
        alert("content.json 로드 실패");
        return;
    }

    // Alias map: steps that share the same source data
    var dataAliases = {
        // step2_a1_btm은 이제 별도 파일(객관식)을 사용
    };
    function loadStepData(stepKey) {
        var key = dataAliases[stepKey] || stepKey;
        if (data._splitMode && data.step_files && data.step_files[key]) {
            return loadJSON(data.step_files[key]);
        }
        if (data.steps && data.steps[key]) {
            return data.steps[key];
        }
        return null;
    }

    // ========================================================================
    // 2. OPEN INDESIGN FILE (같은 이름 문서는 저장 후 새로 열기)
    // ========================================================================
    var workFile = new File(inddPath);
    var doc = null;

    // 같은 이름의 문서가 열려 있으면 별도 경로에 저장 후 닫기
    for (var di = app.documents.length - 1; di >= 0; di--) {
        try {
            if (app.documents[di].name === workFile.name) {
                // 현재 InDesign 메모리 내용을 백업 경로에 저장
                var now = new Date();
                var ts = ("0" + (now.getMonth()+1)).slice(-2) + ("0" + now.getDate()).slice(-2)
                       + "_" + ("0" + now.getHours()).slice(-2) + ("0" + now.getMinutes()).slice(-2);
                var origName = app.documents[di].name.replace(/\.indd$/i, "");
                var backupFile = new File(workFile.parent + "/" + origName + "_" + ts + ".indd");
                app.documents[di].save(backupFile);
                app.documents[di].close(SaveOptions.NO);
            }
        } catch(e) {}
    }

    // 디스크에서 새로 열기 (항상 원본 템플릿 사용)
    doc = app.open(workFile);
    $.sleep(3000);
    if (!doc || !doc.isValid) {
        try { doc = app.activeDocument; } catch(_) {}
    }
    if (!doc || !doc.isValid) {
        alert("InDesign 파일을 열 수 없습니다: " + inddPath);
        return;
    }
    app.activeDocument = doc;
    app.scriptPreferences.enableRedraw = false;

    // ========================================================================
    // 3. LOG SYSTEM
    // ========================================================================
    var log = [];
    var stepsDone = 0;
    var overflowCount = 0;
    var startTime = new Date();

    function addLog(msg) {
        var line = "[" + new Date().toLocaleTimeString() + "] " + msg;
        log.push(line);
        // Also write to debug file for real-time monitoring
        try {
            var dbgF = new File("/tmp/workbook_debug.txt");
            dbgF.open("a"); dbgF.encoding = "UTF-8";
            dbgF.writeln(line);
            dbgF.close();
        } catch(_){}
    }
    addLog("워크북 조판 시작: 고" + grade + " " + year + "년 " + month + "월");

    // ========================================================================
    // 4. STYLE HELPERS
    // ========================================================================
    function getBasicPara() {
        try { var s = doc.paragraphStyles.itemByName("$ID/NormalParagraphStyle"); if (s && s.isValid) return s; } catch(_){}
        try { var s2 = doc.paragraphStyles.itemByName("[기본 단락]"); if (s2 && s2.isValid) return s2; } catch(_){}
        try { var s3 = doc.paragraphStyles.itemByName("[Basic Paragraph]"); if (s3 && s3.isValid) return s3; } catch(_){}
        return doc.paragraphStyles[0];
    }
    function ps(groupName, styleName) {
        try {
            var g = doc.paragraphStyleGroups.itemByName(groupName);
            if (g && g.isValid) {
                var s = g.paragraphStyles.itemByName(styleName);
                if (s && s.isValid) return s;
            }
        } catch(_){}
        return null;
    }
    function cs(name) {
        try { var s = doc.characterStyles.itemByName(name); if (s && s.isValid) return s; } catch(_){}
        return null;
    }
    function csNone() {
        try { return doc.characterStyles[0]; } catch(_) { return null; }
    }

    var BASIC_PARA = getBasicPara();
    var CS_NONE    = csNone();

    // STEP 01 styles
    var S1_A1         = ps("STEP 01", "A1_어휘 선택");
    var S1_A_NUM      = ps("STEP 01", "A_어휘 선택 번호");
    var S1_A2_BOX     = ps("STEP 01", "A2_본문 박스");
    var S1_A2_OX      = ps("STEP 01", "A2_OX문제");
    var S1_B1_BOX     = ps("STEP 01", "B1_본문 박스");
    var S1_B1         = ps("STEP 01", "B1_내용 정리");
    var S1_B1_SUBJ    = ps("STEP 01", "B1_내용 정리 주제");
    var S1_B1_TITLE   = ps("STEP 01", "B1_내용 정리 제목");
    var S1_B2_NUM     = ps("STEP 01", "B2_내용 종합 번호");
    var S1_B2_CHOICE  = ps("STEP 01", "B2_내용 종합 선지");
    var S1_C1         = ps("STEP 01", "C1_문장 배열");
    var S1_C1_BTM     = ps("STEP 01", "C1_문장 배열 하단");
    var S1_C1_BTM_T   = ps("STEP 01", "C1_문장 배열 하단 지문");
    var S1_C2         = ps("STEP 01", "C2_빈칸 어휘");
    var S1_C2_KOR     = ps("STEP 01", "C2_빈칸 어휘 한글");
    var S1_HADAN      = ps("STEP 01", "하단 문제");
    var S1_HADAN_JIM  = ps("STEP 01", "하단 문제_지문");
    var S1_HADAN_SEO  = ps("STEP 01", "하단 문제_선지");

    // STEP 02 styles
    var S2_A1         = ps("STEP 02", "A1_어법 선택");
    var S2_A1_BTM     = ps("STEP 02", "A1_어법 선택 하단");
    var S2_B1         = ps("STEP 02", "B1_어법 OX");
    var S2_C1         = ps("STEP 02", "C1_빈칸 어법");
    var S2_C2_NUM     = ps("STEP 02", "C2_영작 배열 번호");
    var S2_C2_VIEW    = ps("STEP 02", "C2_영작 배열 보기");

    // STEP 03 styles
    var S3_DEFAULT    = ps("STEP 03", "실전 문제 지문 올림포스_");
    var S3_NUM        = ps("STEP 03", "S_실전문제 번호 수정 올림포스");
    var S3_CHOICE     = ps("STEP 03", "S_선지 올림포스");
    var S3_INTRO      = ps("STEP 03", "다음 글을 읽고");
    var S3_WORD       = ps("STEP 03", "영단어");
    var S3_BG         = ps("STEP 03", "배경 올림포스");
    var S3_COND       = ps("STEP 03", "조건 올림포스");
    var S3_VIEW       = ps("STEP 03", "보기 올림포스");

    // Character styles
    var CS_UNDERLINE  = cs("문제_밑줄") || cs("밑줄");
    var CS_PASSAGE_UL = cs("지문 밑줄");

    // ========================================================================
    // 5. UTILITY FUNCTIONS
    // ========================================================================
    function parasOf(story) { return story.paragraphs.everyItem().getElements(); }
    function ptxt(p) { return (p.contents || "").replace(/\r$/, ""); }
    function isBracketPara(p) {
        var t = ptxt(p);
        if (!/^\s*\[[^\]]+\]\s*$/.test(t)) return false;
        // 공백만 있는 bracket은 제외: [   ] → false
        var inner = t.replace(/^\s*\[/, "").replace(/\]\s*$/, "");
        return inner.replace(/\s/g, "").length > 0;
    }
    function isEmptyPara(p) { return /^\s*$/.test(ptxt(p)); }
    function isBlankPara(p) {
        var t = (p.contents || "").replace(/[\s\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\r\n\t]+/g, "");
        return t === "";
    }
    function isEnglishPara(p) { return /[A-Za-z]/.test(ptxt(p)); }
    function hasCircled(p) { return /[\u2460-\u2473\u24F5-\u24FF\u2776-\u277F]/.test(ptxt(p)); }
    function hasKorean2(txt) { return /[\uAC00-\uD7A3][\s\S]*[\uAC00-\uD7A3]/.test(txt); }
    function startsWithDaeum(p) { return /^(\s*[""'"']*)다음/.test(ptxt(p)); }
    function has3PlusGaps(str) {
        if (!str) return false;
        var run = 0, c;
        for (var i = 0; i < str.length; i++) {
            c = str.charCodeAt(i);
            if (c === 0x20 || c === 0x09 || c === 0x00A0 || (c >= 0x2000 && c <= 0x200B) || c === 0x202F || c === 0x205F || c === 0x3000) {
                if (++run >= 3) return true;
            } else { run = 0; }
        }
        return false;
    }

    function resetGrep() {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
    }
    function resetText() {
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
    }
    function grepChange(scope, findWhat, changeTo) {
        resetGrep();
        app.findGrepPreferences.findWhat = findWhat;
        app.changeGrepPreferences.changeTo = changeTo;
        scope.changeGrep();
        resetGrep();
    }
    function grepFind(scope, findWhat) {
        resetGrep();
        app.findGrepPreferences.findWhat = findWhat;
        var r = scope.findGrep();
        resetGrep();
        return r;
    }

    function findLabeledItem(label) {
        var items = doc.allPageItems;
        for (var i = 0; i < items.length; i++) {
            try { if (items[i].label === label) return items[i]; } catch(_){}
        }
        return null;
    }

    // Header patterns for STEP detection
    // Safe patterns split into multiple simple regexes to avoid ExtendScript ReDoS.
    // Pre-step: strip "N." prefix and remove all whitespace, then test compact form.
    var headerPatterns = [
        /^L\d+[-\u2013\u2014]\uBCF8\uBB38\d+(?:\([^\)]{0,40}\))?$/,
        /^L\d+[-\u2013\u2014][A-Za-z]{1,30}(?:\([^\)]{0,40}\))?$/,
        /^L\d+[-\u2013\u2014]p\.?\d+(?:~\d+)?(?:[A-Za-z]{1,20})?$/i,
        /^p\d+[-\u2013\u2014\.]?(?:no\.)?\d+(?:~\d+)?(?:\([^\)]{0,40}\))?$/i,
        /^p\d+[-\u2013\u2014]?Example\d*$/i,
        /^p\d+[-\u2013\u2014]?Example\d+$/i,
        /^p\d+[-\u2013\u2014][A-Za-z]{1,15}\.?\d+(?:~\d+)?$/i,
        /^p\d+[-\u2013\u2014](?:\uC11C\uC220\uD615|\uB17C\uC220\uD615)Practice$/i,
        /^p\d+[-\u2013\u2014]+\uC218\uB2A5\uB300\uBE44ANALYSIS$/i
    ];
    var reSupp = /^Supplementary Reading$/i;

    function normHeader(s) {
        return (s || "").replace(/\uFEFF/g, "").replace(/[\u00A0\u2000-\u200B\u202F\u205F\u3000]/g, " ").replace(/[ \t]+/g, " ").replace(/^\s+|\s+$/g, "");
    }
    function _matchAnyHeader(s) {
        for (var pi = 0; pi < headerPatterns.length; pi++) {
            if (headerPatterns[pi].test(s)) return true;
        }
        return false;
    }
    function isHeaderLine(txt) {
        var hn = normHeader(txt);
        if (hn.length > 60) return false;
        if (reSupp.test(hn)) return true;
        var body = hn.replace(/^\d+\s*[.)]?\s*/, "");
        if (body.length === 0 || body.length > 50) return false;
        var compact = body.replace(/\s+/g, "");
        return _matchAnyHeader(compact);
    }

    // ========================================================================
    // 6. STORY FINDER — find story by marker text in section label frames
    // ========================================================================
    function findStoryByMarker(markerText, masterPrefix) {
        // Search through all stories looking for section label text
        var allStories = doc.stories.everyItem().getElements();
        for (var si = 0; si < allStories.length; si++) {
            var story = allStories[si];
            try {
                var txt = story.contents || "";
                if (txt.indexOf(markerText) !== -1) {
                    // If masterPrefix specified, verify story is on correct master pages
                    if (masterPrefix) {
                        var containers = story.textContainers;
                        if (containers.length > 0) {
                            var page = containers[0].parentPage;
                            if (page) {
                                var master = page.appliedMaster;
                                if (master && master.namePrefix === masterPrefix) {
                                    return story;
                                }
                            }
                        }
                    }
                    return story;
                }
            } catch(_){}
        }
        return null;
    }

    // Find story by checking the FIRST text frame on pages with a given master
    function findMainStoryOnMaster(masterPrefix) {
        var candidates = [];
        var seen = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            var master = page.appliedMaster;
            if (!master || master.namePrefix !== masterPrefix) continue;
            var tfs = page.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var story = tfs[t].parentStory;
                if (seen[story.id]) continue;
                seen[story.id] = true;
                // Pick the story with the most text containers (main content story)
                candidates.push({ story: story, frames: story.textContainers.length });
            }
        }
        // Return story with the most frames
        candidates.sort(function(a, b) { return b.frames - a.frames; });
        return candidates.length > 0 ? candidates[0].story : null;
    }

    // ========================================================================
    // 7. CONTENT INSERTION — write paragraphs to story
    // ========================================================================
    function insertContent(story, paragraphs, ulStyle) {
        if (!story || !story.isValid || !paragraphs || paragraphs.length === 0) return;

        // Build full text
        var fullText = '';
        for (var i = 0; i < paragraphs.length; i++) {
            fullText += paragraphs[i].text;
            if (i < paragraphs.length - 1) fullText += '\r';
        }
        story.contents = fullText;

        // Reset character styles
        // char style reset skipped (story.contents already clean)

        // Apply underline runs (use provided style or default CS_UNDERLINE)
        var ulCharStyle = ulStyle || CS_UNDERLINE;
        if (ulCharStyle) {
            var paras = story.paragraphs;
            var charPos = 0;
            for (var pi = 0; pi < paragraphs.length && pi < paras.length; pi++) {
                var runs = paragraphs[pi].runs;
                if (runs) {
                    var pos = 0;
                    for (var ri = 0; ri < runs.length; ri++) {
                        var run = runs[ri];
                        var rLen = run.t ? run.t.length : 0;
                        if (rLen === 0) continue;
                        if (run.ul) {
                            try {
                                paras[pi].characters.itemByRange(pos, pos + rLen - 1).appliedCharacterStyle = ulCharStyle;
                            } catch(e) {}
                        }
                        pos += rLen;
                    }
                }
                charPos += (paragraphs[pi].text || "").length + 1;
            }
        }
    }

    // ========================================================================
    // 8. INLINE OBJECT INSERTION
    // ========================================================================
    function unlockItem(item) {
        var state = { itemLocked: false, layerLocked: false };
        try { state.itemLocked = item.locked; item.locked = false; } catch(_){}
        try {
            if (item.itemLayer) {
                state.layerLocked = item.itemLayer.locked;
                item.itemLayer.locked = false;
                item.itemLayer.visible = true;
            }
        } catch(_){}
        return state;
    }
    function relockItem(item, state) {
        try { item.locked = state.itemLocked; } catch(_){}
        try { if (item.itemLayer && state.layerLocked !== undefined) item.itemLayer.locked = state.layerLocked; } catch(_){}
    }

    function insertInlineIcon(src, insertionPoint) {
        if (!src) return null;
        try {
            var clone = src.duplicate();
            try { clone.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION; } catch(_){}
            try { clone.textWrapPreferences.textWrapMode = TextWrapModes.NONE; } catch(_){}
            clone.anchoredObjectSettings.insertAnchoredObject(insertionPoint, AnchorPosition.INLINE_POSITION);
            try { clone.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}
            return clone;
        } catch(e) { return null; }
    }

    // ========================================================================
    // 9. FRAME BREAK HELPERS
    // ========================================================================
    function insertFrameBreaksAtBrackets(story) {
        // Insert frame break before each [XX] paragraph (except the first)
        // Collect bracket indices
        var paras = parasOf(story);
        var bracketIdx = [];
        for (var i = 0; i < paras.length; i++) {
            if (isBracketPara(paras[i])) bracketIdx.push(i);
        }
        // Reverse order for index stability
        for (var k = bracketIdx.length - 1; k >= 1; k--) {
            paras = parasOf(story);
            // Re-collect bracket indices
            bracketIdx = [];
            for (var ii = 0; ii < paras.length; ii++) {
                if (isBracketPara(paras[ii])) bracketIdx.push(ii);
            }
            if (k >= bracketIdx.length) continue;
            var bi = bracketIdx[k];
            // Remove blank paragraphs immediately above (max 5 to avoid infinite loop)
            var safetyLimit = 5;
            while (bi > 0 && safetyLimit > 0 && isEmptyPara(paras[bi - 1])) {
                safetyLimit--;
                var removed = false;
                try { paras[bi - 1].remove(); removed = true; } catch(_){}
                if (!removed) break;
                paras = parasOf(story);
                bracketIdx = [];
                for (var jj = 0; jj < paras.length; jj++) {
                    if (isBracketPara(paras[jj])) bracketIdx.push(jj);
                }
                if (k >= bracketIdx.length) break;
                bi = bracketIdx[k];
            }
            if (k < bracketIdx.length) {
                try { paras[bracketIdx[k]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(_){}
            }
        }
    }

    function insertHeaderBreaks(story) {
        // 헤더 패턴이 있는 단락을 찾아 frame break 삽입 후 헤더 자체를 제거.
        // 알고리즘 — 두 패스:
        //   1) 사전 패스: 헤더 후보 단락 인덱스만 수집 (길이/정규식으로 빠르게 거름)
        //   2) 처리 패스: 인덱스 역순으로 각 헤더 처리 (인덱스 안정성 보장)
        var _hbStart = (new Date()).getTime();
        var paras = story.paragraphs.everyItem().getElements();
        try { addLog("insertHeaderBreaks: 진입 paras.length=" + paras.length); } catch(_){}

        // 1) 헤더 인덱스 수집
        var headerIdx = [];
        for (var i = 0; i < paras.length; i++) {
            var t = "";
            try { t = paras[i].contents || ""; } catch(_){ continue; }
            if (t.length > 80) continue;  // 헤더는 짧음
            if (isHeaderLine(t)) headerIdx.push(i);
        }
        try { addLog("insertHeaderBreaks: 헤더 " + headerIdx.length + "개 발견 elapsed=" + ((new Date()).getTime() - _hbStart) + "ms"); } catch(_){}

        if (headerIdx.length === 0) {
            try { addLog("insertHeaderBreaks: 완료 (헤더 없음) elapsed=" + ((new Date()).getTime() - _hbStart) + "ms"); } catch(_){}
            return;
        }

        // 2) 역순 처리. 각 헤더 단락 객체를 직접 가지고 처리 → 인덱스 변동 무관.
        for (var hi = headerIdx.length - 1; hi >= 0; hi--) {
            var hIdx = headerIdx[hi];
            if (hIdx >= paras.length) continue;
            var header = paras[hIdx];

            // 헤더 위의 가장 가까운 non-blank 단락 찾기 (초기 paras 기준)
            var top = hIdx - 1;
            while (top >= 0 && isBlankPara(paras[top])) top--;

            if (top >= 0) {
                // frame break 삽입
                try {
                    var topPara = paras[top];
                    if (topPara.isValid && topPara.characters.length > 0) {
                        var ipBeforeCR = topPara.insertionPoints[-2];
                        var lastChar = topPara.characters.length > 1 ? topPara.characters[-2] : null;
                        var hasBreak = false;
                        try { hasBreak = (lastChar && lastChar.contents === SpecialCharacters.FRAME_BREAK); } catch(_){}
                        if (!hasBreak) ipBeforeCR.contents = SpecialCharacters.FRAME_BREAK;
                    }
                } catch(_){}

                // top과 header 사이 blank 단락 제거
                for (var k = top + 1; k < hIdx; k++) {
                    try {
                        if (paras[k].isValid && isBlankPara(paras[k])) {
                            paras[k].contents = "";  // 내용만 비움 (.remove() silent-fail 회피)
                        }
                    } catch(_){}
                }
            }

            // 헤더 단락의 내용 비움 (paragraph 객체는 유지)
            try {
                if (header.isValid) header.contents = "";
            } catch(_){}
        }

        // 3) 정리: 빈 단락 일괄 제거 (GREP — 안정적, 무한 루프 없음)
        try {
            grepChange(story, "^\\s*\\r", "");      // 빈 라인 제거
            grepChange(story, "\\r{2,}", "\\r");    // 연속 줄바꿈 정리
        } catch(_){}

        try { addLog("insertHeaderBreaks: 완료 elapsed=" + ((new Date()).getTime() - _hbStart) + "ms"); } catch(_){}
    }

    // ========================================================================
    // 10. OVERFLOW CHECK — add pages/frames if story overflows
    // ========================================================================
    function ensureNoOverflow(story) {
        var containers = story.textContainers;
        if (containers.length === 0) return;
        var lastFrame = containers[containers.length - 1];
        var safeCount = 0;

        while (lastFrame.overflows && safeCount < 10) {
            var lastPage = lastFrame.parentPage;
            if (!lastPage) break;
            var masterPage = lastPage.appliedMaster;
            var bounds = lastFrame.geometricBounds;

            var newPage = doc.pages.add(LocationOptions.AFTER, lastPage);
            if (masterPage) { try { newPage.appliedMaster = masterPage; } catch(_){} }

            var newTF = newPage.textFrames.add();
            newTF.geometricBounds = bounds;
            lastFrame.nextTextFrame = newTF;
            lastFrame = newTF;
            safeCount++;
            overflowCount++;
        }
    }

    // 프레임 간 내용 넘침 방지 (모든 STEP 공통)
    // frame.overflows는 마지막 프레임에서만 작동하므로,
    // 각 프레임의 내용이 프레임 영역을 초과하는지 직접 확인
    function shrinkOverflowFrames(story) {
        try { story.recompose(); } catch(_){}
        var containers = story.textContainers;
        if (containers.length < 2) return;

        // 각 프레임별로 확인: 프레임에 속한 텍스트의 마지막 baseline이 프레임 하단을 넘는지
        for (var fi = 0; fi < containers.length; fi++) {
            var frame = containers[fi];
            try {
                var fp = frame.paragraphs;
                if (fp.length === 0) continue;

                // 프레임 하단 좌표
                var gb = frame.geometricBounds; // [top, left, bottom, right]
                var frameBottom = gb[2];

                // 마지막 단락의 마지막 줄 baseline 확인
                var lastPara = fp[fp.length - 1];
                var lastLine = lastPara.lines[lastPara.lines.length - 1];
                if (!lastLine) continue;
                var lastBaseline = lastLine.baseline;

                // baseline이 프레임 하단 - 2pt 이하면 OK, 넘으면 축소 필요
                if (lastBaseline <= frameBottom - 2) continue;

                // Auto leading → 실제 수치 변환
                for (var pi0 = 0; pi0 < fp.length; pi0++) {
                    try {
                        var ld0 = fp[pi0].leading;
                        if (typeof ld0 !== 'number' || ld0 > 1000) {
                            var fs = fp[pi0].pointSize || 10;
                            fp[pi0].leading = fs * 1.2;
                        }
                    } catch(_){}
                }
                try { story.recompose(); } catch(_){}

                // 행간 단계적 축소
                for (var ld = 0; ld < 12; ld++) {
                    fp = frame.paragraphs;
                    lastPara = fp[fp.length - 1];
                    try {
                        lastLine = lastPara.lines[lastPara.lines.length - 1];
                        if (lastLine.baseline <= frameBottom - 2) break;
                    } catch(_){ break; }

                    for (var pi = 0; pi < fp.length; pi++) {
                        try {
                            var cur = fp[pi].leading;
                            if (typeof cur === 'number' && cur > 6.5) {
                                fp[pi].leading = cur - 0.3;
                            }
                        } catch(_){}
                    }
                    try { story.recompose(); } catch(_){}
                }

                // 여전히 넘치면 프레임 높이 확장
                try {
                    fp = frame.paragraphs;
                    lastPara = fp[fp.length - 1];
                    lastLine = lastPara.lines[lastPara.lines.length - 1];
                    if (lastLine.baseline > frameBottom - 2) {
                        frame.geometricBounds = [gb[0], gb[1], gb[2] + 15, gb[3]];
                        story.recompose();
                    }
                } catch(_){}
            } catch(_){}
        }

        // 내용 넘침 감지: 프레임 간 같은 단락이 split되면 → 행간 축소 또는 프레임 확장
        try { story.recompose(); } catch(_){}
        containers = story.textContainers;
        for (var fi2 = 0; fi2 < containers.length - 1; fi2++) {
            var curF = containers[fi2];
            var nextF = containers[fi2 + 1];
            try {
                var curParas = curF.paragraphs;
                var nextParas = nextF.paragraphs;
                if (curParas.length === 0 || nextParas.length === 0) continue;

                // 다음 프레임의 첫 단락이 현재 프레임의 마지막 단락과 같으면 → split 발생
                var curLast = curParas[curParas.length - 1];
                var nextFirst2 = nextParas[0];
                var isSplit = false;
                try { isSplit = (curLast.index === nextFirst2.index); } catch(_){}
                // 또는: 다음 프레임 첫 문자가 프레임브레이크가 아닌데 내용이 있으면
                if (!isSplit) {
                    var nfContent = ("" + nextFirst2.contents);
                    // 프레임브레이크 문자가 아닌 일반 텍스트로 시작하면
                    if (nfContent.length > 0 && nfContent.charCodeAt(0) !== 0xFFFB) {
                        // 현재 프레임의 마지막 단락과 다음 프레임의 첫 단락 내용이 같으면
                        var curLastTxt = ("" + curLast.contents).substring(0, 30);
                        var nextFirstTxt = nfContent.substring(0, 30);
                        if (curLastTxt === nextFirstTxt) isSplit = true;
                    }
                }

                if (isSplit) {
                    // 1차: 행간 축소
                    for (var pi3 = 0; pi3 < curParas.length; pi3++) {
                        try {
                            var ld3 = curParas[pi3].leading;
                            if (typeof ld3 !== 'number' || ld3 > 1000) {
                                curParas[pi3].leading = (curParas[pi3].pointSize || 10) * 1.2;
                            }
                        } catch(_){}
                    }
                    try { story.recompose(); } catch(_){}
                    for (var shrk = 0; shrk < 15; shrk++) {
                        curParas = curF.paragraphs;
                        nextParas = nextF.paragraphs;
                        var stillSplit = false;
                        try { stillSplit = (curParas[curParas.length-1].index === nextParas[0].index); } catch(_){}
                        if (!stillSplit) break;
                        for (var pi4 = 0; pi4 < curParas.length; pi4++) {
                            try {
                                var ld4 = curParas[pi4].leading;
                                if (typeof ld4 === 'number' && ld4 > 5) curParas[pi4].leading = ld4 - 0.3;
                            } catch(_){}
                        }
                        try { story.recompose(); } catch(_){}
                    }
                    // 2차: 여전히 split이면 프레임 확장
                    curParas = curF.paragraphs;
                    nextParas = nextF.paragraphs;
                    try {
                        if (curParas[curParas.length-1].index === nextParas[0].index) {
                            var curGB2 = curF.geometricBounds;
                            curF.geometricBounds = [curGB2[0], curGB2[1], curGB2[2] + 30, curGB2[3]];
                            try { story.recompose(); } catch(_){}
                        }
                    } catch(_){}
                }
            } catch(_){}
        }

        // 최종: 마지막 프레임 오버플로우 체크
        var lastF = containers[containers.length - 1];
        if (lastF.overflows) {
            try {
                var gbL = lastF.geometricBounds;
                lastF.geometricBounds = [gbL[0], gbL[1], gbL[2] + 15, gbL[3]];
                story.recompose();
            } catch(_){}
        }
    }

    // ========================================================================
    // 11. MASTER PAGE HELPERS
    // ========================================================================
    function getMaster(prefix) {
        for (var i = 0; i < doc.masterSpreads.length; i++) {
            if (doc.masterSpreads[i].namePrefix === prefix) return doc.masterSpreads[i];
        }
        return null;
    }

    var MASTER_A = getMaster("A");  // STEP01
    var MASTER_B = getMaster("B");  // STEP01 B1
    var MASTER_C = getMaster("C");  // STEP02
    var MASTER_O = getMaster("O");  // STEP03
    var MASTER_M = getMaster("M");  // 메모

    // ========================================================================
    // 12. STEP-SPECIFIC PROCESSORS
    // ========================================================================

    // ---- STEP 1 A1: 어휘 선택 ----
    function processStep1A1(story, paragraphs) {
        addLog("STEP1 A1 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Apply basic paragraph to all
            try { story.paragraphs.everyItem().appliedParagraphStyle = BASIC_PARA; } catch(_){}
            // char style reset skipped (story.contents already clean)

            // Replace special brackets
            resetText();
            app.findTextPreferences.findWhat = "\u276E";
            app.changeTextPreferences.changeTo = "[";
            story.changeText();
            app.findTextPreferences.findWhat = "\u276F";
            app.changeTextPreferences.changeTo = "]";
            story.changeText();
            resetText();

            // Clean double returns
            grepChange(story, "\\r{2,}", "\\r");

            // Remove "2. 어휘2단계_Hard" paragraphs
            var paras = parasOf(story);
            for (var d = paras.length - 1; d >= 0; d--) {
                if (/^\s*2\.\s*\uC5B4\uD718\s*2\uB2E8\uACC4_Hard\s*$/.test(ptxt(paras[d]))) {
                    try { paras[d].remove(); } catch(_){}
                }
            }

            // Insert frame breaks at bracket paragraphs
            insertFrameBreaksAtBrackets(story);

            // Apply A1_어휘 선택 to paragraph after each bracket
            if (S1_A1) {
                var paras2 = parasOf(story);
                for (var j = 0; j < paras2.length; j++) {
                    if (isBracketPara(paras2[j]) && j + 1 < paras2.length) {
                        try { paras2[j + 1].appliedParagraphStyle = S1_A1; } catch(_){}
                    }
                }
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP1A1");

        addLog("STEP1 A1 완료");
        stepsDone++;
    }

    // ---- STEP 1 A2: 본문 O/X ----
    function processStep1A2(story, paragraphs) {
        addLog("STEP1 A2 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Apply basic paragraph
            try { story.paragraphs.everyItem().appliedParagraphStyle = BASIC_PARA; } catch(_){}
            // char style reset skipped (story.contents already clean)

            // Bracket index collection
            var paras = parasOf(story);
            var bracketIdx = [];
            for (var i = 0; i < paras.length; i++) {
                if (isBracketPara(paras[i])) bracketIdx.push(i);
            }

            // Apply A2_본문 박스 to first English paragraph after bracket (skip blanks)
            if (S1_A2_BOX) {
                for (var k = 0; k < bracketIdx.length; k++) {
                    paras = parasOf(story);
                    bracketIdx = [];
                    for (var t = 0; t < paras.length; t++) {
                        if (isBracketPara(paras[t])) bracketIdx.push(t);
                    }
                    var bi = bracketIdx[k];
                    var tIdx = bi + 1;
                    while (tIdx < paras.length && isBlankPara(paras[tIdx])) tIdx++;
                    if (tIdx < paras.length && isEnglishPara(paras[tIdx])) {
                        try { paras[tIdx].appliedParagraphStyle = S1_A2_BOX; } catch(_){}
                    }
                }
            }

            // Frame breaks at brackets (skip first)
            insertFrameBreaksAtBrackets(story);

            // TF button insertion for ❮ T / F ❯
            var tfSource = findLabeledItem("TF \uBC84\uD2BC");
            if (tfSource) {
                var tfState = unlockItem(tfSource);
                resetGrep();
                app.findGrepPreferences.findWhat = "\\x{276E}\\s*T\\s*/\\s*F\\s*\\x{276F}";
                var hits = story.findGrep();
                resetGrep();

                // Fallback text search
                if (hits.length === 0) {
                    resetText();
                    app.findTextPreferences.findWhat = "\u276E T / F \u276F";
                    hits = story.findText();
                    resetText();
                }

                for (var h = hits.length - 1; h >= 0; h--) {
                    var range = hits[h];
                    if (S1_A2_OX) {
                        try { range.insertionPoints[0].paragraphs[0].appliedParagraphStyle = S1_A2_OX; } catch(_){}
                    }
                    try {
                        var ip = range.insertionPoints[0];
                        var clone = tfSource.duplicate();
                        clone.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
                        try { clone.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}
                        range.remove();
                    } catch(_){}
                }
                relockItem(tfSource, tfState);
            } else {
                // No TF source — just remove tokens and apply OX style
                resetGrep();
                app.findGrepPreferences.findWhat = "\\x{276E}\\s*T\\s*/\\s*F\\s*\\x{276F}";
                var hits2 = story.findGrep();
                for (var h2 = hits2.length - 1; h2 >= 0; h2--) {
                    if (S1_A2_OX) { try { hits2[h2].insertionPoints[0].paragraphs[0].appliedParagraphStyle = S1_A2_OX; } catch(_){} }
                    try { hits2[h2].remove(); } catch(_){}
                }
                resetGrep();
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP1A2");

        addLog("STEP1 A2 완료");
        stepsDone++;
    }

    // ---- STEP 1 B1: 본문 정리 ----
    function processStep1B1(story, paragraphs) {
        addLog("STEP1 B1 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Apply B1_내용 정리 to all + character [없음]
            if (S1_B1) { try { story.paragraphs.everyItem().appliedParagraphStyle = S1_B1; } catch(_){} }
            /* char style reset skipped */

            // Clean {주제}/{제목} text
            grepChange(story, "\\{\\s*\uC8FC\uC81C\\s*\\}", "\uC8FC\uC81C");
            grepChange(story, "\\{\\s*\uC81C\uBAA9\\s*\\}", "\uC81C\uBAA9");
            grepChange(story, "^(\uC8FC\uC81C|\uC81C\uBAA9)\\s*\\r+", "$1 ");

            // Collect bracket indices and "다음" indices
            var P = parasOf(story);
            var bracketIdx = [];
            for (var k = 0; k < P.length; k++) {
                if (isBracketPara(P[k])) bracketIdx.push(k);
            }

            // Insert frame breaks (reverse order) at brackets (2nd+) and "다음" paragraphs
            var targets = [];
            for (var b = 1; b < bracketIdx.length; b++) targets.push({ idx: bracketIdx[b], type: "br" });
            for (var d = 0; d < P.length; d++) {
                if (startsWithDaeum(P[d])) targets.push({ idx: d, type: "daum" });
            }
            targets.sort(function(a, b) { return b.idx - a.idx; });
            for (var t = 0; t < targets.length; t++) {
                P = parasOf(story);
                var pi = targets[t].idx;
                if (pi < 0 || pi >= P.length) continue;
                try { P[pi].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(_){}
            }

            // 하단문제 선지(원문자) 위에 빈 줄 보장 (hwp 파싱에서 빈줄 누락 대비)
            P = parasOf(story);
            for (var bl = P.length - 1; bl > 0; bl--) {
                if (!hasCircled(P[bl]) || startsWithDaeum(P[bl])) continue;
                // 이전 단락이 빈 줄이 아니고 선지도 아니면 → 빈 줄 삽입
                var prevTxt = ptxt(P[bl - 1]).replace(/[\r\n]/g, '');
                if (prevTxt !== '' && !hasCircled(P[bl - 1])) {
                    try { P[bl].insertionPoints[0].contents = '\r'; } catch(_){}
                }
            }

            // Apply styles: circled numbers → 선지, "다음" → 하단 문제, English after "다음" → 하단 문제_지문
            if (S1_HADAN_SEO) {
                P = parasOf(story);
                for (var s = 0; s < P.length; s++) {
                    if (!startsWithDaeum(P[s]) && hasCircled(P[s])) {
                        try { P[s].appliedParagraphStyle = S1_HADAN_SEO; } catch(_){}
                    }
                }
            }
            if (S1_HADAN) {
                P = parasOf(story);
                for (var h = 0; h < P.length; h++) {
                    if (startsWithDaeum(P[h])) { try { P[h].appliedParagraphStyle = S1_HADAN; } catch(_){} }
                }
            }
            if (S1_HADAN_JIM) {
                P = parasOf(story);
                for (var m = 0; m < P.length - 1; m++) {
                    if (startsWithDaeum(P[m]) && isEnglishPara(P[m + 1])) {
                        try { P[m + 1].appliedParagraphStyle = S1_HADAN_JIM; } catch(_){}
                    }
                }
            }
            if (S1_B1_BOX) {
                P = parasOf(story);
                for (var j = 0; j < P.length - 1; j++) {
                    if (isBracketPara(P[j])) { try { P[j + 1].appliedParagraphStyle = S1_B1_BOX; } catch(_){} }
                }
            }

            // Icon insertion for "다음" paragraphs — 프레임브레이크 뒤에 아이콘+탭 삽입
            var iconSrc = findLabeledItem("STEP1 \uBB38\uC81C\uC544\uC774\uCF58");
            if (iconSrc) {
                var iconState = unlockItem(iconSrc);
                P = parasOf(story);
                for (var i3 = 0; i3 < P.length; i3++) {
                    if (!startsWithDaeum(P[i3])) continue;
                    try {
                        // 프레임브레이크 찾기
                        resetGrep();
                        app.findGrepPreferences.findWhat = "~R";
                        var fbFound = P[i3].texts[0].findGrep();
                        resetGrep();
                        var ip;
                        if (fbFound && fbFound.length > 0) {
                            ip = fbFound[0].insertionPoints[-1]; // 프레임브레이크 직후
                        } else {
                            ip = P[i3].insertionPoints[0]; // 단락 시작
                        }
                        // 이미 아이콘 있으면 건너뛰기
                        try {
                            var chk = P[i3].characters[ip.index - P[i3].insertionPoints[0].index];
                            if (chk && ("" + chk.contents) === "\uFFFC") continue;
                        } catch(_){}
                        insertInlineIcon(iconSrc, ip);
                        // 아이콘 직후에 탭 삽입
                        P = parasOf(story);
                        try {
                            // 아이콘(\uFFFC) 바로 다음 위치에 탭
                            var chars3 = P[i3].characters;
                            for (var ci3 = 0; ci3 < chars3.length; ci3++) {
                                if (("" + chars3[ci3].contents) === "\uFFFC") {
                                    P[i3].insertionPoints[ci3 + 1].contents = "\t";
                                    break;
                                }
                            }
                        } catch(_){}
                    } catch(_){}
                }
                relockItem(iconSrc, iconState);
            }

            // {주제} / {제목} style application
            P = parasOf(story);
            for (var a2 = 0; a2 < P.length; a2++) {
                var s3 = ptxt(P[a2]);
                if (/^\s*\{?\s*\uC8FC\uC81C\s*\}?(\s|$)/.test(s3)) {
                    grepChange(P[a2], "^(\\s*)\\{?\\s*\uC8FC\uC81C\\s*\\}?\\s*", "{\uC8FC\uC81C} ");
                    if (S1_B1_SUBJ) { try { P[a2].appliedParagraphStyle = S1_B1_SUBJ; } catch(_){} }
                }
                if (/^\s*\{?\s*\uC81C\uBAA9\s*\}?(\s|$)/.test(s3)) {
                    grepChange(P[a2], "^(\\s*)\\{?\\s*\uC81C\uBAA9\\s*\\}?\\s*", "{\uC81C\uBAA9} ");
                    if (S1_B1_TITLE) { try { P[a2].appliedParagraphStyle = S1_B1_TITLE; } catch(_){} }
                }
            }

            // 주제↔제목 사이 빈줄 보장 (스타일 기준, 역순 처리)
            P = parasOf(story);
            for (var zb = P.length - 1; zb >= 1; zb--) {
                var curSty = P[zb].appliedParagraphStyle;
                var prevSty = P[zb - 1].appliedParagraphStyle;
                var isCurTitle = (curSty === S1_B1_TITLE || (curSty && S1_B1_TITLE && curSty.name === S1_B1_TITLE.name));
                var isPrevSubj = false;
                // 이전 단락이 주제 스타일이거나, 주제 스타일 블록의 내용인지
                if (prevSty === S1_B1_SUBJ || (prevSty && S1_B1_SUBJ && prevSty.name === S1_B1_SUBJ.name)) isPrevSubj = true;
                // 제목 단락 앞에 빈줄이 없으면 삽입
                if (isCurTitle) {
                    var prevTxt = ptxt(P[zb - 1]).replace(/[\r\n]/g, '');
                    if (prevTxt !== '') {
                        try { P[zb].insertionPoints[0].contents = '\r'; } catch(_){}
                        P = parasOf(story);
                    }
                }
            }

            // Final: bracket paragraphs → [기본 단락]
            P = parasOf(story);
            for (var z = 0; z < P.length; z++) {
                var zs = (P[z].contents || "").replace(/\r$/, "").replace(/[\uFFFC\uFEFF]/g, "").replace(/^[\s\u00A0\u2000-\u200B]+/, "");
                if (/^[\[\uFF3B]/.test(zs)) {
                    try { P[z].appliedParagraphStyle = BASIC_PARA; } catch(_){}
                }
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP1B1");

        addLog("STEP1 B1 완료");
        stepsDone++;
    }

    // ---- STEP 1 B2: 내용 종합 ----
    function processStep1B2(story, paragraphs) {
        addLog("STEP1 B2 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Reset all to basic paragraph
            try { story.paragraphs.everyItem().appliedParagraphStyle = BASIC_PARA; } catch(_){}

            // Frame breaks at '[' (skip first)
            resetGrep();
            app.findGrepPreferences.findWhat = "\\[";
            var opens = story.findGrep();
            for (var i = opens.length - 1; i >= 1; i--) {
                var idx = opens[i].index;
                if (idx > 0) {
                    try { story.characters[idx].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(_){}
                }
            }
            resetGrep();

            // Apply A2_본문 박스 to paragraphs after ']' closing
            var paras = story.paragraphs;
            var reNumStart = /^\s*\((\d+)\)/;
            var reCircled = /^(?:\s*[\u2460-\u2473])/;

            for (var pIdx = 0; pIdx < paras.length; pIdx++) {
                var p = paras[pIdx];
                var t = p.contents || "";
                if (t.indexOf("[") === -1) continue;

                var closeIdx = pIdx;
                for (var s = pIdx; s < paras.length; s++) {
                    var qt = paras[s].contents || "";
                    if (qt.indexOf("]") !== -1) { closeIdx = s; break; }
                    if (s > pIdx && qt.indexOf("[") !== -1) break;
                }

                var start = closeIdx + 1;
                while (start < paras.length) {
                    var st = (paras[start].contents || "").replace(/[\s\u00A0\r\n]+/g, "");
                    if (st === "") { start++; } else { break; }
                }

                var z = start;
                for (; z < paras.length; z++) {
                    var rt = paras[z].contents || "";
                    if (rt.indexOf("[") !== -1) break;
                    if (reNumStart.test(rt) || reCircled.test(rt)) break;
                    if (S1_A2_BOX) { try { paras[z].appliedParagraphStyle = S1_A2_BOX; } catch(_){} }
                }
                pIdx = z - 1;
            }

            // B2 번호/(숫자) style
            paras = story.paragraphs;
            for (var j = 0; j < paras.length; j++) {
                var txt = paras[j].contents || "";
                if (reNumStart.test(txt)) {
                    if (S1_B2_NUM) paras[j].appliedParagraphStyle = S1_B2_NUM;
                }
            }

            // Circled numbers → B2 선지
            for (var m = 0; m < paras.length; m++) {
                var t2 = paras[m].contents || "";
                if (reCircled.test(t2)) {
                    if (S1_B2_CHOICE) paras[m].appliedParagraphStyle = S1_B2_CHOICE;
                }
            }

            // Clean trailing returns
            grepChange(story, "\\r{2,}\\s*$", "\\r");
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP1B2");

        addLog("STEP1 B2 완료");
        stepsDone++;
    }

    // ---- STEP 1 C1: 문장 배열 ----
    function processStep1C1(story, paragraphs) {
        addLog("STEP1 C1 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // 공백만 있는 bracket 단락 제거: [     ] → 삭제
            var parasClean0 = parasOf(story);
            for (var pc0 = parasClean0.length - 1; pc0 >= 0; pc0--) {
                var pcTxt = ptxt(parasClean0[pc0]);
                if (/^\s*\[[\s\u00A0\u2000-\u200B]*\]\s*$/.test(pcTxt)) {
                    try { parasClean0[pc0].remove(); } catch(_){}
                }
            }

            // Header normalization: convert headers to {본문N} format
            grepChange(story, "\\bno\\.\\s*(\\d{1,3}(?:~\\d{1,3})?)", "{$1}");
            // EBS \uB9AC\uB529\uD30C\uC6CC \uB4F1\uC758 "Example N" \uB77C\uBCA8\uB3C4 \uB3D9\uC77C\uD558\uAC8C {N}\uC73C\uB85C \uBCC0\uD658
            // (\uB77C\uBCA8 \uC885\uB958\uC5D0 \uBB34\uAD00\uD558\uAC8C \uD5E4\uB354 \uB77C\uC778 \uB05D\uC758 \uC9C0\uBB38 \uBC88\uD638\uB97C {N}\uC73C\uB85C \uC815\uADDC\uD654)
            grepChange(story, "\\bExample\\s+(\\d{1,3})", "{$1}");
            // "N. p<page>-Example" (Example \uB4A4 \uC22B\uC790 \uC5C6\uC74C) \u2014 prefix \uBC88\uD638\uB97C \uBCF8\uBB38\uBC88\uD638\uB85C \uC0AC\uC6A9 (\uC608: 13\uB144 3\uC6D4 \uBAA8\uC758\uACE0\uC0AC)
            grepChange(story, "\\b(\\d+)\\.\\s*p\\d+\\s*[-\u2013\u2014]?\\s*Example\\b", "{$1}");
            grepChange(story, "\\bANALYSIS\\b", "{\uBD84\uC11D}");
            grepChange(story, "\\b\\d+\\.\\s*L\\d+\\s*[-\u2013\u2014\\.]?\\s*p\\.?\\s*\\d+[^\\r\\n]*?\uBCF8\uBB38\\s*(\\d+)\\b", "{\uBCF8\uBB38$1}");
            grepChange(story, "L\\d+\\s*[-\u2013\u2014\\.]?\\s*p\\.?\\s*\\d+[^\\r\\n]*?\uBCF8\uBB38\\s*(\\d+)\\b", "{\uBCF8\uBB38$1}");
            grepChange(story, "(\uBCF8\uBB38)\\s*(\\d+)", "{$1$2}");
            grepChange(story, "\\b(\\d+)\\.\\s*L\\d+\\s*[-\u2013\u2014\\.]?\\s*p\\.?\\s*\\d+\\b", "{\uBCF8\uBB38$1}");
            grepChange(story, "\\bL\\d+\\s*[-\u2013\u2014\\.]?\\s*p\\.?\\s*\\d+\\b", "");
            grepChange(story, "\\b\\d+\\.\\s*p\\d+\\s*[-\u2013\u2014]?\\s*\uC11C\uC220\uD615\\s*Practice\\b", "{\uC11C\uC220\uD615 Practice}");
            grepChange(story, "\\b\\d+\\.\\s*p\\d+\\s*[-\u2013\u2014]?\\s*\uB17C\uC220\uD615\\s*Prac(?:tice|ice)\\b", "{\uB17C\uC220\uD615 Practice}");

            // Clean up residual text before {
            for (var r = 0; r < 3; r++) {
                grepChange(story, "((?:^|,)\\s*)[^\\{\\r\\n]*?(\\{[^\\}]+\\})", "$1$2");
                grepChange(story, "\\-\\s*(\\{)", "$1");
                grepChange(story, "(^|,)\\s+(\\{)", "$1$2");
            }

            // 구조 기반 frame 분리:
            // (1) 헤더({...}) = 새 본문 = 페이지 시작 (startParagraph = NEXT_PAGE)
            // (2) 조건(주어진 문장) = 같은 본문 안 하단 영역 = 새 frame (startParagraph = NEXT_FRAME)
            //
            // SpecialCharacters.FRAME_BREAK character 삽입은 동아박 마스터 구조에서
            // silent fail 또는 효과 없음이 확인되어 startParagraph 속성 방식으로 변경.
            //
            // 조건 식별 시퀀스: 헤더 블록 안에서 (X) 선지 시퀀스가 끝난 직후
            // 첫 영문 알파벳으로 시작하는(한글 미포함) 단락
            var parasAll = parasOf(story);
            var headerIdx = [];
            for (var i = 0; i < parasAll.length; i++) {
                if (/^\s*\{[^}]+\}/.test(ptxt(parasAll[i]))) headerIdx.push(i);
            }

            var conditionIdxList = [];
            var headerEnds = headerIdx.concat([parasAll.length]);
            for (var iBl = 0; iBl < headerEnds.length - 1; iBl++) {
                var bStart = headerEnds[iBl];
                var bEnd = headerEnds[iBl + 1];
                var sawChoice = false;
                for (var iPB = bStart + 1; iPB < bEnd; iPB++) {
                    var pTxtB = ptxt(parasAll[iPB]);
                    var pTrim = pTxtB.replace(/^[\s　]+|[\s　]+$/g, "");
                    if (!pTrim) continue;
                    if (/^\s*\([A-Z]\)/.test(pTxtB)) { sawChoice = true; continue; }
                    // 영문 알파벳으로 시작 + 한글 미포함 → 조건(주어진 문장)
                    // (￼ 앵커, 한글 발문, 빈줄 등은 모두 skip)
                    if (sawChoice && /^[A-Za-z]/.test(pTrim) && !/[가-힣]/.test(pTrim)) {
                        conditionIdxList.push(iPB);
                        break;
                    }
                }
            }

            // 헤더 (첫 번째 제외) → 본문 1개당 새 프레임/페이지
            // EBS 리딩파워: 페이지당 2 프레임이라 NEXT_FRAME (페이지 안 다음 프레임), 동아박: NEXT_PAGE
            var headerStart = (workbookType === "EBS") ? StartParagraph.NEXT_FRAME : StartParagraph.NEXT_PAGE;
            for (var h = 1; h < headerIdx.length; h++) {
                try { parasAll[headerIdx[h]].startParagraph = headerStart; } catch(_){}
            }
            // EBS: startParagraph만으로 frame 분리가 깨지는 케이스 대비 GREP로 FRAME_BREAK 메타시퀀스(~M) 추가
            // 첫 번째 헤더(스토리 시작)는 제외하기 위해 lookbehind로 \r(paragraph break) 다음만 매칭
            if (workbookType === "EBS") {
                try {
                    resetGrep();
                    app.findGrepPreferences.findWhat = "(?<=\\r)(\\{[^}]+\\})";
                    app.changeGrepPreferences.changeTo = "~M$1";
                    story.changeGrep();
                    resetGrep();
                } catch(_){}
            }
            // 조건 → NEXT_FRAME: 같은 페이지 안 하단 영역으로 강제 분리
            for (var ic = 0; ic < conditionIdxList.length; ic++) {
                try { parasAll[conditionIdxList[ic]].startParagraph = StartParagraph.NEXT_FRAME; } catch(_){}
            }

            // {…} headers + [N] bracket → [기본 단락] (전체 단락에 스타일 적용)
            parasAll = parasOf(story);
            for (var iFx = 0; iFx < parasAll.length; iFx++) {
                var tt = ptxt(parasAll[iFx]);
                // bracket [41~42] 등에도 기본 단락 적용
                if (/^\s*\[\d+/.test(tt)) {
                    try { parasAll[iFx].applyParagraphStyle(BASIC_PARA, true); } catch(_){}
                }
                if (/^\s*\{[^}]+\}/.test(tt)) {
                    try { parasAll[iFx].appliedParagraphStyle = BASIC_PARA; } catch(_){}
                }
            }

            // 모든 {header} 다음 첫 비빈 단락 → C1_BTM
            // (지문번호 다음 오는 지문 본문 — EBS 등 본문이 별도 줄로 있는 원고 처리)
            // mockexam의 (A) 같은 경우는 다음 (A)~(Z) → C1 단계에서 다시 덮어씌워짐
            if (S1_C1_BTM) {
                var hParas = parasOf(story);
                for (var hi = 0; hi < hParas.length - 1; hi++) {
                    var hTxt = ptxt(hParas[hi]);
                    if (!/^\s*\{[^}]+\}/.test(hTxt)) continue;
                    // 다음 비빈 단락 찾기 — 공백/탭/특수공백/ZWSP만 있는 단락은 건너뜀
                    var hn = hi + 1;
                    while (hn < hParas.length &&
                           /^[\s\u00A0\u2000-\u200B\u202F\u205F\u3000]*$/.test(ptxt(hParas[hn]))) {
                        hn++;
                    }
                    if (hn < hParas.length) {
                        try { hParas[hn].appliedParagraphStyle = S1_C1_BTM; } catch(_){}
                    }
                }
            }

            // (A)~(Z) → C1_문장 배열
            if (S1_C1) {
                var paras2 = parasOf(story);
                var inBlock = false;
                for (var i2 = 0; i2 < paras2.length; i2++) {
                    if (i2 > 0 && /^\s*\{[^}]+\}/.test(ptxt(paras2[i2 - 1]))) inBlock = true;
                    if (has3PlusGaps(ptxt(paras2[i2]))) inBlock = false;
                    if (inBlock && /^\s*\([A-Z]\)/.test(ptxt(paras2[i2]))) {
                        try { paras2[i2].appliedParagraphStyle = S1_C1; } catch(_){}
                    }
                }
            }

            // 3+ space paragraphs → C1_문장 배열 하단 + 탭 제거
            if (S1_C1_BTM) {
                paras2 = parasOf(story);
                for (var i3 = 0; i3 < paras2.length; i3++) {
                    if (has3PlusGaps(ptxt(paras2[i3]))) {
                        try { paras2[i3].appliedParagraphStyle = S1_C1_BTM; } catch(_){}
                    }
                }
                // 하단 단락의 탭 + 선행 공백 제거
                resetGrep();
                app.findGrepPreferences.appliedParagraphStyle = S1_C1_BTM;
                app.findGrepPreferences.findWhat = "\\t";
                app.changeGrepPreferences.changeTo = "";
                story.changeGrep();
                resetGrep();
                // 선행 공백(3칸 이상) → 제거
                resetGrep();
                app.findGrepPreferences.appliedParagraphStyle = S1_C1_BTM;
                app.findGrepPreferences.findWhat = "^\\s{3,}";
                app.changeGrepPreferences.changeTo = "";
                story.changeGrep();
                resetGrep();
            }

            // After bottom, (A|B|C) → C1_문장 배열 하단 지문
            // BTM 라인이 3+ space gaps 패턴(mockexam의 "주어진 문장")일 때만 적용.
            // EBS처럼 헤더 다음 본문이 BTM이 된 케이스는 (A)(B)(C)도 일반 선지여야 하므로 건너뜀.
            if (S1_C1_BTM_T) {
                paras2 = parasOf(story);
                for (var i4 = 0; i4 < paras2.length; i4++) {
                    try {
                        var pStyle = paras2[i4].appliedParagraphStyle;
                        if (!(pStyle === S1_C1_BTM || (pStyle && S1_C1_BTM && pStyle.name === S1_C1_BTM.name))) continue;
                        // mockexam 주어진 문장 식별: 3+ space gaps 또는 탭 패턴
                        if (!has3PlusGaps(ptxt(paras2[i4]))) continue;
                        var j2 = i4 + 1;
                        while (j2 < paras2.length && /^[\u0009\u0020\u00A0\u2000-\u200B\u202F\u205F\u3000]*$/.test(ptxt(paras2[j2]))) j2++;
                        if (j2 >= paras2.length) continue;
                        var m = ptxt(paras2[j2]).match(/^\s*\(([ABC])\)/);
                        if (m) {
                            var kk = j2;
                            while (kk < paras2.length) {
                                var ct = ptxt(paras2[kk]);
                                if (/\{/.test(ct)) break;
                                if (!/^\s*\(([ABC])\)/.test(ct)) break;
                                paras2[kk].appliedParagraphStyle = S1_C1_BTM_T;
                                kk++;
                            }
                        }
                    } catch(_){}
                }

                // Circled numbers → 하단 지문
                var hits7 = grepFind(story, "[\\x{2460}-\\x{2473}\\x{24F5}-\\x{24FF}\\x{2776}-\\x{2793}]");
                for (var i5 = 0; i5 < hits7.length; i5++) {
                    try { hits7[i5].paragraphs[0].appliedParagraphStyle = S1_C1_BTM_T; } catch(_){}
                }

                // BTM(주어진 문장) → 빈 단락 → BTM_T(하단 본문) 사이의 [기본 단락] 빈 줄 한 개 제거
                var parasGap = parasOf(story);
                for (var iG = parasGap.length - 2; iG >= 1; iG--) {
                    var prevStyG = parasGap[iG - 1].appliedParagraphStyle;
                    var isPrevBTM = (prevStyG === S1_C1_BTM || (prevStyG && S1_C1_BTM && prevStyG.name === S1_C1_BTM.name));
                    if (!isPrevBTM) continue;
                    var curTG = ptxt(parasGap[iG]);
                    if (!/^[\s\u00A0\u2000-\u200B\u202F\u205F\u3000]*$/.test(curTG)) continue;
                    var nextStyG = parasGap[iG + 1].appliedParagraphStyle;
                    var isNextBTM_T = (nextStyG === S1_C1_BTM_T || (nextStyG && S1_C1_BTM_T && nextStyG.name === S1_C1_BTM_T.name));
                    if (!isNextBTM_T) continue;
                    try { parasGap[iG].remove(); } catch(_){}
                }
            }

            // 교과서 워크북 c1 하단 영역 식별
            // 모의고사 c1은 "주어진 문장"이 3+ space gap 패턴이라 위 BTM/BTM_T 로직이 잡지만,
            // 교과서 c1은 《제목》 또는 평문 한 줄 + (A)/원문자 하단지문 구조라 별도 분기 필요.
            // 헤더({...}) + (A)~(Z) 선지 + 빈줄 + 한 줄 텍스트(BTM) + 빈줄? + (A)/원문자 시작 단락(BTM_T) 매칭.
            if (workbookType === "교과서" && S1_C1_BTM && S1_C1_BTM_T) {
                var parasTb = parasOf(story);
                var hdrIdxsTb = [];
                for (var hh = 0; hh < parasTb.length; hh++) {
                    if (/^\s*\{[^}]+\}/.test(ptxt(parasTb[hh]))) hdrIdxsTb.push(hh);
                }
                hdrIdxsTb.push(parasTb.length);
                for (var iHB = 0; iHB < hdrIdxsTb.length - 1; iHB++) {
                    var bStart = hdrIdxsTb[iHB];
                    var bEnd = hdrIdxsTb[iHB + 1];
                    var lastChoiceTb = -1;
                    for (var iCt = bStart + 1; iCt < bEnd; iCt++) {
                        if (/^\s*\([A-Z]\)/.test(ptxt(parasTb[iCt]))) lastChoiceTb = iCt;
                    }
                    if (lastChoiceTb === -1) continue;
                    var idxAfterTb = lastChoiceTb + 1;
                    while (idxAfterTb < bEnd && /^[\s  -​  　]*$/.test(ptxt(parasTb[idxAfterTb]))) idxAfterTb++;
                    if (idxAfterTb >= bEnd) continue;
                    var btmIdxTb = idxAfterTb;
                    var idxAfterBtmTb = btmIdxTb + 1;
                    while (idxAfterBtmTb < bEnd && /^[\s  -​  　]*$/.test(ptxt(parasTb[idxAfterBtmTb]))) idxAfterBtmTb++;
                    if (idxAfterBtmTb >= bEnd) continue;
                    var nxtTxtTb = ptxt(parasTb[idxAfterBtmTb]);
                    if (!/^\s*\([A-Z]\)/.test(nxtTxtTb) && !/[①-⑳]/.test(nxtTxtTb)) continue;
                    var existingBtmSty = parasTb[btmIdxTb].appliedParagraphStyle;
                    if (existingBtmSty && S1_C1_BTM && existingBtmSty.name === S1_C1_BTM.name) continue;
                    try { parasTb[btmIdxTb].appliedParagraphStyle = S1_C1_BTM; } catch(_){}
                    var idxBtmTtb = idxAfterBtmTb;
                    while (idxBtmTtb < bEnd) {
                        var btTxtTb = ptxt(parasTb[idxBtmTtb]);
                        if (/^\s*\{[^}]+\}/.test(btTxtTb)) break;
                        if (btTxtTb.replace(/[\s  -​  　]/g, '') !== '') {
                            try { parasTb[idxBtmTtb].appliedParagraphStyle = S1_C1_BTM_T; } catch(_){}
                        }
                        idxBtmTtb++;
                    }
                }
                // BTM → 빈 단락 → BTM_T 사이 빈 줄 1개 제거 (mockexam 갭 처리와 동일)
                var parasGapTb = parasOf(story);
                for (var iGt = parasGapTb.length - 2; iGt >= 1; iGt--) {
                    var prevStyTb = parasGapTb[iGt - 1].appliedParagraphStyle;
                    var isPrevBTMtb = (prevStyTb === S1_C1_BTM || (prevStyTb && S1_C1_BTM && prevStyTb.name === S1_C1_BTM.name));
                    if (!isPrevBTMtb) continue;
                    var curTGtb = ptxt(parasGapTb[iGt]);
                    if (!/^[\s  -​  　]*$/.test(curTGtb)) continue;
                    var nextStyTb = parasGapTb[iGt + 1].appliedParagraphStyle;
                    var isNextBTM_Ttb = (nextStyTb === S1_C1_BTM_T || (nextStyTb && S1_C1_BTM_T && nextStyTb.name === S1_C1_BTM_T.name));
                    if (!isNextBTM_Ttb) continue;
                    try { parasGapTb[iGt].remove(); } catch(_){}
                }
            }

            // Arrow icon insertion after C1 blocks (원본 STEP1C1.jsx 방식)
            var arrowSrc = findLabeledItem("\uD654\uC0B4\uD45C \uB2F5\uC9C0");
            if (arrowSrc && S1_C1) {
                var arrowState = unlockItem(arrowSrc);
                // STEP1C1_New.jsx 방식: 블록 마지막 C1 단락 끝에 \\r\\r 삽입 → 두 번째 빈 줄에 화살표
                // 기존 빈 줄 의존하지 않아 EBS 등 빈 줄이 없거나 불규칙해도 안정적으로 동작
                var paras3 = parasOf(story);
                for (var ia = 0; ia < paras3.length; ia++) {
                    var pa = paras3[ia].appliedParagraphStyle;
                    var isC1Cur = (pa === S1_C1 || (pa && S1_C1 && pa.name === S1_C1.name));
                    if (!isC1Cur) continue;
                    // 다음 단락도 C1이면 블록 내부 → 마지막 단락이 아님
                    if (ia + 1 < paras3.length) {
                        var na = paras3[ia + 1].appliedParagraphStyle;
                        var nextIsC1 = (na === S1_C1 || (na && S1_C1 && na.name === S1_C1.name));
                        if (nextIsC1) continue;
                    }
                    // 여기서 ia = 블록 마지막 C1 단락
                    var lastP = paras3[ia];
                    // 이미 화살표가 있으면 건너뜀 (재실행 안전성)
                    var hasArrow = false;
                    try {
                        var chsA = lastP.characters;
                        for (var ccA = 0; ccA < chsA.length; ccA++) {
                            if (chsA[ccA].contents === SpecialCharacters.ANCHOR_MARKER) {
                                var piA = chsA[ccA].pageItems[0];
                                if (piA && piA.label === "\uD654\uC0B4\uD45C \uB2F5\uC9C0") { hasArrow = true; break; }
                            }
                        }
                        for (var na2 = 1; na2 <= 2 && !hasArrow && ia + na2 < paras3.length; na2++) {
                            var chsB = paras3[ia + na2].characters;
                            for (var ccB = 0; ccB < chsB.length; ccB++) {
                                if (chsB[ccB].contents === SpecialCharacters.ANCHOR_MARKER) {
                                    var piB = chsB[ccB].pageItems[0];
                                    if (piB && piB.label === "\uD654\uC0B4\uD45C \uB2F5\uC9C0") { hasArrow = true; break; }
                                }
                            }
                        }
                    } catch(_){}
                    if (hasArrow) continue;

                    try {
                        var ipL = lastP.insertionPoints[-1];
                        var arrowParaIdx = -1;
                        if (workbookType === "EBS") {
                            // EBS: \uC6D0\uACE0 \uAD6C\uC870\uC0C1 \uB9C8\uC9C0\uB9C9 \uC120\uC9C0 \uB2E4\uC74C \uBE48 \uB2E8\uB77D\uC774 \uC774\uBBF8 \uC788\uC74C \u2192 \uAC70\uAE30\uC5D0 \uD654\uC0B4\uD45C \uC0BD\uC785
                            // \r\r\uB85C \uBE48 \uC904 \uCD94\uAC00\uD558\uBA74 \uD654\uC0B4\uD45C\uAC00 \uB2E4\uC74C \uD398\uC774\uC9C0\uB85C \uD758\uB7EC\uAC00 frame break \uC704\uCE58\uAC00 \uC5B4\uAE0B\uB0A8
                            if (ia + 1 < paras3.length) {
                                var nextTxt = ptxt(paras3[ia + 1]);
                                if (/^[\s\u00A0\u2000-\u200B\u202F\u205F\u3000\r\n]*$/.test(nextTxt)) {
                                    arrowParaIdx = ia + 1;
                                }
                            }
                            if (arrowParaIdx < 0) {
                                ipL.contents = "\r";
                                paras3 = parasOf(story);
                                if (ia + 1 < paras3.length) arrowParaIdx = ia + 1;
                            }
                        } else {
                            // \uB3D9\uC544\uBC15/\uAD50\uACFC\uC11C \uAE30\uC874 \uBC29\uC2DD \u2014 \r\r\uB85C \uBE48 \uB2E8\uB77D 2\uAC1C \uB9CC\uB4E4\uACE0 \uB450 \uBC88\uC9F8\uC5D0 \uD654\uC0B4\uD45C
                            ipL.contents = "\r\r";
                            paras3 = parasOf(story);
                            if (ia + 1 < paras3.length) {
                                try { paras3[ia + 1].appliedParagraphStyle = BASIC_PARA; } catch(_){}
                            }
                            if (ia + 2 < paras3.length) arrowParaIdx = ia + 2;
                        }
                        if (arrowParaIdx >= 0 && arrowParaIdx < paras3.length) {
                            var newPara = paras3[arrowParaIdx];
                            var icon = arrowSrc.duplicate();
                            try {
                                icon.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION;
                                icon.textWrapPreferences.textWrapMode = TextWrapModes.NONE;
                            } catch(_){}
                            try { icon.label = "\uD654\uC0B4\uD45C \uB2F5\uC9C0"; } catch(_){}
                            icon.anchoredObjectSettings.insertAnchoredObject(
                                newPara.insertionPoints[0], AnchorPosition.INLINE_POSITION
                            );
                            try { newPara.appliedParagraphStyle = BASIC_PARA; } catch(_){}
                            try { icon.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}
                            paras3 = parasOf(story);
                            ia = arrowParaIdx;
                        }
                    } catch(_){}
                }
                relockItem(arrowSrc, arrowState);
            }

            // 발문 삽입: C1_하단 지문(하단 선지) 앞에 발문 텍스트 삽입
            // 원문자(①②③) → 위치 발문, (A)(B)(C) → 순서 발문
            var PROMPT_CIRC = "\uC544\uB798 \uC8FC\uC5B4\uC9C4 \uBB38\uC7A5\uC774 \uB4E4\uC5B4\uAC08 \uC704\uCE58\uB85C \uC54C\uB9DE\uC740 \uACF3\uC744 \uACE0\uB974\uC2DC\uC624.";
            var PROMPT_ORDER = "\uC544\uB798 \uC8FC\uC5B4\uC9C4 \uBB38\uC7A5 \uB2E4\uC74C\uC5D0 \uC774\uC5B4\uC9C8 \uBB38\uC7A5\uB4E4\uC758 \uC801\uC808\uD55C \uC21C\uC11C\uB97C \uC4F0\uC2DC\uC624.";
            paras2 = parasOf(story);
            for (var pi2 = paras2.length - 1; pi2 >= 0; pi2--) {
                var p2sty = paras2[pi2].appliedParagraphStyle;
                var isBottomT = (p2sty === S1_C1_BTM_T || (p2sty && S1_C1_BTM_T && p2sty.name === S1_C1_BTM_T.name));
                if (!isBottomT) continue;
                // 이 블록의 첫 번째 하단지문인지 확인
                if (pi2 > 0) {
                    var prevSty2 = paras2[pi2 - 1].appliedParagraphStyle;
                    var isPrevBT = (prevSty2 === S1_C1_BTM_T || (prevSty2 && S1_C1_BTM_T && prevSty2.name === S1_C1_BTM_T.name));
                    if (isPrevBT) continue; // 블록 중간은 건너뛰기
                }
                // 유형 판별
                var btTxt = ptxt(paras2[pi2]);
                var promptText = "";
                if (/[\u2460-\u2473]/.test(btTxt)) {
                    promptText = PROMPT_CIRC;
                } else if (/^\s*\([A-Z]\)/.test(btTxt)) {
                    promptText = PROMPT_ORDER;
                }
                if (promptText !== "") {
                    // 하단지문 앞 하단(C1_BTM) 단락을 찾아 그 앞에 삽입
                    var insertIdx = pi2;
                    // 하단지문 바로 위의 빈줄/하단 단락 건너뛰기
                    while (insertIdx > 0) {
                        var aboveSty = paras2[insertIdx - 1].appliedParagraphStyle;
                        var isBTM = (aboveSty === S1_C1_BTM || (aboveSty && S1_C1_BTM && aboveSty.name === S1_C1_BTM.name));
                        var isEmpty = ptxt(paras2[insertIdx - 1]).replace(/[\r\n]/g, '') === '';
                        if (isBTM || isEmpty) { insertIdx--; } else { break; }
                    }
                    try {
                        paras2[insertIdx].insertionPoints[0].contents = promptText + "\r";
                        paras2 = parasOf(story);
                        // 발문 단락에 하단문제 스타일 적용
                        if (S1_HADAN) {
                            try { paras2[insertIdx].appliedParagraphStyle = S1_HADAN; } catch(_){}
                        }
                        // 발문 앞에 아이콘+탭 삽입
                        var iconC1 = findLabeledItem("STEP1 \uBB38\uC81C\uC544\uC774\uCF58");
                        if (iconC1) {
                            try {
                                var icState = unlockItem(iconC1);
                                insertInlineIcon(iconC1, paras2[insertIdx].insertionPoints[0]);
                                paras2 = parasOf(story);
                                // 아이콘 뒤 탭
                                var chs = paras2[insertIdx].characters;
                                for (var cci = 0; cci < chs.length; cci++) {
                                    if (("" + chs[cci].contents) === "\uFFFC") {
                                        paras2[insertIdx].insertionPoints[cci + 1].contents = "\t";
                                        break;
                                    }
                                }
                                relockItem(iconC1, icState);
                            } catch(_){}
                        }
                    } catch(_){}
                    paras2 = parasOf(story);
                }
            }

            // Final: {…} paragraphs → [기본 단락] (safety)
            var parasEnd = parasOf(story);
            for (var e1 = 0; e1 < parasEnd.length; e1++) {
                if (/\{/.test(ptxt(parasEnd[e1]))) {
                    try { parasEnd[e1].appliedParagraphStyle = BASIC_PARA; } catch(_){}
                }
            }

            // Clean up header remnants
            grepChange(story, "(\\{\uBCF8\uBB38\\d+\\})\\([^\\)]*\\)", "$1");
            grepChange(story, "(\\{[A-Za-z][A-Za-z\\s]+\\})\\([^\\)]*\\)", "$1");

            // c1_btm\uB9CC \uC81C\uC678: \uD558\uB2E8 \uB2E8\uB77D(BTM/BTM_T/HADAN) \uC0AD\uC81C \u2192 \uD558\uB2E8 frame\uC740 \uBE48 \uCC44\uB85C \uB0A8\uACE0 \uC0C1\uB2E8\uC740 \uC720\uC9C0
            if (excludeSet["step1_c1_btm"]) {
                var btmName  = S1_C1_BTM   ? S1_C1_BTM.name   : null;
                var btmTName = S1_C1_BTM_T ? S1_C1_BTM_T.name : null;
                var hadanName= S1_HADAN    ? S1_HADAN.name    : null;
                var parasDel = parasOf(story);
                for (var iDel = parasDel.length - 1; iDel >= 0; iDel--) {
                    try {
                        var styDel = parasDel[iDel].appliedParagraphStyle;
                        if (!styDel) continue;
                        var snm = styDel.name;
                        if (snm === btmName || snm === btmTName || snm === hadanName) {
                            parasDel[iDel].remove();
                        }
                    } catch(_){}
                }
                try { story.recompose(); } catch(_){}
            }

        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP1C1");

        addLog("STEP1 C1 완료");
        stepsDone++;
    }

    // ---- STEP 1 C2: 빈칸 어휘 ----
    function processStep1C2(story, paragraphs) {
        addLog("STEP1 C2 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Character style reset
            // char style reset skipped (story.contents already clean)

            // Remove headers
            insertHeaderBreaks(story);

            // Tab → return
            grepChange(story, "\\t", "\\r");

            // All paragraphs → C2_빈칸 어휘
            if (S1_C2) {
                var parasAll = story.paragraphs;
                for (var i = 0; i < parasAll.length; i++) {
                    try { parasAll[i].applyParagraphStyle(S1_C2, true); } catch(_){}
                }
            }

            // Korean 2+ characters → C2_빈칸 어휘 한글
            if (S1_C2_KOR) {
                var paras2 = story.paragraphs;
                for (var j = 0; j < paras2.length; j++) {
                    var txt = paras2[j].contents || "";
                    if (hasKorean2(txt)) {
                        try { paras2[j].applyParagraphStyle(S1_C2_KOR, true); } catch(_){}
                    }
                }
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP1C2");

        addLog("STEP1 C2 완료");
        stepsDone++;
    }

    // ---- STEP 2 A1: 어법 선택 ----
    function processStep2A1(story, paragraphs) {
        addLog("STEP2 A1 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Character style reset
            // char style reset skipped (story.contents already clean)

            // Extract tail from header for {…} conversion
            function extractTail(txt) {
                var s = (txt || "").replace(/^\s+|\s+$/g, "");
                var m;
                m = s.match(/^\s*\d+[\s.)-]*L\d+(?:\s*[-\u2013\u2014]\s*p\.?\s*\d+)?\s*[-\u2013\u2014]?\s*(\uBCF8\uBB38\s*\d+)\b/i);
                if (m) return m[1];
                m = s.match(/^\s*(\d+)[\s.)-]*L\d+(?:\s*[-\u2013\u2014]\s*p\.?\s*\d+)\s*$/i);
                if (m) return "\uBCF8\uBB38" + m[1];
                m = s.match(/^\s*\d+[\s.)-]*L\d+(?:\s*[-\u2013\u2014]\s*p\.?\s*\d+)?\s*[-\u2013\u2014]?\s*(.+)$/i);
                if (m) {
                    var tail = m[1].replace(/^\s*p\.?\s*\d+\s*[-\u2013\u2014]?\s*/i, "");
                    return tail;
                }
                m = s.match(/^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*(\d+(?:~\d+)?)(?:[\s-]*(.+))?$/i);
                if (m) return (m[2] ? m[2] : m[1]);
                if (/\uC218\uB2A5\s*\uB300\uBE44\s*analysis/i.test(s)) return "\uBD84\uC11D";
                m = s.match(/^\s*\d+[\s.)-]*p\.?\s*\d+\s*(?:[-\u2013\u2014]|\s)+\s*(.+)$/i);
                if (m) return m[1];
                return "";
            }

            // Find and process headers
            var reL = /^\s*\d+\s*[.)]?\s*L\d+\s*[-\u2013\u2014\uFE63\uFF0D]\s*.+/i;
            var rePNo = /^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-\u2013\u2014\uFE63\uFF0D]|\s)*no\.?\s*\d+(?:~\d+)?\b.*$/i;
            var rePDesc = /^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-\u2013\u2014\uFE63\uFF0D]|\s)+\s*.+$/i;
            var reAnalysis = /^\s*\d+.*\uC218\uB2A5\s*\uB300\uBE44\s*analysis.*$/i;

            function isA1Header(txt) {
                var t = (txt || "").replace(/\r|\n/g, "");
                return reL.test(t) || rePNo.test(t) || rePDesc.test(t) || reAnalysis.test(t);
            }

            // Find top header
            var parasArr = parasOf(story);
            var topIdx = null;
            for (var ti = 0; ti < parasArr.length; ti++) {
                if (isA1Header(parasArr[ti].contents || "")) {
                    topIdx = parasArr[ti].index;
                    break;
                }
            }

            // Process headers in reverse
            for (var h = parasArr.length - 1; h >= 0; h--) {
                var header = parasArr[h];
                var htxt = header.contents || "";
                if (!isA1Header(htxt)) continue;

                // Remove blank paragraphs above and below
                // Convert header text to {…}
                try {
                    var tail = extractTail(htxt);
                    if (tail !== "") {
                        var newText = "{" + tail.replace(/^\s+|\s+$/g, "") + "}\r";
                        if (header.contents !== newText) header.contents = newText;
                    }
                } catch(_){}

                // Insert frame break (skip the very first/top header)
                try {
                    if (header.index !== topIdx) {
                        header.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
                    }
                } catch(_){}
            }

            // Apply A1_어법 선택 to all paragraphs
            if (S2_A1) {
                try { story.paragraphs.everyItem().appliedParagraphStyle = S2_A1; } catch(_){}
            }
            if (CS_NONE) {
                // char style reset skipped (story.contents already clean)
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP2A1");

        addLog("STEP2 A1 완료");
        stepsDone++;
    }

    // ---- STEP 2 A1 BTM (하단): 어법 선택 객관식 ----
    // 원고 구조: 각 프레임에 "지문 1개"만 들어간다.
    //   - 어법선택 객관식의 지문은 본문 내 5개 보기를 ①②③④⑤로 표시
    //     → 지문 단락에는 반드시 ①(U+2460)~⑳ circled-digit 1개 이상 포함됨.
    //   - 그 외(책 제목/발문/섹션 라벨/부제목/지문번호 헤더/빈 단락)는 모두 삭제 대상.
    // 헤더 형식 정규식 매칭이 아니라 "이 단락이 지문인가?"의 구조 판단을 사용한다 (헤더 형식 변동 무관).
    function processStep2A1Btm(story, paragraphs) {
        addLog("STEP2 A1 하단 처리 시작");
        // 밑줄은 지문 밑줄 문자스타일로
        insertContent(story, paragraphs, CS_PASSAGE_UL);

        app.doScript(function() {
            function isPassage(txt) {
                if (!txt) return false;
                for (var k = 0; k < txt.length; k++) {
                    var c = txt.charCodeAt(k);
                    if (c >= 0x2460 && c <= 0x2473) return true; // ①~⑳ (circled 1~20)
                }
                return false;
            }

            // 1) 비지문 단락 모두 삭제 (역순)
            var paras = parasOf(story);
            for (var i = paras.length - 1; i >= 0; i--) {
                if (i >= paras.length) continue;
                var t = (paras[i].contents || "").replace(/[\r\n]+$/, "");
                if (!isPassage(t)) {
                    try { paras[i].remove(); } catch(_){}
                    paras = parasOf(story);
                }
            }

            // 2) 두 번째 지문부터 단락 시작 위치에 프레임 브레이크 (첫 지문은 첫 프레임)
            paras = parasOf(story);
            for (var j = paras.length - 1; j >= 1; j--) {
                try {
                    paras[j].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
                } catch(_){}
            }

            // 3) A1_어법 선택 하단 스타일 적용
            if (S2_A1_BTM) {
                try { story.paragraphs.everyItem().appliedParagraphStyle = S2_A1_BTM; } catch(_){}
            }

            try { story.recompose(); } catch(_){}
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP2A1BTM");

        addLog("STEP2 A1 하단 완료");
        stepsDone++;
    }

    // ---- STEP 2 B1: 어법 OX ----
    function processStep2B1(story, paragraphs) {
        addLog("STEP2 B1 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // Apply B1_어법 OX to all
            if (S2_B1) {
                try { story.paragraphs.everyItem().appliedParagraphStyle = S2_B1; } catch(_){}
            }

            // Remove headers and insert frame breaks
            insertHeaderBreaks(story);

            // TF button placement via link
            var tfLinkPath = null, tfWidth = null;
            for (var gi = 0; gi < doc.allGraphics.length; gi++) {
                var g = doc.allGraphics[gi];
                try {
                    if (g.parent && g.parent.label === "TF \uBC84\uD2BC" && g.itemLink) {
                        tfLinkPath = g.itemLink.filePath;
                        var gb = g.parent.geometricBounds;
                        tfWidth = gb[3] - gb[1];
                        break;
                    }
                } catch(_){}
            }

            if (tfLinkPath) {
                var paras = story.paragraphs;
                for (var pIdx = paras.length - 1; pIdx >= 0; pIdx--) {
                    var p = paras[pIdx];
                    if (p.contents === "\r" || p.characters.length < 2) continue;

                    var hasAnchor = false;
                    try { hasAnchor = (p.characters[-2].contents === "\uFFFC"); } catch(_){}
                    if (hasAnchor) continue;

                    var ip = p.insertionPoints[-2];
                    try {
                        if (p.characters[-2].contents !== " ") {
                            ip.contents = " ";
                            ip = p.insertionPoints[-2];
                        }
                    } catch(_){}
                    try {
                        var placed = story.insertionPoints[ip.index].place(File(tfLinkPath))[0];
                        try { placed.anchoredObjectSettings.anchorType = AnchorPosition.INLINE_POSITION; } catch(_){}
                        try {
                            placed.fit(FitOptions.FRAME_TO_CONTENT);
                            var pgb = placed.geometricBounds, pw = pgb[3] - pgb[1];
                            if (pw > 0 && tfWidth) {
                                var scale = (tfWidth / pw) * 100;
                                placed.absoluteHorizontalScale = scale;
                                placed.absoluteVerticalScale = scale;
                            }
                        } catch(_){}
                    } catch(_){}
                }
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP2B1");

        addLog("STEP2 B1 완료");
        stepsDone++;
    }

    // ---- STEP 2 C1: 빈칸 어법 ----
    function processStep2C1(story, paragraphs) {
        addLog("STEP2 C1 처리 시작");
        addLog("STEP2 C1: insertContent 시작 (paragraphs=" + paragraphs.length + ")");
        insertContent(story, paragraphs);
        addLog("STEP2 C1: insertContent 완료");

        app.doScript(function() {
            addLog("STEP2 C1: insertHeaderBreaks 시작");
            insertHeaderBreaks(story);
            addLog("STEP2 C1: insertHeaderBreaks 완료");

            addLog("STEP2 C1: grepChange(tab->return) 시작");
            grepChange(story, "\\t", "\\r");
            addLog("STEP2 C1: grepChange 완료");

            if (S2_C1) {
                var parasAll = story.paragraphs;
                addLog("STEP2 C1: applyStyle S2_C1 시작 (count=" + parasAll.length + ")");
                for (var i = 0; i < parasAll.length; i++) {
                    try { parasAll[i].applyParagraphStyle(S2_C1, true); } catch(_){}
                }
                addLog("STEP2 C1: applyStyle S2_C1 완료");
            } else {
                addLog("STEP2 C1: S2_C1 스타일 없음, 건너뜀");
            }

            if (S1_C2_KOR) {
                var paras2 = story.paragraphs;
                addLog("STEP2 C1: applyStyle S1_C2_KOR 시작 (count=" + paras2.length + ")");
                for (var j = 0; j < paras2.length; j++) {
                    var txt = paras2[j].contents || "";
                    if (hasKorean2(txt)) {
                        try { paras2[j].applyParagraphStyle(S1_C2_KOR, true); } catch(_){}
                    }
                }
                addLog("STEP2 C1: applyStyle S1_C2_KOR 완료");
            } else {
                addLog("STEP2 C1: S1_C2_KOR 스타일 없음, 건너뜀");
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP2C1");

        addLog("STEP2 C1 완료");
        stepsDone++;
    }

    // ---- STEP 2 C2: 영작 배열 ----
    function processStep2C2(story, paragraphs) {
        addLog("STEP2 C2 처리 시작");
        insertContent(story, paragraphs);

        app.doScript(function() {
            // 소괄호 번호 (1), (2)...(99) 단독 줄 제거
            grepChange(story, "^\\s*\\(\\d{1,2}\\)\\s*$", "");
            // 연속 빈줄 정리
            grepChange(story, "\\r{2,}", "\\r");

            // 1단계: 영어 전용 답 단락 먼저 삭제 (아이콘 삽입 전)
            try {
                for (var rr = story.paragraphs.length - 1; rr >= 0; rr--) {
                    var pr = story.paragraphs[rr], srr = pr.contents || "";
                    if (srr.replace(/[\s\u00A0]+/g, "").length === 0) continue;
                    if (srr.indexOf("[") !== -1 && srr.indexOf("]") !== -1) continue;
                    var isEngOnly = /[A-Za-z]/.test(srr) && !/[\uAC00-\uD7A3]/.test(srr) && srr.indexOf("/") === -1;
                    if (isEngOnly) {
                        try { pr.remove(); } catch(_){}
                    }
                }
            } catch(_){}

            // 2단계: 빈줄 정리
            grepChange(story, "\\r{2,}", "\\r");

            // 3단계: Reset to basic
            try { story.paragraphs.everyItem().appliedParagraphStyle = BASIC_PARA; } catch(_){}

            var reKor2 = /[\uAC00-\uD7A3][\s\S]*[\uAC00-\uD7A3]/;

            // 4단계: Korean 2+ → 번호
            if (S2_C2_NUM) {
                var paras = parasOf(story);
                for (var i = 0; i < paras.length; i++) {
                    var txt = paras[i].contents || "";
                    if (reKor2.test(txt)) {
                        try { paras[i].applyParagraphStyle(S2_C2_NUM, true); } catch(_){}
                    }
                }
            }

            // 5단계: Slash paragraphs → 보기
            if (S2_C2_VIEW) {
                var paras2 = parasOf(story);
                for (var j = 0; j < paras2.length; j++) {
                    var raw = paras2[j].contents || "";
                    if (raw.indexOf("/") !== -1) {
                        try { paras2[j].applyParagraphStyle(S2_C2_VIEW, true); } catch(_){}
                    }
                }
            }

            // 6단계: 보기(슬래시) 블록 뒤에 빈줄 2개 + 아이콘 삽입
            // 완성본 구조: 번호→보기→￼(아이콘)→번호→보기→￼→빈줄2~3개→다음문제
            var iconSrc = findLabeledItem("STEP2 \uC601\uC791 \uB2F5\uC9C0");
            if (iconSrc && S2_C2_VIEW) {
                var iconState = unlockItem(iconSrc);
                // 보기 블록의 끝을 역순으로 찾아 아이콘 삽입
                var pAll = parasOf(story);
                for (var t = pAll.length - 1; t >= 0; t--) {
                    var pStyle = pAll[t].appliedParagraphStyle;
                    var isView = (pStyle === S2_C2_VIEW || (pStyle && S2_C2_VIEW && pStyle.name === S2_C2_VIEW.name));
                    if (!isView) continue;
                    // 보기 블록의 마지막인지 확인 (다음이 보기가 아님)
                    var nextIsView = false;
                    if (t + 1 < pAll.length) {
                        var ns = pAll[t + 1].appliedParagraphStyle;
                        nextIsView = (ns === S2_C2_VIEW || (ns && S2_C2_VIEW && ns.name === S2_C2_VIEW.name));
                    }
                    if (nextIsView) continue; // 블록 중간이면 건너뜀

                    // 보기 끝 뒤에 빈줄 삽입 (아이콘용)
                    try { pAll[t].insertionPoints[-1].contents = "\r"; } catch(_){}
                    pAll = parasOf(story);
                    // 새 빈줄에 아이콘 삽입
                    var iconPara = pAll[t + 1];
                    if (iconPara) {
                        try {
                            var dup = iconSrc.duplicate();
                            try { dup.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION; } catch(_){}
                            try { dup.textWrapPreferences.textWrapMode = TextWrapModes.NONE; } catch(_){}
                            dup.anchoredObjectSettings.insertAnchoredObject(iconPara.insertionPoints[0], AnchorPosition.INLINE_POSITION);
                            try { dup.fit(FitOptions.FRAME_TO_CONTENT); } catch(_){}
                            try { dup.label = "STEP2 \uC601\uC791 \uB2F5\uC9C0"; } catch(_){}
                            if (BASIC_PARA) { try { iconPara.applyParagraphStyle(BASIC_PARA, true); } catch(_){} }
                        } catch(_){}
                        pAll = parasOf(story);
                    }
                }
                relockItem(iconSrc, iconState);
            }

            // 7단계: bracket 사이에 빈줄 2개 보장 (문제 간 간격)
            var pFinal = parasOf(story);
            for (var bf = pFinal.length - 1; bf >= 1; bf--) {
                var bfTxt = ptxt(pFinal[bf]);
                if (bfTxt.indexOf("[") === -1 || bfTxt.indexOf("]") === -1) continue;
                // bracket 앞 빈줄 수 확인
                var blanks = 0;
                for (var bb = bf - 1; bb >= 0; bb--) {
                    var bbTxt = ptxt(pFinal[bb]).replace(/[\r\n]/g, '');
                    // 앵커(아이콘) 있는 줄은 건너뜀
                    var hasAnc = false;
                    try {
                        var chs = pFinal[bb].characters;
                        for (var cc = 0; cc < chs.length; cc++) {
                            if (chs[cc].contents === "\uFFFC") { hasAnc = true; break; }
                        }
                    } catch(_){}
                    if (hasAnc) break;
                    if (bbTxt === '') blanks++;
                    else break;
                }
                var need = 2 - blanks;
                if (need > 0 && bf > 0) {
                    for (var nb = 0; nb < need; nb++) {
                        try { pFinal[bf].insertionPoints[0].contents = "\r"; } catch(_){}
                    }
                    pFinal = parasOf(story);
                }
            }

            // 8단계: Remove pure blank paragraphs that are NOT between icon and bracket
            // (빈줄은 아이콘~bracket 사이만 유지, 나머지 제거)
            try {
                var pClean = parasOf(story);
                for (var zz = pClean.length - 1; zz >= 0; zz--) {
                    var zp = pClean[zz], zs = zp.contents || "";
                    var hasAnc = false;
                    try {
                        var zc = zp.characters;
                        for (var z = 0; z < zc.length; z++) {
                            if (zc[z].contents === "\uFFFC") { hasAnc = true; break; }
                        }
                    } catch(_){}
                    if (hasAnc) continue;
                    if (zs.replace(/[\s\u00A0\r\n]+/g, "") !== "") continue;
                    // 빈줄: 다음 단락이 bracket이거나 마지막이면 유지
                    var keepBlank = false;
                    // 아래쪽에 bracket이 있는지 확인
                    for (var zn = zz + 1; zn < pClean.length && zn <= zz + 3; zn++) {
                        var znTxt = ptxt(pClean[zn]);
                        if (znTxt.indexOf("[") !== -1 && znTxt.indexOf("]") !== -1) { keepBlank = true; break; }
                        if (znTxt.replace(/[\s\r\n]+/g, "") !== "") break;
                    }
                    // 위쪽에 아이콘이 있는지 확인
                    if (keepBlank) {
                        var hasIconAbove = false;
                        for (var za = zz - 1; za >= 0 && za >= zz - 3; za--) {
                            try {
                                var ac = pClean[za].characters;
                                for (var az = 0; az < ac.length; az++) {
                                    if (ac[az].contents === "\uFFFC") { hasIconAbove = true; break; }
                                }
                            } catch(_){}
                            if (hasIconAbove) break;
                            var aaTxt = ptxt(pClean[za]).replace(/[\s\r\n]+/g, "");
                            if (aaTxt !== "") break;
                        }
                        if (hasIconAbove) continue; // 아이콘~bracket 사이 빈줄 유지
                    }
                    // 그 외 빈줄 제거
                    try { zp.remove(); } catch(_){}
                }
            } catch(_){}

            // 9단계: Frame breaks at brackets (skip first) + bracket → basic
            // EBS 리딩파워는 영작 배열 문제들이 연속해서 흐르도록 하므로 프레임 브레이크 생략
            try {
                var pBr = parasOf(story);
                var bracketIdxC2 = [];
                for (var bi = 0; bi < pBr.length; bi++) {
                    var biTxt = ptxt(pBr[bi]);
                    if (biTxt.indexOf("[") !== -1 && biTxt.indexOf("]") !== -1 && /^\s*\[/.test(biTxt)) {
                        bracketIdxC2.push(bi);
                    }
                }
                if (workbookType !== "EBS") {
                    for (var bk = bracketIdxC2.length - 1; bk >= 1; bk--) {
                        try { pBr[bracketIdxC2[bk]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(_){}
                        pBr = parasOf(story);
                        // 재색인
                        bracketIdxC2 = [];
                        for (var br2 = 0; br2 < pBr.length; br2++) {
                            var br2Txt = ptxt(pBr[br2]);
                            if (br2Txt.indexOf("[") !== -1 && br2Txt.indexOf("]") !== -1 && /^\s*\[/.test(br2Txt)) {
                                bracketIdxC2.push(br2);
                            }
                        }
                    }
                }

                // All paragraphs containing [ or ] → basic
                pBr = parasOf(story);
                for (var mm = 0; mm < pBr.length; mm++) {
                    var ttm = ptxt(pBr[mm]);
                    if (ttm.indexOf("[") !== -1 || ttm.indexOf("]") !== -1) {
                        try { pBr[mm].applyParagraphStyle(BASIC_PARA, true); } catch(_){}
                    }
                }
            } catch(_){}

        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP2C2");

        addLog("STEP2 C2 완료");
        stepsDone++;
    }

    // ---- STEP 3: 실전 문제 ----
    function processStep3(story, step3Data, isShortStory) {
        addLog("STEP3 처리 시작");

        if (!step3Data) { addLog("STEP3 데이터 없음, 건너뜀"); return; }

        var normalQs = step3Data.normal || [];
        var shortQs  = step3Data.short  || [];

        // Build all paragraphs: normal first, then short
        // Each question prefixed with {YYMMNN} code
        var allParagraphs = [];
        var allQuestions = normalQs.concat(shortQs);

        for (var qi = 0; qi < allQuestions.length; qi++) {
            var q = allQuestions[qi];
            var code = q.code || "";
            // 6자리 코드가 있을 때만 {code} 단락 추가 (교과서 Step3는 code 없음)
            if (code) {
                allParagraphs.push({ text: "{" + code + "}", runs: [] });
            }
            // 원고에 발문이 포함되어 있으므로 별도 추가하지 않음
            // Add question paragraphs
            var qParas = q.paragraphs || [];
            for (var pi = 0; pi < qParas.length; pi++) {
                allParagraphs.push(qParas[pi]);
            }
        }

        if (allParagraphs.length === 0) { addLog("STEP3 문단 없음, 건너뜀"); return; }

        // Insert content
        insertContent(story, allParagraphs);


        app.doScript(function() {
         try {
            // ── 1. 연속 리턴 정리 ──────────────────────────────────────────
            grepChange(story, "\\r{2,}", "\\r");

            // ── 2. <보기>, <조건> 정규화 ────────────────────────────────────
            grepChange(story, "<\\s*\uBCF4\\s*\uAE30\\s*>", "<\uBCF4\uAE30>");
            grepChange(story, "<\\s*\uC870\\s*\uAC74\\s*>", "<\uC870\uAC74>");
            grepChange(story, "\\[\\s*\uBCF4\uAE30\\s*\\]", "<\uBCF4\uAE30>");
            grepChange(story, "\\[\\s*\uC870\uAC74\\s*\\]", "<\uC870\uAC74>");

            // ── 2.5. 보기 박스 순서 정규화 ─────────────────────────────────
            // hwpx 보기 박스 컨테이너에서 본문 rect가 보기 라벨 rect보다 먼저 들어있어
            // 파싱 시 [본문, 보기] 순서로 추출됨. "보기" 단락 직전이 한글 없는 본문이면
            // (= 발문이 아니면) 보기 라벨을 본문 위로 이동.
            // swap된 본문에는 ZWSP(​, U+200B) 임시 마커 삽입 → 보기 propagation 단계에서
            // skip되도록 함 (기존 default 스타일 유지). propagation 후 ZWSP 제거.
            var swParas = story.paragraphs;
            for (var sw = swParas.length - 1; sw >= 1; sw--) {
                var swCur = (swParas[sw].contents || "").replace(/[\r\n]+$/, "").replace(/^[\s　]+|[\s　]+$/g, "");
                if (swCur !== "보기") continue;
                var swPrev = (swParas[sw-1].contents || "").replace(/[\r\n]+$/, "").replace(/^[\s　]+|[\s　]+$/g, "");
                if (swPrev === "" || swPrev === "보기") continue;
                if (/[가-힣]/.test(swPrev)) continue;
                swParas[sw].move(LocationOptions.BEFORE, swParas[sw-1]);
                // swap 후 sw 위치 = 본문 단락. ZWSP(U+200B) 마커로 propagation skip 표시.
                try {
                    var movedPara = swParas[sw];
                    if (movedPara && movedPara.contents.length > 0 && movedPara.contents.charAt(0) !== "​") {
                        movedPara.insertionPoints[0].contents = "​";
                    }
                } catch (e1) {}
            }

            // ── 3. 기본 스타일 일괄 적용 ─────────────────────────────────────
            if (S3_DEFAULT) {
                var paras = story.paragraphs;
                for (var d = 0; d < paras.length; d++) {
                    paras[d].appliedParagraphStyle = S3_DEFAULT;
                }
            }

            // ── 4. "답: ___" 단락 삭제 ──────────────────────────────────────
            grepChange(story, "^\\s*\uB2F5\\s*:?\\s*_+\\s*\\r", "");

            // ── 5. 메인 스타일 분류 ──────────────────────────────────────────
            var paras = story.paragraphs;
            for (var i = 0; i < paras.length; i++) {
                var text = (paras[i].contents || "").replace(/[\r\n]+$/, "");

                // "주어진 문장/글" or "들어갈 위치" → next non-blank paragraph gets 배경
                if (/\uC8FC\uC5B4\uC9C4\s*(\uBB38\uC7A5|\uAE00)/.test(text) || /\uB4E4\uC5B4\uAC08\s*\uC704\uCE58/.test(text)) {
                    var n = i + 1;
                    while (n < paras.length) {
                        var t2 = (paras[n].contents || "").replace(/[\r\n]+$/, "");
                        if (!/^\s*$/.test(t2)) {
                            if (S3_BG) paras[n].appliedParagraphStyle = S3_BG;
                            break;
                        }
                        n++;
                    }
                }

                // Korean + ? → 번호
                if (/[\uAC00-\uD7A3]\?/.test(text)) {
                    if (S3_NUM) paras[i].appliedParagraphStyle = S3_NUM;
                    continue;
                }
                // ①~⑤ 단락 첫 시작에 올 경우만 → 선지
                if (/^[\u2460\u2461\u2462\u2463\u2464]/.test(text)) {
                    if (S3_CHOICE) paras[i].appliedParagraphStyle = S3_CHOICE;
                    continue;
                }
                // "다음 글을 읽고 물음에" 만 매칭 (다른 형태는 번호로)
                if (text.indexOf("\uB2E4\uC74C \uAE00\uC744 \uC77D\uACE0 \uBB3C\uC74C\uC5D0") !== -1) {
                    if (S3_INTRO) paras[i].appliedParagraphStyle = S3_INTRO;
                    continue;
                }
                // "시오" → 번호
                if (text.indexOf("\uC2DC\uC624") !== -1) {
                    if (S3_NUM) paras[i].appliedParagraphStyle = S3_NUM;
                    continue;
                }
                // * → 영단어 (보기/조건보다 먼저)
                if (text.indexOf("*") !== -1) {
                    if (S3_WORD) paras[i].appliedParagraphStyle = S3_WORD;
                    continue;
                }
                // (A) + space or tab → 선지
                if (/\(A\)\s{2,}/.test(text) || /\(A\)\t/.test(text)) {
                    if (S3_CHOICE) paras[i].appliedParagraphStyle = S3_CHOICE;
                    continue;
                }
            }

            // ── 6. 보기 적용 (조건보다 먼저) ─────────────────────────────────
            // <보기> 다음에 한글이 오면 보기 스타일 입히지 않음
            paras = story.paragraphs;
            for (var k = 0; k < paras.length; k++) {
                var txtV = (paras[k].contents || "").replace(/[\r\n]+$/, "");
                var txtVTrim = txtV.replace(/^[\s\u3000]+/, "").replace(/[\s\u3000]+$/, "");
                if (paras[k].appliedParagraphStyle == S3_NUM) continue;
                var isView = false;
                // (1) 문단 시작에 <보기> — 단, <보기> 뒤에 한글이 오면 제외
                if (/^[\s\u3000]*<\uBCF4\uAE30>/.test(txtV)) {
                    var afterTag = txtV.replace(/^[\s\u3000]*<\uBCF4\uAE30>\s*/, "");
                    // <보기> 뒤 내용이 없거나 영문/특수문자만이면 보기
                    if (!/[\uAC00-\uD7A3]/.test(afterTag)) {
                        isView = true;
                    }
                }
                // (2) 독립 "보기" (트림 후 정확히 "보기")
                if (!isView && txtVTrim === "\uBCF4\uAE30") isView = true;
                if (isView && S3_VIEW) paras[k].appliedParagraphStyle = S3_VIEW;
            }

            // ── 7. 조건 적용 (보기 뒤) ──────────────────────────────────────
            paras = story.paragraphs;
            for (var k2 = 0; k2 < paras.length; k2++) {
                var txtC = (paras[k2].contents || "").replace(/[\r\n]+$/, "");
                var txtCTrim = txtC.replace(/^[\s\u3000]+/, "").replace(/[\s\u3000]+$/, "");
                if (txtCTrim === "<\uC870\uAC74>" || /^[\s\u3000]*<\uC870\uAC74>\s*$/.test(txtC)) {
                    if (S3_COND) paras[k2].appliedParagraphStyle = S3_COND;
                }
            }

            // ── 7.5. 발문 블록 단위 의미 분류: "배경(컨텍스트)" 단락 결정 ──────
            // 각 발문(S3_NUM)을 시작점으로 하나의 "문제 블록"이라 보고, 첫 비빈 단락 X와
            // 그 다음 비빈 단락 Y를 검사한다.
            //   - Y가 "(A)"로 시작 → 순서배열 패턴 → X는 씨앗문장(배경)
            //   - 발문에 "주어진 문장/글" 또는 "들어갈 위치" → 문장삽입 패턴 → X는 주어진 문장(배경)
            // 이 한 곳에서 모든 "배경" 결정. 일반 발문(주제/요지/빈칸 등)은 Y가 ①②③④⑤이므로
            // (A) 검사가 안 걸려 X는 지문(DEFAULT)으로 유지된다.
            paras = story.paragraphs;
            for (var bgi = 0; bgi < paras.length; bgi++) {
                if (paras[bgi].appliedParagraphStyle != S3_NUM) continue;
                var qText = (paras[bgi].contents || "").replace(/[\r\n]+$/, "");
                // 다음 발문 또는 스토리 끝까지가 한 블록
                var blockEnd = paras.length;
                for (var bj = bgi + 1; bj < paras.length; bj++) {
                    if (paras[bj].appliedParagraphStyle == S3_NUM) { blockEnd = bj; break; }
                }
                // X = 발문 다음 첫 비빈 단락 (지문번호 코드 마커 {YYMMNN}/{1234} 건너뜀)
                var xi = bgi + 1;
                while (xi < blockEnd) {
                    var xt = (paras[xi].contents || "").replace(/[\r\n]+$/, "")
                              .replace(/^[\s　]+|[\s　]+$/g, "");
                    if (xt && !/^\{\d{4,6}\}$/.test(xt)) break;
                    xi++;
                }
                if (xi >= blockEnd) continue;
                if (paras[xi].appliedParagraphStyle != S3_DEFAULT) continue; // 이미 다른 분류됨
                // Y = X 다음 비빈 단락
                var yi = xi + 1;
                while (yi < blockEnd) {
                    var yt = (paras[yi].contents || "").replace(/[\r\n]+$/, "")
                              .replace(/^[\s　]+|[\s　]+$/g, "");
                    if (yt) break;
                    yi++;
                }
                var isContext = false;
                // 패턴 1: 순서배열 — Y가 "(A) <영문단어>"로 시작
                // (A) 다음에 알파벳 단어가 와야 진짜 순서배열의 구성요소.
                // "(A)     (B)       (C)" 같은 어법 네모 헤더(공백/괄호 연속)는 제외.
                if (yi < blockEnd) {
                    var yt2 = (paras[yi].contents || "").replace(/[\r\n]+$/, "")
                              .replace(/^[\s　]+/, "");
                    if (/^\(A\)\s+[A-Za-z]/.test(yt2)) isContext = true;
                }
                // 패턴 2: 문장삽입 — 발문에 "주어진 문장/글" / "들어갈 위치"
                if (!isContext && (/주어진\s*(문장|글)/.test(qText) || /들어갈\s*위치/.test(qText))) {
                    isContext = true;
                }
                if (isContext && S3_BG) {
                    try { paras[xi].appliedParagraphStyle = S3_BG; } catch(_){}
                }
            }

            // ── 8. 보기 propagation (먼저, 쉼표 3개 이상, 한글 포함 시 중단) ──
            paras = story.paragraphs;
            for (var m = 0; m < paras.length - 1; m++) {
                if (paras[m].appliedParagraphStyle == S3_VIEW) {
                    var n3 = m + 1;
                    while (n3 < paras.length) {
                        var p3 = paras[n3];
                        if (p3.appliedParagraphStyle != S3_DEFAULT) break;
                        var p3Txt = (p3.contents || "").replace(/[\r\n]+$/, "");
                        // 2.5에서 swap된 본문(ZWSP 마커)은 보기 propagation 대상 아님
                        if (p3Txt.charAt(0) === "​") break;
                        // 한글이 포함된 단락은 보기로 변경하지 않음
                        if (/[\uAC00-\uD7A3]/.test(p3Txt)) break;
                        // 슬래시 포함 또는 쉼표 3개 이상이면 보기 계속
                        var hasSlash = p3Txt.indexOf("/") !== -1;
                        var commaCount = 0;
                        for (var cci = 0; cci < p3Txt.length; cci++) { if (p3Txt.charAt(cci) === ',') commaCount++; }
                        if (hasSlash || commaCount >= 3) {
                            if (S3_VIEW) p3.appliedParagraphStyle = S3_VIEW;
                            n3++;
                        } else {
                            break;
                        }
                    }
                }
            }

            // ── 8.5. swap 본문 마커(ZWSP) 제거 ──────────────────────────────
            grepChange(story, "\\x{200B}", "");

            // ── 9. 조건 propagation (보기 뒤) ────────────────────────────────
            paras = story.paragraphs;
            for (var m2 = 0; m2 < paras.length - 1; m2++) {
                if (paras[m2].appliedParagraphStyle == S3_COND) {
                    var n2 = m2 + 1;
                    while (n2 < paras.length) {
                        var p2 = paras[n2];
                        var p2Sty = p2.appliedParagraphStyle;
                        // DEFAULT \ub610\ub294 (\uc624\ubd84\ub958\ub41c) CHOICE \ub9cc \uc7ac\ubd84\ub958 \ub300\uc0c1.
                        // ExtendScript\uc758 \uac1d\uccb4 \ube44\uad50\uac00 reference \uc77c\uce58\ub9cc \ubcf4\uc9c0 \uc54a\uc744 \ub54c\ub97c \ub300\ube44,
                        // name \uae30\ubc18 fallback \ube44\uad50 \ucd94\uac00.
                        var isDefault = (p2Sty === S3_DEFAULT) ||
                                        (p2Sty && S3_DEFAULT && p2Sty.name === S3_DEFAULT.name);
                        var isChoice  = (p2Sty === S3_CHOICE) ||
                                        (p2Sty && S3_CHOICE && p2Sty.name === S3_CHOICE.name);
                        if (!isDefault && !isChoice) break;
                        var pTrim = (p2.contents || "").replace(/[\r\n]+$/, "").replace(/^[\s\u3000]+/, "");
                        if (!/^(\u2022|\u2981|-|<|\d+\.|[\u2460-\u2473]|\(\d+\))/.test(pTrim)) break;
                        if (S3_COND) p2.appliedParagraphStyle = S3_COND;
                        n2++;
                    }
                }
            }

            // ── 10. "숫자. " 제거 (번호 단락) ───────────────────────────────
            if (S3_NUM) {
                resetGrep();
                app.findGrepPreferences.appliedParagraphStyle = S3_NUM;
                app.findGrepPreferences.findWhat = "^\\d+\\.\\s";
                app.changeGrepPreferences.changeTo = "";
                story.changeGrep();
                resetGrep();
            }

            // ── 11. 화살표 단독 단락 → 다음 배경 + 삭제 ─────────────────────
            // 화살표 글리프: ⬇(2B07) ⇩(21E9) ↓(2193) ↘(2198) ⇓(21D3) ⬇️ 등
            paras = story.paragraphs;
            for (var ai = paras.length - 1; ai >= 0; ai--) {
                var rawA = (paras[ai].contents || "").replace(/[\r\n]+$/, "").replace(/^\s+|\s+$/g, "");
                // 화살표 계열 글리프만 단독으로 있는 단락
                if (/^[\u2B07\u21E9\u2193\u2198\u21D3\u2B06\u2191\u21E7\u21D1\uFE0F]+$/.test(rawA)) {
                    // 다음 단락에 배경 적용
                    if (ai + 1 < paras.length && S3_BG) {
                        paras[ai + 1].appliedParagraphStyle = S3_BG;
                    }
                    // 화살표 단락 삭제 (내용 + 리턴)
                    try {
                        paras[ai].contents = "";
                    } catch(_){}
                }
            }
            // 삭제 후 남은 빈 리턴 정리
            grepChange(story, "\\r{2,}", "\\r");

            // ── 12. 요약+빈칸 발문 → 빈칸(___) 있는 단락에 배경 (답란 제외) ──
            // "요약"과 "빈칸"이 동시에 들어간 발문일 때만 적용
            // <조건> 이전까지만 (답란 (A):___ 같은 건 <조건> 이후이므로 제외)
            paras = story.paragraphs;
            for (var si = 0; si < paras.length; si++) {
                if (paras[si].appliedParagraphStyle != S3_NUM) continue;
                var sTxt = (paras[si].contents || "").replace(/[\r\n]+$/, "");
                if (sTxt.indexOf("\uC694\uC57D") !== -1 && sTxt.indexOf("\uBE48\uCE78") !== -1) {
                    for (var sn = si + 1; sn < paras.length; sn++) {
                        var snSty = paras[sn].appliedParagraphStyle;
                        if (snSty == S3_NUM || snSty == S3_INTRO) break;
                        if (snSty == S3_COND || snSty == S3_VIEW) break; // <조건>/<보기> 만나면 중단
                        var snTxt = (paras[sn].contents || "").replace(/[\r\n]+$/, "");
                        if (/^\s*\{\d{6}\}\s*$/.test(snTxt)) break;
                        if (/_{3,}/.test(snTxt)) {
                            if (S3_BG) paras[sn].appliedParagraphStyle = S3_BG;
                        }
                    }
                }
            }

            // ── 13. 배경 다음 단락에 ①~⑤ → restore default ─────────────────
            paras = story.paragraphs;
            for (var bi = 0; bi < paras.length - 1; bi++) {
                if (paras[bi].appliedParagraphStyle == S3_BG) {
                    var nextText = (paras[bi + 1].contents || "").replace(/[\r\n]+$/, "");
                    if (/^[\u2460\u2461\u2462\u2463\u2464]/.test(nextText)) {
                        if (S3_DEFAULT) paras[bi + 1].appliedParagraphStyle = S3_DEFAULT;
                    }
                }
            }

            // ── 14. "다음 밑줄 친 부분 중" → next paragraph to default ───────
            paras = story.paragraphs;
            for (var ci = 0; ci < paras.length - 1; ci++) {
                if (paras[ci].appliedParagraphStyle == S3_NUM) {
                    var curText = (paras[ci].contents || "").replace(/[\r\n]+$/, "");
                    if (curText.indexOf("\uB2E4\uC74C \uBC11\uC904 \uCE5C \uBD80\uBD84 \uC911") !== -1) {
                        if (S3_DEFAULT) paras[ci + 1].appliedParagraphStyle = S3_DEFAULT;
                    }
                }
            }

            // ── 15. 조건 + <조건> marker → propagate ────────────────────────
            paras = story.paragraphs;
            for (var di = 0; di < paras.length - 1; di++) {
                if (paras[di].appliedParagraphStyle != S3_COND) continue;
                var headTxt = (paras[di].contents || "").replace(/[\r\n]+$/, "");
                if (headTxt.indexOf("<\uC870\uAC74>") === -1) continue;
                if (paras[di + 1].appliedParagraphStyle != S3_DEFAULT) continue;
                var startJ = di + 1;
                var endJ = startJ;
                while (endJ < paras.length && paras[endJ].appliedParagraphStyle == S3_DEFAULT) endJ++;
                for (var jj = startJ; jj < endJ; jj++) {
                    var bodyTxt = (paras[jj].contents || "").replace(/[\r\n]+$/, "");
                    if (/^[\s\u3000\t]*\d+\.\s*/.test(bodyTxt) || /^[\s\u3000\t]*[\u2022\u2981]/.test(bodyTxt)) {
                        if (S3_COND) paras[jj].appliedParagraphStyle = S3_COND;
                    }
                }
            }

            // ── 16. <조건> 뒤 '것'으로 끝나는 단락 → 조건 ──────────────────
            // 다음 번호/선지 스타일 만나기 전까지 연속 적용
            paras = story.paragraphs;
            for (var cdi = 0; cdi < paras.length - 1; cdi++) {
                if (paras[cdi].appliedParagraphStyle != S3_COND) continue;
                var cdTxt = (paras[cdi].contents || "").replace(/[\r\n]+$/, "");
                var cdTrim = cdTxt.replace(/^[\s\u3000]+/, "").replace(/[\s\u3000]+$/, "");
                if (cdTrim !== "<\uC870\uAC74>" && !/^[\s\u3000]*<\uC870\uAC74>\s*$/.test(cdTxt)) continue;
                var cdj = cdi + 1;
                while (cdj < paras.length) {
                    var cdnSty = paras[cdj].appliedParagraphStyle;
                    // 번호, 선지, 보기, 배경 등 이미 다른 스타일이면 중단
                    // 영단어(S3_WORD)는 제외 — <조건> 뒤 *로 시작하는 조건 내용이 영단어로 잘못 분류된 것
                    if (cdnSty == S3_NUM || cdnSty == S3_CHOICE || cdnSty == S3_INTRO ||
                        cdnSty == S3_VIEW || cdnSty == S3_BG) break;
                    var cdnTxt = (paras[cdj].contents || "").replace(/[\r\n]+$/, "").replace(/^[\s\u3000]+/, "").replace(/[\s\u3000]+$/, "");
                    if (/^\s*\{\d{6}\}\s*$/.test(cdnTxt)) break; // 지문번호면 중단
                    if (cdnTxt === '') { cdj++; continue; }
                    // '것'으로 끝나거나 '필요시'로 시작하거나 숫자/불릿/한글 조건문
                    if (/\uAC83$/.test(cdnTxt) || /^\uD544\uC694\uC2DC/.test(cdnTxt) ||
                        /^\uB2E8,/.test(cdnTxt) ||  // "단,"으로 시작
                        /^\d+[\.\)]/.test(cdnTxt) || /^[\u2022\u2981\-]/.test(cdnTxt) ||
                        /[\uAC00-\uD7A3]/.test(cdnTxt)) {  // 한글 포함 시 조건으로 포함
                        if (S3_COND) { try { paras[cdj].appliedParagraphStyle = S3_COND; } catch(_){} }
                        cdj++;
                    } else {
                        break;
                    }
                }
            }

            // ── 17. "우리말:" → 배경 ────────────────────────────────────────
            paras = story.paragraphs;
            for (var ui = 0; ui < paras.length; ui++) {
                var uTxt = (paras[ui].contents || "").replace(/[\r\n]+$/, "");
                if (/\uC6B0\uB9AC\uB9D0[\s\u3000]*:/.test(uTxt)) {
                    if (S3_BG) paras[ui].appliedParagraphStyle = S3_BG;
                }
            }

            // ── 18. 흐름과 관계 / 어법상 틀린 것 ─────────────────────────────
            paras = story.paragraphs;
            var S3_PASSAGE_NOUL = null;
            var S3_PASSAGE = null;
            try {
                var sg3 = doc.paragraphStyleGroups.itemByName("STEP 03");
                if (sg3 && sg3.isValid) {
                    var _names = sg3.paragraphStyles.everyItem().name;
                    for (var _ni = 0; _ni < _names.length; _ni++) {
                        if (_names[_ni].indexOf("\uBC11\uC904\uC81C\uAC70") !== -1) {
                            S3_PASSAGE_NOUL = sg3.paragraphStyles.itemByName(_names[_ni]);
                        }
                        if (_names[_ni].indexOf("\uC2E4\uC804 \uBB38\uC81C \uC9C0\uBB38 \uC62C\uB9BC\uD3EC\uC2A4") !== -1 && _names[_ni].indexOf("\uBC11\uC904") === -1) {
                            S3_PASSAGE = sg3.paragraphStyles.itemByName(_names[_ni]);
                        }
                    }
                }
            } catch(_){}

            for (var hi = 0; hi < paras.length - 1; hi++) {
                var hTxt = (paras[hi].contents || "").replace(/[\r\n]+$/, "");
                if (/\uD750\uB984\uACFC\s*\uAD00\uACC4/.test(hTxt) && S3_PASSAGE_NOUL && S3_PASSAGE_NOUL.isValid) {
                    var hn = hi + 1;
                    while (hn < paras.length) {
                        var hnt = (paras[hn].contents || "").replace(/[\r\n]+$/, "");
                        if (!/^\s*$/.test(hnt)) { try { paras[hn].appliedParagraphStyle = S3_PASSAGE_NOUL; } catch(_){} break; }
                        hn++;
                    }
                }
                if (/\uBC11\uC904\s*\uCE5C\s*\uBD80\uBD84\s*\uC911,?\s*\uC5B4\uBC95\uC0C1\s*\uD2C0\uB9B0\s*\uAC83/.test(hTxt) && S3_PASSAGE && S3_PASSAGE.isValid) {
                    if (hi + 1 < paras.length) {
                        var nxt = paras[hi + 1];
                        if (nxt.appliedParagraphStyle == S3_CHOICE) {
                            try { nxt.appliedParagraphStyle = S3_PASSAGE; } catch(_){}
                        }
                    }
                }
            }

            // ── 19. {YYMMNN} code paragraphs → [기본 단락] ──────────────────
            paras = story.paragraphs;
            for (var fi = 0; fi < paras.length; fi++) {
                var fTxt = (paras[fi].contents || "").replace(/[\r\n]+$/, "");
                if (/^\s*\{\d{6}\}\s*$/.test(fTxt)) {
                    paras[fi].appliedParagraphStyle = BASIC_PARA;
                }
            }

            // 밑줄은 별도 후처리 스크립트(workbook_underline.jsx)에서 적용

            // 분리된 짤지문 스토리만 character fillColor 강제 검정 적용
            // (메인 스토리는 기존 character override가 본문 색을 유지하지만, 분리된 새 스토리는
            //  paragraph style의 character defaults(=paper)가 그대로 적용되어 텍스트가 안 보임)
            if (isShortStory) {
                try {
                    var __blk = doc.swatches.itemByName("Black");
                    if (__blk && __blk.isValid && story.characters.length > 0) {
                        story.characters.itemByRange(0, story.characters.length - 1).fillColor = __blk;
                    }
                } catch(_) {}
            }
         } catch(innerErr) {
            var ef = new File("/tmp/workbook_debug.txt");
            ef.open("a"); ef.encoding = "UTF-8";
            ef.writeln("STEP3_INNER_ERROR: " + innerErr.message + " line:" + innerErr.line);
            ef.close();
         }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "STEP3");

        addLog("STEP3 완료");
        stepsDone++;
    }

    // ========================================================================
    // 13. STEP3 PAGE LAYOUT — left-page start, M-master for empty right pages
    // ========================================================================
    function adjustStep3Pages(story) {
        if (!story || !story.isValid) return;
        addLog("STEP3 페이지 레이아웃 조정 시작");

        // story.contents = fullText 이후이므로 기존 프레임브레이크 없음
        try { story.recompose(); } catch(_){}

        // Find {YYMMNN} code paragraphs
        var paras = story.paragraphs;
        var codeIndices = [];
        for (var i = 0; i < paras.length; i++) {
            var txt = (paras[i].contents || "").replace(/[\r\n]+$/, "");
            if (/^\s*\{\d{6}\}\s*$/.test(txt)) {
                codeIndices.push(i);
            }
        }

        addLog("STEP3 지문번호 " + codeIndices.length + "개 발견");

        // {YYMMNN} 지문번호 앞에만 프레임브레이크 삽입 (첫 번째 제외, 역순)
        for (var ci = codeIndices.length - 1; ci >= 1; ci--) {
            paras = story.paragraphs;
            var cIdx = codeIndices[ci];
            if (cIdx >= paras.length) continue;
            try {
                paras[cIdx].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
            } catch(_){}
        }
        try { story.recompose(); } catch(_){}

        // 지문번호가 짝수페이지(LEFT) 첫 프레임에서 시작하도록 보장
        // 정순(forward) 처리: 앞에서부터 하나씩, 매번 recompose 후 위치 확인
        var containers = story.textContainers;

        function checkCodePosition(codeVal) {
            // 코드의 현재 위치 확인: {페이지, 짝수여부, 첫프레임여부}
            var paras2 = story.paragraphs;
            for (var p = 0; p < paras2.length; p++) {
                if ((paras2[p].contents || "").indexOf("{" + codeVal + "}") !== -1) {
                    var tf = null, pg = null;
                    try { tf = paras2[p].parentTextFrames[0]; pg = tf.parentPage; } catch(_){}
                    if (!tf || !pg) return { found: false };
                    var pn = parseInt(pg.name, 10);
                    var isLeft = (!isNaN(pn) && pn % 2 === 0);
                    var isFirst = true;
                    try {
                        var pgTFs = pg.textFrames;
                        for (var t = 0; t < pgTFs.length; t++) {
                            if (pgTFs[t].parentStory === story && pgTFs[t].geometricBounds[1] < tf.geometricBounds[1] - 1) {
                                isFirst = false; break;
                            }
                        }
                    } catch(_){}
                    return { found: true, paraIdx: p, pageNum: pn, isLeft: isLeft, isFirst: isFirst, ok: isLeft && isFirst };
                }
            }
            return { found: false };
        }

        function insertFBBeforeCode(codeVal) {
            var paras2 = story.paragraphs;
            for (var p = 0; p < paras2.length; p++) {
                if ((paras2[p].contents || "").indexOf("{" + codeVal + "}") !== -1) {
                    paras2[p].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
                    return true;
                }
            }
            return false;
        }

        // 코드값 목록 수집
        var codeValues = [];
        paras = story.paragraphs;
        for (var cv = 0; cv < paras.length; cv++) {
            var cvTxt = (paras[cv].contents || "").replace(/[\r\n]+$/, "");
            var cvM = cvTxt.match(/^\s*\{(\d{6})\}\s*$/);
            if (cvM) codeValues.push(cvM[1]);
        }

        // 정순 처리 (첫 번째는 건너뜀 — 이미 스토리 시작)
        for (var ci2 = 1; ci2 < codeValues.length; ci2++) {
            var cv2 = codeValues[ci2];
            // 최대 12회 프레임브레이크 추가 시도
            for (var tryN = 0; tryN < 12; tryN++) {
                try { story.recompose(); } catch(_){}
                var pos = checkCodePosition(cv2);
                if (!pos.found) break;
                if (pos.ok) break; // 짝수페이지 + 첫 프레임 → 완료
                if (!insertFBBeforeCode(cv2)) break;
            }
        }

        // ── 오버플로우 해결: 기존 STEP3 페이지를 통째로 복제 후 메인 프레임만 연결 ──
        // 페이지 추가 + 마스터 override 방식은 페이지 헤더/번호 영역까지 깨지므로 페이지 복제 사용.
        // 복제된 페이지는 마스터/페이지헤더/메인콘텐츠 프레임이 모두 동일 위치/크기로 복사됨.
        try { story.recompose(); } catch(_){}

        var maxOverflowTries = 20;
        for (var ofTry = 0; ofTry < maxOverflowTries; ofTry++) {
            var lastTF = story.textContainers[story.textContainers.length - 1];
            if (!lastTF.overflows) break;

            addLog("STEP3 오버플로우 감지 — 페이지 복제 (시도 " + (ofTry + 1) + ")");

            var lastPage = null;
            try { lastPage = lastTF.parentPage; } catch(_){}
            if (!lastPage) {
                addLog("마지막 페이지 식별 실패");
                break;
            }

            // 마지막 STEP3 페이지를 복제 (마스터 + 모든 항목 그대로 복사)
            var newPage = null;
            try {
                newPage = lastPage.duplicate(LocationOptions.AFTER, lastPage);
            } catch(e) {
                addLog("페이지 복제 실패: " + e.message);
                break;
            }

            if (newPage) {
                // 복제된 페이지에서 메인 콘텐츠 프레임 식별 (가장 큰 텍스트 프레임)
                // 페이지 헤더/번호 같은 작은 프레임은 자동 제외
                var newTFs = newPage.textFrames;
                var bestTF = null;
                var bestArea = 0;
                for (var nt = 0; nt < newTFs.length; nt++) {
                    try {
                        var b = newTFs[nt].geometricBounds;
                        var area = (b[3] - b[1]) * (b[2] - b[0]);
                        if (area > bestArea) {
                            bestArea = area;
                            bestTF = newTFs[nt];
                        }
                    } catch(_){}
                }

                if (bestTF) {
                    // 메인 콘텐츠 프레임의 복제된 텍스트 비우고 STEP3 스토리에 연결
                    try { bestTF.parentStory.contents = ""; } catch(_){}
                    try { lastTF.nextTextFrame = bestTF; } catch(_){}
                } else {
                    addLog("복제 페이지에서 메인 프레임 식별 실패");
                    break;
                }
            }

            try { story.recompose(); } catch(_){}
        }

        // 오버플로우 최종 확인
        try {
            var finalTF = story.textContainers[story.textContainers.length - 1];
            if (finalTF.overflows) {
                addLog("STEP3 경고: 오버플로우 미해결");
            } else {
                addLog("STEP3 오버플로우 없음");
            }
        } catch(_){}

        // ── 빈 페이지에 M 마스터 적용 ────────────────────────────────────
        // Step3 영역 내 모든 빈 페이지(내용 없는 페이지)에 M 마스터
        if (MASTER_M) {
            try { story.recompose(); } catch(_){}
            var allContainers = story.textContainers;
            if (allContainers.length > 0) {
                var firstPg = null, lastPg = null;
                try { firstPg = allContainers[0].parentPage; } catch(_){}
                try { lastPg = allContainers[allContainers.length - 1].parentPage; } catch(_){}
                if (firstPg && lastPg) {
                    var startOff = firstPg.documentOffset;
                    var endOff = lastPg.documentOffset;
                    for (var mp = startOff; mp <= endOff; mp++) {
                        try {
                            var pg = doc.pages[mp];
                            // 이 페이지의 Step3 스토리 프레임에 내용이 있는지 확인
                            var hasContent = false;
                            var pgTFs = pg.textFrames;
                            for (var pt = 0; pt < pgTFs.length; pt++) {
                                if (pgTFs[pt].parentStory === story) {
                                    var c = (pgTFs[pt].contents || "").replace(/[\s\r\n\uFFFC]+/g, "");
                                    if (c.length > 0) { hasContent = true; break; }
                                }
                            }
                            if (!hasContent) {
                                try { pg.appliedMaster = MASTER_M; } catch(_){}
                            }
                        } catch(_){}
                    }
                }
            }
        }

        addLog("STEP3 페이지 레이아웃 조정 완료");
    }

    // ========================================================================
    // 14. STORY MAPPING — map step keys to stories
    // ========================================================================
    function mapStepToStory(stepKey) {
        // Page-based story mapping (from template analysis)
        // Each STEP has a known start page and marker text
        // settings.stepStoryMap\uC774 \uC788\uC73C\uBA74 \uADF8\uAC78 \uC6B0\uC120 \uC0AC\uC6A9 (EBS \uB4F1 \uB2E4\uB978 \uC6D0\uBCF8 .indd\uC6A9)
        var stepConfig = settings.stepStoryMap || {
            "step1_a1":   { page: "4",   marker: "\uC5B4\uD718 \uC120\uD0DD 1" }, // 어휘 선택 1
            "step1_a1_2": { page: "13",  marker: "\uC5B4\uD718 \uC120\uD0DD 2" }, // 어휘 선택 2
            "step1_a2":   { page: "22",  marker: "\uBCF8\uBB38 O/X" },             // 본문 O/X
            "step1_b1": { page: "40",  marker: "\uBCF8\uBB38 \uC815\uB9AC" },    // 본문 정리
            "step1_b2": { page: "58",  marker: "\uB0B4\uC6A9 \uC885\uD569" },    // 내용 종합
            "step1_c1": { page: "76",  marker: "\uBB38\uC7A5 \uBC30\uC5F4" },    // 문장 배열
            "step1_c2": { page: "94",  marker: "\uBE48\uCE78 \uC5B4\uD718" },    // 빈칸 어휘
            "step2_a1":     { page: "114", marker: "\uC5B4\uBC95 \uC120\uD0DD" },    // 어법 선택
            "step2_a1_btm": { page: "114", marker: "\uC5B4\uBC95 \uC120\uD0DD", rank: 2 }, // 어법 선택 하단 (2nd story on p114)
            "step2_b1": { page: "132", marker: "\uC5B4\uBC95 O/X" },             // 어법 O/X
            "step2_c1": { page: "150", marker: "\uBE48\uCE78 \uC5B4\uBC95" },    // 빈칸 어법
            "step2_c2": { page: "168", marker: "\uC601\uC791 \uBC30\uC5F4" }     // 영작 배열
        };

        if (stepKey === "step3") {
            // step3 마스터 prefix는 settings.stepStoryMap.step3.master 우선 (수능특강 분석/문제 분리용)
            var step3Cfg = settings.stepStoryMap && settings.stepStoryMap.step3;
            var step3Master = (step3Cfg && step3Cfg.master) || "O";
            return findMainStoryOnMaster(step3Master);
        }

        var cfg = stepConfig[stepKey];
        if (!cfg) return null;

        // 1차: 마커 텍스트로 페이지 검색 — 페이지 번호 변동에 강건 (학교별 indd 등)
        // 2차: cfg.page 번호로 fallback — 기존 동작 호환
        var targetPage = null;
        if (cfg.marker) {
            var allPages = doc.pages;
            for (var pp = 0; pp < allPages.length; pp++) {
                var pTfs = allPages[pp].textFrames;
                for (var pt = 0; pt < pTfs.length; pt++) {
                    var pContent = "";
                    try { pContent = pTfs[pt].contents; } catch(_) { continue; }
                    if (typeof pContent !== "string") continue;
                    if (pContent.indexOf(cfg.marker) !== -1) {
                        targetPage = allPages[pp];
                        break;
                    }
                }
                if (targetPage) break;
            }
        }
        if (!targetPage || !targetPage.isValid) {
            try { targetPage = doc.pages.itemByName(cfg.page); } catch(_){}
        }
        if (!targetPage || !targetPage.isValid) return null;

        // 매핑된 페이지 번호를 로그에 (디버그용)
        var foundPageName = "?";
        try { foundPageName = targetPage.name; } catch(_){}

        var tfs = targetPage.textFrames;
        var candidates = []; // collect {story, score} pairs
        var seen = {};
        for (var t = 0; t < tfs.length; t++) {
            var story = tfs[t].parentStory;
            if (seen[story.id]) continue;
            seen[story.id] = true;
            var frames = story.textContainers.length;
            if (frames <= 1) continue; // skip label stories (1 frame)
            // Prefer story whose FIRST frame is on this page (not a spillover from earlier)
            var firstFramePage = "?";
            try { firstFramePage = story.textContainers[0].parentPage.name; } catch(_){}
            var isOwnStory = (firstFramePage === foundPageName);
            // Score: own story gets huge bonus, then frame count
            var score = (isOwnStory ? 10000 : 0) + frames;
            candidates.push({ story: story, score: score });
        }
        // Sort by score descending
        candidates.sort(function(a, b) { return b.score - a.score; });
        // rank=1 (default) = largest, rank=2 = second largest, etc.
        var rank = cfg.rank || 1;
        if (candidates.length >= rank) {
            return candidates[rank - 1].story;
        }
        return candidates.length > 0 ? candidates[0].story : null;
    }

    // 짤지문 영역 분리: 메인 step3 스토리에서 "짤지문" 마커 페이지 다음의 첫 프레임을
    // unthread하여 별도 스토리로 만든다. 짤지문 마커가 없거나 다음 페이지에 해당 스토리
    // 프레임이 없으면 null 반환(= EBS/수능특강 등 기존 동작 유지).
    function splitStep3ShortStory(mainStory) {
        if (!mainStory || !mainStory.isValid) return null;
        var shortMarkerPage = null;
        var allPages = doc.pages;
        for (var p = 0; p < allPages.length; p++) {
            var pTfs = allPages[p].textFrames;
            for (var t = 0; t < pTfs.length; t++) {
                var c = "";
                try { c = pTfs[t].contents; } catch(_) { continue; }
                if (typeof c !== "string") continue;
                if (c.indexOf("짤지문") !== -1) {  // "짤지문"
                    shortMarkerPage = allPages[p];
                    break;
                }
            }
            if (shortMarkerPage) break;
        }
        if (!shortMarkerPage) return null;

        var markerOffset = shortMarkerPage.documentOffset;
        if (markerOffset + 1 >= allPages.length) return null;
        var nextPage = allPages[markerOffset + 1];

        var containers = mainStory.textContainers;
        var splitFrame = null;
        for (var cc = 0; cc < containers.length; cc++) {
            try {
                if (containers[cc].parentPage === nextPage) {
                    splitFrame = containers[cc];
                    break;
                }
            } catch(_) {}
        }
        if (!splitFrame) return null;

        try {
            splitFrame.previousTextFrame = NothingEnum.NOTHING;
        } catch(e) {
            addLog("step3 짤지문 분리 실패: " + e.message);
            return null;
        }
        addLog("step3 짤지문 영역 분리 성공: p" + nextPage.name);
        return splitFrame.parentStory;
    }

    // ========================================================================
    // 15. MAIN EXECUTION PIPELINE
    // ========================================================================
    addLog("파이프라인 실행 시작");

    // ── STEP 3 first (p178+, farthest back) — 텍스트/스타일만, 프레임브레이크는 나중에
    var step3Data = loadStepData("step3");
    var step3Story = null;
    var step3ShortStory = null;
    if (excludeSet["step3"]) {
        addLog("step3: 사용자 제외, 건너뜀");
        step3Data = null;
    }
    if (step3Data) {
        step3Story = mapStepToStory("step3");
        if (step3Story) {
            addLog("step3: 스토리 매핑 성공 (프레임 " + step3Story.textContainers.length + "개)");
            try {
                addLog("STEP3 처리 시작");
                // 짤지문 페이지 분리 일시 비활성화 — 분리 후 본문 character defaults 시각 문제 진단 중.
                // 현재는 기존 동작: normal + short 모두 메인 step3 스토리에 부음 (짤지문이 일반 페이지에 들어감).
                // step3ShortStory = splitStep3ShortStory(step3Story);
                processStep3(step3Story, step3Data, false);
                addLog("STEP3 텍스트/스타일 완료");
                stepsDone++;
            } catch(e) {
                addLog("step3: 오류 — " + e.message);
            }
        } else {
            addLog("step3: 스토리를 찾을 수 없음");
        }
    }

    // ── STEP 1 & 2 in REVERSE order (back-to-front) ────────────────────
    // When text overflows, InDesign links to the NEXT empty frames.
    // By filling from the back first, earlier empty stories stay independent.
    var stepOrder = [
        "step2_c2", "step2_c1", "step2_b1", "step2_a1_btm", "step2_a1",
        "step1_c2", "step1_c1",
        "step1_b2", "step1_b1", "step1_a2", "step1_a1_2", "step1_a1"
    ];

    var processors = {
        "step1_a1": processStep1A1,
        "step1_a1_2": processStep1A1,  // same processor, different story
        "step1_a2": processStep1A2,
        "step1_b1": processStep1B1,
        "step1_b2": processStep1B2,
        "step1_c1": processStep1C1,
        "step1_c2": processStep1C2,
        "step2_a1": processStep2A1,
        "step2_a1_btm": processStep2A1Btm,
        "step2_b1": processStep2B1,
        "step2_c1": processStep2C1,
        "step2_c2": processStep2C2
    };

    // Process STEP 1 & 2
    for (var si = 0; si < stepOrder.length; si++) {
        var stepKey = stepOrder[si];
        if (excludeSet[stepKey]) {
            addLog(stepKey + ": 사용자 제외, 건너뜀");
            continue;
        }
        var stepData = loadStepData(stepKey);

        if (!stepData || !stepData.paragraphs || stepData.paragraphs.length === 0) {
            addLog(stepKey + ": 데이터 없음, 건너뜀");
            continue;
        }

        var story = mapStepToStory(stepKey);
        if (!story) {
            addLog(stepKey + ": 스토리를 찾을 수 없음 (마커: " + stepKey + ")");
            continue;
        }

        addLog(stepKey + ": 스토리 매핑 성공 (프레임 " + story.textContainers.length + "개)");

        try {
            // Debug: write progress to file before each processor
            var dbgF = new File("/tmp/workbook_debug.txt");
            dbgF.open("a"); dbgF.encoding = "UTF-8";
            dbgF.writeln("START: " + stepKey + " at " + new Date().toLocaleTimeString());
            dbgF.close();

            processors[stepKey](story, stepData.paragraphs);

            dbgF.open("a"); dbgF.encoding = "UTF-8";
            dbgF.writeln("DONE: " + stepKey + " at " + new Date().toLocaleTimeString());
            dbgF.close();

            ensureNoOverflow(story);
            shrinkOverflowFrames(story);
            try { story.recompose(); } catch(_){}
        } catch(e) {
            addLog(stepKey + ": 오류 — " + e.message);
            var dbgE = new File("/tmp/workbook_debug.txt");
            dbgE.open("a"); dbgE.encoding = "UTF-8";
            dbgE.writeln("ERROR: " + stepKey + " — " + e.message);
            dbgE.close();
        }
    }

    // ── STEP 3 프레임브레이크 + 페이지 레이아웃 (모든 조판 완료 후) ────────
    if (step3Story) {
        try {
            adjustStep3Pages(step3Story);
            if (step3ShortStory && step3ShortStory.isValid) {
                adjustStep3Pages(step3ShortStory);
            }
            addLog("STEP3 페이지 레이아웃 완료");
        } catch(e) {
            addLog("step3 페이지 레이아웃 오류 — " + e.message);
        }
    }

    // ========================================================================
    // 16. WRITE LOG FILE FIRST (before save, to ensure log is written)
    // ========================================================================
    var endTime = new Date();
    var elapsed = Math.round((endTime - startTime) / 1000);

    addLog("\uC870\uD310 \uC644\uB8CC: " + stepsDone + "\uAC1C STEP \uCC98\uB9AC (" + elapsed + "\uCD08)");

    log.push("");
    log.push("=== \uC870\uD310 \uACB0\uACFC \uC694\uC57D ===");
    log.push("STEP\uC644\uB8CC: " + stepsDone + "\uAC1C");
    log.push("\uC624\uBC84\uD50C\uB85C\uC6B0: " + overflowCount + "\uAC1C");

    var logContent = log.join("\n");
    var logFile = new File(outputDir + "/\uC870\uD310_\uB85C\uADF8.txt");
    logFile.encoding = 'UTF-8';
    logFile.open('w');
    logFile.write(logContent);
    logFile.close();

    addLog("\uB85C\uADF8 \uD30C\uC77C \uC791\uC131 \uC644\uB8CC: " + outputDir + "/\uC870\uD310_\uB85C\uADF8.txt");

    // ========================================================================
    // 16.5. REMOVE EMPTY PAGES (프레임 확장으로 생긴 빈 페이지 삭제)
    // ========================================================================
    try {
        // STEP3 영역 이전의 빈 페이지만 삭제 (STEP3는 adjustStep3Pages에서 관리)
        var step3StartPage = 999;
        try {
            // Step3 스토리의 첫 프레임이 있는 페이지부터 보호
            if (step3Story) {
                var s3containers = step3Story.textContainers;
                if (s3containers.length > 0) {
                    var s3pg = s3containers[0].parentPage;
                    if (s3pg) step3StartPage = s3pg.documentOffset;
                }
            }
        } catch(_){}

        for (var dp = doc.pages.length - 1; dp >= 0; dp--) {
            if (dp >= step3StartPage) continue; // STEP3 영역 건너뛰기
            var pg = doc.pages[dp];
            var tfs = pg.textFrames;
            var hasContent = false;
            for (var tf = 0; tf < tfs.length; tf++) {
                var c = (tfs[tf].contents || "").replace(/[\s\r\n\uFFFC]+/g, "");
                if (c.length > 0) { hasContent = true; break; }
            }
            if (!hasContent && tfs.length > 0) {
                // 빈 페이지지만 마스터 프레임만 있는 경우는 건너뛰기
                var hasLocalFrame = false;
                for (var tf2 = 0; tf2 < tfs.length; tf2++) {
                    try {
                        if (tfs[tf2].parentStory.textContainers.length > 1) { hasLocalFrame = true; break; }
                    } catch(_){}
                }
                if (hasLocalFrame) {
                    try { pg.remove(); addLog("빈 페이지 삭제: p" + (dp + 1)); } catch(_){}
                }
            }
        }
    } catch(_){}

    // ========================================================================
    // 16.7. UPDATE DIVIDER PAGE TEXT (간지 텍스트 업데이트)
    // ========================================================================
    try {
        // 간지 페이지: 마스터 [None], right-side, 텍스트프레임 1개
        // 1단락: "고2 모의고사" or "공통영어1 YBM(박)"
        // 2단락: "26년 3월" or "1과"
        var line1, line2;
        if (workbookType === "\uAD50\uACFC\uC11C") {
            // 교과서: subject + publisher / lesson
            line1 = tbSubject + " " + tbPublisher;
            line2 = tbLesson;
        } else {
            // 모의고사: 고N 모의고사 / YY년 MM월
            line1 = "\uACE0" + grade + " \uBAA8\uC758\uACE0\uC0AC";
            line2 = year + "\uB144 " + month + "\uC6D4";
        }

        for (var dpi = 0; dpi < doc.pages.length; dpi++) {
            var dpg = doc.pages[dpi];
            // right-side(1919382632) + 마스터 [None] + 텍스트프레임 1개
            try {
                var masterName = dpg.appliedMaster ? dpg.appliedMaster.name : "";
            } catch(_) { var masterName = ""; }
            if (masterName !== "" && masterName !== "[None]") continue;
            if (dpg.side !== 1919382632) continue;
            if (dpg.textFrames.length !== 1) continue;

            var divTf = dpg.textFrames[0];
            var divParas = divTf.paragraphs;
            if (divParas.length < 2) continue;

            // 기존 텍스트가 간지 패턴인지 확인 (한글 포함)
            var existingP1 = (divParas[0].contents || "").replace(/[\r\n]+$/, "");
            if (!/[\uAC00-\uD7A3]/.test(existingP1)) continue;

            divParas[0].contents = line1 + "\r";
            divParas[1].contents = line2 + "\r";
        }
        addLog("\uAC04\uC9C0 \uD14D\uC2A4\uD2B8 \uC5C5\uB370\uC774\uD2B8 \uC644\uB8CC: " + line1 + " / " + line2);
    } catch(e) {
        addLog("\uAC04\uC9C0 \uD14D\uC2A4\uD2B8 \uC624\uB958: " + e.message);
    }

    // ========================================================================
    // 16.8. TEXTBOOK POST-PROCESSING (교과서: 빈 페이지 삭제 + 마스터 재할당)
    // ========================================================================
    if (workbookType === "\uAD50\uACFC\uC11C") {
        try {
            addLog("\uAD50\uACFC\uC11C \uD6C4\uCC98\uB9AC \uC2DC\uC791");

            // B-마스터, D-마스터 참조
            var bMaster = null, dMaster = null;
            try { bMaster = doc.masterSpreads.itemByName("B-\uB9C8\uC2A4\uD130"); bMaster.name; } catch(_) { bMaster = null; }
            try { dMaster = doc.masterSpreads.itemByName("D-\uB9C8\uC2A4\uD130"); dMaster.name; } catch(_) { dMaster = null; }

            // 각 STEP 스토리의 시작/끝 페이지 인덱스 파악
            // step1 = A-마스터 영역, step2 = C-마스터 영역
            // 간지(마스터 [None]) 사이의 콘텐츠 영역을 식별
            // STEP1 빈 right-page -> B-마스터, STEP2 빈 right-page -> D-마스터

            // 마스터별 빈 페이지에 올바른 빈 마스터 적용
            for (var tpi = doc.pages.length - 1; tpi >= 0; tpi--) {
                var tpg = doc.pages[tpi];
                var tfs = tpg.textFrames;
                var tHasContent = false;
                for (var ttf = 0; ttf < tfs.length; ttf++) {
                    var tc = (tfs[ttf].contents || "").replace(/[\s\r\n\uFFFC]+/g, "");
                    if (tc.length > 0) { tHasContent = true; break; }
                }

                if (tHasContent) continue;

                // 빈 페이지의 현재 마스터 확인
                var curMaster = "";
                try { curMaster = tpg.appliedMaster ? tpg.appliedMaster.name : ""; } catch(_) {}

                // A-마스터 빈 페이지 -> B-마스터
                if (curMaster === "A-\uB9C8\uC2A4\uD130" && bMaster) {
                    tpg.appliedMaster = bMaster;
                    addLog("B-\uB9C8\uC2A4\uD130 \uC801\uC6A9: p" + (tpi + 1));
                }
                // C-마스터 빈 페이지 -> D-마스터
                if (curMaster === "C-\uB9C8\uC2A4\uD130" && dMaster) {
                    tpg.appliedMaster = dMaster;
                    addLog("D-\uB9C8\uC2A4\uD130 \uC801\uC6A9: p" + (tpi + 1));
                }
            }

            addLog("\uAD50\uACFC\uC11C \uD6C4\uCC98\uB9AC \uC644\uB8CC");
        } catch(e) {
            addLog("\uAD50\uACFC\uC11C \uD6C4\uCC98\uB9AC \uC624\uB958: " + e.message);
        }
    }

    // ========================================================================
    // 17. SAVE DOCUMENT (last step — may be slow for large docs)
    // ========================================================================
    addLog("\uBB38\uC11C \uC800\uC7A5 \uC911...");
    try {
        doc.save();
    } catch(e) {}

    addLog("\uB85C\uADF8 \uD30C\uC77C \uC791\uC131 \uC644\uB8CC: " + logFile.fsName);

    app.scriptPreferences.enableRedraw = true;
    try { doc.recompose(); } catch(_){}

})();
