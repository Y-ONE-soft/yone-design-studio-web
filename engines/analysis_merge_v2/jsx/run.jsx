// [ENGINE TEMPLATE] 분석본 결합 v2 JSX
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// v1(engines/analysis_merge/jsx/run.jsx) 대비 변경 — 2026 여름 개편:
//   [스펙2] page.duplicate 후 프레임 지오메트리를 소스 좌표로 복원
//           (실측: 문서 간 복제 시 LEFT +2mm / RIGHT +4mm 수평 이동)
//           + 복원 전/후 드리프트를 report_path JSON에 기록 (verify 게이트)
//   [스펙4] 저장 전 링크 전수 점검 — 깨진 링크 relink_map으로 리링크 후
//           전부 임베드(Link.unlink() == InDesign 임베드), 결과 기록
//   [스펙5] 1페이지(간지) 텍스트 — 간지 마스터 학교명(챕터_숫자)/순번 갱신,
//           상단 슬러그 범위/범위_추가내용 기재, 범위 프레임쌍
//           오버라이드 병기 (범위 여러 개면 아래로 +21.5mm 간격 복제)
//   [스펙3·1] PDF export 제거 (목업 핸드오프 원천 차단) — .indd만 저장
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
    // [스펙2] 프레임 지오메트리 캡처/복원
    //   실측(repro1): 문서 간 page.duplicate가 콘텐츠 아이템을 페이지 기준
    //   LEFT +2mm / RIGHT +4mm 순수 평행이동시킨다 (슬러그 탭은 무이동).
    //   → 복제 직후 소스 좌표와의 (dx,dy)를 item.move로 되돌린다.
    //   move는 회전/크기를 건드리지 않는 순수 이동이라 안전.
    // ───────────────────────────────────────────────────────────────

    function collectGeo(page) {
        var arr = [];
        try {
            var items = page.pageItems;
            for (var i = 0; i < items.length; i++) {
                var gb;
                try { gb = items[i].geometricBounds; } catch (eG) { gb = null; }
                arr.push(gb);
            }
        } catch (eP) {}
        return arr;
    }

    function restoreGeo(newPage, srcGeo, geoRep, srcLabel) {
        var items;
        try { items = newPage.pageItems; } catch (eI) { return; }
        var n = Math.min(items.length, srcGeo.length);
        var maxBefore = 0, maxAfter = 0;
        if (items.length !== srcGeo.length) {
            geoRep.count_mismatch_pages.push(
                "p" + newPage.name + "(" + srcLabel + "): " +
                srcGeo.length + "->" + items.length);
        }
        for (var i = 0; i < n; i++) {
            var want = srcGeo[i];
            if (!want) continue;
            var cur;
            try { cur = items[i].geometricBounds; } catch (eC) { continue; }
            var dx = want[1] - cur[1];
            var dy = want[0] - cur[0];
            var drift = Math.max(Math.abs(dx), Math.abs(dy));
            if (drift > maxBefore) maxBefore = drift;
            if (drift > 0.01) {
                try {
                    try { items[i].locked = false; } catch (eLk) {}
                    items[i].move(undefined, [dx, dy]);
                } catch (eMv) {
                    writeLog("[경고] 지오메트리 복원 실패 p" + newPage.name +
                             " item" + i + ": " + eMv.message);
                }
            }
            var after;
            try { after = items[i].geometricBounds; } catch (eA) { continue; }
            var rx = Math.abs(want[1] - after[1]);
            var ry = Math.abs(want[0] - after[0]);
            var resid = Math.max(rx, ry);
            if (resid > maxAfter) maxAfter = resid;
        }
        geoRep.pages.push({
            page: String(newPage.name), src: srcLabel,
            items: n,
            drift_before_mm: round3(maxBefore),
            residual_mm: round3(maxAfter)
        });
        if (maxBefore > geoRep.max_drift_before_mm) {
            geoRep.max_drift_before_mm = round3(maxBefore);
        }
        if (maxAfter > geoRep.max_residual_mm) {
            geoRep.max_residual_mm = round3(maxAfter);
        }
    }

    // ───────────────────────────────────────────────────────────────
    // [스펙5] 간지/1페이지 텍스트
    //   실측 스펙 (GDrive 기존 결합본 덤프 — 강동2_분석본03/명일1_분석본04):
    //     · 간지-마스터 학교명 프레임: 문자스타일 '챕터_숫자',
    //       내용 "2026 강동고2" 형태  → settings.ganji_school
    //     · 간지-마스터 순번 프레임: 작은 프레임, 내용 숫자("3") → issue_num
    //     · 페이지1 상단 슬러그 프레임 2개(y<0): cs '범위'=교재명/회차,
    //       cs '범위_추가내용'=상세 범위
    //     · 범위 프레임쌍(가로 스트립): 간지-마스터의 '범위'(y1 238)/
    //       '범위_추가내용'(y1 259) 프레임을 페이지로 오버라이드해
    //       y1 232 / 242.5로 이동, 범위가 여러 개면 쌍을 아래로
    //       +21.5mm 간격 복제해 위아래로 병기
    // ───────────────────────────────────────────────────────────────

    var GANJI_RANGE_Y = 232;      // 오버라이드 후 범위 프레임 y1 (실측)
    var GANJI_DETAIL_Y = 242.5;   // 오버라이드 후 추가내용 프레임 y1 (실측)
    var GANJI_PAIR_STEP = 21.5;   // 추가 범위쌍 y 간격 (실측 21~23.5 중간값)

    function frameCS(tf) {
        try { return tf.texts[0].textStyleRanges[0].appliedCharacterStyle.name; }
        catch (e) { return ""; }
    }

    function findCharStyle(doc, name) {
        // itemByName은 스타일 그룹 내부를 못 찾음 — allCharacterStyles에서 탐색
        try {
            var all = doc.allCharacterStyles;
            for (var i = 0; i < all.length; i++) {
                if (all[i].name === name) return all[i];
            }
        } catch (e) {}
        return null;
    }

    function setFrameText(doc, tf, text, csName) {
        tf.contents = String(text);
        // 문자스타일 재적용 (자동 생성 금지 — 없으면 경고만)
        if (csName) {
            var cs = findCharStyle(doc, csName);
            if (cs) {
                try { tf.texts[0].appliedCharacterStyle = cs; } catch (eA) {}
            } else {
                writeLog("[경고] 문자스타일 없음: " + csName);
            }
        }
    }

    function moveToY(item, y1) {
        var gb = item.geometricBounds;
        item.move(undefined, [0, y1 - gb[0]]);
    }

    function overrideOrReuse(masterItem, page) {
        // 이미 페이지에 재정의돼 있으면 그 항목을 재사용 (override 중복 오류 방지)
        try {
            var pis = page.pageItems;
            for (var i = 0; i < pis.length; i++) {
                try {
                    var om = pis[i].overriddenMasterPageItem;
                    if (om && om.id === masterItem.id) return pis[i];
                } catch (eOm) {}
            }
        } catch (eP) {}
        return masterItem.override(page);
    }

    function applyGanji(doc, ganjiRep) {
        var page0 = doc.pages[0];
        var master = null;
        try { master = page0.appliedMaster; } catch (eM) {}
        if (!master || String(master.name).indexOf("간지") === -1) {
            try { master = doc.masterSpreads.itemByName("간지-마스터"); } catch (eM2) {}
        }
        if (!master || !master.isValid) {
            throw new Error("간지 마스터를 찾지 못함");
        }

        // 마스터 프레임 분류
        var mSchool = null, mIssue = null, mRange = null, mDetail = null;
        var mtf = master.textFrames;
        for (var i = 0; i < mtf.length; i++) {
            var tf = mtf[i];
            var cs = frameCS(tf);
            var txt = "";
            try { txt = String(tf.contents); } catch (eT) {}
            if (cs === "챕터_숫자") { mSchool = tf; }
            else if (cs === "범위") { mRange = tf; }
            else if (cs === "범위_추가내용") { mDetail = tf; }
            else if (/^\s*\d+\s*$/.test(txt)) { mIssue = tf; }
        }
        if (!mSchool) writeLog("[경고] 간지 학교명 프레임(챕터_숫자) 미발견");
        if (!mIssue) writeLog("[경고] 간지 순번 프레임 미발견");
        if (!mRange || !mDetail) {
            throw new Error("간지 범위/범위_추가내용 마스터 프레임 미발견");
        }

        // 1) 마스터: 학교명 + 순번
        if (mSchool) setFrameText(doc, mSchool, settings.ganji_school, "챕터_숫자");
        var issueNum = String(parseInt(settings.issue_num, 10) || 1);
        if (mIssue) { try { mIssue.contents = issueNum; } catch (eIN) {} }

        // 2) 페이지1 상단 슬러그 (y<0 프레임: 범위/범위_추가내용)
        var ranges = settings.ranges || [];
        var titles = [], details = [];
        for (var r = 0; r < ranges.length; r++) {
            if (ranges[r].title) titles.push(ranges[r].title);
            if (ranges[r].detail) details.push(ranges[r].detail);
        }
        var slugTitle = titles.join(" / ");
        var slugDetail = details.join(" / ");
        var p0tf = page0.textFrames;
        var slugTitleSet = false, slugDetailSet = false;
        for (var s = 0; s < p0tf.length; s++) {
            var stf = p0tf[s];
            var gb;
            try { gb = stf.geometricBounds; } catch (eG) { continue; }
            if (gb[0] >= 0) continue;               // 페이지 위 슬러그만
            var scs = frameCS(stf);
            if (scs === "범위") {
                setFrameText(doc, stf, slugTitle, "범위");
                slugTitleSet = true;
            } else if (scs === "범위_추가내용") {
                setFrameText(doc, stf, slugDetail, "범위_추가내용");
                slugDetailSet = true;
            }
        }

        // 3) 범위 프레임쌍 — 마스터 오버라이드 후 위로 이동, 추가 범위는
        //    아래로 +21.5mm 간격 복제 (위아래 병기 — 기존 결합본 실측 배치)
        var ovrRange = overrideOrReuse(mRange, page0);
        var ovrDetail = overrideOrReuse(mDetail, page0);
        moveToY(ovrRange, GANJI_RANGE_Y);
        moveToY(ovrDetail, GANJI_DETAIL_Y);
        setFrameText(doc, ovrRange, ranges.length ? ranges[0].title : " ", "범위");
        setFrameText(doc, ovrDetail,
                     (ranges.length && ranges[0].detail) ? ranges[0].detail : " ",
                     "범위_추가내용");
        var pairs = 1;
        for (var k = 1; k < ranges.length; k++) {
            var dupR = ovrRange.duplicate();
            var dupD = ovrDetail.duplicate();
            moveToY(dupR, GANJI_RANGE_Y + GANJI_PAIR_STEP * k);
            moveToY(dupD, GANJI_DETAIL_Y + GANJI_PAIR_STEP * k);
            setFrameText(doc, dupR, ranges[k].title, "범위");
            setFrameText(doc, dupD, ranges[k].detail || " ", "범위_추가내용");
            pairs++;
        }

        ganjiRep.ok = true;
        ganjiRep.school = settings.ganji_school;
        ganjiRep.issue_num = issueNum;
        ganjiRep.slug_title = slugTitle;
        ganjiRep.slug_title_set = slugTitleSet;
        ganjiRep.slug_detail = slugDetail;
        ganjiRep.slug_detail_set = slugDetailSet;
        ganjiRep.range_pairs = pairs;
        writeLog("간지 기재: " + settings.ganji_school + " / 순번 " + issueNum +
                 " / 범위쌍 " + pairs + "개");
    }

    // ───────────────────────────────────────────────────────────────
    // [스펙4] 링크 점검 — 리링크 후 전부 임베드
    //   Link.unlink() 가 InDesign '링크 임베드'에 해당 (임베드 후에도
    //   doc.links 에 status LINK_EMBEDDED 로 남음 — 기존 결합본 실측 동일).
    // ───────────────────────────────────────────────────────────────

    function linkEls(doc) {
        try { return doc.links.everyItem().getElements(); } catch (e) { return []; }
    }

    function processLinks(doc, relinkMap, linkRep) {
        var els = linkEls(doc);
        linkRep.total = els.length;
        var missingBefore = 0, relinked = 0, embedded = 0;

        // 1) 깨진 링크 리링크 (파일명 매칭 — 파이썬 사전 스캔 맵)
        for (var i = 0; i < els.length; i++) {
            var lk = els[i];
            var st;
            try { st = lk.status; } catch (eS) { continue; }
            if (st === LinkStatus.LINK_MISSING) {
                missingBefore++;
                var nm = "";
                try { nm = String(lk.name); } catch (eN) {}
                var cand = relinkMap[nm];
                if (cand && (new File(cand)).exists) {
                    try {
                        lk.relink(new File(cand));
                        relinked++;
                        writeLog("리링크: " + nm + " -> " + cand);
                    } catch (eRl) {
                        writeLog("[경고] 리링크 실패: " + nm + " — " + eRl.message);
                    }
                } else {
                    writeLog("[경고] 리링크 후보 없음: " + nm);
                }
            }
        }

        // 2) 구버전 링크 업데이트
        els = linkEls(doc);
        for (var u = 0; u < els.length; u++) {
            try {
                if (els[u].status === LinkStatus.LINK_OUT_OF_DATE) els[u].update();
            } catch (eU) {}
        }

        // 3) 전부 임베드
        els = linkEls(doc);
        for (var e2 = 0; e2 < els.length; e2++) {
            var lk2 = els[e2];
            var st2;
            try { st2 = lk2.status; } catch (eS2) { continue; }
            if (st2 === LinkStatus.LINK_EMBEDDED) continue;
            if (st2 === LinkStatus.LINK_MISSING) continue;   // 리링크 실패분 — 아래 재계수
            try {
                lk2.unlink();     // == 임베드
                embedded++;
            } catch (eE) {
                var nm2 = ""; try { nm2 = String(lk2.name); } catch (eN2) {}
                writeLog("[경고] 임베드 실패: " + nm2 + " — " + eE.message);
            }
        }

        // 4) 최종 재계수 (게이트 판정값)
        els = linkEls(doc);
        var missingAfter = 0, unembeddedAfter = 0;
        var detail = [];
        for (var f = 0; f < els.length; f++) {
            var st3, nm3 = "";
            try { st3 = els[f].status; } catch (eS3) { continue; }
            try { nm3 = String(els[f].name); } catch (eN3) {}
            if (st3 === LinkStatus.LINK_MISSING) {
                missingAfter++;
                detail.push({ name: nm3, status: "MISSING" });
            } else if (st3 !== LinkStatus.LINK_EMBEDDED) {
                unembeddedAfter++;
                detail.push({ name: nm3, status: String(st3) });
            }
        }
        linkRep.missing_before = missingBefore;
        linkRep.relinked = relinked;
        linkRep.embedded = embedded;
        linkRep.missing_after = missingAfter;
        linkRep.unembedded_after = unembeddedAfter;
        linkRep.detail = detail;
        writeLog("링크: 총 " + els.length + " (깨짐 " + missingBefore +
                 " → 리링크 " + relinked + ", 임베드 " + embedded +
                 ", 잔여 깨짐 " + missingAfter + ", 미임베드 " + unembeddedAfter + ")");
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
        // 같은 경로의 문서가 이미 열려 있으면 닫는다 — 재실행 시 InDesign이
        // 낡은 문서를 재사용해 override 중복 오류가 나는 것 방지.
        for (var dPre = app.documents.length - 1; dPre >= 0; dPre--) {
            try {
                if (app.documents[dPre].fullName.toString() === outFile.toString()) {
                    app.documents[dPre].close(SaveOptions.NO);
                }
            } catch (ePre) {}
        }
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
                // [스펙2] 소스 지오메트리 캡처 → 복제 → 복원
                var srcGeo = collectGeo(matchedDoc.pages[p2]);
                try {
                    matchedDoc.pages[p2].duplicate(
                        LocationOptions.AT_END, newDoc.pages.lastItem()
                    );
                } catch (eDup) {
                    writeLog("[경고] " + code + " p" + p2 +
                             " 복제 실패: " + eDup.message);
                    continue;
                }
                try {
                    restoreGeo(newDoc.pages.lastItem(), srcGeo, report.geometry,
                               matchedFileName + " p" + (p2 + 1));
                } catch (eRg) {
                    writeLog("[경고] 지오메트리 복원 오류 p" + (p2 + 1) + ": " +
                             eRg.message);
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

        // [스펙5] 간지/1페이지 텍스트
        try {
            applyGanji(newDoc, report.ganji);
        } catch (eGj) {
            report.ganji.ok = false;
            report.ganji.error = eGj.message || String(eGj);
            writeLog("[경고] 간지 기재 실패: " + report.ganji.error);
        }

        // [스펙4] 링크 리링크 + 전부 임베드 (저장 전)
        try {
            processLinks(newDoc, settings.relink_map || {}, report.links);
        } catch (eLn) {
            writeLog("[경고] 링크 처리 오류: " + (eLn.message || eLn));
        }

        // 스프레드 재편성 허용 (v1 동일)
        try {
            allowShuffleAll(newDoc);
            writeLog("스프레드 재편성 허용 설정: " + newDoc.spreads.length + " spread");
        } catch (eShf) { writeLog("[경고] 재편성 허용 설정 실패: " + eShf.message); }

        // 오버플로우 스캔 (전체 페이지 텍스트 프레임)
        try {
            for (var op = 0; op < newDoc.pages.length; op++) {
                var otf = newDoc.pages[op].textFrames;
                for (var of2 = 0; of2 < otf.length; of2++) {
                    var isOvf = false;
                    try { isOvf = otf[of2].overflows; } catch (eOv) {}
                    if (isOvf) {
                        report.overflow_pages.push(String(newDoc.pages[op].name));
                        break;
                    }
                }
            }
        } catch (eOs) {}

        // 저장 (.indd만 — PDF export 없음 [스펙3·1])
        try { newDoc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
        writeLog("저장: " + newDoc.fullName.fsName);
        writeLog("총 페이지: " + newDoc.pages.length);
        if (report.unresolved.length > 0) {
            writeLog("[경고] 매칭 실패 코드 " + report.unresolved.length + "개: " +
                     report.unresolved.join(", "));
        }
        writeLog("지오메트리: 교정 전 최대 " + report.geometry.max_drift_before_mm +
                 "mm → 잔여 " + report.geometry.max_residual_mm + "mm");

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
