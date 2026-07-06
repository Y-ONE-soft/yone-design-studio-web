// Slim_Merge.jsx
// "단원" 스타일이 "본문 O/X"인 섹션의 짝-홀 페이지를 자동 병합.
//   - 짝수(왼쪽) 페이지의 면적 최대 프레임을 상단으로 축소
//   - 다음 홀수(오른쪽) 페이지의 면적 최대 프레임을 왼쪽 페이지 하단으로 move + 정확 배치
//   - 비어진 오른쪽 페이지 자동 삭제
//   - 단일 Undo (ENTIRE_SCRIPT) — Cmd+Z 한 번에 전체 복구

(function () {

    if (app.documents.length === 0) {
        alert("문서를 열어주세요.");
        return;
    }

    var doc = app.activeDocument;

    // ── "단원" 스타일 탐색 ────────────────────────────────
    function getUnitStyle() {
        var s = null;
        var group = doc.characterStyleGroups.itemByName("마스터페이지");
        if (group.isValid) {
            s = group.characterStyles.itemByName("단원");
            if (s && s.isValid) return { style: s, type: "character" };
        }
        s = doc.characterStyles.itemByName("단원");
        if (s && s.isValid) return { style: s, type: "character" };
        s = doc.paragraphStyles.itemByName("단원");
        if (s && s.isValid) return { style: s, type: "paragraph" };
        alert("단원 스타일을 찾을 수 없습니다.");
        return null;
    }

    var unitData = getUnitStyle();
    if (!unitData) return;
    var unitStyle = unitData.style;
    var unitType  = unitData.type;

    // ── "단원" 마커 수집 ──────────────────────────────────
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

    // ── "본문 O/X" 범위 그룹화 ─────────────────────────────
    //   연속된 "본문 O/X" 마커는 한 그룹(다음 다른 단원 직전까지)
    var mergeRanges = [];
    var m = 0;
    while (m < unitMarkers.length) {
        if (unitMarkers[m].text.indexOf("본문 O/X") === -1) {
            m++; continue;
        }
        var startOffset = unitMarkers[m].pageOffset;
        var endOffset   = doc.pages.length - 1;
        var nextIdx = m + 1;
        while (nextIdx < unitMarkers.length &&
               unitMarkers[nextIdx].text.indexOf("본문 O/X") !== -1) {
            nextIdx++;
        }
        if (nextIdx < unitMarkers.length) {
            endOffset = unitMarkers[nextIdx].pageOffset - 1;
        }
        mergeRanges.push({ start: startOffset, end: endOffset });
        m = nextIdx;
    }

    if (mergeRanges.length === 0) {
        alert("본문 O/X 섹션을 찾을 수 없습니다.");
        return;
    }

    // ── 헬퍼 ─────────────────────────────────────────────
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
            } catch (e) {}
        }
        return false;
    }

    function unthreadInRange(range) {
        // 페이지 간 스토리 체인이 있으면 페이지 삭제 시 텍스트가 재배치됨 → 미리 끊음
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

    var log = [];

    // ── 그룹 처리 ────────────────────────────────────────
    function processRange(range) {
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

        // 1) 짝-홀 처리: 왼쪽 상단 축소 + 오른쪽 면적최대 프레임 → 왼쪽 하단으로 이동
        for (var p = 0; p < pairs.length; p++) {
            var leftPg  = pairs[p].left;
            var rightPg = pairs[p].right;

            var leftRef = maxAreaTextFrame(leftPg);
            if (!leftRef) {
                log.push('p' + leftPg.name + ': 왼쪽 기준 프레임 없음 — 스킵');
                continue;
            }

            var lb = leftRef.geometricBounds; // [y1, x1, y2, x2]
            var splitY = (lb[0] + lb[2]) / 2; // 자동 = 왼쪽 프레임 중간

            // 왼쪽 기준 프레임 → 상단으로 축소
            try {
                leftRef.geometricBounds = [lb[0], lb[1], splitY, lb[3]];
            } catch (e) {
                log.push('[ERR] p' + leftPg.name + ' 왼쪽 축소 실패: ' + e.message);
                continue;
            }

            // 오른쪽 기준 프레임 → 왼쪽 페이지로 이동 + 하단 정확 배치
            var rightRef = maxAreaTextFrame(rightPg);
            if (!rightRef) {
                log.push('p' + rightPg.name + ': 오른쪽 기준 프레임 없음 — 왼쪽만 축소');
                continue;
            }

            try {
                rightRef.move(leftPg);
                rightRef.geometricBounds = [splitY, lb[1], lb[2], lb[3]];
                log.push('p' + leftPg.name + ' ← p' + rightPg.name +
                         ' 병합 OK (splitY=' + splitY.toFixed(2) + ')');
            } catch (e) {
                log.push('[ERR] p' + rightPg.name + ' 이동/배치 실패: ' + e.message);
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
                log.push('p' + pg2.name + ' 콘텐츠 잔존 — 삭제 스킵');
                continue;
            }
            try {
                pg2.remove();
            } catch (e) {
                log.push('[ERR] p' + pg2.name + ' 삭제 실패: ' + e.message);
            }
        }
    }

    // 뒤쪽 그룹부터 처리 — 앞쪽 그룹의 페이지 인덱스가 영향받지 않도록
    mergeRanges.sort(function (a, b) { return b.start - a.start; });

    app.doScript(function () {
        for (var r = 0; r < mergeRanges.length; r++) {
            processRange(mergeRanges[r]);
        }
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT,
       "본문 O/X 짝-홀 페이지 병합");

    alert("본문 O/X 짝수페이지 기준 병합 완료 — " + mergeRanges.length + "개 그룹 처리\n\n" +
          log.join('\n'));

})();
