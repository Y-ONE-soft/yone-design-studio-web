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

function dbg(s){try{var f=new File("/tmp/workbook_debug.txt");f.open("w");f.encoding="UTF-8";f.write(""+s);f.close();}catch(e){}}

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

// 정답 스토리 찾기: 해설_번호 사본/정답 사본 단락이 앞쪽(첫 6단락)에 있는 스토리
// (이미 조판된 파일은 첫 단락 스타일이 바뀌어 있어 첫단락 비교로는 못 찾음)
function findAnswerStory(doc) {
    for (var s = 0; s < doc.stories.length; s++) {
        var st = doc.stories[s];
        if (st.paragraphs.length < 8) continue;
        var lim = Math.min(st.paragraphs.length, 6);
        for (var p = 0; p < lim; p++) {
            try {
                var nm = st.paragraphs[p].appliedParagraphStyle.name;
                if (nm === "해설_번호 사본" || nm === "정답 사본") return st;
            } catch(e) {}
        }
    }
    return null;
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
        silGrp.paragraphStyles.itemByName("\uD575\uC2EC\uBB38\uC7A5_\uBC15\uC2A4"), // 4
        aver.paragraphStyles.itemByName("\uB2F5\uC548\uC9C0")          // 5 \uB2F5\uC548\uC9C0
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

// ===== PART2 본문 조판 (intro 별도영역 + 문제 1단/그룹별, 양쪽 페이지) =====
function typesetPart2Main(doc, introData, mainData, settings, logLines) {
    // PART2 본문 스토리 찾기 (첫 단락 스타일 무관 — 이미 조판된 파일도 대응):
    //   PART1(6페이지)·정답 스토리를 제외한 최대 스토리를 PART2로 간주
    var p1Story = findBiggestStory(doc.pages[5]);
    var ansStory = findAnswerStory(doc);
    var story = null, _maxP = 0;
    for (var s = 0; s < doc.stories.length; s++) {
        var st = doc.stories[s];
        if (st === p1Story || st === ansStory) continue;
        if (st.paragraphs.length > _maxP && st.paragraphs.length < 9000) { _maxP = st.paragraphs.length; story = st; }
    }
    if (!story || story.paragraphs.length < 10) { logLines.push("PART2: 실전문제 스토리 없음 - 스킵"); return 0; }

    // 클리어 + 프레임 1개만 남김
    story.contents = "";
    while (story.textContainers.length > 1) {
        story.textContainers[story.textContainers.length - 1].remove();
    }
    var baseFrame = story.textContainers[0];
    var basePage = baseFrame.parentPage;
    var currentSpread = basePage.parent;

    // 1단(전면) 프레임 = 페이지 마진박스 (page.bounds+margin → 양쪽 페이지 자동 대응)
    function marginBox(page) {
        // geometricBounds=페이지상대좌표, page.bounds의 x=spread좌표 →
        // x오프셋(b[1]) 빼고 페이지 폭 기준으로 계산해야 양쪽 페이지 모두 정상
        var b = page.bounds;                 // [y1,x1,y2,x2]
        var m = page.marginPreferences;
        var pw = b[3] - b[1], ph = b[2] - b[0];
        return [b[0] + m.top, m.left, b[0] + ph - m.bottom, pw - m.right];
    }
    baseFrame.geometricBounds = marginBox(basePage);
    var prevFrame = baseFrame;

    // intro + main 합쳐 한 스토리에 흘림
    var entries = [];
    var i;
    for (i = 0; i < introData.length; i++) entries.push(introData[i]);
    for (i = 0; i < mainData.length; i++)  entries.push(mainData[i]);

    var textParts = [], styleCodes = [];
    for (i = 0; i < entries.length; i++) { textParts.push(entries[i].text); styleCodes.push(entries[i].style); }
    story.contents = textParts.join("\r");

    // 문자스타일 [없음] 초기화
    var noneCS = doc.characterStyles[0];
    for (var p = 0; p < story.paragraphs.length; p++) story.paragraphs[p].appliedCharacterStyle = noneCS;

    // 단락스타일 (확장 0~12): 0출처 1실전문제_번호 2지문 3선지 4배경 5보기 6조건
    //   7소제목 8핵심문장_박스 9step 10설명_기본 11세희T 12서답형_발문
    var aver = doc.paragraphStyleGroups.itemByName("A ver");
    var sil  = aver.paragraphStyleGroups.itemByName("실전문제");
    function S(grp, name) { var x = grp.paragraphStyles.itemByName(name); return (x && x.isValid) ? x : null; }
    var fb = S(sil,"선지");
    // '다음 글을 읽고' 스타일이 템플릿에 없으면 placeholder 생성(서답형_발문 기반)
    var styDaum = S(sil,"다음 글을 읽고");
    if (!styDaum) {
        try { styDaum = sil.paragraphStyles.add({name:"다음 글을 읽고", basedOn:S(sil,"서답형_발문")}); }
        catch(e) { styDaum = S(sil,"서답형_발문"); }
    }
    var p2Styles = [
        S(sil,"출처"), S(sil,"실전문제_번호"), S(sil,"지문"), S(sil,"선지"),
        S(sil,"배경"), S(sil,"보기"), S(sil,"조건"),
        S(aver,"소제목"), S(sil,"핵심문장_박스"), S(aver,"step"),
        S(aver,"설명_기본"), S(aver,"세희T"), S(sil,"서답형_발문"),
        styDaum
    ];
    for (var p = 0; p < story.paragraphs.length && p < styleCodes.length; p++) {
        var c = styleCodes[p];
        var sty = (c >= 0 && c < p2Styles.length) ? p2Styles[c] : null;
        if (!sty) sty = fb;
        if (sty) story.paragraphs[p].appliedParagraphStyle = sty;
    }

    // 밑줄 (구형식 호환; 새 형식엔 ul_key 없음 → no-op)
    for (i = 0; i < mainData.length; i++) {
        if (!mainData[i].ul_key) continue;
        var ulKey = mainData[i].ul_key, ulLen = mainData[i].ul_len, ulRanges = mainData[i].ul_ranges;
        for (var p = 0; p < story.paragraphs.length; p++) {
            var para = story.paragraphs[p];
            var ptxt = (para.contents + "").replace(/\r/g, "");
            if (ptxt.substring(0,50).replace(/\n/g," ") === ulKey && Math.abs(ptxt.length - ulLen) <= 2) {
                var parts = ulRanges.split(",");
                for (var r = 0; r < parts.length; r++) {
                    var se = parts[r].split(":"); if (se.length !== 2) continue;
                    var ss = parseInt(se[0],10), ee = parseInt(se[1],10) - 1;
                    if (ee >= para.characters.length) ee = para.characters.length - 1;
                    if (ss <= ee) { var rg = para.characters.itemByRange(para.characters[ss], para.characters[ee]); rg.underline = true; rg.underlineWeight = 0.5; rg.underlineOffset = 1.5; }
                }
                break;
            }
        }
    }

    // 프레임 브레이크: 대표유형(7)/문제그룹(1) 단락 앞 (첫 단락 제외, 역순)
    var brk = [];
    for (var p = 1; p < story.paragraphs.length && p < styleCodes.length; p++) {
        if (styleCodes[p] === 0 || styleCodes[p] === 7) brk.push(p);
    }
    for (var b = brk.length - 1; b >= 0; b--) {
        story.paragraphs[brk[b] - 1].insertionPoints[-1].contents = SpecialCharacters.FRAME_BREAK;
    }

    // 오버플로우: 페이지마다 1단 프레임 (양쪽 페이지), 스프레드 추가
    function addFrame(page) {
        var tf = page.textFrames.add();
        tf.geometricBounds = marginBox(page);
        prevFrame.nextTextFrame = tf;
        prevFrame = tf;
    }
    for (var pp = 0; pp < currentSpread.pages.length; pp++) {
        if (!story.overflows) break;
        if (currentSpread.pages[pp] !== basePage) addFrame(currentSpread.pages[pp]);
    }
    var safety = 0;
    while (story.overflows && safety < 400) {
        var si = -1;
        for (var s = 0; s < doc.spreads.length; s++) { if (doc.spreads[s].id === currentSpread.id) { si = s; break; } }
        currentSpread = doc.spreads.add(1634104421, doc.spreads[si]);
        for (var pp = 0; pp < currentSpread.pages.length; pp++) {
            if (!story.overflows) break;
            addFrame(currentSpread.pages[pp]);
        }
        safety++;
    }

    // 그룹/문항 수 카운트
    var qCount = 0, gCount = 0;
    for (var p = 0; p < story.paragraphs.length; p++) {
        var nm = story.paragraphs[p].appliedParagraphStyle.name;
        if (nm === "실전문제_번호") qCount++;
        if (nm === "다음 글을 읽고") gCount++;
    }
    logLines.push("PART2: " + gCount + "그룹 " + qCount + "문항 (" + story.paragraphs.length + "단락)");
    return qCount;
}

// ===== PART2 정답지 조판 =====
function typesetPart2Answers(doc, answersData, logLines) {
    // 정답지 스토리 찾기: 해설_번호 사본 스타일이 적용된 스토리
    var ansStory = findAnswerStory(doc);

    if (!ansStory) {
        logLines.push("정답: 정답지 스토리 없음 - 스킵");
        return 0;
    }

    var silGrp = doc.paragraphStyleGroups.itemByName("A ver")
                    .paragraphStyleGroups.itemByName("\uC2E4\uC804\uBB38\uC81C");
    var sNum = silGrp.paragraphStyles.itemByName("\uD574\uC124_\uBC88\uD638 \uC0AC\uBCF8");
    var sAns = silGrp.paragraphStyles.itemByName("\uC815\uB2F5 \uC0AC\uBCF8");
    var sSrc = silGrp.paragraphStyles.itemByName("\uC815\uB2F5\uC9C0 \uCD9C\uCC98"); // \uC815\uB2F5\uC9C0 \uD5E4\uB354(\uC0AC\uC6A9\uC790 \uCD94\uAC00)
    if (!sSrc || !sSrc.isValid) sSrc = silGrp.paragraphStyles.itemByName("\uCD9C\uCC98");

    if (!sNum.isValid || !sAns.isValid) {
        logLines.push("정답: 스타일 없음 - 스킵");
        return 0;
    }

    // 텍스트 빌드 — answersData = [{text, style}]
    //   style: 0 = 해설_번호 사본, 1 = 정답 사본(정답·해설 본문), 2 = 출처(헤더)
    var textParts = [];
    var styleCodes = [];
    for (var i = 0; i < answersData.length; i++) {
        textParts.push(answersData[i].text);
        styleCodes.push(answersData[i].style);
    }

    ansStory.contents = "";
    ansStory.contents = textParts.join("\r");

    var srcObj = (sSrc && sSrc.isValid) ? sSrc : sAns;
    var sObjs = [sNum, sAns, srcObj];
    for (var p = 0; p < ansStory.paragraphs.length && p < styleCodes.length; p++) {
        var c = styleCodes[p];
        if (c == null || c < 0 || c >= sObjs.length) c = 1;
        ansStory.paragraphs[p].appliedParagraphStyle = sObjs[c];
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

// 대화상자 억제 (폰트/링크 경고로 자동화가 멈추지 않도록) — finally에서 원복
var _origUIL = app.scriptPreferences.userInteractionLevel;
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
try {

// InDesign 파일 열기
var inddFile = new File(settings.indd_path);
// 같은 파일이 이미 열려 있으면 닫기 (재실행 시 stale 문서 충돌 = Object is invalid 방지)
// iCloud Documents 경로 이중성(~/Documents == ~/Library/Mobile Documents/.../Documents) 대응
function _suf(p){ var k=p.lastIndexOf("/Documents/"); return k>=0 ? p.substring(k) : p; }
var _tf = inddFile.fsName, _ts = _suf(_tf);
for (var _di = app.documents.length - 1; _di >= 0; _di--) {
    try {
        var _df = app.documents[_di].fullName.fsName;
        if (_df === _tf || _suf(_df) === _ts) app.documents[_di].close(SaveOptions.NO);
    } catch (e) {}
}
dbg("opening");
var doc = app.open(inddFile);

app.doScript(function() {
  var __step = "start"; dbg("start");
  try {
    // PART1 조판
    __step = "part1"; dbg("part1");
    typesetPart1(doc, data.part1, logLines);

    // PART2 본문 조판
    __step = "part2main"; dbg("part2main");
    typesetPart2Main(doc, data.part2.intro || [], data.part2.main, settings, logLines);

    // PART2 정답지 조판 (정답 데이터 있을 때만 — 없으면 기존 정답 스토리 보존)
    __step = "part2answers"; dbg("part2answers");
    if (data.part2.answers && data.part2.answers.length > 0) {
        typesetPart2Answers(doc, data.part2.answers, logLines);
    } else {
        logLines.push("정답: 입력 없음 - 기존 정답 스토리 보존(스킵)");
    }

    // 빈 페이지 정리: PART2 본문 끝 ~ 정답 시작 사이에 내용 없는 페이지 제거
    // (PART2 스토리 축소 시 프레임만 사라지고 페이지가 남아 누적되는 문제 해결)
    __step = "cleanup"; dbg("cleanup");
    try {
        var _p1s = findBiggestStory(doc.pages[5]);
        var _anss = findAnswerStory(doc);
        var _p2s = null, _mxp = 0;
        for (var _s = 0; _s < doc.stories.length; _s++) {
            var _st = doc.stories[_s];
            if (_st === _p1s || _st === _anss) continue;
            if (_st.paragraphs.length > _mxp && _st.paragraphs.length < 9000) { _mxp = _st.paragraphs.length; _p2s = _st; }
        }
        function _lastPg(st){ var tc = st.textContainers; var pg = tc[tc.length-1].parentPage; return pg ? pg.documentOffset : -1; }
        function _firstPg(st){ var pg = st.textContainers[0].parentPage; return pg ? pg.documentOffset : -1; }
        var _from = _p2s ? _lastPg(_p2s) : -1;
        var _to = _anss ? _firstPg(_anss) : doc.pages.length;
        var _removed = 0;
        if (_from >= 0 && _to > _from + 1) {
            var _lo = _from + 1, _hi = _to - 1, _allEmpty = true;
            for (var _pi = _lo; _pi <= _hi; _pi++) {
                if (doc.pages[_pi].pageItems.length !== 0) { _allEmpty = false; break; }
            }
            if (_allEmpty) {
                doc.pages.itemByRange(doc.pages[_lo], doc.pages[_hi]).remove(); // 범위 한 번에 제거(빠름)
                _removed = _hi - _lo + 1;
            } else {
                for (var _pi2 = _hi; _pi2 >= _lo; _pi2--) {
                    try { if (doc.pages[_pi2].pageItems.length === 0) { doc.pages[_pi2].remove(); _removed++; } } catch(e) {}
                }
            }
        }
        logLines.push("빈 페이지 제거: " + _removed + "개 (본문끝 p" + (_from+1) + " ~ 정답 p" + (_to+1) + ")");
    } catch(e) { logLines.push("빈 페이지 정리 오류: " + e.message); }

    // 오버플로우 체크
    __step = "overflow"; dbg("overflow");
    var overflowCount = 0;
    for (var s = 0; s < doc.stories.length; s++) {
        try { if (doc.stories[s].overflows) overflowCount++; } catch(e) {}
    }
    logLines.push("오버플로우: " + overflowCount + "개");

    // PDF 내보내기
    __step = "pdf"; dbg("pdf");
    try {
        var pdfFile = new File(settings.output_dir + "/" + doc.name.replace(".indd", ".pdf"));
        app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES; // 전체 페이지 보장
        doc.exportFile(ExportFormat.PDF_TYPE, pdfFile);
        logLines.push("PDF: 성공");
    } catch(e) {
        logLines.push("PDF: 실패 - " + e.message);
    }

    // 저장
    __step = "save"; dbg("save");
    doc.save();
  } catch(__e) {
    var __ef = new File("/tmp/run_err.txt"); __ef.open("w"); __ef.encoding = "UTF-8";
    __ef.write("STEP=" + __step + "  ERR=" + __e.message + "  @line " + __e.line); __ef.close();
    logLines.push("[오류] " + __step + ": " + __e.message + " @line " + __e.line);
  }
}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "세서특필 조판");

// 로그 기록
writeLog(settings.output_dir, logLines);

} finally {
  // 사용자 상호작용 레벨 원복 (조판 후 InDesign이 비대화 상태로 남지 않도록)
  try { app.scriptPreferences.userInteractionLevel = _origUIL; } catch(e) {}
}

})();
