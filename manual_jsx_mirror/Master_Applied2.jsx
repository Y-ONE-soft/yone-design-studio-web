/*
    Master_Applied2.jsx
    - 기준 파일: document.extractLabel("MASTER_SOURCE") === "YES"
    - 대상 파일: 현재 활성 문서만 (열린 모든 문서 X)
    - Master_Applied(C).jsx 기반 + relinkSpecialImages 포함
*/

main();

function main() {
    if (app.documents.length < 2) {
        alert("기준 파일과 대상 파일을 모두 열어주세요.");
        return;
    }

    var sourceDoc = null;
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

    // 현재 활성 문서만 대상
    var tgt = app.activeDocument;
    if (tgt === sourceDoc) {
        alert("현재 문서가 기준 파일입니다. 대상 파일을 활성화한 후 실행하세요.");
        return;
    }

    try {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

        app.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
        sourceDoc.zeroPoint = [0, 0];
        tgt.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
        tgt.zeroPoint = [0, 0];

        unlockEverything(sourceDoc);
        unlockEverything(tgt);
        syncLayers(sourceDoc, tgt);

        finalPhysicalSync(sourceDoc, tgt);
        syncStyles(sourceDoc, tgt);

        applyCMasterExceptFirst(tgt);
        applyGanjiToFirstPage(tgt);
        remapGanjiCharacterStyles(tgt);
        setFirstPageItemsYToZero(tgt);
        relinkSpecialImages(tgt);

        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
        alert("동기화 완료: " + tgt.name);

    } catch (e) {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
        alert("에러: " + e.message);
    }
}

/* ============================= */
/* 잠금 해제                      */
/* ============================= */
function unlockEverything(doc) {
    try { doc.layers.everyItem().locked = false; } catch(e) {}
    try { doc.layers.everyItem().visible = true; } catch(e) {}
    try { doc.masterSpreads.everyItem().pageItems.everyItem().locked = false; } catch(e) {}
}

/* ============================= */
/* 레이어 동기화                   */
/* ============================= */
function syncLayers(src, tgt) {
    for (var i = src.layers.length - 1; i >= 0; i--) {
        if (!tgt.layers.itemByName(src.layers[i].name).isValid) {
            tgt.layers.add({name: src.layers[i].name});
        }
    }
}

/* ============================= */
/* 마스터 동기화 (loadMasters 방식) */
/* ============================= */
function finalPhysicalSync(src, tgt) {
    var appliedBackup = [];
    for (var i = 0; i < tgt.pages.length; i++) {
        try {
            appliedBackup[i] = tgt.pages[i].appliedMaster
                ? tgt.pages[i].appliedMaster.name : null;
        } catch(e) { appliedBackup[i] = null; }
    }

    try { tgt.loadMasters(src.fullName); } catch(e) {
        throw new Error("마스터 로드 실패: " + e.message);
    }

    var sourceNameMap = {};
    for (var s = 0; s < src.masterSpreads.length; s++) {
        var sM = src.masterSpreads[s];
        if (sM.name === "[None]" || sM.name === "[없음]") continue;
        sourceNameMap[sM.name] = true;
    }

    for (var p = 0; p < tgt.pages.length; p++) {
        var oldName = appliedBackup[p];
        try {
            if (!oldName) {
                tgt.pages[p].appliedMaster = NothingEnum.NOTHING;
            } else if (sourceNameMap[oldName]) {
                var restored = tgt.masterSpreads.itemByName(oldName);
                if (restored && restored.isValid) {
                    tgt.pages[p].appliedMaster = restored;
                } else { tgt.pages[p].appliedMaster = NothingEnum.NOTHING; }
            } else { tgt.pages[p].appliedMaster = NothingEnum.NOTHING; }
        } catch(e) {}
    }

    for (var i = tgt.masterSpreads.length - 1; i >= 0; i--) {
        var m = tgt.masterSpreads[i];
        if (m.name === "[None]" || m.name === "[없음]") continue;
        if (sourceNameMap[m.name]) continue;
        try { m.remove(); } catch(e) {}
    }
}

