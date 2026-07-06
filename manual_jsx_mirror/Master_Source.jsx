if (app.documents.length === 0) {
    alert("열려 있는 문서가 없습니다.");
    exit();
}

var doc = app.activeDocument;

// 다른 열려 있는 문서에 설정돼 있던 기존 기준을 모두 해제하고
// 현재 문서로 기준을 이전한다.
var releasedNames = [];
for (var i = 0; i < app.documents.length; i++) {
    if (app.documents[i] === doc) continue;
    try {
        if (app.documents[i].extractLabel("MASTER_SOURCE") === "YES") {
            app.documents[i].insertLabel("MASTER_SOURCE", "");
            releasedNames.push(app.documents[i].name);
        }
    } catch (e) {}
}

doc.insertLabel("MASTER_SOURCE", "YES");

var msg = "이 문서는 마스터 기준 파일로 설정되었습니다.\n\n" +
    "파일명: " + doc.name;

if (releasedNames.length > 0) {
    msg += "\n\n기존 기준이 해제된 문서:\n";
    for (var j = 0; j < releasedNames.length; j++) {
        msg += "  - " + releasedNames[j] + "\n";
    }
}

alert(msg);