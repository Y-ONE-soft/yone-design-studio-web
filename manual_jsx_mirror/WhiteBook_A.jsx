// Whitebook_A.jsx
(function () {
    var doc = app.activeDocument;

    // 기준 표 (36페이지, index 35)
    var refTbl  = doc.pages[35].textFrames[0].tables[0];
    var refRow  = refTbl.rows[0];

    var paraStyle0  = refRow.cells[0].texts[0].paragraphs[0].appliedParagraphStyle;
    var paraStyle1  = refRow.cells[1].texts[0].paragraphs[0].appliedParagraphStyle;
    var paraStyle2  = refRow.cells[2].texts[0].paragraphs[0].appliedParagraphStyle;
    var charStyle0  = refRow.cells[0].texts[0].characters[0].appliedCharacterStyle;
    var noneCS      = doc.characterStyles[0]; // [없음] - 항상 인덱스 0
    var cellStyle   = refRow.cells[0].appliedCellStyle;
    var strokeColor = refRow.cells[0].topEdgeStrokeColor;
    var font1       = refRow.cells[1].texts[0].characters[0].appliedFont;
    var font2       = refRow.cells[2].texts[0].characters[0].appliedFont;
    var fillColor0  = refRow.cells[0].texts[0].characters[0].fillColor;
    var fillColor1  = refRow.cells[1].texts[0].characters[0].fillColor;
    var fillColor2  = refRow.cells[2].texts[0].paragraphs[0].appliedParagraphStyle.fillColor;
    var colW        = [refRow.cells[0].width, refRow.cells[1].width, refRow.cells[2].width];

    // 처리 대상 표 찾기 (36페이지 제외, 30행 이상, 뒤 페이지부터)
    var targetFrame = null;
    for (var p = doc.pages.length - 1; p >= 0; p--) {
        if (p === 35) continue;
        var pg = doc.pages[p];
        for (var f = 0; f < pg.textFrames.length; f++) {
            var fr = pg.textFrames[f];
            if (fr.tables.length > 0 && fr.tables[0].rows.length >= 30) {
                targetFrame = fr;
                break;
            }
        }
        if (targetFrame) break;
    }
    if (!targetFrame) {
        alert("RTF \uD45C\uB97C \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.");
        return;
    }

    var tbl = targetFrame.tables[0];

    // 표 위 헤더 단락 삭제
    var txt = targetFrame.texts[0];
    for (var p2 = 0; p2 < txt.paragraphs.length; p2++) {
        if (txt.paragraphs[p2].tables.length > 0) {
            for (var d = p2 - 1; d >= 0; d--) {
                txt.paragraphs[d].remove();
            }
            break;
        }
    }

    // 표 헤더행 삭제
    var fc = tbl.rows[0].cells[0].contents;
    if (typeof fc === "string" && fc.replace(/\s/g, "") === "\uBC88\uD638") {
        tbl.rows[0].remove();
    }

    // 열 너비
    tbl.columns[0].width = colW[0];
    tbl.columns[1].width = colW[1];
    tbl.columns[2].width = colW[2];

    // 서식 적용
    for (var r = 0; r < tbl.rows.length; r++) {
        var row = tbl.rows[r];
        row.autoGrow = true;

        for (var c = 0; c < 3; c++) {
            var cell = row.cells[c];

            // 셀 서식
            cell.appliedCellStyle      = cellStyle;
            cell.topInset              = 2;
            cell.bottomInset           = 2.5;
            cell.leftInset             = 2;
            cell.rightInset            = 2;
            cell.topEdgeStrokeColor    = strokeColor;
            cell.bottomEdgeStrokeColor = strokeColor;
            cell.leftEdgeStrokeColor   = strokeColor;
            cell.rightEdgeStrokeColor  = strokeColor;
            cell.fillColor             = doc.swatches.itemByName("Paper");
            cell.verticalJustification = VerticalJustification.CENTER_ALIGN;

            // 직접 오버라이드 제거 (RTF 임포트 색상/폰트 오버라이드 초기화)
            cell.texts[0].clearOverrides();

            // 단락 스타일
            var cp = cell.texts[0].paragraphs;
            for (var pp = 0; pp < cp.length; pp++) {
                if (c === 0) {
                    cp[pp].appliedParagraphStyle = paraStyle0;
                    cp[pp].justification = Justification.CENTER_ALIGN;
                } else if (c === 1) {
                    cp[pp].appliedParagraphStyle = paraStyle1;
                } else {
                    cp[pp].appliedParagraphStyle = paraStyle2;
                }
            }

            // 문자 스타일 + 폰트 + 색상 (문자별 루프)
            var ac = cell.texts[0].characters;
            var acLen = ac.length;
            for (var i = 0; i < acLen; i++) {
                var ch = ac[i];
                if (c === 0) {
                    ch.appliedCharacterStyle = charStyle0;
                    ch.fillColor = fillColor0;
                } else if (c === 1) {
                    ch.appliedCharacterStyle = noneCS;
                    ch.appliedFont = font1;
                    ch.fillColor = fillColor1;
                } else {
                    ch.appliedCharacterStyle = noneCS;
                    ch.appliedFont = font2;
                    ch.fillColor = fillColor2;
                }
            }
        }
    }

    // 결과 확인
    var r0c0cs = tbl.rows[0].cells[0].texts[0].characters[0].appliedCharacterStyle.name;
    var r0c1cs = tbl.rows[0].cells[1].texts[0].characters[0].appliedCharacterStyle.name;
    var r0c1ft = tbl.rows[0].cells[1].texts[0].characters[0].appliedFont.name;
    var r0c2cs = tbl.rows[0].cells[2].texts[0].characters[0].appliedCharacterStyle.name;
    var r0c2ft = tbl.rows[0].cells[2].texts[0].characters[0].appliedFont.name;

    return "\uC644\uB8CC: " + tbl.rows.length + "\uD589\n" +
           "\uC5F40: " + r0c0cs + "\n" +
           "\uC5F41: cs=" + r0c1cs + " / font=" + r0c1ft + "\n" +
           "\uC5F42: cs=" + r0c2cs + " / font=" + r0c2ft;
})();
