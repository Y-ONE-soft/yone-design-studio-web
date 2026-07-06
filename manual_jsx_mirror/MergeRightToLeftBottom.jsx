// MergeRightToLeftBottom.jsx
//
// 오른쪽 페이지의 텍스트 프레임을 다음 왼쪽 페이지의 하단으로 이동(원하는 만큼)
// + 비어진 오른쪽 페이지 자동 삭제
//
// 동작:
//   1. 다이얼로그에서 [시작 페이지 ~ 끝 페이지] + [상/하 경계 Y] + [단락 스타일 필터] 입력
//   2. 짝수 페이지(왼쪽)의 첫 대상 프레임을 위쪽 절반(상단)으로 축소
//   3. 그 다음 페이지(오른쪽)의 대상 프레임을 같은 왼쪽 페이지로 이동 +
//      아래쪽 절반(하단)으로 배치
//   4. 비어진 오른쪽 페이지 삭제
//
// 단일 Undo로 묶임(ENTIRE_SCRIPT). 잘못되면 ⌘Z 한 번에 전체 복구.
//
// 작성: 블랙북 면 합치기 작업용. 다른 책에도 페이지 범위/스타일 변경하여 사용.

#target indesign
(function() {
    if (app.documents.length === 0) {
        alert('열린 문서가 없습니다.');
        return;
    }
    var doc = app.activeDocument;

    // ── 다이얼로그 ─────────────────────────────────────────
    var dlg = new Window('dialog', '오른쪽 프레임 → 왼쪽 하단 + 빈 페이지 삭제');
    dlg.alignChildren = 'left';

    var grp1 = dlg.add('group');
    grp1.add('statictext', undefined, '시작 페이지:');
    var startInput = grp1.add('edittext', undefined, '4');
    startInput.characters = 5;
    grp1.add('statictext', undefined, '끝 페이지:');
    var endInput = grp1.add('edittext', undefined, '58');
    endInput.characters = 5;

    var grp2 = dlg.add('group');
    grp2.add('statictext', undefined, '왼쪽 페이지 상/하 경계 Y (mm):');
    var splitYInput = grp2.add('edittext', undefined, '148.5');
    splitYInput.characters = 8;

    var grp3 = dlg.add('group');
    grp3.add('statictext', undefined, '대상 단락 스타일 (빈 입력 = 모든 프레임):');
    var styInput = grp3.add('edittext', undefined, '문제');
    styInput.characters = 16;

    dlg.add('statictext', undefined, '─ 동작 ─────────────────────────');
    dlg.add('statictext', undefined, '왼쪽 페이지(짝수): 첫 대상 프레임을 상단으로 축소');
    dlg.add('statictext', undefined, '오른쪽 페이지(다음 홀수): 대상 프레임을 왼쪽 하단으로 이동');
    dlg.add('statictext', undefined, '비어진 오른쪽 페이지 자동 삭제 (⌘Z 한 번으로 복구)');

    var btnGrp = dlg.add('group');
    btnGrp.alignment = 'right';
    var okBtn = btnGrp.add('button', undefined, '실행', {name: 'ok'});
    btnGrp.add('button', undefined, '취소', {name: 'cancel'});

    if (dlg.show() !== 1) return;

    var startPg = parseInt(startInput.text, 10);
    var endPg   = parseInt(endInput.text, 10);
    var splitY  = parseFloat(splitYInput.text);
    var styFilter = String(styInput.text).replace(/^\s+|\s+$/g, '');

    if (isNaN(startPg) || isNaN(endPg) || isNaN(splitY)) {
        alert('숫자 입력 오류 (시작/끝 페이지, 경계 Y는 모두 숫자)');
        return;
    }
    if (startPg > endPg) {
        alert('시작 페이지가 끝 페이지보다 큽니다.');
        return;
    }

    // ── 대상 쌍 수집 ──────────────────────────────────────
    function _firstStyle(tf) {
        try { return tf.parentStory.paragraphs[0].appliedParagraphStyle.name; }
        catch(e) { return ''; }
    }

    var pairs = [];
    for (var i = 0; i < doc.pages.length; i++) {
        var pg = doc.pages[i];
        var pageNum = parseInt(pg.name, 10);
        if (isNaN(pageNum) || pageNum < startPg || pageNum > endPg) continue;
        if (pageNum % 2 !== 0) continue;                 // 왼쪽(짝수)만
        if (pg.textFrames.length === 0) continue;
        if (styFilter !== '' && _firstStyle(pg.textFrames[0]) !== styFilter) continue;
        if (i + 1 >= doc.pages.length) continue;

        pairs.push({
            left: pg, right: doc.pages[i + 1],
            leftName: pg.name, rightName: doc.pages[i + 1].name
        });
    }

    if (pairs.length === 0) {
        alert('처리 대상 쌍이 없습니다. 페이지 범위/스타일 필터를 확인하세요.');
        return;
    }

    // ── 처리 (단일 Undo 묶음) ─────────────────────────────
    var log = [];
    log.push('처리 대상: ' + pairs.length + '개 쌍');

    app.doScript(function() {
        // 1) 각 쌍: 왼쪽 상단 축소 + 오른쪽 프레임을 왼쪽 하단으로 이동
        for (var k = 0; k < pairs.length; k++) {
            var pair = pairs[k];
            var leftPg  = pair.left;
            var rightPg = pair.right;

            // 왼쪽 페이지의 대상 프레임
            var leftTF = null;
            for (var lt = 0; lt < leftPg.textFrames.length; lt++) {
                var lTF = leftPg.textFrames[lt];
                if (styFilter !== '' && _firstStyle(lTF) !== styFilter) continue;
                leftTF = lTF; break;
            }
            if (!leftTF) {
                log.push('p' + pair.leftName + ': 대상 프레임 없음 — 스킵');
                continue;
            }

            // 상단 영역으로 축소: y2만 splitY로
            var lb = leftTF.geometricBounds;  // [y1, x1, y2, x2]
            try {
                leftTF.geometricBounds = [lb[0], lb[1], splitY, lb[3]];
                log.push('p' + pair.leftName + ' 상단 리사이즈 OK');
            } catch(e) {
                log.push('[ERR] p' + pair.leftName + ' 리사이즈 실패: ' + e.message);
                continue;
            }

            // 오른쪽 페이지 대상 프레임 모두 이동
            var rtfs = rightPg.textFrames;
            var moved = 0;
            for (var rt = rtfs.length - 1; rt >= 0; rt--) {
                var rTF = rtfs[rt];
                if (styFilter !== '' && _firstStyle(rTF) !== styFilter) continue;
                try {
                    rTF.move(leftPg);
                    // 하단 영역으로 배치: y1=splitY, 나머지는 왼쪽 프레임의 폭 그대로
                    rTF.geometricBounds = [splitY, lb[1], lb[2], lb[3]];
                    moved++;
                    log.push('p' + pair.rightName + ' → p' + pair.leftName + ' 하단 이동 OK');
                } catch(e) {
                    log.push('[ERR] p' + pair.rightName + ' 이동 실패: ' + e.message);
                }
            }
            if (moved === 0) {
                log.push('[WARN] p' + pair.rightName + ': 이동할 대상 프레임 없음');
            }
        }

        // 2) 비어진 오른쪽 페이지 삭제
        var toDelete = [];
        for (var k2 = 0; k2 < pairs.length; k2++) toDelete.push(pairs[k2].right);
        toDelete.sort(function(a, b) {
            return parseInt(b.name, 10) - parseInt(a.name, 10);  // 큰 번호부터
        });

        var deleted = 0;
        for (var d = 0; d < toDelete.length; d++) {
            var pg2 = toDelete[d];
            if (!pg2.isValid) continue;

            // 사용자 콘텐츠 있는지
            var hasContent = false;
            var tfs = pg2.textFrames;
            for (var tt = 0; tt < tfs.length; tt++) {
                try {
                    var c = tfs[tt].contents;
                    if (typeof c === 'string' && c.replace(/[\r\n\s]/g, '').length > 0) {
                        hasContent = true; break;
                    }
                } catch(e) {}
            }
            if (!hasContent) {
                try {
                    if (pg2.allPageItems.length > pg2.textFrames.length) hasContent = true;
                } catch(e) {}
            }
            if (hasContent) {
                log.push('p' + pg2.name + ' 콘텐츠 있음 — 삭제 스킵');
                continue;
            }
            try {
                pg2.remove();
                deleted++;
            } catch(e) {
                log.push('[ERR] p' + pg2.name + ' 삭제 실패: ' + e.message);
            }
        }
        log.push('');
        log.push('총 삭제 페이지: ' + deleted + '개');
        log.push('남은 페이지 수: ' + doc.pages.length);

    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT,
       '오른쪽 프레임 → 왼쪽 하단 + 빈 페이지 삭제');

    alert(log.join('\n'));
})();
