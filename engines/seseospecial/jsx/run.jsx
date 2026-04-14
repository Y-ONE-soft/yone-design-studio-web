// [ENGINE TEMPLATE] 세서특필 InDesign 조판 스크립트
// settingsPath는 engine.py에서 주입됨
#target indesign

var settingsPath = "__SETTINGS_PATH__";

(function() {

// ===== 유틸리티 =====
function readJSON(path) {
    var f = new File(path);
    f.open("r"); f.encoding = "UTF-8";
    var txt = f.read(); f.close();
    return eval("(" + txt + ")");
}

function writeLog(outputDir, lines) {
    var f = new File(outputDir + "/조판_로그.txt");
    f.open("w"); f.encoding = "UTF-8";
    f.write(lines.join("\n"));
    f.close();
}

function findBiggestStory(page) {
    var items = page.textFrames;
    var maxP = 0; var best = null;
    for (var i = 0; i < items.length; i++) {
        try {
            var st = items[i].parentStory;
            if (st.paragraphs.length > maxP) { maxP = st.paragraphs.length; best = st; }
        } catch(e) {}
    }
    return best;
}

// ===== PART1 조판 =====
function typesetPart1(doc, part1Data, logLines) {
    // 6페이지 교과서 스토리 찾기
    var story = findBiggestStory(doc.pages[5]);
    if (!story) { logLines.push("PART1: 6페이지 스토리 없음"); return 0; }

    // 클리어
    story.contents = "";

    // 텍스트 삽입
    var paras = part1Data.paragraphs;
    var textParts = [];
    var styleCodes = [];
    for (var i = 0; i < paras.length; i++) {
        textParts.push(paras[i].text);
        styleCodes.push(paras[i].style);
    }
    story.contents = textParts.join("\r");

    // 문자스타일 [없음] 초기화 (단락별)
    var noneCS = doc.characterStyles[0];
    for (var p = 0; p < story.paragraphs.length; p++) {
        story.paragraphs[p].appliedCharacterStyle = noneCS;
    }

    // 단락스타일 적용
    // 0=소제목, 1=핵심문장_단원, 2=핵심문장_음영, 3=단락스타일2, 4=핵심문장_박스
    var aver = doc.paragraphStyleGroups.itemByName("A ver");
    var silGrp = aver.paragraphStyleGroups.itemByName("\uC2E4\uC804\uBB38\uC81C");
    var p1Styles = [
        doc.paragraphStyles.itemByName("\uC18C\uC81C\uBAA9"),          // 0
        aver.paragraphStyles.itemByName("\uD575\uC2EC\uBB38\uC7A5_\uB2E8\uC6D0"), // 1
        aver.paragraphStyles.itemByName("\uD575\uC2EC\uBB38\uC7A5_\uC74C\uC601"), // 2
        doc.paragraphStyles.itemByName("\uB2E8\uB77D \uC2A4\uD0C0\uC77C 2"),      // 3
        silGrp.paragraphStyles.itemByName("\uD575\uC2EC\uBB38\uC7A5_\uBC15\uC2A4") // 4
    ];

    for (var p = 0; p < story.paragraphs.length && p < styleCodes.length; p++) {
        var c = styleCodes[p];
        if (c >= 0 && c < p1Styles.length && p1Styles[c].isValid) {
            story.paragraphs[p].appliedParagraphStyle = p1Styles[c];
        }
    }

    // overflow 처리
    if (story.overflows) {
        var fr = story.textContainers;
        var lastFrame = fr[fr.length - 1];
        var lastSpread = lastFrame.parentPage.parent;
        var prevFrame = lastFrame;
        var cnt = 0;
        while (story.overflows && cnt < 100) {
            var si = -1;
            for (var s = 0; s < doc.spreads.length; s++) {
                if (doc.spreads[s].id === lastSpread.id) { si = s; break; }
            }
            lastSpread = doc.spreads.add(1634104421, doc.spreads[si]);
            for (var pp = 0; pp < lastSpread.pages.length; pp++) {
                if (!story.overflows) break;
                var isR = (lastSpread.pages[pp].side === 1919382632);
                var l = isR ? 233 : 20;
                var r = isR ? 400 : 187;
                var tf = lastSpread.pages[pp].textFrames.add();
                tf.geometricBounds = [20, l, 277, r];
                prevFrame.nextTextFrame = tf;
                prevFrame = tf;
            }
            cnt++;
        }
    }

    logLines.push("PART1: " + story.paragraphs.length + "개 단락");
    return story.paragraphs.length;
}

// ===== PART2 본문 조판 =====
function typesetPart2Main(doc, mainData, settings, logLines) {
    // PART2 시작 페이지 찾기 - config의 part2_story_page 또는 설정에서 결정
    // 기존 스토리 찾기 (실전문제 내용이 있는 스토리)
    var story = null;
    // 모든 페이지 순회하여 실전문제 스타일이 있는 스토리 찾기
    for (var p = 0; p < doc.pages.length; p++) {
        var tfs = doc.pages[p].textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                var st = tfs[t].parentStory;
                if (st.paragraphs.length > 5) {
                    var sn = st.paragraphs[0].appliedParagraphStyle.name;
                    if (sn === "\uCD9C\uCC98" || sn === "\uC2E4\uC804\uBB38\uC81C_\uBC88\uD638") {
                        story = st;
                        break;
                    }
                }
            } catch(e) {}
        }
        if (story) break;
    }

    if (!story) {
        logLines.push("PART2: 실전문제 스토리 없음 - 스킵");
        return 0;
    }

    // 클리어 + 프레임 정리
    story.contents = "";
    while (story.textContainers.length > 1) {
        story.textContainers[story.textContainers.length - 1].remove();
    }
    var baseFrame = story.textContainers[0];
    var basePage = baseFrame.parentPage;

    // 프레임 bounds 계산
    var botEnd = 277;
    var gap = 4;
    var bTop = 24; var bHalf = (botEnd - bTop - gap) / 2;
    var nTop = 36; var nHalf = (botEnd - nTop - gap) / 2;
    var wPt = 167 * 2.834645; // 167mm -> pt

    function getFrameBounds(page) {
        var isR = (page.side === 1919382632);
        var isB = (page.appliedMaster && page.appliedMaster.name.indexOf("B") >= 0);
        var top = isB ? bTop : nTop;
        var hh = isB ? bHalf : nHalf;
        var l = isR ? 233 : 20;
        return {
            t: [top, l, top + hh, l + wPt],
            b: [top + hh + gap, l, botEnd, l + wPt]
        };
    }

    // 첫 프레임 상/하 분할
    var bd = getFrameBounds(basePage);
    baseFrame.geometricBounds = bd.t;
    var botF = basePage.textFrames.add();
    botF.geometricBounds = bd.b;
    baseFrame.nextTextFrame = botF;
    var prevFrame = botF;
    var currentSpread = basePage.parent;

    // 텍스트 삽입
    var textParts = [];
    var styleCodes = [];
    for (var i = 0; i < mainData.length; i++) {
        textParts.push(mainData[i].text);
        styleCodes.push(mainData[i].style);
    }
    story.contents = textParts.join("\r");

    // 문자스타일 [없음] 초기화
    var noneCS = doc.characterStyles[0];
    for (var p = 0; p < story.paragraphs.length; p++) {
        story.paragraphs[p].appliedCharacterStyle = noneCS;
    }

    // 단락스타일 적용
    var aver = doc.paragraphStyleGroups.itemByName("A ver");
    var silGrp = aver.paragraphStyleGroups.itemByName("\uC2E4\uC804\uBB38\uC81C");
    var p2Styles = [
        silGrp.paragraphStyles.itemByName("\uCD9C\uCC98"),
        silGrp.paragraphStyles.itemByName("\uC2E4\uC804\uBB38\uC81C_\uBC88\uD638"),
        silGrp.paragraphStyles.itemByName("\uC9C0\uBB38"),
        silGrp.paragraphStyles.itemByName("\uC120\uC9C0"),
        silGrp.paragraphStyles.itemByName("\uBC30\uACBD"),
        silGrp.paragraphStyles.itemByName("\uBCF4\uAE30"),
        silGrp.paragraphStyles.itemByName("\uC870\uAC74")
    ];

    for (var p = 0; p < story.paragraphs.length && p < styleCodes.length; p++) {
        var c = styleCodes[p];
        if (c >= 0 && c < p2Styles.length && p2Styles[c].isValid) {
            story.paragraphs[p].appliedParagraphStyle = p2Styles[c];
        }
    }

    // 밑줄 적용 (단락스타일 적용 후! 내용+길이 매칭)
    for (var i = 0; i < mainData.length; i++) {
        if (!mainData[i].ul_key) continue;
        var ulKey = mainData[i].ul_key;
        var ulLen = mainData[i].ul_len;
        var ulRanges = mainData[i].ul_ranges;

        // 스토리에서 매칭되는 단락 찾기
        for (var p = 0; p < story.paragraphs.length; p++) {
            var para = story.paragraphs[p];
            var ptxt = (para.contents + "").replace(/\r/g, "");
            var pkey = ptxt.substring(0, 50).replace(/\n/g, " ");
            var plen = ptxt.length;

            if (pkey === ulKey && Math.abs(plen - ulLen) <= 2) {
                var parts = ulRanges.split(",");
                for (var r = 0; r < parts.length; r++) {
                    var se = parts[r].split(":");
                    if (se.length !== 2) continue;
                    var ss = parseInt(se[0], 10);
                    var ee = parseInt(se[1], 10) - 1;
                    if (ee >= para.characters.length) ee = para.characters.length - 1;
                    if (ss <= ee) {
                        var range = para.characters.itemByRange(para.characters[ss], para.characters[ee]);
                        range.underline = true;
                        range.underlineWeight = 0.5;
                        range.underlineOffset = 1.5;
                    }
                }
                break;
            }
        }
    }

    // 프레임 브레이크: 실전문제_번호 단락의 끝에 삽입 (역순, 첫 문항 제외)
    var qEndIndices = []; // 실전문제_번호 다음 단락의 시작 직전 = 현재 단락의 끝
    for (var p = 0; p < story.paragraphs.length; p++) {
        if (story.paragraphs[p].appliedParagraphStyle.name === "\uC2E4\uC804\uBB38\uC81C_\uBC88\uD638") {
            qEndIndices.push(p);
        }
    }
    // 각 실전문제_번호 이전 단락의 끝에 프레임브레이크 (= 실전문제_번호 앞 insertionPoint)
    // "단락의 끝에 넣어"라는 요청 → 실전문제_번호 바로 앞 단락의 마지막 insertionPoint
    for (var q = qEndIndices.length - 1; q >= 1; q--) {
        var qIdx = qEndIndices[q];
        // qIdx 단락의 insertionPoints[0] (= 이전 단락 끝 다음) 에 프레임브레이크
        if (qIdx > 0) {
            story.paragraphs[qIdx - 1].insertionPoints[-1].contents = SpecialCharacters.FRAME_BREAK;
        }
    }

    // overflow 처리: 스프레드 추가 (상/하 2프레임)
    if (story.overflows && currentSpread.pages.length > 1) {
        var rpIdx = (basePage === currentSpread.pages[0]) ? 1 : 0;
        if (rpIdx < currentSpread.pages.length) {
            var rp = currentSpread.pages[rpIdx];
            var rb = getFrameBounds(rp);
            var t1 = rp.textFrames.add(); t1.geometricBounds = rb.t;
            prevFrame.nextTextFrame = t1;
            if (story.overflows) {
                var b1 = rp.textFrames.add(); b1.geometricBounds = rb.b;
                t1.nextTextFrame = b1; prevFrame = b1;
            } else prevFrame = t1;
        }
    }
    var safety = 0;
    while (story.overflows && safety < 200) {
        var si = -1;
        for (var s = 0; s < doc.spreads.length; s++) {
            if (doc.spreads[s].id === currentSpread.id) { si = s; break; }
        }
        currentSpread = doc.spreads.add(1634104421, doc.spreads[si]);
        for (var pp = 0; pp < currentSpread.pages.length; pp++) {
            if (!story.overflows) break;
            var pb = getFrameBounds(currentSpread.pages[pp]);
            var t1 = currentSpread.pages[pp].textFrames.add(); t1.geometricBounds = pb.t;
            prevFrame.nextTextFrame = t1;
            if (!story.overflows) { prevFrame = t1; break; }
            var b1 = currentSpread.pages[pp].textFrames.add(); b1.geometricBounds = pb.b;
            t1.nextTextFrame = b1; prevFrame = b1;
        }
        safety++;
    }

    // 문항 수 카운트
    var qCount = 0;
    for (var p = 0; p < story.paragraphs.length; p++) {
        if (story.paragraphs[p].appliedParagraphStyle.name === "\uC2E4\uC804\uBB38\uC81C_\uBC88\uD638") qCount++;
    }
    logLines.push("PART2: " + qCount + "문항 (" + story.paragraphs.length + "단락)");
    return qCount;
}

