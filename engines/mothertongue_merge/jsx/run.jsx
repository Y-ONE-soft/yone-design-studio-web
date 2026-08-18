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
    // [간지] 1페이지 기재 — 학교명/순번/범위
    //   analysis_merge_v2 [스펙5] 이식. 마더텅 결합은 종전에 간지를 손대지
    //   않아 템플릿의 예전 학교(광문고1)·순번·범위가 그대로 남아 나갔다.
    //     · 간지-마스터 학교명 프레임: 문자스타일 '챕터_숫자' ("2026 한영고1")
    //     · 순번 프레임: 내용이 숫자뿐인 작은 프레임 (주차)
    //     · 범위 프레임쌍: 마스터 '범위'/'범위_추가내용'을 페이지로 오버라이드
    // ───────────────────────────────────────────────────────────────

    var GANJI_RANGE_Y  = 232;     // 오버라이드 후 범위 프레임 y1 (v2 실측)
    var GANJI_DETAIL_Y = 242.5;   // 오버라이드 후 추가내용 프레임 y1
    var GANJI_PAIR_STEP = 21.5;   // 범위쌍 추가 간격

    function frameCS(tf) {
        try { return tf.texts[0].textStyleRanges[0].appliedCharacterStyle.name; }
        catch (e) { return ""; }
    }

    function findCharStyle(doc, name) {
        // itemByName 은 스타일 그룹 내부를 못 찾음 — allCharacterStyles 탐색
        try {
            var all = doc.allCharacterStyles;
            for (var i = 0; i < all.length; i++) {
                if (all[i].name === name) return all[i];
            }
        } catch (e) {}
        return null;
    }

    // 문자스타일 재적용이 색·밑줄을 스타일 정의값으로 되돌리지 않도록
    // 로컬 서식을 캡처→복원한다 (v2 W28-피드백2 계열).
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
            try { t[k] = keep[k]; } catch (eK) {}
        }
    }

    function setFrameText(doc, tf, text, csName) {
        // 오버셋 상태에서 tf.texts[0] 은 빈 범위가 되어 서식 대입이 침묵
        // no-op 이 된다 → 서식 조작은 parentStory 기준 (v2 실측).
        var keep = null;
        try { keep = captureTextAttrs(tf.parentStory.textStyleRanges[0]); }
        catch (eKeep) {}
        try { tf.contents = String(text); } catch (eSet) {
            writeLog("[경고] 프레임 기재 실패: " + (eSet.message || eSet));
            return;
        }
        var storyText = null;
        try { storyText = tf.parentStory.texts[0]; } catch (eSt) {}
        if (csName) {
            var cs = findCharStyle(doc, csName);
            if (cs) {
                try { if (storyText) storyText.appliedCharacterStyle = cs; } catch (eA) {}
            } else {
                writeLog("[경고] 문자스타일 없음: " + csName);
            }
        }
        if (keep !== null && storyText) applyTextAttrs(storyText, keep);
    }

    function moveToY(item, y1) {
        var gb = item.geometricBounds;
        item.move(undefined, [0, y1 - gb[0]]);
    }

    function overrideOrReuse(masterItem, page) {
        // 이미 오버라이드돼 있으면 그 항목 재사용 (중복 override 오류 방지)
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

    function applyGanji(doc) {
        var school = settings.ganji_school || "";
        var ranges = settings.ranges || [];
        if (!school && !ranges.length && !settings.issue_num) {
            writeLog("간지 기재: 설정 없음 — 건너뜀");
            return;
        }
        var page0 = doc.pages[0];
        var master = null;
        try { master = page0.appliedMaster; } catch (eM) {}
        if (!master || String(master.name).indexOf("간지") === -1) {
            try { master = doc.masterSpreads.itemByName("간지-마스터"); } catch (eM2) {}
        }
        if (!master || !master.isValid) {
            writeLog("[경고] 간지 마스터를 찾지 못함 — 간지 기재 생략");
            return;
        }

        var mSchool = null, mIssue = null, mRange = null, mDetail = null;
        var mtf = master.textFrames;
        for (var i = 0; i < mtf.length; i++) {
            var tf = mtf[i];
            var cs = frameCS(tf);
            var txt = "";
            try { txt = String(tf.contents); } catch (eT) {}
            if (cs === "챕터_숫자") mSchool = tf;
            else if (cs === "범위") mRange = tf;
            else if (cs === "범위_추가내용") mDetail = tf;
            else if (/^\s*\d+\s*$/.test(txt)) mIssue = tf;
        }
        var edited = [];
        if (mSchool && school) {
            setFrameText(doc, mSchool, school, "챕터_숫자");
            edited.push({ tf: mSchool, name: "간지 학교명" });
        } else if (!mSchool) {
            writeLog("[경고] 간지 학교명 프레임(챕터_숫자) 미발견");
        }
        var issueNum = String(parseInt(settings.issue_num, 10) || 1);
        if (mIssue) {
            try { mIssue.contents = issueNum; } catch (eIN) {}
            edited.push({ tf: mIssue, name: "간지 순번" });
        } else {
            writeLog("[경고] 간지 순번 프레임 미발견");
        }

        // 페이지1 상단 슬러그(y<0) — 범위/범위_추가내용
        var titles = [], details = [];
        for (var r = 0; r < ranges.length; r++) {
            if (ranges[r].title) titles.push(ranges[r].title);
            if (ranges[r].detail) details.push(ranges[r].detail);
        }
        var p0tf = page0.textFrames;
        for (var s2 = 0; s2 < p0tf.length; s2++) {
            var stf = p0tf[s2], gbS;
            try { gbS = stf.geometricBounds; } catch (eG) { continue; }
            if (gbS[0] >= 0) continue;
            var scs = frameCS(stf);
            if (scs === "범위") {
                setFrameText(doc, stf, titles.join(" / "), "범위");
                edited.push({ tf: stf, name: "슬러그 범위" });
            } else if (scs === "범위_추가내용") {
                setFrameText(doc, stf, details.join(" / "), "범위_추가내용");
                edited.push({ tf: stf, name: "슬러그 추가내용" });
            }
        }

        // 범위 프레임쌍 — 마스터 오버라이드 후 위치 이동, 여러 개면 아래로 복제
        var pairs = 0;
        if (mRange && mDetail && ranges.length) {
            var ovrRange = overrideOrReuse(mRange, page0);
            var ovrDetail = overrideOrReuse(mDetail, page0);
            moveToY(ovrRange, GANJI_RANGE_Y);
            moveToY(ovrDetail, GANJI_DETAIL_Y);
            setFrameText(doc, ovrRange, ranges[0].title || " ", "범위");
            setFrameText(doc, ovrDetail, ranges[0].detail || " ", "범위_추가내용");
            edited.push({ tf: ovrRange, name: "범위쌍1 범위" });
            edited.push({ tf: ovrDetail, name: "범위쌍1 추가내용" });
            pairs = 1;
            for (var k = 1; k < ranges.length; k++) {
                var dupR = ovrRange.duplicate();
                var dupD = ovrDetail.duplicate();
                moveToY(dupR, GANJI_RANGE_Y + GANJI_PAIR_STEP * k);
                moveToY(dupD, GANJI_DETAIL_Y + GANJI_PAIR_STEP * k);
                setFrameText(doc, dupR, ranges[k].title || " ", "범위");
                setFrameText(doc, dupD, ranges[k].detail || " ", "범위_추가내용");
                edited.push({ tf: dupR, name: "범위쌍" + (k + 1) + " 범위" });
                edited.push({ tf: dupD, name: "범위쌍" + (k + 1) + " 추가내용" });
                pairs++;
            }
        } else if (!mRange || !mDetail) {
            writeLog("[경고] 간지 범위/범위_추가내용 마스터 프레임 미발견");
        }

        // 기재 프레임 오버셋 게이트 — 넘치면 조용히 잘려 나간다
        var oversetNames = [];
        for (var ov = 0; ov < edited.length; ov++) {
            var isOver = false;
            try { isOver = edited[ov].tf.overflows; } catch (eOvf) {}
            if (isOver) oversetNames.push(edited[ov].name);
        }
        if (oversetNames.length) {
            writeLog("[경고] 간지 기재 프레임 오버셋: " + oversetNames.join(", "));
        }
        writeLog("간지 기재: " + school + " / 순번 " + issueNum +
                 " / 범위쌍 " + pairs + "개" +
                 (oversetNames.length ? " / 오버셋 " + oversetNames.length + "건" : ""));
    }

    // ───────────────────────────────────────────────────────────────
    // [헤더] 지문 머리말을 마더텅 지문번호로 교체 — "13강 | 1번"
    //   레이아웃은 [라벨칸] | [코드칸] 2단. 코드칸에는 소스의
    //   "고1 23년 9월 36번" 이 그대로 실려 오고, 라벨칸은 소스 마스터에
    //   있던 항목이라 결합본에서는 비어 있다(구형 소스) 또는 페이지
    //   항목으로 따라온다(신형 지문별 분석본 "외부지문").
    //   → 코드 프레임을 마커로 찾고, 같은 높이대에서 그보다 왼쪽에 있는
    //     프레임을 라벨로 본다. 페이지에 없으면 마스터에서 같은 조건으로
    //     찾아 오버라이드한다.
    // ───────────────────────────────────────────────────────────────

    function vOverlap(a, b) {
        return (a[0] < b[2] - 1) && (b[0] < a[2] - 1);
    }

    function rewriteHeader(page, labelText, codeText, tag) {
        var frames = [], i;
        try { frames = page.textFrames.everyItem().getElements(); }
        catch (eF) { return false; }

        // 1) 코드 프레임 — 내용이 마커 패턴인 짧은 프레임
        var codeTF = null;
        for (i = 0; i < frames.length; i++) {
            var c = "";
            try { c = String(frames[i].contents); } catch (eC) { continue; }
            if (c.length > 40) continue;
            if (MARKER_PAT.test(c)) { codeTF = frames[i]; break; }
        }
        if (!codeTF) {
            writeLog("[경고] 헤더 코드 프레임 미발견 (" + tag + ")");
            return false;
        }
        var codeGB;
        try { codeGB = codeTF.geometricBounds; } catch (eGB) { return false; }

        // 2) 라벨 프레임 — 같은 높이대에서 코드보다 왼쪽. 페이지 → 마스터 순
        var labelTF = null;
        for (i = 0; i < frames.length; i++) {
            if (frames[i] === codeTF) continue;
            var gb;
            try { gb = frames[i].geometricBounds; } catch (eG2) { continue; }
            if (!vOverlap(gb, codeGB)) continue;
            if (gb[1] >= codeGB[1]) continue;      // 코드보다 왼쪽만
            if (!labelTF) labelTF = frames[i];
        }
        if (!labelTF) {
            var mst = null;
            try { mst = page.appliedMaster; } catch (eM) {}
            if (mst && mst.isValid) {
                var mfs = [];
                try { mfs = mst.textFrames.everyItem().getElements(); } catch (eMF) {}
                for (i = 0; i < mfs.length; i++) {
                    var mgb;
                    try { mgb = mfs[i].geometricBounds; } catch (eG3) { continue; }
                    if (!vOverlap(mgb, codeGB)) continue;
                    if (mgb[1] >= codeGB[1]) continue;
                    try { labelTF = overrideOrReuse(mfs[i], page); } catch (eOv) {}
                    if (labelTF) break;
                }
            }
        }

        setFrameText(newDocRef, codeTF, codeText, null);
        if (labelTF) {
            setFrameText(newDocRef, labelTF, labelText, null);
        } else {
            writeLog("[경고] 헤더 라벨 프레임 미발견 (" + tag +
                     ") — 코드칸만 기재");
        }
        var over = false;
        try { over = codeTF.overflows || (labelTF && labelTF.overflows); }
        catch (eO) {}
        if (over) writeLog("[경고] 헤더 프레임 오버셋 (" + tag + ")");
        return true;
    }

    // ───────────────────────────────────────────────────────────────
    // [지오메트리] 좌표계 정규화 + 프레임 위치 복원
    //   문서 간 page.duplicate 는 콘텐츠 아이템을 페이지 기준으로 평행이동
    //   시킨다(실측: 왼쪽 페이지 +2mm 오른쪽·-1.33mm 위 — 2026-08-18 마더텅
    //   13강 결합본 vs 소스 PDF 좌표 대조). 복제 직후 소스 좌표와의 (dx,dy)를
    //   move 로 되돌린다. geometricBounds 는 문서별 rulerOrigin 기준이라
    //   캡처/복원 구간에는 양쪽 문서를 PAGE_ORIGIN + zeroPoint(0,0) 로 맞추고
    //   끝나면 원복한다(analysis_merge_v2 [스펙2]/한영2 사고와 같은 계열).
    // ───────────────────────────────────────────────────────────────

    var GEO_MAX_DRIFT_MM = 20;   // 이 이상은 좌표계 불일치 신호 → 이동 금지·경고

    var geoRep = { max_drift_before_mm: 0, max_residual_mm: 0,
                   oversized: 0, count_mismatch: 0 };

    // 결합본 참조 — 헬퍼(setFrameText 등)에서 스타일 조회에 쓴다
    var newDocRef = null;

    function round3(v) { return Math.round(v * 1000) / 1000; }

    function normalizeRuler(doc) {
        var prev = { origin: null, zero: null };
        try {
            prev.origin = doc.viewPreferences.rulerOrigin;
            if (prev.origin !== RulerOrigin.PAGE_ORIGIN) {
                doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
            } else {
                prev.origin = null;
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
        try { if (prev.zero !== null) doc.zeroPoint = prev.zero; } catch (eZr) {}
        try {
            if (prev.origin !== null) doc.viewPreferences.rulerOrigin = prev.origin;
        } catch (eOr) {}
    }

    // page.pageItems 는 라이브 컬렉션 — 이동으로 페이지를 벗어나면 인덱스가
    // 밀리므로 반드시 배열 스냅샷으로 잡는다.
    function snapItems(page) {
        try { return page.pageItems.everyItem().getElements(); } catch (eEv) {}
        var arr = [];
        try {
            var it = page.pageItems;
            for (var i = 0; i < it.length; i++) arr.push(it[i]);
        } catch (eP) {}
        return arr;
    }

    function collectGeo(page) {
        var arr = [], items = snapItems(page);
        for (var i = 0; i < items.length; i++) {
            var gb;
            try { gb = items[i].geometricBounds; } catch (eG) { gb = null; }
            arr.push(gb);
        }
        return arr;
    }

    function restoreGeo(newPage, srcGeo, srcLabel) {
        var items = snapItems(newPage);
        var n = Math.min(items.length, srcGeo.length);
        var maxBefore = 0, maxAfter = 0;
        if (items.length !== srcGeo.length) {
            geoRep.count_mismatch++;
            writeLog("[경고] 지오메트리 아이템 수 불일치 " + srcLabel + ": " +
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
                geoRep.oversized++;
                writeLog("[경고] 지오메트리 드리프트 과대 " + srcLabel +
                         " item" + i + " (dx=" + round3(dx) + ", dy=" +
                         round3(dy) + "mm > 상한 " + GEO_MAX_DRIFT_MM +
                         "mm) — 이동 생략");
                if (drift > maxAfter) maxAfter = drift;
                continue;
            }
            if (drift > 0.01) {
                try {
                    try { items[i].locked = false; } catch (eLk) {}
                    items[i].move(undefined, [dx, dy]);
                } catch (eMv) {
                    writeLog("[경고] 지오메트리 복원 실패 " + srcLabel +
                             " item" + i + ": " + eMv.message);
                }
            }
            var after;
            try { after = items[i].geometricBounds; } catch (eA) { continue; }
            var resid = Math.max(Math.abs(want[1] - after[1]),
                                 Math.abs(want[0] - after[0]));
            if (resid > maxAfter) maxAfter = resid;
        }
        if (maxBefore > geoRep.max_drift_before_mm) {
            geoRep.max_drift_before_mm = round3(maxBefore);
        }
        if (maxAfter > geoRep.max_residual_mm) {
            geoRep.max_residual_mm = round3(maxAfter);
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 스프레드 재편성 허용 — 내지 전부 allowPageShuffle = true
    //   소스 분석본의 잠긴(island) spread 가 그대로 복제되면 결과 문서의
    //   spread 도 "재편성 비허용"으로 남아, 이후 duplicate 가 새 스프레드를
    //   만들지 못하고 같은 스프레드에 계속 붙는다(→ 페이지가 2P 쌍으로
    //   나뉘지 않고 한 스프레드에 쭉 이어지고, 10페이지에서
    //   "스프레드의 페이지 수는 10 이하여야 합니다" 로 복제 실패).
    //   (analysis_merge / engines/final/indesign_stepper.py 와 동일 패턴)
    // ───────────────────────────────────────────────────────────────

    function allowShuffleAll(doc) {
        try { doc.documentPreferences.allowPageShuffle = true; } catch (eDPS) {}
        for (var s = 0; s < doc.spreads.length; s++) {
            try { doc.spreads[s].allowPageShuffle = true; } catch (eSh) {}
        }
    }

    // 복제 직전 가드 — 마지막 스프레드만 즉시 재편성 허용으로 풀어 둔다.
    function allowShuffleTail(doc) {
        try { doc.spreads.lastItem().allowPageShuffle = true; } catch (eSt) {}
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

        newDocRef = newDoc;

        // 내지 전부 스프레드 재편성 허용 — 복제 전 문서 기본값 보정
        allowShuffleAll(newDoc);

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

        // 좌표계 정규화 — 결합(복제+지오메트리 복원) 구간에만 PAGE_ORIGIN.
        // 소스 문서는 열 때마다 정규화하고(rulerPrevSrc), 끝나면 전부 원복.
        var rulerPrevNew = normalizeRuler(newDoc);
        var rulerPrevSrc = {};
        for (var uriN in docCache) {
            try { rulerPrevSrc[uriN] = normalizeRuler(docCache[uriN]); }
            catch (eNr) {}
        }

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
                // [지오메트리] 소스 좌표 캡처 → 복제 → 원위치 복원
                var srcGeo = collectGeo(matchedDoc.pages[p2]);
                try {
                    allowShuffleTail(newDoc);
                    matchedDoc.pages[p2].duplicate(
                        LocationOptions.AT_END, newDoc.pages.lastItem()
                    );
                    totalPages++;
                } catch (eDup) {
                    writeLog("[경고] " + code + " p" + p2 +
                             " 복제 실패: " + eDup.message);
                    continue;
                }
                try {
                    restoreGeo(newDoc.pages.lastItem(), srcGeo,
                               matchedName + " p" + (p2 + 1));
                } catch (eRg) {
                    writeLog("[경고] 지오메트리 복원 오류 p" + (p2 + 1) + ": " +
                             eRg.message);
                }
            }
            var grpEnd = newDoc.pages.length - 1;
            if (grpEnd >= grpStart) {
                codeRanges.push({ code: code, startIdx: grpStart, endIdx: grpEnd });
                // 헤더를 마더텅 지문번호로 교체 — 머리말은 그룹 첫 페이지에만
                if (P.header_label || P.header_code) {
                    try {
                        rewriteHeader(newDoc.pages[grpStart],
                                      P.header_label || "",
                                      P.header_code || "",
                                      code);
                    } catch (eHd) {
                        writeLog("[경고] 헤더 교체 실패 " + code + ": " +
                                 (eHd.message || eHd));
                    }
                }
                writeLog("  " + code + " [강" + lessonNum + " " + matchedSrc + "] ← " +
                         matchedName + " p" + (matchedRange.startIdx + 1) +
                         "..p" + (matchedRange.endIdx + 1) +
                         " (" + (matchedRange.endIdx - matchedRange.startIdx + 1) + "p)");
            }
        }

        // 좌표계 원복 — 이후 단계(rethread/저장)는 문서 원래 설정으로
        for (var uriR in rulerPrevSrc) {
            try { restoreRuler(docCache[uriR], rulerPrevSrc[uriR]); } catch (eRr) {}
        }
        restoreRuler(newDoc, rulerPrevNew);
        writeLog("지오메트리: 교정 전 최대 " + geoRep.max_drift_before_mm +
                 "mm → 잔여 " + geoRep.max_residual_mm + "mm" +
                 (geoRep.oversized ? " / 과대 드리프트 " + geoRep.oversized +
                                     "건(이동 생략)" : ""));

        for (var rgi = 0; rgi < codeRanges.length; rgi++) {
            try {
                rethreadGroup(newDoc, codeRanges[rgi].startIdx, codeRanges[rgi].endIdx);
            } catch (eRt) {
                writeLog("[경고] rethread " + codeRanges[rgi].code + ": " + eRt.message);
            }
        }

        try { cleanLabels(newDoc); } catch (eCl) {}

        // 간지(1페이지) 기재 — 학교/순번/범위
        try { applyGanji(newDoc); }
        catch (eGj) { writeLog("[경고] 간지 기재 실패: " + (eGj.message || eGj)); }

        // 내지 전부 스프레드 재편성 허용 — 복제된 분석본 spread 까지 모두 풀기
        try {
            allowShuffleAll(newDoc);
            writeLog("스프레드 재편성 허용 설정: " + newDoc.spreads.length + " spread");
        } catch (eShf) { writeLog("[경고] 재편성 허용 설정 실패: " + eShf.message); }

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
