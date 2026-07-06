// TableWidthFix.jsx — 모든 표를 텍스트 프레임 내폭에 맞춤 조정
#target "InDesign"

(function () {
    var doc = app.activeDocument;

    // 단위를 포인트로 강제 고정 (geometricBounds ↔ column.width 단위 통일)
    var origUnit;
    try {
        origUnit = app.scriptPreferences.measurementUnit;
        app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS;
    } catch (e) {}

    var resized = 0;
    var skipped = 0;
    var stories = doc.stories;

    for (var si = 0; si < stories.length; si++) {
        try {
            var story = stories[si];
            if (!story || !story.isValid) continue;

            // 텍스트 컨테이너 없는 스토리 건너뜀
            var containers;
            try { containers = story.textContainers; } catch (e) { continue; }
            if (!containers || containers.length === 0) continue;

            var tables = story.tables;
            if (!tables || tables.length === 0) continue;

            // ── 이 스토리의 프레임 내폭 계산 (포인트 단위) ──
            var contentWidth = 0;
            for (var ci = 0; ci < containers.length; ci++) {
                try {
                    var fr = containers[ci];
                    if (!fr || !fr.isValid) continue;
                    var b  = fr.geometricBounds;         // [top, left, bottom, right] in pt
                    var fw = b[3] - b[1];                // 프레임 너비
                    if (fw <= 0) continue;

                    // 텍스트 인셋 빼기
                    var ins = fr.textFramePreferences.insetSpacing; // [top, left, bottom, right]
                    var iL  = (ins && ins[1] != null) ? Number(ins[1]) : 0;
                    var iR  = (ins && ins[3] != null) ? Number(ins[3]) : 0;
                    var cw  = fw - iL - iR;
                    if (cw > 0) { contentWidth = cw; break; }
                } catch (e) {}
            }

            if (contentWidth <= 0) { skipped++; continue; }

            // ── 각 표 너비 조정 ──
            for (var ti = 0; ti < tables.length; ti++) {
                try {
                    var tbl = tables[ti];
                    if (!tbl || !tbl.isValid) { skipped++; continue; }

                    // 현재 표 너비
                    var curW = 0;
                    for (var c = 0; c < tbl.columns.length; c++) {
                        try { curW += tbl.columns[c].width; } catch (e) {}
                    }
                    if (curW <= 0) { skipped++; continue; }

                    // 이미 맞으면 건너뜀 (오차 0.5pt 이하)
                    if (Math.abs(curW - contentWidth) <= 0.5) continue;

                    // 비례 스케일
                    var scale = contentWidth / curW;
                    for (var c = 0; c < tbl.columns.length; c++) {
                        try {
                            tbl.columns[c].width = tbl.columns[c].width * scale;
                        } catch (e) {}
                    }
                    resized++;
                } catch (e) { skipped++; }
            }
        } catch (e) {}
    }

    // 단위 복원
    try { app.scriptPreferences.measurementUnit = origUnit; } catch (e) {}

    alert("표 너비 조정 완료\n조정: " + resized + "개\n스킵: " + skipped + "개");
})();
