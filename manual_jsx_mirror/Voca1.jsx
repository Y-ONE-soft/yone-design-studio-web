#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("열려 있는 문서가 없습니다.");
        return;
    }

    var doc = app.activeDocument;

    // 단락스타일 이름
    var targetStyleName = "파생어";

    // 단락스타일 존재 확인
    var targetStyle;
    try {
        targetStyle = doc.paragraphStyles.itemByName(targetStyleName);
        targetStyle.name; // 존재 체크
    } catch (e) {
        alert("단락스타일 '파생어' 를 찾을 수 없습니다.");
        return;
    }

    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    // 🔎 찾기 설정
    app.findGrepPreferences.findWhat = "(?<=[가-힣\\)])\\x{0020}(?=[A-Za-z])";
    app.findGrepPreferences.appliedParagraphStyle = targetStyle;

    // 🔁 바꾸기 설정
    app.changeGrepPreferences.changeTo = "\\r";

    // 실행
    var result = doc.changeGrep();

    // 초기화
    app.findGrepPreferences = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    alert("완료: " + result.length + "개 변경됨.");

})();