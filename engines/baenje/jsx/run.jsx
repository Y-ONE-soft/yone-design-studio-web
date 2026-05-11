// [ENGINE TEMPLATE] 배N제 조판 자동화
// 파이프라인: settings.json 로드 -> 원본 열기 -> RTF 배치 -> 스타일 적용 -> PDF 출력

var settingsPath = "/SETTINGS_PLACEHOLDER/settings.json";

// ── 설정 로드 ────────────────────────────────────────────────────────────
var sf = new File(settingsPath);
sf.encoding = "UTF-8";
sf.open("r");
var settings = eval("(" + sf.read() + ")");
sf.close();

var rtfPath        = settings.rtf_path;
var answersRtfPath = settings.answers_rtf_path || "";
var inddPath       = settings.indd_path;
var outputDir      = settings.output_dir;
var schoolName     = settings.school   || "";
var issueNum       = settings.issue_num || "01";

var logPath = outputDir + "/\uc870\ud310_\ub85c\uadf8.txt";  // 조판_로그.txt

function writeLog(msg) {
    var lf = new File(logPath);
    lf.encoding = "UTF-8";
    lf.open("a");
    lf.writeln(msg);
    lf.close();
}

// ── 문서 열기 ────────────────────────────────────────────────────────────
var doc = app.open(new File(inddPath));

// ── 스타일 참조 ──────────────────────────────────────────────────────────
function getPStyle(name) {
    var all = doc.allParagraphStyles;
    for (var i = 0; i < all.length; i++) {
        if (all[i].name === name) return all[i];
    }
    return null;
}

var mundaeStyle   = getPStyle("\ubb38\uc81c");          // 문제
var seonjiStyle   = getPStyle("\uc120\uc9c0");          // 선지
var boxStyle      = getPStyle("!\ubc15\uc2a4-\ub0b4\uc6a9_");  // !박스-내용_
var nextReadStyle = getPStyle("\ub2e4\uc74c \uae00\uc744 \uc77d\uace0");  // 다음 글을 읽고
var smallBoxStyle = getPStyle("!\uc791\uc740\ubc15\uc2a4");  // !작은박스
var jogeonStyle   = getPStyle("\uc870\uac74");          // 조건
var bogiStyle     = getPStyle("\ubcf4\uae30");          // 보기
var noneCharStyle = doc.characterStyles.itemByName("[\uc5c6\uc74c]");  // [없음]

// 스타일 존재 검사
if (!mundaeStyle)  { writeLog("ERROR: '\ubb38\uc81c' \uc2a4\ud0c0\uc77c \uc5c6\uc74c"); doc.close(SaveOptions.NO); exit(); }
if (!seonjiStyle)  { writeLog("ERROR: '\uc120\uc9c0' \uc2a4\ud0c0\uc77c \uc5c6\uc74c"); doc.close(SaveOptions.NO); exit(); }
if (!boxStyle)     { writeLog("ERROR: '!\ubc15\uc2a4-\ub0b4\uc6a9_' \uc2a4\ud0c0\uc77c \uc5c6\uc74c"); doc.close(SaveOptions.NO); exit(); }

// PRESERVE: 이 스타일이 적용된 단락은 재처리하지 않음
var PRESERVE = {};
PRESERVE["\uc815\ub2f5_\ubb38\uc81c \ubc88\ud638"] = true;  // 정답_문제 번호
PRESERVE["\uc815\ub2f5"]     = true;  // 정답
PRESERVE["\uc815\ub2f5_"]    = true;  // 정답_
PRESERVE["\ud574\uc124_"]    = true;  // 해설_
PRESERVE["\ud574\uc124_\uc2dc\uc791"] = true;  // 해설_시작
PRESERVE["\ud574\uc11d"]     = true;  // 해석
PRESERVE["\uc5b4\ud718"]     = true;  // 어휘

// ── 메인 콘텐츠 스토리 탐색 (컨테이너가 가장 많은 스토리) ─────────────
var mainStory = null;
var maxCnt = 0;
for (var si = 0; si < doc.stories.length; si++) {
    var c = doc.stories[si].textContainers.length;
    if (c > maxCnt) { maxCnt = c; mainStory = doc.stories[si]; }
}
if (!mainStory) {
    writeLog("ERROR: \uba54\uc778 \uc2a4\ud1a0\ub9ac\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc74c");
    doc.close(SaveOptions.NO);
    exit();
}
writeLog("\uba54\uc778 \uc2a4\ud1a0\ub9ac \ucee8\ud14c\uc774\ub108 \uc218: " + maxCnt);

// ── 원고 RTF 배치 ───────────────────────────────────────────────────────
var firstFrame = mainStory.textContainers[0];
firstFrame.place(new File(rtfPath));
writeLog("RTF \ubc30\uce58 \uc644\ub8cc: " + rtfPath);

// (정답지 배치는 원고 스타일 적용 후로 지연)

