(function() {

    var doc = app.activeDocument;
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

    function getContentFrames(page) {
        var all = page.textFrames.everyItem().getElements();
        var content = [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].geometricBounds[0] > 0) { content.push(all[i]); }
        }
        content.sort(function(a, b) { return a.geometricBounds[0] - b.geometricBounds[0]; });
        return content;
    }

    function getHeaderFrames(page) {
        var all = page.textFrames.everyItem().getElements();
        var headers = [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].geometricBounds[0] <= 0) { headers.push(all[i]); }
        }
        return headers;
    }

    function getPageContentX(pg) {
        // marginPreferences.left = inside (spine) margin = 22 for ALL pages
        // marginPreferences.right = outside margin = 20 for ALL pages
        // LEFT_HAND page: outside margin is on the physical left → use .right
        // RIGHT_HAND page: inside margin is on the physical left → use .left
        return (pg.side === PageSideOptions.LEFT_HAND)
            ? pg.marginPreferences.right
            : pg.marginPreferences.left;
    }

    function movePageWithFix(pg, locOpt, anchor) {
        var oldX = getPageContentX(pg);
        pg.move(locOpt, anchor);
        var newX = getPageContentX(pg);
        var shift = newX - oldX;
        if (Math.abs(shift) > 0.01) {
            var frames = pg.textFrames.everyItem().getElements();
            for (var fi = 0; fi < frames.length; fi++) {
                var fb = frames[fi].geometricBounds;
                if (fb[0] >= 0) {
                    frames[fi].geometricBounds = [fb[0], fb[1] + shift, fb[2], fb[3] + shift];
                }
            }
        }
    }

    function isMasterNone(page) {
        var ms = page.appliedMaster;
        if (!ms) { return true; }
        var n = ms.name;
        return (n === "[없음]" || n === "[None]" || n === "none" || n === "");
    }

    // ======================================================
    // STEP 1: 구분 페이지 탐지 및 삭제
    // none-master 페이지 그룹 중 index > 100 인 것 (앞뒤 표지 제외)
    // ======================================================
    var lastIdx = doc.pages.length - 1;
    var sepGroups = [];
    var inSep = false;
    var sepStart = -1;
    for (var i = 100; i < lastIdx; i++) {
        if (isMasterNone(doc.pages[i])) {
            if (!inSep) { inSep = true; sepStart = i; }
        } else {
            if (inSep) { inSep = false; sepGroups.push([sepStart, i - 1]); }
        }
    }
    if (inSep) { sepGroups.push([sepStart, lastIdx - 1]); }

    if (sepGroups.length < 2) {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
        alert("\uAD6C\uC870 \uC624\uB958: \uAD6C\uBD84 \uD398\uC774\uC9C0 2\uC138\uD2B8\uAC00 \uBD80\uC871\uD569\uB2C8\uB2E4 (" + sepGroups.length + "\uC138\uD2B8 \uBC1C\uACAC)");
        return;
    }

    var sep1 = sepGroups[0];                         // e.g. [111, 112]
    var sep2 = sepGroups[sepGroups.length - 1];      // e.g. [177,178] or [185,186]

    // A-master sections: indices 21 ~ sep1[0]-1 = 90p → 5 sections × 18 problems
    var A_SECT_COUNT = sep1[0] - 21;                 // always 90
    var NUM_PROBLEMS = Math.round(A_SECT_COUNT / 5); // always 18

    // C-master sections: between sep1 and sep2
    var C_SIZE = sep2[0] - sep1[1] - 1;             // 64 or 72
    var C_SECT_SIZE = Math.round(C_SIZE / 4);        // 16 or 18

    // After deletion: sep1 removes 2 pages → C starts at sep1[0]
    var C_START = sep1[0];
    var OM_START_AFTER = C_START + C_SIZE;

    // 구분 페이지 삭제 (역순)
    var delPages = [];
    for (var g = sepGroups.length - 1; g >= 0; g--) {
        for (var j = sepGroups[g][1]; j >= sepGroups[g][0]; j--) {
            delPages.push(doc.pages[j]);
        }
    }
    for (var d = 0; d < delPages.length; d++) { delPages[d].remove(); }

    // ======================================================
    // STEP 2: 어휘 페이지 결합 (9쌍, 항상 indices 3-11 / 12-20)
    // ======================================================
    var aMaster = doc.masterSpreads.itemByName("A-\uB9C8\uC2A4\uD130");

    for (var pair = 0; pair < 9; pair++) {
        var pg1 = doc.pages[3 + pair];
        var pg2 = doc.pages[12 + pair];
        var cf1 = getContentFrames(pg1);
        var cf2 = getContentFrames(pg2);
        if (cf1.length < 2 || cf2.length < 2) { continue; }

        var hw1A = cf1[0]; var hw1B = cf1[1];
        var hw2A = cf2[0]; var hw2B = cf2[1];

        // Read ALL bounds before any move/resize
        var b1A = hw1A.geometricBounds;
        var b1B = hw1B.geometricBounds;
        var b2A = hw2A.geometricBounds;
        var b2B = hw2B.geometricBounds;

        var x1 = b1A[1];  // actual left-x of pg1 frames (outer margin for left page, inner for right)
        var x2 = b2B[1];  // actual left-x of pg2 frames

        // hw1A: stays on pg1 at top position (no change)

        // hw2A: move from pg2 → pg1 bottom position
        hw2A.move(pg1);
        hw2A.geometricBounds = [b1B[0], x1, b1B[0] + (b2A[2]-b2A[0]), x1 + (b2A[3]-b2A[1])];

        // hw1B: move from pg1 → pg2 top position
        hw1B.move(pg2);
        hw1B.geometricBounds = [b2A[0], x2, b2A[0] + (b1B[2]-b1B[0]), x2 + (b1B[3]-b1B[1])];

        // hw2B: stays on pg2 at bottom position (no change)

        var hdr1 = getHeaderFrames(pg1);
        var hdr2 = getHeaderFrames(pg2);
        for (var hh = 0; hh < hdr1.length; hh++) { hdr1[hh].remove(); }
        for (var hh = 0; hh < hdr2.length; hh++) { hdr2[hh].remove(); }

        if (aMaster.isValid) { pg2.appliedMaster = aMaster; }
    }

    // ======================================================
    // STEP 3: O/M 섹션 그룹화
    // OM_START_AFTER 이후부터 마지막-1 페이지까지 스캔
    // ======================================================
    var omGroups = [];
    var curGroup = null;
    for (var i = OM_START_AFTER; i < doc.pages.length - 1; i++) {
        var pg = doc.pages[i];
        var frames = pg.textFrames.everyItem().getElements();
        var hasCode = false;
        for (var f = 0; f < frames.length; f++) {
            try {
                if (/^\{[^}]+\}/.test(frames[f].contents)) { hasCode = true; break; }
            } catch(e) {}
        }
        if (hasCode) {
            curGroup = [pg];
            omGroups.push(curGroup);
        } else if (curGroup) {
            curGroup.push(pg);
        }
    }

    // ======================================================
    // STEP 4: 페이지 레이블 설정 (재배치 추적용)
    // ======================================================
    var PFX = "__cv_";

    // 어휘 (9쌍 = 18문제)
    for (var i = 0; i < 9; i++) {
        doc.pages[3 + i].label = PFX + "hw_" + (i * 2);
        doc.pages[12 + i].label = PFX + "hw_" + (i * 2 + 1);
    }

    // A-master 5개 섹션 (각 NUM_PROBLEMS 페이지)
    var aSecNames = ["ox", "title", "content", "insert", "blank"];
    for (var s = 0; s < aSecNames.length; s++) {
        for (var k = 0; k < NUM_PROBLEMS; k++) {
            doc.pages[21 + s * NUM_PROBLEMS + k].label = PFX + aSecNames[s] + "_" + k;
        }
    }

    // C-master 4개 섹션 (각 C_SECT_SIZE 페이지)
    var cSecNames = ["grammar", "grammarox", "blankgrammar", "arrange"];
    for (var s = 0; s < cSecNames.length; s++) {
        for (var k = 0; k < C_SECT_SIZE; k++) {
            doc.pages[C_START + s * C_SECT_SIZE + k].label = PFX + cSecNames[s] + "_" + k;
        }
    }

    // O/M 페이지
    for (var g = 0; g < omGroups.length; g++) {
        for (var p = 0; p < omGroups[g].length; p++) {
            omGroups[g][p].label = PFX + "om_" + g + "_" + p;
        }
    }

    function buildLabelMap() {
        var map = {};
        for (var i = 0; i < doc.pages.length; i++) {
            var lbl = doc.pages[i].label;
            if (lbl && lbl.indexOf(PFX) === 0) { map[lbl] = doc.pages[i]; }
        }
        return map;
    }

    // ======================================================
    // STEP 5: 페이지 재배치
    // 세로(C) 구조: 각 문제마다 [hw, ox, title, content, insert, blank,
    //                             grammar, grammarox, blankgrammar, arrange, om...]
    // ======================================================
    var insertAnchor = doc.pages[2];
    var locAfter = LocationOptions.AFTER;

    for (var k = 0; k < NUM_PROBLEMS; k++) {
        var lmap = buildLabelMap();
        var pages_k = [];
        pages_k.push(lmap[PFX + "hw_" + k]);
        pages_k.push(lmap[PFX + "ox_" + k]);
        pages_k.push(lmap[PFX + "title_" + k]);
        pages_k.push(lmap[PFX + "content_" + k]);
        pages_k.push(lmap[PFX + "insert_" + k]);
        pages_k.push(lmap[PFX + "blank_" + k]);
        pages_k.push(lmap[PFX + "grammar_" + k]);
        pages_k.push(lmap[PFX + "grammarox_" + k]);
        pages_k.push(lmap[PFX + "blankgrammar_" + k]);
        pages_k.push(lmap[PFX + "arrange_" + k]);

        if (omGroups[k]) {
            for (var p = 0; p < omGroups[k].length; p++) {
                var omPage = lmap[PFX + "om_" + k + "_" + p];
                if (omPage && omPage.isValid) { pages_k.push(omPage); }
            }
        }

        // Forward-order insertion: each page placed AFTER the previous page.
        for (var j = 0; j < pages_k.length; j++) {
            var pg = pages_k[j];
            if (pg && pg.isValid) {
                pg.move(locAfter, insertAnchor);
                insertAnchor = pg;
            }
        }
    }

    // ======================================================
    // STEP 6: 레이블 정리
    // ======================================================
    for (var i = 0; i < doc.pages.length; i++) {
        if (doc.pages[i].label && doc.pages[i].label.indexOf(PFX) === 0) {
            doc.pages[i].label = "";
        }
    }

    // ======================================================
    // STEP 6.5: 프레임 x위치 보정
    // 원본: L페이지 x=20, R페이지 x=22. 목표: 복원
    // pg.move() 이후 InDesign 자동보정 결과:
    //   L: x≈22 → 20 (-2)
    //   R: x≈24 → 22 (-2), x≈20 → 22 (+2)
    // ======================================================
    for (var i = 0; i < doc.pages.length; i++) {
        var pg6 = doc.pages[i];
        var isL6 = (pg6.side === PageSideOptions.LEFT_HAND);
        var frames6 = pg6.textFrames.everyItem().getElements();
        for (var f6 = 0; f6 < frames6.length; f6++) {
            try {
                var fb6 = frames6[f6].geometricBounds;
                if (fb6[0] <= 0) { continue; }
                var x6 = fb6[1];
                var shift6 = 0;
                if (isL6  && x6 > 21.4 && x6 < 22.6) { shift6 = -2; }
                else if (!isL6 && x6 > 23.4 && x6 < 24.6) { shift6 = -2; }
                else if (!isL6 && x6 > 19.4 && x6 < 20.6) { shift6 =  2; }
                if (shift6 !== 0) {
                    frames6[f6].geometricBounds = [fb6[0], fb6[1]+shift6, fb6[2], fb6[3]+shift6];
                }
            } catch(e) {}
        }
    }

    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
    alert("\uBCC0\uD658 \uC644\uB8CC! \uD398\uC774\uC9C0 \uC218: " + doc.pages.length);

})();
