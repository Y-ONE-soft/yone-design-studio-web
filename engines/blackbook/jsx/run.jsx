// 블랙북 조판 자동화 v3
// - content.json (Day별 단락 + 정답/해설) → InDesign 스타일 적용
// - 본문: 독해 그룹 스타일 / 정답: 정답지 그룹 스타일
// - runs[].ul == true → 밑줄 문자 스타일 적용
#target indesign
(function() {

    // ── settings.json 로드 ─────────────────────────────────────────────────
    var settingsPath = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/프리미엄북/블랙북/auto/output/.blackbook_settings.json";

    var sf = new File(settingsPath);
    sf.encoding = 'UTF-8'; sf.open('r');
    var settings = eval("(" + sf.read() + ")");
    sf.close();

    var jsonPath   = settings.json_path;
    var outputDir  = settings.output_dir;
    var inddPath   = settings.indd_path;
    var issueNum   = settings.issue_num ? String(settings.issue_num) : '';

    // ── content.json 로드 ─────────────────────────────────────────────────
    var jf = new File(jsonPath);
    jf.encoding = 'UTF-8'; jf.open('r');
    var data = eval("(" + jf.read() + ")");
    jf.close();

    if (!data || !data.days || data.days.length === 0) { return; }

    // ── 조기 로그 기록 (runner 폴링용) ────────────────────────────────────
    var _earlyLog = new File(outputDir + '/조판_로그.txt');
    _earlyLog.encoding = 'UTF-8'; _earlyLog.open('w');
    _earlyLog.write('조판 시작: ' + new Date().toString());
    _earlyLog.close();

    // ── InDesign 파일 열기 ────────────────────────────────────────────────
    var workFile = new File(inddPath);
    var doc = null;

    try {
        var origDoc = null;
        for (var od = 0; od < app.documents.length; od++) {
            try {
                var odFsn = app.documents[od].fullName.fsName;
                if (app.documents[od].name === workFile.name && odFsn !== workFile.fsName) {
                    origDoc = app.documents[od]; break;
                }
            } catch(e) {}
        }

        if (origDoc) {
            for (var cd = 0; cd < app.documents.length; cd++) {
                try {
                    if (app.documents[cd].fullName.fsName === workFile.fsName) {
                        app.documents[cd].close(SaveOptions.NO); break;
                    }
                } catch(e) {}
            }
            origDoc.fullName.copy(workFile.fsName);
        }

        for (var di2 = 0; di2 < app.documents.length; di2++) {
            try {
                if (app.documents[di2].fullName.fsName === workFile.fsName) {
                    doc = app.documents[di2]; break;
                }
            } catch(e) {}
        }

        if (!doc) {
            doc = app.open(workFile);
            if (!doc || !doc.isValid) doc = app.activeDocument;
        }
    } catch(initErr) {
        doc = app.activeDocument;
    }

    if (!doc || !doc.isValid) { return; }
    app.activeDocument = doc;

    // ── 스타일 확보 ───────────────────────────────────────────────────────
    function ensureGroup(name) {
        var g = doc.paragraphStyleGroups.itemByName(name);
        if (!g.isValid) g = doc.paragraphStyleGroups.add({ name: name });
        return g;
    }
    function ensureStyle(groupName, styleName) {
        var g = ensureGroup(groupName);
        var s = g.paragraphStyles.itemByName(styleName);
        if (!s.isValid) s = g.paragraphStyles.add({ name: styleName });
        return s;
    }
    function ensureRootStyle(name) {
        var s = doc.paragraphStyles.itemByName(name);
        if (!s.isValid) s = doc.paragraphStyles.add({ name: name });
        return s;
    }
    function ensureCharStyle(name) {
        var s = doc.characterStyles.itemByName(name);
        if (!s.isValid) {
            s = doc.characterStyles.add({ name: name });
            try { s.underline = true; } catch(e) {}
        }
        return s;
    }

    // ── 본문 스타일 (독해 그룹) ─────────────────────────────────────────
    var GRP       = '독해';
    var stProblem = ensureStyle(GRP, '문제');
    var stSeonji  = ensureStyle(GRP, '선지');
    var stJogon   = ensureStyle(GRP, '조건');
    var stBase    = ensureRootStyle('!박스_지문');
    var stNextQ   = ensureStyle(GRP, '다음 글을 읽고');
    var stBox     = ensureStyle(GRP, '박스');
    var stExample = ensureStyle(GRP, '보기');
    var stUnder   = ensureCharStyle('밑줄');

    // ── 정답 스타일 (정답지 그룹) ───────────────────────────────────────
    var ANS_GRP   = '정답지';
    var stAnswer  = ensureStyle(ANS_GRP, '정답');
    var stExplan  = ensureStyle(ANS_GRP, '해설');

    function typeToStyle(typ) {
        if (typ === 'problem')          return stProblem;
        if (typ === 'choice')           return stSeonji;
        if (typ === 'condition')        return stJogon;
        if (typ === 'condition_item')   return stJogon;
        if (typ === 'answer_blank')     return stSeonji;
        if (typ === 'next_question')    return stNextQ;
        if (typ === 'passage_header')   return stNextQ;
        if (typ === 'summary_label')    return stBox;
        if (typ === 'summary_content')  return stBox;
        if (typ === 'example_label')    return stExample;
        if (typ === 'example_content')  return stExample;
        return stBase;  // passage
    }

    // ── 밑줄 적용 ────────────────────────────────────────────────────────
    function applyUnderlineRuns(para, runs) {
        if (!runs || runs.length === 0) return;
        var pos = 0;
        for (var ri = 0; ri < runs.length; ri++) {
            var run = runs[ri];
            var rLen = run.t ? run.t.length : 0;
            if (rLen === 0) { continue; }
            if (run.ul) {
                try {
                    para.characters.itemByRange(pos, pos + rLen - 1).appliedCharacterStyle = stUnder;
                } catch(e) {}
            }
            pos += rLen;
        }
    }

    // ── 스토리 내용 교체 ──────────────────────────────────────────────────
    function replaceStoryContent(story, paragraphs) {
        if (!story || !story.isValid || !paragraphs || paragraphs.length === 0) return;

        var fullText = '';
        for (var i = 0; i < paragraphs.length; i++) {
            fullText += paragraphs[i].text;
            if (i < paragraphs.length - 1) fullText += '\r';
        }
        story.contents = fullText;

        // 단락 스타일 + 문자스타일 초기화 + 밑줄 적용 (단락 단위)
        var noneStyle = doc.characterStyles[0];
        var paras = story.paragraphs;
        for (var i = 0; i < paragraphs.length && i < paras.length; i++) {
            paras[i].appliedParagraphStyle = typeToStyle(paragraphs[i].type);
            paras[i].appliedCharacterStyle = noneStyle;
            applyUnderlineRuns(paras[i], paragraphs[i].runs);
        }
    }

    // ── 프레임 브레이크 삽입 (문제 블록 시작점 앞, 두 번째부터) ────────────
    // 문제 블록 시작 = next_question 또는 (앞에 next_question 없는) problem
    function insertFrameBreaks(story) {
        var paras = story.paragraphs;
        var breakIndices = [];
        var nextQPending = false;

        for (var i = 0; i < paras.length; i++) {
            var sty = paras[i].appliedParagraphStyle;
            if (sty === stNextQ) {
                breakIndices.push(i);
                nextQPending = true;
            } else if (sty === stProblem) {
                if (!nextQPending) {
                    breakIndices.push(i);
                }
                nextQPending = false;
            }
        }

        for (var k = breakIndices.length - 1; k >= 1; k--) {
            try {
                paras = story.paragraphs;
                paras[breakIndices[k]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
            } catch(e) {}
        }
    }

    // ── 프레임 부족 시 자동 추가 ──────────────────────────────────────────
    function ensureEnoughFrames(story, neededFrames) {
        var containers = story.textContainers;
        var deficit = neededFrames - containers.length;
        if (deficit <= 0) return;

        var lastCont = containers[containers.length - 1];
        var lastPage = lastCont.parentPage;

        var tmplBounds = [];
        for (var i = 0; i < containers.length; i++) {
            if (containers[i].parentPage === lastPage) {
                var b = containers[i].geometricBounds;
                tmplBounds.push([b[0], b[1], b[2], b[3]]);
            }
        }
        tmplBounds.sort(function(a, b) { return a[1] - b[1]; });
        var fpp = tmplBounds.length || 1;
        var masterPage = lastPage.appliedMaster;
        var insertAfter = lastPage;
        var curFrame = lastCont;
        var added = 0;

        while (added < deficit) {
            var newPage = doc.pages.add(LocationOptions.AFTER, insertAfter);
            if (masterPage) { try { newPage.appliedMaster = masterPage; } catch(e) {} }
            insertAfter = newPage;
            for (var j = 0; j < fpp && added < deficit; j++) {
                var newTF = newPage.textFrames.add();
                newTF.geometricBounds = tmplBounds[j] || [10, 10, 270, 190];
                curFrame.nextTextFrame = newTF;
                curFrame = newTF;
                added++;
            }
        }
    }

    // ── 문제 번호 연속화 ─────────────────────────────────────────────────
    function fixProblemNumbering(stories) {
        var cumulative = 1;
        for (var di = 0; di < stories.length; di++) {
            var paras = stories[di].paragraphs;
            var storyProblemCount = 0;
            var isFirstInStory = true;
            for (var i = 0; i < paras.length; i++) {
                if (paras[i].appliedParagraphStyle === stProblem) {
                    try {
                        if (isFirstInStory) {
                            paras[i].numberingContinue = false;
                            paras[i].numberingStartAt  = cumulative;
                            isFirstInStory = false;
                        } else {
                            paras[i].numberingContinue = true;
                        }
                    } catch(e) {}
                    storyProblemCount++;
                }
            }
            cumulative += storyProblemCount;
        }
    }

    // ── 빈 페이지 삭제 ────────────────────────────────────────────────────
    function deleteEmptyPages() {
        var deleted = 0;
        for (var p = doc.pages.length - 1; p >= 1; p--) {
            var page = doc.pages[p];
            var tfs  = page.textFrames;
            if (tfs.length === 0) continue;

            var pageEmpty = true;
            for (var t = 0; t < tfs.length && pageEmpty; t++) {
                try {
                    // 프레임 자체의 contents만 체크 (parentStory 전체 읽기 회피)
                    var c = tfs[t].contents;
                    if (typeof c === 'string' && c.replace(/[\r\n\s]/g, '').length > 0) {
                        pageEmpty = false;
                    }
                } catch(e) {
                    pageEmpty = false;
                }
            }

            if (pageEmpty) {
                try { page.remove(); deleted++; } catch(e) {}
            }
        }
        log.push('빈 페이지 삭제: ' + deleted + '개');
    }

    // ── Day별 본문 + 정답 스토리 수집 (단일 순회) ──────────────────────
    var BODY_STYLE_NAMES = {
        '\uBB38\uC81C': 1,         // 문제
        '\uB2E4\uC74C \uAE00\uC744 \uC77D\uACE0': 1, // 다음 글을 읽고
        '\uC120\uC9C0': 1,         // 선지
        '\uC870\uAC74': 1,         // 조건
        '!\uBC15\uC2A4_\uC9C0\uBB38': 1 // !박스_지문
    };
    function collectStories() {
        var bodyFound = [], ansFound = [], seen = {};
        var bodyDone = false;
        for (var p = 0; p < doc.pages.length; p++) {
            var tfs = doc.pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var story = tfs[t].parentStory;
                if (seen[story.id]) continue;
                seen[story.id] = true;

                // 본문 스토리 판별 (첫 10개 단락 체크)
                if (!bodyDone) {
                    var paras = story.paragraphs;
                    var limit = Math.min(paras.length, 10);
                    var isBody = false;
                    for (var pi = 0; pi < limit; pi++) {
                        if (BODY_STYLE_NAMES[paras[pi].appliedParagraphStyle.name]) {
                            isBody = true; break;
                        }
                    }
                    if (isBody) {
                        bodyFound.push(story);
                        if (bodyFound.length >= data.days.length) bodyDone = true;
                        continue;
                    }
                }

                // 정답 스토리 판별
                var aParas = story.paragraphs;
                for (var api = 0; api < aParas.length; api++) {
                    var sty = aParas[api].appliedParagraphStyle;
                    if (sty === stAnswer || sty === stExplan) {
                        ansFound.push(story);
                        break;
                    }
                }
            }
        }
        return { body: bodyFound, answer: ansFound };
    }

    // ── 마스터 페이지 찾기 ───────────────────────────────────────────────
    function getMaster(prefix) {
        for (var i = 0; i < doc.masterSpreads.length; i++) {
            var ms = doc.masterSpreads[i];
            if (ms.namePrefix === prefix) return ms;
        }
        return null;
    }

    // ── 정답 스토리 내용 교체 ────────────────────────────────────────────
    function replaceAnswerContent(story, dayAns) {
        if (!story || !story.isValid || !dayAns || dayAns.length === 0) return;

        // 텍스트 조합: 정답 + 해설 단락 교대
        var fullText = '';
        var paraTypes = [];
        for (var ai = 0; ai < dayAns.length; ai++) {
            var a = dayAns[ai];
            fullText += a.num + '.  ' + a.answer;
            paraTypes.push('answer');
            if (a.explanation) {
                fullText += '\r' + a.explanation;
                paraTypes.push('explanation');
            }
            if (ai < dayAns.length - 1) fullText += '\r';
        }
        story.contents = fullText;

        // 스타일 적용 (단락 단위)
        var noneStyle = doc.characterStyles[0];
        var paras = story.paragraphs;
        for (var pi = 0; pi < paraTypes.length && pi < paras.length; pi++) {
            paras[pi].appliedCharacterStyle = noneStyle;
            paras[pi].appliedParagraphStyle = (paraTypes[pi] === 'answer') ? stAnswer : stExplan;
        }
    }

    // ── 정답 스토리 페이지 관리 ──────────────────────────────────────────
    // 오버플로우 시 페이지+프레임 추가, 빈 페이지 제거, 마스터 페이지 적용
    function adjustAnswerPages(story) {
        var masterC2 = getMaster('C2');
        var masterE  = getMaster('E');

        // 오버플로우 체크 → 프레임/페이지 추가
        var containers = story.textContainers;
        var lastFrame = containers[containers.length - 1];

        // 오버플로우면 페이지 추가 (최대 3페이지까지)
        var safetyCount = 0;
        while (lastFrame.overflows && safetyCount < 3) {
            var lastPage = lastFrame.parentPage;
            // 같은 페이지의 프레임 바운드를 템플릿으로 사용 (왼쪽→오른쪽 정렬)
            var tmplBounds = [];
            var pageTFs = lastPage.textFrames;
            for (var ti = 0; ti < pageTFs.length; ti++) {
                var b = pageTFs[ti].geometricBounds;
                tmplBounds.push([b[0], b[1], b[2], b[3]]);
            }
            tmplBounds.sort(function(a, b) { return a[1] - b[1]; });
            var fpp = tmplBounds.length || 2;  // 정답 페이지는 기본 2프레임/페이지

            var newPage = doc.pages.add(LocationOptions.AFTER, lastPage);
            if (masterC2) {
                try { newPage.appliedMaster = masterC2; } catch(e) {}
            }
            for (var fi = 0; fi < fpp; fi++) {
                var newTF = newPage.textFrames.add();
                newTF.geometricBounds = tmplBounds[fi] || [10, 10, 130, 190];
                lastFrame.nextTextFrame = newTF;
                lastFrame = newTF;
            }
            safetyCount++;
        }

        // 스토리가 점유하는 페이지 목록 수집
        containers = story.textContainers;
        var storyPages = [];
        var seenPages = {};
        for (var ci = 0; ci < containers.length; ci++) {
            var pg = containers[ci].parentPage;
            if (pg && !seenPages[pg.id]) {
                seenPages[pg.id] = true;
                storyPages.push(pg);
            }
        }

        // 마지막 페이지가 비어있으면 프레임 체인 해제 후 삭제
        if (storyPages.length > 1) {
            var lastStoryPage = storyPages[storyPages.length - 1];
            var lastPageEmpty = true;
            var lastPageTFs = lastStoryPage.textFrames;
            for (var t = 0; t < lastPageTFs.length; t++) {
                try {
                    var pars = lastPageTFs[t].paragraphs;
                    for (var pp = 0; pp < pars.length; pp++) {
                        if (pars[pp].contents.replace(/[\r\n\s]/g, '').length > 0) {
                            lastPageEmpty = false; break;
                        }
                    }
                } catch(e) { lastPageEmpty = false; }
                if (!lastPageEmpty) break;
            }

            if (lastPageEmpty) {
                // 체인에서 마지막 페이지의 프레임 분리
                for (var t = 0; t < lastPageTFs.length; t++) {
                    try {
                        // 이 프레임을 가리키는 이전 프레임의 nextTextFrame을 null로
                        var prevFrame = lastPageTFs[t].previousTextFrame;
                        if (prevFrame && prevFrame.isValid) {
                            prevFrame.nextTextFrame = null;
                        }
                    } catch(e) {}
                }
                try { lastStoryPage.remove(); } catch(e) {}
                // storyPages 갱신
                storyPages.pop();
            }
        }

        // 마스터 페이지 적용: 1페이지 → E, 2페이지 이상 → C2
        var master = (storyPages.length >= 2) ? masterC2 : masterE;
        if (master) {
            for (var sp = 0; sp < storyPages.length; sp++) {
                try { storyPages[sp].appliedMaster = master; } catch(e) {}
            }
        }

        return storyPages.length;
    }

    // ── 수집 ────────────────────────────────────────────────────────────
    var collected     = collectStories();
    var dayStories    = collected.body;
    var answerStories = collected.answer;

    var log = ['=== 블랙북 조판 자동화 v3 ==='];
    log.push(new Date().toString());
    log.push('');
    log.push('Day 수: ' + data.days.length + ' / 본문 스토리: ' + dayStories.length);
    log.push('Day 정답: ' + (data.day_answers ? data.day_answers.length : 0) + '개 Day / 정답 스토리: ' + answerStories.length);
    log.push('');

    app.doScript(function() {

        // ── 주차 텍스트 치환 ("\d+주 차" → issueNum + "주 차") ────────────
        if (issueNum) {
            var weekText = issueNum + '\uC8FC \uCC28'; // "N주 차"
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = '\\d+\uC8FC.?\uCC28';
            app.changeGrepPreferences.changeTo = weekText;
            for (var mi = 0; mi < doc.masterSpreads.length; mi++) {
                var ms = doc.masterSpreads[mi];
                for (var mp = 0; mp < ms.pages.length; mp++) {
                    var mtfs = ms.pages[mp].textFrames;
                    for (var mt = 0; mt < mtfs.length; mt++) {
                        try { mtfs[mt].parentStory.changeGrep(); } catch(e) {}
                    }
                }
            }
            doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log.push('\uC8FC\uCC28 \uD14D\uC2A4\uD2B8 \uCE58\uD658: ' + weekText); // "주차 텍스트 치환: N주 차"
        }

        // ── Day별 본문 조판 ────────────────────────────────────────────
        for (var di = 0; di < data.days.length; di++) {
            var day = data.days[di];
            var paras = day.paragraphs;
            log.push('── Day ' + day.day_num + ' (' + paras.length + '개 단락) ──');

            var story;
            if (dayStories.length >= data.days.length) {
                story = dayStories[di];
            } else if (dayStories.length > 0) {
                story = dayStories[0];
                if (di > 0) {
                    log.push('  [경고] 스토리 부족 — Day ' + day.day_num + ' 스킵');
                    continue;
                }
            } else {
                log.push('  [오류] 스토리 없음 — 스킵');
                continue;
            }

            replaceStoryContent(story, paras);
            insertFrameBreaks(story);

            var blockCount = 0;
            var nqPending = false;
            for (var i = 0; i < paras.length; i++) {
                if (paras[i].type === 'next_question' || paras[i].type === 'passage_header') {
                    blockCount++;
                    nqPending = true;
                } else if (paras[i].type === 'problem') {
                    if (!nqPending) blockCount++;
                    nqPending = false;
                }
            }
            if (blockCount > 1) {
                ensureEnoughFrames(story, blockCount);
            }

            log.push('  단락: ' + paras.length + '개, 블록: ' + blockCount + '개 ✓');
        }

        // ── Day별 정답/해설 조판 ──────────────────────────────────────
        if (data.day_answers && data.day_answers.length > 0) {
            var ansCount = Math.min(data.day_answers.length, answerStories.length);
            for (var dai = 0; dai < ansCount; dai++) {
                var da = data.day_answers[dai];
                if (!da.answers || da.answers.length === 0) continue;

                replaceAnswerContent(answerStories[dai], da.answers);
                var pgCount = adjustAnswerPages(answerStories[dai]);
                log.push('정답 Day ' + da.day_num + ': ' + da.answers.length + '개, ' + pgCount + '페이지 ✓');
            }

            if (data.day_answers.length > answerStories.length) {
                log.push('[경고] 정답 스토리 부족: ' + answerStories.length + '개 (필요 ' + data.day_answers.length + '개)');
            }
        }

        // ── 문제 번호 연속화 ──────────────────────────────────────────────
        try {
            fixProblemNumbering(dayStories);
            log.push('문제 번호 연속화 완료: ' + dayStories.length + '개 스토리');
        } catch(e) {
            log.push('[경고] 번호 연속화 실패: ' + e.message);
        }

        // ── 빈 페이지 삭제 ────────────────────────────────────────────────
        try { deleteEmptyPages(); } catch(e) { log.push('[경고] 빈 페이지 삭제 실패: ' + e.message); }

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '블랙북 조판 자동화');

    // ── 오버플로우 체크 ───────────────────────────────────────────────────
    var overflows = [];
    var tfs = doc.textFrames;
    for (var i = 0; i < tfs.length; i++) {
        try {
            if (tfs[i].overflows) {
                var pg = tfs[i].parentPage;
                overflows.push('P' + (pg ? pg.name : '?'));
            }
        } catch(e) {}
    }
    log.push('');
    log.push('오버플로우: ' + overflows.length + '개');
    if (overflows.length > 0) log.push('  페이지: ' + overflows.join(', '));
    log.push('Day조판완료: ' + data.days.length + '개');

    // ── 로그 저장 ─────────────────────────────────────────────────────────
    var logFile = new File(outputDir + '/조판_로그.txt');
    logFile.encoding = 'UTF-8'; logFile.open('w');
    logFile.write(log.join('\n'));
    logFile.close();

    // ── 문서 저장 ─────────────────────────────────────────────────────────
    doc.save();

    // ── PDF 내보내기 ──────────────────────────────────────────────────────
    var pdfFile = new File(outputDir + '/' + doc.name.replace(/\.indd$/i, '') + '.pdf');
    var pdfOk = false;
    try {
        var preset = app.pdfExportPresets.itemByName('[고품질 인쇄]');
        if (!preset.isValid) preset = app.pdfExportPresets.itemByName('[High Quality Print]');
        if (preset.isValid) {
            doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false, preset);
        } else {
            doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false);
        }
        pdfOk = true;
    } catch(err) {
        log.push('PDF 오류: ' + err.message);
    }

    log.push('PDF: ' + (pdfOk ? '성공 → ' + pdfFile.name : '실패'));
    logFile = new File(outputDir + '/조판_로그.txt');
    logFile.encoding = 'UTF-8'; logFile.open('w');
    logFile.write(log.join('\n'));
    logFile.close();

})();
