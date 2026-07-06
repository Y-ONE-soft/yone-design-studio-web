// PocketbookAddIllustrationBox.jsx
// 포켓북 하단 "삽화 추가" 버전 일괄 적용
//  - 하단 전체폭 번역 프레임 -> 오른쪽 좁은 박스로 축소/이동
//  - 왼쪽에 빈 삽화(PICTURE) placeholder 박스 삽입
//  - 좌/우 페이지 미러 좌표 자동 적용
//  - 오버플로우 시: 행간 -8pt 후 프레임 하단을 아래로 확장
// UI: 시작/끝 페이지, 왼쪽/오른쪽/둘 다 선택
// 좌표는 올림포스/광문 포켓북 작업과 동일 (2페이지/12페이지 기준)

#target indesign

(function () {
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    var doc = app.activeDocument;

    // ----- 고정 좌표 (이 작업과 동일) -----
    // geometricBounds = [y1(top), x1(left), y2(bottom), x2(right)]
    var COORD = {
        L: {
            PIC:   [149.999999999936, 15,                194.999999999936, 70.9999999999792],
            TRANS: [150,               73.9999999999792, 194.999999999936, 129.999999999958]
        },
        R: {
            PIC:   [149.999999999936, 18,                194.999999999936, 73.9999999999792],
            TRANS: [150,               76.9999999999792, 194.999999999936, 132.999999999958]
        }
    };
    var LEADING_REDUCE = 8;   // 오버플로우 시 행간 감소량(pt)
    var MIN_LEADING    = 5;   // 행간 하한
    var EXTEND_STEP    = 2;   // 하단 확장 단위(pt)
    var MAX_BOTTOM     = 204; // 하단 확장 한계(페이지 footer 바로 위)
    var SIDE_L = 1818653800, SIDE_R = 1919382632;

    // ----- 헬퍼 -----
    function hasKorean(s) {
        if (!s) return false;
        for (var i = 0; i < s.length; i++) {
            var c = s.charCodeAt(i);
            if ((c >= 0xAC00 && c <= 0xD7A3) || (c >= 0x1100 && c <= 0x11FF) || (c >= 0x3130 && c <= 0x318F)) return true;
        }
        return false;
    }
    function realType(it) { try { return it.getElements()[0].constructor.name; } catch (e) { return it.constructor.name; } }

    // 하단(번역) 프레임 = y1>140 영역에서 한글 포함 최하단 TextFrame
    function findTransFrame(pg) {
        var best = null, bestTop = -1;
        for (var i = 0; i < pg.pageItems.length; i++) {
            var it = pg.pageItems[i];
            if (realType(it) !== "TextFrame") continue;
            var c; try { c = String(it.contents); } catch (e) { continue; }
            if (!hasKorean(c)) continue;
            var top = it.geometricBounds[0];
            if (top > 140 && top > bestTop) { bestTop = top; best = it; }
        }
        return best;
    }

    function curLeading(t) {
        var ld = t.leading;
        if (typeof ld === "number") return ld;
        // auto leading -> 해석
        var ps = t.pointSize;
        if (typeof ps !== "number") { try { ps = t.characters[0].pointSize; } catch (e) { ps = 9; } }
        var pct = 120; try { pct = t.parentStory.paragraphs[0].autoLeading; } catch (e) {}
        if (typeof pct !== "number") pct = 120;
        return ps * pct / 100;
    }

    // 오버플로우 처리: 행간 -8 -> 하단 확장
    function fixOverflow(tf) {
        if (!tf.overflows) return "fit";
        // 1) 행간 8pt 감소
        try {
            var t = tf.texts[0];
            var nl = curLeading(t) - LEADING_REDUCE;
            if (nl < MIN_LEADING) nl = MIN_LEADING;
            t.leading = nl;
        } catch (e) {}
        if (!tf.overflows) return "leading";
        // 2) 프레임 하단을 아래로 확장
        var guard = 0;
        while (tf.overflows && tf.geometricBounds[2] < MAX_BOTTOM && guard < 200) {
            var gb = tf.geometricBounds;
            gb[2] = Math.min(gb[2] + EXTEND_STEP, MAX_BOTTOM);
            tf.geometricBounds = gb;
            guard++;
        }
        return tf.overflows ? "overflow" : "extend";
    }

    function noneSwatch() {
        var d = app.activeDocument;
        var sw = d.swatches.itemByName("None");
        if (sw && sw.isValid) return sw;
        // 폴백: 이름이 None 인 스와치 탐색
        for (var i = 0; i < d.swatches.length; i++) {
            try { if (String(d.swatches[i].name) === "None") return d.swatches[i]; } catch (e) {}
        }
        return d.swatches[0];
    }

    function addPicBox(pg, bounds, layer) {
        var none = noneSwatch();
        var rect = pg.rectangles.add(layer);
        rect.geometricBounds = bounds;
        // 획 없음 강제 (오브젝트 스타일은 건드리지 않음 - 건드리면 검정 획이 생김)
        try { rect.fillColor = none; } catch (e) {}
        try { rect.strokeColor = none; } catch (e) {}   // 획 없음 (핵심)
        try { rect.contentType = ContentType.GRAPHIC_TYPE; } catch (e) {}
        // 빈 프레임 기본 내용 맞추기 = 비율에 맞게 내용 맞추기
        try { rect.frameFittingOptions.fittingOnEmptyFrame = EmptyFrameFittingOptions.PROPORTIONALLY; } catch (e) {}
        return rect;
    }

    // ----- UI -----
    var dlg = app.dialogs.add({ name: "삽화 추가 - 하단 번역 박스" });
    var col = dlg.dialogColumns.add();
    var r1 = col.dialogRows.add();
    r1.staticTexts.add({ staticLabel: "시작 페이지:" });
    var fromBox = r1.integerEditboxes.add({ editValue: 1, minimumValue: 1, maximumValue: 99999 });
    var r2 = col.dialogRows.add();
    r2.staticTexts.add({ staticLabel: "끝 페이지:" });
    var toBox = r2.integerEditboxes.add({ editValue: doc.pages.length, minimumValue: 1, maximumValue: 99999 });
    var r3 = col.dialogRows.add();
    r3.staticTexts.add({ staticLabel: "대상:" });
    var sideDrop = r3.dropdowns.add({ stringList: ["왼쪽 페이지", "오른쪽 페이지", "둘 다"], selectedIndex: 2 });

    if (!dlg.show()) { dlg.destroy(); return; }
    var fromN = fromBox.editValue, toN = toBox.editValue, sideSel = sideDrop.selectedIndex;
    dlg.destroy();
    if (fromN > toN) { var tmp = fromN; fromN = toN; toN = tmp; }

    // ----- 실행 -----
    var summary = { done: 0, leading: [], extend: [], overflow: [], skip: [] };

    app.doScript(function () {
        for (var p = 0; p < doc.pages.length; p++) {
            var pg = doc.pages[p];
            var n = parseInt(pg.name, 10);
            if (isNaN(n) || n < fromN || n > toN) continue;
            var isR = (pg.side === SIDE_R);
            // 대상 필터: 0=왼쪽만, 1=오른쪽만, 2=둘다
            if (sideSel === 0 && isR) continue;
            if (sideSel === 1 && !isR) continue;

            var tf = findTransFrame(pg);
            if (!tf) { summary.skip.push(pg.name + "(번역없음)"); continue; }
            if (tf.geometricBounds[0] < 155) { summary.skip.push(pg.name + "(이미적용)"); continue; }

            var key = isR ? "R" : "L";
            tf.geometricBounds = COORD[key].TRANS;
            addPicBox(pg, COORD[key].PIC, tf.itemLayer);

            var res = fixOverflow(tf);
            if (res === "leading") summary.leading.push(pg.name);
            else if (res === "extend") summary.extend.push(pg.name);
            else if (res === "overflow") summary.overflow.push(pg.name);
            summary.done++;
        }
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "포켓북 삽화 추가");

    var msg = "완료: " + summary.done + "개 페이지\n";
    msg += "행간 -8pt 로 해결: [" + summary.leading.join(",") + "]\n";
    msg += "하단 확장으로 해결: [" + summary.extend.join(",") + "]\n";
    msg += "여전히 오버플로우(수동 확인): [" + summary.overflow.join(",") + "]\n";
    msg += "건너뜀: [" + summary.skip.join(",") + "]";
    alert(msg);
})();
