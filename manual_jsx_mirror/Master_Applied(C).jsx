/*
    InDesign Master Page Sync - Total Group Strategy
    - 해결: 왼쪽 페이지 그룹 개체 누락 (좌표 유실 방지)
    - 해결: duplicate/snippet 실패 케이스 완벽 대응
    - 원리: 왼쪽/오른쪽 페이지별로 모든 개체를 임시 그룹화하여 물리적 복제
*/

main();

function main() {
    if (app.documents.length < 2) {
        alert("기준 파일과 대상 파일을 모두 열어주세요.");
        return;
    }

    var sourceDoc = null;
    var targetDocs = [];
    
    for (var i = 0; i < app.documents.length; i++) {
        if (app.documents[i].extractLabel("MASTER_SOURCE") === "YES") {
            sourceDoc = app.documents[i];
        } else {
            targetDocs.push(app.documents[i]);
        }
    }

    if (!sourceDoc) {
        alert("기준 파일(MASTER_SOURCE 라벨)을 찾을 수 없습니다.");
        return;
    }

    try {
        app.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
        sourceDoc.zeroPoint = [0, 0];

        for (var t = 0; t < targetDocs.length; t++) {
            var tDoc = targetDocs[t];
            tDoc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
            tDoc.zeroPoint = [0, 0];
            
            unlockEverything(sourceDoc);
            unlockEverything(tDoc);
            syncLayers(sourceDoc, tDoc);

            finalPhysicalSync(sourceDoc, tDoc);
            syncStyles(sourceDoc, tDoc);

            // 🔥 추가: 1페이지 제외 모든 페이지에 C 마스터 적용
            applyCMasterExceptFirst(tDoc);
            applyGanjiToFirstPage(tDoc);
            remapGanjiCharacterStyles(tDoc);
            setFirstPageItemsYToZero(tDoc);
        }
        alert("동기화가 완료되었습니다. 모든 개체가 복제되었는지 확인해 주세요.");
    } catch (e) {
        alert("에러: " + e.message);
    }
}

function applyCMasterExceptFirst(doc) {
    var cMaster = null;

    for (var i = 0; i < doc.masterSpreads.length; i++) {
        var name = doc.masterSpreads[i].name;
        if (/^C($|[\- _])/i.test(name)) {
            cMaster = doc.masterSpreads[i];
            break;
        }
    }

    if (!cMaster) {
        alert("문서 '" + doc.name + "'에 C 마스터가 없습니다.");
        return;
    }

    for (var p = 1; p < doc.pages.length; p++) {
        try {
            doc.pages[p].appliedMaster = cMaster;
        } catch (_) {}
    }
}

function applyGanjiToFirstPage(doc) {
    if (doc.pages.length === 0) return;

    var firstPage = doc.pages[0];

    // 1️⃣ 1페이지에서 문자스타일 그룹 '간지'에 속하지 않은 개체는 전부 삭제
    var items = firstPage.pageItems.everyItem().getElements();

    for (var i = items.length - 1; i >= 0; i--) {
        try {
            var item = items[i];
            var keep = false;

            // 텍스트박스가 아닌 개체는 무조건 삭제
            if (!(item instanceof TextFrame)) {
                item.remove();
                continue;
            }

            // 텍스트박스인 경우 → 내부 문자스타일 중 하나라도 '간지' 그룹이면 유지
            if (item.texts.length > 0) {
                var chars = item.texts[0].characters;

                for (var c = 0; c < chars.length; c++) {
                    var cStyle = chars[c].appliedCharacterStyle;

                    try {
                        if (
                            cStyle.parent &&
                            cStyle.parent.constructor.name === "CharacterStyleGroup" &&
                            cStyle.parent.name === "간지"
                        ) {
                            keep = true;
                            break;
                        }
                    } catch(_) {}
                }
            }

            if (!keep) {
                item.remove();
            }

        } catch (_) {}
    }

    // 2️⃣ 간지-마스터 찾기
    var ganjiMaster = null;
    for (var m = 0; m < doc.masterSpreads.length; m++) {
        if (doc.masterSpreads[m].name === "간지-마스터") {
            ganjiMaster = doc.masterSpreads[m];
            break;
        }
    }

    if (!ganjiMaster) {
        alert("문서 '" + doc.name + "'에 '간지-마스터'가 없습니다.");
        return;
    }

    // 3️⃣ 1페이지에 간지_마스터 적용
    try {
        firstPage.appliedMaster = ganjiMaster;
    } catch (_) {}
}

