// PocketbookRemoveBox.jsx
// 포켓북 "삽화 추가" 되돌리기 (반대 동작)
//  - 왼쪽 빈 삽화(PICTURE) placeholder 박스 삭제
//  - 오른쪽 번역 프레임을 하단 전체폭으로 복원 (크기 확대 + 위치 이동)
//  - 좌/우 페이지 미러 좌표 자동 적용
// UI: 시작/끝 페이지, 왼쪽/오른쪽/둘 다 선택
// 좌표는 PocketbookAddBox.jsx 와 짝을 이룸

#target indesign

(function () {
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    var doc = app.activeDocument;

    // ----- 고정 좌표 (AddBox 와 동일 기준) -----
    // geometricBounds = [y1(top), x1(left), y2(bottom), x2(right)]
    // 복원 목표 = 하단 전체폭 번역 프레임
    var FULL = {
        L: [162.5, 15, 194.999999999936, 129.999999999958],
        R: [162.5, 18, 194.999999999936, 132.999999999958]
    };
    // 삭제 대상(왼쪽 삽화 박스) 식별 범위
    var PIC = {
        L: { top: [145, 155], left: [10, 25], right: [55, 85] },
        R: { top: [145, 155], left: [13, 28], right: [58, 88] }
    };
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

    function inRange(v, r) { return v >= r[0] && v <= r[1]; }

    // 왼쪽 빈 삽화 박스 찾기 (빈 Rectangle, 하단 좌측)
    function findPicBoxes(pg, spec) {
        var res = [];
        for (var i = 0; i < pg.pageItems.length; i++) {
            var it = pg.pageItems[i];
            if (realType(it) !== "Rectangle") continue;
            var ng = 0; try { ng = it.allGraphics.length; } catch (e) {}
            if (ng > 0) continue; // 내용(삽화) 있으면 보존
            var b = it.geometricBounds;
            if (inRange(b[0], spec.top) && inRange(b[1], spec.left) && inRange(b[3], spec.right)) res.push(it);
        }
        return res;
    }

    // ----- UI -----
    var dlg = app.dialogs.add({ name: "삽화 박스 되돌리기 (전체폭 복원)" });
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
    var summary = { done: 0, delBox: 0, skip: [] };

    app.doScript(function () {
        for (var p = 0; p < doc.pages.length; p++) {
            var pg = doc.pages[p];
            var n = parseInt(pg.name, 10);
            if (isNaN(n) || n < fromN || n > toN) continue;
            var isR = (pg.side === SIDE_R);
            if (sideSel === 0 && isR) continue;
            if (sideSel === 1 && !isR) continue;

            var key = isR ? "R" : "L";

            var tf = findTransFrame(pg);
            if (!tf) { summary.skip.push(pg.name + "(번역없음)"); continue; }
            if (tf.geometricBounds[0] >= 158) { summary.skip.push(pg.name + "(이미전체폭)"); continue; }

            // 1) 번역 프레임 전체폭 복원
            tf.geometricBounds = FULL[key];

            // 2) 왼쪽 빈 삽화 박스 삭제
            var boxes = findPicBoxes(pg, PIC[key]);
            for (var k = 0; k < boxes.length; k++) { try { boxes[k].remove(); summary.delBox++; } catch (e) {} }

            summary.done++;
        }
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "포켓북 삽화 박스 되돌리기");

    var msg = "완료: " + summary.done + "개 페이지 복원\n";
    msg += "삭제한 삽화 박스: " + summary.delBox + "개\n";
    msg += "건너뜀: [" + summary.skip.join(",") + "]";
    alert(msg);
})();
