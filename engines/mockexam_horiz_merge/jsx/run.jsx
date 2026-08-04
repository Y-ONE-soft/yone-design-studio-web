// [ENGINE TEMPLATE] 모의고사 가로판 결합 JSX — 수동 MergeMockExam.jsx 흡수.
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작 요약 (수동본 파리티 — 다이얼로그/alert 만 제거):
//   1) settings.sources 의 각 .indd(로컬 사본) 를 창 없이 열고 마커 수집
//      (마커 = A마스터 페이지 + 6자리 문제 코드)
//   2) 코드별 페이지 범위를 섹션 번호 임시 재설정(순차 폴리오) 후
//      개별 PDF export → job_dir/pdf_parts/
//   3) python3 CoreGraphics 로 부분 PDF 결합 → output_pdf
//      (page.move() 없음 — 페이지 순서/마스터 문제 없음, 원본 무수정)
//   4) settings.save_indd 면 첫 코드 문서 saveACopy → 범위 외 삭제 →
//      나머지 코드 페이지 duplicate → output_indd
//   5) 우리가 연 문서만 닫기 (사용자 문서 무접촉)
#target indesign

(function () {

    // ───────────────────────────────────────────────────────────────
    // settings.json 로드 + 로그 헬퍼
    // ───────────────────────────────────────────────────────────────

    var SETTINGS_PATH = "__SETTINGS_PATH__";

    function readJSON(path) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (!f.open("r")) throw new Error("settings 열기 실패: " + path);
        var raw = f.read();
        f.close();
        return eval("(" + raw + ")");
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n; }
    function ts() {
        var d = new Date();
        return "[" + pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" +
               pad2(d.getSeconds()) + "] ";
    }

    // settings 로드 실패 시에도 job_dir 로그에 흔적 (부트스트랩 try-catch)
    var settings;
    try {
        settings = readJSON(SETTINGS_PATH);
    } catch (eBoot) {
        try {
            var _ef = new File(new File(SETTINGS_PATH).parent.fsName + "/merge_log.txt");
            _ef.encoding = "UTF-8";
            if (_ef.open("a")) {
                _ef.write(ts() + "[치명적 오류] settings 로드 실패: " +
                          (eBoot.message || eBoot) + "\n");
                _ef.close();
            }
        } catch (eEf) {}
        throw eBoot;
    }

    var LOG_PATH  = settings.log_path;
    var LOG_PATHS = settings.log_paths || [];

    function writeLog(msg) {
        var line = ts() + msg + "\n";
        var paths = [LOG_PATH];
        for (var i = 0; i < LOG_PATHS.length; i++) paths.push(LOG_PATHS[i]);
        for (var pi = 0; pi < paths.length; pi++) {
            try {
                var lf = new File(paths[pi]);
                lf.encoding = "UTF-8";
                if (lf.open("a")) { lf.write(line); lf.close(); }
            } catch (eL) {}
        }
    }

    function fail(msg) { writeLog("[오류] " + msg); }

    // ───────────────────────────────────────────────────────────────
    // 문서 캐시 / 마커 수집 (수동 MergeMockExam.jsx 동일)
    // ───────────────────────────────────────────────────────────────

    function getDoc(file, cache) {
        var key = file.absoluteURI;
        if (cache[key]) return { doc: cache[key], opened: false };
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (app.documents[d].fullName.toString() === file.toString()) {
                    cache[key] = app.documents[d];
                    return { doc: cache[key], opened: false };
                }
            } catch (e) {}
        }
        var doc = app.open(file, false);
        cache[key] = doc;
        return { doc: doc, opened: true };
    }

    // A마스터 페이지의 구간 시작 마커 — 6자리 코드 또는 [QQ]/[QQ~QQ] 표기.
    // 수동 MergeMockExam.jsx는 6자리 코드만 봤지만, 가로판(전체 C) 실물은
    // 지문 시작을 [32] 같은 문제번호 표기로 적는 경우가 많다 (E2E 실측:
    // 26년 3월 전체(C) 마커 0개 / c20 덤프 [20]~[35] 실증) —
    // MergeMockExamSero.jsx 의 검증된 마커 로직(qNum + sameAsLast)을 사용.
    // 문단구분자(U+2029)/공백으로 시작하는 프레임 contents 선두 정리.
    // 원시 U+2029 를 소스에 직접 쓰면 컴파일이 깨지므로 charCode 로 비교.
    function lstrip(s) {
        while (s.length) {
            var cc = s.charCodeAt(0);
            if (cc === 0x2029 || cc === 0x2028 || cc <= 32) s = s.substring(1);
            else break;
        }
        return s;
    }

    // 페이지 1장에서 마커 후보를 "전부" 수집.
    // wantCode=true  → 6자리 코드 (페이지 내 여러 개 모두)
    // wantCode=false → 지문 앞 문항번호("33 Anthropologist", "41~42 A ball")
    //                  및 대괄호 표기 [32]
    function collectPageMarkers(page, wantCode) {
        var found = [];
        var seen  = {};
        var items;
        try { items = page.allPageItems; } catch (ep) { return found; }

        for (var f = 0; f < items.length; f++) {
            var txt;
            try { txt = items[f].contents; } catch (ef) { continue; }
            if (typeof txt !== 'string' || !txt) continue;

            if (wantCode) {
                var codes = txt.match(/\d{6}/g);
                if (!codes) continue;
                for (var c = 0; c < codes.length; c++) {
                    if (seen['c' + codes[c]]) continue;
                    seen['c' + codes[c]] = true;
                    found.push({ code: codes[c], qNum: null, qNumEnd: null });
                }
            } else {
                var head = lstrip(txt);
                var mq = /^(\d{1,2})(?:\s*[~\-]\s*(\d{1,2}))?\s+[A-Z]/.exec(head);
                if (!mq) {
                    mq = /\[\s*(\d{1,2})(?:\s*[~\-]\s*(\d{1,2}))?\s*\]/.exec(txt);
                }
                if (!mq) continue;
                var key = 'q' + mq[1] + '-' + (mq[2] || '');
                if (seen[key]) continue;
                seen[key] = true;
                found.push({ code: null, qNum: mq[1], qNumEnd: mq[2] || null });
            }
        }
        return found;
    }

    function findAllMarkers(doc) {
        // A마스터 페이지 목록
        var aPages = [];
        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];
            var mn;
            try { mn = page.appliedMaster.name; } catch (e) { continue; }
            if (!mn || mn.charAt(0).toUpperCase() !== 'A') continue;
            aPages.push({ page: page, index: i });
        }

        // 회차별 표기 방식 판정 — A파트에 6자리 코드가 하나라도 있으면 코드 모드,
        // 전무하면(23년11월/24년6월/23년6월 실측) 문항번호 모드.
        var hasCode = false;
        for (var a = 0; a < aPages.length && !hasCode; a++) {
            if (collectPageMarkers(aPages[a].page, true).length > 0) hasCode = true;
        }

        var markers = [];
        for (var b = 0; b < aPages.length; b++) {
            var got = collectPageMarkers(aPages[b].page, hasCode);
            for (var g = 0; g < got.length; g++) {
                markers.push({
                    code:      got[g].code,
                    qNum:      got[g].qNum,
                    qNumEnd:   got[g].qNumEnd,
                    pageIndex: aPages[b].index,
                    pageName:  aPages[b].page.name
                });
            }
        }
        return markers;   // 페이지 순으로 push — 별도 정렬 불필요
    }

    // 코드 → 마커 인덱스: 6자리 코드 일치 우선, 없으면 [QQ]/[QQ~QQ] 범위 매칭
    function findMarkerIndex(markers, code) {
        for (var i = 0; i < markers.length; i++) {
            if (markers[i].code === code) return i;
        }
        var qqInt = parseInt(code.substring(4, 6), 10);
        for (var j = 0; j < markers.length; j++) {
            var m = markers[j];
            if (!m.qNum) continue;
            var s = parseInt(m.qNum, 10);
            var e = m.qNumEnd ? parseInt(m.qNumEnd, 10) : s;
            if (qqInt >= s && qqInt <= e) return j;
        }
        return -1;
    }

    function getCodeRange(markers, code, srcDoc) {
        var idx = findMarkerIndex(markers, code);
        if (idx === -1) return null;
        var startIdx = markers[idx].pageIndex;

        // 한 페이지에 문항이 2개면 마커도 2개(같은 pageIndex) — 단순히
        // markers[idx+1] 을 쓰면 endIdx < startIdx 가 된다. 페이지가
        // "실제로 넘어가는" 다음 마커를 찾는다.
        var endIdx = null;
        for (var j = idx + 1; j < markers.length; j++) {
            if (markers[j].pageIndex > startIdx) {
                endIdx = markers[j].pageIndex - 1;
                break;
            }
        }
        if (endIdx === null) endIdx = srcDoc.pages.length - 1;

        // A마스터가 끊기는 지점을 넘지 않는다. 다음 A마스터 마커까지로만
        // 자르면 사이에 낀 B마스터(= 다음 섹션 시작) 페이지를 흡수한다
        // (실측: 23년3월 32번 구간에 다른 섹션의 33번 p13 이 딸려옴).
        for (var k = startIdx + 1; k <= endIdx; k++) {
            var mn;
            try { mn = srcDoc.pages[k].appliedMaster.name; }
            catch (e) { mn = ''; }
            if (!mn || mn.charAt(0).toUpperCase() !== 'A') {
                endIdx = k - 1;
                break;
            }
        }
        if (endIdx < startIdx) endIdx = startIdx;
        return { startIdx: startIdx, endIdx: endIdx };
    }

    // ───────────────────────────────────────────────────────────────
    // 페이지 범위를 순차 번호로 임시 재설정해서 내보낸 뒤 원복 (수동본 동일)
    // ───────────────────────────────────────────────────────────────

    function exportRangeWithNumber(srcDoc, range, startNum, tempPdf, preset) {
        var startIdx  = range.startIdx;
        var endIdx    = range.endIdx;
        var pageCount = endIdx - startIdx + 1;
        var BIG       = 50000;   // 원본 번호 대피용 오프셋

        // Phase 1: 원본 섹션 전체 저장
        var saved = [];
        for (var s = 0; s < srcDoc.sections.length; s++) {
            try {
                saved.push({
                    sec:    srcDoc.sections[s],
                    num:    srcDoc.sections[s].pageNumberStart,
                    isCont: srcDoc.sections[s].continueNumbering,
                    pfx:    srcDoc.sections[s].sectionPrefix
                });
            } catch (e) {}
        }

        // Phase 2: continueNumbering=false 섹션을 BIG번대로 대피
        for (var s2 = 0; s2 < saved.length; s2++) {
            if (!saved[s2].isCont) {
                try {
                    saved[s2].sec.pageNumberStart = saved[s2].num + BIG;
                    saved[s2].sec.sectionPrefix   = '';
                } catch (e) {}
            }
        }

        // Phase 3: 내보낼 구간에 순차 번호 섹션 삽입
        var secStart = null, secAfter = null;
        try {
            secStart = srcDoc.sections.add(srcDoc.pages[startIdx]);
            secStart.continueNumbering = false;
            secStart.pageNumberStart   = startNum;
            secStart.sectionPrefix     = '';
        } catch (eAdd) {}

        var afterIdx = endIdx + 1;
        if (afterIdx < srcDoc.pages.length) {
            var afterBigNum = parseInt(srcDoc.pages[afterIdx].name, 10);
            try {
                secAfter = srcDoc.sections.add(srcDoc.pages[afterIdx]);
                secAfter.continueNumbering = false;
                secAfter.pageNumberStart   = afterBigNum;
                secAfter.sectionPrefix     = '';
            } catch (eAdd2) {}
        }

        // Phase 4: 내보내기
        // pageRange 는 "섹션 페이지 번호"가 아니라 "+n" 절대 페이지 문법으로
        // 지정한다. 번호 기반("1-2")은 continueNumbering=true 인 섹션이
        // 대피 대상에서 빠져 같은 번호가 문서에 중복 존재할 때 InDesign 이
        // 범위를 무시하고 전 페이지를 내보낸다 (실측: 부분 PDF 5개 중 4개가
        // 소스 전체 256~317p 로 나옴 — 2026-08-04).
        var newRange = '+' + (startIdx + 1) + '-+' + (endIdx + 1);
        app.pdfExportPreferences.pageRange = newRange;

        try {
            if (preset && preset.isValid) {
                srcDoc.exportFile(ExportFormat.PDF_TYPE, tempPdf, false, preset);
            } else {
                srcDoc.exportFile(ExportFormat.PDF_TYPE, tempPdf, false);
            }
            return tempPdf.exists;
        } finally {
            // Phase 5: 임시 섹션 제거 & 원본 복원
            if (secAfter) { try { secAfter.remove(); } catch (er) {} }
            if (secStart) { try { secStart.remove(); } catch (er2) {} }
            for (var s3 = 0; s3 < saved.length; s3++) {
                try {
                    saved[s3].sec.pageNumberStart = saved[s3].num;
                    saved[s3].sec.sectionPrefix   = saved[s3].pfx;
                } catch (er3) {}
            }
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 결합 .indd 저장 (수동 saveAsIndd 동일)
    // ───────────────────────────────────────────────────────────────

    function saveAsIndd(orderedCodes, codeFileMap, markersCache, inddPath) {
        var validCodes = [];
        var seenM = {};   // 같은 페이지 구간은 1회만 (PDF 쪽 seenRanges 와 동일 기준)
        for (var ci = 0; ci < orderedCodes.length; ci++) {
            var c0 = orderedCodes[ci];
            if (!codeFileMap[c0]) continue;
            var u0  = codeFileMap[c0].uri;
            var rg0 = getCodeRange(markersCache[u0], c0, codeFileMap[c0].doc);
            if (!rg0) continue;
            var k0 = u0 + "#" + rg0.startIdx + "-" + rg0.endIdx;
            if (seenM[k0]) continue;
            seenM[k0] = true;
            validCodes.push(c0);
        }
        if (validCodes.length === 0) return { ok: false, error: '유효한 코드 없음' };

        var inddFile = new File(inddPath);
        var firstSrc = codeFileMap[validCodes[0]].doc;

        // 첫 소스의 사본을 그릇으로 쓴다 — 마스터/스타일/스와치를 그대로
        // 물려받기 위해서다(빈 새 문서에 duplicate 하면 마스터가 없어
        // 상단 장식과 푸터가 통째로 빠진다 — 실측 2026-08-04).
        //
        // 단, 사본에서 "범위 밖 페이지를 지워 첫 구간만 남기는" 기존 방식은
        // 쓰지 않는다. 본편이 하나로 연결된(threaded) 스토리라 삭제된
        // 페이지의 텍스트가 남은 프레임으로 되흘러 첫 페이지가 그 회차
        // 20번 지문으로 바뀌었다(+ 오버셋 1건).
        //
        // 대신 (1) 필요한 구간을 전부 맨 뒤에 duplicate 하고 — 복제본은
        // 원본 스토리와 무관한 독립 사본이다 — (2) 원래 페이지 전체를
        // 지운다. 되흐름은 어차피 전부 삭제될 페이지들 사이에서만 일어난다.
        firstSrc.saveACopy(inddFile);

        var newDoc = app.open(inddFile, false);
        try {
            var origCount = newDoc.pages.length;

            for (var ci2 = 0; ci2 < validCodes.length; ci2++) {
                var c    = validCodes[ci2];
                var sd   = codeFileMap[c].doc;
                var sUri = codeFileMap[c].uri;
                var rg   = getCodeRange(markersCache[sUri], c, sd);
                if (!rg) continue;
                for (var p2 = rg.startIdx; p2 <= rg.endIdx; p2++) {
                    try {
                        sd.pages[p2].duplicate(
                            LocationOptions.AT_END, newDoc.pages.lastItem());
                    } catch (eDup) {}
                }
            }

            if (newDoc.pages.length <= origCount) {
                return { ok: false, error: '구간 복제 0건' };
            }

            // 그릇으로 쓴 원본 페이지 전량 제거 (뒤에서 앞으로)
            for (var p3 = origCount - 1; p3 >= 0; p3--) {
                try { newDoc.pages[p3].remove(); } catch (eRm) {}
            }

            newDoc.save();
            return { ok: true, path: inddFile.fsName };
        } finally {
            try { newDoc.close(SaveOptions.NO); } catch (eClose) {}
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 메인
    // ───────────────────────────────────────────────────────────────

    try {
        var SOURCES    = settings.sources || [];
        var OUTPUT_PDF = settings.output_pdf;
        var PARTS_DIR  = settings.pdf_parts_dir;

        writeLog("===== 모의고사 가로판 결합 시작 =====");
        writeLog("소스: " + SOURCES.length + "개");

        // 소스 파일 열기 + 마커 수집 (같은 파일은 1회)
        var docCache     = {};
        var openedByUs   = {};
        var codeFileMap  = {};   // code → { doc, uri }
        var markersCache = {};   // uri  → markers[]
        var orderedCodes = [];   // 입력 순서 (중복 제거는 엔진 parse에서 완료)

        for (var si = 0; si < SOURCES.length; si++) {
            var src = SOURCES[si];
            orderedCodes.push(src.code);
            var srcFile = new File(src.local_path);
            if (!srcFile.exists) {
                writeLog("[경고] 소스 누락: " + src.local_path);
                continue;
            }
            var uri = srcFile.absoluteURI;
            if (!markersCache[uri]) {
                var got;
                try { got = getDoc(srcFile, docCache); }
                catch (eOp) {
                    writeLog("[경고] 소스 열기 실패: " + srcFile.fsName +
                             " — " + eOp.message);
                    continue;
                }
                if (got.opened) openedByUs[uri] = true;
                markersCache[uri] = findAllMarkers(got.doc);
                writeLog(srcFile.displayName + ": 마커 " +
                         markersCache[uri].length + "개 / " +
                         got.doc.pages.length + "p");
            }
            // 이 파일이 코드를 커버하면 매핑 (6자리 일치 또는 [QQ] 범위)
            if (!codeFileMap[src.code] &&
                findMarkerIndex(markersCache[uri], src.code) !== -1) {
                codeFileMap[src.code] = { doc: docCache[uri], uri: uri };
            }
        }

        // PDF export preferences 백업 + 위험 설정 정규화
        // (사용자 UI 잔존 설정 상속 방지 — 2026-05-28 페이지별 분할 사례)
        var savedRange   = app.pdfExportPreferences.pageRange;
        var savedSpreads = app.pdfExportPreferences.exportReaderSpreads;
        app.pdfExportPreferences.exportReaderSpreads = false;
        try { app.pdfExportPreferences.exportAsSinglePages = false; } catch (eSp) {}
        try { app.pdfExportPreferences.viewPDF = false; } catch (eVp) {}

        var preset = null;
        if (settings.pdf_preset) {
            try { preset = app.pdfExportPresets.itemByName(settings.pdf_preset); }
            catch (ePre) {}
        }

        var tempPdfPaths = [];
        var expectedRows = [];  // 부분 PDF 기대 페이지수 (Python verify 대조용)
        var pageCounter  = 1;   // 결합 PDF 순차 폴리오
        // 같은 페이지 구간이 여러 코드로 지목돼도 1회만 삽입.
        // 키는 마커 인덱스가 아니라 "구간"이어야 한다 — 가로판은 한 페이지에
        // 문항이 2개라 32번/33번이 서로 다른 마커면서 같은 페이지를 가리키고,
        // 마커 인덱스로 키를 잡으면 같은 페이지가 두 번 실린다(실측: 15p 중
        // 2p가 중복 — 23년11월 32/33, 21년11월 32/33).
        var seenRanges   = {};

        for (var ci = 0; ci < orderedCodes.length; ci++) {
            var code = orderedCodes[ci];
            var meta = SOURCES[ci];
            var label = (meta && meta.display) ? meta.display : code;

            if (!codeFileMap[code]) {
                if (meta && meta.from_range) {
                    writeLog("[정보] 해당 지문 없음 — 건너뜀: " + label);
                } else {
                    writeLog("[경고] A마스터 페이지에서 코드를 찾을 수 없음: " + label);
                }
                continue;
            }

            var srcDoc  = codeFileMap[code].doc;
            var srcUri  = codeFileMap[code].uri;
            var range   = getCodeRange(markersCache[srcUri], code, srcDoc);

            if (!range) {
                writeLog("[경고] 페이지 범위 계산 실패: " + label);
                continue;
            }

            var rKey = srcUri + '#' + range.startIdx + '-' + range.endIdx;
            if (seenRanges[rKey]) {
                writeLog("[정보] 같은 페이지에 이미 실림 — 건너뜀: " + label +
                         " (" + seenRanges[rKey] + " 와 동일 페이지)");
                continue;
            }
            seenRanges[rKey] = label;

            var tempPdf = new File(PARTS_DIR + '/part_' +
                                   (ci < 10 ? '0' + ci : ci) + '_' + code + '.pdf');
            try {
                var exported = exportRangeWithNumber(
                    srcDoc, range, pageCounter, tempPdf, preset);
                if (exported) {
                    var cnt = range.endIdx - range.startIdx + 1;
                    pageCounter += cnt;
                    tempPdfPaths.push(tempPdf.fsName);
                    expectedRows.push(tempPdf.fsName + '\t' + cnt + '\t' + label);
                    writeLog(label + ": p" + range.startIdx + "~" +
                             range.endIdx + " (" + cnt + "p) export OK");
                } else {
                    writeLog("[경고] 부분 PDF 생성 실패: " + label);
                }
            } catch (eExp) {
                writeLog("[경고] 내보내기 오류: " + label + " — " + eExp.message);
            }
        }

        // export preferences 복원
        try { app.pdfExportPreferences.pageRange           = savedRange;   } catch (e1) {}
        try { app.pdfExportPreferences.exportReaderSpreads = savedSpreads; } catch (e2) {}

        // 부분 PDF 기대 페이지수 기록 — JSX 는 PDF 페이지수를 셀 수 없으므로
        // 실제 대조는 engine.verify(Python) 가 한다.
        try {
            var expFile = new File(PARTS_DIR + '/_expected.txt');
            expFile.encoding = 'UTF-8';
            expFile.lineFeed = 'Unix';
            expFile.open('w');
            expFile.write(expectedRows.join('\n'));
            expFile.close();
        } catch (eExpW) {
            writeLog("[경고] 기대 페이지수 기록 실패: " + eExpW.message);
        }

        if (tempPdfPaths.length === 0) {
            fail("처리된 코드가 없습니다 — 부분 PDF 0개");
        } else {
            // ── python3 CoreGraphics 결합 (수동본 동일 — 경로만 job_dir) ──
            var pathsTxt = new File(settings.paths_txt);
            pathsTxt.encoding = 'UTF-8';
            pathsTxt.open('w');
            pathsTxt.writeln(OUTPUT_PDF);
            for (var ti = 0; ti < tempPdfPaths.length; ti++) {
                pathsTxt.writeln(tempPdfPaths[ti]);
            }
            pathsTxt.close();

            var pathsTxtPy = settings.paths_txt.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
            var pyCode = [
                'import sys, ctypes, ctypes.util',
                'CF = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))',
                'CG = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))',
                'class CGPoint(ctypes.Structure):',
                '    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]',
                'class CGSize(ctypes.Structure):',
                '    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]',
                'class CGRect(ctypes.Structure):',
                '    _fields_ = [("origin", CGPoint), ("size", CGSize)]',
                'CF.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p',
                'CF.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]',
                'CF.CFRelease.argtypes = [ctypes.c_void_p]',
                'CG.CGPDFDocumentCreateWithURL.restype = ctypes.c_void_p',
                'CG.CGPDFDocumentCreateWithURL.argtypes = [ctypes.c_void_p]',
                'CG.CGPDFDocumentGetNumberOfPages.restype = ctypes.c_size_t',
                'CG.CGPDFDocumentGetNumberOfPages.argtypes = [ctypes.c_void_p]',
                'CG.CGPDFDocumentGetPage.restype = ctypes.c_void_p',
                'CG.CGPDFDocumentGetPage.argtypes = [ctypes.c_void_p, ctypes.c_size_t]',
                'CG.CGPDFPageGetBoxRect.restype = CGRect',
                'CG.CGPDFPageGetBoxRect.argtypes = [ctypes.c_void_p, ctypes.c_int]',
                'CG.CGPDFDocumentRelease.argtypes = [ctypes.c_void_p]',
                'CG.CGPDFContextCreateWithURL.restype = ctypes.c_void_p',
                'CG.CGPDFContextCreateWithURL.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGRect), ctypes.c_void_p]',
                'CG.CGContextBeginPage.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGRect)]',
                'CG.CGContextEndPage.argtypes = [ctypes.c_void_p]',
                'CG.CGContextRelease.argtypes = [ctypes.c_void_p]',
                'CG.CGContextDrawPDFPage.argtypes = [ctypes.c_void_p, ctypes.c_void_p]',
                'def url(p):',
                '    b = p.encode("utf-8")',
                '    return CF.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)',
                'with open("' + pathsTxtPy + '", encoding="utf-8") as f:',
                '    lines = [l.strip() for l in f if l.strip()]',
                'out_path = lines[0]; in_paths = lines[1:]',
                'docs = []',
                'for p in in_paths:',
                '    u = url(p); d = CG.CGPDFDocumentCreateWithURL(u); CF.CFRelease(u)',
                '    if d: docs.append((d, CG.CGPDFDocumentGetNumberOfPages(d)))',
                'if not docs: sys.exit("no docs")',
                'fp = CG.CGPDFDocumentGetPage(docs[0][0], 1)',
                'ir = CG.CGPDFPageGetBoxRect(fp, 0)',
                'ou = url(out_path)',
                'ctx = CG.CGPDFContextCreateWithURL(ou, ctypes.byref(ir), None)',
                'CF.CFRelease(ou)',
                'if not ctx: sys.exit("no ctx")',
                'for d, n in docs:',
                '    for i in range(1, n+1):',
                '        pg = CG.CGPDFDocumentGetPage(d, i)',
                '        if not pg: continue',
                '        r = CG.CGPDFPageGetBoxRect(pg, 0)',
                '        CG.CGContextBeginPage(ctx, ctypes.byref(r))',
                '        CG.CGContextDrawPDFPage(ctx, pg)',
                '        CG.CGContextEndPage(ctx)',
                'CG.CGContextRelease(ctx)',
                'for d, n in docs: CG.CGPDFDocumentRelease(d)',
                'print("OK")'
            ].join('\n');

            var pyFile = new File(settings.combine_py);
            pyFile.encoding = 'UTF-8';
            pyFile.open('w');
            pyFile.write(pyCode);
            pyFile.close();

            try {
                app.doScript(
                    'do shell script "python3 " & quoted form of "' +
                    pyFile.fsName + '"',
                    ScriptLanguage.APPLESCRIPT_LANGUAGE
                );
            } catch (eCombine) {
                fail("PDF 결합 실패: " + eCombine.message);
            }

            var outPdfFile = new File(OUTPUT_PDF);
            for (var wPdf = 0; wPdf < 20 && !outPdfFile.exists; wPdf++) { $.sleep(500); }
            if (outPdfFile.exists) {
                writeLog("PDF: " + outPdfFile.fsName +
                         " (" + (pageCounter - 1) + "p)");
            } else {
                writeLog("[경고] 결합 PDF 파일이 생성되지 않음");
            }
        }

        // ── INDD 결합 (옵션 — 수동 체크박스 기본 ON 파리티) ─────────────
        if (settings.save_indd && tempPdfPaths.length > 0) {
            try {
                var inddRes = saveAsIndd(orderedCodes, codeFileMap,
                                         markersCache, settings.output_indd);
                if (inddRes.ok) {
                    writeLog("INDD: " + inddRes.path);
                } else {
                    writeLog("[경고] INDD 저장 실패: " + inddRes.error);
                }
            } catch (eIndd) {
                writeLog("[경고] INDD 저장 실패: " + eIndd.message);
            }
        }

        // 소스 문서 닫기 (우리가 연 것만 — 사용자 문서 무접촉)
        for (var u in openedByUs) {
            try { docCache[u].close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        writeLog("[치명적 오류] " + (eMain.message || eMain));
    }

})();
