// SlimBuild.jsx  [ENGINE TEMPLATE]
// 워크북 풀버전(.indd) → 슬림버전 원샷 변환
//   Slim_Ver.jsx(섹션 삭제) + Slim_Merge.jsx(본문 O/X 반쪽 병합)
//   + Slim_Merge2.jsx(문장 배열 적층 병합)을 하나로 통합 + 검증 내장.
//
// 실행 방식 2가지
//   (A) 자동화: __SETTINGS_PATH__ 를 실제 JSON 경로로 치환한 사본을 실행
//   (B) 수동:   InDesign Scripts 패널에서 직접 실행 → 대상 문서 확인 후 진행
//
// 안전 규칙
//   - 문서는 항상 fullName(정확한 경로)로 특정. app.activeDocument 무단 사용 금지.
//   - 자동화 모드는 미리 복사해 둔 출력본을 열어 in-place 수정 후 save (원본 무접촉).
//   - 스레드 해제는 Adobe SplitStory 방식(duplicate → remove). nextTextFrame=null 금지.

#target "indesign"

(function () {

    // ─────────────────────────────────────────────────────────────
    // 기본 설정 (settings JSON 으로 덮어쓸 수 있음)
    // ─────────────────────────────────────────────────────────────
    var CFG = {
        doc_path: "",                 // 비면 수동 모드
        save: true,
        unit_style_name: "단원",
        unit_style_group: "마스터페이지",

        // 통째로 삭제할 섹션 (공백 무시 비교)
        delete_sections: ["어휘 선택 2", "본문 정리", "내용 종합",
                          "어법 O/X", "빈칸 어법"],

        // 전체높이 프레임 1개짜리 섹션: 2p → 1p (상단 절반 + 하단 절반)
        merge_half_sections: ["본문 O/X"],

        // 상단(문제) + 하단(부가문제) 2프레임 섹션:
        // 하단 프레임 삭제 후 다음 페이지 상단 프레임을 적층 → 2p → 1p
        merge_stack_sections: ["문장 배열"],
        stack_drop_y: 100,            // 이 y 아래에서 시작하는 프레임 = 삭제 대상
        stack_gap: 6.85,              // host 프레임 하단 ~ 적층 프레임 상단 간격

        // 섹션 첫 페이지가 오른쪽으로 밀렸을 때 헤더가 있는 마스터로 교체
        master_pairs: [["A", "B"], ["C", "D"]],

        // 삭제 범위에서 제외할 마스터 (간지/백지)
        protect_masters: ["M", "간지"],

        // 간지 스프레드 정렬 — 간지 블록([없음] 마스터 연속 런)의 마지막 페이지가
        // 왼쪽으로 밀리면 그 앞에 메모 페이지를 끼워 (왼쪽,오른쪽) 2P 구성을 복원
        fix_divider_spreads: true,
        memo_master: "M",

        // true 면 삭제/병합/파리티 보정을 건너뛰고 간지 정렬만 수행 (증분 보정용)
        skip_slim: false,

        log_path: ""
    };

    var SETTINGS_PATH = "__SETTINGS_PATH__";

    // ─────────────────────────────────────────────────────────────
    // 로그
    // ─────────────────────────────────────────────────────────────
    var LOG = [];
    var logFile = null;

    function flushLog() {
        if (!logFile) return;
        try {
            logFile.open("w");
            logFile.write(LOG.join("\n") + "\n");
            logFile.close();
        } catch (e) {}
    }

    function log(s) {
        LOG.push(s);
        if (LOG.length % 10 === 0) flushLog();
    }

    function fail(msg) {
        log("[오류] " + msg);
        flushLog();
        throw new Error(msg);
    }

    // ─────────────────────────────────────────────────────────────
    // settings 로드
    // ─────────────────────────────────────────────────────────────
    if (SETTINGS_PATH.indexOf("__SETTINGS") !== 0) {
        var sf = new File(SETTINGS_PATH);
        if (sf.exists) {
            sf.encoding = "UTF-8";
            sf.open("r");
            var raw = sf.read();
            sf.close();
            var user = eval("(" + raw + ")");
            for (var k in user) { CFG[k] = user[k]; }
        }
    }

    if (CFG.log_path) {
        logFile = new File(CFG.log_path);
        logFile.lineFeed = "Unix";
        logFile.encoding = "UTF-8";
    }
    log("===== SlimBuild 시작 =====");
    flushLog();

    // ─────────────────────────────────────────────────────────────
    // 대상 문서 확보 (경로 우선, 없으면 수동 확인)
    // ─────────────────────────────────────────────────────────────
    var doc = null;
    if (CFG.doc_path) {
        var f = new File(CFG.doc_path);
        if (!f.exists) fail("문서 없음: " + CFG.doc_path);
        doc = app.open(f, false);            // 이미 열려 있으면 그 참조 반환
    } else {
        if (app.documents.length === 0) fail("문서를 열어주세요.");
        var d0 = app.documents[0];
        var ok = confirm("아래 문서를 슬림버전으로 변환합니다.\n\n" +
                         d0.fullName.fsName + "\n\n계속할까요?");
        if (!ok) { log("사용자 취소"); flushLog(); return; }
        doc = d0;
    }
    log("[문서] " + doc.fullName.fsName);
    log("[변환 전] pages=" + doc.pages.length);

    // 레이아웃 자동조정 OFF + 눈금자 원점 = 페이지 (좌우 파리티 무관 좌표)
    var prevRuler = doc.viewPreferences.rulerOrigin;
    try { doc.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e) {}
    doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;

    // ─────────────────────────────────────────────────────────────
    // 유틸
    // ─────────────────────────────────────────────────────────────
    function norm(s) { return String(s).replace(/\s+/g, ""); }

    function inList(arr, v) {
        for (var i = 0; i < arr.length; i++) if (norm(arr[i]) === v) return true;
        return false;
    }

    function masterPrefix(page) {
        try {
            return page.appliedMaster ? page.appliedMaster.namePrefix : "";
        } catch (e) { return ""; }
    }

    function isProtected(page) {
        var mp = masterPrefix(page);
        if (mp === "") return true;                 // [없음] = 간지/백지
        for (var i = 0; i < CFG.protect_masters.length; i++) {
            if (CFG.protect_masters[i] === mp) return true;
        }
        return false;
    }

    function preview(tf) {
        var c = "";
        try { c = String(tf.contents); } catch (e) { return "<err>"; }
        c = c.replace(/[\r\n\t]/g, " ").replace(/^\s+/, "");
        return c.length > 50 ? c.substring(0, 50) + "~" : c;
    }

    // ─────────────────────────────────────────────────────────────
    // "단원" 스타일 + 마커 수집
    // ─────────────────────────────────────────────────────────────
    function getUnitStyle() {
        var g = doc.characterStyleGroups.itemByName(CFG.unit_style_group);
        if (g.isValid) {
            var s = g.characterStyles.itemByName(CFG.unit_style_name);
            if (s && s.isValid) return { style: s, type: "character" };
        }
        var s2 = doc.characterStyles.itemByName(CFG.unit_style_name);
        if (s2 && s2.isValid) return { style: s2, type: "character" };
        var s3 = doc.paragraphStyles.itemByName(CFG.unit_style_name);
        if (s3 && s3.isValid) return { style: s3, type: "paragraph" };
        return null;
    }

    var unitInfo = getUnitStyle();
    if (!unitInfo) fail("'" + CFG.unit_style_name + "' 스타일을 찾을 수 없습니다.");

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

        var list = [];
        var seen = {};
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
            list.push({ off: off, label: norm(found[i].contents),
                        raw: String(found[i].contents) });
        }
        list.sort(function (a, b) { return a.off - b.off; });
        return list;
    }

    // 같은 라벨 연속 마커 = 한 섹션
    function buildSections() {
        var markers = collectMarkers();
        var secs = [];
        var i = 0;
        while (i < markers.length) {
            var label = markers[i].label;
            var start = markers[i].off;
            var j = i + 1;
            while (j < markers.length && markers[j].label === label) j++;
            var end = (j < markers.length) ? markers[j].off - 1
                                           : doc.pages.length - 1;
            secs.push({ label: label, raw: markers[i].raw,
                        start: start, end: end });
            i = j;
        }
        return secs;
    }

    var sections = buildSections();
    log("[섹션 " + sections.length + "개]");
    for (var si = 0; si < sections.length; si++) {
        log("  " + sections[si].label + "  p" +
            (sections[si].start + 1) + "~p" + (sections[si].end + 1) +
            " (" + (sections[si].end - sections[si].start + 1) + "p)");
    }

    // ─────────────────────────────────────────────────────────────
    // 콘텐츠 프레임 (마커 프레임 제외)
    // ─────────────────────────────────────────────────────────────
    // 인덱스 지정자(page.textFrames[i])는 컬렉션 변경 시 다른 프레임을 가리키게
    // 되므로 반드시 getElements()로 실체 참조를 확보한다.
    function contentFrames(page) {
        var out = [];
        var els = [];
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

    // ─────────────────────────────────────────────────────────────
    // 스레드 스토리 독립화 (Adobe SplitStory 방식)
    // ─────────────────────────────────────────────────────────────
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
                // 섹션 밖까지 이어지는 스토리는 해제 시 파급 범위가 넓다 — 고지
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
                    log("[경고] 스토리 " + st.id + " 컨테이너 " + outside +
                        "개가 섹션 범위 밖 — 해제 파급 확인 필요");
                }
                stories.push(st);
            }
        }
        var splitCount = 0;
        for (var s = 0; s < stories.length; s++) {
            var st2 = stories[s];
            var containers = [];
            for (var c = 0; c < st2.textContainers.length; c++) {
                containers.push(st2.textContainers[c]);
            }
            var dups = [];
            for (c = 0; c < containers.length; c++) {
                try { dups.push(containers[c].duplicate()); }
                catch (e) { log("[경고] 프레임 복제 실패: " + e.message); }
            }
            for (c = containers.length - 1; c >= 0; c--) {
                try { containers[c].remove(); }
                catch (e) { log("[경고] 원본 프레임 삭제 실패: " + e.message); }
            }
            // 복제본 오버셋 점검
            for (var d = 0; d < dups.length; d++) {
                try {
                    if (dups[d].overflows) {
                        log("[경고] 스레드 해제 후 오버셋: " + preview(dups[d]));
                    }
                } catch (e) {}
            }
            splitCount += containers.length;
        }
        if (splitCount) log("  스레드 해제: " + splitCount + "개 프레임 독립화");
    }

    // ─────────────────────────────────────────────────────────────
    // 페이지 개체 통째 이동 (host 프레임 기준 delta)
    // ─────────────────────────────────────────────────────────────
    function movePageContents(srcPage, dstPage, refFrame, targetBounds) {
        var items = [];
        var srcItems = [];
        try { srcItems = srcPage.pageItems.everyItem().getElements(); }
        catch (e) {}
        for (var i = 0; i < srcItems.length; i++) {
            var it = srcItems[i];
            var isMarker = false;
            try { isMarker = !!markerFrameIds[it.id]; } catch (e) {}
            if (isMarker) {
                log("[경고] 이동 대상 페이지에 단원 마커 존재 — 제외: p" +
                    srcPage.name);
                continue;
            }
            items.push(it);
        }
        for (i = 0; i < items.length; i++) {
            try { items[i].move(dstPage); }
            catch (e) { log("[경고] 개체 이동 실패: " + e.message); }
        }
        var nb = refFrame.geometricBounds;
        var dx = targetBounds[1] - nb[1];
        var dy = targetBounds[0] - nb[0];
        if (dx !== 0 || dy !== 0) {
            for (i = 0; i < items.length; i++) {
                try { items[i].move(undefined, [dx, dy]); } catch (e) {}
            }
        }
        try { refFrame.geometricBounds = targetBounds; }
        catch (e) { log("[경고] 프레임 배치 실패: " + e.message); }
        return items;
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
            try { tf.geometricBounds = gb; } catch (e) { return false; }
            guard++;
        }
        return false;
    }

    // ─────────────────────────────────────────────────────────────
    // 병합: 반쪽(본문 O/X)
    // ─────────────────────────────────────────────────────────────
    function mergeHalf(sec) {
        log("[병합-반쪽] " + sec.label + " p" + (sec.start + 1) +
            "~p" + (sec.end + 1));
        splitStoriesInRange(sec.start, sec.end);

        var removed = [];
        for (var i = sec.start; i + 1 <= sec.end; i += 2) {
            var host = doc.pages[i], src = doc.pages[i + 1];
            var hostFrame = largestFrame(contentFrames(host));
            var srcFrame = largestFrame(contentFrames(src));
            if (!hostFrame || !srcFrame) {
                log("[경고] p" + host.name + "/p" + src.name +
                    " 기준 프레임 없음 — 병합 스킵");
                continue;
            }
            var hb = hostFrame.geometricBounds.slice(0);
            var splitY = (hb[0] + hb[2]) / 2;

            hostFrame.geometricBounds = [hb[0], hb[1], splitY, hb[3]];
            if (hostFrame.overflows) {
                log("[경고] p" + host.name + " 상단 절반 오버셋 — 내용 확인 필요: " +
                    preview(hostFrame));
            }
            movePageContents(src, host, srcFrame,
                             [splitY, hb[1], hb[2], hb[3]]);
            if (srcFrame.overflows) {
                log("[경고] p" + host.name + " 하단 절반 오버셋 — 내용 확인 필요: " +
                    preview(srcFrame));
            }
            removed.push(src);
            log("  p" + host.name + " ← p" + src.name +
                " (splitY=" + splitY.toFixed(2) + ")");
        }
        removeEmptied(removed);
    }

    // ─────────────────────────────────────────────────────────────
    // 병합: 적층(문장 배열) — 하단 부가문제 프레임 제거 후 적층
    // ─────────────────────────────────────────────────────────────
    function mergeStack(sec) {
        log("[병합-적층] " + sec.label + " p" + (sec.start + 1) +
            "~p" + (sec.end + 1));
        splitStoriesInRange(sec.start, sec.end);

        // 1) 하단 프레임 삭제
        var dropped = 0;
        for (var p = sec.start; p <= sec.end; p++) {
            var frames = contentFrames(doc.pages[p]);
            if (frames.length < 2) continue;
            for (var f = frames.length - 1; f >= 0; f--) {
                var gb = frames[f].geometricBounds;
                if (gb[0] > CFG.stack_drop_y) {
                    log("  하단 프레임 삭제 p" + doc.pages[p].name + ": " +
                        preview(frames[f]));
                    try { frames[f].remove(); dropped++; } catch (e) {
                        log("[경고] 하단 프레임 삭제 실패: " + e.message);
                    }
                }
            }
        }
        log("  하단(부가문제) 프레임 " + dropped + "개 삭제");

        // 2) 적층 병합
        var removed = [];
        for (var i = sec.start; i + 1 <= sec.end; i += 2) {
            var host = doc.pages[i], src = doc.pages[i + 1];
            var hostFrame = largestFrame(contentFrames(host));
            var srcFrame = largestFrame(contentFrames(src));
            if (!hostFrame || !srcFrame) {
                log("[경고] p" + host.name + "/p" + src.name +
                    " 기준 프레임 없음 — 병합 스킵");
                continue;
            }
            var hb = hostFrame.geometricBounds;
            var sb = srcFrame.geometricBounds;
            var top = hb[2] + CFG.stack_gap;
            var target = [top, hb[1], top + (sb[2] - sb[0]), hb[3]];

            movePageContents(src, host, srcFrame, target);
            if (!growUntilFits(srcFrame, top + 400)) {
                log("[경고] p" + host.name + " 적층 프레임 오버셋 해소 실패: " +
                    preview(srcFrame));
            }
            removed.push(src);
            log("  p" + host.name + " ← p" + src.name +
                " (top=" + top.toFixed(2) + ")");
        }
        removeEmptied(removed);
    }

    // 비워진 페이지 삭제 (뒤에서부터)
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
                log("[경고] p" + pg.name + " 잔존 개체 " + left +
                    "개 — 삭제 보류");
                continue;
            }
            var nm = pg.name;
            try { pg.remove(); log("  페이지 삭제 p" + nm); }
            catch (e) { log("[경고] p" + nm + " 삭제 실패: " + e.message); }
        }
    }

    // ─────────────────────────────────────────────────────────────
    // 섹션 삭제
    // ─────────────────────────────────────────────────────────────
    function deleteSection(sec) {
        var end = sec.end;
        while (end > sec.start && isProtected(doc.pages[end])) {
            log("  [가드] p" + doc.pages[end].name +
                " (마스터=" + (masterPrefix(doc.pages[end]) || "[없음]") +
                ") 삭제 범위에서 제외");
            end--;
        }
        log("[삭제] " + sec.label + " p" + (sec.start + 1) +
            "~p" + (end + 1) + " (" + (end - sec.start + 1) + "p)");
        for (var p = end; p >= sec.start; p--) {
            var pg = doc.pages[p];
            var fr = contentFrames(pg);
            log("  - p" + pg.name + " : " +
                (fr.length ? preview(fr[0]) : "(빈 페이지)"));
            try { pg.remove(); }
            catch (e) { log("[경고] p" + pg.name + " 삭제 실패: " + e.message); }
        }
    }

    // ─────────────────────────────────────────────────────────────
    // 실행 — 뒤 섹션부터 (앞 섹션 오프셋 불변 + 좌우 파리티 유지)
    // ─────────────────────────────────────────────────────────────
    sections.sort(function (a, b) { return b.start - a.start; });

    if (CFG.skip_slim) {
        log("[스킵] skip_slim=true — 삭제/병합/파리티 보정 생략, 간지 정렬만 수행");
    } else {
        for (var s = 0; s < sections.length; s++) {
            var sec = sections[s];
            if (inList(CFG.delete_sections, sec.label))      deleteSection(sec);
            else if (inList(CFG.merge_half_sections, sec.label))  mergeHalf(sec);
            else if (inList(CFG.merge_stack_sections, sec.label)) mergeStack(sec);
        }
    }
    flushLog();

    // ─────────────────────────────────────────────────────────────
    // 마스터 좌우 변형 보정 (섹션 첫 페이지에 헤더가 오도록)
    // ─────────────────────────────────────────────────────────────
    function masterByPrefix(pfx) {
        for (var i = 0; i < doc.masterSpreads.length; i++) {
            if (doc.masterSpreads[i].namePrefix === pfx) {
                return doc.masterSpreads[i];
            }
        }
        return null;
    }

    markerFrameIds = {};
    var after = buildSections();
    if (CFG.skip_slim) { after = []; }
    log("[마스터 파리티 보정]");
    for (var a = 0; a < after.length; a++) {
        var pg2 = doc.pages[after[a].start];
        var pfx = masterPrefix(pg2);
        var isRight = false;
        try { isRight = (pg2.side === PageSideOptions.RIGHT_HAND); } catch (e) {}
        var want = null;
        for (var mp = 0; mp < CFG.master_pairs.length; mp++) {
            var L = CFG.master_pairs[mp][0], R = CFG.master_pairs[mp][1];
            if (pfx === L && isRight) want = R;
            if (pfx === R && !isRight) want = L;
        }
        if (want) {
            var ms = masterByPrefix(want);
            if (ms) {
                pg2.appliedMaster = ms;
                log("  p" + pg2.name + " " + after[a].label + " : " +
                    pfx + " → " + want + (isRight ? " (오른쪽 시작)" : " (왼쪽 시작)"));
            } else {
                log("[경고] 마스터 " + want + " 없음 — p" + pg2.name + " 미보정");
            }
        }
    }

    // ─────────────────────────────────────────────────────────────
    // 간지 스프레드 정렬 (메모 페이지 삽입)
    //
    // 간지 블록 = 마스터가 [없음]인 페이지의 연속 런.
    //   왼쪽 페이지 = 스프레드 전체를 덮는 배경 사각형
    //   오른쪽 페이지 = 단원 제목 (흰 글자 — 배경이 없으면 안 보인다)
    // 슬림 변환으로 앞 섹션이 왼쪽 페이지에서 끝나면 이 블록이 한 칸 밀려
    // 배경이 pasteboard로 나가고 제목이 흰 배경에 얹힌다.
    // → 블록 앞(오른쪽 페이지 자리)에 메모 페이지를 끼워 2P 구성을 복원한다.
    // ─────────────────────────────────────────────────────────────
    function isRight(page) {
        try { return page.side === PageSideOptions.RIGHT_HAND; }
        catch (e) { return false; }
    }

    function noMasterRuns() {
        var runs = [], cur = null;
        for (var i = 0; i < doc.pages.length; i++) {
            var none = (masterPrefix(doc.pages[i]) === "");
            if (none) {
                if (cur === null) cur = { start: i, end: i };
                else cur.end = i;
            } else if (cur !== null) {
                runs.push(cur); cur = null;
            }
        }
        if (cur !== null) runs.push(cur);
        return runs;
    }

    function fixDividerSpreads() {
        var memoMaster = masterByPrefix(CFG.memo_master);
        if (!memoMaster) {
            log("[경고] 메모 마스터 '" + CFG.memo_master + "' 없음 — 간지 정렬 생략");
            return 0;
        }
        var inserted = 0, guard = 0;
        while (guard++ < 50) {
            var runs = noMasterRuns();
            var target = -1;
            for (var r = 0; r < runs.length; r++) {
                var lastPg = doc.pages[runs[r].end];
                if (!isRight(lastPg)) { target = r; break; }
            }
            if (target < 0) break;

            var run = runs[target];
            if (run.start === 0) {
                log("[경고] 문서 첫 블록은 보정 대상 아님 — 중단");
                break;
            }
            var dividerName = doc.pages[run.start].name;
            // 인덱스 지정자는 페이지 추가 시 다른 페이지를 가리키게 되므로
            // 실체 참조(getElements)로 앞 페이지를 고정한 뒤 AFTER 로 삽입한다.
            // pages.add(BEFORE, ...) 는 facing pages 셔플 때문에 한 칸 앞
            // (콘텐츠 페이지 사이)에 끼는 사례가 확인됨.
            var prevRef = doc.pages[run.start - 1].getElements()[0];
            var prevName = prevRef.name;
            var newPage;
            try {
                newPage = doc.pages.add(LocationOptions.AFTER, prevRef);
            } catch (e) {
                log("[오류] 메모 페이지 삽입 실패 (p" + dividerName + " 앞): " +
                    e.message);
                break;
            }
            if (newPage.documentOffset !== run.start) {
                log("  삽입 슬롯 어긋남(" + newPage.documentOffset +
                    " != " + run.start + ") — move 로 보정");
                try { newPage.move(LocationOptions.AFTER, prevRef); }
                catch (e2) { log("[오류] 위치 보정 실패: " + e2.message); }
            }
            // 최종 인접성 검증: 앞=콘텐츠 마지막 페이지, 뒤=간지 블록 첫 페이지
            var okPos = (newPage.documentOffset === run.start) &&
                        (doc.pages[newPage.documentOffset - 1].id === prevRef.id) &&
                        (masterPrefix(doc.pages[newPage.documentOffset + 1]) === "");
            if (!okPos) {
                log("[오류] 메모 페이지가 잘못된 위치에 삽입됨 — 되돌리고 중단 " +
                    "(off=" + newPage.documentOffset + ", 기대=" + run.start + ")");
                try { newPage.remove(); } catch (e4) {}
                break;
            }
            try { newPage.appliedMaster = memoMaster; } catch (e3) {
                log("[경고] 메모 마스터 적용 실패: " + e3.message);
            }
            inserted++;
            log("  메모 페이지 삽입 → p" + newPage.name +
                " (" + (isRight(newPage) ? "오른쪽" : "왼쪽") + " 페이지) : " +
                "앞 p" + prevName + " / 뒤 간지 p" +
                doc.pages[newPage.documentOffset + 1].name);
        }
        return inserted;
    }

    if (CFG.fix_divider_spreads) {
        log("[간지 스프레드 정렬]");
        var runsBefore = noMasterRuns();
        for (var rb = 0; rb < runsBefore.length; rb++) {
            var s0 = doc.pages[runsBefore[rb].start], e0 = doc.pages[runsBefore[rb].end];
            log("  블록 p" + s0.name + "~p" + e0.name +
                " 끝=" + (isRight(e0) ? "오른쪽 OK" : "왼쪽 ← 보정 필요"));
        }
        var n = fixDividerSpreads();
        log("  메모 페이지 " + n + "장 삽입");
        var runsAfter = noMasterRuns();
        var bad = 0;
        for (var ra = 0; ra < runsAfter.length; ra++) {
            if (!isRight(doc.pages[runsAfter[ra].end])) bad++;
        }
        if (bad > 0) log("[경고] 정렬 후에도 어긋난 간지 블록 " + bad + "건");
        else log("  간지 블록 " + runsAfter.length + "개 전부 (왼쪽,오른쪽) 구성 확인");
    }

    // ─────────────────────────────────────────────────────────────
    // 검증
    // ─────────────────────────────────────────────────────────────
    log("[검증]");
    var overset = 0, oversetList = [];
    for (var st = 0; st < doc.stories.length; st++) {
        try {
            if (doc.stories[st].overflows) {
                overset++;
                var tc = doc.stories[st].textContainers;
                var where = "";
                if (tc.length) {
                    try {
                        where = " p" + (tc[tc.length - 1].parentPage
                                        ? tc[tc.length - 1].parentPage.name
                                        : "?") + " : " +
                                preview(tc[tc.length - 1]);
                    } catch (e) {}
                }
                oversetList.push(where);
            }
        } catch (e) {}
    }
    log("  오버셋 스토리: " + overset + "건");
    for (var o = 0; o < oversetList.length && o < 40; o++) {
        log("   ! " + oversetList[o]);
    }

    var missLink = 0;
    try {
        for (var lk = 0; lk < doc.links.length; lk++) {
            if (doc.links[lk].status === LinkStatus.LINK_MISSING) missLink++;
        }
    } catch (e) {}
    log("  누락 링크: " + missLink + "건");

    log("[변환 후] pages=" + doc.pages.length);

    // 섹션 재확인
    markerFrameIds = {};
    var fin = buildSections();
    log("[최종 섹션 " + fin.length + "개]");
    for (var fi = 0; fi < fin.length; fi++) {
        log("  " + fin[fi].label + "  p" + (fin[fi].start + 1) + "~p" +
            (fin[fi].end + 1) + " (" + (fin[fi].end - fin[fi].start + 1) +
            "p) master=" +
            (masterPrefix(doc.pages[fin[fi].start]) || "[없음]"));
    }

    // ─────────────────────────────────────────────────────────────
    doc.viewPreferences.rulerOrigin = prevRuler;
    if (CFG.save) {
        doc.save();
        log("[저장] " + doc.fullName.fsName);
    }
    if (CFG.doc_path) { doc.close(SaveOptions.NO); }

    log("===== 완료 =====");
    flushLog();

    if (!CFG.doc_path) {
        alert("슬림 변환 완료\n\n" + LOG.slice(-25).join("\n"));
    }
})();
