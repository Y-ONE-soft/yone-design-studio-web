// 블랙북 조판 자동화 v3
// - content.json (Day별 단락 + 정답/해설) → InDesign 스타일 적용
// - 본문: 독해 그룹 스타일 / 정답: 정답지 그룹 스타일
// - runs[].ul == true → 밑줄 문자 스타일 적용
#target indesign
(function() {

    // 모든 대화상자 자동 차단 (사용자 개입 X)
    try { app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT; } catch(e) {}

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

    if (!data || !data.sections) { return; }

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
    var GRP        = '독해';
    var stProblem  = ensureStyle(GRP, '문제');
    var stSeonji   = ensureStyle(GRP, '!선지');
    var stJogon    = ensureStyle(GRP, '조건');
    var stBase     = ensureRootStyle('!박스_지문');
    var stNextQ    = ensureStyle(GRP, '다음 글을 읽고');
    var stBox      = ensureStyle(GRP, '박스');
    var stExample  = ensureStyle(GRP, '보기');
    var stCategory = ensureStyle(GRP, '카테고리');
    var stUnder    = ensureCharStyle('밑줄');

    // ── 어휘 스타일 (Vocabulary+ 그룹) ─────────────────────────────────
    var VOC_GRP            = 'Vocabulary+';
    var stVocabBonmunCat   = ensureStyle(VOC_GRP, '본문 카테고리'); // <N과 본문M>
    var stVocabCategory    = ensureStyle(VOC_GRP, '카테고리');      // 〈연관 어휘〉
    var stVocabItem        = ensureStyle(VOC_GRP, '!연관 어휘');    // 표제어+뜻+동의어

    // ── 추가 본문 스타일 (배경) ────────────────────────────────────────
    var stBackground       = ensureStyle(GRP, '배경');

    // ── 정답 스타일 (정답 및 해설 그룹) ────────────────────────────────
    var ANS_GRP   = '정답 및 해설';
    var stAnswer  = ensureStyle(ANS_GRP, '정답');
    var stExplan  = ensureStyle(ANS_GRP, '해설');

    function typeToStyle(typ) {
        if (typ === 'problem')          return stProblem;
        if (typ === 'choice')           return stSeonji;
        if (typ === 'condition')        return stSeonji;  // 조건 → 선지 (지문 뒤 선택지)
        if (typ === 'condition_item')   return stSeonji;
        if (typ === 'answer_blank')     return stSeonji;
        if (typ === 'next_question')    return stNextQ;
        if (typ === 'passage_header')   return stNextQ;
        if (typ === 'summary_label')    return stBox;
        if (typ === 'summary_content')  return stBox;
        if (typ === 'example_label')    return stExample;
        if (typ === 'example_content')  return stExample;
        if (typ === 'vocab_header')     return stVocabBonmunCat;  // <N과 본문M> → 본문 카테고리
        if (typ === 'vocab_passage')    return stBase;
        if (typ === 'vocab_category')   return stVocabCategory;
        if (typ === 'vocab_item')       return stVocabItem;
        if (typ === 'background')       return stBackground;       // 문장 삽입/요약 배경
        return stBase;
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
        // 단락 속성 startParagraph = NEXT_FRAME 사용 (FRAME_BREAK 문자 삽입보다 빠르고 안전)
        // story.paragraphs를 한 번만 가져와 캐시 (큰 스토리에서 매번 재조회는 매우 느림)
        var paras = story.paragraphs;
        var nextQPending = false;
        for (var i = 0; i < paras.length; i++) {
            try {
                var sty = paras[i].appliedParagraphStyle;
                if (sty === stNextQ) {
                    if (i > 0) {
                        try { paras[i].startParagraph = StartParagraph.NEXT_FRAME; } catch(e) {}
                    }
                    nextQPending = true;
                } else if (sty === stProblem) {
                    if (!nextQPending && i > 0) {
                        try { paras[i].startParagraph = StartParagraph.NEXT_FRAME; } catch(e) {}
                    }
                    nextQPending = false;
                }
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

    // ── 영역 자동 분류 (frame 크기 + 페이지 순) ─────────────────────────
    // 마스터 이름 의존 안 함. 모듈식 본문 + 큰 어휘 frame + 2단 정답 구조 자동 인식.
    //   본문 모듈 frame : width >= 150 && height <  150  → frame당 한 문제
    //   어휘 큰  frame  : width >= 150 && height >= 200  → frame당 한 어휘 본문
    //   정답 좁은frame  : width <  100 && height >= 200  → 한 스토리(연결된 frame)에 정답 전체
    //   헤더 등         : 그 외 (제외)
    //
    // 영역 분리:
    //   본문 모듈: large(어휘) 첫 페이지 직전 → part1, 그 이후 → part2
    //   정답: 서로 다른 parentStory id별로 묶음 → firstPgIdx 순으로 part1, part2
    // ── 페이지 카테고리 + 연속 페이지 영역 검출 ─────────────────────────
    //   module : 본문 모듈 frame (w>=150, h<150) 1개 이상
    //   large  : 큰 frame (w>=150, h>=200) 1개 이상 (어휘 또는 표지)
    //   narrow : 좁고 긴 frame (w<100, h>=200) 1개 이상 (정답 2단)
    //   empty  : 매칭 frame 없음 (표지/구분 페이지)
    // 같은 카테고리가 연속된 페이지를 한 영역으로 묶음. 마스터 이름 의존 X.
    function categorizePage(page) {
        var module = 0, large = 0, narrow = 0;
        var tfs = page.textFrames;
        for (var t = 0; t < tfs.length; t++) {
            var b;
            try { b = tfs[t].geometricBounds; } catch(e) { continue; }
            var w = b[3] - b[1], h = b[2] - b[0];
            if (h < 30 || w < 50) continue;
            if (w >= 150 && h < 200) module++;
            else if (w >= 150 && h >= 200) large++;
            else if (w < 100 && h >= 200) narrow++;
        }
        if (module > 0) return 'module';
        if (large > 0)  return 'large';
        if (narrow > 0) return 'narrow';
        return 'empty';
    }

    function detectAreas() {
        var areas = [];
        var cur = null;
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            var cat = categorizePage(page);
            if (cur === null || cur.cat !== cat) {
                if (cur) areas.push(cur);
                cur = {cat: cat, pages: [page]};
            } else {
                cur.pages.push(page);
            }
        }
        if (cur) areas.push(cur);
        return areas;
    }

    function filterAreas(areas, cat) {
        var out = [];
        for (var i = 0; i < areas.length; i++) {
            if (areas[i].cat === cat) out.push(areas[i]);
        }
        return out;
    }

    var FILTER_MODULE = function(b) {
        var w = b[3] - b[1], h = b[2] - b[0];
        // 본문 모듈: w>=150 + h 30~199 (다양한 크기 모듈 포함)
        return w >= 150 && h < 200 && h >= 30;
    };
    var FILTER_LARGE = function(b) {
        var w = b[3] - b[1], h = b[2] - b[0];
        // 어휘 큰 frame: w>=150 + h>=200
        return w >= 150 && h >= 200;
    };

    // 영역 내 매칭 frame들의 체인을 모두 끊어 각 frame을 독립 스토리로 만듦.
    // (원본 indd가 한 스토리 흐름으로 디자인되어 있어도 frame당 한 문제 매핑 가능하게 함)
    function unchainAreaFrames(area, filterFn) {
        var broken = 0;
        for (var p = 0; p < area.pages.length; p++) {
            var tfs = area.pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var b = tfs[t].geometricBounds;
                    if (!filterFn(b)) continue;
                    if (tfs[t].nextTextFrame) {
                        tfs[t].nextTextFrame = null;
                        broken++;
                    }
                } catch(e) {}
            }
        }
        return broken;
    }

    // 영역 내 매칭 frame을 페이지 순 + y 순 (같은 y면 x 순) 으로 정렬해 반환
    function collectFramesInArea(area, filterFn) {
        var frames = [];
        for (var p = 0; p < area.pages.length; p++) {
            var page = area.pages[p];
            var pageFrames = [];
            var tfs = page.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var b = tfs[t].geometricBounds;
                    if (filterFn(b)) pageFrames.push({tf: tfs[t], y: b[0], x: b[1]});
                } catch(e) {}
            }
            pageFrames.sort(function(a, b) {
                if (Math.abs(a.y - b.y) < 5) return a.x - b.x;
                return a.y - b.y;
            });
            for (var n = 0; n < pageFrames.length; n++) frames.push(pageFrames[n]);
        }
        return frames;
    }

    // 영역 페이지의 textFrame을 새 페이지에 똑같이 복제
    function clonePageFrames(srcPage, dstPage) {
        var srcTfs = srcPage.textFrames;
        for (var s = 0; s < srcTfs.length; s++) {
            try {
                var src = srcTfs[s];
                var b = src.geometricBounds;
                var nf = dstPage.textFrames.add({geometricBounds: b});
                // 텍스트 스토리는 새 frame이 자체 새 스토리. 기존 frame 속성은 복제 안 함 (단순)
            } catch(e) {}
        }
    }

    // 영역의 마지막 페이지 다음에 새 페이지 추가 + frame 복제. 영역 안에서만 확장.
    function ensureFramesInArea(area, neededCount, filterFn, label) {
        var frames = collectFramesInArea(area, filterFn);
        var added = 0;
        var safetyMax = 200;
        while (frames.length < neededCount && added < safetyMax) {
            // area.pages 중 doc.pages에서 가장 뒤 위치 페이지를 lastPage로
            var lastPage = null, maxIdx = -1;
            for (var ai = 0; ai < area.pages.length; ai++) {
                var pg = area.pages[ai];
                if (!pg || !pg.isValid) continue;
                for (var di = 0; di < doc.pages.length; di++) {
                    if (doc.pages[di] === pg) {
                        if (di > maxIdx) { maxIdx = di; lastPage = pg; }
                        break;
                    }
                }
            }
            if (!lastPage) {
                log.push('[ERR] ' + label + ': 영역 마지막 페이지 무효');
                break;
            }
            // 빈 페이지 추가 + 마스터 적용 + lastPage frame 복제
            var newPage;
            try {
                newPage = doc.pages.add(LocationOptions.AFTER, lastPage);
                if (lastPage.appliedMaster) {
                    try { newPage.appliedMaster = lastPage.appliedMaster; } catch(e) {}
                }
                clonePageFrames(lastPage, newPage);
            } catch(e) {
                log.push('[ERR] ' + label + ': 페이지 추가 실패: ' + e.message);
                break;
            }
            area.pages.push(newPage);

            // 새 페이지의 매칭 frame 수집 (체인 끊기로 모두 독립 스토리)
            var newPageFrames = [];
            var newTfs = newPage.textFrames;
            for (var t = 0; t < newTfs.length; t++) {
                try {
                    var b = newTfs[t].geometricBounds;
                    if (filterFn(b)) {
                        // 체인 끊기 (새 페이지도 한 스토리에 연결돼 있을 수 있음)
                        try { if (newTfs[t].nextTextFrame) newTfs[t].nextTextFrame = null; } catch(e) {}
                        newPageFrames.push({tf: newTfs[t], y: b[0], x: b[1]});
                    }
                } catch(e) {}
            }
            newPageFrames.sort(function(a, b) {
                if (Math.abs(a.y - b.y) < 5) return a.x - b.x;
                return a.y - b.y;
            });

            if (newPageFrames.length === 0) {
                log.push('[WARN] ' + label + ': 복제 페이지에 매칭 frame 없음 - 중단');
                break;
            }
            // 복제된 frame 콘텐츠 비우기
            for (var c = 0; c < newPageFrames.length; c++) {
                try { newPageFrames[c].tf.contents = ''; } catch(e) {}
                frames.push(newPageFrames[c]);
            }
            added++;
        }
        if (added > 0) log.push('[INFO] ' + label + ': 페이지 ' + added + '개 추가 (frame ' + frames.length + '개 확보)');
        return frames;
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

    // ── 영역 자동 분류 + 매핑 ──────────────────────────────────────────
    // ── 영역 검출 + 매핑 ──────────────────────────────────────────────
    var areas = detectAreas();
    var moduleAreas = filterAreas(areas, 'module');
    var largeAreas  = filterAreas(areas, 'large');

    // doc 전체에서 narrow frame을 페이지 순으로 수집하고, 페이지 인덱스 gap(>1)을
    // 기준으로 그룹핑. 정답 표지 페이지가 narrow 영역 사이에 끼어 있어도 같은 정답지
    // 안의 narrow는 한 그룹으로 묶임. 두 정답지 사이는 빈 페이지 + 표지 페이지로 gap이 큼.
    function findNarrowAreas() {
        var narrows = [];
        for (var p = 0; p < doc.pages.length; p++) {
            var pg = doc.pages[p];
            var tfs = pg.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var b = tfs[t].geometricBounds;
                    var w = b[3] - b[1], h = b[2] - b[0];
                    if (w < 100 && h >= 200) {
                        narrows.push({page: pg, pgIdx: p, y: b[0]});
                        break;  // 페이지당 한 번만 등록
                    }
                } catch(e) {}
            }
        }
        // pgIdx 순 (이미 순회 순)
        var result = [];
        var current = null;
        var lastPg = -10;
        for (var i = 0; i < narrows.length; i++) {
            if (narrows[i].pgIdx - lastPg > 1) {
                if (current) result.push(current);
                current = {cat: 'narrow', pages: []};
            }
            current.pages.push(narrows[i].page);
            lastPg = narrows[i].pgIdx;
        }
        if (current) result.push(current);
        return result;
    }
    var narrowAreas = findNarrowAreas();

    var sections = data.sections || {};

    var log = ['=== 블랙북 조판 자동화 v6 (영역 객체 기반) ==='];
    log.push(new Date().toString());
    log.push('');
    log.push('영역: module=' + moduleAreas.length + ', large=' + largeAreas.length + ', narrow=' + narrowAreas.length);
    log.push('필요: PART1 문제=' + (sections.part1_problem || []).length +
             ', PART1 어휘=' + (sections.part1_vocab || []).length +
             ', PART2 문제=' + (sections.part2_problem || []).length +
             ', PART1 해설=' + (sections.part1_answer || []).length +
             ', PART2 해설=' + (sections.part2_answer || []).length);
    log.push('');

    var bodyDoneCount = 0;
    var ansDoneCount  = 0;

    app.doScript(function() {

        // ── 주차 텍스트 치환 ──────────────────────────────────────────────
        if (issueNum) {
            var weekText = issueNum + '주 차';
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = '\\d+주.?차';
            app.changeGrepPreferences.changeTo = weekText;
            for (var mi2 = 0; mi2 < doc.masterSpreads.length; mi2++) {
                var ms = doc.masterSpreads[mi2];
                for (var mp = 0; mp < ms.pages.length; mp++) {
                    var mtfs = ms.pages[mp].textFrames;
                    for (var mt = 0; mt < mtfs.length; mt++) {
                        try { mtfs[mt].parentStory.changeGrep(); } catch(e) {}
                    }
                }
            }
            doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log.push('주차 텍스트 치환: ' + weekText);
        }

        // ── 본문 모듈 frame 채우기 (frame당 한 문제/어휘 본문) ─────────────
        function fillFrames(frames, groups, label) {
            var filled = 0;
            var cnt = Math.min(frames.length, groups.length);
            for (var i = 0; i < cnt; i++) {
                try {
                    replaceStoryContent(frames[i].tf.parentStory, groups[i].paragraphs);
                    filled++;
                } catch(e) {
                    log.push('[ERR] ' + label + ' frame ' + i + ': ' + e.message);
                }
            }
            if (frames.length > groups.length) {
                log.push('[INFO] ' + label + ': frame ' + frames.length + ' / 그룹 ' + groups.length + ' (남은 frame 그대로 둠)');
                // 남는 frame 비우지 않음 (디자인 placeholder/콘텐츠 보존)
            }
            log.push(label + ': ' + filled + '/' + groups.length + ' frame 채움');
            return filled;
        }

        var p1prob = sections.part1_problem || [];
        var p1voc  = sections.part1_vocab   || [];
        var p2prob = sections.part2_problem || [];

        // 영역의 모든 매칭 frame을 페이지 순으로 한 줄 체인 연결 + 첫 스토리에 통째 흘려넣기
        function fillAreaAsSingleFlow(area, filterFn, groups, label, isProblem) {
            // 1) 영역의 모든 frame 수집
            var frames = collectFramesInArea(area, filterFn);
            if (frames.length === 0) {
                log.push('[ERR] ' + label + ': 영역에 매칭 frame 없음');
                return 0;
            }
            // 2) 모든 frame의 기존 체인 끊기 + 새 체인 연결
            for (var i = 0; i < frames.length; i++) {
                try { if (frames[i].tf.nextTextFrame) frames[i].tf.nextTextFrame = null; } catch(e) {}
            }
            for (var i2 = 0; i2 < frames.length - 1; i2++) {
                try { frames[i2].tf.nextTextFrame = frames[i2+1].tf; } catch(e) {}
            }
            // 3) 그룹 paragraphs 합쳐서 한 흐름 텍스트 만들기
            var allParas = [];
            for (var g = 0; g < groups.length; g++) {
                if (!groups[g].paragraphs) continue;
                for (var pi = 0; pi < groups[g].paragraphs.length; pi++) {
                    allParas.push(groups[g].paragraphs[pi]);
                }
            }
            // 4) 첫 frame의 스토리에 통째 채움
            var story = frames[0].tf.parentStory;
            replaceStoryContent(story, allParas);
            // 5) 문제 영역이면 각 문제 시작점에 frame break 삽입 + 첫 문제 번호 1로 리셋
            if (isProblem) {
                try { insertFrameBreaks(story); } catch(e) { log.push('[WARN] ' + label + ' frame break: ' + e.message); }
                // 첫 문제 단락의 자동 번호를 1번부터 다시 시작 (PART1/PART2 각각 독립)
                try {
                    var sParas = story.paragraphs;
                    for (var pi = 0; pi < sParas.length; pi++) {
                        if (sParas[pi].appliedParagraphStyle === stProblem) {
                            sParas[pi].numberingContinue = false;
                            sParas[pi].numberingStartAt = 1;
                            break;
                        }
                    }
                } catch(e) { log.push('[WARN] ' + label + ' 번호 리셋: ' + e.message); }
            }
            // 6) 오버플로우 체크 (자동 페이지 추가 X — 사용자 수동 처리)
            var lastFrame = story.textContainers[story.textContainers.length - 1];
            var overflow = false;
            try { overflow = lastFrame && lastFrame.overflows; } catch(e) {}
            if (overflow) {
                log.push('[WARN] ' + label + ': 마지막 frame 오버플로우 — 사용자 수동 처리 필요');
            }
            log.push(label + ': ' + groups.length + '개 그룹, frame ' + story.textContainers.length + '개, 오버플로우=' + overflow);
            return groups.length;
        }

        // 영역의 모든 frame 체인 끊고 → 각 frame 독립 스토리화 → frame당 한 문제 채움.
        // frame 부족 시 마지막 페이지 복제로 새 frame 추가 (영역 안에서만).
        function fillAreaPerFrame(area, filterFn, groups, label) {
            var brokenCnt = unchainAreaFrames(area, filterFn);
            log.push('[INFO] ' + label + ': frame 체인 ' + brokenCnt + '개 끊음');
            var frames = ensureFramesInArea(area, groups.length, filterFn, label);
            return fillFrames(frames, groups, label);
        }

        // PART1 문제 = moduleAreas[0] — 스토리 연결 + frame break (사용자 명시 방식)
        if (p1prob.length > 0) {
            if (moduleAreas.length < 1) log.push('[ERR] PART1 문제: module 영역 없음');
            else { fillAreaAsSingleFlow(moduleAreas[0], FILTER_MODULE, p1prob, 'PART1 문제', true); bodyDoneCount++; }
        }
        // PART1 어휘 = largeAreas[0] — 어휘는 frame당 한 본문 유지
        if (p1voc.length > 0) {
            if (largeAreas.length < 1) log.push('[ERR] PART1 어휘: large 영역 없음');
            else { fillAreaPerFrame(largeAreas[0], FILTER_LARGE, p1voc, 'PART1 어휘'); bodyDoneCount++; }
        }
        // PART2 문제 = moduleAreas[1] — 동일하게 스토리 연결 + frame break
        if (p2prob.length > 0) {
            if (moduleAreas.length < 2) log.push('[ERR] PART2 문제: 두 번째 module 영역 없음');
            else { fillAreaAsSingleFlow(moduleAreas[1], FILTER_MODULE, p2prob, 'PART2 문제', true); bodyDoneCount++; }
        }

        // ── 정답 영역 채우기 (narrowAreas[0]=PART1 해설, [1]=PART2 해설) ─
        function findFirstNarrowStory(area) {
            for (var p = 0; p < area.pages.length; p++) {
                var tfs = area.pages[p].textFrames;
                for (var t = 0; t < tfs.length; t++) {
                    try {
                        var b = tfs[t].geometricBounds;
                        var w = b[3] - b[1], h = b[2] - b[0];
                        if (w < 100 && h >= 200) return tfs[t].parentStory;
                    } catch(e) {}
                }
            }
            return null;
        }

        // 정답 영역의 narrow 스토리에 콘텐츠 채우고, 오버플로우 시 영역 안에서만
        // 페이지 복제 + 새 narrow frame을 체인 연결. (PART1/PART2 영역 분리 보장)
        function chainAndFillAnswerArea(area, story, label) {
            var safetyMax = 100;
            var added = 0;
            // 마지막 frame을 계속 추적
            function getLastFrame() {
                try { return story.textContainers[story.textContainers.length - 1]; }
                catch(e) { return null; }
            }
            var lastFrame = getLastFrame();
            while (lastFrame && lastFrame.overflows && added < safetyMax) {
                // area.pages 중 doc.pages에서 가장 뒤 위치 페이지를 lastPage로
                var lastPage = null, maxIdx = -1;
                for (var ai2 = 0; ai2 < area.pages.length; ai2++) {
                    var pg2 = area.pages[ai2];
                    if (!pg2 || !pg2.isValid) continue;
                    for (var di2 = 0; di2 < doc.pages.length; di2++) {
                        if (doc.pages[di2] === pg2) {
                            if (di2 > maxIdx) { maxIdx = di2; lastPage = pg2; }
                            break;
                        }
                    }
                }
                if (!lastPage) {
                    log.push('[ERR] ' + label + ': 영역 마지막 페이지 무효');
                    break;
                }
                var newPage;
                try {
                    newPage = doc.pages.add(LocationOptions.AFTER, lastPage);
                    if (lastPage.appliedMaster) {
                        try { newPage.appliedMaster = lastPage.appliedMaster; } catch(e) {}
                    }
                    clonePageFrames(lastPage, newPage);
                } catch(e) {
                    log.push('[ERR] ' + label + ': 페이지 추가 실패: ' + e.message);
                    break;
                }
                area.pages.push(newPage);

                // 새 페이지의 narrow frame 수집 (좌→우)
                var newFrames = [];
                var newTfs = newPage.textFrames;
                for (var t = 0; t < newTfs.length; t++) {
                    try {
                        var b = newTfs[t].geometricBounds;
                        var w = b[3] - b[1], h = b[2] - b[0];
                        if (w < 100 && h >= 200) {
                            newFrames.push({tf: newTfs[t], y: b[0], x: b[1]});
                        }
                    } catch(e) {}
                }
                newFrames.sort(function(a, b) {
                    if (Math.abs(a.y - b.y) < 5) return a.x - b.x;
                    return a.y - b.y;
                });
                if (newFrames.length === 0) {
                    log.push('[WARN] ' + label + ': 복제 페이지에 narrow frame 없음 - 중단');
                    break;
                }
                // 새 frame을 비우고 체인 끝에 연결 (텍스트 자동 흘러감)
                for (var n = 0; n < newFrames.length; n++) {
                    var nf = newFrames[n].tf;
                    try { nf.contents = ''; } catch(e) {}
                    try {
                        lastFrame.nextTextFrame = nf;
                        lastFrame = nf;
                    } catch(e) {
                        log.push('[ERR] ' + label + ': frame 체인 연결 실패: ' + e.message);
                        return added;
                    }
                }
                added++;
                lastFrame = getLastFrame();
            }
            return added;
        }

        // ── 정답 영역: doc 전체 narrow frame을 스토리 ID 기준 그룹핑 ──
        // 한 스토리 = 한 정답지. 첫 등장 스토리 = PART1 해설, 둘째 = PART2 해설.
        // (페이지 순서가 섞여 있어도 스토리 단위로 정확히 분리됨)
        function findNarrowFrameGroups() {
            var byStory = {};
            var orderedSids = [];
            for (var p = 0; p < doc.pages.length; p++) {
                var pg = doc.pages[p];
                var tfs = pg.textFrames;
                var pageFrames = [];
                for (var t = 0; t < tfs.length; t++) {
                    try {
                        var b = tfs[t].geometricBounds;
                        var w = b[3] - b[1], h = b[2] - b[0];
                        if (w < 100 && h >= 200) {
                            pageFrames.push({tf: tfs[t], pgIdx: p, page: pg, y: b[0], x: b[1]});
                        }
                    } catch(e) {}
                }
                pageFrames.sort(function(a, b) {
                    if (Math.abs(a.y - b.y) < 5) return a.x - b.x;
                    return a.y - b.y;
                });
                for (var k = 0; k < pageFrames.length; k++) {
                    var pf = pageFrames[k];
                    var sid;
                    try { sid = pf.tf.parentStory.id; } catch(e) { continue; }
                    if (!byStory[sid]) {
                        byStory[sid] = {storyId: sid, frames: [], pages: []};
                        orderedSids.push(sid);
                    }
                    byStory[sid].frames.push(pf);
                    var addPg = true;
                    for (var pp = 0; pp < byStory[sid].pages.length; pp++) {
                        if (byStory[sid].pages[pp] === pf.page) { addPg = false; break; }
                    }
                    if (addPg) byStory[sid].pages.push(pf.page);
                }
            }
            var groups = [];
            for (var i = 0; i < orderedSids.length; i++) {
                groups.push(byStory[orderedSids[i]]);
            }
            return groups;
        }

        var narrowGroups = findNarrowFrameGroups();
        log.push('narrowGroups: ' + narrowGroups.length);
        for (var ng = 0; ng < narrowGroups.length; ng++) {
            log.push('  [' + ng + '] frames=' + narrowGroups[ng].frames.length + ' pages=' + narrowGroups[ng].pages.length);
        }

        var ANSWER_KEYS  = ['part1_answer', 'part2_answer'];
        var ANSWER_LABEL = {'part1_answer': 'PART1 해설', 'part2_answer': 'PART2 해설'};
        for (var ai = 0; ai < ANSWER_KEYS.length; ai++) {
            var akey = ANSWER_KEYS[ai];
            var ansList = sections[akey] || [];
            var aLabel = ANSWER_LABEL[akey];
            if (ansList.length === 0) { log.push('── ' + aLabel + ' 단락 없음 ──'); continue; }
            if (ai >= narrowGroups.length) {
                log.push('[ERR] ' + aLabel + ': narrow 그룹 부족');
                continue;
            }
            var grp = narrowGroups[ai];
            var grpFrames = grp.frames;
            // 모든 frame 체인 끊고 재연결
            for (var nfi = 0; nfi < grpFrames.length; nfi++) {
                try { if (grpFrames[nfi].tf.nextTextFrame) grpFrames[nfi].tf.nextTextFrame = null; } catch(e) {}
                try { grpFrames[nfi].tf.contents = ''; } catch(e) {}
            }
            for (var nfi2 = 0; nfi2 < grpFrames.length - 1; nfi2++) {
                try { grpFrames[nfi2].tf.nextTextFrame = grpFrames[nfi2+1].tf; } catch(e) {}
            }
            var ansStory = grpFrames[0].tf.parentStory;
            // 페이지 객체 묶음 (chainAndFillAnswerArea가 사용)
            var grpArea = {cat: 'narrow', pages: grp.pages};
            try {
                replaceAnswerContent(ansStory, ansList);
                var addedPg = chainAndFillAnswerArea(grpArea, ansStory, aLabel);
                log.push(aLabel + ': ' + ansList.length + '개, 페이지 ' + grpArea.pages.length + ' (+' + addedPg + ' 추가) frames ' + ansStory.textContainers.length + ' ✓');
                ansDoneCount++;
            } catch(e) {
                log.push('[ERR] ' + aLabel + ': ' + e.message);
            }
        }

        // ── 빈 페이지 삭제 ───────────────────────────────────────────────
        // deleteEmptyPages 호출 비활성화 (영역 침범 위험 — 빈 페이지는 그대로 두기)
        log.push('빈 페이지 삭제: 비활성화');

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '블랙북 조판 자동화 v6');


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
    log.push('본문조판완료: ' + bodyDoneCount + '개');
    log.push('정답조판완료: ' + ansDoneCount + '개');

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
