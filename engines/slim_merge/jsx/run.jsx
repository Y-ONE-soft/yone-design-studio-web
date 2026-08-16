// [ENGINE TEMPLATE] 워크북 슬림 변환 JSX
//   수동 Slim_Ver.jsx(섹션 삭제) + Slim_Merge.jsx(반쪽 병합)
//   + Slim_Merge2.jsx(적층 병합) + 간지 스프레드 정렬을 하나로 통합.
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작 요약:
//   1) settings.output_indd (엔진이 미리 복사해 둔 사본) 를 창 없이 열기
//   2) '단원' 스타일 마커(파스트보드 숨김 프레임)로 섹션 경계 인식
//   3) 섹션별 액션 — delete / merge_half / merge_stack (뒤 섹션부터 처리)
//   4) 섹션 첫 페이지 마스터 좌/우 보정 (A↔B, C↔D)
//   5) 간지 스프레드 정렬 — 간지 블록이 (왼쪽,오른쪽) 2P 가 되도록 메모 삽입
//   6) 검증(오버셋/누락링크/섹션) → 저장 + 닫기 (사용자 문서 무접촉)
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

    // settings 로드 실패 시에도 job_dir 로그에 흔적을 남긴다 (부트스트랩
    // try-catch — 무로그 침묵 실패 방지, 2026-07-17 merge 계열 감사 패턴).
    var settings;
    try {
        settings = readJSON(SETTINGS_PATH);
    } catch (eBoot) {
        try {
            var _ef = new File(new File(SETTINGS_PATH).parent.fsName + "/slim_log.txt");
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
    // 설정 기본값
    // ───────────────────────────────────────────────────────────────
    var UNIT_NAME   = settings.unit_style_name || "단원";
    var UNIT_GROUP  = settings.unit_style_group || "마스터페이지";
    var DEL_LIST    = settings.delete_sections || [];
    var HALF_LIST   = settings.merge_half_sections || [];
    var STACK_LIST  = settings.merge_stack_sections || [];
    var STACK_DROP  = (settings.stack_drop_y === undefined)
                      ? 100 : settings.stack_drop_y;
    var STACK_GAP   = (settings.stack_gap === undefined)
                      ? 6.85 : settings.stack_gap;
    var PAIRS       = settings.master_pairs || [["A", "B"], ["C", "D"]];
    var PROTECT     = settings.protect_masters || ["M", "간지"];
    var FIX_DIV     = (settings.fix_divider_spreads === undefined)
                      ? true : !!settings.fix_divider_spreads;
    var MEMO_MASTER = settings.memo_master || "M";

    // ───────────────────────────────────────────────────────────────
    // 문서 열기 — 반드시 경로로 지정 (activeDocument 금지)
    // ───────────────────────────────────────────────────────────────
    var doc = null;
    try {
        var srcFile = new File(settings.output_indd);
        if (!srcFile.exists) {
            fail("대상 .indd 없음: " + settings.output_indd);
            writeLog("===== 완료 =====");
            return;
        }
        doc = app.open(srcFile, false);
    } catch (eOpen) {
        fail("문서 열기 실패: " + (eOpen.message || eOpen));
        writeLog("===== 완료 =====");
        return;
    }

    writeLog("슬림 변환 시작 — " + doc.name);
    writeLog("변환 전 페이지: " + doc.pages.length);

    var prevRuler = doc.viewPreferences.rulerOrigin;
    try { doc.adjustLayoutPreferences.enableAdjustLayout = false; } catch (eAdj) {}
    doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;

    // ───────────────────────────────────────────────────────────────
    // 유틸
    // ───────────────────────────────────────────────────────────────
    function norm(s) { return String(s).replace(/\s+/g, ""); }

    function inList(arr, v) {
        for (var i = 0; i < arr.length; i++) {
            if (norm(arr[i]) === v) return true;
        }
        return false;
    }

    function masterPrefix(page) {
        try {
            return page.appliedMaster ? String(page.appliedMaster.namePrefix) : "";
        } catch (e) { return ""; }
    }

    function isRight(page) {
        try { return page.side === PageSideOptions.RIGHT_HAND; }
        catch (e) { return false; }
    }

    function isProtected(page) {
        var mp = masterPrefix(page);
        if (mp === "") return true;
        for (var i = 0; i < PROTECT.length; i++) {
            if (PROTECT[i] === mp) return true;
        }
        return false;
    }

    function preview(tf) {
        var c = "";
        try { c = String(tf.contents); } catch (e) { return "<err>"; }
        c = c.replace(/[\r\n\t]/g, " ").replace(/^\s+/, "");
        return c.length > 50 ? c.substring(0, 50) + "~" : c;
    }

    // ───────────────────────────────────────────────────────────────
    // '단원' 스타일 + 섹션 경계
    // ───────────────────────────────────────────────────────────────
    function getUnitStyle() {
        var g = doc.characterStyleGroups.itemByName(UNIT_GROUP);
        if (g.isValid) {
            var s = g.characterStyles.itemByName(UNIT_NAME);
            if (s && s.isValid) return { style: s, type: "character" };
        }
        var s2 = doc.characterStyles.itemByName(UNIT_NAME);
        if (s2 && s2.isValid) return { style: s2, type: "character" };
        var s3 = doc.paragraphStyles.itemByName(UNIT_NAME);
        if (s3 && s3.isValid) return { style: s3, type: "paragraph" };
        return null;
    }

    var unitInfo = getUnitStyle();
    if (!unitInfo) {
        fail("'" + UNIT_NAME + "' 스타일을 찾을 수 없습니다.");
        try { doc.close(SaveOptions.NO); } catch (eC) {}
        writeLog("===== 완료 =====");
        return;
    }

    var markerFrameIds = {};

    function collectMarkers() {
        app.findTextPreferences = NothingEnum.nothing;
        app.changeTextPreferences = NothingEnum.nothing;
        if (unitInfo.type === "character") {
            app.findTextPreferences.appliedCharacterStyle = unitInfo.style;
        } else {
            app.findTextPreferences.appliedParagraphStyle = unitInfo.style;
        }
        var found = doc.findText();
        app.findTextPreferences = NothingEnum.nothing;
        app.changeTextPreferences = NothingEnum.nothing;

        var list = [], seen = {};
        for (var i = 0; i < found.length; i++) {
            var tf = null, pg = null;
            try { tf = found[i].parentTextFrames[0]; } catch (e) {}
            if (!tf) continue;
            try { pg = tf.parentPage; } catch (e) {}
            if (!pg) continue;
            markerFrameIds[tf.id] = true;
            var off = pg.documentOffset;
            if (seen[off]) continue;
            seen[off] = true;
            list.push({ off: off, label: norm(found[i].contents) });
        }
        list.sort(function (a, b) { return a.off - b.off; });
        return list;
    }

    // 같은 라벨 연속 마커 = 한 섹션
    function buildSections() {
        var markers = collectMarkers();
        var secs = [], i = 0;
        while (i < markers.length) {
            var label = markers[i].label;
            var start = markers[i].off;
            var j = i + 1;
            while (j < markers.length && markers[j].label === label) j++;
            var end = (j < markers.length) ? markers[j].off - 1
                                           : doc.pages.length - 1;
            secs.push({ label: label, start: start, end: end });
            i = j;
        }
        return secs;
    }

    var sections = buildSections();
    writeLog("섹션 " + sections.length + "개 인식");
    for (var si = 0; si < sections.length; si++) {
        writeLog("  " + sections[si].label + " p" + (sections[si].start + 1) +
                 "~p" + (sections[si].end + 1) +
                 " (" + (sections[si].end - sections[si].start + 1) + "p)");
    }

    // ───────────────────────────────────────────────────────────────
    // 프레임 헬퍼 — 인덱스 지정자 금지(getElements 로 실체 확보)
    // ───────────────────────────────────────────────────────────────
    function contentFrames(page) {
        var out = [], els = [];
        try { els = page.textFrames.everyItem().getElements(); } catch (e) {}
        for (var i = 0; i < els.length; i++) {
            if (markerFrameIds[els[i].id]) continue;
            out.push(els[i]);
        }
        return out;
    }

    function largestFrame(frames) {
        var best = null, maxA = -1;
        for (var i = 0; i < frames.length; i++) {
            var gb = frames[i].geometricBounds;
            var a = (gb[2] - gb[0]) * (gb[3] - gb[1]);
            if (a > maxA) { maxA = a; best = frames[i]; }
        }
        return best;
    }

    // 스레드 스토리 독립화 (Adobe SplitStory 방식 — duplicate 후 원본 remove).
    // nextTextFrame=null 방식은 뒤 프레임 텍스트를 앞 프레임 오버셋으로
    // 빨아들일 수 있어 쓰지 않는다.
    function splitStoriesInRange(start, end) {
        var seen = {}, stories = [];
        for (var p = start; p <= end; p++) {
            var frames = contentFrames(doc.pages[p]);
            for (var f = 0; f < frames.length; f++) {
                var st;
                try { st = frames[f].parentStory; } catch (e) { continue; }
                if (st.textContainers.length < 2) continue;
                if (seen[st.id]) continue;
                seen[st.id] = true;
                var outside = 0;
                for (var c0 = 0; c0 < st.textContainers.length; c0++) {
                    var pp = null;
                    try { pp = st.textContainers[c0].parentPage; } catch (e) {}
                    if (!pp) { outside++; continue; }
                    if (pp.documentOffset < start || pp.documentOffset > end) {
                        outside++;
                    }
                }
                if (outside > 0) {
                    writeLog("[경고] 스토리 " + st.id + " 컨테이너 " + outside +
                             "개가 섹션 범위 밖 — 해제 파급 확인 필요");
                }
                stories.push(st);
            }
        }
        var n = 0;
        for (var s = 0; s < stories.length; s++) {
            var st2 = stories[s], containers = [];
            for (var c = 0; c < st2.textContainers.length; c++) {
                containers.push(st2.textContainers[c]);
            }
            var dups = [];
            for (c = 0; c < containers.length; c++) {
                try { dups.push(containers[c].duplicate()); }
                catch (e) { writeLog("[경고] 프레임 복제 실패: " + e); }
            }
            for (c = containers.length - 1; c >= 0; c--) {
                try { containers[c].remove(); }
                catch (e) { writeLog("[경고] 원본 프레임 삭제 실패: " + e); }
            }
            for (var d = 0; d < dups.length; d++) {
                try {
                    if (dups[d].overflows) {
                        writeLog("[경고] 스레드 해제 후 오버셋: " + preview(dups[d]));
                    }
                } catch (e) {}
            }
            n += containers.length;
        }
        if (n) writeLog("  스레드 해제: " + n + "개 프레임 독립화");
    }

    // 페이지 개체 통째 이동 (host 프레임 기준 delta)
    function movePageContents(srcPage, dstPage, refFrame, targetBounds) {
        var items = [], srcItems = [];
        try { srcItems = srcPage.pageItems.everyItem().getElements(); }
        catch (e) {}
        for (var i = 0; i < srcItems.length; i++) {
            var isMarker = false;
            try { isMarker = !!markerFrameIds[srcItems[i].id]; } catch (e2) {}
            if (isMarker) {
                writeLog("[경고] 이동 대상 페이지에 단원 마커 존재 — 제외: p" +
                         srcPage.name);
                continue;
            }
            items.push(srcItems[i]);
        }
        for (i = 0; i < items.length; i++) {
            try { items[i].move(dstPage); }
            catch (e3) { writeLog("[경고] 개체 이동 실패: " + e3); }
        }
        var nb = refFrame.geometricBounds;
        var dx = targetBounds[1] - nb[1];
        var dy = targetBounds[0] - nb[0];
        if (dx !== 0 || dy !== 0) {
            for (i = 0; i < items.length; i++) {
                try { items[i].move(undefined, [dx, dy]); } catch (e4) {}
            }
        }
        try { refFrame.geometricBounds = targetBounds; }
        catch (e5) { writeLog("[경고] 프레임 배치 실패: " + e5); }
    }

    function growUntilFits(tf, maxBottom) {
        var guard = 0;
        while (guard < 60) {
            var ovf = false;
            try { ovf = tf.overflows; } catch (e) { break; }
            if (!ovf) return true;
            var gb = tf.geometricBounds;
            if (gb[2] >= maxBottom) return false;
            gb[2] = Math.min(gb[2] + 10, maxBottom);
            try { tf.geometricBounds = gb; } catch (e2) { return false; }
            guard++;
        }
        return false;
    }

    function removeEmptied(pages) {
        pages.sort(function (a, b) {
            return b.documentOffset - a.documentOffset;
        });
        for (var i = 0; i < pages.length; i++) {
            var pg = pages[i];
            if (!pg.isValid) continue;
            var left = 0;
            try { left = pg.pageItems.length; } catch (e) {}
            if (left > 0) {
                writeLog("[경고] p" + pg.name + " 잔존 개체 " + left +
                         "개 — 삭제 보류");
                continue;
            }
            var nm = pg.name;
            try { pg.remove(); writeLog("  페이지 삭제 p" + nm); }
            catch (e2) { writeLog("[경고] p" + nm + " 삭제 실패: " + e2); }
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 액션 3종
    // ───────────────────────────────────────────────────────────────
    function deleteSection(sec) {
        var end = sec.end;
        while (end > sec.start && isProtected(doc.pages[end])) {
            writeLog("  [가드] p" + doc.pages[end].name + " (마스터=" +
                     (masterPrefix(doc.pages[end]) || "[없음]") +
                     ") 삭제 범위 제외");
            end--;
        }
        writeLog("[삭제] " + sec.label + " p" + (sec.start + 1) + "~p" +
                 (end + 1) + " (" + (end - sec.start + 1) + "p)");
        for (var p = end; p >= sec.start; p--) {
            var pg = doc.pages[p];
            var fr = contentFrames(pg);
            writeLog("  - p" + pg.name + " : " +
                     (fr.length ? preview(fr[0]) : "(빈 페이지)"));
            try { pg.remove(); }
            catch (e) { writeLog("[경고] p" + pg.name + " 삭제 실패: " + e); }
        }
    }

    // 전체높이 프레임 1개짜리 섹션: 2p → 1p (상단 절반 + 하단 절반)
    function mergeHalf(sec) {
        writeLog("[병합-반쪽] " + sec.label + " p" + (sec.start + 1) +
                 "~p" + (sec.end + 1));
        splitStoriesInRange(sec.start, sec.end);
        var removed = [];
        for (var i = sec.start; i + 1 <= sec.end; i += 2) {
            var host = doc.pages[i], src = doc.pages[i + 1];
            var hostFrame = largestFrame(contentFrames(host));
            var srcFrame = largestFrame(contentFrames(src));
            if (!hostFrame || !srcFrame) {
                writeLog("[경고] p" + host.name + "/p" + src.name +
                         " 기준 프레임 없음 — 병합 스킵");
                continue;
            }
            var hb = hostFrame.geometricBounds.slice(0);
            var splitY = (hb[0] + hb[2]) / 2;
            hostFrame.geometricBounds = [hb[0], hb[1], splitY, hb[3]];
            if (hostFrame.overflows) {
                writeLog("[경고] p" + host.name +
                         " 상단 절반 오버셋 — 내용 확인 필요: " +
                         preview(hostFrame));
            }
            movePageContents(src, host, srcFrame,
                             [splitY, hb[1], hb[2], hb[3]]);
            if (srcFrame.overflows) {
                writeLog("[경고] p" + host.name +
                         " 하단 절반 오버셋 — 내용 확인 필요: " +
                         preview(srcFrame));
            }
            removed.push(src);
            writeLog("  p" + host.name + " ← p" + src.name +
                     " (splitY=" + splitY.toFixed(2) + ")");
        }
        removeEmptied(removed);
    }

    // 상단(문제)+하단(부가문제) 2프레임 섹션: 하단 삭제 후 적층, 2p → 1p
    function mergeStack(sec) {
        writeLog("[병합-적층] " + sec.label + " p" + (sec.start + 1) +
                 "~p" + (sec.end + 1));
        splitStoriesInRange(sec.start, sec.end);

        var dropped = 0;
        for (var p = sec.start; p <= sec.end; p++) {
            var frames = contentFrames(doc.pages[p]);
            if (frames.length < 2) continue;
            for (var f = frames.length - 1; f >= 0; f--) {
                var gb = frames[f].geometricBounds;
                if (gb[0] > STACK_DROP) {
                    writeLog("  하단 프레임 삭제 p" + doc.pages[p].name + ": " +
                             preview(frames[f]));
                    try { frames[f].remove(); dropped++; }
                    catch (e) { writeLog("[경고] 하단 프레임 삭제 실패: " + e); }
                }
            }
        }
        writeLog("  하단(부가문제) 프레임 " + dropped + "개 삭제");

        var removed = [];
        for (var i = sec.start; i + 1 <= sec.end; i += 2) {
            var host = doc.pages[i], src = doc.pages[i + 1];
            var hostFrame = largestFrame(contentFrames(host));
            var srcFrame = largestFrame(contentFrames(src));
            if (!hostFrame || !srcFrame) {
                writeLog("[경고] p" + host.name + "/p" + src.name +
                         " 기준 프레임 없음 — 병합 스킵");
                continue;
            }
            var hb = hostFrame.geometricBounds;
            var sb = srcFrame.geometricBounds;
            var top = hb[2] + STACK_GAP;
            var target = [top, hb[1], top + (sb[2] - sb[0]), hb[3]];
            movePageContents(src, host, srcFrame, target);
            if (!growUntilFits(srcFrame, top + 400)) {
                writeLog("[경고] p" + host.name +
                         " 적층 프레임 오버셋 해소 실패: " + preview(srcFrame));
            }
            removed.push(src);
            writeLog("  p" + host.name + " ← p" + src.name +
                     " (top=" + top.toFixed(2) + ")");
        }
        removeEmptied(removed);
    }

    // ───────────────────────────────────────────────────────────────
    // 실행 — 뒤 섹션부터 (앞 섹션 오프셋 + 좌우 파리티 보존)
    // ───────────────────────────────────────────────────────────────
    var actionCount = 0;
    sections.sort(function (a, b) { return b.start - a.start; });
    for (var s = 0; s < sections.length; s++) {
        var sec = sections[s];
        try {
            if (inList(DEL_LIST, sec.label))        { deleteSection(sec); actionCount++; }
            else if (inList(HALF_LIST, sec.label))  { mergeHalf(sec);     actionCount++; }
            else if (inList(STACK_LIST, sec.label)) { mergeStack(sec);    actionCount++; }
        } catch (eAct) {
            fail("섹션 처리 실패 (" + sec.label + "): " + (eAct.message || eAct));
        }
    }
    writeLog("처리 섹션: " + actionCount + "개");

    // ───────────────────────────────────────────────────────────────
    // 섹션 첫 페이지 마스터 좌/우 보정 (A↔B, C↔D)
    // ───────────────────────────────────────────────────────────────
    function masterByPrefix(pfx) {
        for (var i = 0; i < doc.masterSpreads.length; i++) {
            if (String(doc.masterSpreads[i].namePrefix) === pfx) {
                return doc.masterSpreads[i];
            }
        }
        return null;
    }

    markerFrameIds = {};
    var after = buildSections();
    var fixedMasters = 0;
    for (var a = 0; a < after.length; a++) {
        var pg2 = doc.pages[after[a].start];
        var pfx = masterPrefix(pg2);
        var right = isRight(pg2);
        var want = null;
        for (var mp = 0; mp < PAIRS.length; mp++) {
            var L = PAIRS[mp][0], R = PAIRS[mp][1];
            if (pfx === L && right) want = R;
            if (pfx === R && !right) want = L;
        }
        if (want) {
            var ms = masterByPrefix(want);
            if (ms) {
                try {
                    pg2.appliedMaster = ms;
                    fixedMasters++;
                    writeLog("마스터 보정 p" + pg2.name + " " + after[a].label +
                             " : " + pfx + " → " + want +
                             (right ? " (오른쪽 시작)" : " (왼쪽 시작)"));
                } catch (eM) {
                    writeLog("[경고] 마스터 적용 실패 p" + pg2.name + ": " + eM);
                }
            } else {
                writeLog("[경고] 마스터 " + want + " 없음 — p" + pg2.name + " 미보정");
            }
        }
    }
    writeLog("마스터 보정: " + fixedMasters + "건");

    // ───────────────────────────────────────────────────────────────
    // 단원 마커 텍스트 교체 (예: '어법 선택' → '어법 수정')
    //
    // 마커는 파스트보드 숨김 프레임이자 마스터 러닝헤더 텍스트변수의 소스라,
    // 이 텍스트를 바꾸면 섹션 헤더 표기가 따라 바뀐다. 문자 스타일을 조건에
    // 걸어 본문의 같은 문구는 건드리지 않는다.
    // ───────────────────────────────────────────────────────────────
    function renameMarkers(map) {
        var total = 0;
        for (var from in map) {
            if (!map.hasOwnProperty(from)) continue;
            var to = map[from];
            if (!to || to === from) continue;
            try {
                app.findGrepPreferences = NothingEnum.nothing;
                app.changeGrepPreferences = NothingEnum.nothing;
                app.findGrepPreferences.findWhat = from;
                if (unitInfo.type === "character") {
                    app.findGrepPreferences.appliedCharacterStyle = unitInfo.style;
                } else {
                    app.findGrepPreferences.appliedParagraphStyle = unitInfo.style;
                }
                app.changeGrepPreferences.changeTo = to;
                var hits = doc.changeGrep();
                var n = hits ? hits.length : 0;
                total += n;
                writeLog("마커 교체: '" + from + "' → '" + to + "' (" + n + "건)");
                if (n === 0) {
                    writeLog("[경고] 마커 '" + from + "' 미발견 — 교체 없음");
                }
            } catch (eR) {
                writeLog("[경고] 마커 교체 실패 (" + from + "): " + eR);
            }
            app.findGrepPreferences = NothingEnum.nothing;
            app.changeGrepPreferences = NothingEnum.nothing;
        }
        return total;
    }

    var RENAME = settings.rename_markers || null;
    if (RENAME) {
        var renamed = renameMarkers(RENAME);
        writeLog("마커 교체 합계: " + renamed + "건");
    }

    // ───────────────────────────────────────────────────────────────
    // 간지 스프레드 정렬 (메모 페이지 삽입)
    //
    // 간지 블록 = 마스터가 [없음]인 페이지의 연속 런.
    //   왼쪽 = 스프레드 전체를 덮는 배경, 오른쪽 = 단원 제목(흰 글자)
    // 앞 섹션이 왼쪽에서 끝나면 블록이 한 칸 밀려 배경이 pasteboard로
    // 나가고 제목이 흰 배경에 얹힌다 → 블록 앞에 메모 페이지 삽입.
    // ───────────────────────────────────────────────────────────────
    function noMasterRuns() {
        var runs = [], cur = null;
        for (var i = 0; i < doc.pages.length; i++) {
            if (masterPrefix(doc.pages[i]) === "") {
                if (cur === null) cur = { start: i, end: i };
                else cur.end = i;
            } else if (cur !== null) { runs.push(cur); cur = null; }
        }
        if (cur !== null) runs.push(cur);
        return runs;
    }

    // 간지 블록만 대상 — 런의 마지막 페이지에 단원 제목 프레임이 있어야 한다.
    // 판권(크레딧) 페이지도 [없음] 마스터지만 텍스트 프레임이 0개이고,
    // **판권은 왼쪽이 정상**(책은 오른쪽에서 시작해 왼쪽에서 끝난다)이라
    // 이 필터가 없으면 판권 앞에 메모를 끼워 파리티를 되레 깨뜨린다.
    function isDividerRun(run) {
        try { return doc.pages[run.end].textFrames.length > 0; }
        catch (e) { return false; }
    }

    function fixDividerSpreads() {
        var memoMaster = masterByPrefix(MEMO_MASTER);
        if (!memoMaster) {
            writeLog("[경고] 메모 마스터 '" + MEMO_MASTER +
                     "' 없음 — 간지 정렬 생략");
            return 0;
        }
        var inserted = 0, guard = 0;
        while (guard++ < 50) {
            var runs = noMasterRuns();
            var target = -1;
            for (var r = 0; r < runs.length; r++) {
                if (!isDividerRun(runs[r])) { continue; }   // 판권 등 제외
                if (!isRight(doc.pages[runs[r].end])) { target = r; break; }
            }
            if (target < 0) break;

            var run = runs[target];
            if (run.start === 0) {
                writeLog("[경고] 문서 첫 블록은 보정 대상 아님 — 중단");
                break;
            }
            var refPage = doc.pages[run.start].getElements()[0];
            var refName = refPage.name;
            var prevRef = doc.pages[run.start - 1].getElements()[0];
            var newPage;
            try {
                // pages.add(BEFORE, page)는 스프레드 단위로 삽입돼 목표보다
                // 한 칸 앞(콘텐츠 페이지 사이)에 끼어든다 — 끝에 추가 후
                // move(BEFORE, ref)가 페이지 단위로 정확하다.
                newPage = doc.pages.add(LocationOptions.AT_END);
                newPage.appliedMaster = memoMaster;
                newPage.move(LocationOptions.BEFORE, refPage);
            } catch (eIns) {
                fail("메모 페이지 삽입 실패 (간지 p" + refName + " 앞): " +
                     (eIns.message || eIns));
                break;
            }
            // 인접성 검증 — 앞=콘텐츠 마지막, 뒤=간지 블록 첫 페이지
            var off = newPage.documentOffset;
            var okPos = (off > 0) &&
                        (doc.pages[off - 1].id === prevRef.id) &&
                        (off + 1 < doc.pages.length) &&
                        (doc.pages[off + 1].id === refPage.id);
            if (!okPos) {
                fail("메모 페이지가 잘못된 위치에 삽입됨 — 되돌리고 중단 (off=" +
                     off + ", 기대=" + run.start + ")");
                try { newPage.remove(); } catch (eR) {}
                break;
            }
            inserted++;
            writeLog("간지 정렬: 메모 페이지 p" + newPage.name + " 삽입 (" +
                     (isRight(newPage) ? "오른쪽" : "왼쪽") + ", 뒤 간지 p" +
                     refPage.name + ")");
        }
        return inserted;
    }

    if (FIX_DIV) {
        var nIns = fixDividerSpreads();
        writeLog("간지 정렬: 메모 페이지 " + nIns + "장 삽입");
        var runsAfter = noMasterRuns();
        var bad = 0, nDiv = 0;
        for (var ra = 0; ra < runsAfter.length; ra++) {
            if (!isDividerRun(runsAfter[ra])) continue;
            nDiv++;
            if (!isRight(doc.pages[runsAfter[ra].end])) bad++;
        }
        if (bad > 0) writeLog("[경고] 정렬 후에도 어긋난 간지 블록 " + bad + "건");
        else writeLog("간지 블록 " + nDiv + "개 전부 (왼쪽,오른쪽) 확인");
    }

    // ───────────────────────────────────────────────────────────────
    // 검증
    // ───────────────────────────────────────────────────────────────
    var overset = 0;
    for (var st = 0; st < doc.stories.length; st++) {
        try { if (doc.stories[st].overflows) overset++; } catch (e) {}
    }
    writeLog("오버셋 스토리: " + overset + "건");

    var missLink = 0;
    try {
        for (var lk = 0; lk < doc.links.length; lk++) {
            if (doc.links[lk].status === LinkStatus.LINK_MISSING) missLink++;
        }
    } catch (e) {}
    writeLog("누락 링크: " + missLink + "건");

    writeLog("변환 후 페이지: " + doc.pages.length);

    markerFrameIds = {};
    var fin = buildSections();
    writeLog("최종 섹션 " + fin.length + "개");
    for (var fi = 0; fi < fin.length; fi++) {
        writeLog("  " + fin[fi].label + " p" + (fin[fi].start + 1) + "~p" +
                 (fin[fi].end + 1) + " (" +
                 (fin[fi].end - fin[fi].start + 1) + "p) master=" +
                 (masterPrefix(doc.pages[fin[fi].start]) || "[없음]"));
    }
    writeLog("병합 그룹: " + actionCount + "개");

    // ───────────────────────────────────────────────────────────────
    try { doc.viewPreferences.rulerOrigin = prevRuler; } catch (eRu) {}
    try {
        doc.save();
        writeLog("저장: " + doc.fullName.fsName);
    } catch (eSave) {
        fail("저장 실패: " + (eSave.message || eSave));
    }
    try { doc.close(SaveOptions.NO); } catch (eCl) {}

    writeLog("===== 완료 =====");
})();
