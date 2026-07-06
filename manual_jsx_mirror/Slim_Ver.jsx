#target "InDesign"

(function () {

    if (app.documents.length === 0) {
        alert("문서를 열어주세요.");
        return;
    }

    var doc = app.activeDocument;

    // 🔵 단원 스타일 가져오기 (그룹 포함 정밀 검색)
    var unitStyle = null;
    var isCharacterStyle = true;

    // 1️⃣ 문자스타일 그룹 "마스터페이지" 안에서 먼저 검색
    var group = doc.characterStyleGroups.itemByName("마스터페이지");
    if (group.isValid) {
        unitStyle = group.characterStyles.itemByName("단원");
        if (unitStyle.isValid) {
            isCharacterStyle = true;
        }
    }

    // 2️⃣ 전체 문자스타일에서 검색 (fallback)
    if (!unitStyle || !unitStyle.isValid) {
        unitStyle = doc.characterStyles.itemByName("단원");
        if (unitStyle.isValid) {
            isCharacterStyle = true;
        }
    }

    // 3️⃣ 단락스타일에서도 검색
    if (!unitStyle || !unitStyle.isValid) {
        unitStyle = doc.paragraphStyles.itemByName("단원");
        if (unitStyle.isValid) {
            isCharacterStyle = false;
        }
    }

    if (!unitStyle || !unitStyle.isValid) {
        alert("'마스터페이지 > 단원' 스타일을 찾을 수 없습니다.");
        return;
    }

    // 🔵 트리거 텍스트
    var triggerTexts = [
        "어휘 선택 2",
        "본문 정리",
        "내용 종합",
        "어법 O/X",
        "빈칸 어법"
    ];

    var pages = doc.pages;
    var unitPages = [];
    var deleteRanges = [];

    // 🔵 1️⃣ 단원 스타일이 적용된 페이지 찾기 (고속 검색 방식)
    app.findTextPreferences = NothingEnum.nothing;
    app.changeTextPreferences = NothingEnum.nothing;

    if (isCharacterStyle) {
        app.findTextPreferences.appliedCharacterStyle = unitStyle;
    } else {
        app.findTextPreferences.appliedParagraphStyle = unitStyle;
    }

    var foundItems = doc.findText();

    var checkedPages = {};

    for (var f = 0; f < foundItems.length; f++) {

        var parentPage = foundItems[f].parentTextFrames[0].parentPage;
        if (!parentPage) continue;

        var pageIndex = parentPage.documentOffset;

        // 같은 페이지 중복 방지
        if (checkedPages[pageIndex]) continue;
        checkedPages[pageIndex] = true;

        unitPages.push({
            pageIndex: pageIndex,
            text: foundItems[f].contents
        });
    }

    // 🔵 unitPages를 pageIndex 기준으로 정렬 (중요)
    unitPages.sort(function(a, b) {
        return a.pageIndex - b.pageIndex;
    });

    app.findTextPreferences = NothingEnum.nothing;
    app.changeTextPreferences = NothingEnum.nothing;

    // 🔵 2️⃣ 삭제 범위 계산

    for (var u = 0; u < unitPages.length; u++) {

        var currentPageIndex = unitPages[u].pageIndex;
        var currentText = unitPages[u].text;
        var matchedTrigger = null;

        var normalizedCurrent = currentText.replace(/\s+/g, "");

        for (var t = 0; t < triggerTexts.length; t++) {
            var normalizedTrigger = triggerTexts[t].replace(/\s+/g, "");
            if (normalizedCurrent.indexOf(normalizedTrigger) !== -1) {
                matchedTrigger = triggerTexts[t];
                break;
            }
        }

        if (!matchedTrigger) continue;

        // 🔵 다음 unitPages[u+1]만 사용 (정렬되어 있으므로 안전)
        var nextUnitIndex = (u + 1 < unitPages.length)
            ? unitPages[u + 1].pageIndex
            : doc.pages.length;

        deleteRanges.push({
            start: currentPageIndex,
            end: nextUnitIndex - 1,
            trigger: matchedTrigger
        });
    }

    if (deleteRanges.length === 0) {
        alert("삭제 대상이 없습니다.");
        return;
    }

    // 🔵 3️⃣ 삭제 목록 메시지 생성
    var message = "[삭제 예정 목록]\r\r";

    for (var r = 0; r < deleteRanges.length; r++) {

        message +=
            (deleteRanges[r].start + 1) + "페이지 ~ " +
            (deleteRanges[r].end + 1) + "페이지\r" +
            "트리거: " + deleteRanges[r].trigger + "\r\r";
    }

    message += "계속 진행하시겠습니까?";

    var confirmDelete = confirm(message);

    if (!confirmDelete) {
        alert("취소되었습니다.");
        return;
    }

    // 🔵 4️⃣ 실제 삭제 (뒤에서부터, 안전 방식)
    for (var r = deleteRanges.length - 1; r >= 0; r--) {

        var start = deleteRanges[r].start;
        var end = deleteRanges[r].end;

        for (var p = end; p >= start; p--) {

            if (p < doc.pages.length) {
                doc.pages[p].remove();
            }
        }
    }

    alert("삭제 완료.");

})();