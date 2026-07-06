#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("문서 없음");
        return;
    }

    var doc = app.activeDocument;
    var tables = doc.stories.everyItem().tables.everyItem().getElements();

    var deleteCount = 0;

    for (var t = 0; t < tables.length; t++) {

        var table = tables[t];

        for (var r = table.rows.length - 1; r >= 0; r--) {

            var row = table.rows[r];

            if (row.cells.length < 2) continue;

            var leftText = row.cells[0].texts[0].contents;
            var rightText = row.cells[1].texts[0].contents;

            // 왼쪽이 "파생어"
            if (leftText.replace(/\s+/g, "") === "파생어") {

                // 오른쪽이 공백인지 체크
                if (rightText.replace(/\s+/g, "") === "") {

                    row.remove();
                    deleteCount++;
                }
            }
        }
    }

    alert("삭제된 파생어 행: " + deleteCount + "개");

})();