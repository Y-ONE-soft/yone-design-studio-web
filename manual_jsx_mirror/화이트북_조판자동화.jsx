// 화이트북_조판자동화.jsx
// hwpx에서 추출한 JSON 데이터를 InDesign 화이트북 템플릿에 자동으로 채워 넣는 스크립트
// 실행: InDesign Scripts 패널에서 더블클릭, 또는 osascript로 원격 실행
//
// ExtendScript(ES3) 호환 - const/let/화살표함수/템플릿 리터럴 사용 불가

#target indesign

(function () {

    // ─────────────────────────────────────────────
    // 설정
    // ─────────────────────────────────────────────
    var CONFIG = {
        // 각 섹션의 단락 스타일명 (InDesign 문서 내 정의된 이름과 일치해야 함)
        styles: {
            A_word:     'A 어휘',
            B_eng:      'C 예문',
            B_kor:      'C 예문 사본',
            C_bogis:    'C 단어 박스',
            C_def:      'D 영영사전',
            D_box:      'D 단어 박스 new',
            D_item:     'D 단어 new',
            D_item_old: 'D 단어',      // Day1~2용 (구형 스타일)
            E_sent:     'E 전치사',
            ANS_header: '정답_',
            ANS_item:   '정답지 번호',
            ANS_num:    '정답',        // Day3+용 번호 스타일
        },
        // A 섹션 단어 포맷: 앞뒤 공백 포함 여부 (hwpx에서 추출한 raw 값 사용)
        useRawAFormat: true,
        // B 섹션 번호 접두사 포함 여부 (true = '1. sentence', false = 'sentence')
        includeBNumber: true,
        // 오버플로우 경고 포함 여부
        checkOverflow: true
    };

    // ─────────────────────────────────────────────
    // JSON 파일 읽기
    // ─────────────────────────────────────────────
    function readJsonFile(filePath) {
        var f = new File(filePath);
        if (!f.exists) {
            alert('JSON 파일을 찾을 수 없습니다:\n' + filePath);
            return null;
        }
        f.encoding = 'UTF-8';
        f.open('r');
        var content = f.read();
        f.close();
        return JSON.parse(content);
    }

    // ─────────────────────────────────────────────
    // 단락 스타일 가져오기 (없으면 경고)
    // ─────────────────────────────────────────────
    function getStyle(doc, styleName) {
        var sty = doc.paragraphStyles.itemByName(styleName);
        if (!sty.isValid) {
            alert('단락 스타일을 찾을 수 없습니다: ' + styleName);
            return doc.paragraphStyles[0];
        }
        return sty;
    }

    // ─────────────────────────────────────────────
    // 스토리 내용 교체 (핵심 함수)
    // items = [{text: '...', styleName: '...'}]
    // ─────────────────────────────────────────────
    function replaceStoryContent(doc, story, items) {
        if (!story || !story.isValid) return;
        if (!items || items.length === 0) return;

        // 전체 내용 문자열 구성 (단락 구분자 \r 사용)
        var fullText = '';
        for (var i = 0; i < items.length; i++) {
            fullText += items[i].text;
            if (i < items.length - 1) fullText += '\r';
        }

        // story.contents 교체 (모든 단락 스타일이 초기화됨)
        story.contents = fullText;

        // 단락 스타일 재적용
        var paras = story.paragraphs;
        for (var i = 0; i < items.length && i < paras.length; i++) {
            var sty = getStyle(doc, items[i].styleName);
            paras[i].appliedParagraphStyle = sty;
        }
    }

    // ─────────────────────────────────────────────
    // 페이지 순서 기준으로 스토리 정렬
    // 특정 단락 스타일로 필터링
    // ─────────────────────────────────────────────
    function getStoriesByStyle(doc, targetStyleName) {
        var found = [];
        var pages = doc.pages;
        var seenStories = {};

        for (var p = 0; p < pages.length; p++) {
            var tfs = pages[p].textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var tf = tfs[t];
                var story = tf.parentStory;
                // 스토리 ID로 중복 제거
                var storyId = story.id;
                if (seenStories[storyId]) continue;
                // 첫 단락 스타일 확인
                if (story.paragraphs.length > 0) {
                    var style = story.paragraphs[0].appliedParagraphStyle.name;
                    if (style === targetStyleName) {
                        seenStories[storyId] = true;
                        found.push({story: story, pageIndex: p});
                    }
                }
            }
        }
        // 페이지 인덱스 기준 정렬 (이미 페이지 순이지만 명시적으로)
        found.sort(function(a, b) { return a.pageIndex - b.pageIndex; });
        return found;
    }

    // ─────────────────────────────────────────────
    // 섹션 A 채우기: 단어 목록
    // ─────────────────────────────────────────────
    function fillSectionA(doc, story, aData) {
        // aData = [{num: 1, word: '...', raw: '1. significant   '}, ...]
        var items = [];
        for (var i = 0; i < aData.length; i++) {
            var d = aData[i];
            var text = CONFIG.useRawAFormat ? d.raw : (d.num + '. ' + d.word);
            items.push({text: text, styleName: CONFIG.styles.A_word});
        }
        replaceStoryContent(doc, story, items);
    }

    // ─────────────────────────────────────────────
    // 섹션 B 채우기: 영문 문장 + 한글 해석 교대
    // ─────────────────────────────────────────────
    function fillSectionB(doc, story, bData) {
        // bData = [{num: 1, eng: '...', kor: '...'}]
        var items = [];
        for (var i = 0; i < bData.length; i++) {
            var d = bData[i];
            var engText = CONFIG.includeBNumber ? (d.num + '. ' + d.eng) : d.eng;
            items.push({text: engText, styleName: CONFIG.styles.B_eng});
            if (d.kor) {
                items.push({text: d.kor, styleName: CONFIG.styles.B_kor});
            }
        }
        replaceStoryContent(doc, story, items);
    }

    // ─────────────────────────────────────────────
    // 섹션 C 채우기: 영영사전 (보기 + 정의)
    // ─────────────────────────────────────────────
    function fillSectionC(doc, story, cData) {
        // cData = [{set: 1, bogis: [...], defs: ['1. def : ___', ...]}, ...]
        var items = [];
        for (var s = 0; s < cData.length; s++) {
            var set = cData[s];
            // 보기 라인: 〈보기〉  word1  /  word2  /  ...
            var bogisText = '\u300C보기\u300D  ' + set.bogis.join('  /  ');
            items.push({text: bogisText, styleName: CONFIG.styles.C_bogis});
            // 정의 라인들
            for (var d = 0; d < set.defs.length; d++) {
                items.push({text: set.defs[d], styleName: CONFIG.styles.C_def});
            }
        }
        replaceStoryContent(doc, story, items);
    }

    // ─────────────────────────────────────────────
    // 섹션 D 채우기: 보기 박스 (D 단어 박스 new 스타일 스토리)
    // 보기 원문 라인들을 그대로 사용
    // ─────────────────────────────────────────────
    function fillSectionD_box(doc, story, dData) {
        // dData.bogis_raw = ['〈보기〉', '① concord ...', '㉝ break off ...']
        var bogisLines = dData.bogis_raw;
        if (!bogisLines || bogisLines.length === 0) return;
        var items = [];
        for (var i = 0; i < bogisLines.length; i++) {
            items.push({text: bogisLines[i], styleName: CONFIG.styles.D_box});
        }
        replaceStoryContent(doc, story, items);
    }

    // ─────────────────────────────────────────────
    // 섹션 D 채우기: 항목 목록 (D 단어 new 스타일 스토리)
    // ─────────────────────────────────────────────
    function fillSectionD_items(doc, story, dData, useOldStyle) {
        // dData.items = [{num: 1, word: '...', type: '유의어', text: '1. word [유의어] : ___'}]
        var items = dData.items;
        if (!items || items.length === 0) return;
        var styleName = useOldStyle ? CONFIG.styles.D_item_old : CONFIG.styles.D_item;
        var paragraphItems = [];
        for (var i = 0; i < items.length; i++) {
            paragraphItems.push({text: items[i].text, styleName: styleName});
        }
        replaceStoryContent(doc, story, paragraphItems);
    }

    // ─────────────────────────────────────────────
    // 섹션 E 채우기: 전치사 문장
    // ─────────────────────────────────────────────
    function fillSectionE(doc, story, eData) {
        // eData = [{num: 1, text: '...______...'}]
        var items = [];
        for (var i = 0; i < eData.length; i++) {
            var d = eData[i];
            items.push({text: d.num + '. ' + d.text, styleName: CONFIG.styles.E_sent});
        }
        replaceStoryContent(doc, story, items);
    }

    // ─────────────────────────────────────────────
    // 정답 채우기 (정답_ + 정답지 번호 스타일)
    // Day 1-2 형식: word\t뜻 (탭 구분)
    // Day 3+ 형식: 1. word : 뜻 (번호 포함)
    // ─────────────────────────────────────────────
    function fillAnswerStory(doc, story, answerData, dayNum) {
        if (!answerData || !answerData.A) return;

        var items = [];
        var useTabFormat = (dayNum <= 2);  // Day 1-2는 탭 형식

        // 섹션 A 정답
        for (var i = 0; i < answerData.A.length; i++) {
            var a = answerData.A[i];
            var text;
            if (useTabFormat) {
                text = a.word + '\t' + a.meaning;
            } else {
                text = a.num + '. ' + a.word + ' : ' + a.meaning;
            }
            items.push({text: text, styleName: CONFIG.styles.ANS_item});
        }

        // 섹션 B 정답
        for (var i = 0; i < answerData.B.length; i++) {
            var b = answerData.B[i];
            items.push({
                text: b.num + '. ' + b.answer,
                styleName: CONFIG.styles.ANS_item
            });
        }

        // 섹션 C 정답
        for (var s = 0; s < answerData.C.length; s++) {
            var cSet = answerData.C[s];
            items.push({text: '[문제 ' + cSet.set + ']', styleName: CONFIG.styles.ANS_item});
            for (var j = 0; j < cSet.answers.length; j++) {
                items.push({
                    text: (j + 1) + '. ' + cSet.answers[j],
                    styleName: CONFIG.styles.ANS_item
                });
            }
        }

        // 섹션 D 정답
        for (var i = 0; i < answerData.D.length; i++) {
            var d = answerData.D[i];
            items.push({
                text: d.num + '. ' + d.word + ' : ' + d.answer,
                styleName: CONFIG.styles.ANS_item
            });
        }

        // 섹션 E 정답
        for (var i = 0; i < answerData.E.length; i++) {
            var e = answerData.E[i];
            items.push({
                text: e.num + '. ' + e.sentence,
                styleName: CONFIG.styles.ANS_item
            });
        }

        // 정답 헤더 (첫 번째 단락은 헤더 유지)
        // 스토리 첫 단락이 '정답_' 스타일이면 그것을 유지하고 나머지 교체
        if (story.paragraphs.length > 0 &&
            story.paragraphs[0].appliedParagraphStyle.name === CONFIG.styles.ANS_header) {
            var headerText = story.paragraphs[0].contents.replace(/\r$/, '');
            // 헤더 + 내용 전체 재작성
            var fullItems = [{text: headerText, styleName: CONFIG.styles.ANS_header}];
            for (var i = 0; i < items.length; i++) fullItems.push(items[i]);
            replaceStoryContent(doc, story, fullItems);
        } else {
            replaceStoryContent(doc, story, items);
        }
    }

    // ─────────────────────────────────────────────
    // 오버플로우 체크
    // ─────────────────────────────────────────────
    function checkOverflowAll(doc) {
        var overflows = [];
        var tfs = doc.textFrames;
        for (var i = 0; i < tfs.length; i++) {
            try {
                if (tfs[i].overflows) {
                    var pg = tfs[i].parentPage;
                    var pgNum = pg ? pg.name : '?';
                    overflows.push('페이지 ' + pgNum + ' - 텍스트 프레임 오버플로우');
                }
            } catch(e) {}
        }
        return overflows;
    }

    // ─────────────────────────────────────────────
    // 메인 실행
    // ─────────────────────────────────────────────
    function main() {
        // JSON 파일 선택 대화상자
        var jsonFile = File.openDialog('content.json 파일을 선택하세요', '*.json');
        if (!jsonFile) {
            alert('취소됨.');
            return;
        }

        var data = readJsonFile(jsonFile.fsName);
        if (!data || !data.days || data.days.length === 0) {
            alert('JSON 데이터가 비어 있거나 올바르지 않습니다.');
            return;
        }

        var doc = app.activeDocument;
        if (!doc) {
            alert('열린 InDesign 문서가 없습니다.');
            return;
        }

        // 섹션별 스토리 목록 (페이지 순서)
        var aStories    = getStoriesByStyle(doc, CONFIG.styles.A_word);
        var bStories    = getStoriesByStyle(doc, CONFIG.styles.B_eng);
        var cStories    = getStoriesByStyle(doc, CONFIG.styles.C_bogis);
        var dBoxStories = getStoriesByStyle(doc, CONFIG.styles.D_box);
        var dItemStories= getStoriesByStyle(doc, CONFIG.styles.D_item);
        var eStories    = getStoriesByStyle(doc, CONFIG.styles.E_sent);
        var ansStories  = getStoriesByStyle(doc, CONFIG.styles.ANS_header);

        var numDays = data.days.length;
        var log = ['화이트북 조판 자동화 시작\n총 ' + numDays + '개 Day\n'];

        app.doScript(function () {

            for (var dayIdx = 0; dayIdx < numDays; dayIdx++) {
                var dayData = data.days[dayIdx];
                var dayNum  = dayData.day_num;
                var content = dayData.content;
                var answers = dayData.answers;

                log.push('── Day ' + dayNum + ' 처리 중 ──');

                // ── A 섹션 ──
                if (dayIdx < aStories.length && content.A && content.A.length > 0) {
                    fillSectionA(doc, aStories[dayIdx].story, content.A);
                    log.push('  A: ' + content.A.length + '개 단어 입력');
                } else {
                    log.push('  A: 스킵 (스토리 없음 또는 데이터 없음)');
                }

                // ── B 섹션 ──
                if (dayIdx < bStories.length && content.B && content.B.length > 0) {
                    fillSectionB(doc, bStories[dayIdx].story, content.B);
                    log.push('  B: ' + content.B.length + '개 문장 입력');
                } else {
                    log.push('  B: 스킵');
                }

                // ── C 섹션 ──
                if (dayIdx < cStories.length && content.C && content.C.length > 0) {
                    fillSectionC(doc, cStories[dayIdx].story, content.C);
                    log.push('  C: ' + content.C.length + '개 문제 세트 입력');
                } else {
                    log.push('  C: 스킵');
                }

                // ── D 보기 박스 ──
                if (dayIdx < dBoxStories.length && content.D && content.D.bogis_raw) {
                    fillSectionD_box(doc, dBoxStories[dayIdx].story, content.D);
                    log.push('  D 보기: ' + content.D.bogis_raw.length + '줄 입력');
                } else {
                    log.push('  D 보기: 스킵');
                }

                // ── D 항목 (D 단어 new 스토리가 있는 경우) ──
                if (dayIdx < dItemStories.length && content.D && content.D.items) {
                    fillSectionD_items(doc, dItemStories[dayIdx].story, content.D, false);
                    log.push('  D 항목: ' + content.D.items.length + '개 입력');
                } else if (content.D && content.D.items && content.D.items.length > 0) {
                    // D 단어 박스 스토리의 마지막 단락에 D 단어 스타일로 삽입 시도
                    if (dayIdx < dBoxStories.length) {
                        var dBoxStory = dBoxStories[dayIdx].story;
                        var lastParaIdx = dBoxStory.paragraphs.length - 1;
                        if (lastParaIdx >= 0) {
                            var lastPara = dBoxStory.paragraphs[lastParaIdx];
                            var lastStyle = lastPara.appliedParagraphStyle.name;
                            if (lastStyle === CONFIG.styles.D_item_old) {
                                // 마지막 단락부터 D 항목 삽입
                                var dItems = content.D.items;
                                var addText = '';
                                for (var di = 0; di < dItems.length; di++) {
                                    addText += (di === 0 ? '' : '\r') + dItems[di].text;
                                }
                                lastPara.contents = addText;
                                lastPara.appliedParagraphStyle = getStyle(doc, CONFIG.styles.D_item_old);
                                log.push('  D 항목: ' + dItems.length + '개 입력 (박스 내 마지막 단락)');
                            }
                        }
                    }
                } else {
                    log.push('  D 항목: 스킵');
                }

                // ── E 섹션 ──
                if (dayIdx < eStories.length && content.E && content.E.length > 0) {
                    fillSectionE(doc, eStories[dayIdx].story, content.E);
                    log.push('  E: ' + content.E.length + '개 문장 입력');
                } else {
                    log.push('  E: 스킵');
                }

                // ── 정답 ──
                if (dayIdx < ansStories.length && answers && answers.A) {
                    fillAnswerStory(doc, ansStories[dayIdx].story, answers, dayNum);
                    log.push('  정답: 입력 완료');
                } else {
                    log.push('  정답: 스킵 (데이터 없음)');
                }
            }

        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, '화이트북 조판 자동화');

        // ── 오버플로우 체크 ──
        if (CONFIG.checkOverflow) {
            var overflows = checkOverflowAll(doc);
            if (overflows.length > 0) {
                log.push('\n⚠️ 오버플로우 발생 (' + overflows.length + '개):');
                for (var i = 0; i < overflows.length; i++) {
                    log.push('  ' + overflows[i]);
                }
            } else {
                log.push('\n✅ 오버플로우 없음');
            }
        }

        // ── 로그 저장 ──
        var logFile = new File(jsonFile.path + '/조판_로그.txt');
        logFile.encoding = 'UTF-8';
        logFile.open('w');
        logFile.write(log.join('\n'));
        logFile.close();

        // ── 완료 메시지 ──
        alert('조판 완료!\n\n' + log.join('\n') + '\n\n로그 저장: 조판_로그.txt');
    }

    main();

})();
