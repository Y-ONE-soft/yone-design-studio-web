(function () {

    if (app.documents.length === 0) {
        alert("문서를 열어주세요.");
        return;
    }

    var doc = app.activeDocument;

    function getUnitStyle() {

        var s = null;
        var type = "character";

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
    var unitType = unitData.type;

    // 🔵 단원 스타일이 있는 모든 페이지를 수집하여 섹션 범위 계산

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
        for (var i = 0; i < markers.length; i++) {
            if (i === 0 || markers[i].pageOffset !== markers[i - 1].pageOffset) {
                unique.push(markers[i]);
            }
        }
        return unique;
    }

    var unitMarkers = collectUnitMarkers();

    // 🔵 모든 "문장 배열" 그룹 수집
    //   연속된 "문장 배열" 마커는 하나의 그룹(다음 다른 단원 직전까지)으로 묶음
    var mergeRanges = [];
    var m = 0;
    while (m < unitMarkers.length) {
        if (unitMarkers[m].text.indexOf("문장 배열") === -1) {
            m++;
            continue;
        }
        var startOffset = unitMarkers[m].pageOffset;
        var endOffset = doc.pages.length - 1;
        var nextIdx = m + 1;
        // 같은 그룹의 연속된 "문장 배열" 마커는 건너뛰기
        while (nextIdx < unitMarkers.length &&
               unitMarkers[nextIdx].text.indexOf("문장 배열") !== -1) {
            nextIdx++;
        }
        if (nextIdx < unitMarkers.length) {
            endOffset = unitMarkers[nextIdx].pageOffset - 1;
        }
        mergeRanges.push({ start: startOffset, end: endOffset });
        m = nextIdx;
    }

    if (mergeRanges.length === 0) {
        alert("문장 배열 섹션을 찾을 수 없습니다.");
        return;
    }

    // 🔵 그룹 한 개를 슬림 병합 처리
    function processRange(range) {
        // 1. 그룹 범위 내 모든 스레드 스토리를 독립 프레임으로 변환
        //    (한 페이지에 여러 스토리가 시작될 수 있고, 페이지마다 별개 스토리일 수 있음)
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
            // 컬렉션 변경 대비: 컨테이너 참조를 미리 배열에 캡처
            var containers = [];
            for (var c = 0; c < st.textContainers.length; c++) {
                containers.push(st.textContainers[c]);
            }
            for (var c = 0; c < containers.length; c++) {
                try { containers[c].duplicate(); } catch (e) {}
            }
            for (var c = containers.length - 1; c >= 0; c--) {
                try { containers[c].remove(); } catch (e) {}
            }
        }

        // 2. 하단 프레임 삭제 (y > 100)
        for (var i = range.start; i <= range.end; i++) {
            var page = doc.pages[i];
            var bottomFrame = null;
            var maxY = -999999;
            for (var f = 0; f < page.textFrames.length; f++) {
                var tf = page.textFrames[f];
                var y = tf.geometricBounds[0];
                if (y < 0) continue;
                if (y > maxY) {
                    maxY = y;
                    bottomFrame = tf;
                }
            }
            if (bottomFrame && maxY > 100) {
                try { bottomFrame.remove(); } catch (e) {}
            }
        }

        // 3. 짝수-홀수 페어 병합
        var pagesToDelete = {};
        var deleteList = [];
        var leftBounds  = [160.249999999867, 20, 404.74999999596, 187.9999999999936];
        var rightBounds = [160.249999999867, 22, 404.74999999596, 189.9999999999936];

        for (var i = range.start; i <= range.end - 1; i++) {
            var currentPage = doc.pages[i];
            var pageNumber = currentPage.documentOffset + 1;
            if (pageNumber % 2 !== 0) continue;
            if (i + 1 > range.end) break;

            var nextPage = doc.pages[i + 1];

            var deletedBeforeCurrent = 0;
            for (var c = 0; c < deleteList.length; c++) {
                if (deleteList[c] < currentPage.documentOffset) {
                    deletedBeforeCurrent++;
                }
            }
            var finalPageNumber = pageNumber - deletedBeforeCurrent;

            var frames = nextPage.textFrames;
            var duplicatedFrames = [];
            var referenceDup = null;
            var maxArea = -1;

            for (var f = 0; f < frames.length; f++) {
                if (!frames[f].parentPage) continue;
                if (frames[f].geometricBounds[0] < 0) continue;
                var dup = frames[f].duplicate(currentPage);
                duplicatedFrames.push(dup);
                var gb = dup.geometricBounds;
                var area = (gb[2] - gb[0]) * (gb[3] - gb[1]);
                if (area > maxArea) {
                    maxArea = area;
                    referenceDup = dup;
                }
            }

            if (referenceDup) {
                var targetBounds = (finalPageNumber % 2 === 0) ? leftBounds : rightBounds;
                var refGB = referenceDup.geometricBounds;
                var deltaX = targetBounds[1] - refGB[1];
                var deltaY = targetBounds[0] - refGB[0];
                for (var k = 0; k < duplicatedFrames.length; k++) {
                    duplicatedFrames[k].move(undefined, [deltaX, deltaY]);
                }
                referenceDup.geometricBounds = targetBounds;
            }

            var delIdx = nextPage.documentOffset;
            if (!pagesToDelete[delIdx]) {
                pagesToDelete[delIdx] = true;
                deleteList.push(delIdx);
            }
        }

        deleteList.sort(function (a, b) { return b - a; });
        for (var d = 0; d < deleteList.length; d++) {
            var idx = deleteList[d];
            if (idx >= 0 && idx < doc.pages.length) {
                doc.pages[idx].remove();
            }
        }
    }

    // 🔵 뒤쪽 그룹부터 처리 — 앞쪽 그룹의 페이지 인덱스가 영향받지 않도록
    mergeRanges.sort(function (a, b) { return b.start - a.start; });
    for (var r = 0; r < mergeRanges.length; r++) {
        processRange(mergeRanges[r]);
    }

    alert("문장 배열 병합 완료 — " + mergeRanges.length + "개 그룹 처리");

})();
