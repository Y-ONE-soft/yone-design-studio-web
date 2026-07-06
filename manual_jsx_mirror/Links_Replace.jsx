#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("열린 문서가 없습니다.");
        return;
    }

    var totalChanged = 0;
    var totalErrors = 0;

    for (var d = 0; d < app.documents.length; d++) {

        var doc = app.documents[d];
        var links = doc.links;

        for (var i = 0; i < links.length; i++) {

            try {
                var link = links[i];
                var oldPath = link.filePath;

                if (oldPath.indexOf("/B버전/") !== -1) {

                    // 1️⃣ 폴더 변경
                    var newPath = oldPath.replace("/B버전/", "/C버전/");

                    // 2️⃣ 파일명에서 (B) 제거
                    newPath = newPath.replace("(B)", "");

                    var newFile = new File(newPath);

                    if (newFile.exists) {
                        link.relink(newFile);
                        link.update();
                        totalChanged++;
                    } else {
                        totalErrors++;
                    }
                }

            } catch (e) {
                totalErrors++;
            }
        }
    }

    alert(
        "전체 문서 링크 변경 완료\n\n" +
        "변경된 링크 수: " + totalChanged + "\n" +
        "오류 수: " + totalErrors
    );

})();