// ===== PART2 정답지 조판 =====
function typesetPart2Answers(doc, answersData, logLines) {
    // 정답지 스토리 찾기: 해설_번호 사본 스타일이 적용된 스토리
    var ansStory = null;
    for (var s = 0; s < doc.stories.length; s++) {
        try {
            var st = doc.stories[s];
            if (st.paragraphs.length > 2 &&
                st.paragraphs[0].appliedParagraphStyle.name === "\uD574\uC124_\uBC88\uD638 \uC0AC\uBCF8") {
                ansStory = st;
                break;
            }
        } catch(e) {}
    }

    if (!ansStory) {
        logLines.push("정답: 정답지 스토리 없음 - 스킵");
        return 0;
    }

    var silGrp = doc.paragraphStyleGroups.itemByName("A ver")
                    .paragraphStyleGroups.itemByName("\uC2E4\uC804\uBB38\uC81C");
    var sNum = silGrp.paragraphStyles.itemByName("\uD574\uC124_\uBC88\uD638 \uC0AC\uBCF8");
    var sAns = silGrp.paragraphStyles.itemByName("\uC815\uB2F5 \uC0AC\uBCF8");

    if (!sNum.isValid || !sAns.isValid) {
        logLines.push("정답: 스타일 없음 - 스킵");
        return 0;
    }

    // 텍스트 빌드
    var textParts = [];
    var styleFlags = []; // 0 = 해설_번호 사본, 1 = 정답 사본
    for (var i = 0; i < answersData.length; i++) {
        var a = answersData[i];
        if (a.num && a.num.length > 0) {
            textParts.push(a.num + ") ");
            styleFlags.push(0);
        }
        textParts.push(a.text);
        styleFlags.push(1);
    }

    ansStory.contents = "";
    ansStory.contents = textParts.join("\r");

    var sObjs = [sNum, sAns];
    for (var p = 0; p < ansStory.paragraphs.length && p < styleFlags.length; p++) {
        ansStory.paragraphs[p].appliedParagraphStyle = sObjs[styleFlags[p]];
    }

    // overflow 처리
    if (ansStory.overflows) {
        var afr = ansStory.textContainers;
        var lf = afr[afr.length - 1];
        var ls = lf.parentPage.parent;
        var pv = lf;
        var cnt = 0;
        while (ansStory.overflows && cnt < 40) {
            var si = -1;
            for (var s = 0; s < doc.spreads.length; s++) {
                if (doc.spreads[s].id === ls.id) { si = s; break; }
            }
            ls = doc.spreads.add(1634104421, doc.spreads[si]);
            for (var pp = 0; pp < ls.pages.length; pp++) {
                if (!ansStory.overflows) break;
                var isR = (ls.pages[pp].side === 1919382632);
                var l = isR ? 233 : 20;
                var r = isR ? 400 : 187;
                var tf = ls.pages[pp].textFrames.add();
                tf.geometricBounds = [17, l, 280, r];
                pv.nextTextFrame = tf;
                pv = tf;
            }
            cnt++;
        }
    }

    var ansCount = 0;
    for (var p = 0; p < ansStory.paragraphs.length; p++) {
        if (ansStory.paragraphs[p].appliedParagraphStyle.name === "\uD574\uC124_\uBC88\uD638 \uC0AC\uBCF8") ansCount++;
    }
    logLines.push("정답: " + ansCount + "개");
    return ansCount;
}

