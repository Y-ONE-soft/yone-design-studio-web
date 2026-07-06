/*
    Master_Applied.jsx (Rebuilt Stable Version)
    - 기준 파일: document.extractLabel("MASTER_SOURCE") === "YES"
    - 대상 파일: 나머지 열린 문서 전부
*/

function withNoUI(fn) {
    var oldLevel = app.scriptPreferences.userInteractionLevel;
    try {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
        fn();
    } finally {
        try {
            app.scriptPreferences.userInteractionLevel = oldLevel;
        } catch (e) {}
    }
}

main();

function main() {

    if (app.documents.length < 2) {
        alert("기준 파일과 대상 파일을 모두 열어주세요.");
        return;
    }

    var sourceDoc = null;
    var targetDocs = [];

    for (var i = 0; i < app.documents.length; i++) {
        try {
            if (app.documents[i].extractLabel("MASTER_SOURCE") === "YES") {
                sourceDoc = app.documents[i];
                break;
            }
        } catch(e) {}
    }

    if (!sourceDoc) {
        alert("MASTER_SOURCE 라벨이 설정된 기준 파일을 찾을 수 없습니다.");
        return;
    }

    for (var i = 0; i < app.documents.length; i++) {
        if (app.documents[i] !== sourceDoc) {
            targetDocs.push(app.documents[i]);
        }
    }

    try {
        withNoUI(function () {
            for (var t = 0; t < targetDocs.length; t++) {

                var tgt = targetDocs[t];

                unlockEverything(sourceDoc);
                unlockEverything(tgt);

                finalPhysicalSync(sourceDoc, tgt);
                syncStyles(sourceDoc, tgt);
                relinkSpecialImages(tgt);
            }
        });

        alert("동기화 완료");

    } catch (e) {
        alert("에러: " + e.message);
    }
}

/* ============================= */
/* 🔵 마스터 동기화 */
/* ============================= */

function finalPhysicalSync(src, tgt) {

    var appliedBackup = [];
    for (var i = 0; i < tgt.pages.length; i++) {
        try {
            appliedBackup[i] = tgt.pages[i].appliedMaster
                ? tgt.pages[i].appliedMaster.name
                : null;
        } catch (e) { appliedBackup[i] = null; }
    }

    // 1) 먼저 source 마스터를 로드한다.
    //    기존처럼 전체 페이지를 [None]으로 돌리지 않아서
    //    페이지 위 텍스트박스/오브젝트에 영향을 최소화한다.
    try {
        tgt.loadMasters(src.fullName);
    } catch(e) {
        throw new Error("마스터 로드 실패: " + e.message);
    }

    // 2) source 기준 마스터 이름 목록을 만든다.
    var sourceNames = [];
    var sourceNameMap = {};
    for (var s = 0; s < src.masterSpreads.length; s++) {
        var sM = src.masterSpreads[s];
        if (sM.name === "[None]" || sM.name === "[없음]") continue;
        sourceNames.push(sM.name);
        sourceNameMap[sM.name] = true;
    }

    // 3) 기존에 적용되어 있던 마스터를 같은 이름으로 다시 연결해 준다.
    //    source 에 없는 이름이면 [None] 처리한다.
    for (var p = 0; p < tgt.pages.length; p++) {
        var oldName = appliedBackup[p];
        try {
            if (!oldName) {
                tgt.pages[p].appliedMaster = NothingEnum.NOTHING;
            } else if (sourceNameMap[oldName]) {
                var restored = tgt.masterSpreads.itemByName(oldName);
                if (restored && restored.isValid) {
                    tgt.pages[p].appliedMaster = restored;
                } else {
                    tgt.pages[p].appliedMaster = NothingEnum.NOTHING;
                }
            } else {
                tgt.pages[p].appliedMaster = NothingEnum.NOTHING;
            }
        } catch (e) {}
    }

    // 4) source 에 없는 target 마스터만 제거한다.
    //    전체 마스터를 무조건 삭제하지 않고 불필요한 것만 정리한다.
    for (var i = tgt.masterSpreads.length - 1; i >= 0; i--) {
        var m = tgt.masterSpreads[i];
        var name = m.name;

        if (name === "[None]" || name === "[없음]") continue;
        if (sourceNameMap[name]) continue;

        try { m.remove(); } catch(e) {}
    }

    // 5) source 순서와 동일하게 정렬한다.
    try {
        for (var r = sourceNames.length - 1; r >= 0; r--) {
            var orderedMaster = tgt.masterSpreads.itemByName(sourceNames[r]);
            if (orderedMaster && orderedMaster.isValid) {
                orderedMaster.move(LocationOptions.AT_BEGINNING);
            }
        }
    } catch(e) {}
}

/* ============================= */
/* 🔵 잠금 해제 */
/* ============================= */

function unlockEverything(doc) {
    try { doc.layers.everyItem().locked = false; } catch(e) {}
    try { doc.layers.everyItem().visible = true; } catch(e) {}
}

/* ============================= */
/* 🔵 스타일 동기화 */
/* ============================= */

function syncStyles(src, tgt) {
    try {
        tgt.importStyles(
            ImportFormat.PARAGRAPH_STYLES_FORMAT,
            src.fullName,
            GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE
        );
    } catch (e) {}

    try {
        tgt.importStyles(
            ImportFormat.CHARACTER_STYLES_FORMAT,
            src.fullName,
            GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE
        );
    } catch (e) {}
}

/* ============================= */
/* 🔵 링크 이름 정규화 */
/* ============================= */

function normalizeLinkName(name) {

    var n = name;

    n = n.replace("(B)", "");
    n = n.replace(/^간지_/, "");
    n = n.replace(/간지(?=\.[^.]+$)/, "");
    n = n.replace(/^마지막P(?=\.[^.]+$)/, "LastP");

    return n;
}

/* ============================= */
/* 🔵 링크 재연결 */
/* ============================= */

function relinkSpecialImages(doc) {

    var baseFolder = Folder("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비/인디자인 파일/이미지/워크북/C버전");
    if (!baseFolder.exists) return;

    // 🔵 C버전 폴더 전체 파일 수집
    var allFiles = [];
    var stack = [baseFolder];

    while (stack.length > 0) {

        var current = stack.pop();
        var items = current.getFiles();

        for (var s = 0; s < items.length; s++) {

            var it = items[s];

            if (it instanceof Folder) {
                stack.push(it);
                continue;
            }

            if (it instanceof File) {
                allFiles.push(it);
            }
        }
    }

    var links = doc.links;

    for (var i = 0; i < links.length; i++) {

        var link = links[i];
        var originalName = link.name;

        var targetName = normalizeLinkName(originalName);

        var relinked = false;

        for (var f = 0; f < allFiles.length; f++) {

            var file = allFiles[f];
            var fileName = file.name;

            if (
                fileName === originalName ||
                normalizeLinkName(fileName) === targetName
            ) {
                try {
                    link.relink(file);
                    link.update();
                    relinked = true;
                    break;
                } catch (e) {}
            }
        }

        if (!relinked) continue;
    }
}