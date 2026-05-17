// [ENGINE TEMPLATE] 화이트북 조판 자동화 v3
// - 정답지: dayNum-agnostic (모든 Day 동일 패턴). A=아이콘pos0, B/C/D/E=pos1. D→E 사이만 빈줄
// - D 단어 박스: ①②.. 앞 공백을 \r로 치환 (사용자 요청 GREP)
// - 연습문제: WEEK별 본문(F-마스터)/정답(C-마스터 비-Day스토리) 스토리 자동 식별, 채우기, 밑줄 적용
#target indesign
(function() {
    // Dialog/alert 자동 무시 — 폰트/링크 누락 시 자동화 중단 방지
    try { app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT; } catch(_e){}
__SETTINGS_PATH__

    var sf = new File(settingsPath);
    sf.encoding = 'UTF-8'; sf.open('r');
    var settings = eval("(" + sf.read() + ")");
    sf.close();

    var jsonPath = settings.json_path;
    var outputDir = settings.output_dir;
    var inddPath = settings.indd_path;
    var issueNum = settings.issue_num ? String(settings.issue_num) : '';

    var f = new File(jsonPath);
    f.encoding = 'UTF-8'; f.open('r');
    var data = eval("(" + f.read() + ")");
    f.close();

    if (!data || !data.days || data.days.length === 0) { return; }

    // ── 작업 파일 확보 (구글드라이브 동일 이름 원본 → 작업 경로 복사 후 열기) ──
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
            $.sleep(3000);
            if (!doc || !doc.isValid) doc = app.activeDocument;
        }
    } catch(initErr) {
        doc = app.activeDocument;
    }
    if (!doc || !doc.isValid) { return; }
    app.activeDocument = doc;

    var STYLES = {
        A_word: 'A 어휘',
        B_eng: 'C 예문',
        B_kor: 'C 예문 사본',
        C_bogis: 'C 단어 박스',
        C_def: 'D 영영사전',
        D_box: 'D 단어 박스 new',
        D_item: 'D 단어 new',
        D_item_old: 'D 단어',
        E_sent: 'E 전치사',
        ANS_hdr:  '정답_',
        ANS_item: '정답지 번호',
        ANS_sol:  '해설_',
        PRAC_q: '문제',
        PRAC_choice: '선지',
        PRAC_bogi: '보기',
        CHAR_U: '밑줄'   // 밑줄 (문자 스타일)
    };

    function getStyle(name) {
        var s = doc.paragraphStyles.itemByName(name);
        if (s.isValid) return s;
        for (var gi = 0; gi < doc.paragraphStyleGroups.length; gi++) {
            var grp = doc.paragraphStyleGroups[gi];
            var gs = grp.paragraphStyles.itemByName(name);
            if (gs.isValid) return gs;
        }
        return doc.paragraphStyles[0];
    }

    function getCharStyle(name) {
        var s = doc.characterStyles.itemByName(name);
        if (s.isValid) return s;
        for (var gi = 0; gi < doc.characterStyleGroups.length; gi++) {
            var grp = doc.characterStyleGroups[gi];
            var gs = grp.characterStyles.itemByName(name);
            if (gs.isValid) return gs;
        }
        return null;
    }

    function replaceContent(story, items) {
        if (!story || !story.isValid || !items || items.length === 0) return false;
        var fullText = '';
        for (var i = 0; i < items.length; i++) {
            fullText += items[i].text;
            if (i < items.length - 1) fullText += '\r';
        }
        story.contents = fullText;
        story.characters.everyItem().appliedCharacterStyle = doc.characterStyles[0];
        var paras = story.paragraphs;
        for (var i = 0; i < items.length && i < paras.length; i++) {
            paras[i].appliedParagraphStyle = getStyle(items[i].sty);
        }
        return true;
    }

    var HEIGHT_ONLY_VAL = 1751476583;
    function expandChainLastFrame(story) {
        if (!story || !story.isValid) return;
        try {
            var c = story.textContainers;
            if (c.length > 0) c[c.length - 1].textFramePreferences.autoSizingType = HEIGHT_ONLY_VAL;
        } catch(e) {}
    }

    function expandFrameAndMoveBelow(story, moveStyles) {
        if (!story || !story.isValid) return;
        try {
            var c = story.textContainers;
            if (c.length === 0) return;
            var frame = c[0];
            var oldGb = frame.geometricBounds;
            var oldTop = oldGb[0], oldBot = oldGb[2];
            frame.textFramePreferences.autoSizingType = HEIGHT_ONLY_VAL;
            var measuredGb = frame.geometricBounds;
            var measuredHeight = measuredGb[2] - measuredGb[0];
            frame.textFramePreferences.autoSizingType = 1330005536;
            frame.geometricBounds = [oldTop, oldGb[1], oldTop + measuredHeight, oldGb[3]];
            var newBot = oldTop + measuredHeight;
            var delta = newBot - oldBot;
            if (delta < 0.01) return;
            var pg = frame.parentPage;
            if (!pg) return;
            var tfs = pg.textFrames;
            for (var i = 0; i < tfs.length; i++) {
                try {
                    var other = tfs[i];
                    if (other.parentStory === story) continue;
                    if (other.parentStory.paragraphs.length === 0) continue;
                    var osty = other.parentStory.paragraphs[0].appliedParagraphStyle.name;
                    for (var s = 0; s < moveStyles.length; s++) {
                        if (osty === moveStyles[s]) {
                            var ob = other.geometricBounds;
                            other.geometricBounds = [ob[0]+delta, ob[1], ob[2]+delta, ob[3]];
                            break;
                        }
                    }
                } catch(e2) {}
            }
        } catch(e) {}
    }

    // ── 섹션 아이콘 (A~E) ──
    var ICON_COLORS = [
        [65, 36, 22, 0],
        [19, 42, 56, 0],
        [52, 27, 39, 9],
        [20, 41, 10, 0],
        [44, 43, 52, 0]
    ];
    var ICON_LETTERS = ['A', 'B', 'C', 'D', 'E'];

    function findOrCreateColor(c, m, y, k) {
        for (var ci = 0; ci < doc.colors.length; ci++) {
            try {
                var col = doc.colors[ci];
                var v = col.colorValue;
                if (v && Math.abs(v[0]-c)<0.5 && Math.abs(v[1]-m)<0.5 &&
                    Math.abs(v[2]-y)<0.5 && Math.abs(v[3]-k)<0.5) return col;
            } catch(e) {}
        }
        return doc.colors.add({
            model: ColorModel.PROCESS,
            space: ColorSpace.CMYK,
            colorValue: [c, m, y, k],
            name: 'SecIcon_' + c + '_' + m + '_' + y + '_' + k
        });
    }

    function insertSectionIcon(para, sectionIdx) {
        var letter = ICON_LETTERS[sectionIdx];
        var cv = ICON_COLORS[sectionIdx];
        var color = findOrCreateColor(cv[0], cv[1], cv[2], cv[3]);
        var page = para.parentTextFrames[0].parentPage;
        var tf = page.textFrames.add();
        tf.geometricBounds = [0, 0, 6.3, 6.3];
        tf.fillColor = color;
        tf.strokeColor = color;
        tf.strokeWeight = 1;
        tf.contents = letter;
        var tp = tf.parentStory.paragraphs[0];
        tp.pointSize = 12;
        try { tp.appliedFont = doc.fonts.itemByName('고도 B\tRegular'); } catch(e) {
            try { tp.appliedFont = app.fonts.itemByName('Godo B\tRegular'); } catch(e2) {}
        }
        tp.justification = Justification.CENTER_ALIGN;
        tp.fillColor = doc.colors.itemByName('Paper');
        // FIXED v3: A=pos0, BCDE=pos1 (사용자 수정본 분석 결과)
        var ipIdx = (sectionIdx === 0) ? 0 : 1;
        var ip = para.insertionPoints[ipIdx];
        tf.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
        tf.anchoredObjectSettings.anchorYoffset = -0.72;
    }

    function postProcessAnswerStory(story) {
        var paras = story.paragraphs;
        var ANS_HDR  = STYLES.ANS_hdr;
        var ANS_ITEM = STYLES.ANS_item;
        var ANS_SOL  = STYLES.ANS_sol;
        var hdrIndices = [];
        var firstAnsOfSection = [];
        var solIndices = [];
        var currentSection = -1;
        var sectionHadFirstAns = [];
        for (var i = 0; i < paras.length; i++) {
            var sty = paras[i].appliedParagraphStyle.name;
            if (sty === ANS_HDR) {
                currentSection++;
                hdrIndices.push(i);
                sectionHadFirstAns.push(false);
            } else if (sty === ANS_ITEM) {
                if (currentSection >= 0 && !sectionHadFirstAns[currentSection]) {
                    sectionHadFirstAns[currentSection] = true;
                    firstAnsOfSection.push({section: currentSection, idx: i});
                }
            } else if (sty === ANS_SOL) {
                var txt = paras[i].contents.replace(/\r/g, '');
                if (txt.indexOf('[문제') >= 0) solIndices.push(i);
            }
        }
        for (var s = 0; s < firstAnsOfSection.length; s++) {
            if (firstAnsOfSection[s].section > 0) {
                try { paras[firstAnsOfSection[s].idx].numberingContinue = false; } catch(e) {}
            }
        }
        for (var s = 0; s < solIndices.length; s++) {
            var nextIdx = solIndices[s] + 1;
            if (nextIdx < paras.length && paras[nextIdx].appliedParagraphStyle.name === ANS_ITEM) {
                try { paras[nextIdx].numberingContinue = false; } catch(e) {}
            }
        }
        // "정답" 문자 스타일
        var charSty = getCharStyle('정답');
        if (charSty) {
            for (var h = 0; h < hdrIndices.length; h++) {
                var para = paras[hdrIndices[h]];
                var content = para.contents;
                for (var c = 0; c < content.length - 1; c++) {
                    if (content.charAt(c) === '정' && content.charAt(c + 1) === '답') {
                        try {
                            para.characters[c].appliedCharacterStyle = charSty;
                            para.characters[c + 1].appliedCharacterStyle = charSty;
                        } catch(e) {}
                    }
                }
            }
        }
        for (var h = 0; h < Math.min(hdrIndices.length, 5); h++) {
            try { insertSectionIcon(paras[hdrIndices[h]], h); } catch(e) {}
        }
    }

    function getStoriesByFirstStyle(styleName) {
        var found = [], seen = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var tfs = doc.pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var story = tfs[t].parentStory;
                if (seen[story.id]) continue;
                if (story.paragraphs.length > 0 &&
                    story.paragraphs[0].appliedParagraphStyle.name === styleName) {
                    seen[story.id] = true;
                    found.push(story);
                }
            }
        }
        return found;
    }

    function getAnswerStories() {
        var found = [], seen = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var tfs = doc.pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var story = tfs[t].parentStory;
                if (seen[story.id]) continue;
                if (story.paragraphs.length > 1) {
                    var firstPara = story.paragraphs[0];
                    var txt = firstPara.contents.replace(/￼/g,'').replace(/\r/g,'').replace(/^\s+/,'');
                    var secondSty = story.paragraphs[1].appliedParagraphStyle.name;
                    if (txt.indexOf('정답') >= 0 && secondSty === STYLES.ANS_item) {
                        seen[story.id] = true;
                        found.push(story);
                    }
                }
            }
        }
        return found;
    }

    // 연습문제 본문 스토리: F-마스터 시작 페이지의 가장 위·왼쪽 본문 TF
    function getPracticeMainStories() {
        var found = [], seen = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            var mname = '';
            try { mname = page.appliedMaster ? page.appliedMaster.name : ''; } catch(e){}
            if (mname !== 'F-마스터') continue;
            var tfs = page.textFrames;
            // 본문 영역 TF 후보 수집
            var candidates = [];
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var gb = tfs[t].geometricBounds;
                    if (gb[1] < 19.5) continue;     // 사이드바 제외
                    if (gb[3] - gb[1] < 50) continue; // 좁은 프레임 제외
                    if (gb[2] - gb[0] < 50) continue; // 높이 부족 제외
                    candidates.push({tf: tfs[t], gb: gb});
                } catch(e){}
            }
            // y 작은 → x 작은 순 정렬, 첫 후보를 thread head 후보로
            candidates.sort(function(a,b){
                if (Math.abs(a.gb[0] - b.gb[0]) > 5) return a.gb[0] - b.gb[0];
                return a.gb[1] - b.gb[1];
            });
            for (var ci = 0; ci < candidates.length; ci++) {
                var tf = candidates[ci].tf;
                var st = tf.parentStory;
                if (seen[st.id]) continue;
                // 스토리의 첫 textContainer 페이지가 이 페이지인지(즉 시작점) 확인
                try {
                    var firstContainer = st.textContainers[0];
                    if (firstContainer && firstContainer.parentPage &&
                        firstContainer.parentPage.id !== page.id) continue;
                } catch(e){}
                seen[st.id] = true;
                found.push(st);
                break;
            }
        }
        return found;
    }

    // 연습문제 정답 스토리: C-마스터 페이지 본문 TF 중 Day 정답 아닌 스토리
    function getPracticeAnswerStories(dayAnsStories) {
        var dayAnsIds = {};
        for (var i = 0; i < dayAnsStories.length; i++) dayAnsIds[dayAnsStories[i].id] = true;
        var found = [], seen = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            var mname = '';
            try { mname = page.appliedMaster ? page.appliedMaster.name : ''; } catch(e){}
            if (mname !== 'C-마스터') continue;
            var tfs = page.textFrames;
            var candidates = [];
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var gb = tfs[t].geometricBounds;
                    // 본문 큰 박스만 (사이드 작은 TF 제외)
                    if (gb[1] < 19.5) continue;
                    if (gb[3] - gb[1] < 100) continue;  // width >= 100
                    if (gb[2] - gb[0] < 100) continue;  // height >= 100
                    candidates.push({tf: tfs[t], gb: gb});
                } catch(e){}
            }
            candidates.sort(function(a,b){
                if (Math.abs(a.gb[0] - b.gb[0]) > 5) return a.gb[0] - b.gb[0];
                return a.gb[1] - b.gb[1];
            });
            for (var ci = 0; ci < candidates.length; ci++) {
                var st = candidates[ci].tf.parentStory;
                if (dayAnsIds[st.id]) continue;
                if (seen[st.id]) continue;
                // 스토리 시작 페이지 = 이 페이지인지
                try {
                    var firstContainer = st.textContainers[0];
                    if (firstContainer && firstContainer.parentPage &&
                        firstContainer.parentPage.id !== page.id) continue;
                } catch(e){}
                seen[st.id] = true;
                found.push(st);
                break;
            }
        }
        return found;
    }

    // ── GREP: D 박스 ① 앞 공백 → \r ──
    function applyOnesGrep(story) {
        if (!story || !story.isValid) return;
        try {
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = ' +(?=[\\x{2460}-\\x{2473}\\x{3251}-\\x{325F}\\x{32B1}-\\x{32BF}])';
            app.changeGrepPreferences.changeTo = '\\r';
            story.changeGrep();
        } catch(e) {}
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    }

    // ── GREP: <u>...</u> 마커 → 밑줄 문자 스타일 ──
    function applyUnderlineMarkers(story) {
        if (!story || !story.isValid) return;
        var cs = getCharStyle(STYLES.CHAR_U);
        if (!cs) return;
        try {
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = '<u>(.+?)</u>';
            app.changeGrepPreferences.changeTo = '$1';
            app.changeGrepPreferences.appliedCharacterStyle = cs;
            story.changeGrep();
        } catch(e) {}
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
    }

    // ── Day 정답 빌더 (dayNum-agnostic) ──
    function buildAnswerItems(answers) {
        var items = [];
        if (!answers || !answers.A) return items;

        // A (1. word : meaning)
        for (var i = 0; i < answers.A.length; i++) {
            var a = answers.A[i];
            items.push({text: a.num + '. ' + a.word + ' : ' + a.meaning, sty: STYLES.ANS_item});
        }
        // B (header pos1 → 공백2 + 정답)
        items.push({text: '  정답', sty: STYLES.ANS_hdr});
        if (answers.B) for (var i = 0; i < answers.B.length; i++)
            items.push({text: answers.B[i].answer, sty: STYLES.ANS_item});

        // C
        items.push({text: '  정답', sty: STYLES.ANS_hdr});
        if (answers.C) {
            for (var i = 0; i < answers.C.length; i++) {
                var c = answers.C[i];
                if (i > 0) items.push({text: '', sty: STYLES.ANS_sol});
                items.push({text: '[문제 ' + c.set + ']', sty: STYLES.ANS_sol});
                for (var j = 0; j < c.answers.length; j++)
                    items.push({text: c.answers[j], sty: STYLES.ANS_item});
            }
        }

        // D
        items.push({text: '  정답', sty: STYLES.ANS_hdr});
        if (answers.D) for (var i = 0; i < answers.D.length; i++) {
            var d = answers.D[i];
            items.push({text: d.word + ' : ' + d.answer, sty: STYLES.ANS_item});
        }

        // E: 빈줄 + 헤더
        items.push({text: '', sty: STYLES.ANS_sol});
        items.push({text: '  정답', sty: STYLES.ANS_hdr});
        if (answers.E) for (var i = 0; i < answers.E.length; i++)
            items.push({text: answers.E[i].sentence, sty: STYLES.ANS_item});

        return items;
    }

    var aList    = getStoriesByFirstStyle(STYLES.A_word);
    var bList    = getStoriesByFirstStyle(STYLES.B_eng);
    var cList    = getStoriesByFirstStyle(STYLES.C_bogis);
    var dBoxList = getStoriesByFirstStyle(STYLES.D_box);
    var dItemList= getStoriesByFirstStyle(STYLES.D_item);
    var eList    = getStoriesByFirstStyle(STYLES.E_sent);
    var ansList  = getAnswerStories();
    var pracMainList = getPracticeMainStories();
    var pracAnsList  = getPracticeAnswerStories(ansList);

    var log = ['=== 화이트북 조판 자동화 v3 ==='];
    log.push(new Date().toString());
    log.push('');
    log.push('발견된 스토리 수:');
    log.push('  A어휘: ' + aList.length + ' (예상: 10)');
    log.push('  B문장: ' + bList.length + ' (예상: 10)');
    log.push('  C영영사전: ' + cList.length + ' (예상: 10)');
    log.push('  D보기: ' + dBoxList.length + ' (예상: 10)');
    log.push('  D항목(D단어new): ' + dItemList.length + ' (예상: 8)');
    log.push('  E전치사: ' + eList.length + ' (예상: 10)');
    log.push('  정답: ' + ansList.length + ' (예상: 10)');
    log.push('  연습문제본문: ' + pracMainList.length + ' (예상: 3)');
    log.push('  연습문제답지: ' + pracAnsList.length + ' (예상: 3)');
    log.push('  처리 Day: ' + data.days.length);
    log.push('  처리 Week: ' + (data.practices ? data.practices.length : 0));
    log.push('');

    app.doScript(function() {

        // 주차 텍스트 치환
        if (issueNum) {
            var weekText = issueNum + '주 차';
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = '\\d+주.?차';
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
            log.push('주차 텍스트 치환: ' + weekText);
        }

        for (var di = 0; di < data.days.length; di++) {
            var day = data.days[di];
            var content = day.content;
            var answers = day.answers;
            var dayNum = day.day_num;
            log.push('── Day ' + dayNum + ' (idx=' + di + ') ──');

            // A
            if (di < aList.length && content.A && content.A.length > 0) {
                var items = [];
                for (var i = 0; i < content.A.length; i++) {
                    var rawText = content.A[i].raw || (content.A[i].num + '. ' + content.A[i].word);
                    items.push({text: rawText, sty: STYLES.A_word});
                }
                replaceContent(aList[di], items);
                log.push('  A: ' + content.A.length + '단어 ✓');
            }

            // B
            if (di < bList.length && content.B && content.B.length > 0) {
                var items = [];
                for (var i = 0; i < content.B.length; i++) {
                    var b = content.B[i];
                    items.push({text: b.num + '. ' + b.eng, sty: STYLES.B_eng});
                    if (b.kor) items.push({text: b.kor, sty: STYLES.B_kor});
                }
                replaceContent(bList[di], items);
                expandChainLastFrame(bList[di]);
                log.push('  B: ' + content.B.length + '문장 ✓');
            }

            // C
            if (di < cList.length && content.C && content.C.length > 0) {
                var items = [];
                for (var s = 0; s < content.C.length; s++) {
                    var cSet = content.C[s];
                    var bogisText = '「보기」  ' + cSet.bogis.join('  /  ');
                    items.push({text: bogisText, sty: STYLES.C_bogis});
                    for (var dd = 0; dd < cSet.defs.length; dd++) {
                        items.push({text: cSet.defs[dd], sty: STYLES.C_def});
                    }
                }
                replaceContent(cList[di], items);
                log.push('  C: ' + content.C.length + '세트 ✓');
            }

            // D — 모든 Day 동일 처리 (사용자 수정본 분석 결과)
            if (di < dBoxList.length && content.D) {
                // D 보기 박스: 〈보기〉 첫 줄 제거하고 채우기
                if (content.D.bogis_raw && content.D.bogis_raw.length > 0) {
                    var items = [];
                    for (var i = 0; i < content.D.bogis_raw.length; i++) {
                        var raw = content.D.bogis_raw[i];
                        if (raw.indexOf('〈보기〉') === 0) continue; // 〈보기〉 헤더 스킵
                        items.push({text: raw, sty: STYLES.D_box});
                    }
                    if (items.length > 0) {
                        replaceContent(dBoxList[di], items);
                        applyOnesGrep(dBoxList[di]);
                        expandFrameAndMoveBelow(dBoxList[di],
                            ['D 단어 new', '발문', 'E 전치사']);
                        log.push('  D보기: ' + items.length + '줄 ✓');
                    }
                }
                // D 항목 (모든 Day, di 그대로 매핑)
                if (di < dItemList.length && content.D.items && content.D.items.length > 0) {
                    var items = [];
                    for (var i = 0; i < content.D.items.length; i++) {
                        items.push({text: content.D.items[i].text, sty: STYLES.D_item});
                    }
                    replaceContent(dItemList[di], items);
                    log.push('  D항목: ' + content.D.items.length + '개 ✓');
                }
            }

            // E
            if (di < eList.length && content.E && content.E.length > 0) {
                var items = [];
                for (var i = 0; i < content.E.length; i++) {
                    var e = content.E[i];
                    items.push({text: e.num + '. ' + e.text, sty: STYLES.E_sent});
                }
                replaceContent(eList[di], items);
                log.push('  E: ' + content.E.length + '문장 ✓');
            }

            // 정답
            var ansIdx = di;
            if (ansIdx < ansList.length && answers && answers.A && answers.A.length > 0) {
                var ansItems = buildAnswerItems(answers);
                // A 헤더: " 정답" (공백1, 아이콘 pos 0) — 사용자 수정본 분석 결과
                var allItems = [{text: ' 정답', sty: STYLES.ANS_hdr}];
                for (var i = 0; i < ansItems.length; i++) allItems.push(ansItems[i]);
                replaceContent(ansList[ansIdx], allItems);
                postProcessAnswerStory(ansList[ansIdx]);
                var ansC = ansList[ansIdx].textContainers;
                if (ansC.length > 1) {
                    var ansF1 = ansC[1];
                    var ansGb = ansF1.geometricBounds;
                    ansF1.geometricBounds = [20, 23, ansGb[2], 190];
                    ansF1.textFramePreferences.autoSizingType = 1330005536;
                }
                log.push('  정답(Day' + dayNum + '): ' + allItems.length + '단락 ✓');
            }
        }

        // ── 연습문제 본문 + 답지 처리 ──
        if (data.practices) {
            for (var w = 0; w < data.practices.length; w++) {
                var prac = data.practices[w];
                // 본문
                if (w < pracMainList.length && prac.questions && prac.questions.length > 0) {
                    var items = [];
                    for (var qi = 0; qi < prac.questions.length; qi++) {
                        var q = prac.questions[qi];
                        for (var li = 0; li < q.lines.length; li++) {
                            var ln = q.lines[li];
                            items.push({text: ln.text, sty: ln.sty});
                        }
                        if (qi < prac.questions.length - 1)
                            items.push({text: '', sty: STYLES.PRAC_choice});
                    }
                    replaceContent(pracMainList[w], items);
                    applyUnderlineMarkers(pracMainList[w]);
                    log.push('연습문제 본문 WEEK' + prac.week + ': ' + prac.questions.length + '문제 ✓');
                }
                // 답지
                if (w < pracAnsList.length && prac.answers && prac.answers.length > 0) {
                    var items = [];
                    for (var ai = 0; ai < prac.answers.length; ai++) {
                        var a = prac.answers[ai];
                        for (var li = 0; li < a.lines.length; li++) {
                            var ln = a.lines[li];
                            items.push({text: ln.text, sty: ln.sty});
                        }
                    }
                    replaceContent(pracAnsList[w], items);
                    applyUnderlineMarkers(pracAnsList[w]);
                    log.push('연습문제 답지 WEEK' + prac.week + ': ' + prac.answers.length + '문제 ✓');
                }
            }
        }

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '화이트북 조판 자동화 v3');

    // 오버플로우 체크
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

    var logFile = new File(outputDir + '/조판_로그.txt');
    logFile.encoding = 'UTF-8'; logFile.open('w');
    logFile.write(log.join('\n'));
    logFile.close();

    doc.save();

    var pdfFile = new File(outputDir + '/' + doc.name.replace(/\.indd$/i, '') + '.pdf');
    var pdfOk = false;
    try {
        var preset = app.pdfExportPresets.itemByName('[고품질 인쇄]');
        if (!preset.isValid) preset = app.pdfExportPresets.itemByName('[High Quality Print]');
        if (preset.isValid) doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false, preset);
        else doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false);
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
