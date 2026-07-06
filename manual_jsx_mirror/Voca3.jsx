#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("문서 없음");
        return;
    }

    var doc = app.activeDocument;

    //------------------------------------------
    // 1단계
    // 표제어_뜻 단락에서
    // 공백 + 2이상 숫자 + 마침표
    // 공백만 \r\t 로 변경
    //------------------------------------------

    var paraStyleName = "표제어_뜻";
    var paraStyle;

    try {
        paraStyle = doc.paragraphStyles.itemByName(paraStyleName);
        paraStyle.name;
    } catch (e) {
        alert("단락스타일 '표제어_뜻' 없음");
        return;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    app.findGrepPreferences.appliedParagraphStyle = paraStyle;

    // 공백 + 2이상 숫자 + .
    app.findGrepPreferences.findWhat = "\\x{0020}(?=[2-9]\\.|[1-9][0-9]+\\.)";

    app.changeGrepPreferences.changeTo = "\\r\\t";

    doc.changeGrep();

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    //------------------------------------------
    // 2단계
    // 문자스타일 번호_뜻 → 동그라미 숫자
    //------------------------------------------

    var charStyleName = "번호_뜻";
    var charStyle;

    try {
        charStyle = doc.characterStyles.itemByName(charStyleName);
        charStyle.name;
    } catch (e) {
        alert("문자스타일 '번호_뜻' 없음");
        return;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    app.findGrepPreferences.appliedCharacterStyle = charStyle;
    app.findGrepPreferences.findWhat = "(\\d+)\\.";

    var found = doc.findGrep();

    for (var i = found.length - 1; i >= 0; i--) {

        var num = parseInt(found[i].contents.replace(".", ""), 10);

        if (num >= 1 && num <= 20) {
            var circled = String.fromCharCode(9311 + num);
            found[i].contents = circled;

            // 문자스타일 다시 적용
            found[i].appliedCharacterStyle = charStyle;
        }
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    alert("완료");

})();