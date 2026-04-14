#target indesign

(function () {

    var settingsPath = "__SETTINGS_PATH__";
    var sf = new File(settingsPath);
    sf.encoding = "UTF-8"; sf.open("r");
    var settings = eval("(" + sf.read() + ")");
    sf.close();

    var logFilePath = settingsPath.replace(".settings.json", "typeset_log.txt");
    var logLines = [];
    function log(msg) { logLines.push(msg); }
    function saveLog() {
        var lf = new File(logFilePath);
        lf.encoding = "UTF-8"; lf.open("w"); lf.write(logLines.join("\n")); lf.close();
    }

    var origUI = app.scriptPreferences.userInteractionLevel;
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

    var jobs = settings.jobs || [];
    log("=== \ud55c\uc601\ubcf4\uce74 \uc870\ud310 ===");
    log("\uc791\uc5c5: " + jobs.length + "\uac1c");

    for (var ji = 0; ji < jobs.length; ji++) {
        try { _processJob(jobs[ji]); }
        catch (ex) { log("[\uc624\ub958] " + ex.message); }
    }

    app.scriptPreferences.userInteractionLevel = origUI;
    saveLog();

    // =====================================================================
    function _processJob(job) {
        var cf = new File(job.json_path);
        cf.encoding = "UTF-8"; cf.open("r");
        var content = eval("(" + cf.read() + ")");
        cf.close();

        var layoutName = content.layout || "?";
        var isSero = (layoutName === "\uc138\ub85c\ud615");
        log("\n--- " + layoutName + " ---");

        var totalEntries = 0;
        for (var ci = 0; ci < content.chapters.length; ci++)
            for (var si2 = 0; si2 < content.chapters[ci].sections.length; si2++)
                totalEntries += content.chapters[ci].sections[si2].count;
        log("\ub2e8\uc6d0: " + content.chapters.length + " | \ub2e8\uc5b4: " + totalEntries);

        var doc = app.open(File(job.indd_path));

        // ── 마스터 ─────────────────────────────────────────
        var masterI = null, masterA = null;
        for (var mi = 0; mi < doc.masterSpreads.length; mi++) {
            var n = doc.masterSpreads[mi].name;
            if (n.charAt(0) === "I") masterI = doc.masterSpreads[mi];
            if (n.charAt(0) === "A") masterA = doc.masterSpreads[mi];
        }

        // ── 텍스트변수 "단원" ──────────────────────────────
        var tvChapter = null;
        try { tvChapter = doc.textVariables.itemByName("\ub2e8\uc6d0");
              if (!tvChapter.isValid) tvChapter = null; } catch (e) {}

        // ── 문자스타일 "단원" ──────────────────────────────
        var csChapter = null;
        try { csChapter = doc.characterStyles.itemByName("\ub2e8\uc6d0"); } catch (e) {}
        if (csChapter && !csChapter.isValid) csChapter = null;

        // ── 표 정보 수집 ───────────────────────────────────
        var refTable = null;
        for (var i = 0; i < doc.pages.length && !refTable; i++)
            for (var j = 0; j < doc.pages[i].textFrames.length; j++)
                if (doc.pages[i].textFrames[j].tables.length > 0) {
                    refTable = doc.pages[i].textFrames[j].tables[0]; break;
                }
        if (!refTable) { log("[\uc624\ub958] \ud45c \uc5c6\uc74c"); doc.close(SaveOptions.NO); return; }

        var colCount = refTable.columns.length;
        var stdH = refTable.rows.length > 1 ? refTable.rows[1].height : 7;
        var hasDef = (colCount >= 6);
        var COL_W = 0, COL_M = 1;
        var COL_D = hasDef ? 2 : -1;
        var COL_S = hasDef ? 3 : 2;
        var COL_A = hasDef ? 4 : 3;
        var LAST = hasDef ? 4 : 3;
        log("\uc5f4: " + colCount + (hasDef ? "(\uc601\uc601\ud480\uc774)" : "") + " stdH: " + stdH.toFixed(1));

        // ── 섹션 초기화 ────────────────────────────────────
        while (doc.sections.length > 1) doc.sections[doc.sections.length - 1].remove();
        doc.sections[0].marker = "";

        // ── 모든 페이지 A-마스터 + 데이터 초기화 ──────────
        for (var i = 1; i < doc.pages.length; i++) {
            var pg = doc.pages[i];
            if (masterA) try { pg.appliedMaster = masterA; } catch (e) {}
            for (var j = 0; j < pg.textFrames.length; j++) {
                var tf = pg.textFrames[j];
                if (tf.tables.length > 0) {
                    var tbl = tf.tables[0];
                    for (var r = 1; r < tbl.rows.length; r++)
                        for (var c = 0; c <= LAST; c++)
                            try { tbl.cells.item(r * colCount + c).contents = ""; } catch (e) {}
                } else {
                    try { tf.contents = ""; } catch (e) {}
                }
            }
        }

        // ── 표 수집 ────────────────────────────────────────
        var allTables = [];
        for (var i = 0; i < doc.pages.length; i++) {
            var pg = doc.pages[i];
            for (var j = 0; j < pg.textFrames.length; j++)
                if (pg.textFrames[j].tables.length > 0)
                    allTables.push({ table: pg.textFrames[j].tables[0], page: pg.name, pageObj: pg });
        }
        log("\ud45c: " + allTables.length);

        // ── 데이터 채우기 ──────────────────────────────────
        var tableIdx = 0, rowIdx = 1, filledCount = 0;
        var currentChapter = "";
        var isFirstSection = true;

        for (var chi = 0; chi < content.chapters.length; chi++) {
            var chapter = content.chapters[chi];

            for (var si = 0; si < chapter.sections.length; si++) {
                var section = chapter.sections[si];

                // 테이블이 꽉 찼으면 다음으로
                if (tableIdx < allTables.length && rowIdx >= allTables[tableIdx].table.rows.length) {
                    tableIdx++; rowIdx = 1;
                }
                // 가로형: 각 섹션마다 새 테이블
                if (!isSero && !isFirstSection && rowIdx > 1) {
                    tableIdx++; rowIdx = 1;
                }
                isFirstSection = false;
                if (tableIdx >= allTables.length) { log("[\uacbd\uace0] \ud45c \ubd80\uc871!"); break; }

                var curPage = allTables[tableIdx].pageObj;

                // 세로형: I-마스터 적용
                if (isSero && masterI)
                    try { curPage.appliedMaster = masterI; } catch (e) {}

                // 단원 헤더
                if (chapter.name !== currentChapter) {
                    currentChapter = chapter.name;
                    if (tvChapter) try { tvChapter.variableOptions.contents = currentChapter; } catch (e) {}
                    // 페이지 헤더 텍스트 프레임
                    for (var fi = 0; fi < curPage.textFrames.length; fi++) {
                        var htf = curPage.textFrames[fi];
                        if (htf.tables.length === 0) {
                            try {
                                htf.contents = currentChapter;
                                if (csChapter && htf.characters.length > 0)
                                    htf.characters.everyItem().appliedCharacterStyle = csChapter;
                            } catch (e) {}
                            break;
                        }
                    }
                    log(currentChapter + " (" + chapter.total + "\uac1c)");
                }

                // 섹션 표시자
                if (section.name) {
                    var found = false;
                    for (var k = 0; k < doc.sections.length; k++) {
                        if (doc.sections[k].pageStart === curPage) {
                            doc.sections[k].marker = section.name; found = true; break;
                        }
                    }
                    if (!found) {
                        try {
                            var ns = doc.sections.add(curPage);
                            ns.marker = section.name;
                            ns.continueNumbering = true;
                        } catch (e) {}
                    }
                }

                log("  [" + section.name + "] " + section.count + "\uac1c (p" + allTables[tableIdx].page + ")");

                // 엔트리 채우기
                for (var ei = 0; ei < section.entries.length; ei++) {
                    if (tableIdx >= allTables.length) break;
                    var tbl = allTables[tableIdx].table;
                    if (rowIdx >= tbl.rows.length) {
                        tableIdx++; rowIdx = 1;
                        if (tableIdx >= allTables.length) break;
                        tbl = allTables[tableIdx].table;
                    }
                    var en = section.entries[ei];
                    var b = rowIdx * colCount;
                    try {
                        tbl.cells.item(b + COL_W).contents = en.word || "";
                        tbl.cells.item(b + COL_M).contents = en.meaning || "";
                        if (COL_D >= 0) tbl.cells.item(b + COL_D).contents = en.definition || "";
                        tbl.cells.item(b + COL_S).contents = en.synonym || "";
                        tbl.cells.item(b + COL_A).contents = en.antonym || "";
                    } catch (ex) {}
                    rowIdx++; filledCount++;
                }
            }
        }
        log("\ucc44\uc6b0\uae30: " + filledCount + "/" + totalEntries);

        // ── 행 높이 통일 + autoGrow ────────────────────────
        for (var t = 0; t < allTables.length; t++) {
            var tbl = allTables[t].table;
            for (var r = 1; r < tbl.rows.length; r++) {
                try { tbl.rows[r].height = stdH; tbl.rows[r].autoGrow = true; } catch (e) {}
            }
        }

        // ── 빈 페이지 삭제 ─────────────────────────────────
        if (tableIdx < allTables.length) {
            var lastPageName = allTables[Math.min(tableIdx, allTables.length - 1)].page;
            var lastPageIdx = -1;
            for (var i = 0; i < doc.pages.length; i++)
                if (doc.pages[i].name === lastPageName) lastPageIdx = i;
            var removed = 0;
            while (doc.pages.length > lastPageIdx + 2 && doc.pages.length > 2) {
                try { doc.pages[doc.pages.length - 1].remove(); removed++; } catch (e) { break; }
            }
            if (removed > 0) log("\ube48\ud398\uc774\uc9c0 " + removed + "\uac1c \uc0ad\uc81c");
        }

        // ── 오버플로우 해결 ────────────────────────────────
        for (var i = 0; i < doc.stories.length; i++) {
            if (doc.stories[i].overflows) {
                var frames = doc.stories[i].textContainers;
                for (var fi = 0; fi < frames.length; fi++) {
                    try {
                        var fr = frames[fi];
                        if (fr.tables.length > 0) {
                            var geo = fr.geometricBounds;
                            var need = geo[0] + fr.tables[0].height + 1;
                            if (need > geo[2]) fr.geometricBounds = [geo[0], geo[1], need, geo[3]];
                        }
                    } catch (e) {}
                }
            }
        }
        var ov = 0;
        for (var i = 0; i < doc.stories.length; i++) if (doc.stories[i].overflows) ov++;
        log("\uc624\ubc84\ud50c\ub85c\uc6b0: " + ov);

        // ── PDF ────────────────────────────────────────────
        try {
            var pdfName = doc.name.replace(/\.indd$/i, ".pdf");
            var pdfFile = new File(settingsPath.replace(".settings.json", pdfName));
            doc.exportFile(ExportFormat.PDF_TYPE, pdfFile);
            log("PDF: \uc131\uacf5 (" + pdfName + ")");
        } catch (ex) { log("PDF: \uc2e4\ud328 - " + ex.message); }

        try { doc.save(); } catch (e) {}
        doc.close(SaveOptions.NO);
    }
})();
