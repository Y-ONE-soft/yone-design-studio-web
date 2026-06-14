// [ENGINE TEMPLATE] 모의고사 세로 결합 JSX
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작 요약:
//   1) 템플릿(.indd) -> 출력 위치로 복사 -> 결합 베이스로 열기
//   2) 베이스 앞 KEEP_HEAD 페이지(간지)와 마지막 1페이지(꼬리)만 보존, 사이 페이지 삭제
//   3) settings.sources 의 각 .indd 를 열고 markers 범위 페이지를 AT_END 로 duplicate
//      (그룹 마커 = 페이지 마스터가 'A*' 로 시작하고 그 페이지에 6자리 코드 또는
//       [QQ]/[QQ~QQ] 표기가 있는 페이지)
//   4) 코드 그룹 내 텍스트프레임 storyId 라벨을 이용해 nextTextFrame 재연결
//   5) LastP.ai 링크가 있는 페이지 -> 끝으로 / 템플릿 마지막 페이지를 다시 끝으로
//   6) 저장 + PDF export
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

    var settings   = readJSON(SETTINGS_PATH);
    var LOG_PATH   = settings.log_path;
    var LOG_PATHS  = settings.log_paths || [];   // 추가 로그 경로 (job_dir 등)

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
    // 결합 로직 (MergeMockExamSero.jsx 와 동일 — 다이얼로그/사용자 입력만 제거)
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
    var SID_PFX = '__sero_sid:';
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

    function moveLastPagesToEnd(doc) {
        var hits = [];
        for (var p = 0; p < doc.pages.length; p++) {
            var items;
            try { items = doc.pages[p].allPageItems; } catch (eAp) { continue; }
            var isLast = false;
            for (var i = 0; i < items.length; i++) {
                try {
                    var link = items[i].itemLink;
                    if (link && link.isValid) {
                        var nm = link.name || '';
                        if (nm.indexOf('LastP') !== -1) { isLast = true; break; }
                    }
                } catch (eL) {}
            }
            if (isLast) hits.push(p);
        }
        hits.sort(function (a, b) { return b - a; });
        for (var h = 0; h < hits.length; h++) {
            var idx = hits[h];
            if (idx >= doc.pages.length - 1) continue;
            try { doc.pages[idx].move(LocationOptions.AT_END); } catch (eMv) {}
        }
        return hits.length;
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

    function findAllMarkers(doc) {
        var markers = [];
        var code6Pat = /\b(\d{6})\b/;
        var qNumPat  = /\[\s*(\d{1,2})(?:\s*[~\-]\s*(\d{1,2}))?\s*\]/;

        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];
            try {
                var masterName = page.appliedMaster.name;
                if (!masterName || masterName.charAt(0).toUpperCase() !== 'A') continue;
            } catch (e) { continue; }

            var foundCode = null;
            var foundQ    = null;
            var foundQEnd = null;
            try {
                var items = page.allPageItems;
                for (var f = 0; f < items.length; f++) {
                    try {
                        var txt = items[f].contents;
                        if (typeof txt !== 'string') continue;
                        if (!foundCode) {
                            var m6 = code6Pat.exec(txt);
                            if (m6) foundCode = m6[1];
                        }
                        if (!foundQ) {
                            var mq = qNumPat.exec(txt);
                            if (mq) { foundQ = mq[1]; foundQEnd = mq[2] || null; }
                        }
                        if (foundCode && foundQ) break;
                    } catch (ef) {}
                }
            } catch (ep) {}

            if (foundCode || foundQ) {
                var lastM = markers.length > 0 ? markers[markers.length - 1] : null;
                var sameAsLast = false;
                if (lastM) {
                    if (foundCode && foundCode === lastM.code) sameAsLast = true;
                    else if (!foundCode && foundQ &&
                             foundQ === lastM.qNum &&
                             (foundQEnd || '') === (lastM.qNumEnd || '')) sameAsLast = true;
                }
                if (!sameAsLast) {
                    markers.push({
                        code: foundCode, qNum: foundQ, qNumEnd: foundQEnd, pageIndex: i
                    });
                }
            }
        }
        markers.sort(function (a, b) { return a.pageIndex - b.pageIndex; });
        return markers;
    }

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

    function getCodeRange(markers, code, doc) {
        var idx = findMarkerIndex(markers, code);
        if (idx === -1) return null;
        var startIdx = markers[idx].pageIndex;
        var endIdx   = (idx < markers.length - 1)
                         ? markers[idx + 1].pageIndex - 1
                         : doc.pages.length - 1;
        return { startIdx: startIdx, endIdx: endIdx };
    }

    // ───────────────────────────────────────────────────────────────
    // 메인 — settings.json 기반 결합 + PDF export
    // ───────────────────────────────────────────────────────────────

    try {
        writeLog("===== 모의고사 세로 결합 시작 =====");
        writeLog("소스: " + (settings.sources || []).length + "개");

        var TEMPLATE_PATH = settings.template_path;
        var OUTPUT_INDD   = settings.output_indd;
        var OUTPUT_PDF    = settings.output_pdf;
        var KEEP_HEAD     = (settings.keep_head != null) ? settings.keep_head : 3;
        var SOURCES       = settings.sources || [];

        var tplFile = new File(TEMPLATE_PATH);
        if (!tplFile.exists) { fail("템플릿 없음: " + TEMPLATE_PATH); return; }

        var outFile = new File(OUTPUT_INDD);
        if (!tplFile.copy(outFile)) { fail("템플릿 복사 실패: " + OUTPUT_INDD); return; }
        writeLog("템플릿 복사 -> " + outFile.fsName);

        var newDoc;
        try { newDoc = app.open(outFile, false); }
        catch (eOpen) { fail("사본 열기 실패: " + eOpen.message); return; }

        // 소스 파일 열기 + 마커 수집
        var docCache   = {};
        var openedByUs = {};
        var fileMarkers = {};
        var sourceFiles = [];          // 코드 순서대로 처리하기 위한 배열

        for (var si = 0; si < SOURCES.length; si++) {
            var src = SOURCES[si];
            var srcFile = new File(src.local_path);
            if (!srcFile.exists) {
                writeLog("[경고] 소스 누락: " + src.local_path);
                sourceFiles.push(null);
                continue;
            }
            var uri = srcFile.absoluteURI;
            if (!docCache[uri]) {
                var got;
                try { got = getDoc(srcFile, docCache); }
                catch (eOp) {
                    writeLog("[경고] 소스 열기 실패: " + srcFile.fsName + " — " + eOp.message);
                    sourceFiles.push(null);
                    continue;
                }
                if (got.opened) openedByUs[uri] = true;
                fileMarkers[uri] = findAllMarkers(got.doc);
                try { tagStoryLabels(got.doc); } catch (eTag) {}
            }
            sourceFiles.push(srcFile);
        }

        var totalPages = 0;
        var codeRanges = [];

        // 베이스 페이지 정리 + tail 보존
        var tailPageRef = null;
        if (newDoc.pages.length > KEEP_HEAD) {
            tailPageRef = newDoc.pages[newDoc.pages.length - 1];
            for (var p = newDoc.pages.length - 2; p >= KEEP_HEAD; p--) {
                try { newDoc.pages[p].remove(); } catch (er) {}
            }
        }
        totalPages = newDoc.pages.length;

        // 코드 순서대로 markers 범위를 AT_END 로 추가
        // 같은 지문(마커)을 여러 번호가 가리키면(장문 41~42 등) 1회만 삽입
        var seenMarkers = {};
        for (var ci = 0; ci < SOURCES.length; ci++) {
            var srcMeta = SOURCES[ci];
            var sf = sourceFiles[ci];
            if (!sf) continue;
            var u = sf.absoluteURI;
            var sd = docCache[u];
            var label = (srcMeta.display || srcMeta.code);

            var mIdx = findMarkerIndex(fileMarkers[u], srcMeta.code);
            if (mIdx === -1) {
                var miss = label + " (" + (sf.displayName || sf.name) + ")";
                // 범위 전개분(from_range)은 정보, 직접 입력한 번호는 경고
                if (srcMeta.from_range) {
                    writeLog("[정보] 해당 지문 없음 — 건너뜀: " + miss);
                } else {
                    writeLog("[경고] 마커 범위 없음: " + miss);
                }
                continue;
            }

            var mKey = u + "#" + mIdx;
            if (seenMarkers[mKey]) {
                writeLog("[정보] 중복 지문 — 건너뜀: " + label);
                continue;
            }
            seenMarkers[mKey] = true;

            var rg = getCodeRange(fileMarkers[u], srcMeta.code, sd);
            if (!rg) {
                writeLog("[경고] 마커 범위 계산 실패: " + label);
                continue;
            }
            var grpStart = newDoc.pages.length;
            for (var p2 = rg.startIdx; p2 <= rg.endIdx; p2++) {
                try {
                    sd.pages[p2].duplicate(LocationOptions.AT_END, newDoc.pages.lastItem());
                    totalPages++;
                } catch (eDup) {
                    writeLog("[경고] " + label + " p" + p2 +
                             " 복제 실패: " + eDup.message);
                }
            }
            var grpEnd = newDoc.pages.length - 1;
            if (grpEnd >= grpStart) {
                codeRanges.push({ code: srcMeta.code, startIdx: grpStart, endIdx: grpEnd });
            }
        }

        // tail 다시 끝으로
        if (tailPageRef) {
            try { tailPageRef.move(LocationOptions.AT_END); } catch (eMv) {}
        }

        // rethread
        for (var rgi = 0; rgi < codeRanges.length; rgi++) {
            try {
                rethreadGroup(newDoc, codeRanges[rgi].startIdx, codeRanges[rgi].endIdx);
            } catch (eRt) {
                writeLog("[경고] rethread " + codeRanges[rgi].code + ": " + eRt.message);
            }
        }

        // LastP move + tail 재이동
        try { moveLastPagesToEnd(newDoc); } catch (eLp) {}
        if (tailPageRef) {
            try { tailPageRef.move(LocationOptions.AT_END); } catch (eMv2) {}
        }

        try { cleanLabels(newDoc); } catch (eCl) {}

        // 저장
        try { newDoc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
        writeLog("저장: " + newDoc.fullName.fsName);
        writeLog("총 페이지: " + newDoc.pages.length);

        // PDF export
        try {
            var pdfFile = new File(OUTPUT_PDF);
            newDoc.exportFile(ExportFormat.PDF_TYPE, pdfFile);
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

        // 소스 문서 닫기 (열었던 것만)
        for (var uri in openedByUs) {
            try { docCache[uri].close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        writeLog("[치명적 오류] " + (eMain.message || eMain));
    }

})();
