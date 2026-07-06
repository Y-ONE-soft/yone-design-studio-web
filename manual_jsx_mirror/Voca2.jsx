#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("열려 있는 문서가 없습니다.");
        return;
    }

    var doc = app.activeDocument;

    var replaceMap = {
        "명. ": "명사",
        "형. ": "형용사",
        "부. ": "부사",
        "동. ": "동사"
    };

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    // 마침표 뒤 반드시 공백 1칸 포함
    app.findGrepPreferences.findWhat = "(명|형|부|동)\\.\\x{0020}";

    var found = doc.findGrep();

    if (found.length === 0) {
        alert("대상 없음");
        return;
    }

    var changeCount = 0;

    for (var i = found.length - 1; i >= 0; i--) {

        var matchText = found[i].contents; // 예: "명. "
        var labelName = replaceMap[matchText];

        if (!labelName) continue;

        var insertionPoint = found[i].insertionPoints[0];

        // 공백은 남겨야 하므로 마지막 한 칸 유지
        var spaceChar = " ";
        found[i].contents = spaceChar;

        // 스크립트 레이블 객체 찾기
        var labelItem = null;
        var allItems = doc.allPageItems;

        for (var j = 0; j < allItems.length; j++) {
            if (allItems[j].label === labelName) {
                labelItem = allItems[j];
                break;
            }
        }

        if (!labelItem) continue;

        // 복제해서 삽입
        var newItem = labelItem.duplicate();

        newItem.anchoredObjectSettings.insertAnchoredObject(
            insertionPoint,
            AnchorPosition.INLINE_POSITION
        );

        changeCount++;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    alert("완료: " + changeCount + "개 삽입됨.");

})();