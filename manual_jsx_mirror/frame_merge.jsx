if (app.selection.length < 2) {
    alert("텍스트 프레임을 2개 이상 선택하세요.");
    exit();
}

var frames = [];

// 텍스트프레임만 수집
for (var i = 0; i < app.selection.length; i++) {
    if (app.selection[i] instanceof TextFrame) {
        frames.push(app.selection[i]);
    }
}

if (frames.length < 2) {
    alert("텍스트 프레임이 부족합니다.");
    exit();
}

// 정렬: 페이지 → 왼쪽좌표
frames.sort(function(a, b){

    var pageA = a.parentPage.documentOffset;
    var pageB = b.parentPage.documentOffset;

    if (pageA != pageB) {
        return pageA - pageB;
    }

    return a.geometricBounds[1] - b.geometricBounds[1];
});

// 기존 연결 제거
for (var i = 0; i < frames.length; i++){
    frames[i].previousTextFrame = null;
    frames[i].nextTextFrame = null;
}

// 순서대로 연결
for (var i = 0; i < frames.length - 1; i++){
    frames[i].nextTextFrame = frames[i+1];
}

// 마지막 프레임 선택 (사용자가 다음 프레임을 수동 연결할 수 있게)
app.select(frames[frames.length - 1]);