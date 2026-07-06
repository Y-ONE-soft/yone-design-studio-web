/**
 * MergeTextbook.jsx
 * 교과서 단원 파일들을 순서대로 합쳐 PDF로 내보냅니다.
 *
 * 병합 규칙:
 *   첫 번째 파일 : 첫 페이지 ~ 끝에서 두 번째 페이지 (마지막 페이지 제외)
 *   중간 파일   : 두 번째 페이지 ~ 끝에서 두 번째 페이지 (앞·뒤 각 1페이지 제외)
 *   마지막 파일 : 두 번째 페이지 ~ 마지막 페이지 (첫 페이지 제외)
 *   파일 1개    : 전체 페이지
 */

#target indesign

(function () {

    // ═══════════════════════════════════════════════════════════
    // 유틸
    // ═══════════════════════════════════════════════════════════

    function getPageRange(fileIndex, totalFiles, pageCount) {
        if (totalFiles === 1) return { start: 0, count: pageCount };
        if (fileIndex === 0)  return { start: 0, count: pageCount - 1 };
        if (fileIndex === totalFiles - 1) return { start: 1, count: pageCount - 1 };
        return { start: 1, count: pageCount - 2 };
    }

    function openOrGet(file) {
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (app.documents[d].fullName.toString() === file.toString()) {
                    return { doc: app.documents[d], wasOpen: true };
                }
            } catch (e) {}
        }
        return { doc: app.open(file, false), wasOpen: false };
    }

    // ═══════════════════════════════════════════════════════════
    // 다이얼로그
    // ═══════════════════════════════════════════════════════════

    var dlg = new Window('dialog', '교과서 단원 합치기  ›  PDF 내보내기');
    dlg.orientation = 'column';
    dlg.alignChildren = 'fill';
    dlg.margins = [16, 16, 16, 16];
    dlg.spacing = 10;

    dlg.add('statictext', undefined, '합칠 순서대로 파일을 추가하세요.');

    // 파일 목록 + 버튼
    var grpFiles = dlg.add('group');
    grpFiles.orientation = 'row';
    grpFiles.alignChildren = ['left', 'top'];
    grpFiles.spacing = 8;

    var fileList = grpFiles.add('listbox', [0, 0, 320, 180]);
    var files = [];

    var grpCtrl = grpFiles.add('group');
    grpCtrl.orientation = 'column';
    grpCtrl.alignChildren = 'fill';
    grpCtrl.spacing = 5;

    var btnAdd    = grpCtrl.add('button', undefined, '추가');
    var btnRemove = grpCtrl.add('button', undefined, '제거');
    var btnUp     = grpCtrl.add('button', undefined, '▲ 위로');
    var btnDown   = grpCtrl.add('button', undefined, '▼ 아래로');

    function rebuildFileList() {
        fileList.removeAll();
        for (var i = 0; i < files.length; i++) {
            fileList.add('item', (i + 1) + '.  ' + files[i].displayName);
        }
    }

    btnAdd.onClick = function () {
        var f = File.openDialog('InDesign 파일 선택', '*.indd;*.INDD');
        if (!f) return;
        files.push(f);
        rebuildFileList();
    };

    btnRemove.onClick = function () {
        var sel = fileList.selection;
        if (!sel) return;
        files.splice(sel.index, 1);
        rebuildFileList();
    };

    btnUp.onClick = function () {
        var sel = fileList.selection;
        if (!sel || sel.index === 0) return;
        var i = sel.index;
        var tmp = files[i]; files[i] = files[i - 1]; files[i - 1] = tmp;
        rebuildFileList();
        fileList.selection = i - 1;
    };

    btnDown.onClick = function () {
        var sel = fileList.selection;
        if (!sel || sel.index === files.length - 1) return;
        var i = sel.index;
        var tmp = files[i]; files[i] = files[i + 1]; files[i + 1] = tmp;
        rebuildFileList();
        fileList.selection = i + 1;
    };

    // PDF 파일명
    var grpName = dlg.add('group');
    grpName.orientation = 'row';
    grpName.spacing = 6;
    grpName.add('statictext', [0, 0, 72, 18], 'PDF 파일명:');
    var txtName = grpName.add('edittext', [0, 0, 274, 22], '');
    txtName.helpTip = '예: 명일1_워크북01(교과1과)_내지';

    // 출력 폴더
    var grpOut = dlg.add('group');
    grpOut.orientation = 'row';
    grpOut.spacing = 6;
    grpOut.add('statictext', [0, 0, 72, 18], '출력 폴더:');
    var txtOut = grpOut.add('edittext', [0, 0, 230, 22], '');
    txtOut.enabled = false;
    var btnBrowseOut = grpOut.add('button', undefined, '선택...');
    var outFolder = null;

    btnBrowseOut.onClick = function () {
        var f = Folder.selectDialog('PDF 저장 폴더 선택');
        if (f) { outFolder = f; txtOut.text = f.fsName; }
    };

    // PDF 프리셋
    var grpPreset = dlg.add('group');
    grpPreset.orientation = 'row';
    grpPreset.spacing = 6;
    grpPreset.add('statictext', [0, 0, 72, 18], 'PDF 프리셋:');
    var presetItems = [];
    var presets = app.pdfExportPresets.everyItem().getElements();
    for (var pi = 0; pi < presets.length; pi++) presetItems.push(presets[pi].name);
    var ddPreset = grpPreset.add('dropdownlist', [0, 0, 274, 22], presetItems);
    if (presetItems.length > 0) ddPreset.selection = 0;

    // 실행 / 취소
    var grpBtns = dlg.add('group');
    grpBtns.alignment = 'right';
    grpBtns.add('button', undefined, '취소', { name: 'cancel' });
    grpBtns.add('button', undefined, '실행', { name: 'ok' });

    if (dlg.show() !== 1) return;

    // 유효성 검사
    if (files.length === 0) { alert('파일을 하나 이상 추가해 주세요.'); return; }
    if (!txtName.text.replace(/\s/g, '')) { alert('PDF 파일명을 입력해 주세요.'); return; }
    if (!outFolder) { alert('출력 폴더를 선택해 주세요.'); return; }

    var pdfName    = txtName.text;
    var presetName = (ddPreset.selection) ? ddPreset.selection.text : '';

    // ═══════════════════════════════════════════════════════════
    // 병합
    // ═══════════════════════════════════════════════════════════

    var targetDoc = app.documents.add(false);
    var blankPage = targetDoc.pages[0];

    for (var fi = 0; fi < files.length; fi++) {
        var opened = openOrGet(files[fi]);
        var srcDoc = opened.doc;

        // 이미 열려있던 파일은 복사본으로 작업해 원본 보호
        var workDoc = opened.wasOpen ? srcDoc.duplicate() : srcDoc;

        var pageCount = workDoc.pages.length;
        var range = getPageRange(fi, files.length, pageCount);

        for (var p = 0; p < range.count; p++) {
            workDoc.pages[range.start].move(LocationOptions.AFTER, targetDoc.pages[-1]);
        }

        workDoc.close(SaveOptions.NO);
    }

    // 초기 빈 페이지 제거
    if (targetDoc.pages.length > 1) {
        try { blankPage.remove(); } catch (e) {}
    }

    if (targetDoc.pages.length === 0) {
        targetDoc.close(SaveOptions.NO);
        alert('처리된 페이지가 없습니다.');
        return;
    }

    // ═══════════════════════════════════════════════════════════
    // PDF 내보내기
    // ═══════════════════════════════════════════════════════════

    var pdfFile = new File(outFolder.absoluteURI + '/' + pdfName + '.pdf');

    try {
        var preset = null;
        if (presetName) {
            try { preset = app.pdfExportPresets.itemByName(presetName); } catch (e) {}
        }
        if (preset && preset.isValid) {
            targetDoc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false, preset);
        } else {
            targetDoc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false);
        }
        targetDoc.close(SaveOptions.NO);
        alert('완료!\n\n저장 위치:\n' + pdfFile.fsName);
    } catch (e) {
        targetDoc.close(SaveOptions.NO);
        alert('PDF 내보내기 실패:\n' + e.message);
    }

}());
