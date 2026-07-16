// [ENGINE TEMPLATE] 마더텅 결합 JSX
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작 요약:
//   1) 분석본 마스터 템플릿(.indd) -> 출력 위치로 복사 -> 결합 베이스로 열기
//   2) 베이스 앞 KEEP_HEAD 페이지만 보존, 나머지 페이지 모두 삭제
//   3) settings.passages 의 각 항목(엑셀 순서) 처리:
//      a) primary_candidates (모의고사 작업/ 분석본) → 마커 텍스트 매칭
//         "(고N) {YY}년 {M}월 {QQ}번" 패턴
//      b) fallback (마더텅 강 파일) → 고정 페이지 위치 (엑셀 순서 기반)
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
    // readJSON 예외가 로그 0바이트 침묵 실패로 빠져 원인 진단이 불가했다
    // (2026-05-15 73605d61: 마더텅 결합 유일 실행이 무로그로 소멸).
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

    // Story threading 보존
    var SID_PFX = '__mt_sid:';
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
    // 분석본 마커 탐색 (analysis_merge 와 동일)
    // ───────────────────────────────────────────────────────────────

    var MARKER_PAT = /(?:고\d+\s*)?(\d{1,2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*(?:[\-~]\s*(\d{1,2}))?\s*번/;

    function findAllMarkers(doc) {
        var markers = [];
        var seenKey = {};

        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];
            try {
                var masterName = page.appliedMaster.name;
                if (masterName) {
                    if (masterName.indexOf("간지") !== -1) continue;
                    if (masterName.indexOf("표지") !== -1) continue;
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
        return markers;
    }

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
        writeLog("===== 마더텅 결합 시작 =====");
        var PASSAGES = settings.passages || [];
        writeLog("지문: " + PASSAGES.length + "개");

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

        // 후보 파일 dedup + open + markers 수집
        var docCache    = {};
        var openedByUs  = {};
        var fileMarkers = {};   // uri → markers[] (primary 만)

        function openCandidate(localPath) {
            var cf = new File(localPath);
            if (!cf.exists) {
                writeLog("[경고] 후보 누락: " + localPath);
                return null;
            }
            var uri = cf.absoluteURI;
            if (docCache[uri]) return cf;
            try {
                var got = getDoc(cf, docCache);
                if (got.opened) openedByUs[uri] = true;
                try { tagStoryLabels(got.doc); } catch (eTag) {}
                return cf;
            } catch (eOp) {
                writeLog("[경고] 열기 실패: " + cf.fsName + " — " + eOp.message);
                return null;
            }
        }

        // 1) primary 후보 모두 열기 + 마커 추출
        var primaryUris = {};
        for (var si = 0; si < PASSAGES.length; si++) {
            var pas = PASSAGES[si];
            var prim = pas.primary_candidates || [];
            for (var pi = 0; pi < prim.length; pi++) {
                var cf = openCandidate(prim[pi]);
                if (!cf) continue;
                var uri = cf.absoluteURI;
                if (primaryUris[uri]) continue;
                primaryUris[uri] = true;
                fileMarkers[uri] = findAllMarkers(docCache[uri]);
                writeLog("열기(primary): " + cf.displayName +
                         " (markers=" + fileMarkers[uri].length + ")");
            }
        }

        // 2) fallback 후보 모두 열기 (마커 추출 안 함 — 고정 페이지 사용)
        var fallbackUris = {};
        for (var si2 = 0; si2 < PASSAGES.length; si2++) {
            var pas2 = PASSAGES[si2];
            if (!pas2.fallback) continue;
            var cf2 = openCandidate(pas2.fallback.local_path);
            if (!cf2) continue;
            var uri2 = cf2.absoluteURI;
            if (fallbackUris[uri2]) continue;
            fallbackUris[uri2] = true;
            writeLog("열기(fallback): " + cf2.displayName);
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
        var extractedKeys = {};  // dedup

        for (var ci = 0; ci < PASSAGES.length; ci++) {
            var P = PASSAGES[ci];
            var code = P.code;
            var year = P.year, month = P.month, qNum = P.qNum;
            var lessonNum = P.lesson_num;

            var matchedDoc = null;
            var matchedRange = null;
            var matchedName = "";
            var matchedSrc = "";  // "primary" | "fallback"
            var dedupKey = null;

            // 1) primary 시도 — 마커 매칭
            var prim = P.primary_candidates || [];
            for (var ki = 0; ki < prim.length; ki++) {
                var cFile = new File(prim[ki]);
                if (!cFile.exists) continue;
                var uri = cFile.absoluteURI;
                var md = docCache[uri];
                var mks = fileMarkers[uri];
                if (!md || !mks) continue;
                var rg = getCodeRange(mks, year, month, qNum, md);
                if (rg) {
                    matchedDoc = md;
                    matchedRange = rg;
                    matchedName = cFile.displayName;
                    matchedSrc = "primary";
                    dedupKey = "P|" + uri + "|" + rg.markerIdx;
                    break;
                }
            }

            // 2) fallback 시도 — 고정 페이지
            if (!matchedDoc && P.fallback) {
                var fbFile = new File(P.fallback.local_path);
                if (fbFile.exists) {
                    var fbUri = fbFile.absoluteURI;
                    var fbDoc = docCache[fbUri];
                    if (fbDoc) {
                        var startIdx = P.fallback.start_idx;
                        var pageCnt = P.fallback.page_count;
                        var endIdx = Math.min(startIdx + pageCnt - 1, fbDoc.pages.length - 1);
                        if (startIdx >= 0 && startIdx < fbDoc.pages.length) {
                            matchedDoc = fbDoc;
                            matchedRange = { startIdx: startIdx, endIdx: endIdx, markerIdx: -1 };
                            matchedName = fbFile.displayName;
                            matchedSrc = "fallback";
                            dedupKey = "F|" + fbUri + "|" + startIdx;
                        }
                    }
                }
            }

            if (!matchedDoc || !matchedRange) {
                unresolved.push(code + "(L" + lessonNum + ")");
                writeLog("[경고] 해결 불가: " + code + " (강 " + lessonNum + ")");
                continue;
            }

            if (extractedKeys[dedupKey]) {
                writeLog("  " + code + " (강 " + lessonNum + ") → 이미 추출됨 — skip");
                continue;
            }
            extractedKeys[dedupKey] = true;

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
                writeLog("  " + code + " [강" + lessonNum + " " + matchedSrc + "] ← " +
                         matchedName + " p" + (matchedRange.startIdx + 1) +
                         "..p" + (matchedRange.endIdx + 1) +
                         " (" + (matchedRange.endIdx - matchedRange.startIdx + 1) + "p)");
            }
        }

        for (var rgi = 0; rgi < codeRanges.length; rgi++) {
            try {
                rethreadGroup(newDoc, codeRanges[rgi].startIdx, codeRanges[rgi].endIdx);
            } catch (eRt) {
                writeLog("[경고] rethread " + codeRanges[rgi].code + ": " + eRt.message);
            }
        }

        try { cleanLabels(newDoc); } catch (eCl) {}

        try { newDoc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
        writeLog("저장: " + newDoc.fullName.fsName);
        writeLog("총 페이지: " + newDoc.pages.length);
        if (unresolved.length > 0) {
            writeLog("[경고] 해결 안 된 코드 " + unresolved.length + "개: " + unresolved.join(", "));
        }

        // PDF export — 사용자 UI 잔존 설정(페이지별 분할/페이지 범위) 상속 방지
        // (세로결합 2026-05-28 폴더 분할 사례와 동일 계열). 프리셋/품질은
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

        try { newDoc.windows.add(); } catch (eWin) {}

        for (var uriClose in openedByUs) {
            try { docCache[uriClose].close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        writeLog("[치명적 오류] " + (eMain.message || eMain));
    }

})();
