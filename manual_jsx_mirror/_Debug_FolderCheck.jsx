/**
 * _Debug_FolderCheck.jsx
 * 선택한 폴더의 .indd 파일 목록과 파일명 파싱 결과를 보여줍니다.
 * MergeMockExam.jsx 문제 진단용 — 확인 후 삭제해도 됩니다.
 */

#target indesign

(function () {
    var folder = Folder.selectDialog('진단할 폴더 선택 (세로버전 .indd 파일이 있는 폴더)');
    if (!folder) return;

    // 모든 항목 가져오기
    var allItems = folder.getFiles();
    var inddFiles = [];
    for (var i = 0; i < allItems.length; i++) {
        if (allItems[i] instanceof File && /\.indd$/i.test(allItems[i].name)) {
            inddFiles.push(allItems[i]);
        }
    }

    if (inddFiles.length === 0) {
        alert('이 폴더에서 .indd 파일을 찾지 못했습니다.\n\n폴더 경로:\n' + folder.fsName
              + '\n\n혹시 파일이 하위 폴더(예: A버전, B버전)에 있는 건 아닌가요?');
        return;
    }

    // 첫 10개 파일의 파싱 결과 출력
    var SERO_NFD = '\u1109\u1166\u1105\u1169'; // "세로" NFD
    var msg = '폴더: ' + folder.fsName + '\n';
    msg += '.indd 파일 수: ' + inddFiles.length + '\n';
    msg += '─────────────────────────────\n';

    var limit = Math.min(inddFiles.length, 10);
    for (var j = 0; j < limit; j++) {
        var name  = inddFiles[j].name;
        var parts = name.split('_');
        var isSero = (parts.length >= 4 && parts[3].indexOf(SERO_NFD) === 0);

        msg += '\n[' + (j + 1) + '] ' + name;
        msg += '\n    parts.length=' + parts.length;
        msg += '\n    parts[1]="' + parts[1] + '" / parts[2]="' + parts[2] + '"';
        msg += '\n    세로 감지: ' + (isSero ? 'YES' : 'NO');
    }

    if (inddFiles.length > 10) {
        msg += '\n\n... 외 ' + (inddFiles.length - 10) + '개';
    }

    alert(msg);
}());
