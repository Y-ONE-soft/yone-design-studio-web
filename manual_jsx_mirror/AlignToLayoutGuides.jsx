#target indesign

/*
    AlignToLayoutGuides.jsx
    -----------------------
    페이지 마진/단(컬럼)/룰러 가이드를 기준으로 프레임 좌측을 자동 정렬.
    각 페이지의 가이드 X 좌표 후보 중 프레임의 현재 좌측에서 가장 가까운
    것에 스냅한다. 너비는 유지(좌측만 이동), 상하 위치도 유지.

    적용 범위: 선택된 항목 / 전체 페이지 / 페이지 범위 (다이얼로그)
    스냅 거리(임계치) 안에 있는 가이드만 후보로 사용.

    Facing pages 문서에서는 margin.left가 inside, margin.right가 outside를
    가리키므로 page.side에 따라 좌/우 마진을 적절히 매핑한다.
*/

(function() {
    if (app.documents.length === 0) {
        alert("열려있는 문서가 없습니다.");
        return;
    }
    var doc = app.activeDocument;

    // ----- 다이얼로그 -----
    var dlg = app.dialogs.add({name: "레이아웃 선 기준 정렬", canCancel: true});
    var col = dlg.dialogColumns.add();

    var rangeRow = col.dialogRows.add();
    rangeRow.staticTexts.add({staticLabel: "적용 범위:"});
    var rangeBox = rangeRow.dropdowns.add({
        stringList: ["선택된 항목", "전체 페이지", "페이지 범위"],
        selectedIndex: 0
    });

    var pageRow = col.dialogRows.add();
    pageRow.staticTexts.add({staticLabel: "페이지 범위 (예: 1-10,15):"});
    var pageInput = pageRow.textEditboxes.add({editContents: "", minWidth: 140});

    var tolRow = col.dialogRows.add();
    tolRow.staticTexts.add({staticLabel: "스냅 거리 (mm):"});
    var tolInput = tolRow.textEditboxes.add({editContents: "5", minWidth: 60});

    var minWRow = col.dialogRows.add();
    minWRow.staticTexts.add({staticLabel: "큰 프레임 최소 너비 (mm):"});
    var minWInput = minWRow.textEditboxes.add({editContents: "60", minWidth: 60});

    if (!dlg.show()) { dlg.destroy(); return; }

    var rangeMode = rangeBox.selectedIndex; // 0:selection 1:all 2:range
    var pageRangeStr = pageInput.editContents;
    var TOL = parseFloat(tolInput.editContents);
    var BIG_W = parseFloat(minWInput.editContents);
    if (isNaN(TOL) || TOL <= 0) TOL = 5;
    if (isNaN(BIG_W) || BIG_W < 0) BIG_W = 60;
    dlg.destroy();

    // ----- 좌표계/단위 강제 (작업 후 원복) -----
    var prevOrigin = doc.viewPreferences.rulerOrigin;
    var prevHU = doc.viewPreferences.horizontalMeasurementUnits;
    var prevVU = doc.viewPreferences.verticalMeasurementUnits;
    doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
    doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
    doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;

    var facingPages = false;
    try { facingPages = doc.documentPreferences.facingPages; } catch(e) {}

    // ----- 페이지 범위 파서 -----
    function parsePageRange(str, total) {
        var pages = [];
        var parts = str.split(",");
        for (var i = 0; i < parts.length; i++) {
            var part = parts[i].replace(/\s/g, "");
            if (!part) continue;
            var m = part.match(/^(\d+)-(\d+)$/);
            if (m) {
                var s = parseInt(m[1]);
                var e = parseInt(m[2]);
                for (var k = s; k <= e; k++) {
                    if (k >= 1 && k <= total) pages.push(k - 1);
                }
            } else {
                var n = parseInt(part);
                if (!isNaN(n) && n >= 1 && n <= total) pages.push(n - 1);
            }
        }
        return pages;
    }

    // ----- 페이지의 좌/우 가이드 X 좌표 후보 수집 (페이지 좌표) -----
    function pageGuideXs(page) {
        var b = page.bounds; // spread 좌표 [y1, x1, y2, x2]
        var pw = b[3] - b[1];
        var pageOffsetX = b[1]; // spread 좌표상 페이지 좌측 X

        var mp = page.marginPreferences;

        // facing pages mirror 처리
        var marginLeftActual, marginRightActual;
        if (facingPages) {
            if (page.side == PageSideOptions.LEFT_HAND) {
                marginLeftActual = mp.right;  // outside = 좌측
                marginRightActual = mp.left;  // inside = 우측
            } else {
                marginLeftActual = mp.left;   // inside = 좌측
                marginRightActual = mp.right; // outside = 우측
            }
        } else {
            marginLeftActual = mp.left;
            marginRightActual = mp.right;
        }

        var contentL = marginLeftActual;
        var contentR = pw - marginRightActual;
        var contentW = contentR - contentL;
        var cc = mp.columnCount || 1;
        var cg = mp.columnGutter || 0;

        var leftXs = [contentL];
        var rightXs = [contentR];

        if (cc > 1) {
            var oneW = (contentW - cg * (cc - 1)) / cc;
            for (var c = 1; c < cc; c++) {
                var endX = contentL + c * oneW + (c - 1) * cg;
                rightXs.push(endX);
                leftXs.push(endX + cg);
            }
        }

        // 페이지 룰러 가이드 (vertical only) - location은 ruler 좌표(페이지 좌표)
        try {
            for (var g = 0; g < page.guides.length; g++) {
                var gd = page.guides[g];
                if (gd.orientation == HorizontalOrVertical.VERTICAL) {
                    leftXs.push(gd.location);
                    rightXs.push(gd.location);
                }
            }
        } catch(e) {}

        // 스프레드 룰러 가이드 (spread 좌표 → 페이지 좌표)
        try {
            var spread = page.parent;
            for (var sg = 0; sg < spread.guides.length; sg++) {
                var sgd = spread.guides[sg];
                if (sgd.orientation == HorizontalOrVertical.VERTICAL) {
                    var lx = sgd.location - pageOffsetX;
                    if (lx >= -1 && lx <= pw + 1) {
                        leftXs.push(lx);
                        rightXs.push(lx);
                    }
                }
            }
        } catch(e) {}

        // 마스터 페이지 가이드 (page side가 일치하는 마스터 페이지의 page.guides + spread.guides)
        try {
            var am = page.appliedMaster;
            if (am !== null && am !== undefined) {
                for (var mp = 0; mp < am.pages.length; mp++) {
                    var masterPage = am.pages[mp];
                    if (masterPage.side != page.side &&
                        page.side != PageSideOptions.SINGLE_SIDED) continue;
                    for (var mg = 0; mg < masterPage.guides.length; mg++) {
                        var mgd = masterPage.guides[mg];
                        if (mgd.orientation == HorizontalOrVertical.VERTICAL) {
                            leftXs.push(mgd.location);
                            rightXs.push(mgd.location);
                        }
                    }
                    var mb = masterPage.bounds;
                    var masterPageOffsetX = mb[1];
                    for (var msg = 0; msg < am.guides.length; msg++) {
                        var msgd = am.guides[msg];
                        if (msgd.orientation == HorizontalOrVertical.VERTICAL) {
                            var mlx = msgd.location - masterPageOffsetX;
                            if (mlx >= -1 && mlx <= pw + 1) {
                                leftXs.push(mlx);
                                rightXs.push(mlx);
                            }
                        }
                    }
                    break;
                }
            }
        } catch(e) {}

        // === 페이지 내 큰 프레임 너비 통계 → N단 분할 자동 추정 ===
        // 페이지에 같은 너비의 큰 프레임이 N개(2~) 있고
        // contentW = N*colW + (N-1)*gutter 로 균등 분할 가능하면
        // 각 단의 시작 X를 가이드로 추가 (마스터 ruler guide나 column 분할이
        // 명시적으로 그어지지 않은 워크북에서 2단 본문 자동 인식)
        try {
            var pageItems = page.pageItems;
            var widthBuckets = {};
            for (var pi = 0; pi < pageItems.length; pi++) {
                try {
                    var pib = pageItems[pi].geometricBounds;
                    var pT = pib[0], pL = pib[1], pR = pib[3];
                    var piw = pR - pL;
                    if (piw < BIG_W) continue;                           // 큰 프레임만 단 추론에 카운트
                    if (pT < -10) continue;                              // 페이지 외곽 헤더 제외
                    if (pL < contentL - 5 || pR > contentR + 5) continue; // 본문 영역 밖 제외
                    var keyW = Math.round(piw * 10) / 10;
                    if (!widthBuckets[keyW]) widthBuckets[keyW] = 0;
                    widthBuckets[keyW]++;
                } catch(e) {}
            }
            var modeW = null, modeCount = 0;
            for (var kw in widthBuckets) {
                if (widthBuckets[kw] > modeCount) {
                    modeCount = widthBuckets[kw];
                    modeW = parseFloat(kw);
                }
            }
            if (modeW && modeCount >= 2) {
                for (var nc = modeCount; nc >= 2; nc--) {
                    if (modeW * nc > contentW + 1) continue;
                    var gutter = (contentW - nc * modeW) / (nc - 1);
                    if (gutter < -0.3 || gutter > 30) continue;
                    for (var c2 = 0; c2 < nc; c2++) {
                        var startX = contentL + c2 * (modeW + gutter);
                        leftXs.push(startX);
                        rightXs.push(startX + modeW);
                    }
                    break;
                }
            }
        } catch(e) {}

        return {left: leftXs, right: rightXs};
    }

    // ----- 단일 프레임 좌측 스냅 (선택 모드 / 단일 처리용) -----
    // 가이드와 거리 TOL 이내면 스냅. 너비 무관.
    function snapItem(it, page) {
        try {
            if (it.locked) return false;
            var bds = it.geometricBounds;
            var T = bds[0], L = bds[1], B = bds[2], R = bds[3];
            var w = R - L;
            if (w < 1) return false;

            var gx = pageGuideXs(page);
            var bestL = null, bestDiff = Infinity;
            for (var i = 0; i < gx.left.length; i++) {
                var d = Math.abs(L - gx.left[i]);
                if (d > 0.05 && d < bestDiff) {
                    bestDiff = d;
                    bestL = gx.left[i];
                }
            }
            if (bestL === null) return false;
            if (bestDiff > TOL) return false;

            it.geometricBounds = [T, bestL, B, bestL + w];
            return true;
        } catch(e) {
            return false;
        }
    }

    // ----- 페이지 단위 처리 (전체/범위 모드용) -----
    // 1차: 큰 프레임(w >= BIG_W)을 가이드에 스냅, dx 기록
    // 2차: 작은 프레임(w < BIG_W)에 같은 페이지 가까운 큰 프레임의 dx 전파
    function processPage(page, counters) {
        var items = page.pageItems;
        var gx = pageGuideXs(page);
        var bigFrames = []; // {T, B, oldL, newL, dx}

        for (var i = 0; i < items.length; i++) {
            try {
                var it = items[i];
                if (it.locked) continue;
                var bds = it.geometricBounds;
                var T = bds[0], L = bds[1], B = bds[2], R = bds[3];
                var w = R - L;
                if (w < BIG_W) continue;
                counters.total++;

                var bestL = null, bestDiff = Infinity;
                for (var gi = 0; gi < gx.left.length; gi++) {
                    var d = Math.abs(L - gx.left[gi]);
                    if (d > 0.05 && d < bestDiff) {
                        bestDiff = d;
                        bestL = gx.left[gi];
                    }
                }
                var newL = L, dx = 0;
                if (bestL !== null && bestDiff <= TOL) {
                    newL = bestL;
                    dx = bestL - L;
                    it.geometricBounds = [T, bestL, B, bestL + w];
                    counters.fixed++;
                }
                bigFrames.push({T: T, B: B, oldL: L, newL: newL, dx: dx});
            } catch(e) {}
        }

        for (var i2 = 0; i2 < items.length; i2++) {
            try {
                var it2 = items[i2];
                if (it2.locked) continue;
                var bds2 = it2.geometricBounds;
                var T2 = bds2[0], L2 = bds2[1], B2 = bds2[2], R2 = bds2[3];
                var w2 = R2 - L2;
                if (w2 >= BIG_W) continue;
                if (w2 < 1) continue;
                if (T2 < -10) continue;     // 외곽 마스터 영역 제외
                counters.total++;

                // 가까운 큰 프레임의 dx 채택 (X 거리 + Y 겹침)
                var bestDx = null, bestScore = Infinity;
                for (var bf = 0; bf < bigFrames.length; bf++) {
                    var bigF = bigFrames[bf];
                    if (Math.abs(bigF.dx) < 0.05) continue;
                    var xDist = Math.min(Math.abs(L2 - bigF.oldL), Math.abs(L2 - bigF.newL));
                    var yOverlap = Math.min(B2, bigF.B) - Math.max(T2, bigF.T);
                    var score = xDist - Math.max(0, yOverlap);
                    if (score < bestScore) {
                        bestScore = score;
                        bestDx = bigF.dx;
                    }
                }
                if (bestDx !== null && Math.abs(bestDx) > 0.05) {
                    it2.geometricBounds = [T2, L2 + bestDx, B2, R2 + bestDx];
                    counters.fixed++;
                }
            } catch(e) {}
        }
    }

    var fixed = 0, total = 0, errMsg = null;

    // ----- 본 작업 -----
    app.doScript(function() {
        if (rangeMode === 0) {
            var sel = app.selection;
            if (sel.length === 0) {
                errMsg = "선택된 항목이 없습니다.";
                return;
            }
            for (var i = 0; i < sel.length; i++) {
                var it = sel[i];
                var pg = null;
                try { pg = it.parentPage; } catch(e) {}
                if (!pg) continue;
                total++;
                if (snapItem(it, pg)) fixed++;
            }
        } else {
            var pageIdxs = [];
            if (rangeMode === 1) {
                for (var p = 0; p < doc.pages.length; p++) pageIdxs.push(p);
            } else {
                pageIdxs = parsePageRange(pageRangeStr, doc.pages.length);
                if (pageIdxs.length === 0) {
                    errMsg = "유효한 페이지 범위를 입력하세요.";
                    return;
                }
            }
            var counters = {total: 0, fixed: 0};
            for (var pi = 0; pi < pageIdxs.length; pi++) {
                processPage(doc.pages[pageIdxs[pi]], counters);
            }
            total = counters.total;
            fixed = counters.fixed;
        }
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "레이아웃 선 기준 정렬");

    // ----- 좌표계 원복 -----
    doc.viewPreferences.rulerOrigin = prevOrigin;
    doc.viewPreferences.horizontalMeasurementUnits = prevHU;
    doc.viewPreferences.verticalMeasurementUnits = prevVU;

    if (errMsg) { alert(errMsg); return; }
    alert("검사 " + total + "개 / 정렬 " + fixed + "개");
})();
