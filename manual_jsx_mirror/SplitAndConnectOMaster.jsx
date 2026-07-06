#target indesign
/*
    SplitAndConnectOMaster.jsx
    ------------------------------------------------------------------
    1단계: 문서 내 모든 연결 스토리를 Adobe 샘플 SplitStory.jsx로 분리
           - 각 프레임이 자기 텍스트만 가진 독립 스토리가 됨 (오버플로우 없음)
           - 마스터 페이지 위의 프레임은 제외

    2단계: O마스터(마스터 이름이 "O"로 시작) 페이지를 연속된 그룹으로 묶고,
           그룹 내 텍스트 프레임을 페이지 순서대로 다시 연결한다.
           - 그룹 경계: O마스터가 아닌 페이지(다른 마스터 또는 무마스터)가 등장하면 종료
           - 그룹 내 정렬: 페이지 순서 → 페이지 내 top → 페이지 내 left
*/
(function () {
    if (app.documents.length === 0) {
        alert("열린 문서가 없습니다.");
        return;
    }
    var doc = app.activeDocument;

    function isOnMaster(tf) {
        try {
            var p = tf.parentPage;
            if (!p) return false;
            var parent = p.parent;
            return (parent && parent.constructor && parent.constructor.name === "MasterSpread");
        } catch (_) { return false; }
    }

    function isOMasterPage(page) {
        try {
            var m = page.appliedMaster;
            if (!m) return false;
            var name = m.name || "";
            return name.indexOf("O") === 0;
        } catch (_) { return false; }
    }

    function findSplitStoryFile() {
        var base = app.filePath.fsName;
        var candidates = [
            File(base + "/Scripts/Scripts Panel/Samples/JavaScript/SplitStory.jsx"),
            File(base + "/Scripts/Samples/JavaScript/SplitStory.jsx"),
            File(base + "/Scripts and Extensions/Scripts/Scripts Panel/Samples/JavaScript/SplitStory.jsx")
        ];
        for (var i = 0; i < candidates.length; i++) {
            try { if (candidates[i].exists) return candidates[i]; } catch (_) {}
        }
        return null;
    }

    // 1단계: 연결된 스토리들을 Adobe 샘플 SplitStory.jsx로 분리 (오버플로우 없음)
    function splitAllStories() {
        var storyFirstFrameMap = {};
        var tfs = doc.textFrames.everyItem().getElements();
        for (var i = 0; i < tfs.length; i++) {
            var tf = tfs[i];
            if (!tf || !tf.isValid) continue;
            if (isOnMaster(tf)) continue;
            var st = null;
            try { st = tf.parentStory; } catch (_) { st = null; }
            if (!st || !st.isValid) continue;

            var hasLink = !!(tf.previousTextFrame && tf.previousTextFrame.isValid) ||
                          !!(tf.nextTextFrame && tf.nextTextFrame.isValid);
            if (!hasLink) continue;

            if (!storyFirstFrameMap[st.id]) {
                var containers = st.textContainers;
                var first = null;
                for (var k = 0; k < containers.length; k++) {
                    var c = containers[k];
                    if (!c || !c.isValid) continue;
                    if (c.constructor && (c.constructor.name === "TextFrame" || c.constructor.name === "TextPath")) {
                        if (isOnMaster(c)) continue;
                        first = c; break;
                    }
                }
                if (first) storyFirstFrameMap[st.id] = first;
            }
        }

        var storyIds = [];
        for (var sid in storyFirstFrameMap) {
            if (storyFirstFrameMap.hasOwnProperty(sid)) storyIds.push(sid);
        }
        if (storyIds.length === 0) return 0;

        var splitFile = findSplitStoryFile();
        if (!splitFile) {
            alert("Adobe 샘플 SplitStory.jsx를 찾을 수 없습니다.\nInDesign 설치 폴더의 Scripts/Samples/JavaScript 경로를 확인해 주세요.");
            return 0;
        }

        var splitCount = 0;
        for (var i = 0; i < storyIds.length; i++) {
            var firstFrame = storyFirstFrameMap[storyIds[i]];
            if (!firstFrame || !firstFrame.isValid) continue;

            try { app.selection = firstFrame; } catch (_) {
                try { app.select(firstFrame); } catch (__) {}
            }

            try {
                app.doScript(splitFile, ScriptLanguage.JAVASCRIPT, undefined,
                             UndoModes.FAST_ENTIRE_SCRIPT, "SplitStory (Samples)");
                splitCount++;
            } catch (e) {}
        }
        return splitCount;
    }

    // 페이지 내 텍스트 프레임 수집 + 정렬 (top, then left)
    // - 페이지 면적의 MIN_AREA_RATIO 미만인 작은 박스(지문번호/발문 띠 등)는 제외
    var MIN_AREA_RATIO = 0.08; // 페이지 면적의 8% 미만이면 무시
    function collectPageFrames(page) {
        var all = page.textFrames.everyItem().getElements();
        var pb = page.bounds; // [y1, x1, y2, x2]
        var pageArea = (pb[2] - pb[0]) * (pb[3] - pb[1]);
        var minArea = pageArea * MIN_AREA_RATIO;

        var arr = [];
        for (var i = 0; i < all.length; i++) {
            var tf = all[i];
            if (!tf || !tf.isValid) continue;
            var gb = tf.geometricBounds;
            var area = (gb[2] - gb[0]) * (gb[3] - gb[1]);
            if (area < minArea) continue;
            arr.push(tf);
        }
        arr.sort(function (a, b) {
            var ay = a.geometricBounds[0], by = b.geometricBounds[0];
            if (Math.abs(ay - by) > 1) return ay - by;
            return a.geometricBounds[1] - b.geometricBounds[1];
        });
        return arr;
    }

    function connectGroup(group) {
        var linked = 0;
        for (var i = 0; i < group.length - 1; i++) {
            try {
                var a = group[i], b = group[i + 1];
                if (a && a.isValid && b && b.isValid) {
                    a.nextTextFrame = b;
                    linked++;
                }
            } catch (_) {}
        }
        return linked;
    }

    // 2단계: O마스터 연속 그룹 단위로 프레임 연결
    function processOMasterGroups() {
        var groupCount = 0, linkCount = 0;
        var group = [];
        var pages = doc.pages;

        for (var i = 0; i < pages.length; i++) {
            var page = pages[i];

            if (!isOMasterPage(page)) {
                if (group.length >= 2) {
                    linkCount += connectGroup(group);
                    groupCount++;
                } else if (group.length === 1) {
                    groupCount++;
                }
                group = [];
                continue;
            }

            var frames = collectPageFrames(page);
            for (var f = 0; f < frames.length; f++) {
                group.push(frames[f]);
            }
        }

        if (group.length >= 2) {
            linkCount += connectGroup(group);
            groupCount++;
        } else if (group.length === 1) {
            groupCount++;
        }

        return { groups: groupCount, links: linkCount };
    }

    // 실행
    var _uil = app.scriptPreferences.userInteractionLevel;
    var _rd = app.scriptPreferences.enableRedraw;
    var splitN = 0, groupN = 0, linkN = 0;

    try {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
        app.scriptPreferences.enableRedraw = false;

        // 1단계: SplitStory (각 호출이 자체 doScript이므로 외부 묶음 없이 실행)
        splitN = splitAllStories();

        // 2단계: O마스터 그룹 연결 (단일 Undo)
        app.doScript(function () {
            var r = processOMasterGroups();
            groupN = r.groups;
            linkN = r.links;
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "Connect O-Master Groups");

    } finally {
        try { app.scriptPreferences.userInteractionLevel = _uil; } catch (_) {}
        try { app.scriptPreferences.enableRedraw = _rd; } catch (_) {}
        try { doc.recompose(); app.redraw(); } catch (_) {}
    }

    alert(
        "완료\n" +
        "─────────────\n" +
        "분리한 스토리: " + splitN + "개\n" +
        "O마스터 그룹: " + groupN + "개\n" +
        "연결한 프레임: " + linkN + "개"
    );
})();
