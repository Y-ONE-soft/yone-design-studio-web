// [ENGINE TEMPLATE] 배N제 조판 자동화
// 파이프라인: settings.json 로드 -> 원본 열기 -> RTF 배치 -> 스타일 적용 -> PDF 출력

var settingsPath = "/SETTINGS_PLACEHOLDER/settings.json";

// ── 설정 로드 ────────────────────────────────────────────────────────────
var sf = new File(settingsPath);
sf.encoding = "UTF-8";
sf.open("r");
var settings = eval("(" + sf.read() + ")");
sf.close();

var rtfPath    = settings.rtf_path;
var inddPath   = settings.indd_path;
var outputDir  = settings.output_dir;
var schoolName = settings.school   || "";
var issueNum   = settings.issue_num || "01";

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

// ── RTF 배치 ─────────────────────────────────────────────────────────────
var firstFrame = mainStory.textContainers[0];
firstFrame.place(new File(rtfPath));
writeLog("RTF \ubc30\uce58 \uc644\ub8cc: " + rtfPath);

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
    var paras = ft.paragraphs;
    var qCount = 0;

    for (var i = 0; i < paras.length; i++) {
        var p   = paras[i];
        var txt = p.contents;

        // PRESERVE 스타일 → 상태 초기화 후 건너뜀
        if (PRESERVE[p.appliedParagraphStyle.name]) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
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

        // 문제 발문 감지: 한글? / 시오. / 윗글|위 글 + ?
        var isMundae = (
            /[\uAC00-\uD7A3]\?/.test(txt) ||
            /\uc2dc\uc624\./.test(txt) ||
            (/(\uc717\uae00|\uc704 \uae00)/.test(txt) && /\?/.test(txt))
        );
        if (isMundae) {
            inBogi = false; inJogon = false; inYoyak = false;
            nextIsGivenSent = /\uc8fc\uc5b4\uc9c4 \ubb38\uc7a5/.test(txt);
            p.appliedParagraphStyle = mundaeStyle;
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
            if (/ \/ /.test(txt)) {
                p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
                continue;
            }
            if (jogeonStyle) { p.appliedParagraphStyle = jogeonStyle; continue; }
        }

        // <보기> 헤더
        if (isBogiHeader) {
            inBogi = true; inJogon = false; inYoyak = false;
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            continue;
        }

        // 다음 글을 읽고
        if (/\ub2e4\uc74c \uae00\uc744 \uc77d\uace0/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
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

        // 답:
        if (/^\s*\ub2f5\s*:/.test(txt)) {
            p.appliedParagraphStyle = seonjiStyle; continue;
        }

        // / 구분자 (보기 단어 목록)
        if (/ \/ /.test(txt)) {
            p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
            continue;
        }

        // 나머지 → 본문 박스
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

    for (var ci = 0; ci < containers.length; ci++) {
        var fr = containers[ci];
        if (!fr.isValid) continue;
        try {
            var frText = fr.texts[0];
            if (frText.length === 0) continue;
            var fParas = frText.paragraphs;
            for (var pi = 0; pi < fParas.length; pi++) {
                var fp = fParas[pi];
                var ftxt = fp.contents.replace(/[\r\n]/g, "");
                var isMundae = (
                    /[\uAC00-\uD7A3]\?/.test(ftxt) ||
                    /\uc2dc\uc624\./.test(ftxt) ||
                    (/(\uc717\uae00|\uc704 \uae00)/.test(ftxt) && /\?/.test(ftxt))
                );
                if (isMundae) {
                    try { fp.startParagraph = StartParagraph.NEXT_FRAME; } catch(e) {}
                }
            }
        } catch(e) {}
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

exportPDF(doc, outputDir, schoolName, issueNum);

doc.save(new File(inddPath));

writeLog("\uc644\ub8cc");
