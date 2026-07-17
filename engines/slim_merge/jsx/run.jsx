// [ENGINE TEMPLATE] 펼침면 압축 JSX — 수동 Slim_Merge.jsx(ox) / Slim_Merge2.jsx(arrange) 흡수.
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작 요약:
//   1) settings.output_indd (엔진이 미리 복사해 둔 사본) 를 창 없이 열기
//   2) '단원' 스타일 마커 수집 → settings.marker_text 포함 섹션 범위 그룹화
//   3) 모드별 짝-홀 페이지 병합 (ox: 프레임 축소+move / arrange: duplicate+고정좌표)
//   4) 저장 + 닫기 (사용자 문서 무접촉 — 우리가 연 사본만 닫음)
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
    // 메인
    // ───────────────────────────────────────────────────────────────

    try {
        var MODE        = settings.mode || "ox";
        var MARKER_TEXT = settings.marker_text;
        var STYLE_NAME  = settings.unit_style_name || "단원";
        var STYLE_GROUP = settings.unit_style_group || "마스터페이지";

        writeLog("===== 펼침면 압축 시작 (" + MODE + " / '" + MARKER_TEXT + "') =====");

        var outFile = new File(settings.output_indd);
        if (!outFile.exists) { fail("대상 .indd 없음: " + settings.output_indd); return; }

        var doc;
        try { doc = app.open(outFile, false); }
        catch (eOpen) { fail("문서 열기 실패: " + eOpen.message); return; }

        try {

            // ── '단원' 스타일 탐색 (수동본과 동일 폴백 순서) ────────────
            function getUnitStyle() {
                var s = null;
                var group = doc.characterStyleGroups.itemByName(STYLE_GROUP);
                if (group.isValid) {
                    s = group.characterStyles.itemByName(STYLE_NAME);
                    if (s && s.isValid) return { style: s, type: "character" };
                }
                s = doc.characterStyles.itemByName(STYLE_NAME);
                if (s && s.isValid) return { style: s, type: "character" };
                s = doc.paragraphStyles.itemByName(STYLE_NAME);
                if (s && s.isValid) return { style: s, type: "paragraph" };
                return null;
            }

            var unitData = getUnitStyle();
            if (!unitData) { fail("'" + STYLE_NAME + "' 스타일을 찾을 수 없습니다."); return; }
            var unitStyle = unitData.style;
            var unitType  = unitData.type;

            // ── '단원' 마커 수집 ────────────────────────────────────────
            function collectUnitMarkers() {
                app.findTextPreferences = NothingEnum.nothing;
                if (unitType === "character") {
                    app.findTextPreferences.appliedCharacterStyle = unitStyle;
                } else {
                    app.findTextPreferences.appliedParagraphStyle = unitStyle;
                }
                var found = doc.findText();
                app.findTextPreferences = NothingEnum.nothing;

                var markers = [];
                for (var i = 0; i < found.length; i++) {
                    var tf = found[i].parentTextFrames[0];
                    if (!tf || !tf.parentPage) continue;
                    markers.push({
                        pageOffset: tf.parentPage.documentOffset,
                        text: found[i].contents
                    });
                }
                markers.sort(function (a, b) { return a.pageOffset - b.pageOffset; });

                var unique = [];
                for (var j = 0; j < markers.length; j++) {
                    if (j === 0 || markers[j].pageOffset !== markers[j - 1].pageOffset) {
                        unique.push(markers[j]);
                    }
                }
                return unique;
            }

            var unitMarkers = collectUnitMarkers();
            writeLog("단원 마커: " + unitMarkers.length + "개");

            // ── 마커 텍스트 포함 범위 그룹화 (연속 마커 = 한 그룹) ──────
            var mergeRanges = [];
            var m = 0;
            while (m < unitMarkers.length) {
                if (unitMarkers[m].text.indexOf(MARKER_TEXT) === -1) {
                    m++; continue;
                }
                var startOffset = unitMarkers[m].pageOffset;
                var endOffset   = doc.pages.length - 1;
                var nextIdx = m + 1;
                while (nextIdx < unitMarkers.length &&
                       unitMarkers[nextIdx].text.indexOf(MARKER_TEXT) !== -1) {
                    nextIdx++;
                }
                if (nextIdx < unitMarkers.length) {
                    endOffset = unitMarkers[nextIdx].pageOffset - 1;
                }
                mergeRanges.push({ start: startOffset, end: endOffset });
                m = nextIdx;
            }

            if (mergeRanges.length === 0) {
                writeLog("[경고] '" + MARKER_TEXT + "' 섹션을 찾을 수 없습니다.");
                writeLog("병합 그룹: 0개");
                try { doc.close(SaveOptions.NO); } catch (eC0) {}
                writeLog("===== 완료 =====");
                return;
            }
            for (var ri = 0; ri < mergeRanges.length; ri++) {
                writeLog("그룹 " + (ri + 1) + ": 페이지 오프셋 " +
                         mergeRanges[ri].start + "~" + mergeRanges[ri].end);
            }

            // ═══════════════════════════════════════════════════════════
            // ox 모드 — Slim_Merge.jsx 로직 (프레임 축소 + move)
            // ═══════════════════════════════════════════════════════════

            function maxAreaTextFrame(page) {
                var best = null, maxA = -1;
                for (var f = 0; f < page.textFrames.length; f++) {
                    var tf = page.textFrames[f];
                    if (!tf.parentPage) continue;
                    var gb = tf.geometricBounds;
                    var a  = (gb[2] - gb[0]) * (gb[3] - gb[1]);
                    if (a > maxA) { maxA = a; best = tf; }
                }
                return best;
            }

            function pageHasNonTextContent(pg) {
                try {
                    if (pg.allPageItems.length > pg.textFrames.length) return true;
                } catch (e) {}
                for (var t = 0; t < pg.textFrames.length; t++) {
                    try {
                        var c = pg.textFrames[t].contents;
                        if (typeof c === 'string' && c.replace(/[\r\n\s]/g, '').length > 0) {
                            return true;
                        }
                    } catch (e2) {}
                }
                return false;
            }

            function unthreadInRange(range) {
                // 페이지 간 스토리 체인이 있으면 페이지 삭제 시 텍스트 재배치 → 미리 끊음
                var chainFrames = [];
                for (var i = range.start; i <= range.end; i++) {
                    var pg = doc.pages[i];
                    for (var f = 0; f < pg.textFrames.length; f++) {
                        var tf = pg.textFrames[f];
                        if (tf.nextTextFrame || tf.previousTextFrame) {
                            chainFrames.push(tf);
                        }
                    }
                }
                for (var k = chainFrames.length - 1; k >= 0; k--) {
                    try {
                        if (chainFrames[k].nextTextFrame) {
                            chainFrames[k].nextTextFrame = NothingEnum.nothing;
                        }
                    } catch (e) {}
                }
            }

            function processRangeOX(range) {
                unthreadInRange(range);

                // 페어 수집: LEFT_HAND + 다음 RIGHT_HAND
                var pairs = [];
                for (var i = range.start; i <= range.end - 1; i++) {
                    var pg = doc.pages[i];
                    if (pg.side !== PageSideOptions.LEFT_HAND) continue;
                    var next = doc.pages[i + 1];
                    if (next.side !== PageSideOptions.RIGHT_HAND) continue;
                    pairs.push({ left: pg, right: next });
                }

                // 1) 왼쪽 상단 축소 + 오른쪽 면적최대 프레임 → 왼쪽 하단
                for (var p = 0; p < pairs.length; p++) {
                    var leftPg  = pairs[p].left;
                    var rightPg = pairs[p].right;

                    var leftRef = maxAreaTextFrame(leftPg);
                    if (!leftRef) {
                        writeLog('p' + leftPg.name + ': 왼쪽 기준 프레임 없음 — 스킵');
                        continue;
                    }

                    var lb = leftRef.geometricBounds; // [y1, x1, y2, x2]
                    var splitY = (lb[0] + lb[2]) / 2;

                    try {
                        leftRef.geometricBounds = [lb[0], lb[1], splitY, lb[3]];
                    } catch (e) {
                        writeLog('[경고] p' + leftPg.name + ' 왼쪽 축소 실패: ' + e.message);
                        continue;
                    }

                    var rightRef = maxAreaTextFrame(rightPg);
                    if (!rightRef) {
                        writeLog('p' + rightPg.name + ': 오른쪽 기준 프레임 없음 — 왼쪽만 축소');
                        continue;
                    }

                    try {
                        rightRef.move(leftPg);
                        rightRef.geometricBounds = [splitY, lb[1], lb[2], lb[3]];
                        writeLog('p' + leftPg.name + ' <- p' + rightPg.name +
                                 ' 병합 OK (splitY=' + splitY.toFixed(2) + ')');
                    } catch (e2) {
                        writeLog('[경고] p' + rightPg.name + ' 이동/배치 실패: ' + e2.message);
                    }
                }

                // 2) 비어진 오른쪽 페이지 삭제 (큰 번호부터)
                var toDelete = [];
                for (var q = 0; q < pairs.length; q++) toDelete.push(pairs[q].right);
                toDelete.sort(function (a, b) { return b.documentOffset - a.documentOffset; });

                for (var d = 0; d < toDelete.length; d++) {
                    var pg2 = toDelete[d];
                    if (!pg2.isValid) continue;
                    if (pageHasNonTextContent(pg2)) {
                        writeLog('p' + pg2.name + ' 콘텐츠 잔존 — 삭제 스킵');
                        continue;
                    }
                    var delName = pg2.name;
                    try {
                        pg2.remove();
                        // 대형 문서 page.remove()는 페이지당 수십 초 — 진행
                        // 로그로 runner 스톨(300초 무갱신) 오탐 방지 (E2E 실측)
                        writeLog('p' + delName + ' 삭제 (' +
                                 (d + 1) + '/' + toDelete.length + ')');
                    } catch (e3) {
                        writeLog('[경고] p' + delName + ' 삭제 실패: ' + e3.message);
                    }
                }
            }

            // ═══════════════════════════════════════════════════════════
            // arrange 모드 — Slim_Merge2.jsx 로직 (duplicate + 고정 좌표)
            // ═══════════════════════════════════════════════════════════

            var ARR_LEFT  = settings.arrange_left_bounds;
            var ARR_RIGHT = settings.arrange_right_bounds;
            var ARR_BTM_Y = (settings.arrange_bottom_y != null)
                              ? settings.arrange_bottom_y : 100;

            function processRangeArrange(range) {
                // 1. 스레드 스토리를 독립 프레임으로 변환
                var processedStoryIds = {};
                var storiesToSplit = [];
                for (var p = range.start; p <= range.end; p++) {
                    var pageFrames = doc.pages[p].textFrames;
                    for (var f = 0; f < pageFrames.length; f++) {
                        var tf = pageFrames[f];
                        if (!tf.nextTextFrame && !tf.previousTextFrame) continue;
                        var sid = tf.parentStory.id;
                        if (processedStoryIds[sid]) continue;
                        processedStoryIds[sid] = true;
                        storiesToSplit.push(tf.parentStory);
                    }
                }
                for (var s = 0; s < storiesToSplit.length; s++) {
                    var st = storiesToSplit[s];
                    var containers = [];
                    for (var c1 = 0; c1 < st.textContainers.length; c1++) {
                        containers.push(st.textContainers[c1]);
                    }
                    for (var c2 = 0; c2 < containers.length; c2++) {
                        try { containers[c2].duplicate(); } catch (e) {}
                    }
                    for (var c3 = containers.length - 1; c3 >= 0; c3--) {
                        try { containers[c3].remove(); } catch (e2) {}
                    }
                }

                // 2. 하단 프레임 삭제 (y > 임계값)
                for (var i = range.start; i <= range.end; i++) {
                    var page = doc.pages[i];
                    var bottomFrame = null;
                    var maxY = -999999;
                    for (var f2 = 0; f2 < page.textFrames.length; f2++) {
                        var tf2 = page.textFrames[f2];
                        var y = tf2.geometricBounds[0];
                        if (y < 0) continue;
                        if (y > maxY) { maxY = y; bottomFrame = tf2; }
                    }
                    if (bottomFrame && maxY > ARR_BTM_Y) {
                        try { bottomFrame.remove(); } catch (e3) {}
                    }
                }

                // 3. 짝수-홀수 페어 병합 (duplicate + 고정 좌표)
                var pagesToDelete = {};
                var deleteList = [];

                for (var i2 = range.start; i2 <= range.end - 1; i2++) {
                    var currentPage = doc.pages[i2];
                    var pageNumber = currentPage.documentOffset + 1;
                    if (pageNumber % 2 !== 0) continue;
                    if (i2 + 1 > range.end) break;

                    var nextPage = doc.pages[i2 + 1];

                    var deletedBeforeCurrent = 0;
                    for (var c4 = 0; c4 < deleteList.length; c4++) {
                        if (deleteList[c4] < currentPage.documentOffset) {
                            deletedBeforeCurrent++;
                        }
                    }
                    var finalPageNumber = pageNumber - deletedBeforeCurrent;

                    var frames = nextPage.textFrames;
                    var duplicatedFrames = [];
                    var referenceDup = null;
                    var maxArea = -1;

                    for (var f3 = 0; f3 < frames.length; f3++) {
                        if (!frames[f3].parentPage) continue;
                        if (frames[f3].geometricBounds[0] < 0) continue;
                        var dup = frames[f3].duplicate(currentPage);
                        duplicatedFrames.push(dup);
                        var gb = dup.geometricBounds;
                        var area = (gb[2] - gb[0]) * (gb[3] - gb[1]);
                        if (area > maxArea) { maxArea = area; referenceDup = dup; }
                    }

                    if (referenceDup) {
                        var targetBounds = (finalPageNumber % 2 === 0) ? ARR_LEFT : ARR_RIGHT;
                        var refGB = referenceDup.geometricBounds;
                        var deltaX = targetBounds[1] - refGB[1];
                        var deltaY = targetBounds[0] - refGB[0];
                        for (var k = 0; k < duplicatedFrames.length; k++) {
                            duplicatedFrames[k].move(undefined, [deltaX, deltaY]);
                        }
                        referenceDup.geometricBounds = targetBounds;
                        writeLog('p' + currentPage.name + ' <- p' + nextPage.name + ' 병합 OK');
                    }

                    var delIdx = nextPage.documentOffset;
                    if (!pagesToDelete[delIdx]) {
                        pagesToDelete[delIdx] = true;
                        deleteList.push(delIdx);
                    }
                }

                deleteList.sort(function (a, b) { return b - a; });
                for (var d2 = 0; d2 < deleteList.length; d2++) {
                    var idx = deleteList[d2];
                    if (idx >= 0 && idx < doc.pages.length) {
                        try {
                            doc.pages[idx].remove();
                            writeLog('오프셋 ' + idx + ' 페이지 삭제 (' +
                                     (d2 + 1) + '/' + deleteList.length + ')');
                        } catch (e4) {}
                    }
                }
            }

            // ── 실행: 뒤쪽 그룹부터 (앞쪽 인덱스 보호 — 수동본 동일) ────
            mergeRanges.sort(function (a, b) { return b.start - a.start; });

            var pagesBefore = doc.pages.length;
            for (var r = 0; r < mergeRanges.length; r++) {
                if (MODE === "arrange") processRangeArrange(mergeRanges[r]);
                else processRangeOX(mergeRanges[r]);
            }
            var pagesAfter = doc.pages.length;

            writeLog("병합 그룹: " + mergeRanges.length + "개");
            writeLog("페이지: " + pagesBefore + " -> " + pagesAfter);

            // 저장
            writeLog("저장 중...");
            try { doc.save(); } catch (eS) { fail("저장 실패: " + eS.message); }
            writeLog("저장: " + doc.fullName.fsName);

        } finally {
            // 우리가 연 사본만 닫는다 (사용자 문서 무접촉)
            try { doc.close(SaveOptions.NO); } catch (eC) {}
        }

        writeLog("===== 완료 =====");

    } catch (eMain) {
        writeLog("[치명적 오류] " + (eMain.message || eMain));
    }

})();
