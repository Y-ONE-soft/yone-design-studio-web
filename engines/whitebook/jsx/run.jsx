// 화이트북 조판 자동화 (수정판 v2)
// - D items 인덱스 오류 수정 (Days 1-2 embedded, Days 3+ offset)
// - 정답 스토리 탐지 방식 수정 (정답지 번호 스타일 기준)
// - alert() 제거 (대화상자 없이 로그 파일만 사용)
#target indesign
(function() {
    var settingsPath = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/프리미엄북/화이트북/auto/output/.whitebook_settings.json";
    
    var sf = new File(settingsPath);
    sf.encoding = 'UTF-8'; sf.open('r');
    var settings = eval("(" + sf.read() + ")");
    sf.close();

    var jsonPath = settings.json_path;
    var outputDir = settings.output_dir;
    var inddPath = settings.indd_path; // settings 기준 작업 파일 경로

    var f = new File(jsonPath);
    f.encoding = 'UTF-8'; f.open('r');
    var data = eval("(" + f.read() + ")");
    f.close();

    if (!data || !data.days || data.days.length === 0) { return; }

    // settings.indd_path 기준 작업 파일 확보
    // Google Drive 동일 이름 파일이 열려있으면 → 작업 경로로 복사 후 열기
    var workFile = new File(inddPath);
    var doc = null;

    try {
        // 같은 이름이지만 다른 경로(Google Drive 등)의 원본 찾기
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
            // 기존 작업 파일이 열려있으면 닫기
            for (var cd = 0; cd < app.documents.length; cd++) {
                try {
                    if (app.documents[cd].fullName.fsName === workFile.fsName) {
                        app.documents[cd].close(SaveOptions.NO); break;
                    }
                } catch(e) {}
            }
            // 원본 → 작업 경로 복사 (fsName 문자열로 전달)
            origDoc.fullName.copy(workFile.fsName);
        }

        // 작업 파일이 이미 열려있는지 확인
        for (var di2 = 0; di2 < app.documents.length; di2++) {
            try {
                if (app.documents[di2].fullName.fsName === workFile.fsName) {
                    doc = app.documents[di2]; break;
                }
            } catch(e) {}
        }

        // 없으면 열기 + 로드 대기
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
        A_word: 'A 어휘', B_eng: 'C 예문', B_kor: 'C 예문 사본',
        C_bogis: 'C 단어 박스', C_def: 'D 영영사전',
        D_box: 'D 단어 박스 new', D_item: 'D 단어 new',
        D_item_old: 'D 단어', E_sent: 'E 전치사',
        ANS_hdr:  '\uc815\ub2f5_',          // 정답_  (섹션 헤더)
        ANS_item: '\uc815\ub2f5\uc9c0 \ubc88\ud638', // 정답지 번호
        ANS_sol:  '\ud574\uc124_',           // 해설_  ([문제N], 빈줄)
        ANS_sep:  'C \uc608\ubb38 \uc0ac\ubcf8' // C 예문 사본 (B섹션 앞 빈줄)
    };

    function getStyle(name) {
        // 최상위 스타일 먼저 탐색
        var s = doc.paragraphStyles.itemByName(name);
        if (s.isValid) return s;
        // 스타일 그룹 내 탐색
        for (var gi = 0; gi < doc.paragraphStyleGroups.length; gi++) {
            var grp = doc.paragraphStyleGroups[gi];
            var gs = grp.paragraphStyles.itemByName(name);
            if (gs.isValid) return gs;
        }
        return doc.paragraphStyles[0];
    }

    function replaceContent(story, items) {
        if (!story || !story.isValid || !items || items.length === 0) return false;
        var fullText = '';
        for (var i = 0; i < items.length; i++) {
            fullText += items[i].text;
            if (i < items.length - 1) fullText += '\r';
        }
        story.contents = fullText;
        // 잔존 문자 스타일 초기화
        story.characters.everyItem().appliedCharacterStyle = doc.characterStyles[0];
        var paras = story.paragraphs;
        for (var i = 0; i < items.length && i < paras.length; i++) {
            paras[i].appliedParagraphStyle = getStyle(items[i].sty);
        }
        return true;
    }

    // HEIGHT_ONLY 숫자값 (enum 미정의 환경 방어)
    var HEIGHT_ONLY_VAL = 1751476583;

    // C 예문 체인: 마지막 프레임만 확장 (이전 페이지 레이아웃 영향 없음)
    function expandChainLastFrame(story) {
        if (!story || !story.isValid) return;
        try {
            var c = story.textContainers;
            if (c.length > 0) {
                c[c.length - 1].textFramePreferences.autoSizingType = HEIGHT_ONLY_VAL;
            }
        } catch(e) {}
    }

    // D 박스: 첫 프레임 확장 + 같은 페이지의 지정 스타일 프레임들을 delta 만큼 아래로 이동
    function expandFrameAndMoveBelow(story, moveStyles) {
        if (!story || !story.isValid) return;
        try {
            var c = story.textContainers;
            if (c.length === 0) return;
            var frame = c[0];
            var oldGb = frame.geometricBounds;
            var oldTop = oldGb[0];
            var oldBot = oldGb[2];
            // HEIGHT_ONLY로 내용 실제 높이 측정
            frame.textFramePreferences.autoSizingType = HEIGHT_ONLY_VAL;
            var measuredGb = frame.geometricBounds;
            var measuredHeight = measuredGb[2] - measuredGb[0];
            // HEIGHT_ONLY 해제 후 top 고정, bottom만 조정
            frame.textFramePreferences.autoSizingType = 1330005536; // OFF
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

    // ── 정답 섹션 아이콘 (A~E) ──
    var ICON_COLORS = [
        [65, 36, 22, 0],  // A
        [19, 42, 56, 0],  // B
        [52, 27, 39, 9],  // C
        [20, 41, 10, 0],  // D
        [44, 43, 52, 0]   // E
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
        try { tp.appliedFont = doc.fonts.itemByName('\uace0\ub3c4 B\tRegular'); } catch(e) {
            try { tp.appliedFont = app.fonts.itemByName('Godo B\tRegular'); } catch(e2) {}
        }
        tp.justification = Justification.CENTER_ALIGN;
        tp.fillColor = doc.colors.itemByName('Paper');

        // E헤더는 아이콘이 첫 번째 문자 (pos 0), 나머지는 pos 1
        var ipIdx = (sectionIdx === 4) ? 0 : 1;
        var ip = para.insertionPoints[ipIdx];
        tf.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
        tf.anchoredObjectSettings.anchorYoffset = -0.72;
    }

    function postProcessAnswerStory(story) {
        var paras = story.paragraphs;
        var ANS_HDR  = '\uc815\ub2f5_';
        var ANS_ITEM = '\uc815\ub2f5\uc9c0 \ubc88\ud638';
        var ANS_SOL  = '\ud574\uc124_';

        // 1. 헤더/섹션/문제 인덱스 수집
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
                if (txt.indexOf('[\ubb38\uc81c') >= 0) solIndices.push(i); // "[문제"
            }
        }

        // 2. B,C,D,E 섹션 첫 답 numberingContinue=false
        for (var s = 0; s < firstAnsOfSection.length; s++) {
            if (firstAnsOfSection[s].section > 0) {
                try { paras[firstAnsOfSection[s].idx].numberingContinue = false; } catch(e) {}
            }
        }

        // 3. [문제N] 바로 다음 첫 답 numberingContinue=false
        for (var s = 0; s < solIndices.length; s++) {
            var nextIdx = solIndices[s] + 1;
            if (nextIdx < paras.length && paras[nextIdx].appliedParagraphStyle.name === ANS_ITEM) {
                try { paras[nextIdx].numberingContinue = false; } catch(e) {}
            }
        }

        // 4. "정답" 문자 스타일 적용
        var charSty = doc.characterStyles.itemByName('\uc815\ub2f5'); // '정답'
        if (charSty && charSty.isValid) {
            for (var h = 0; h < hdrIndices.length; h++) {
                var para = paras[hdrIndices[h]];
                var content = para.contents;
                for (var c = 0; c < content.length - 1; c++) {
                    if (content.charAt(c) === '\uC815' && content.charAt(c + 1) === '\uB2F5') {
                        try {
                            para.characters[c].appliedCharacterStyle = charSty;
                            para.characters[c + 1].appliedCharacterStyle = charSty;
                        } catch(e) {}
                    }
                }
            }
        }

        // 5. 아이콘 삽입 (A~E) - 문자 스타일 적용 후
        for (var h = 0; h < Math.min(hdrIndices.length, 5); h++) {
            try { insertSectionIcon(paras[hdrIndices[h]], h); } catch(e) {}
        }

    }

    // 특정 스타일의 첫 단락을 가진 스토리를 페이지 순으로 수집
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

    // 정답 스토리: 첫 단락 내용이 '정답'을 포함하고, 두 번째 단락이 '정답지 번호' 스타일인 스토리 (페이지 순)
    function getAnswerStories() {
        var found = [], seen = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var tfs = doc.pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var story = tfs[t].parentStory;
                if (seen[story.id]) continue;
                if (story.paragraphs.length > 1) {
                    var firstPara = story.paragraphs[0];
                    var txt = firstPara.contents.replace(/\uFFFC/g,'').replace(/\r/g,'').replace(/^\s+/,'');
                    var secondSty = story.paragraphs[1].appliedParagraphStyle.name;
                    if (txt.indexOf('\uc815\ub2f5') >= 0 && secondSty === '\uc815\ub2f5\uc9c0 \ubc88\ud638') {
                        seen[story.id] = true;
                        found.push(story);
                    }
                }
            }
        }
        return found;
    }

    var aList    = getStoriesByFirstStyle(STYLES.A_word);
    var bList    = getStoriesByFirstStyle(STYLES.B_eng);
    var cList    = getStoriesByFirstStyle(STYLES.C_bogis);
    var dBoxList = getStoriesByFirstStyle(STYLES.D_box);
    var dItemList= getStoriesByFirstStyle(STYLES.D_item);  // Days 3-10 (8개)
    var eList    = getStoriesByFirstStyle(STYLES.E_sent);
    var ansList  = getAnswerStories();

    var log = ['=== 화이트북 조판 자동화 v2 ==='];
    log.push(new Date().toString());
    log.push('');
    log.push('발견된 스토리 수:');
    log.push('  A어휘: ' + aList.length + ' (예상: 10)');
    log.push('  B문장: ' + bList.length + ' (예상: 10)');
    log.push('  C영영사전: ' + cList.length + ' (예상: 10)');
    log.push('  D보기: ' + dBoxList.length + ' (예상: 10)');
    log.push('  D항목(D단어new): ' + dItemList.length + ' (예상: 8, Day3-10)');
    log.push('  E전치사: ' + eList.length + ' (예상: 10)');
    log.push('  정답: ' + ansList.length + ' (예상: 10, Day1-10 각각)');
    log.push('  처리 Day: ' + data.days.length);
    log.push('');

    // 정답 스토리 구조 (원본 분석 기준):
    // [0] 정답_ " ￼ 정답 "
    // [1..A] 정답지번호 word\t뜻 (Day1-2) 또는 N. word : 뜻 (Day3-10)
    // [B헤더] 정답_  " 정답"  ← 빈줄 없이 바로
    // [..B] 정답지번호 answer (번호 없이)
    // [C헤더] 정답_  " 정답"
    // [문제1] 해설_   (앞 빈줄 없음, 첫 문제)
    // [..C1] 정답지번호
    // [빈줄] 해설_  ← 문제 사이
    // [문제2] 해설_
    // ... 반복
    // [D헤더] 정답_  " 정답"
    // [..D] 정답지번호 word : answer (번호 없이)
    // [빈줄] 해설_
    // [E헤더] 정답_  "정답"
    // [..E] 정답지번호 sentence (번호 없이)
    function buildAnswerItems(answers, dayNum) {
        var items = [];
        if (!answers || !answers.A) return items;
        var useTab = (dayNum <= 2);

        // A 정답
        for (var i = 0; i < answers.A.length; i++) {
            var a = answers.A[i];
            var txt = useTab ? (a.word + '\t' + a.meaning)
                             : (a.num + '. ' + a.word + ' : ' + a.meaning);
            items.push({text: txt, sty: STYLES.ANS_item});
        }

        // Day1: A 다음 빈줄 (원본 구조상)
        if (dayNum === 1) items.push({text: '', sty: STYLES.ANS_sep});

        // B 헤더 (아이콘 삽입 위치: pos1 → 앞 공백 2개 필요)
        items.push({text: '  \uc815\ub2f5', sty: STYLES.ANS_hdr});
        if (answers.B) {
            for (var i = 0; i < answers.B.length; i++) {
                items.push({text: answers.B[i].answer, sty: STYLES.ANS_item});
            }
        }

        // Days 2,3,6: B 다음 빈줄 (원본 구조상)
        if (dayNum === 2 || dayNum === 3 || dayNum === 6) items.push({text: '', sty: STYLES.ANS_sep});

        // C 헤더
        items.push({text: '  \uc815\ub2f5', sty: STYLES.ANS_hdr});
        if (answers.C) {
            for (var i = 0; i < answers.C.length; i++) {
                var cAns = answers.C[i];
                // 두 번째 문제부터 앞에 빈줄
                if (i > 0) items.push({text: '', sty: STYLES.ANS_sol});
                items.push({text: '[\ubb38\uc81c ' + cAns.set + ']', sty: STYLES.ANS_sol});
                for (var j = 0; j < cAns.answers.length; j++) {
                    items.push({text: cAns.answers[j], sty: STYLES.ANS_item});
                }
            }
        }

        // D 헤더
        items.push({text: '  \uc815\ub2f5', sty: STYLES.ANS_hdr});
        if (answers.D) {
            for (var i = 0; i < answers.D.length; i++) {
                var d = answers.D[i];
                items.push({text: d.word + ' : ' + d.answer, sty: STYLES.ANS_item});
            }
        }

        // E 헤더 (앞에 빈줄, 아이콘 pos0 → 앞 공백 1개)
        items.push({text: '', sty: STYLES.ANS_sol});
        items.push({text: ' \uc815\ub2f5', sty: STYLES.ANS_hdr});
        if (answers.E) {
            for (var i = 0; i < answers.E.length; i++) {
                items.push({text: answers.E[i].sentence, sty: STYLES.ANS_item});
            }
        }

        return items;
    }

    app.doScript(function() {
        var dItemIdx = 0;  // Days 3-10용 D item 스토리 인덱스

        for (var di = 0; di < data.days.length; di++) {
            var day = data.days[di];
            var content = day.content;
            var answers = day.answers;
            var dayNum = day.day_num;
            log.push('── Day ' + dayNum + ' (idx=' + di + ') ──');

            // ── A 섹션 ──
            if (di < aList.length && content.A && content.A.length > 0) {
                var items = [];
                for (var i = 0; i < content.A.length; i++) {
                    var rawText = content.A[i].raw || (content.A[i].num + '. ' + content.A[i].word);
                    items.push({text: rawText, sty: STYLES.A_word});
                }
                replaceContent(aList[di], items);
                log.push('  A: ' + content.A.length + '단어 ✓');
            }

            // ── B 섹션 ──
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

            // ── C 섹션 ──
            if (di < cList.length && content.C && content.C.length > 0) {
                var items = [];
                for (var s = 0; s < content.C.length; s++) {
                    var cSet = content.C[s];
                    var bogisText = '\u300C보기\u300D  ' + cSet.bogis.join('  /  ');
                    items.push({text: bogisText, sty: STYLES.C_bogis});
                    for (var dd = 0; dd < cSet.defs.length; dd++) {
                        items.push({text: cSet.defs[dd], sty: STYLES.C_def});
                    }
                }
                replaceContent(cList[di], items);
                log.push('  C: ' + content.C.length + '세트 ✓');
            }

            // ── D 보기 + D 항목 ──
            if (di < dBoxList.length && content.D) {
                if (di < 2) {
                    // Days 1-2: 원본 구조 = D 박스에 D보기만 (D항목 별도 프레임 없음)
                    // 원본 P7/P13 D박스 para=3 (D보기 2줄 + 빈 D단어 1줄)
                    var items = [];
                    if (content.D.bogis_raw) {
                        for (var i = 0; i < content.D.bogis_raw.length; i++) {
                            items.push({text: content.D.bogis_raw[i], sty: STYLES.D_box});
                        }
                    }
                    // 빈 D단어 플레이스홀더 1줄 (원본 구조 유지)
                    items.push({text: '', sty: STYLES.D_item_old});
                    replaceContent(dBoxList[di], items);
                    // D박스 크기 변화 없으므로 expandFrameAndMoveBelow 불필요
                    log.push('  D(Days1-2 보기전용): 보기' + (content.D.bogis_raw ? content.D.bogis_raw.length : 0) + '줄 ✓');
                } else {
                    // Days 3-10: D 보기만 D 박스 스토리에, 항목은 별도 스토리
                    if (content.D.bogis_raw && content.D.bogis_raw.length > 0) {
                        var items = [];
                        for (var i = 0; i < content.D.bogis_raw.length; i++) {
                            items.push({text: content.D.bogis_raw[i], sty: STYLES.D_box});
                        }
                        replaceContent(dBoxList[di], items);
                        // 확장 후 D단어new / 발문 / E전치사 프레임 이동
                        expandFrameAndMoveBelow(dBoxList[di],
                            ['D \ub2e8\uc5b4 new', '\ubc1c\ubb38', 'E \uc804\uce58\uc0ac']);
                        log.push('  D보기: ' + content.D.bogis_raw.length + '줄 ✓');
                    }
                    // D 항목 (별도 스토리)
                    if (dItemIdx < dItemList.length && content.D.items && content.D.items.length > 0) {
                        var items = [];
                        for (var i = 0; i < content.D.items.length; i++) {
                            items.push({text: content.D.items[i].text, sty: STYLES.D_item});
                        }
                        replaceContent(dItemList[dItemIdx], items);
                        log.push('  D항목: ' + content.D.items.length + '개 → dItemList[' + dItemIdx + '] ✓');
                        dItemIdx++;
                    } else {
                        dItemIdx++;  // 데이터 없어도 인덱스 진행
                        log.push('  D항목: 스킵');
                    }
                }
            }

            // ── E 섹션 ──
            if (di < eList.length && content.E && content.E.length > 0) {
                var items = [];
                for (var i = 0; i < content.E.length; i++) {
                    var e = content.E[i];
                    items.push({text: e.num + '. ' + e.text, sty: STYLES.E_sent});
                }
                replaceContent(eList[di], items);
                log.push('  E: ' + content.E.length + '문장 ✓');
            }

            // ── 정답 ──
            // 매핑: ansList[0]=Day1, ansList[1]=Day2, ..., ansList[9]=Day10
            var ansIdx = di;  // di=0→Day1, di=1→Day2, ...
            if (ansIdx < ansList.length && answers && answers.A && answers.A.length > 0) {
                var ansItems = buildAnswerItems(answers, dayNum);
                // A 헤더: "  정답 " (공백2 + 정답 + 공백1) → 아이콘 pos1에 삽입
                var allItems = [{text: '  \uc815\ub2f5 ', sty: STYLES.ANS_hdr}];
                for (var i = 0; i < ansItems.length; i++) allItems.push(ansItems[i]);
                replaceContent(ansList[ansIdx], allItems);
                postProcessAnswerStory(ansList[ansIdx]);
                // 원본 정답 F1 프레임 위치 복원 (expandChainLastFrame 적용 금지 - top이 바뀜)
                var ansC = ansList[ansIdx].textContainers;
                if (ansC.length > 1) {
                    var ansF1 = ansC[1];
                    var ansGb = ansF1.geometricBounds;
                    ansF1.geometricBounds = [20, 23, ansGb[2], 190];
                    ansF1.textFramePreferences.autoSizingType = 1330005536; // OFF
                }
                log.push('  정답(Day' + dayNum + '): ' + allItems.length + '단락 ✓');
            }
        }

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '화이트북 조판 자동화 v2');

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
    if (overflows.length > 0) {
        log.push('  페이지: ' + overflows.join(', '));
    }

    // 로그 저장
    var logFile = new File(outputDir + '/조판_로그.txt');
    logFile.encoding = 'UTF-8'; logFile.open('w');
    logFile.write(log.join('\n'));
    logFile.close();

    // 문서 저장
    doc.save();

    // PDF 내보내기
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

    // 최종 로그 업데이트
    log.push('PDF: ' + (pdfOk ? '성공 → ' + pdfFile.name : '실패'));
    logFile = new File(outputDir + '/조판_로그.txt');
    logFile.encoding = 'UTF-8'; logFile.open('w');
    logFile.write(log.join('\n'));
    logFile.close();
})();
