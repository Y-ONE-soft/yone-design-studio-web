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
//   [W28-확장] 교과서/EBS 분석본 소스(kind:"doc") — 문서 전체를 결합
//     (간지/표지 마스터·마스터 없는 개요 페이지 스킵), 페이지 크기 대조
//     리포트(doc_sources), 자동 유도 범위를 소스 간지/개요 텍스트로 보강
//     (교과서: cs 범위/챕터, EBS: cs 카테고리/부제목 — 손마무리 실물 전례)
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
    // 좌표계 정규화 — geometricBounds는 문서의 눈금자 원점(rulerOrigin)
    //   기준이라 소스와 결합본의 설정이 다르면 같은 위치가 다른 수치로
    //   읽힌다. 실사고(2026-08-17 한영2): 소스는 PAGE_ORIGIN(오른쪽 페이지
    //   프레임 x=22mm), 템플릿은 SPREAD_ORIGIN(x=232mm) → 아래 restoreGeo가
    //   페이지폭 210mm를 "드리프트"로 오인해 오른쪽 페이지 프레임을 전부
    //   왼쪽 페이지로 210+4mm 밀어버렸다.
    //   → 캡처/복원 구간 동안 양쪽 문서를 PAGE_ORIGIN + zeroPoint(0,0)로
    //     맞추고, 끝나면 원래 설정으로 되돌린다(문서 원본 설정 보존).
    // ───────────────────────────────────────────────────────────────

    function normalizeRuler(doc) {
        // 반환값을 restoreRuler에 그대로 넘기면 원상복구된다.
        var prev = { origin: null, zero: null };
        try {
            prev.origin = doc.viewPreferences.rulerOrigin;
            if (prev.origin !== RulerOrigin.PAGE_ORIGIN) {
                doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
            } else {
                prev.origin = null;   // 변경 없음 — 되돌릴 것도 없음
            }
        } catch (eRo) { prev.origin = null; }
        try {
            var z = doc.zeroPoint;
            if (Math.abs(z[0]) > 0.001 || Math.abs(z[1]) > 0.001) {
                prev.zero = [z[0], z[1]];
                doc.zeroPoint = [0, 0];
            }
        } catch (eZp) { prev.zero = null; }
        return prev;
    }

    function restoreRuler(doc, prev) {
        if (!prev) return;
        try {
            if (prev.zero !== null) doc.zeroPoint = prev.zero;
        } catch (eZr) {}
        try {
            if (prev.origin !== null) doc.viewPreferences.rulerOrigin = prev.origin;
        } catch (eOr) {}
    }

    // ───────────────────────────────────────────────────────────────
    // [스펙2] 프레임 지오메트리 캡처/복원
    //   실측(repro1): 문서 간 page.duplicate가 콘텐츠 아이템을 페이지 기준
    //   LEFT +2mm / RIGHT +4mm 순수 평행이동시킨다 (슬러그 탭은 무이동).
    //   → 복제 직후 소스 좌표와의 (dx,dy)를 item.move로 되돌린다.
    //   move는 회전/크기를 건드리지 않는 순수 이동이라 안전.
    // ───────────────────────────────────────────────────────────────

    // 실측 드리프트는 LEFT +2 / RIGHT +4mm. 이 상한을 넘는 값은 좌표계
    // 불일치·아이템 순서 어긋남 신호이므로 "교정"하지 않고 실패로 남긴다
    // (조용히 밀면 페이지 하나만큼 어긋난 조판이 그대로 납품된다).
    var GEO_MAX_DRIFT_MM = 20;

    // 페이지의 pageItems는 라이브 컬렉션이라 아이템이 이동으로 페이지
    // 소속을 벗어나면 인덱스가 밀린다 → 미리 배열로 스냅샷한다.
    function snapItems(page) {
        try { return page.pageItems.everyItem().getElements(); }
        catch (eEv) {}
        var arr = [];
        try {
            var it = page.pageItems;
            for (var i = 0; i < it.length; i++) arr.push(it[i]);
        } catch (eP) {}
        return arr;
    }

    function collectGeo(page) {
        var arr = [];
        var items = snapItems(page);
        for (var i = 0; i < items.length; i++) {
            var gb;
            try { gb = items[i].geometricBounds; } catch (eG) { gb = null; }
            arr.push(gb);
        }
        return arr;
    }

    function restoreGeo(newPage, srcGeo, geoRep, srcLabel) {
        var items = snapItems(newPage);
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
            if (drift > GEO_MAX_DRIFT_MM) {
                geoRep.oversized_drift.push({
                    page: String(newPage.name), src: srcLabel, item: i,
                    dx: round3(dx), dy: round3(dy)
                });
                writeLog("[경고] 지오메트리 드리프트 과대 p" + newPage.name +
                         " item" + i + " (dx=" + round3(dx) + ", dy=" +
                         round3(dy) + "mm > 상한 " + GEO_MAX_DRIFT_MM +
                         "mm) — 이동 생략, 게이트 실패로 남김");
                if (drift > maxAfter) maxAfter = drift;
                continue;
            }
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

    // 캡처→복원 대상 로컬 서식 속성 (W28-피드백2, 2026-07-19):
    // 크기 계열(폰트/크기/행간)만 복원하던 1차 수리는 색 계열을 놓쳐
    // 문자스타일 재적용이 학교명 글자색·밑줄 색을 스타일 정의값으로
    // 되돌렸다(사용자 피드백: "색상이 이상하다"). 색/밑줄/획 계열까지
    // 전부 캡처해 복원한다.
    var KEEP_COLOR_ATTRS = [
        "fillColor", "fillTint", "strokeColor", "strokeTint",
        "underline", "underlineColor", "underlineTint",
        "underlineWeight", "underlineOffset", "underlineType"
    ];

    function captureTextAttrs(r0) {
        var keep = {};
        try { keep.appliedFont = r0.appliedFont; } catch (e1) {}
        try { keep.pointSize = r0.pointSize; } catch (e2) {}
        try { keep.leading = r0.leading; } catch (e3) {}
        for (var i = 0; i < KEEP_COLOR_ATTRS.length; i++) {
            var k = KEEP_COLOR_ATTRS[i];
            try { keep[k] = r0[k]; } catch (eK) {}
        }
        return keep;
    }

    function applyTextAttrs(t, keep) {
        try { if (keep.appliedFont) t.appliedFont = keep.appliedFont; } catch (e1) {}
        try { if (keep.pointSize !== undefined) t.pointSize = keep.pointSize; } catch (e2) {}
        try { if (keep.leading !== undefined) t.leading = keep.leading; } catch (e3) {}
        for (var i = 0; i < KEEP_COLOR_ATTRS.length; i++) {
            var k = KEEP_COLOR_ATTRS[i];
            if (keep[k] === undefined) continue;
            try { t[k] = keep[k]; } catch (eK) {
                writeLog("[경고] 서식 복원 실패(" + k + "): " + (eK.message || eK));
            }
        }
    }

    function swatchName(v) {
        if (v === null || v === undefined) return null;
        try { if (v.name !== undefined) return String(v.name); } catch (e) {}
        try { return String(v); } catch (e2) { return null; }
    }

    // 리포트/게이트용 직렬화 스냅샷 (기대 vs 실측 대조 — verify 게이트)
    function attrsSnapshot(r0) {
        var s = {};
        try { s.font = String(r0.appliedFont.name); }
        catch (e1) { try { s.font = String(r0.appliedFont); } catch (e1b) {} }
        try { s.pointSize = r0.pointSize; } catch (e2) {}
        try { s.leading = String(r0.leading); } catch (e3) {}
        try { s.fillColor = swatchName(r0.fillColor); } catch (e4) {}
        try { s.fillTint = r0.fillTint; } catch (e5) {}
        try { s.strokeColor = swatchName(r0.strokeColor); } catch (e6) {}
        try { s.underline = r0.underline; } catch (e7) {}
        try { s.underlineColor = swatchName(r0.underlineColor); } catch (e8) {}
        try { s.underlineTint = r0.underlineTint; } catch (e9) {}
        try { s.underlineWeight = String(r0.underlineWeight); } catch (e10) {}
        try { s.underlineOffset = String(r0.underlineOffset); } catch (e11) {}
        return s;
    }

    function diffAttrs(expected, actual) {
        var out = [];
        if (!expected || !actual) return out;
        for (var k in expected) {
            if (!expected.hasOwnProperty(k)) continue;
            var e = expected[k], a = actual[k];
            var same;
            if (typeof e == "number" && typeof a == "number") {
                same = Math.abs(e - a) < 0.01;
            } else {
                same = String(e) === String(a);
            }
            if (!same) out.push(k + ": " + e + " -> " + a);
        }
        return out;
    }

    function setFrameText(doc, tf, text, csName) {
        // 템플릿 프레임의 손질된 로컬 서식(폰트/크기/행간/색/밑줄)을 캡처→복원.
        // 실사고(2026-07-19 배재1): 간지 학교명 프레임은 문자스타일
        // '챕터_숫자'(MBC 1961 OTF 16pt) 위에 로컬 오버라이드(G마켓 산스
        // 11pt)로 3.88mm 프레임에 맞춰져 있는데, contents 대입+스타일
        // 재적용이 오버라이드를 유실시켜 16pt로 튀며 전량 오버셋
        // (0자 표시 + 빨간 +)이 됐다.
        // 주의: tf.texts[0]은 '프레임에 표시된 텍스트'라 오버셋 상태에서는
        // 빈 범위가 되어 서식 대입이 예외 없는 침묵 no-op이 된다 (실측:
        // contents 대입 직후 16pt로 튀며 즉시 오버셋 → 이후 texts[0] 조작
        // 전부 무효). 스토리(parentStory)는 오버셋과 무관하게 전체 텍스트를
        // 담으므로 서식 조작은 스토리 기준으로 한다.
        // 반환: { expected, actual } — 기재 전 캡처 스냅샷과 기재 후 실측
        // 스냅샷 (verify의 간지 서식 게이트가 대조).
        var keep = null, expected = null;
        try {
            var r0 = tf.parentStory.textStyleRanges[0];
            keep = captureTextAttrs(r0);
            expected = attrsSnapshot(r0);
        } catch (eKeep) {}
        tf.contents = String(text);
        var storyText = null;
        try { storyText = tf.parentStory.texts[0]; } catch (eSt) {}
        // 문자스타일 재적용 (자동 생성 금지 — 없으면 경고만)
        if (csName) {
            var cs = findCharStyle(doc, csName);
            if (cs) {
                try { if (storyText) storyText.appliedCharacterStyle = cs; } catch (eA) {}
            } else {
                writeLog("[경고] 문자스타일 없음: " + csName);
            }
        }
        if (keep !== null && storyText) {
            applyTextAttrs(storyText, keep);
        }
        var actual = null;
        try { actual = attrsSnapshot(tf.parentStory.textStyleRanges[0]); } catch (eAct) {}
        return { expected: expected, actual: actual };
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

        // 기재 프레임 오버셋 게이트용 수집 (2026-07-19 실사고: 학교명
        // 프레임은 마스터 위에 있어 페이지 오버플로우 스캔에 안 잡혔다)
        var edited = [];

        // 1) 마스터: 학교명 + 순번
        var schoolAttrs = null;
        if (mSchool) {
            schoolAttrs = setFrameText(doc, mSchool, settings.ganji_school, "챕터_숫자");
            edited.push({ tf: mSchool, name: "간지 학교명(챕터_숫자)" });
        }
        var issueNum = String(parseInt(settings.issue_num, 10) || 1);
        if (mIssue) {
            try { mIssue.contents = issueNum; } catch (eIN) {}
            edited.push({ tf: mIssue, name: "간지 순번" });
        }

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
                edited.push({ tf: stf, name: "슬러그 범위" });
            } else if (scs === "범위_추가내용") {
                setFrameText(doc, stf, slugDetail, "범위_추가내용");
                slugDetailSet = true;
                edited.push({ tf: stf, name: "슬러그 범위_추가내용" });
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
        edited.push({ tf: ovrRange, name: "범위쌍1 범위" });
        edited.push({ tf: ovrDetail, name: "범위쌍1 추가내용" });
        var pairs = 1;
        for (var k = 1; k < ranges.length; k++) {
            var dupR = ovrRange.duplicate();
            var dupD = ovrDetail.duplicate();
            moveToY(dupR, GANJI_RANGE_Y + GANJI_PAIR_STEP * k);
            moveToY(dupD, GANJI_DETAIL_Y + GANJI_PAIR_STEP * k);
            setFrameText(doc, dupR, ranges[k].title, "범위");
            setFrameText(doc, dupD, ranges[k].detail || " ", "범위_추가내용");
            edited.push({ tf: dupR, name: "범위쌍" + (k + 1) + " 범위" });
            edited.push({ tf: dupD, name: "범위쌍" + (k + 1) + " 추가내용" });
            pairs++;
        }

        // 기재 프레임 오버셋 게이트 — 하나라도 넘치면 간지 기재 실패로
        // 판정한다 (verify ganji_ok=False → GDrive 저장 보류).
        var oversetNames = [];
        for (var ov = 0; ov < edited.length; ov++) {
            var isOver = false;
            try { isOver = edited[ov].tf.overflows; } catch (eOvf) {}
            if (isOver) oversetNames.push(edited[ov].name);
        }
        ganjiRep.overset_frames = oversetNames;

        // 학교명 서식 보존 게이트 (W28-피드백2): 기재 전 캡처(기대)와
        // 기재 후 실측을 대조 — 색/밑줄/크기 계열이 하나라도 달라지면
        // 간지 기재 실패로 판정 (verify ganji_ok=False → GDrive 저장 보류).
        var attrMismatches = [];
        if (schoolAttrs) {
            ganjiRep.school_attrs = schoolAttrs;
            attrMismatches = diffAttrs(schoolAttrs.expected, schoolAttrs.actual);
            ganjiRep.attr_mismatches = attrMismatches;
        }

        ganjiRep.ok = true;
        ganjiRep.school = settings.ganji_school;
        ganjiRep.issue_num = issueNum;
        ganjiRep.slug_title = slugTitle;
        ganjiRep.slug_title_set = slugTitleSet;
        ganjiRep.slug_detail = slugDetail;
        ganjiRep.slug_detail_set = slugDetailSet;
        ganjiRep.range_pairs = pairs;
        if (oversetNames.length) {
            ganjiRep.ok = false;
            ganjiRep.error = "기재 프레임 오버셋: " + oversetNames.join(", ");
            writeLog("[경고] 간지 " + ganjiRep.error);
        }
        if (attrMismatches.length) {
            ganjiRep.ok = false;
            var attrMsg = "학교명 서식 훼손: " + attrMismatches.join(", ");
            ganjiRep.error = ganjiRep.error
                ? ganjiRep.error + " / " + attrMsg : attrMsg;
            writeLog("[경고] 간지 " + attrMsg);
        }
        writeLog("간지 기재: " + settings.ganji_school + " / 순번 " + issueNum +
                 " / 범위쌍 " + pairs + "개" +
                 (oversetNames.length ? " / 오버셋 " + oversetNames.length + "건" : "") +
                 (attrMismatches.length ? " / 서식 불일치 " + attrMismatches.length + "건" : ""));
    }

    // ───────────────────────────────────────────────────────────────
    // [스펙4] 링크 점검 — 리링크 후 전부 임베드
    //   Link.unlink() 가 InDesign '링크 임베드'에 해당 (임베드 후에도
    //   doc.links 에 status LINK_EMBEDDED 로 남음 — 기존 결합본 실측 동일).
    // ───────────────────────────────────────────────────────────────

    function linkEls(doc) {
        try { return doc.links.everyItem().getElements(); } catch (e) { return []; }
    }

    // ───────────────────────────────────────────────────────────────
    // [1주차] 간지 1P 가이드 버전 교체
    //   첫 주차(순번 1)로 나가는 분석본만 간지 1P를 가이드 버전으로 넣는다.
    //   2주차부터는 템플릿 기본 1P 그대로.
    //   템플릿의 1P는 간지-마스터에 임베드된 링크(실측: 1P.pdf, D버전)라
    //   relink로 교체한다 — 임베드 링크도 relink가 되고 배치/스케일이
    //   그대로 보존된다(실측: gb 오차 0.00002mm). 교체 후 processLinks가
    //   다시 임베드한다.
    // ───────────────────────────────────────────────────────────────

    function guideFileFor(link, cfg) {
        var nm = "";
        try { nm = String(link.name); } catch (eN) { return null; }
        var alt = cfg.pairs[nm];
        if (!alt) return null;
        // ① 현재 링크와 같은 폴더(C버전/D버전 등)에서 먼저 찾는다 —
        //    버전 폴더가 바뀌어도 짝을 놓치지 않는다.
        try {
            var cur = new File(link.filePath);
            var sib = new File(cur.parent.fsName + "/" + alt);
            if (sib.exists) return sib;
        } catch (eS) {}
        // ② 파이썬이 이미지 폴더를 스캔해 넘긴 절대경로 폴백
        var p = cfg.map ? cfg.map[nm] : null;
        if (p) {
            var f = new File(p);
            if (f.exists) return f;
        }
        return null;
    }

    function applyGuide1P(doc, cfg, rep) {
        rep.enabled = !!(cfg && cfg.enabled);
        if (!rep.enabled) return;
        var els = linkEls(doc);
        for (var i = 0; i < els.length; i++) {
            var lk = els[i], nm = "";
            try { nm = String(lk.name); } catch (eN) { continue; }
            if (!cfg.pairs[nm]) continue;
            var gf = guideFileFor(lk, cfg);
            if (!gf) {
                rep.missing.push(cfg.pairs[nm]);
                writeLog("[경고] 1주차 간지 1P 가이드 파일 없음: " + cfg.pairs[nm]);
                continue;
            }
            var gName = String(gf.name);
            // File.name은 URI 인코딩("%20") — 로그/리포트는 원래 이름으로
            try { gName = decodeURI(gName); } catch (eDe) {}
            try {
                lk.relink(gf);
                rep.applied.push({ from: nm, to: gName });
                writeLog("간지 1P → 가이드 버전 교체: " + nm + " → " + gName);
            } catch (eRl) {
                rep.failed.push(nm + ": " + (eRl.message || eRl));
                writeLog("[경고] 간지 1P 가이드 교체 실패: " + nm +
                         " — " + (eRl.message || eRl));
            }
        }
        if (!rep.applied.length && !rep.missing.length && !rep.failed.length) {
            rep.failed.push("교체 대상 링크 없음 (1P.pdf/1P.ai 미발견)");
            writeLog("[경고] 1주차인데 간지 1P 링크를 찾지 못했습니다 — 교체 없음");
        }
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
                    count_mismatch_pages: [], oversized_drift: [], pages: [] },
        links: {},
        ganji: { ok: false },
        overflow_pages: [],
        // doc 소스가 결합 전부터 갖고 있던 오버셋을 그대로 물려받은 페이지
        // (실측: 올독기2 9강 p13 — 소스와 동일 스토리/프레임/자수).
        // 손마무리 실물에도 잔존 overset 전례가 있어 게이트는 통과시키고
        // verify가 경고로만 노출한다. 결합이 새로 만든 오버셋은 여전히
        // overflow_pages로 게이트 실패.
        preexisting_overflow_pages: [],
        doc_sources: [],
        guide_1p: { enabled: false, applied: [], missing: [], failed: [] }
    };

    // ── [W28-확장] 유틸 ────────────────────────────────────────────

    function trimStr(s) {
        return String(s).replace(/^[\s ]+|[\s ]+$/g, "");
    }

    // 자동 유도 범위(auto:true)를 소스 간지/개요 텍스트로 보강.
    // 손마무리 실물 전례(w28_ext/probe_ranges 실측):
    //   교과서 간지: cs '범위'="공통영어1 비상(홍) 3과", cs '챕터'=과 제목
    //   EBS 개요:   cs '카테고리'="올림포스 영어독해 기본2",
    //               cs '부제목'="9강 어휘 적절성"
    function enrichDocRange(doc, srcMeta, scanPages) {
        var idx = (srcMeta.range_idx === undefined) ? -1 : srcMeta.range_idx;
        if (idx < 0) return null;
        var ranges = settings.ranges || [];
        var rng = ranges[idx];
        if (!rng || !rng.auto) return null;
        var titleCS = (srcMeta.type === "ebs") ? "카테고리" : "범위";
        var detailCS = (srcMeta.type === "ebs") ? "부제목" : "챕터";
        var pagesToScan = scanPages.length ? scanPages : [0];
        var title = null, detail = null;
        for (var sp = 0; sp < pagesToScan.length; sp++) {
            var pIdx = pagesToScan[sp];
            if (pIdx < 0 || pIdx >= doc.pages.length) continue;
            var items;
            try { items = doc.pages[pIdx].allPageItems; } catch (eIt) { continue; }
            for (var i = 0; i < items.length; i++) {
                var txt;
                try { txt = items[i].contents; } catch (eC) { continue; }
                if (typeof txt !== "string" || !trimStr(txt).length) continue;
                var cs = frameCS(items[i]);
                if (title === null && cs === titleCS) title = trimStr(txt);
                if (detail === null && cs === detailCS) detail = trimStr(txt);
            }
            if (title !== null && detail !== null) break;
        }
        if (title !== null) rng.title = title;
        if (detail !== null) rng.detail = detail;
        return { title: rng.title, detail: rng.detail };
    }

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
        // 같은 경로/이름의 문서가 이미 열려 있으면 닫는다 — 재실행 시
        // InDesign이 낡은 문서를 재사용해 override 중복·저장 행(hang)이
        // 나는 것 방지. fullName은 백킹 파일이 지워진 문서에서 접근이
        // 불안정할 수 있어 이름(name) 매칭도 함께 사용한다 (job별 출력
        // 파일명은 고유 — 이름 충돌로 남의 문서를 닫을 일 없음).
        var outBase = outFile.name;
        for (var dPre = app.documents.length - 1; dPre >= 0; dPre--) {
            var closeIt = false;
            try {
                if (app.documents[dPre].fullName.toString() === outFile.toString()) closeIt = true;
            } catch (ePre) {}
            try {
                if (!closeIt && app.documents[dPre].name === outBase) closeIt = true;
            } catch (ePre2) {}
            if (closeIt) {
                try { app.documents[dPre].close(SaveOptions.NO); } catch (ePre3) {}
            }
        }
        // 잔존 출력 파일은 복사 전에 제거 — 직전 실행이 남긴 파일 위로
        // 덮어쓰며 열면 InDesign이 낡은 문서 상태를 되살려 페이지 정리가
        // 침묵 no-op이 되고 행(hang)으로 이어질 수 있다 (2026-07-19 재실행 실측:
        // 7페이지 잔존 → 정리 무효 → duplicate 중 무기한 블록).
        if (outFile.exists && !outFile.remove()) {
            fail("잔존 출력 파일 제거 실패(파일 사용 중?): " + OUTPUT_INDD);
            writeReport(report);
            return;
        }
        if (!tplFile.copy(outFile)) { fail("템플릿 복사 실패: " + OUTPUT_INDD); writeReport(report); return; }
        writeLog("템플릿 복사 -> " + outFile.fsName);

        var newDoc;
        try { newDoc = app.open(outFile, false); }
        catch (eOpen) { fail("사본 열기 실패: " + eOpen.message); writeReport(report); return; }

        allowShuffleAll(newDoc);

        // 좌표계 정규화 — 결합(복제+지오메트리 복원) 구간 동안만 PAGE_ORIGIN.
        // 결합이 끝나면 rulerPrevNew로 템플릿 원래 설정을 되돌린다.
        var rulerPrevNew = normalizeRuler(newDoc);
        var rulerPrevSrc = {};   // uri -> prev (소스 문서 원상복구용)

        // [W28-확장] 템플릿 페이지 크기 (doc 소스 호환성 대조 기준)
        var TPL_W = 0, TPL_H = 0;
        try {
            TPL_W = newDoc.documentPreferences.pageWidth;
            TPL_H = newDoc.documentPreferences.pageHeight;
        } catch (eTs) {}

        // 후보 파일 dedup + open + markers 수집
        var docCache    = {};
        var openedByUs  = {};
        var fileMarkers = {};
        var allCandidates = {};

        for (var si = 0; si < SOURCES.length; si++) {
            var src = SOURCES[si];
            var isDoc = (src.kind === "doc");
            var cands = src.candidates ||
                        (src.local_path ? [src.local_path] : []);
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
                    // 소스도 결합본과 같은 좌표계로 (닫기 전 원상복구)
                    rulerPrevSrc[uri] = normalizeRuler(got.doc);
                    // doc 소스(교과서/EBS)는 마커 매칭을 쓰지 않는다
                    fileMarkers[uri] = isDoc ? [] : findAllMarkers(got.doc);
                    try { tagStoryLabels(got.doc); } catch (eTag) {}
                    writeLog("열기: " + cf.displayName +
                             (isDoc ? " (doc 소스)"
                                    : " (markers=" + fileMarkers[uri].length + ")"));
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
        // fail-loud: 정리 후에도 초과 페이지가 남으면 낡은 문서 재사용 등
        // 비정상 상태 — 침묵 진행하면 stale 문서 위 duplicate로 InDesign이
        // 보호 종료(ProtectiveShutdown)까지 갈 수 있다 (2026-07-19 실측).
        if (newDoc.pages.length > KEEP_HEAD) {
            fail("베이스 정리 실패: " + newDoc.pages.length + "p 잔존 (기대 " +
                 KEEP_HEAD + "p) — 낡은 문서 재사용 의심, 중단");
            try { newDoc.close(SaveOptions.NO); } catch (eClAb) {}
            writeReport(report);
            return;
        }

        var codeRanges = [];
        var extractedRanges = {};
        // 소스에 원래 있던 오버셋을 물려받은 새 문서 페이지 인덱스
        var preexistingOvfNewPages = {};

        for (var ci2 = 0; ci2 < SOURCES.length; ci2++) {
            var srcMeta = SOURCES[ci2];

            // ── [W28-확장] 교과서/EBS 문서 소스 — 전체 결합 ────────────
            if (srcMeta.kind === "doc") {
                var dFile = new File(srcMeta.local_path || "");
                var dUri = dFile.exists ? dFile.absoluteURI : "";
                var dDoc = dUri ? docCache[dUri] : null;
                var docRec = {
                    label: srcMeta.label || "", type: srcMeta.type || "",
                    pages_total: 0, pages_merged: 0, skipped_pages: [],
                    page_w: null, page_h: null,
                    tpl_w: round3(TPL_W), tpl_h: round3(TPL_H),
                    size_mismatch: false, range: null
                };
                if (!dDoc) {
                    report.unresolved.push(srcMeta.label || "doc소스");
                    report.doc_sources.push(docRec);
                    writeLog("[경고] doc 소스 열기 실패: " + (srcMeta.label || ""));
                    continue;
                }
                var dKey = "doc|" + dUri;
                if (extractedRanges[dKey]) {
                    writeLog("  [doc] " + srcMeta.label + " → 이미 결합됨 — skip");
                    continue;
                }
                extractedRanges[dKey] = true;
                try {
                    docRec.page_w = round3(dDoc.documentPreferences.pageWidth);
                    docRec.page_h = round3(dDoc.documentPreferences.pageHeight);
                } catch (eDs) {}
                if (docRec.page_w !== null &&
                        (Math.abs(docRec.page_w - TPL_W) > 1 ||
                         Math.abs(docRec.page_h - TPL_H) > 1)) {
                    // 비호환 — 무리하게 맞추지 않는다. verify doc_ok 게이트가
                    // GDrive 저장을 보류하고 실측치를 보고한다.
                    docRec.size_mismatch = true;
                    writeLog("[경고] 페이지 크기 비호환: " + srcMeta.label +
                             " " + docRec.page_w + "x" + docRec.page_h +
                             "mm (템플릿 " + round3(TPL_W) + "x" +
                             round3(TPL_H) + "mm) — 결합 보류");
                    report.doc_sources.push(docRec);
                    continue;
                }
                docRec.pages_total = dDoc.pages.length;
                // 간지/표지 마스터·마스터 없는 개요 페이지 스킵 (손마무리
                // 실물 전례: 결합본 내부에 소스 간지가 남지 않는다 —
                // w28_ext/probe_ranges interior_ganji=[] 실측)
                var mergeIdx = [], skippedIdx = [];
                for (var dp = 0; dp < dDoc.pages.length; dp++) {
                    var dmn = "";
                    try {
                        dmn = dDoc.pages[dp].appliedMaster
                            ? String(dDoc.pages[dp].appliedMaster.name) : "";
                    } catch (eDm) {}
                    if (!dmn || dmn.indexOf("간지") !== -1 ||
                            dmn.indexOf("표지") !== -1) {
                        skippedIdx.push(dp);
                    } else {
                        mergeIdx.push(dp);
                    }
                }
                docRec.skipped_pages = skippedIdx;
                // 자동 유도 범위 보강 — 소스 간지/개요 텍스트 (실물 표기)
                try {
                    docRec.range = enrichDocRange(dDoc, srcMeta, skippedIdx);
                } catch (eEn) {
                    writeLog("[경고] 범위 보강 실패: " + (eEn.message || eEn));
                }
                // 소스가 결합 전부터 갖고 있던 오버셋 페이지 스캔 —
                // 물려받은 오버셋은 게이트 실패가 아니라 경고로 노출한다
                var srcOvf = {};
                var srcOvfList = [];
                for (var so = 0; so < mergeIdx.length; so++) {
                    var soIdx = mergeIdx[so];
                    var soTfs = dDoc.pages[soIdx].textFrames;
                    for (var sof = 0; sof < soTfs.length; sof++) {
                        var soOv = false;
                        try { soOv = soTfs[sof].overflows; } catch (eSo) {}
                        if (soOv) {
                            srcOvf[soIdx] = true;
                            srcOvfList.push(soIdx + 1);
                            break;
                        }
                    }
                }
                docRec.src_overflow_pages = srcOvfList;
                if (srcOvfList.length) {
                    writeLog("[안내] 소스 자체 오버셋 " + srcOvfList.length +
                             "p (결합 전부터): " + srcMeta.label +
                             " p" + srcOvfList.join(",p"));
                }
                var dGrpStart = newDoc.pages.length;
                for (var dpi = 0; dpi < mergeIdx.length; dpi++) {
                    var p3 = mergeIdx[dpi];
                    var srcGeo2 = collectGeo(dDoc.pages[p3]);
                    try {
                        dDoc.pages[p3].duplicate(
                            LocationOptions.AT_END, newDoc.pages.lastItem());
                    } catch (eDup2) {
                        writeLog("[경고] " + srcMeta.label + " p" + (p3 + 1) +
                                 " 복제 실패: " + eDup2.message);
                        continue;
                    }
                    if (srcOvf[p3]) {
                        preexistingOvfNewPages[newDoc.pages.length - 1] = true;
                    }
                    try {
                        restoreGeo(newDoc.pages.lastItem(), srcGeo2,
                                   report.geometry,
                                   (srcMeta.label || "doc") + " p" + (p3 + 1));
                    } catch (eRg2) {
                        writeLog("[경고] 지오메트리 복원 오류 " +
                                 srcMeta.label + " p" + (p3 + 1) + ": " +
                                 (eRg2.message || eRg2));
                    }
                }
                var dGrpEnd = newDoc.pages.length - 1;
                docRec.pages_merged = (dGrpEnd >= dGrpStart)
                    ? (dGrpEnd - dGrpStart + 1) : 0;
                if (dGrpEnd >= dGrpStart) {
                    codeRanges.push({ code: srcMeta.label || "doc",
                                      startIdx: dGrpStart, endIdx: dGrpEnd });
                    writeLog("  [doc] " + srcMeta.label + " ← " + dDoc.name +
                             " " + docRec.pages_merged + "p 결합 (스킵 " +
                             skippedIdx.length + "p)" +
                             (docRec.range
                                 ? " / 범위: " + docRec.range.title +
                                   " / " + docRec.range.detail
                                 : ""));
                }
                report.doc_sources.push(docRec);
                continue;
            }

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

        // 결합 끝 — 좌표계 원상복구 (이후 간지/저장은 템플릿 원래 설정 기준)
        restoreRuler(newDoc, rulerPrevNew);
        for (var uriR in rulerPrevSrc) {
            try { restoreRuler(docCache[uriR], rulerPrevSrc[uriR]); } catch (eRr2) {}
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

        // [1주차] 간지 1P 가이드 버전 교체 — 임베드(processLinks) 前에 수행
        try {
            applyGuide1P(newDoc, settings.guide_1p, report.guide_1p);
        } catch (eG1) {
            report.guide_1p.failed.push(eG1.message || String(eG1));
            writeLog("[경고] 간지 1P 가이드 교체 오류: " + (eG1.message || eG1));
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

        // 오버플로우 스캔 (전체 페이지 텍스트 프레임) — 소스에서 물려받은
        // 오버셋(preexistingOvfNewPages)은 별도 목록으로 분리 (경고 전용)
        try {
            for (var op = 0; op < newDoc.pages.length; op++) {
                var otf = newDoc.pages[op].textFrames;
                for (var of2 = 0; of2 < otf.length; of2++) {
                    var isOvf = false;
                    try { isOvf = otf[of2].overflows; } catch (eOv) {}
                    if (isOvf) {
                        if (preexistingOvfNewPages[op]) {
                            report.preexisting_overflow_pages.push(
                                String(newDoc.pages[op].name));
                        } else {
                            report.overflow_pages.push(
                                String(newDoc.pages[op].name));
                        }
                        break;
                    }
                }
            }
        } catch (eOs) {}

        // 적용 마스터 스프레드 프레임도 스캔 — 마스터 위 프레임(간지
        // 학교명 등)은 page.textFrames에 안 잡혀 오버셋이 게이트를
        // 통과하던 구멍 봉합 (2026-07-19 배재1 실사고)
        try {
            var seenMasters = {};
            for (var mp = 0; mp < newDoc.pages.length; mp++) {
                var am = null;
                try { am = newDoc.pages[mp].appliedMaster; } catch (eAm) {}
                if (!am || !am.isValid) continue;
                var mkey = String(am.name);
                if (seenMasters[mkey]) continue;
                seenMasters[mkey] = true;
                var mfr = am.textFrames;
                for (var mf = 0; mf < mfr.length; mf++) {
                    var mOvf = false;
                    try { mOvf = mfr[mf].overflows; } catch (eMOv) {}
                    if (mOvf) {
                        report.overflow_pages.push("master:" + mkey);
                        break;
                    }
                }
            }
        } catch (eMs) {}

        // 저장 (.indd만 — PDF export 없음 [스펙3·1])
        try { newDoc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
        writeLog("저장: " + newDoc.fullName.fsName);
        writeLog("총 페이지: " + newDoc.pages.length);
        if (report.unresolved.length > 0) {
            writeLog("[경고] 매칭 실패 코드 " + report.unresolved.length + "개: " +
                     report.unresolved.join(", "));
        }
        writeLog("지오메트리: 교정 전 최대 " + report.geometry.max_drift_before_mm +
                 "mm → 잔여 " + report.geometry.max_residual_mm + "mm" +
                 (report.geometry.oversized_drift.length
                     ? " / 과대 드리프트 " +
                       report.geometry.oversized_drift.length + "건(이동 생략)"
                     : ""));

        writeReport(report);

        // 결과 문서 보이기
        try { newDoc.windows.add(); } catch (eWin) {}

        // 소스 문서 닫기
        for (var uriClose in openedByUs) {
            try { docCache[uriClose].close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        // "[오류]" 마커 포함 — 러너의 JSX 에러 감지가 즉시 실패로 처리하게
        // (완료 마커만 기다리다 300초 스톨 보류로 빠지는 것 방지)
        writeLog("[오류] 치명적: " + (eMain.message || eMain));
        try { writeReport(report); } catch (eWr) {}
    }

})();