// ── [TABLE_START:N] ~ [TABLE_END] 마커 제거 (데이터 행은 탭 구분 텍스트로 유지) ──
function convertTablesToInDesignTables(ft) {
    // TABLE_START/END 마커만 삭제, 데이터 행은 그대로 유지 (탭 구분 텍스트)
    // 역순으로 처리해서 인덱스 변동 방지
    var startMarkers = [];
    var endMarkers = [];
    var paras = ft.paragraphs;
    for (var pi = 0; pi < paras.length; pi++) {
        var cc = paras[pi].contents.replace(/[\r\n]/g, "");
        if (/^\s*\[TABLE_START:\d+\]\s*$/.test(cc)) {
            startMarkers.push(pi);
        }
        if (/^\s*\[TABLE_END\]\s*$/.test(cc)) {
            endMarkers.push(pi);
        }
    }

    // 역순으로 마커 단락 삭제 (END 먼저, 그 다음 START)
    // END 마커 삭제
    for (var ei = endMarkers.length - 1; ei >= 0; ei--) {
        paras = ft.paragraphs;
        var idx = endMarkers[ei];
        if (idx < paras.length) {
            try { paras[idx].remove(); } catch(e) {}
        }
    }
    // START 마커 삭제
    for (var si = startMarkers.length - 1; si >= 0; si--) {
        paras = ft.paragraphs;
        var idx = startMarkers[si];
        if (idx < paras.length) {
            try { paras[idx].remove(); } catch(e) {}
        }
    }

    writeLog("TABLE: \ub9c8\ucee4 \uc81c\uac70 \uc644\ub8cc (\ud0ed \uad6c\ubd84 \ud14d\uc2a4\ud2b8 \uc720\uc9c0)");
}

