(function () {

    if (app.documents.length === 0) {
        alert("열려 있는 문서가 없습니다.");
        return;
    }

    var doc = app.activeDocument;

    //--------------------------------------------------
    // 1단계: 파생어 스타일 공백 → \r
    //--------------------------------------------------

    try {
        var style1 = doc.paragraphStyles.itemByName("파생어");
        style1.name;
    } catch (e) {
        alert("단락스타일 '파생어' 없음");
        return;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    app.findGrepPreferences.findWhat = "(?<=[가-힣\\)])\\x{0020}(?=[A-Za-z])";
    app.findGrepPreferences.appliedParagraphStyle = style1;
    app.changeGrepPreferences.changeTo = "\\r";

    doc.changeGrep();

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;


    //--------------------------------------------------
    // 2단계: 명./형./부./동. → 스크립트 레이블 삽입
    //--------------------------------------------------

    var replaceMap = {
        "명. ": "명사",
        "형. ": "형용사",
        "부. ": "부사",
        "동. ": "동사"
    };

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    app.findGrepPreferences.findWhat = "(명|형|부|동)\\.\\x{0020}";

    var found2 = doc.findGrep();

    for (var i = found2.length - 1; i >= 0; i--) {

        var matchText = found2[i].contents;
        var labelName = replaceMap[matchText];

        if (!labelName) continue;

        var insertionPoint = found2[i].insertionPoints[0];

        // 공백 유지
        found2[i].contents = " ";

        // 레이블 찾기
        var labelItem = null;
        var items = doc.allPageItems;

        for (var j = 0; j < items.length; j++) {
            if (items[j].label === labelName) {
                labelItem = items[j];
                break;
            }
        }

        if (!labelItem) continue;

        var newItem = labelItem.duplicate();

        newItem.anchoredObjectSettings.insertAnchoredObject(
            insertionPoint,
            AnchorPosition.INLINE_POSITION
        );
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;


    //--------------------------------------------------
    // 3단계-1: 표제어_뜻에서
    // 명./형./부./동. 앞 공백 → \r
    //--------------------------------------------------

    try {
        var style3 = doc.paragraphStyles.itemByName("표제어_뜻");
        style3.name;
    } catch (e) {
        alert("단락스타일 '표제어_뜻' 없음");
        return;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    app.findGrepPreferences.appliedParagraphStyle = style3;

    // 공백 + 명|형|부|동.
    app.findGrepPreferences.findWhat = "\\x{0020}(?=(명|형|부|동)\\.)";
    app.changeGrepPreferences.changeTo = "\\r";

    doc.changeGrep();

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;


    //--------------------------------------------------
    // 3단계-2: 번호_뜻 → 동그라미 숫자 (스타일 유지)
    //--------------------------------------------------

    try {
        var charStyle = doc.characterStyles.itemByName("번호_뜻");
        charStyle.name;
    } catch (e) {
        alert("문자스타일 '번호_뜻' 없음");
        return;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    app.findGrepPreferences.appliedCharacterStyle = charStyle;
    app.findGrepPreferences.findWhat = "(\\d+)\\.";

    var found3 = doc.findGrep();

    for (var k = found3.length - 1; k >= 0; k--) {

        var num = parseInt(found3[k].contents.replace(".", ""), 10);

        if (num >= 1 && num <= 20) {

            var circled = String.fromCharCode(9311 + num);
            found3[k].contents = circled;

            // 문자스타일 다시 적용
            found3[k].appliedCharacterStyle = charStyle;
        }
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    alert("1 → 2 → 3 단계 전체 완료");

})();