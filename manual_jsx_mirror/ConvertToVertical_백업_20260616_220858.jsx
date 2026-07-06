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

    var sep1 = sepGroups[0];                         // A↔C 경계, e.g. [111, 112]
    var sep2 = sepGroups[1];                         // C↔O/M 경계, e.g. [185, 186]

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

    // ======================================================
    // STEP 7: 모든 스토리 연결 끊기
    // ======================================================
    var allTF = doc.textFrames.everyItem().getElements();
    for (var i7 = 0; i7 < allTF.length; i7++) {
        try { allTF[i7].nextTextFrame = null; } catch(e) {}
        try { allTF[i7].previousTextFrame = null; } catch(e) {}
    }

    // ======================================================
    // STEP 8: O-마스터 지문별 스토리 재연결
    // 라벨 __cv_om_k_p 를 활용하여 각 문제(k)의 O/M 페이지를 찾고
    // 페이지 내 콘텐츠 프레임(y>0)을 순서대로 연결
    // ======================================================
    var lmapOM = buildLabelMap();
    for (var k8 = 0; k8 < NUM_PROBLEMS; k8++) {
        var omFrames8 = [];
        // om 그룹의 페이지 수를 모르므로 라벨로 탐색
        for (var p8 = 0; p8 < 20; p8++) {
            var omPg = lmapOM[PFX + "om_" + k8 + "_" + p8];
            if (!omPg || !omPg.isValid) break;
            var pgFrames = omPg.textFrames.everyItem().getElements();
            var cfArr = [];
            for (var cf8 = 0; cf8 < pgFrames.length; cf8++) {
                if (pgFrames[cf8].geometricBounds[0] > 0) {
                    cfArr.push(pgFrames[cf8]);
                }
            }
            cfArr.sort(function(a, b) { return a.geometricBounds[0] - b.geometricBounds[0]; });
            for (var c8 = 0; c8 < cfArr.length; c8++) {
                omFrames8.push(cfArr[c8]);
            }
        }
        // 순서대로 연결
        for (var f8 = 0; f8 < omFrames8.length - 1; f8++) {
            try {
                omFrames8[f8].nextTextFrame = omFrames8[f8 + 1];
            } catch(e) {}
        }
    }

    // ======================================================
    // STEP 6: 레이블 정리 (STEP 8 이후로 이동됨)
    // ======================================================
    for (var i = 0; i < doc.pages.length; i++) {
        if (doc.pages[i].label && doc.pages[i].label.indexOf(PFX) === 0) {
            doc.pages[i].label = "";
        }
    }

    // ======================================================
    // STEP 9: STEP1.ai → STEP123.ai 링크 변경
    // ======================================================
    var step123File = new File("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\uB0B4 \uB4DC\uB77C\uC774\uBE0C/\uCF58\uD150\uCE20 \uAD00\uB9AC/\uB0B4\uC2E0\uB300\uBE44/\uC778\uB514\uC790\uC778 \uD30C\uC77C/\uC774\uBBF8\uC9C0/\uC6CC\uD06C\uBD81/C\uBC84\uC804/STEP123.ai");
    if (step123File.exists) {
        for (var lk = doc.links.length - 1; lk >= 0; lk--) {
            try {
                if (doc.links[lk].name === "STEP1.ai") {
                    doc.links[lk].relink(step123File);
                    doc.links[lk].update();
                }
            } catch(e) {}
        }
    }

    // ======================================================
    // STEP 10: Master 원본 열기 + 마스터/스타일 동기화
    // ======================================================
    var masterFile = new File("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\uB0B4 \uB4DC\uB77C\uC774\uBE0C/\uCF58\uD150\uCE20 \uAD00\uB9AC/\uB0B4\uC2E0\uB300\uBE44/\uC778\uB514\uC790\uC778 \uD30C\uC77C/\uC6CC\uD06C\uBD81/\uBAA8\uC758\uACE0\uC0AC/\uB0B4\uC9C0/[\uC6D0\uBCF8]\uC6CC\uD06C\uBD81_C\uC138\uB85C(\uBAA8\uC758\uACE0\uC0AC)_\uB0B4\uC9C0.indd");
    if (masterFile.exists) {
        var sourceDoc = app.open(masterFile);
        // MASTER_SOURCE 라벨 설정 (없을 경우만)
        if (sourceDoc.extractLabel("MASTER_SOURCE") !== "YES") {
            sourceDoc.insertLabel("MASTER_SOURCE", "YES");
        }

        // 대상 문서(변환된 파일)에 마스터/스타일 동기화
        try {
            _unlockEverything(sourceDoc);
            _unlockEverything(doc);
            _syncLayers(sourceDoc, doc);
            _finalPhysicalSync(sourceDoc, doc);
            _syncStyles(sourceDoc, doc);
            _applyCMasterExceptFirst(doc);
            _applyGanjiToFirstPage(doc);
            _remapGanjiCharacterStyles(doc);
            _setFirstPageItemsYToZero(doc);
            _relinkSpecialImages(doc);
        } catch(e) {}

        // 원본 닫기 (저장 안 함)
        sourceDoc.close(SaveOptions.NO);
    }

    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
    alert("\uBCC0\uD658 \uC644\uB8CC! \uD398\uC774\uC9C0 \uC218: " + doc.pages.length);

    // ======================================================
    // Master 동기화 헬퍼 함수들
    // ======================================================
    function _unlockEverything(d) {
        try { d.layers.everyItem().locked = false; } catch(e) {}
        try { d.layers.everyItem().visible = true; } catch(e) {}
        try { d.masterSpreads.everyItem().pageItems.everyItem().locked = false; } catch(e) {}
    }

    function _syncLayers(src, tgt) {
        for (var i = src.layers.length - 1; i >= 0; i--) {
            if (!tgt.layers.itemByName(src.layers[i].name).isValid) {
                tgt.layers.add({name: src.layers[i].name});
            }
        }
    }

    function _finalPhysicalSync(src, tgt) {
        var appliedBackup = [];
        for (var i = 0; i < tgt.pages.length; i++) {
            try {
                appliedBackup[i] = tgt.pages[i].appliedMaster
                    ? tgt.pages[i].appliedMaster.name : null;
            } catch(e) { appliedBackup[i] = null; }
        }
        try { tgt.loadMasters(src.fullName); } catch(e) { return; }

        var sourceNameMap = {};
        for (var s = 0; s < src.masterSpreads.length; s++) {
            var sM = src.masterSpreads[s];
            if (sM.name === "[None]" || sM.name === "[\uC5C6\uC74C]") continue;
            sourceNameMap[sM.name] = true;
        }
        for (var p = 0; p < tgt.pages.length; p++) {
            var oldName = appliedBackup[p];
            try {
                if (!oldName) {
                    tgt.pages[p].appliedMaster = NothingEnum.NOTHING;
                } else if (sourceNameMap[oldName]) {
                    var restored = tgt.masterSpreads.itemByName(oldName);
                    if (restored && restored.isValid) {
                        tgt.pages[p].appliedMaster = restored;
                    } else { tgt.pages[p].appliedMaster = NothingEnum.NOTHING; }
                } else { tgt.pages[p].appliedMaster = NothingEnum.NOTHING; }
            } catch(e) {}
        }
        for (var i = tgt.masterSpreads.length - 1; i >= 0; i--) {
            var m = tgt.masterSpreads[i];
            if (m.name === "[None]" || m.name === "[\uC5C6\uC74C]") continue;
            if (sourceNameMap[m.name]) continue;
            try { m.remove(); } catch(e) {}
        }
    }

    function _syncStyles(src, tgt) {
        try {
            tgt.importStyles(ImportFormat.PARAGRAPH_STYLES_FORMAT,
                src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
        } catch(e) {}
        try {
            tgt.importStyles(ImportFormat.CHARACTER_STYLES_FORMAT,
                src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
        } catch(e) {}
    }

    function _applyCMasterExceptFirst(d) {
        var cMaster = null;
        for (var i = 0; i < d.masterSpreads.length; i++) {
            if (/^C($|[\- _])/i.test(d.masterSpreads[i].name)) {
                cMaster = d.masterSpreads[i]; break;
            }
        }
        if (!cMaster) return;
        for (var p = 1; p < d.pages.length; p++) {
            try { d.pages[p].appliedMaster = cMaster; } catch(e) {}
        }
    }

    function _applyGanjiToFirstPage(d) {
        if (d.pages.length === 0) return;
        var firstPage = d.pages[0];
        var items = firstPage.pageItems.everyItem().getElements();
        for (var i = items.length - 1; i >= 0; i--) {
            try {
                var item = items[i];
                var keep = false;
                if (!(item instanceof TextFrame)) { item.remove(); continue; }
                if (item.texts.length > 0) {
                    var chars = item.texts[0].characters;
                    for (var c = 0; c < chars.length; c++) {
                        try {
                            var cs = chars[c].appliedCharacterStyle;
                            if (cs.parent && cs.parent.constructor.name === "CharacterStyleGroup"
                                && cs.parent.name === "\uAC04\uC9C0") { keep = true; break; }
                        } catch(e) {}
                    }
                }
                if (!keep) item.remove();
            } catch(e) {}
        }
        var ganjiMaster = null;
        for (var m = 0; m < d.masterSpreads.length; m++) {
            if (d.masterSpreads[m].name === "\uAC04\uC9C0-\uB9C8\uC2A4\uD130") {
                ganjiMaster = d.masterSpreads[m]; break;
            }
        }
        if (ganjiMaster) {
            try { firstPage.appliedMaster = ganjiMaster; } catch(e) {}
        }
    }

    function _remapGanjiCharacterStyles(d) {
        function getCS(gn, sn) {
            try {
                var grp = d.characterStyleGroups.itemByName(gn);
                if (!grp.isValid) return null;
                var st = grp.characterStyles.itemByName(sn);
                return st.isValid ? st : null;
            } catch(e) { return null; }
        }
        function replace(fromS, toS) {
            app.findTextPreferences = NothingEnum.NOTHING;
            app.changeTextPreferences = NothingEnum.NOTHING;
            app.findTextPreferences.appliedCharacterStyle = fromS;
            app.changeTextPreferences.appliedCharacterStyle = toS;
            try { d.changeText(); } catch(e) {}
            app.findTextPreferences = NothingEnum.NOTHING;
            app.changeTextPreferences = NothingEnum.NOTHING;
        }
        var f1 = getCS("\uAC04\uC9C0", "\uCE74\uD14C\uACE0\uB9AC");
        var t1 = getCS("\uAC04\uC9C0", "\uBC94\uC704");
        if (f1 && t1) replace(f1, t1);
        var f2 = getCS("\uAC04\uC9C0", "\uBD80\uC81C\uBAA9");
        var t2 = getCS("\uAC04\uC9C0", "\uBC94\uC704_\uCD94\uAC00\uB0B4\uC6A9");
        if (f2 && t2) replace(f2, t2);
    }

    function _setFirstPageItemsYToZero(d) {
        if (d.pages.length === 0) return;
        var p = d.pages[0];
        var items = p.pageItems.everyItem().getElements();
        for (var i = 0; i < items.length; i++) {
            try {
                try { items[i].locked = false; } catch(e) {}
                var gb = items[i].geometricBounds;
                if (!gb || gb.length !== 4) continue;
                var h = gb[2] - gb[0];
                items[i].geometricBounds = [0 - h, gb[1], 0, gb[3]];
            } catch(e) {}
        }
    }

    function _relinkSpecialImages(d) {
        var baseFolder = Folder("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\uB0B4 \uB4DC\uB77C\uC774\uBE0C/\uCF58\uD150\uCE20 \uAD00\uB9AC/\uB0B4\uC2E0\uB300\uBE44/\uC778\uB514\uC790\uC778 \uD30C\uC77C/\uC774\uBBF8\uC9C0/\uC6CC\uD06C\uBD81/C\uBC84\uC804");
        if (!baseFolder.exists) return;
        var allFiles = [];
        var stack = [baseFolder];
        while (stack.length > 0) {
            var cur = stack.pop();
            var items = cur.getFiles();
            for (var s = 0; s < items.length; s++) {
                if (items[s] instanceof Folder) stack.push(items[s]);
                else if (items[s] instanceof File) allFiles.push(items[s]);
            }
        }
        function normName(name) {
            var n = name;
            n = n.replace("(B)", "");
            n = n.replace(/^간지_/, "");
            n = n.replace(/간지(?=\.[^.]+$)/, "");
            n = n.replace(/^마지막P(?=\.[^.]+$)/, "LastP");
            return n;
        }
        var links = d.links;
        for (var i = 0; i < links.length; i++) {
            var lk = links[i];
            var origName = lk.name;
            var tgtName = normName(origName);
            for (var f = 0; f < allFiles.length; f++) {
                if (allFiles[f].name === origName || normName(allFiles[f].name) === tgtName) {
                    try { lk.relink(allFiles[f]); lk.update(); } catch(e) {}
                    break;
                }
            }
        }
    }

})();