/* ============================= */
/* 스타일 동기화                   */
/* ============================= */
function syncStyles(src, tgt) {
    try {
        tgt.importStyles(ImportFormat.PARAGRAPH_STYLES_FORMAT,
            src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
    } catch(e) {}
    try {
        tgt.importStyles(ImportFormat.CHARACTER_STYLES_FORMAT,
            src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
    } catch(e) {}
}

/* ============================= */
/* C 마스터 적용 (1페이지 제외)     */
/* ============================= */
function applyCMasterExceptFirst(doc) {
    var cMaster = null;
    for (var i = 0; i < doc.masterSpreads.length; i++) {
        if (/^C($|[\- _])/i.test(doc.masterSpreads[i].name)) {
            cMaster = doc.masterSpreads[i]; break;
        }
    }
    if (!cMaster) return;
    for (var p = 1; p < doc.pages.length; p++) {
        try { doc.pages[p].appliedMaster = cMaster; } catch(e) {}
    }
}

/* ============================= */
/* 간지 마스터 적용 (1페이지)       */
/* ============================= */
function applyGanjiToFirstPage(doc) {
    if (doc.pages.length === 0) return;
    var firstPage = doc.pages[0];

    // 1페이지에서 간지 문자스타일 그룹에 속하지 않은 개체는 삭제
    var items = firstPage.pageItems.everyItem().getElements();
    for (var i = items.length - 1; i >= 0; i--) {
        try {
            var item = items[i];
            var keep = false;
            if (!(item instanceof TextFrame)) { item.remove(); continue; }
            if (item.texts.length > 0) {
                var chars = item.texts[0].characters;
                for (var c = 0; c < chars.length; c++) {
                    try {
                        var cs = chars[c].appliedCharacterStyle;
                        if (cs.parent && cs.parent.constructor.name === "CharacterStyleGroup"
                            && cs.parent.name === "간지") { keep = true; break; }
                    } catch(e) {}
                }
            }
            if (!keep) item.remove();
        } catch(e) {}
    }

    // 간지-마스터 적용
    var ganjiMaster = null;
    for (var m = 0; m < doc.masterSpreads.length; m++) {
        if (doc.masterSpreads[m].name === "간지-마스터") {
            ganjiMaster = doc.masterSpreads[m]; break;
        }
    }
    if (ganjiMaster) {
        try { firstPage.appliedMaster = ganjiMaster; } catch(e) {}
    }
}

/* ============================= */
/* 간지 문자스타일 리맵핑           */
/* ============================= */
function remapGanjiCharacterStyles(doc) {
    function getCS(gn, sn) {
        try {
            var grp = doc.characterStyleGroups.itemByName(gn);
            if (!grp.isValid) return null;
            var st = grp.characterStyles.itemByName(sn);
            return st.isValid ? st : null;
        } catch(e) { return null; }
    }
    function replaceCS(fromS, toS) {
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findTextPreferences.appliedCharacterStyle = fromS;
        app.changeTextPreferences.appliedCharacterStyle = toS;
        try { doc.changeText(); } catch(e) {}
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
    }
    var f1 = getCS("간지", "카테고리"), t1 = getCS("간지", "범위");
    if (f1 && t1) replaceCS(f1, t1);
    var f2 = getCS("간지", "부제목"), t2 = getCS("간지", "범위_추가내용");
    if (f2 && t2) replaceCS(f2, t2);
}

/* ============================= */
/* 1페이지 개체 Y=0 정렬          */
/* ============================= */
function setFirstPageItemsYToZero(doc) {
    if (doc.pages.length === 0) return;
    var p = doc.pages[0];
    var items = p.pageItems.everyItem().getElements();
    for (var i = 0; i < items.length; i++) {
        try {
            try { items[i].locked = false; } catch(e) {}
            var gb = items[i].geometricBounds;
            if (!gb || gb.length !== 4) continue;
            var h = gb[2] - gb[0];
            items[i].geometricBounds = [0 - h, gb[1], 0, gb[3]];
        } catch(e) {}
    }
}

/* ============================= */
/* 링크 재연결                     */
/* ============================= */
function relinkSpecialImages(doc) {
    var baseFolder = Folder("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비/인디자인 파일/이미지/워크북/C버전");
    if (!baseFolder.exists) return;

    var allFiles = [];
    var stack = [baseFolder];
    while (stack.length > 0) {
        var cur = stack.pop();
        var items = cur.getFiles();
        for (var s = 0; s < items.length; s++) {
            if (items[s] instanceof Folder) stack.push(items[s]);
            else if (items[s] instanceof File) allFiles.push(items[s]);
        }
    }

    function normName(name) {
        var n = name;
        n = n.replace("(B)", "");
        n = n.replace(/^간지_/, "");
        n = n.replace(/간지(?=\.[^.]+$)/, "");
        n = n.replace(/^마지막P(?=\.[^.]+$)/, "LastP");
        return n;
    }

    var links = doc.links;
    for (var i = 0; i < links.length; i++) {
        var lk = links[i];
        var origName = lk.name;
        var tgtName = normName(origName);
        for (var f = 0; f < allFiles.length; f++) {
            if (allFiles[f].name === origName || normName(allFiles[f].name) === tgtName) {
                try { lk.relink(allFiles[f]); lk.update(); } catch(e) {}
                break;
            }
        }
    }
}