// ── 스타일 적용 (전체 스토리 단위) ──────────────────────────────────────
function applyStyles() {
    var ft = mainStory.texts[0];

    // 0-a. 연속 빈 단락 제거
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat   = "\\r{2,}";
    app.changeGrepPreferences.changeTo = "\\r";
    try { ft.changeGrep(); } catch(e) {}
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;

    // 0-ab. [TABLE_START:N] ~ [TABLE_END] 마커를 InDesign 표로 변환
    convertTablesToInDesignTables(ft);

    // 0-b. 밑줄 길이 정규화 (_ 10개 이상 → 표준 길이)
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat   = "_{10,}";
    app.changeGrepPreferences.changeTo = "_________________________";
    try { ft.changeGrep(); } catch(e) {}
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;

    // 1. 밑줄 위치 수집 (스타일 초기화 전에 먼저 기록)
    var ulRanges = [];
    var tsr = ft.textStyleRanges;
    var cumIdx = 0;
    for (var u = 0; u < tsr.length; u++) {
        var rng = tsr[u];
        var rLen = rng.contents.length;
        if (rng.underline === true) {
            ulRanges.push({ s: cumIdx, e: cumIdx + rLen - 1 });
        }
        cumIdx += rLen;
    }
    writeLog("\ubc11\uc904 \ubc94\uc704 \uc218: " + ulRanges.length);

    // 2. 각주/미주 삭제
    try {
        var fnArr = mainStory.footnotes;
        for (var fn = fnArr.length - 1; fn >= 0; fn--) { try { fnArr[fn].remove(); } catch(ex) {} }
    } catch(e) {}
    try {
        var enArr = mainStory.endnotes;
        for (var en = enArr.length - 1; en >= 0; en--) { try { enArr[en].remove(); } catch(ex) {} }
    } catch(e) {}

    // 3. 문자 스타일 + 오버라이드 초기화
    try { ft.appliedCharacterStyle = noneCharStyle; } catch(e) {}
    try { ft.clearOverrides(OverrideType.CHARACTER_ONLY); } catch(e) {}

    // 표 셀 내부도 초기화
    var tbls = ft.tables;
    for (var ti = 0; ti < tbls.length; ti++) {
        var cells = tbls[ti].cells;
        for (var ci = 0; ci < cells.length; ci++) {
            try {
                cells[ci].texts[0].appliedCharacterStyle = noneCharStyle;
                cells[ci].texts[0].clearOverrides(OverrideType.CHARACTER_ONLY);
            } catch(e) {}
        }
    }

    // 4. 단락 스타일 적용 (상태머신)
    var inBogi = false, inJogon = false, inYoyak = false, nextIsGivenSent = false;
    var yoyakBinkan = false;  // 발문에 요약+빈칸이 함께 있는 경우
    var afterJimun = false;   // 지문(boxStyle) 직후 상태
    var inReadAndAnswer = false;  // "다음 글을 읽고 질문에 답하시오" 내부
    var paras = ft.paragraphs;
    var qCount = 0;

    for (var i = 0; i < paras.length; i++) {
        var p   = paras[i];
        var txt = p.contents;

        // PRESERVE 스타일 → 상태 초기화 후 건너뜀
        if (PRESERVE[p.appliedParagraphStyle.name]) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
            yoyakBinkan = false; afterJimun = false;
            continue;
        }

        // 공백만 있는 단락 건너뜀
        if (txt.replace(/[\r\n\t \u0020]/g, "").length === 0) continue;

        var cc = txt.replace(/[\r\n]/g, "");

        // ↓ 기호 → 박스 (요약 화살표)
        if (/^\s*\u2193\s*$/.test(cc)) {
            p.appliedParagraphStyle = boxStyle;
            try { p.justification = Justification.CENTER_ALIGN; } catch(e) {}
            continue;
        }

        var isBogiHeader = /^\s*<\ubcf4\uae30>\s*$/.test(cc) || /^\s*\[\ubcf4\uae30\]\s*$/.test(cc);

        // "다음 글을 읽고 질문에 답하시오" 내부: [문제] / 정답: — isMundae보다 먼저 체크
        if (inReadAndAnswer) {
            if (/^\s*\[\ubb38\uc81c\]/.test(txt)) {
                p.appliedParagraphStyle = mundaeStyle;
                continue;
            }
            if (/^\s*\uc815\ub2f5\s*:/.test(txt)) {
                p.appliedParagraphStyle = seonjiStyle;
                continue;
            }
        }

        // 문제 발문 감지: 한글? / 시오. / 시 오. / 윗글|위 글 + ? / (주관식)
        var isMundae = (
            /[\uAC00-\uD7A3]\?/.test(txt) ||
            /\uc2dc\s*\uc624\./.test(txt) ||
            (/(\uc717\uae00|\uc704 \uae00)/.test(txt) && /\?/.test(txt)) ||
            /^\s*\(\uc8fc\uad00\uc2dd\)/.test(txt)
        );
        if (isMundae) {
            inBogi = false; inJogon = false; inYoyak = false;
            nextIsGivenSent = /\uc8fc\uc5b4\uc9c4 \ubb38\uc7a5/.test(txt);
            // 요약+빈칸 동시 포함 감지
            yoyakBinkan = (/\uc694\uc57d/.test(txt) && /\ube48\uce78/.test(txt));
            afterJimun = false;

            // "(주관식) 다음 글을 읽고 질문에 답하시오" → 다음 글을 읽고 스타일 + 하위문제 모드
            if (/\ub2e4\uc74c \uae00\uc744 \uc77d\uace0/.test(txt) && /\uc9c8\ubb38\uc5d0\s*\ub2f5/.test(txt)) {
                inReadAndAnswer = true;
                if (nextReadStyle) p.appliedParagraphStyle = nextReadStyle;
            } else {
                inReadAndAnswer = false;
                p.appliedParagraphStyle = mundaeStyle;
            }
            qCount++;
            continue;
        }

        // <조건> 안의 내용
        if (inJogon) {
            if (isBogiHeader) {
                inJogon = false; inBogi = true;
                if (bogiStyle) p.appliedParagraphStyle = bogiStyle;
                continue;
            }
            // 조건 내부의 슬래시 구분자 줄도 조건 스타일 유지
            if (jogeonStyle) { p.appliedParagraphStyle = jogeonStyle; continue; }
        }

        // <보기> 헤더
        if (isBogiHeader) {
            inBogi = true; inJogon = false; inYoyak = false;
            if (bogiStyle) p.appliedParagraphStyle = bogiStyle;
            continue;
        }

        // 다음 글을 읽고
        if (/\ub2e4\uc74c \uae00\uc744 \uc77d\uace0/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
            yoyakBinkan = false; afterJimun = false;
            // "질문에 답하시오" 포함 시 하위 문제 구조 진입
            inReadAndAnswer = /\uc9c8\ubb38\uc5d0\s*\ub2f5/.test(txt);
            if (nextReadStyle) p.appliedParagraphStyle = nextReadStyle;
            continue;
        }

        // <조건> 헤더
        if (/^\s*<\uc870\uac74>/.test(txt) || /^\s*\[\uc870\uac74\]/.test(txt)) {
            inBogi = false; inJogon = true; inYoyak = false;
            if (jogeonStyle) p.appliedParagraphStyle = jogeonStyle;
            continue;
        }

        // <요약> / [요약문] / [요약]
        if (/^\s*<\uc694\uc57d>/.test(txt) || /^\s*\[\uc694\uc57d\ubb38\]/.test(txt) || /^\s*\[\uc694\uc57d\]/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = true;
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            continue;
        }

        // ①~⑤ → 선지
        if (/^[\s\r\n]*[\u2460-\u2464]/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
            yoyakBinkan = false; afterJimun = false;
            p.appliedParagraphStyle = seonjiStyle;
            continue;
        }

        // <보기> 안의 내용
        if (inBogi) {
            if (/ \/ /.test(txt) || /\/ $/.test(cc)) {
                p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
                continue;
            }
            inBogi = false;
        }

        // <요약> 안의 내용
        if (inYoyak) {
            if (/^\s*\([AB]\)/.test(txt)) {
                p.appliedParagraphStyle = seonjiStyle; continue;
            }
            if (smallBoxStyle) { p.appliedParagraphStyle = smallBoxStyle; continue; }
        }

        // 주어진 문장 (문장 삽입형)
        if (nextIsGivenSent && /^\s*[A-Za-z("]/.test(txt) && !/^\s*\([A-E]\)/.test(txt)) {
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            nextIsGivenSent = false;
            continue;
        }

        // (A)~(E): 긴 텍스트 → 지문 박스, 짧은 텍스트 → 선지
        if (/^\s*\([A-E]\)/.test(txt)) {
            var rest = cc.replace(/^\s*\([A-E]\)[\s:]*/, "");
            if (rest.length >= 25 && /^[A-Za-z"\u201c\u2018]/.test(rest)) {
                p.appliedParagraphStyle = boxStyle;
            } else {
                p.appliedParagraphStyle = seonjiStyle;
            }
            continue;
        }

        // 답: / 정답:
        if (/^\s*(\ub2f5|\uc815\ub2f5)\s*:/.test(txt)) {
            p.appliedParagraphStyle = seonjiStyle; continue;
        }

        // / 구분자 (보기 단어 목록)
        if (/ \/ /.test(txt)) {
            p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
            continue;
        }

        // 요약+빈칸 발문 후: 지문 다음 비-선지 단락 → !작은박스
        if (yoyakBinkan && afterJimun) {
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            yoyakBinkan = false;
            afterJimun = false;
            continue;
        }

        // 나머지 → 본문 박스
        afterJimun = yoyakBinkan;  // 지문 단락 통과 후 다음 단락에서 체크
        p.appliedParagraphStyle = boxStyle;
    }

    writeLog("\ubb38\uc81c \uc218: " + qCount);

    // 5. 밑줄 복원
    for (var r = 0; r < ulRanges.length; r++) {
        try {
            ft.characters.itemByRange(ulRanges[r].s, ulRanges[r].e).underline = true;
        } catch(e) {}
    }

    // 6. 오버플로우 단독 프레임 자동 높이 조절
    var containers = mainStory.textContainers;
    for (var ci = 0; ci < containers.length; ci++) {
        var fr = containers[ci];
        if (!fr.isValid) continue;
        if (!fr.overflows) continue;
        if (fr.parentStory.textContainers.length > 1) continue;
        try {
            fr.textFramePreferences.autoSizingType = AutoSizingType.HEIGHT_ONLY;
            fr.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.TOP_LEFT_POINT;
        } catch(e) {}
    }

    // 오버플로우 집계
    var overflowCount = 0;
    for (var ci2 = 0; ci2 < containers.length; ci2++) {
        if (containers[ci2].isValid && containers[ci2].overflows) overflowCount++;
    }
    writeLog("\uc624\ubc84\ud50c\ub85c\uc6b0: " + overflowCount + "\uac1c");

    return qCount;
}

// ── startParagraph = NEXT_FRAME 설정 (문제마다 새 프레임) ────────────────
// applyStyles() doScript 밖에서 실행해야 정상 동작
function setNextFrame() {
    var containers = mainStory.textContainers;
    if (containers.length <= 1) return;

    var allParas = mainStory.texts[0].paragraphs;
    var inRA = false;  // "다음 글을 읽고 질문에 답하시오" 내부

    for (var pi = 0; pi < allParas.length; pi++) {
        var fp = allParas[pi];
        var ftxt = fp.contents.replace(/[\r\n]/g, "");
        if (ftxt.replace(/[\s]/g, "").length === 0) continue;

        var isNextRead = /\ub2e4\uc74c \uae00\uc744 \uc77d\uace0/.test(ftxt);
        var isMundae = (
            /[\uAC00-\uD7A3]\?/.test(ftxt) ||
            /\uc2dc\s*\uc624\./.test(ftxt) ||
            (/(\uc717\uae00|\uc704 \uae00)/.test(ftxt) && /\?/.test(ftxt)) ||
            /^\s*\(\uc8fc\uad00\uc2dd\)/.test(ftxt)
        );

        // "다음 글을 읽고 질문에 답하시오" 내부 → 프레임브레이크 금지
        if (inRA && !isNextRead) {
            // [문제]로 시작하는 하위 문제 → 프레임브레이크 없음
            if (/^\s*\[\ubb38\uc81c\]/.test(ftxt)) continue;
            // 새 발문(다음 글을 읽고가 아닌)이 나오면 inRA 해제, 프레임브레이크 설정
            if (isMundae) inRA = false;
            else continue;  // 지문, 정답: 등 → 프레임브레이크 없음
        }

        if (isMundae || isNextRead) {
            // "다음 글을 읽고 질문에 답하시오" → 프레임브레이크 설정 + inRA 진입
            if (isNextRead && /\uc9c8\ubb38\uc5d0\s*\ub2f5/.test(ftxt)) {
                inRA = true;
            } else {
                inRA = false;
            }
            try { fp.startParagraph = StartParagraph.NEXT_FRAME; } catch(e) {}
        }
    }
}

// ── 탭 구분 표 텍스트 → InDesign 표 변환 + 다음 문제 프레임브레이크 조정 ──
function styleTabTextAsTable() {
    var ft = mainStory.texts[0];
    var paras = ft.paragraphs;

    // 탭이 포함된 연속 단락 그룹 찾기
    var tableGroups = [];
    var currentGroup = null;
    for (var pi = 0; pi < paras.length; pi++) {
        var txt = paras[pi].contents.replace(/[\r\n]/g, "");
        var tabCount = 0;
        for (var ti = 0; ti < txt.length; ti++) {
            if (txt.charAt(ti) === "\t") tabCount++;
        }
        if (tabCount >= 1 && txt.replace(/[\s\t]/g, "").length > 0) {
            if (!currentGroup) { currentGroup = { start: pi, end: pi }; }
            else { currentGroup.end = pi; }
        } else {
            if (currentGroup && (currentGroup.end - currentGroup.start) >= 1) {
                tableGroups.push(currentGroup);
            }
            currentGroup = null;
        }
    }
    if (currentGroup && (currentGroup.end - currentGroup.start) >= 1) {
        tableGroups.push(currentGroup);
    }
    if (tableGroups.length === 0) return;

    // 역순 처리
    for (var gi = tableGroups.length - 1; gi >= 0; gi--) {
        var g = tableGroups[gi];
        paras = ft.paragraphs;

        // 행 데이터 수집
        var rowData = [];
        var maxCols = 0;
        for (var ri = g.start; ri <= g.end; ri++) {
            var rowTxt = paras[ri].contents.replace(/[\r\n]/g, "");
            var cells = rowTxt.split("\t");
            if (cells.length > maxCols) maxCols = cells.length;
            rowData.push(cells);
        }
        for (var rd = 0; rd < rowData.length; rd++) {
            while (rowData[rd].length < maxCols) rowData[rd].push("");
        }

        // 탭 텍스트가 들어있는 프레임 찾기 (표 바로 앞 단락의 프레임)
        var tableFrame = null;
        try {
            var tfs = paras[g.start].parentTextFrames;
            if (tfs.length > 0) tableFrame = tfs[0];
        } catch(e) {}

        // 탭 텍스트 삭제 (메인 스토리에서 제거)
        paras = ft.paragraphs;
        var sChar = paras[g.start].characters[0].index;
        var eP = paras[g.end];
        var eChar = eP.characters[eP.characters.length - 1].index;
        ft.characters.itemByRange(sChar, eChar).remove();

        if (!tableFrame || !tableFrame.parentPage) continue;

        // 프레임의 남은 공간 측정
        var gb = tableFrame.geometricBounds;  // [y1, x1, y2, x2]
        var frameW = gb[3] - gb[1];
        var textBottom = gb[0];
        try {
            var lines = tableFrame.lines;
            if (lines.length > 0) {
                textBottom = lines[lines.length - 1].baseline + 4;  // 마지막 줄 + 여유
            }
        } catch(e) { textBottom = gb[0] + 10; }

        var availableH = gb[2] - textBottom;
        if (availableH < 15) {
            writeLog("TABLE: \uacf5\uac04 \ubd80\uc871 (" + availableH.toFixed(1) + "mm)");
            continue;
        }

        // 독립 텍스트 프레임 생성 (메인 스토리와 분리)
        var tblFrame = tableFrame.parentPage.textFrames.add();
        tblFrame.geometricBounds = [textBottom, gb[1], gb[2], gb[3]];
        tblFrame.textFramePreferences.insetSpacing = [0, 0, 0, 0];

        // 표 생성
        var tbl = tblFrame.insertionPoints[0].tables.add();
        tbl.bodyRowCount = rowData.length;
        tbl.columnCount = maxCols;

        // 데이터 (밑줄 20자로 통일)
        for (var dr = 0; dr < rowData.length; dr++) {
            for (var dc = 0; dc < maxCols; dc++) {
                var cellVal = rowData[dr][dc];
                cellVal = cellVal.replace(/_{10,}/g, "____________________");
                try { tbl.rows[dr].cells[dc].contents = cellVal; } catch(e) {}
            }
        }

        // 열 너비
        var tableW = frameW - 2;
        if (maxCols === 3) {
            try {
                tbl.columns[0].width = tableW * 0.20;
                tbl.columns[1].width = tableW * 0.40;
                tbl.columns[2].width = tableW * 0.40;
            } catch(e) {}
        } else {
            var colW = tableW / maxCols;
            for (var ci = 0; ci < maxCols; ci++) {
                try { tbl.columns[ci].width = colW; } catch(e) {}
            }
        }

        // 셀 텍스트 스타일
        try {
            var allC = tbl.cells.everyItem().getElements();
            for (var ac = 0; ac < allC.length; ac++) {
                try {
                    allC[ac].texts[0].pointSize = 8;
                    allC[ac].texts[0].leading = 10;
                    allC[ac].texts[0].justification = Justification.CENTER_ALIGN;
                } catch(e) {}
            }
        } catch(e) {}

        // 행 자동 성장
        for (var rh = 0; rh < tbl.rows.length; rh++) {
            try { tbl.rows[rh].autoGrow = true; } catch(e) {}
        }

        // 테두리: #999999
        var bColor = null;
        try {
            bColor = doc.colors.add({ name: "TblBorder", model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: [153, 153, 153] });
        } catch(e) {
            try { bColor = doc.colors.itemByName("TblBorder"); } catch(e2) {}
        }
        if (bColor) {
            try {
                var allC2 = tbl.cells.everyItem().getElements();
                for (var bc = 0; bc < allC2.length; bc++) {
                    try {
                        allC2[bc].topEdgeStrokeColor = bColor;
                        allC2[bc].topEdgeStrokeWeight = 0.3;
                        allC2[bc].bottomEdgeStrokeColor = bColor;
                        allC2[bc].bottomEdgeStrokeWeight = 0.3;
                        allC2[bc].leftEdgeStrokeColor = bColor;
                        allC2[bc].leftEdgeStrokeWeight = 0.3;
                        allC2[bc].rightEdgeStrokeColor = bColor;
                        allC2[bc].rightEdgeStrokeWeight = 0.3;
                    } catch(e) {}
                }
            } catch(e) {}
        }

        // 헤더 행 배경
        var hFill = null;
        try {
            hFill = doc.colors.add({ name: "TblHeader", model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: [232, 238, 244] });
        } catch(e) {
            try { hFill = doc.colors.itemByName("TblHeader"); } catch(e2) {}
        }
        if (hFill) {
            try {
                var hCells = tbl.rows[0].cells.everyItem().getElements();
                for (var hc = 0; hc < hCells.length; hc++) {
                    hCells[hc].fillColor = hFill;
                }
            } catch(e) {}
        }

        // 셀 인셋
        try {
            var allC3 = tbl.cells.everyItem().getElements();
            for (var ic = 0; ic < allC3.length; ic++) {
                try {
                    allC3[ic].topInset = 0.5;
                    allC3[ic].bottomInset = 0.5;
                    allC3[ic].leftInset = 1;
                    allC3[ic].rightInset = 1;
                } catch(e) {}
            }
        } catch(e) {}

        // 세로 가운데 정렬
        try { tbl.cells.everyItem().verticalJustification = VerticalJustification.CENTER_ALIGN; } catch(e) {}

        // 프레임 높이를 표 실제 높이에 맞춤
        try {
            doc.recompose();
            var actualH = 0;
            for (var rr = 0; rr < tbl.rows.length; rr++) actualH += tbl.rows[rr].height;
            actualH += 2;
            tblFrame.geometricBounds = [textBottom, gb[1], textBottom + actualH, gb[3]];
        } catch(e) {}

        writeLog("TABLE: " + rowData.length + "\ud589 x " + maxCols + "\uc5f4 \ub3c5\ub9bd \ud504\ub808\uc784 \ud45c \ubc30\uce58 \uc644\ub8cc");
    }
}

function styleTabTextAsTable_OLD_UNUSED() {
    var ft = mainStory.texts[0];
    var paras = ft.paragraphs;

    // 탭이 포함된 연속 단락 그룹 찾기
    var tableGroups = [];
    var currentGroup = null;
    for (var pi = 0; pi < paras.length; pi++) {
        var txt = paras[pi].contents.replace(/[\r\n]/g, "");
        var tabCount = 0;
        for (var ti = 0; ti < txt.length; ti++) {
            if (txt.charAt(ti) === "\t") tabCount++;
        }
        if (tabCount >= 1 && txt.replace(/[\s\t]/g, "").length > 0) {
            if (!currentGroup) { currentGroup = { start: pi, end: pi }; }
            else { currentGroup.end = pi; }
        } else {
            if (currentGroup && (currentGroup.end - currentGroup.start) >= 1) {
                tableGroups.push(currentGroup);
            }
            currentGroup = null;
        }
    }
    if (currentGroup && (currentGroup.end - currentGroup.start) >= 1) {
        tableGroups.push(currentGroup);
    }
    if (tableGroups.length === 0) return;

    // 역순 처리
    for (var gi = tableGroups.length - 1; gi >= 0; gi--) {
        var g = tableGroups[gi];
        paras = ft.paragraphs;

        // 행 데이터 수집
        var rowData = [];
        var maxCols = 0;
        for (var ri = g.start; ri <= g.end; ri++) {
            var rowTxt = paras[ri].contents.replace(/[\r\n]/g, "");
            var cells = rowTxt.split("\t");
            if (cells.length > maxCols) maxCols = cells.length;
            rowData.push(cells);
        }
        for (var rd = 0; rd < rowData.length; rd++) {
            while (rowData[rd].length < maxCols) rowData[rd].push("");
        }

        // 프레임 너비
        var frameW = 80;
        try {
            var tfs = paras[g.start].parentTextFrames;
            if (tfs.length > 0) {
                var gb = tfs[0].geometricBounds;
                frameW = gb[3] - gb[1];
            }
        } catch(e) {}

        // 78번 발문은 NEXT_FRAME 유지 (변경하지 않음)

        // 탭 텍스트 삭제
        paras = ft.paragraphs;
        var sChar = paras[g.start].characters[0].index;
        var eP = paras[g.end];
        var eChar = eP.characters[eP.characters.length - 1].index;
        ft.characters.itemByRange(sChar, eChar).remove();

        // 삽입점
        paras = ft.paragraphs;
        var ip = (sChar > 0) ? ft.insertionPoints[sChar] : ft.insertionPoints[0];

        // InDesign 표 생성
        var tbl = ip.tables.add();
        tbl.bodyRowCount = rowData.length;
        tbl.columnCount = maxCols;

        // 표가 들어간 단락 가운데 정렬 (인라인 표는 단락 정렬을 따름)
        try {
            paras = ft.paragraphs;
            // 삽입점 기준으로 표가 있는 단락 찾기
            for (var tpi = 0; tpi < paras.length; tpi++) {
                var tpTables = paras[tpi].tables;
                if (tpTables.length > 0) {
                    for (var tti = 0; tti < tpTables.length; tti++) {
                        if (tpTables[tti].id === tbl.id) {
                            paras[tpi].justification = Justification.CENTER_ALIGN;
                            break;
                        }
                    }
                }
            }
        } catch(e) {}

        // 데이터 (밑줄을 셀 크기에 맞게 축소)
        for (var dr = 0; dr < rowData.length; dr++) {
            for (var dc = 0; dc < maxCols; dc++) {
                var cellVal = rowData[dr][dc];
                // 연속 밑줄 → 20자로 통일 (사본 기준)
                cellVal = cellVal.replace(/_{10,}/g, "____________________");
                try { tbl.rows[dr].cells[dc].contents = cellVal; } catch(e) {}
            }
        }

        // 열 너비
        var tableW = frameW - 2;
        if (maxCols === 3) {
            try {
                tbl.columns[0].width = tableW * 0.20;
                tbl.columns[1].width = tableW * 0.40;
                tbl.columns[2].width = tableW * 0.40;
            } catch(e) {}
        } else {
            var colW = tableW / maxCols;
            for (var ci = 0; ci < maxCols; ci++) {
                try { tbl.columns[ci].width = colW; } catch(e) {}
            }
        }

        // 셀 텍스트 스타일
        try {
            var allC = tbl.cells.everyItem().getElements();
            for (var ac = 0; ac < allC.length; ac++) {
                try {
                    allC[ac].texts[0].pointSize = 8;
                    allC[ac].texts[0].leading = 10;
                    allC[ac].texts[0].justification = Justification.CENTER_ALIGN;
                } catch(e) {}
            }
        } catch(e) {}

        // 테두리: #999999
        var bColor = null;
        try {
            bColor = doc.colors.add({ name: "TblBorder", model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: [153, 153, 153] });
        } catch(e) {
            try { bColor = doc.colors.itemByName("TblBorder"); } catch(e2) {}
        }
        if (bColor) {
            try {
                var allC2 = tbl.cells.everyItem().getElements();
                for (var bc = 0; bc < allC2.length; bc++) {
                    try {
                        allC2[bc].topEdgeStrokeColor = bColor;
                        allC2[bc].topEdgeStrokeWeight = 0.3;
                        allC2[bc].bottomEdgeStrokeColor = bColor;
                        allC2[bc].bottomEdgeStrokeWeight = 0.3;
                        allC2[bc].leftEdgeStrokeColor = bColor;
                        allC2[bc].leftEdgeStrokeWeight = 0.3;
                        allC2[bc].rightEdgeStrokeColor = bColor;
                        allC2[bc].rightEdgeStrokeWeight = 0.3;
                    } catch(e) {}
                }
            } catch(e) {}
        }

        // 헤더 행 배경: #E8EEF4
        var hFill = null;
        try {
            hFill = doc.colors.add({ name: "TblHeader", model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: [232, 238, 244] });
        } catch(e) {
            try { hFill = doc.colors.itemByName("TblHeader"); } catch(e2) {}
        }
        if (hFill) {
            try {
                var hCells = tbl.rows[0].cells.everyItem().getElements();
                for (var hc = 0; hc < hCells.length; hc++) {
                    hCells[hc].fillColor = hFill;
                }
            } catch(e) {}
        }

        // 셀 인셋
        try {
            var allC3 = tbl.cells.everyItem().getElements();
            for (var ic = 0; ic < allC3.length; ic++) {
                try {
                    allC3[ic].topInset = 0.3;
                    allC3[ic].bottomInset = 0.3;
                    allC3[ic].leftInset = 0.5;
                    allC3[ic].rightInset = 0.5;
                } catch(e) {}
            }
        } catch(e) {}

        // 세로 가운데 정렬
        try { tbl.cells.everyItem().verticalJustification = VerticalJustification.CENTER_ALIGN; } catch(e) {}

        // autoGrow로 셀 내용에 맞게 행 높이 자동 조절
        for (var rh = 0; rh < tbl.rows.length; rh++) {
            try { tbl.rows[rh].autoGrow = true; } catch(e) {}
        }
        try { doc.recompose(); } catch(e) {}

        var totalH = 0;
        for (var rr = 0; rr < tbl.rows.length; rr++) totalH += tbl.rows[rr].height;

        // 표 삽입으로 인해 영작 발문의 NEXT_FRAME이 사라질 수 있으므로 재설정
        paras = ft.paragraphs;
        for (var nf = 0; nf < paras.length; nf++) {
            var nfTxt = paras[nf].contents.replace(/[\r\n]/g, "");
            // 영작 발문: "조건에 맞게" 또는 "영작하시오"
            if (/\uc870\uac74\uc5d0 \ub9de\uac8c/.test(nfTxt) && /\uc601\uc791/.test(nfTxt)) {
                try {
                    paras[nf].startParagraph = StartParagraph.NEXT_FRAME;
                    writeLog("TABLE: \uc601\uc791 P" + nf + " NEXT_FRAME \uc7ac\uc124\uc815");
                } catch(e) {}
                break;
            }
        }

        writeLog("TABLE: " + rowData.length + "\ud589 x " + maxCols + "\uc5f4 InDesign \ud45c (\ub192\uc774 " + totalH.toFixed(1) + "mm)");
    }
}

// ── PDF 내보내기 ─────────────────────────────────────────────────────────
function exportPDF(doc, outputDir, school, issueNum) {
    var num = issueNum.length === 1 ? "0" + issueNum : issueNum;
    var pdfName = school + "_\ubc30N\uc81c" + num + "_\ub0b4\uc9c0.pdf";
    var pdfPath = outputDir + "/" + pdfName;

    var preset = app.pdfExportPresets.itemByName("[PDF/X-1a:2001]");
    try {
        doc.exportFile(ExportFormat.PDF_TYPE, new File(pdfPath), false,
                       preset.isValid ? preset : undefined);
        writeLog("PDF: \uc131\uacf5");
        writeLog("PDF_PATH: " + pdfPath);
    } catch(e) {
        writeLog("PDF: \uc2e4\ud328 - " + e.message);
    }
}

// ── 실행 ─────────────────────────────────────────────────────────────────
var qCount = 0;
app.doScript(
    function() { qCount = applyStyles(); },
    ScriptLanguage.JAVASCRIPT,
    undefined,
    UndoModes.ENTIRE_SCRIPT,
    "\ubc30N\uc81c \uc2a4\ud0c0\uc77c \uc801\uc6a9"
);

setNextFrame();

// ── 탭 구분 표 텍스트 스타일링 (표처럼 보이도록) ──────────────────────────
styleTabTextAsTable();

// ── 정답지 RTF 배치 (원고 스타일 적용 완료 후) ─────────────────────────
if (answersRtfPath !== "") {
    var ansStory = null;
    var secondMax = 0;
    for (var si2 = 0; si2 < doc.stories.length; si2++) {
        var st = doc.stories[si2];
        if (st === mainStory) continue;
        var cnt = st.textContainers.length;
        if (cnt > secondMax) { secondMax = cnt; ansStory = st; }
    }
    if (ansStory) {
        writeLog("\uc815\ub2f5\uc9c0 \uc2a4\ud1a0\ub9ac \ubc1c\uacac (\ucee8\ud14c\uc774\ub108 " + secondMax + "\uac1c), \ubc30\uce58 \uc2dc\uc791...");
        try {
            // 한글 경로 회피: /tmp에 복사
            var ansSrc = new File(answersRtfPath);
            var ansTmp = new File("/tmp/baenje_answers.rtf");
            ansSrc.copy(ansTmp);

            var ansFrame = ansStory.textContainers[0];
            // 레이어 잠금 해제
            try { ansFrame.itemLayer.locked = false; } catch(e2) {}
            // 기존 내용 제거
            try { ansStory.texts[0].remove(); } catch(e3) {}
            ansFrame.place(ansTmp);
            writeLog("\uc815\ub2f5\uc9c0 RTF \ubc30\uce58 \uc644\ub8cc");

            // ── 정답지 스타일 적용 ──────────────────────────────
            var ansNumStyle  = getPStyle("\uc815\ub2f5_\ubb38\uc81c \ubc88\ud638");  // 정답_문제 번호
            var ansStyle     = getPStyle("\uc815\ub2f5_");                            // 정답_
            var ansHaeStyle  = getPStyle("\ud574\uc124_\uc2dc\uc791");                // 해설_시작

            if (ansNumStyle && ansStyle) {
                var ansParas = ansStory.texts[0].paragraphs;
                var qNum = 0;

                // 문자 스타일 초기화
                try { ansStory.texts[0].appliedCharacterStyle = noneCharStyle; } catch(ec) {}
                try { ansStory.texts[0].clearOverrides(OverrideType.CHARACTER_ONLY); } catch(ec) {}

                // 연속 빈 단락 제거
                app.findGrepPreferences  = NothingEnum.NOTHING;
                app.changeGrepPreferences = NothingEnum.NOTHING;
                app.findGrepPreferences.findWhat   = "\\r{2,}";
                app.changeGrepPreferences.changeTo = "\\r";
                try { ansStory.texts[0].changeGrep(); } catch(eg) {}
                app.findGrepPreferences  = NothingEnum.NOTHING;
                app.changeGrepPreferences = NothingEnum.NOTHING;

                // 다시 단락 참조 (GREP 후 변경됨)
                ansParas = ansStory.texts[0].paragraphs;

                for (var ai = 0; ai < ansParas.length; ai++) {
                    var ap = ansParas[ai];
                    var atxt = ap.contents.replace(/[\r\n]/g, "");

                    // 빈 단락 건너뛰기
                    if (atxt.replace(/[\s]/g, "").length === 0) continue;

                    // 제목 줄 삭제 (첫 번째 비어있지 않은 줄이 제목인 경우)
                    if (qNum === 0 && !/^\s*\[\uc815\ub2f5\]/.test(atxt) && !/^\s*\[\ud574\uc124\]/.test(atxt)) {
                        // "배N제 통합 — 정답 및 해설" 같은 제목 → 빈 단락으로
                        try { ap.contents = "\r"; } catch(ed) {}
                        continue;
                    }

                    // [정답] → 문제번호 삽입 + 정답_ 스타일
                    if (/^\s*\[\uc815\ub2f5\]/.test(atxt)) {
                        qNum++;
                        // [정답] 앞에 문제번호 단락 삽입
                        try {
                            ap.insertionPoints[0].contents = qNum + "\r";
                            // 삽입된 문제번호 단락에 스타일 적용
                            ansParas = ansStory.texts[0].paragraphs;  // 재참조
                            // 현재 ai 위치에 번호 단락이 삽입되었으므로
                            ansParas[ai].appliedParagraphStyle = ansNumStyle;
                            ai++;  // 다음은 [정답] 단락
                            ansParas[ai].appliedParagraphStyle = ansStyle;
                        } catch(ei) {
                            ap.appliedParagraphStyle = ansStyle;
                        }
                        continue;
                    }

                    // [해설] → 해설_시작 스타일
                    if (/^\s*\[\ud574\uc124\]/.test(atxt)) {
                        if (ansHaeStyle) ap.appliedParagraphStyle = ansHaeStyle;
                        continue;
                    }
                }
                writeLog("\uc815\ub2f5\uc9c0 \uc2a4\ud0c0\uc77c \uc801\uc6a9 \uc644\ub8cc (" + qNum + "\ubb38\uc81c)");
            } else {
                writeLog("\uc815\ub2f5\uc9c0 \uc2a4\ud0c0\uc77c \uc5c6\uc74c (\uc815\ub2f5_\ubb38\uc81c \ubc88\ud638 / \uc815\ub2f5_)");
            }
        } catch(e) {
            writeLog("\uc815\ub2f5\uc9c0 RTF \ubc30\uce58 \uc2e4\ud328: " + e.message);
        }
    } else {
        writeLog("\uc815\ub2f5\uc9c0 \uc2a4\ud1a0\ub9ac \uc5c6\uc74c (\uac74\ub108\ub700)");
    }
}

exportPDF(doc, outputDir, schoolName, issueNum);

doc.save(new File(inddPath));

writeLog("\uc644\ub8cc");
