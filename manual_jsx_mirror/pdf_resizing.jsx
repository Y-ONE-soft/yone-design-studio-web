#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("열려 있는 문서가 없습니다.");
        return;
    }

    var doc = app.activeDocument;

    function mmToPt(mm) {
        return mm * 2.834645669;
    }

    var A4_W = mmToPt(210);
    var A4_H = mmToPt(297);

    var count = 0;

    for (var p = 0; p < doc.pages.length; p++) {
        var page = doc.pages[p];
        var items = page.allPageItems;

        // 페이지 중심 좌표
        var pb = page.bounds; // [y1, x1, y2, x2]
        var pageCenterX = (pb[1] + pb[3]) / 2;
        var pageCenterY = (pb[0] + pb[2]) / 2;

        for (var i = 0; i < items.length; i++) {
            var item = items[i];

            if (!item.graphics || item.graphics.length === 0) continue;

            try {
                var g = item.graphics[0];

                // PDF 판별
                if (g.itemLink && /\.pdf$/i.test(g.itemLink.filePath)) {

                    /* 1️⃣ 프레임을 A4로 */
                    item.resize(
                        CoordinateSpaces.INNER_COORDINATES,
                        AnchorPoint.CENTER_ANCHOR,
                        ResizeMethods.REPLACING_CURRENT_DIMENSIONS_WITH,
                        [A4_W, A4_H]
                    );

                    /* 2️⃣ PDF 내용을 프레임에 비율 유지로 맞춤 */
                    item.fit(FitOptions.PROPORTIONALLY);
                    item.fit(FitOptions.CENTER_CONTENT);

                    /* 3️⃣ 페이지 중앙으로 이동 */
                    var gb = item.geometricBounds;
                    var itemW = gb[3] - gb[1];
                    var itemH = gb[2] - gb[0];

                    item.move([
                        pageCenterX - itemW / 2,
                        pageCenterY - itemH / 2
                    ]);

                    count++;
                }

            } catch (e) {}
        }
    }

    alert("완료!\nPDF A4 리사이징 + 중앙정렬 개체 수: " + count);

})();