// [ENGINE TEMPLATE] 분석본 결합 JSX
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작 요약:
//   1) 분석본 마스터 템플릿(.indd) -> 출력 위치로 복사 -> 결합 베이스로 열기
//   2) 베이스 앞 KEEP_HEAD 페이지만 보존, 나머지 페이지 모두 삭제
//   3) settings.sources 의 각 코드별 candidates (.indd 후보 배열)를 열고
//      "(고N) {YY}년 {M}월 {QQ}번" 마커가 있는 페이지 범위를 AT_END 로 duplicate
//      - 같은 코드가 여러 후보에 있을 수 있어 — 가장 먼저 찾힌 후보 사용
//      - 범위 끝은 다음 마커 직전 페이지 (마지막 마커이면 그 파일의 마지막 페이지)
//   4) storyId 라벨 기반 nextTextFrame 재연결 (threaded 본문 보존)
//   5) 저장 + PDF export
#target indesign

(function () {

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

    // settings 로드 실패 시에도 job_dir 로그에 흔적을 남긴다 — 종전에는
    // readJSON 예외가 로그 0바이트 침묵 실패로 빠져 원인 진단이 불가했다.
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
    var LOG_PATH   = settings.log_path;
    var LOG_PATHS  = settings.log_paths || [];

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
    // 문서 open / cache
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

    // ───────────────────────────────────────────────────────────────
    // Story threading 보존 (분석본 본문이 두 페이지에 걸쳐 threaded 일 때 대비)
    // ───────────────────────────────────────────────────────────────

    var SID_PFX = '__anl_sid:';
    var SID_SEP = '|';

    function tagStoryLabels(doc) {
        for (var p = 0; p < doc.pages.length; p++) {
            var frames = doc.pages[p].textFrames;
            for (var f = 0; f < frames.length; f++) {
                var tf = frames[f];
                try {
                    var existing = tf.label || '';
                    if (existing.indexOf(SID_PFX) === 0) continue;
                    var sid;
                    try { sid = String(tf.parentStory.id); } catch (eS) { sid = 'X'; }
                    tf.label = SID_PFX + sid + (existing ? SID_SEP + existing : '');
                } catch (e) {}
            }
        }
    }

    function getSidFromLabel(tf) {
        var lab = '';
        try { lab = tf.label || ''; } catch (e) { return null; }
        if (lab.indexOf(SID_PFX) !== 0) return null;
        var rest = lab.substring(SID_PFX.length);
        var sepIdx = rest.indexOf(SID_SEP);
        return (sepIdx >= 0) ? rest.substring(0, sepIdx) : rest;
    }

    function rethreadGroup(doc, startIdx, endIdx) {
        var byStory = {};
        for (var p = startIdx; p <= endIdx && p < doc.pages.length; p++) {
            var frames = doc.pages[p].textFrames;
            for (var f = 0; f < frames.length; f++) {
                var tf = frames[f];
                var sid = getSidFromLabel(tf);
                if (!sid) continue;
                var gb;
                try { gb = tf.geometricBounds; } catch (eGb) { gb = [0, 0, 0, 0]; }
                if (!byStory[sid]) byStory[sid] = [];
                byStory[sid].push({ pageIdx: p, tf: tf, y: gb[0], x: gb[1] });
            }
        }
        for (var sid in byStory) {
            var arr = byStory[sid];
            if (arr.length < 2) continue;
            arr.sort(function (a, b) {
                if (a.pageIdx !== b.pageIdx) return a.pageIdx - b.pageIdx;
                if (a.y !== b.y) return a.y - b.y;
                return a.x - b.x;
            });
            for (var i = 0; i < arr.length - 1; i++) {
                try { arr[i].tf.nextTextFrame = arr[i + 1].tf; } catch (eTh) {}
            }
        }
    }

    function cleanLabels(doc) {
        for (var p = 0; p < doc.pages.length; p++) {
            var frames = doc.pages[p].textFrames;
            for (var f = 0; f < frames.length; f++) {
                var tf = frames[f];
                var lab = '';
                try { lab = tf.label || ''; } catch (e) { continue; }
                if (lab.indexOf(SID_PFX) !== 0) continue;
                var rest = lab.substring(SID_PFX.length);
                var sepIdx = rest.indexOf(SID_SEP);
                try {
                    tf.label = (sepIdx >= 0) ? rest.substring(sepIdx + 1) : '';
                } catch (eC) {}
            }
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 스프레드 재편성 허용 — 내지 전부 allowPageShuffle = true
    //   소스 분석본의 잠긴(island) spread 가 그대로 복제돼 결과 .indd 의
    //   spread 가 "재편성 비허용"으로 남는 걸 방지. 문서 + 전체 spread 를
    //   모두 재편성 허용으로 풀어 정상 펼침면으로 흐르게 한다.
    //   (engines/final/indesign_stepper.py 와 동일 패턴)
    // ───────────────────────────────────────────────────────────────

    function allowShuffleAll(doc) {
        try { doc.documentPreferences.allowPageShuffle = true; } catch (eDPS) {}
        for (var s = 0; s < doc.spreads.length; s++) {
            try { doc.spreads[s].allowPageShuffle = true; } catch (eSh) {}
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 분석본 마커 탐색 — "(고N) {YY}년 {M}월 {QQ}(-/~{QQ})번"
    //   고 고  년 년  월 월  번 번
    // ───────────────────────────────────────────────────────────────

    var MARKER_PAT = /(?:고\d+\s*)?(\d{1,2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*(?:[\-~]\s*(\d{1,2}))?\s*번/;

    // 헤더가 '연·월' 프레임과 '문항번호' 프레임으로 쪼개진 분석본 대응
    // (2026-08-21 실측: 고2 24년 9월 분석본(New) — 사이드 라벨이 "20번"만이고
    //  "고2 24년 9월"은 별도 프레임/마스터에 남아 MARKER_PAT 이 0건).
    // 오탐 방지: 프레임 내용이 통째로 번호 토큰일 때만 + 전체 마커가 0건인
    // 파일에서만 사용하고, 연·월은 파이썬이 월 폴더 기준으로 넘긴
    // (year, month)로 채운다 — 기존 인식분(전체 마커 파일)은 무변경.
    var QNUM_ONLY_PAT = /^\s*(\d{1,2})\s*(?:[\-~]\s*(\d{1,2}))?\s*번\s*$/;
    var QNUM_ONLY_MAXLEN = 12;

    function isGanjiPage(page) {
        try {
            var masterName = page.appliedMaster.name;
            if (masterName) {
                if (masterName.indexOf("간지") !== -1) return true;
                if (masterName.indexOf("표지") !== -1) return true;
            }
        } catch (eM) {}
        return false;
    }

    function findQNumOnlyMarkers(doc, fbYear, fbMonth) {
        var markers = [];
        var seenKey = {};
        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];
            if (isGanjiPage(page)) continue;

            var foundQ = null, foundQEnd = null;
            try {
                var items = page.allPageItems;
                for (var f = 0; f < items.length; f++) {
                    try {
                        var txt = items[f].contents;
                        if (typeof txt !== "string") continue;
                        if (txt.length === 0 || txt.length > QNUM_ONLY_MAXLEN) continue;
                        var m = QNUM_ONLY_PAT.exec(txt);
                        if (m) {
                            foundQ = m[1];
                            foundQEnd = m[2] || null;
                            break;
                        }
                    } catch (ef) {}
                }
            } catch (ep) {}

            if (foundQ) {
                var key = foundQ + "-" + (foundQEnd || "");
                if (seenKey[key]) continue;
                seenKey[key] = true;
                markers.push({
                    year: fbYear, month: fbMonth,
                    qNum: foundQ, qNumEnd: foundQEnd,
                    pageIndex: i, qnumOnly: true
                });
            }
        }
        markers.sort(function (a, b) { return a.pageIndex - b.pageIndex; });
        return markers;
    }

    function findAllMarkers(doc, fbYear, fbMonth) {
        var markers = [];
        var seenKey = {};  // "Y-M-Q-QE" → 이미 같은 식별자의 마커가 잡혔는지

        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];
            // 1페이지(간지) 마스터는 마커 후보에서 제외 — 표지에 코드 범위가
            // 적혀 있어 false marker 가 잡힘.
            try {
                var masterName = page.appliedMaster.name;
                // 간지/표지/intro 등이 master 이름에 포함되면 skip
                if (masterName) {
                    if (masterName.indexOf("간지") !== -1) continue; // 간지
                    if (masterName.indexOf("표지") !== -1) continue; // 표지
                }
            } catch (eM) {}

            var foundY = null, foundMon = null, foundQ = null, foundQEnd = null;
            try {
                var items = page.allPageItems;
                for (var f = 0; f < items.length; f++) {
                    try {
                        var txt = items[f].contents;
                        if (typeof txt !== "string" || txt.length === 0) continue;
                        var m = MARKER_PAT.exec(txt);
                        if (m) {
                            foundY = m[1];
                            foundMon = m[2];
                            foundQ = m[3];
                            foundQEnd = m[4] || null;
                            break;
                        }
                    } catch (ef) {}
                }
            } catch (ep) {}

            if (foundQ) {
                // 파일 내에서 이미 같은 식별자가 보였으면 중복 마커로 간주하고 skip
                // (분석본 짤지문 같은 데 stale 마커가 남아 있는 경우 대비 → 다음 마커가
                //  새 문제로 잡혀서 이전 문제의 페이지 범위가 끊기는 사고 방지)
                var key = foundY + "-" + foundMon + "-" + foundQ + "-" + (foundQEnd || "");
                if (seenKey[key]) continue;
                seenKey[key] = true;
                markers.push({
                    year: foundY, month: foundMon,
                    qNum: foundQ, qNumEnd: foundQEnd,
                    pageIndex: i
                });
            }
        }
        markers.sort(function (a, b) { return a.pageIndex - b.pageIndex; });
        if (markers.length === 0 && fbYear && fbMonth) {
            markers = findQNumOnlyMarkers(doc, fbYear, fbMonth);
        }
        return markers;
    }

    // 코드(YYMMQQ)로 마커 인덱스 찾기.
    //   month: "03" / "3" 양쪽 매칭, qNum: 단일/범위 양쪽 매칭
    function findMarkerIndex(markers, year, month, qNum) {
        var monthInt = parseInt(month, 10);
        var qInt = parseInt(qNum, 10);

        for (var i = 0; i < markers.length; i++) {
            var m = markers[i];
            if (m.year !== year) continue;
            if (parseInt(m.month, 10) !== monthInt) continue;
            var s = parseInt(m.qNum, 10);
            var e = m.qNumEnd ? parseInt(m.qNumEnd, 10) : s;
            if (qInt >= s && qInt <= e) return i;
        }
        return -1;
    }

    function getCodeRange(markers, year, month, qNum, doc) {
        var idx = findMarkerIndex(markers, year, month, qNum);
        if (idx === -1) return null;
        var startIdx = markers[idx].pageIndex;
        var endIdx   = (idx < markers.length - 1)
                         ? markers[idx + 1].pageIndex - 1
                         : doc.pages.length - 1;
        return { startIdx: startIdx, endIdx: endIdx, markerIdx: idx };
    }

    // ───────────────────────────────────────────────────────────────
    // 메인
    // ───────────────────────────────────────────────────────────────

    try {
        writeLog("===== 분석본 결합 시작 =====");
        var SOURCES = settings.sources || [];
        writeLog("코드: " + SOURCES.length + "개");

        var TEMPLATE_PATH = settings.template_path;
        var OUTPUT_INDD   = settings.output_indd;
        var OUTPUT_PDF    = settings.output_pdf;
        var KEEP_HEAD     = (settings.keep_head != null) ? settings.keep_head : 1;

        var tplFile = new File(TEMPLATE_PATH);
        if (!tplFile.exists) { fail("템플릿 없음: " + TEMPLATE_PATH); return; }

        var outFile = new File(OUTPUT_INDD);
        if (!tplFile.copy(outFile)) { fail("템플릿 복사 실패: " + OUTPUT_INDD); return; }
        writeLog("템플릿 복사 -> " + outFile.fsName);

        var newDoc;
        try { newDoc = app.open(outFile, false); }
        catch (eOpen) { fail("사본 열기 실패: " + eOpen.message); return; }

        // 내지 전부 스프레드 재편성 허용 — 복제 전 문서 기본값 보정
        allowShuffleAll(newDoc);

        // 후보 파일 dedup + open + markers 수집
        var docCache    = {};
        var openedByUs  = {};
        var fileMarkers = {};   // uri → markers[]
        var allCandidates = {}; // uri → File 객체

        for (var si = 0; si < SOURCES.length; si++) {
            var src = SOURCES[si];
            var cands = src.candidates || [];
            for (var ci = 0; ci < cands.length; ci++) {
                var cf = new File(cands[ci]);
                if (!cf.exists) {
                    writeLog("[경고] 후보 누락: " + cands[ci]);
                    continue;
                }
                var uri = cf.absoluteURI;
                if (allCandidates[uri]) continue;
                allCandidates[uri] = cf;
                try {
                    var got = getDoc(cf, docCache);
                    if (got.opened) openedByUs[uri] = true;
                    // 폴백 연·월 = 이 후보를 담고 있던 월 폴더의 (year, month)
                    fileMarkers[uri] = findAllMarkers(got.doc, src.year, src.month);
                    try { tagStoryLabels(got.doc); } catch (eTag) {}
                    var mkList = fileMarkers[uri];
                    var qOnly = (mkList.length > 0 && mkList[0].qnumOnly);
                    writeLog("열기: " + cf.displayName +
                             " (markers=" + mkList.length +
                             (qOnly ? ", 번호전용 헤더 → " + src.year + "년 " +
                                      parseInt(src.month, 10) + "월로 보정" : "") + ")");
                } catch (eOp) {
                    writeLog("[경고] 열기 실패: " + cf.fsName + " — " + eOp.message);
                }
            }
        }

        // 베이스 페이지 정리 — KEEP_HEAD 만 남기고 나머지 모두 삭제
        if (newDoc.pages.length > KEEP_HEAD) {
            for (var p = newDoc.pages.length - 1; p >= KEEP_HEAD; p--) {
                try { newDoc.pages[p].remove(); } catch (er) {}
            }
        }
        writeLog("베이스 정리 → " + newDoc.pages.length + " 페이지 보존");

        var totalPages = newDoc.pages.length;
        var codeRanges = [];
        var unresolved = [];
        var extractedRanges = {};  // "uri|markerIdx" → true (중복 추출 방지)

        // 코드 순서대로 매칭 후보 중 첫 매칭 파일에서 페이지 추출
        for (var ci2 = 0; ci2 < SOURCES.length; ci2++) {
            var srcMeta = SOURCES[ci2];
            var year = srcMeta.year;
            var month = srcMeta.month;
            var qNum = srcMeta.qNum;
            var code = srcMeta.code;

            var matchedDoc = null;
            var matchedRange = null;
            var matchedFileName = "";
            var matchedUri = "";

            var candList = srcMeta.candidates || [];
            for (var ki = 0; ki < candList.length; ki++) {
                var localPath = candList[ki];
                var cFile = new File(localPath);
                if (!cFile.exists) continue;
                var uri = cFile.absoluteURI;
                var md = docCache[uri];
                var mks = fileMarkers[uri];
                if (!md || !mks) continue;
                var rg = getCodeRange(mks, year, month, qNum, md);
                if (rg) {
                    matchedDoc = md;
                    matchedRange = rg;
                    matchedFileName = cFile.displayName;
                    matchedUri = uri;
                    break;
                }
            }

            if (!matchedDoc || !matchedRange) {
                unresolved.push(code);
                writeLog("[경고] 마커 매칭 실패: " + code +
                         " (" + year + "년 " + parseInt(month,10) + "월 " + qNum + "번)");
                continue;
            }

            // 같은 (uri, markerIdx) 가 이미 추출됐으면 skip (범위형 41-42, 43-45 대응)
            var dedupKey = matchedUri + "|" + matchedRange.markerIdx;
            if (extractedRanges[dedupKey]) {
                writeLog("  " + code + " → 이미 같은 범위 추출됨 (" + matchedFileName +
                         " p" + (matchedRange.startIdx + 1) +
                         "..p" + (matchedRange.endIdx + 1) + ") — skip");
                continue;
            }
            extractedRanges[dedupKey] = true;

            var grpStart = newDoc.pages.length;
            for (var p2 = matchedRange.startIdx; p2 <= matchedRange.endIdx; p2++) {
                try {
                    matchedDoc.pages[p2].duplicate(
                        LocationOptions.AT_END, newDoc.pages.lastItem()
                    );
                    totalPages++;
                } catch (eDup) {
                    writeLog("[경고] " + code + " p" + p2 +
                             " 복제 실패: " + eDup.message);
                }
            }
            var grpEnd = newDoc.pages.length - 1;
            if (grpEnd >= grpStart) {
                codeRanges.push({ code: code, startIdx: grpStart, endIdx: grpEnd });
                writeLog("  " + code + " ← " + matchedFileName +
                         " p" + (matchedRange.startIdx + 1) +
                         "..p" + (matchedRange.endIdx + 1) +
                         " (" + (matchedRange.endIdx - matchedRange.startIdx + 1) + "p)");
            }
        }

        // rethread (threaded story 가 있을 때만 의미 있음)
        for (var rgi = 0; rgi < codeRanges.length; rgi++) {
            try {
                rethreadGroup(newDoc, codeRanges[rgi].startIdx, codeRanges[rgi].endIdx);
            } catch (eRt) {
                writeLog("[경고] rethread " + codeRanges[rgi].code + ": " + eRt.message);
            }
        }

        try { cleanLabels(newDoc); } catch (eCl) {}

        // 내지 전부 스프레드 재편성 허용 — 복제된 분석본 spread 까지 모두 풀기
        try {
            allowShuffleAll(newDoc);
            writeLog("스프레드 재편성 허용 설정: " + newDoc.spreads.length + " spread");
        } catch (eShf) { writeLog("[경고] 재편성 허용 설정 실패: " + eShf.message); }

        // 저장
        try { newDoc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
        writeLog("저장: " + newDoc.fullName.fsName);
        writeLog("총 페이지: " + newDoc.pages.length);
        if (unresolved.length > 0) {
            writeLog("[경고] 매칭 실패 코드 " + unresolved.length + "개: " + unresolved.join(", "));
        }

        // PDF export
        // 사용자가 UI에서 마지막으로 쓴 export 설정(페이지 범위 / 페이지별
        // 개별 PDF)이 스크립트 export에 상속된다 — 세로결합에서 '페이지별
        // 분할'이 켜진 채 결과가 폴더+_NN.pdf 로 쪼개진 사례(2026-05-28)와
        // 동일 계열 결함 재발 방지. 위험 설정만 정규화하고 프리셋/품질은
        // 기존과 동일하게 현재 설정을 따른다.
        try {
            var pdfFile = new File(OUTPUT_PDF);
            try { app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES; } catch (ePr) {}
            try { app.pdfExportPreferences.exportAsSinglePages = false; } catch (eSp) {}
            try { app.pdfExportPreferences.viewPDF = false; } catch (eVp) {}
            newDoc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false);
            // 파일 시스템 반영 지연 대비 — 최대 10초 대기 후 판정
            for (var wPdf = 0; wPdf < 20 && !pdfFile.exists; wPdf++) { $.sleep(500); }
            if (pdfFile.exists) {
                writeLog("PDF: " + pdfFile.fsName);
            } else {
                writeLog("[경고] PDF 파일이 생성되지 않음");
            }
        } catch (eExp) {
            writeLog("[오류] PDF export: " + eExp.message);
        }

        // 결과 문서 보이기
        try { newDoc.windows.add(); } catch (eWin) {}

        // 소스 문서 닫기
        for (var uriClose in openedByUs) {
            try { docCache[uriClose].close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        writeLog("[치명적 오류] " + (eMain.message || eMain));
    }

})();
