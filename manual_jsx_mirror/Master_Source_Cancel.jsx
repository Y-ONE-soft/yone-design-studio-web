if (app.documents.length === 0) {
    alert("열려 있는 문서가 없습니다.");
    exit();
}

var doc = app.activeDocument;

if (doc.extractLabel("MASTER_SOURCE") !== "YES") {
    alert("이 문서는 마스터 기준 파일이 아닙니다.");
    exit();
}

doc.insertLabel("MASTER_SOURCE", "");

alert(
    "마스터 기준 설정이 해제되었습니다.\n\n" +
    "파일명: " + doc.name
);