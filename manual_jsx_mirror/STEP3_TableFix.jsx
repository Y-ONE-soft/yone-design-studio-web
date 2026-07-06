// STEP3_TableFix.jsx
// ① [N] 단락 전체 삭제
// ② 표 너비 → 텍스트 프레임 내폭에 비례 맞춤
// ③ 셀 스타일 "STEP3 선지 셀" 생성 (선택 셀 테두리 기준)
// ④ 문서 내 모든 표에 셀 스타일 적용
//
// 실행 전 준비: 이미 테두리를 수정한 기준 표의 셀 하나를 클릭한 뒤 실행

#target "InDesign"

(function () {
    var doc = app.activeDocument;

    // ════════════════════════════════════════════
    // 기준 셀 획득 (선택 → 커서 위치 → 에러)
    // ════════════════════════════════════════════
    function getSelectedCell() {
        try {
            var sel = app.selection[0];
            if (!sel) return null;
            // 직접 셀 선택
            if (sel.constructor && sel.constructor.name === "Cell") return sel;
            // 텍스트 커서가 셀 안에 있는 경우 (InsertionPoint 등)
            var obj = sel;
            for (var d = 0; d < 8; d++) {
                try { obj = obj.parent; } catch (e) { break; }
                if (!obj || !obj.isValid) break;
                if (obj.constructor && obj.constructor.name === "Cell") return obj;
            }
        } catch (e) {}
        return null;
    }

    var refCell = getSelectedCell();
    if (!refCell) {
        alert("기준 표의 셀을 클릭한 뒤 실행하세요.\n(테두리를 이미 수정한 표의 셀)");
        exit();
    }

    // ════════════════════════════════════════════
    // 기준 셀 테두리 설정 읽기
    // ════════════════════════════════════════════
    function sg(fn) { try { var v = fn(); return (v !== undefined && v !== null) ? v : null; } catch (e) { return null; } }

    var ref = {
        topColor:    sg(function () { return refCell.topEdgeStrokeColor; }),
        topWeight:   sg(function () { return refCell.topEdgeStrokeWeight; }),
        topType:     sg(function () { return refCell.topEdgeStrokeType; }),
        botColor:    sg(function () { return refCell.bottomEdgeStrokeColor; }),
        botWeight:   sg(function () { return refCell.bottomEdgeStrokeWeight; }),
        botType:     sg(function () { return refCell.bottomEdgeStrokeType; }),
        leftColor:   sg(function () { return refCell.leftEdgeStrokeColor; }),
        leftWeight:  sg(function () { return refCell.leftEdgeStrokeWeight; }),
        leftType:    sg(function () { return refCell.leftEdgeStrokeType; }),
        rightColor:  sg(function () { return refCell.rightEdgeStrokeColor; }),
        rightWeight: sg(function () { return refCell.rightEdgeStrokeWeight; }),
        rightType:   sg(function () { return refCell.rightEdgeStrokeType; }),
        rowColor:    sg(function () { return refCell.rowStrokeColor; }),
        rowWeight:   sg(function () { return refCell.rowStrokeWeight; }),
        rowType:     sg(function () { return refCell.rowStrokeType; }),
        colColor:    sg(function () { return refCell.columnStrokeColor; }),
        colWeight:   sg(function () { return refCell.columnStrokeWeight; }),
        colType:     sg(function () { return refCell.columnStrokeType; })
    };

    // ════════════════════════════════════════════
    // 셀 스타일 생성 / 업데이트
    // ════════════════════════════════════════════
    var STYLE_NAME = "STEP3 선지 셀";
    var cs;
    try {
        cs = doc.cellStyles.itemByName(STYLE_NAME);
        if (!cs || !cs.isValid) throw 0;
    } catch (e) {
        cs = doc.cellStyles.add();
        cs.name = STYLE_NAME;
    }

    function ts(fn) { try { fn(); } catch (e) {} }

    if (ref.topColor)    ts(function () { cs.topEdgeStrokeColor    = ref.topColor; });
    if (ref.topWeight)   ts(function () { cs.topEdgeStrokeWeight   = ref.topWeight; });
    if (ref.topType)     ts(function () { cs.topEdgeStrokeType     = ref.topType; });
    if (ref.botColor)    ts(function () { cs.bottomEdgeStrokeColor = ref.botColor; });
    if (ref.botWeight)   ts(function () { cs.bottomEdgeStrokeWeight = ref.botWeight; });
    if (ref.botType)     ts(function () { cs.bottomEdgeStrokeType  = ref.botType; });
    if (ref.leftColor)   ts(function () { cs.leftEdgeStrokeColor   = ref.leftColor; });
    if (ref.leftWeight)  ts(function () { cs.leftEdgeStrokeWeight  = ref.leftWeight; });
    if (ref.leftType)    ts(function () { cs.leftEdgeStrokeType    = ref.leftType; });
    if (ref.rightColor)  ts(function () { cs.rightEdgeStrokeColor  = ref.rightColor; });
    if (ref.rightWeight) ts(function () { cs.rightEdgeStrokeWeight = ref.rightWeight; });
    if (ref.rightType)   ts(function () { cs.rightEdgeStrokeType   = ref.rightType; });
    if (ref.rowColor)    ts(function () { cs.rowStrokeColor        = ref.rowColor; });
    if (ref.rowWeight)   ts(function () { cs.rowStrokeWeight       = ref.rowWeight; });
    if (ref.rowType)     ts(function () { cs.rowStrokeType         = ref.rowType; });
    if (ref.colColor)    ts(function () { cs.columnStrokeColor     = ref.colColor; });
    if (ref.colWeight)   ts(function () { cs.columnStrokeWeight    = ref.colWeight; });
    if (ref.colType)     ts(function () { cs.columnStrokeType      = ref.colType; });

    // ════════════════════════════════════════════
    // ① [N] 단락 삭제 (모든 스토리)
    // ════════════════════════════════════════════
    var delCount = 0;
    var allStories = doc.stories;

    for (var si = 0; si < allStories.length; si++) {
        try {
            var story = allStories[si];
            if (!story || !story.isValid) continue;
            // 텍스트 컨테이너가 없는 스토리(마스터 등) 스킵
            try { if (!story.textContainers || story.textContainers.length === 0) continue; } catch (e) { continue; }

            var fb = app.findGrepPreferences.properties;
            var cb = app.changeGrepPreferences.properties;
            app.findGrepPreferences  = NothingEnum.NOTHING;
            app.changeGrepPreferences = NothingEnum.NOTHING;

            // ^\[\d+\]\s*\r  — [1], [3], [4] 등 단독 단락 (뒤 공백 허용)
            app.findGrepPreferences.findWhat   = "^\\[\\d+\\]\\s*\\r";
            app.changeGrepPreferences.changeTo = "";

            try {
                var found = story.findGrep();
                delCount += found ? found.length : 0;
                story.changeGrep();
            } catch (e) {}

            app.findGrepPreferences  = NothingEnum.NOTHING;
            app.changeGrepPreferences = NothingEnum.NOTHING;
            try { app.findGrepPreferences.properties  = fb; } catch (e) {}
            try { app.changeGrepPreferences.properties = cb; } catch (e) {}
        } catch (e) {}
    }

    // ════════════════════════════════════════════
    // ② 표 너비 조정 + ③ 셀 스타일 적용
    // ════════════════════════════════════════════
    var tblCount  = 0;
    var skipCount = 0;

    for (var si = 0; si < allStories.length; si++) {
        try {
            var story = allStories[si];
            if (!story || !story.isValid) continue;

            var tables = story.tables;
            if (!tables || tables.length === 0) continue;

            // 이 스토리의 텍스트 프레임 내폭 계산
            var contentWidth = null;
            try {
                var containers = story.textContainers;
                for (var ci = 0; ci < containers.length; ci++) {
                    var fr = containers[ci];
                    if (!fr || !fr.isValid) continue;
                    var b   = fr.geometricBounds;          // [top, left, bottom, right]
                    var fw  = b[3] - b[1];
                    var ins = fr.textFramePreferences.insetSpacing; // [top, left, bottom, right]
                    var iL  = (ins && ins[1] != null) ? ins[1] : 0;
                    var iR  = (ins && ins[3] != null) ? ins[3] : iL;
                    var cw  = fw - iL - iR;
                    if (cw > 0) { contentWidth = cw; break; }
                }
            } catch (e) {}

            for (var ti = 0; ti < tables.length; ti++) {
                try {
                    var tbl = tables[ti];
                    if (!tbl || !tbl.isValid) { skipCount++; continue; }

                    // ─ 너비 조정
                    if (contentWidth && contentWidth > 0) {
                        var curW = 0;
                        for (var c = 0; c < tbl.columns.length; c++) {
                            try { curW += tbl.columns[c].width; } catch (e) {}
                        }
                        if (curW > 0 && Math.abs(curW - contentWidth) > 0.5) {
                            var scale = contentWidth / curW;
                            for (var c = 0; c < tbl.columns.length; c++) {
                                try {
                                    tbl.columns[c].width = Math.round(tbl.columns[c].width * scale * 1000) / 1000;
                                } catch (e) {}
                            }
                        }
                    }

                    // ─ 셀 스타일 적용 (everyItem 우선, 실패 시 개별 루프)
                    var styled = false;
                    try {
                        tbl.cells.everyItem().appliedCellStyle = cs;
                        styled = true;
                    } catch (e) {}

                    if (!styled) {
                        for (var r = 0; r < tbl.rows.length; r++) {
                            try {
                                tbl.rows[r].cells.everyItem().appliedCellStyle = cs;
                            } catch (e) {
                                for (var c = 0; c < tbl.rows[r].cells.length; c++) {
                                    try { tbl.rows[r].cells[c].appliedCellStyle = cs; } catch (e2) {}
                                }
                            }
                        }
                    }

                    tblCount++;
                } catch (e) { skipCount++; }
            }
        } catch (e) {}
    }

    // ════════════════════════════════════════════
    // 완료 리포트
    // ════════════════════════════════════════════
    alert(
        "완료!\n\n" +
        "[N] 단락 삭제    : " + delCount  + "개\n" +
        "표 처리          : " + tblCount  + "개\n" +
        (skipCount > 0 ? "스킵(오류/빈 표): " + skipCount + "개\n" : "") +
        "\n셀 스타일 '" + STYLE_NAME + "' 생성/업데이트\n" +
        "\n※ 테두리 다시 변경하려면:\n" +
        "   셀 스타일 패널 → '" + STYLE_NAME + "' 더블클릭"
    );

})();