// ===== 메인 실행 =====
var settings = readJSON(settingsPath);
var data = readJSON(settings.json_path);
var logLines = [];

// InDesign 파일 열기
var inddFile = new File(settings.indd_path);
var doc = app.open(inddFile);

app.doScript(function() {

    // PART1 조판
    typesetPart1(doc, data.part1, logLines);

    // PART2 본문 조판
    typesetPart2Main(doc, data.part2.main, settings, logLines);

    // PART2 정답지 조판
    typesetPart2Answers(doc, data.part2.answers, logLines);

    // 오버플로우 체크
    var overflowCount = 0;
    for (var s = 0; s < doc.stories.length; s++) {
        try { if (doc.stories[s].overflows) overflowCount++; } catch(e) {}
    }
    logLines.push("오버플로우: " + overflowCount + "개");

    // PDF 내보내기
    try {
        var pdfFile = new File(settings.output_dir + "/" + doc.name.replace(".indd", ".pdf"));
        doc.exportFile(ExportFormat.PDF_TYPE, pdfFile);
        logLines.push("PDF: 성공");
    } catch(e) {
        logLines.push("PDF: 실패 - " + e.message);
    }

    // 저장
    doc.save();

}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "세서특필 조판");

// 로그 기록
writeLog(settings.output_dir, logLines);

})();