function remapGanjiCharacterStyles(doc) {
    // 모든 작업이 끝난 후: '간지' 문자스타일 그룹 내 스타일 치환
    // 카테고리 -> 범위, 부제목 -> 범위_추가내용

    function getCharStyleInGroup(groupName, styleName) {
        try {
            var grp = doc.characterStyleGroups.itemByName(groupName);
            if (!grp.isValid) return null;
            var st = grp.characterStyles.itemByName(styleName);
            if (!st.isValid) return null;
            return st;
        } catch (_) {
            return null;
        }
    }

    var from1 = getCharStyleInGroup("간지", "카테고리");
    var to1   = getCharStyleInGroup("간지", "범위");
    var from2 = getCharStyleInGroup("간지", "부제목");
    var to2   = getCharStyleInGroup("간지", "범위_추가내용");

    // 스타일이 없으면 조용히 종료(필요 시 경고로 바꿀 수 있음)
    if (!from1 || !to1) {
        // alert("문서 '" + doc.name + "'에서 '간지' 그룹의 카테고리/범위 문자스타일을 찾지 못했습니다.");
    } else {
        replaceCharStyle(doc, from1, to1);
    }

    if (!from2 || !to2) {
        // alert("문서 '" + doc.name + "'에서 '간지' 그룹의 부제목/범위_추가내용 문자스타일을 찾지 못했습니다.");
    } else {
        replaceCharStyle(doc, from2, to2);
    }

    // 안전: find/change 환경 초기화
    app.findTextPreferences = NothingEnum.NOTHING;
    app.changeTextPreferences = NothingEnum.NOTHING;

    function replaceCharStyle(doc, fromStyle, toStyle) {
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;

        app.findTextPreferences.appliedCharacterStyle = fromStyle;
        app.changeTextPreferences.appliedCharacterStyle = toStyle;

        try {
            doc.changeText();
        } catch (_) {}

        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
    }
}

function setFirstPageItemsYToZero(doc) {
    // 모든 작업이 끝난 후: 1페이지에 존재하는 모든 개체의 Y(상단) 값을 0으로 정렬
    if (doc.pages.length === 0) return;

    var p = doc.pages[0];
    var items = p.pageItems.everyItem().getElements();

    for (var i = 0; i < items.length; i++) {
        try {
            var it = items[i];

            // 잠김 방지
            try { it.locked = false; } catch (_) {}

            // geometricBounds: [y1, x1, y2, x2]
            var gb = it.geometricBounds;
            if (!gb || gb.length !== 4) continue;

            var y1 = gb[0], x1 = gb[1], y2 = gb[2], x2 = gb[3];
            var h = y2 - y1;

            // 하단(Y2)을 0으로 이동 (높이 유지)
            // 결과: [y1, x1, y2, x2]에서 y2=0, y1=-h
            it.geometricBounds = [0 - h, x1, 0, x2];
        } catch (_) {}
    }
}

function finalPhysicalSync(src, tgt) {
    var srcMasters = src.masterSpreads;

    for (var i = 0; i < srcMasters.length; i++) {
        var sM = srcMasters[i];
        var tM = tgt.masterSpreads.itemByName(sM.name);

        // 혹시 기존에 접두어만 같은 다른 이름이 있을 경우 강제 이름 동기화
        if (tM.isValid) {
            try {
                tM.namePrefix = sM.namePrefix;
                tM.baseName = sM.baseName;
            } catch(e) {}
        }

        if (!tM.isValid) {
            tM = tgt.masterSpreads.add();
            try {
                // 기준 파일의 접두어(A,B,C 등)와 이름을 그대로 복사
                tM.namePrefix = sM.namePrefix;
                tM.baseName = sM.baseName;
            } catch(e) {}
        }

        tM.pageItems.everyItem().remove();

        for (var p = 0; p < sM.pages.length; p++) {
            var sPage = sM.pages[p];
            var tPage = tM.pages[p];
            
            var items = sPage.pageItems.everyItem().getElements();
            if (items.length === 0) continue;

            var tempGroup = null;
            if (items.length > 1) {
                tempGroup = sPage.groups.add(items);
            } else {
                tempGroup = items[0];
            }

            try {
                var clonedItem = tempGroup.duplicate(tPage, [0, 0]);
                if (clonedItem.constructor.name === "Group") clonedItem.ungroup();
            } catch(e) {
                app.select(tempGroup);
                app.copy();
                app.activeWindow = tgt.layoutWindows[0];
                app.activeWindow.activeSpread = tM;
                app.activeWindow.activePage = tPage;
                app.pasteInPlace();
                app.activeWindow = src.layoutWindows[0];
            }

            if (tempGroup.constructor.name === "Group") tempGroup.ungroup();
        }

        for (var m = 0; m < sM.pages.length; m++) {
            tM.pages[m].marginPreferences.properties = sM.pages[m].marginPreferences.properties;
        }
    }
}

function unlockEverything(doc) {
    doc.layers.everyItem().locked = false;
    doc.layers.everyItem().visible = true;
    doc.masterSpreads.everyItem().pageItems.everyItem().locked = false;
}

function syncLayers(src, tgt) {
    for (var i = src.layers.length - 1; i >= 0; i--) {
        if (!tgt.layers.itemByName(src.layers[i].name).isValid) {
            tgt.layers.add({name: src.layers[i].name});
        }
    }
}

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
