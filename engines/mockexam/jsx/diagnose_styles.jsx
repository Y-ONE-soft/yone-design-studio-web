#target indesign

// diagnose_styles.jsx
// 동형모의고사 InDesign 템플릿의 단락 스타일, 문자 스타일,
// 마스터 페이지 구조, 텍스트 프레임 레이블을 덤프하는 진단 스크립트.
// 결과는 스크립트와 같은 폴더에 _diagnose_result.txt로 저장.

(function() {
    if (app.documents.length === 0) {
        alert("열려 있는 문서가 없습니다.");
        return;
    }

    var doc = app.activeDocument;
    var lines = [];

    lines.push("=== 동형모의고사 템플릿 진단 ===");
    lines.push("파일: " + doc.fullName);
    lines.push("페이지 수: " + doc.pages.length);
    lines.push("");

    // 1. 단락 스타일
    lines.push("--- 단락 스타일 ---");
    var pStyles = doc.allParagraphStyles;
    for (var i = 0; i < pStyles.length; i++) {
        var ps = pStyles[i];
        var groupPath = "";
        try {
            var parent = ps.parent;
            while (parent && parent.constructor.name === "ParagraphStyleGroup") {
                groupPath = parent.name + "/" + groupPath;
                parent = parent.parent;
            }
        } catch(e) {}
        var info = groupPath + ps.name;
        info += "  |  font: ";
        try { info += ps.appliedFont.name; } catch(e) { info += "?"; }
        info += "  |  size: ";
        try { info += ps.pointSize; } catch(e) { info += "?"; }
        info += "  |  leading: ";
        try { info += ps.leading; } catch(e) { info += "?"; }
        info += "  |  spBefore: ";
        try { info += ps.spaceBefore; } catch(e) { info += "?"; }
        info += "  |  spAfter: ";
        try { info += ps.spaceAfter; } catch(e) { info += "?"; }
        lines.push("  [" + i + "] " + info);
    }
    lines.push("");

    // 2. 문자 스타일
    lines.push("--- 문자 스타일 ---");
    var cStyles = doc.allCharacterStyles;
    for (var j = 0; j < cStyles.length; j++) {
        var cs = cStyles[j];
        var csInfo = cs.name;
        try {
            if (cs.underline === true) csInfo += "  [밑줄]";
        } catch(e) {}
        lines.push("  [" + j + "] " + csInfo);
    }
    lines.push("");

    // 3. 마스터 페이지
    lines.push("--- 마스터 페이지 ---");
    for (var m = 0; m < doc.masterSpreads.length; m++) {
        var ms = doc.masterSpreads[m];
        lines.push("  마스터: " + ms.name + " (" + ms.pages.length + "페이지)");
        for (var mp = 0; mp < ms.pages.length; mp++) {
            var mPage = ms.pages[mp];
            lines.push("    페이지[" + mp + "] side=" + mPage.side);
            for (var ti = 0; ti < mPage.textFrames.length; ti++) {
                var tf = mPage.textFrames[ti];
                var tfInfo = "      TF[" + ti + "]";
                tfInfo += " label=\"" + tf.label + "\"";
                tfInfo += " bounds=" + tf.geometricBounds.join(",");
                var txt = "";
                try { txt = tf.contents.substring(0, 80); } catch(e) {}
                tfInfo += " text=\"" + txt.replace(/[\r\n]/g, "\\n") + "\"";
                lines.push(tfInfo);
            }
        }
    }
    lines.push("");

    // 4. 본문 페이지 텍스트 프레임 (처음 3페이지만)
    lines.push("--- 본문 텍스트 프레임 (처음 3페이지) ---");
    var maxPages = Math.min(doc.pages.length, 3);
    for (var p = 0; p < maxPages; p++) {
        var page = doc.pages[p];
        lines.push("  페이지[" + p + "] name=" + page.name);
        for (var fi = 0; fi < page.textFrames.length; fi++) {
            var frame = page.textFrames[fi];
            var fInfo = "    TF[" + fi + "]";
            fInfo += " label=\"" + frame.label + "\"";
            fInfo += " bounds=" + frame.geometricBounds.join(",");
            fInfo += " cols=" + frame.textFramePreferences.textColumnCount;
            // threaded?
            if (frame.nextTextFrame) {
                fInfo += " -> threaded";
            }
            if (frame.previousTextFrame) {
                fInfo += " <- threaded";
            }
            var content = "";
            try { content = frame.contents.substring(0, 60); } catch(e) {}
            fInfo += " text=\"" + content.replace(/[\r\n]/g, "\\n") + "\"";
            lines.push(fInfo);
        }
    }
    lines.push("");

    // 5. 레이블이 있는 모든 아이템
    lines.push("--- 레이블 있는 PageItem ---");
    var allItems = doc.allPageItems;
    for (var k = 0; k < allItems.length; k++) {
        if (allItems[k].label && allItems[k].label !== "") {
            lines.push("  " + allItems[k].constructor.name + " label=\"" + allItems[k].label + "\" bounds=" + allItems[k].geometricBounds.join(","));
        }
    }

    // 결과 저장
    var resultPath = doc.fullName.toString().replace(/\.indd$/i, "_diagnose.txt");
    // 스크립트 폴더에 저장
    var scriptFolder = (new File($.fileName)).parent;
    var resultFile = new File(scriptFolder + "/_diagnose_result.txt");
    resultFile.encoding = "UTF-8";
    resultFile.open("w");
    resultFile.write(lines.join("\n"));
    resultFile.close();

    alert("진단 완료!\n결과: " + resultFile.fsName + "\n단락 스타일 " + pStyles.length + "개, 문자 스타일 " + cStyles.length + "개");
})();
