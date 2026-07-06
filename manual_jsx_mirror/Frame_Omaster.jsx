var doc = app.activeDocument;
var pages = doc.pages;

var prevFrame = null;
var prevMaster = null;

for (var i = 0; i < pages.length; i++) {

    var page = pages[i];
    var master = page.appliedMaster ? page.appliedMaster.name : "";

    // O 마스터가 아니면 스토리 끊기
    if (master.indexOf("O") !== 0) {
        prevFrame = null;
        prevMaster = null;
        continue;
    }

    var allFrames = page.textFrames.everyItem().getElements();
    var frames = [];

    for (var tf = 0; tf < allFrames.length; tf++) {
        try {
            var paras = allFrames[tf].paragraphs;
            for (var p = 0; p < paras.length; p++) {
                if (paras[p].appliedParagraphStyle && paras[p].appliedParagraphStyle.name == "실전 문제 지문 올림포스") {
                    frames.push(allFrames[tf]);
                    break;
                }
            }
        } catch(e) {}
    }

    if (frames.length < 2) continue;

    // 좌우 정렬
    frames.sort(function(a,b){
        return a.geometricBounds[1] - b.geometricBounds[1];
    });

    for (var f = 0; f < frames.length; f++) {

        if (prevFrame && prevFrame.isValid && frames[f] && frames[f].isValid) {
            try {
                prevFrame.nextTextFrame = frames[f];
            } catch(e) {
                // 이미 연결되어 있거나 잘못된 경우 무시
            }
        }

        prevFrame = frames[f];
    }

    prevMaster = master;
}

// 마지막 프레임 선택
if (prevFrame) app.select(prevFrame);