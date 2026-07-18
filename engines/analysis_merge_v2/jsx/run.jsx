// [ENGINE TEMPLATE] 분석본 결합 v2 JSX
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// v1(engines/analysis_merge/jsx/run.jsx) 대비 변경 — 2026 여름 개편:
//   [스펙3·1] PDF export 제거 (목업 핸드오프 원천 차단) — .indd만 저장
//   검수 리포트(report_path JSON) 기록 — verify 게이트의 입력
// ES3 제약: let/const/화살표/템플릿 리터럴 금지, JSON.parse는 eval.
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

    // settings 로드 실패도 job_dir 로그에 흔적을 남긴다 (침묵 실패 금지).
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

    // ── JSON 직렬화 (report_path 기록용) ───────────────────────────
    function jesc(s) {
        s = String(s);
        var out = "";
        for (var i = 0; i < s.length; i++) {
            var c = s.charAt(i), n = s.charCodeAt(i);
            if (c == "\\") { out += "\\\\"; }
            else if (c == "\"") { out += "\\\""; }
            else if (n == 10) { out += "\\n"; }
            else if (n == 13) { out += "\\r"; }
            else if (n == 9) { out += "\\t"; }
            else if (n < 32) { out += " "; }
            else if (n < 127) { out += c; }
            else {
                var h = n.toString(16);
                while (h.length < 4) { h = "0" + h; }
                out += "\\u" + h;
            }
        }
        return out;
    }
    function jstr(v) {
        if (v === null || v === undefined) return "null";
        if (typeof v == "number") return isFinite(v) ? String(v) : "null";
        if (typeof v == "boolean") return v ? "true" : "false";
        if (typeof v == "string") return "\"" + jesc(v) + "\"";
        if (v instanceof Array) {
            var parts = [];
            for (var i = 0; i < v.length; i++) parts.push(jstr(v[i]));
            return "[" + parts.join(",") + "]";
        }
        var kv = [];
        for (var k in v) {
            if (!v.hasOwnProperty(k)) continue;
            kv.push("\"" + jesc(k) + "\":" + jstr(v[k]));
        }
        return "{" + kv.join(",") + "}";
    }
    function writeReport(rep) {
        try {
            var rf = new File(settings.report_path);
            rf.encoding = "UTF-8";
            if (rf.open("w")) { rf.write(jstr(rep)); rf.close(); }
        } catch (eR) { writeLog("[경고] 리포트 기록 실패: " + eR.message); }
    }

    function round3(n) { return Math.round(n * 1000) / 1000; }

    // ───────────────────────────────────────────────────────────────
    // 문서 open / cache (v1 동일)
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
    // Story threading 보존 (v1 동일)
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
        for (var sid2 in byStory) {
            var arr = byStory[sid2];
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
    // 스프레드 재편성 허용 (v1 동일)
    // ───────────────────────────────────────────────────────────────

    function allowShuffleAll(doc) {
        try { doc.documentPreferences.allowPageShuffle = true; } catch (eDPS) {}
        for (var s = 0; s < doc.spreads.length; s++) {
            try { doc.spreads[s].allowPageShuffle = true; } catch (eSh) {}
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 분석본 마커 탐색 (v1 동일)
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

    var report = {
        unresolved: [],
        geometry: { max_drift_before_mm: 0, max_residual_mm: 0,
                    count_mismatch_pages: [], pages: [] },
        links: {},
        ganji: { ok: false },
        overflow_pages: []
    };

    try {
        writeLog("===== 분석본 결합 v2 시작 =====");
        var SOURCES = settings.sources || [];
        writeLog("코드: " + SOURCES.length + "개");

        var TEMPLATE_PATH = settings.template_path;
        var OUTPUT_INDD   = settings.output_indd;
        var KEEP_HEAD     = (settings.keep_head != null) ? settings.keep_head : 1;

        var tplFile = new File(TEMPLATE_PATH);
        if (!tplFile.exists) { fail("템플릿 없음: " + TEMPLATE_PATH); writeReport(report); return; }

        var outFile = new File(OUTPUT_INDD);
        if (!tplFile.copy(outFile)) { fail("템플릿 복사 실패: " + OUTPUT_INDD); writeReport(report); return; }
        writeLog("템플릿 복사 -> " + outFile.fsName);

        var newDoc;
        try { newDoc = app.open(outFile, false); }
        catch (eOpen) { fail("사본 열기 실패: " + eOpen.message); writeReport(report); return; }

        allowShuffleAll(newDoc);

        // 후보 파일 dedup + open + markers 수집
        var docCache    = {};
        var openedByUs  = {};
        var fileMarkers = {};
        var allCandidates = {};

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
                    fileMarkers[uri] = findAllMarkers(got.doc);
                    try { tagStoryLabels(got.doc); } catch (eTag) {}
                    writeLog("열기: " + cf.displayName +
                             " (markers=" + fileMarkers[uri].length + ")");
                } catch (eOp) {
                    writeLog("[경고] 열기 실패: " + cf.fsName + " — " + eOp.message);
                }
            }
        }

        // 베이스 페이지 정리 — KEEP_HEAD 만 남기고 삭제
        if (newDoc.pages.length > KEEP_HEAD) {
            for (var p = newDoc.pages.length - 1; p >= KEEP_HEAD; p--) {
                try { newDoc.pages[p].remove(); } catch (er) {}
            }
        }
        writeLog("베이스 정리 → " + newDoc.pages.length + " 페이지 보존");

        var codeRanges = [];
        var extractedRanges = {};

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
                var uri2 = cFile.absoluteURI;
                var md = docCache[uri2];
                var mks = fileMarkers[uri2];
                if (!md || !mks) continue;
                var rg = getCodeRange(mks, year, month, qNum, md);
                if (rg) {
                    matchedDoc = md;
                    matchedRange = rg;
                    matchedFileName = cFile.displayName;
                    matchedUri = uri2;
                    break;
                }
            }

            if (!matchedDoc || !matchedRange) {
                report.unresolved.push(code);
                writeLog("[경고] 마커 매칭 실패: " + code +
                         " (" + year + "년 " + parseInt(month, 10) + "월 " + qNum + "번)");
                continue;
            }

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

        // rethread
        for (var rgi = 0; rgi < codeRanges.length; rgi++) {
            try {
                rethreadGroup(newDoc, codeRanges[rgi].startIdx, codeRanges[rgi].endIdx);
            } catch (eRt) {
                writeLog("[경고] rethread " + codeRanges[rgi].code + ": " + eRt.message);
            }
        }
        try { cleanLabels(newDoc); } catch (eCl) {}

        // 스프레드 재편성 허용 (v1 동일)
        try {
            allowShuffleAll(newDoc);
            writeLog("스프레드 재편성 허용 설정: " + newDoc.spreads.length + " spread");
        } catch (eShf) { writeLog("[경고] 재편성 허용 설정 실패: " + eShf.message); }

        // 저장 (.indd만 — PDF export 없음 [스펙3·1])
        try { newDoc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
        writeLog("저장: " + newDoc.fullName.fsName);
        writeLog("총 페이지: " + newDoc.pages.length);
        if (report.unresolved.length > 0) {
            writeLog("[경고] 매칭 실패 코드 " + report.unresolved.length + "개: " +
                     report.unresolved.join(", "));
        }

        writeReport(report);

        // 결과 문서 보이기
        try { newDoc.windows.add(); } catch (eWin) {}

        // 소스 문서 닫기
        for (var uriClose in openedByUs) {
            try { docCache[uriClose].close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        writeLog("[치명적 오류] " + (eMain.message || eMain));
        try { writeReport(report); } catch (eWr) {}
    }

})();
