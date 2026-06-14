// [ENGINE TEMPLATE] 블랙북 Part 양식 조판 자동화
// 파이프라인: settings.json 로드 → 원본 열기 → 영역별 스토리 채우기 → PDF
// 영역: Part 1 (객관식) / Part 1 어휘 (본문별) / Part 2 (객관식) / 정답
#target indesign
(function() {

    // ── settings.json 로드 ─────────────────────────────────────────────────
    var settingsPath = "__SETTINGS_PATH__";

    var sf = new File(settingsPath);
    sf.encoding = 'UTF-8'; sf.open('r');
    var settings = eval("(" + sf.read() + ")");
    sf.close();

    var jsonPath  = settings.json_path;
    var outputDir = settings.output_dir;
    var inddPath  = settings.indd_path;
    var issueNum  = settings.issue_num ? String(settings.issue_num) : '';

    // ── content.json 로드 ─────────────────────────────────────────────────
    var jf = new File(jsonPath);
    jf.encoding = 'UTF-8'; jf.open('r');
    var data = eval("(" + jf.read() + ")");
    jf.close();

    if (!data || data.format !== 'part' || !data.parts) { return; }

    var part1 = data.parts.part1 || [];
    var part2 = data.parts.part2 || [];
    var vocabPassages = data.parts.vocab || [];
    var answers = data.answers || [];

    // ── 조기 로그 ─────────────────────────────────────────────────────────
    var _earlyLog = new File(outputDir + '/조판_로그.txt');
    _earlyLog.encoding = 'UTF-8'; _earlyLog.open('w');
    _earlyLog.write('Part 조판 시작: ' + new Date().toString());
    _earlyLog.close();

    // ── InDesign 파일 열기 ────────────────────────────────────────────────
    var workFile = new File(inddPath);
    var doc = null;
    try {
        for (var di = 0; di < app.documents.length; di++) {
            try {
                if (app.documents[di].fullName.fsName === workFile.fsName) {
                    doc = app.documents[di]; break;
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
    function findPStyle(name) {
        var all = doc.allParagraphStyles;
        for (var i = 0; i < all.length; i++) {
            if (all[i].name === name) return all[i];
        }
        return null;
    }

    var GRP_DOK   = '독해';        // 독해
    var GRP_VOC   = 'Vocabulary+';
    var GRP_ANS   = '정답 및 해설';  // 정답 및 해설

    // 독해 스타일
    var stProblem  = findPStyle('문제');                              // 문제
    var stSeonji   = findPStyle('!선지');                             // !선지
    var stBogi     = findPStyle('보기');                              // 보기
    var stNextQ    = findPStyle('다음 글을 읽고 물음에 답하시오');  // 다음 글을 읽고~
    if (!stNextQ) stNextQ = findPStyle('다음 글을 읽고');
    var stTitle    = findPStyle('제목');                              // 제목
    var stBox      = findPStyle('!박스_지문');                // !박스_지문

    // Vocabulary+ 스타일
    var stCategory = findPStyle('카테고리');                  // 카테고리
    var stVocab    = findPStyle('!연관 어휘');                // !연관 어휘
    var stEngDef   = findPStyle('!영영풀이');                 // !영영풀이
    var stSaying   = findPStyle('!속담');                             // !속담

    // 정답 스타일
    var stAnswer   = findPStyle('정답');                              // 정답
    var stExplain  = findPStyle('해설');                              // 해설

    var noneCharStyle = doc.characterStyles[0];

    // 진단용
    var missing = [];
    if (!stProblem) missing.push('문제');
    if (!stBox)     missing.push('!박스_지문');
    if (!stCategory) missing.push('카테고리');
    if (!stVocab)    missing.push('!연관 어휘');

    // ── 영역별 단락 스타일 매핑 ───────────────────────────────────────────
    function typeToStyleProblem(typ) {
        if (typ === 'problem')         return stProblem;
        if (typ === 'choice')          return stSeonji;
        if (typ === 'condition')       return stSeonji;
        if (typ === 'condition_item')  return stSeonji;
        if (typ === 'answer_blank')    return stSeonji;
        if (typ === 'next_question')   return stNextQ;
        if (typ === 'passage_header')  return stNextQ;
        if (typ === 'summary_label')   return stBox;
        if (typ === 'summary_content') return stBox;
        if (typ === 'example_label')   return stBogi;
        if (typ === 'example_content') return stBogi;
        return stBox;  // passage 기본
    }

    function typeToStyleVocab(typ) {
        if (typ === 'passage_text') return stBox;
        if (typ === 'category')     return stCategory;
        if (typ === 'vocab')        return stVocab;
        if (typ === 'english_def')  return stEngDef;
        if (typ === 'saying')       return stSaying;
        return stBox;
    }

    // ── 메인 스토리 식별 ──────────────────────────────────────────────────
    // 가장 큰 스토리 = Part1 메인. 그 외 스토리에서 Part2/어휘/정답 식별.
    // 원본 .indd 구조에 따라 식별 방식이 달라지므로 라벨 기반 fallback도 제공.
    function findStoryByLabel(label) {
        // 텍스트프레임의 label 속성으로 검색
        for (var p = 0; p < doc.pages.length; p++) {
            var tfs = doc.pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    if (tfs[t].label === label) {
                        return tfs[t].parentStory;
                    }
                } catch(e) {}
            }
        }
        return null;
    }

    var storyPart1 = findStoryByLabel('part1');
    var storyPart2 = findStoryByLabel('part2');
    var storyVocab = findStoryByLabel('vocab');
    var storyAnswer = findStoryByLabel('answer');

    // Fallback: 라벨이 없으면 컨테이너 수 기준 정렬
    if (!storyPart1 || !storyPart2 || !storyVocab) {
        var sortedStories = [];
        for (var si = 0; si < doc.stories.length; si++) {
            var st = doc.stories[si];
            if (st.textContainers.length > 0) sortedStories.push(st);
        }
        sortedStories.sort(function(a, b) {
            return b.textContainers.length - a.textContainers.length;
        });
        if (!storyPart1) storyPart1 = sortedStories[0] || null;
        if (!storyVocab) storyVocab = sortedStories[1] || null;
        if (!storyPart2) storyPart2 = sortedStories[2] || null;
        if (!storyAnswer) storyAnswer = sortedStories[3] || null;
    }

    // ── 스토리 채우기 ─────────────────────────────────────────────────────
    function fillStory(story, paragraphs, typeToStyle) {
        if (!story || !story.isValid || !paragraphs || paragraphs.length === 0) return;
        var fullText = '';
        for (var i = 0; i < paragraphs.length; i++) {
            fullText += paragraphs[i].text;
            if (i < paragraphs.length - 1) fullText += '\r';
        }
        story.contents = fullText;

        var paras = story.paragraphs;
        for (var i = 0; i < paragraphs.length && i < paras.length; i++) {
            try { paras[i].appliedCharacterStyle = noneCharStyle; } catch(e) {}
            var sty = typeToStyle(paragraphs[i].type);
            if (sty) {
                try { paras[i].appliedParagraphStyle = sty; } catch(e) {}
            }
        }
    }

    // Vocab 영역: 본문별 passages 펼치기. 본문 사이에 FRAME_BREAK.
    function buildVocabParagraphs(passages) {
        var flat = [];
        for (var pi = 0; pi < passages.length; pi++) {
            var pp = passages[pi];
            if (pi > 0) {
                // 본문 사이 FRAME_BREAK 신호용 빈 단락
                flat.push({ text: '__FRAME_BREAK__', type: 'frame_break' });
            }
            for (var k = 0; k < pp.paragraphs.length; k++) {
                flat.push(pp.paragraphs[k]);
            }
        }
        return flat;
    }

    function fillVocabStory(story, passages) {
        if (!story || !story.isValid || passages.length === 0) return;
        var paragraphs = buildVocabParagraphs(passages);
        if (paragraphs.length === 0) return;

        var fullText = '';
        for (var i = 0; i < paragraphs.length; i++) {
            fullText += paragraphs[i].text;
            if (i < paragraphs.length - 1) fullText += '\r';
        }
        story.contents = fullText;

        var paras = story.paragraphs;
        for (var i = 0; i < paragraphs.length && i < paras.length; i++) {
            try { paras[i].appliedCharacterStyle = noneCharStyle; } catch(e) {}
            if (paragraphs[i].type === 'frame_break') {
                try {
                    paras[i].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
                    paras[i].contents = '';
                } catch(e) {}
                continue;
            }
            var sty = typeToStyleVocab(paragraphs[i].type);
            if (sty) {
                try { paras[i].appliedParagraphStyle = sty; } catch(e) {}
            }
        }
    }

    function insertFrameBreaksProblem(story) {
        var paras = story.paragraphs;
        var breakIdx = [];
        var nqPending = false;
        for (var i = 0; i < paras.length; i++) {
            var sty = paras[i].appliedParagraphStyle;
            if (sty === stNextQ) {
                breakIdx.push(i);
                nqPending = true;
            } else if (sty === stProblem) {
                if (!nqPending) breakIdx.push(i);
                nqPending = false;
            }
        }
        for (var k = breakIdx.length - 1; k >= 1; k--) {
            try {
                paras = story.paragraphs;
                paras[breakIdx[k]].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
            } catch(e) {}
        }
    }

    function fillAnswerStory(story, ansList) {
        if (!story || !story.isValid || ansList.length === 0) return;
        var lines = [];
        var types = [];
        for (var i = 0; i < ansList.length; i++) {
            var a = ansList[i];
            lines.push(String(a.num));
            types.push('num');
            lines.push('[정답] ' + (a.answer || ''));
            types.push('answer');
            if (a.explanation) {
                lines.push('[해설] ' + a.explanation);
                types.push('explain');
            }
        }
        story.contents = lines.join('\r');
        var paras = story.paragraphs;
        for (var pi = 0; pi < types.length && pi < paras.length; pi++) {
            try { paras[pi].appliedCharacterStyle = noneCharStyle; } catch(e) {}
            var sty;
            if (types[pi] === 'num')         sty = stAnswer;
            else if (types[pi] === 'answer') sty = stAnswer;
            else                             sty = stExplain;
            if (sty) {
                try { paras[pi].appliedParagraphStyle = sty; } catch(e) {}
            }
        }
    }

    var log = ['=== 블랙북 Part 조판 ==='];
    log.push(new Date().toString());
    if (missing.length > 0) {
        log.push('[경고] 누락 스타일: ' + missing.join(', '));
    }
    log.push('Part1: ' + part1.length + '개 단락');
    log.push('Vocab: ' + vocabPassages.length + '개 본문');
    log.push('Part2: ' + part2.length + '개 단락');
    log.push('정답: ' + answers.length + '개');

    app.doScript(function() {

        // 주차 텍스트 치환 (있는 경우)
        if (issueNum) {
            var weekText = issueNum + '주 차';
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = '\\d+주.?차';
            app.changeGrepPreferences.changeTo = weekText;
            try { doc.changeGrep(); } catch(e) {}
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        }

        if (storyPart1) {
            fillStory(storyPart1, part1, typeToStyleProblem);
            insertFrameBreaksProblem(storyPart1);
            log.push('Part1 제판 완료');
        } else {
            log.push('[경고] Part1 스토리 없음');
        }

        if (storyVocab) {
            fillVocabStory(storyVocab, vocabPassages);
            log.push('Vocab 제판 완료');
        } else if (vocabPassages.length > 0) {
            log.push('[경고] Vocab 스토리 없음');
        }

        if (storyPart2) {
            fillStory(storyPart2, part2, typeToStyleProblem);
            insertFrameBreaksProblem(storyPart2);
            log.push('Part2 제판 완료');
        } else if (part2.length > 0) {
            log.push('[경고] Part2 스토리 없음');
        }

        if (storyAnswer && answers.length > 0) {
            fillAnswerStory(storyAnswer, answers);
            log.push('정답 제판 완료');
        }

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '블랙북 Part 조판');

    // 오버플로우 체크
    var overflows = 0;
    var tfs = doc.textFrames;
    for (var i = 0; i < tfs.length; i++) {
        try { if (tfs[i].overflows) overflows++; } catch(e) {}
    }
    log.push('');
    log.push('오버플로우: ' + overflows + '개');
    log.push('Part조판완료');

    // PDF 내보내기
    try {
        var pdfPath = inddPath.replace(/\.indd$/i, '.pdf');
        var preset = app.pdfExportPresets.itemByName('[PDF/X-1a:2001]');
        doc.exportFile(ExportFormat.PDF_TYPE, new File(pdfPath), false,
                       preset.isValid ? preset : undefined);
        log.push('PDF: 성공');
    } catch(e) {
        log.push('PDF: 실패 - ' + e.message);
    }

    try { doc.save(workFile); } catch(e) {}

    var logFile = new File(outputDir + '/조판_로그.txt');
    logFile.encoding = 'UTF-8'; logFile.open('w');
    logFile.write(log.join('\n'));
    logFile.close();

})();
