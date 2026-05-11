// 공통부품.indd 분석 — 라이브러리/개체 리스트 출력
#target indesign

(function() {
    var COMP_PATH = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/재사용부품/공통부품.indd";
    var OUT_PATH = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/조판_자동화/engines/mockexam/analysis/components.txt";

    function getPStyleFullName(ps) {
        if (!ps || !ps.isValid) return "";
        var n = "";
        try { n = ps.name; } catch(e) {}
        var p = null;
        try { p = ps.parent; } catch(e) {}
        var path = "";
        while (p && p.constructor && p.constructor.name === "ParagraphStyleGroup") {
            try { path = p.name + "/" + path; } catch(e) {}
            try { p = p.parent; } catch(e) { p = null; }
        }
        return path + n;
    }

    var lines = [];
    try {
        var file = new File(COMP_PATH);
        if (!file.exists) { lines.push("[오류] 파일 없음: " + COMP_PATH); }
        else {
            var doc = app.open(file, false);
            lines.push("=== 공통부품.indd ===");
            lines.push("페이지: " + doc.pages.length);
            lines.push("");
            lines.push("--- 단락 스타일 ---");
            for (var i = 0; i < doc.allParagraphStyles.length; i++) {
                lines.push("  " + getPStyleFullName(doc.allParagraphStyles[i]));
            }
            lines.push("");
            lines.push("--- 문자 스타일 ---");
            for (var j = 0; j < doc.allCharacterStyles.length; j++) {
                lines.push("  " + doc.allCharacterStyles[j].name);
            }
            lines.push("");
            lines.push("--- 페이지별 개체 ---");
            for (var p = 0; p < doc.pages.length; p++) {
                var pg = doc.pages[p];
                lines.push("페이지 " + (p+1) + " (name=" + pg.name + "):");
                var items = pg.allPageItems;
                for (var k = 0; k < items.length; k++) {
                    var it = items[k];
                    var ctor = "";
                    try { ctor = it.constructor.name; } catch(e) {}
                    var bnds = "";
                    try { bnds = "[" + it.geometricBounds.join(",") + "]"; } catch(e) {}
                    var lbl = "";
                    try { lbl = it.label || ""; } catch(e) {}
                    var preview = "";
                    if (ctor === "TextFrame") {
                        try { preview = it.contents.substring(0, 60).replace(/[\r\n]/g, "\\n"); } catch(e) {}
                    } else if (ctor === "Group") {
                        try {
                            var gItems = it.pageItems;
                            preview = gItems.length + " items";
                        } catch(e) {}
                    }
                    lines.push("  " + ctor + " bnds=" + bnds + " label=\"" + lbl + "\" preview=\"" + preview + "\"");
                }
            }
            doc.close(SaveOptions.NO);
        }
    } catch(e) {
        lines.push("[오류] " + (e.message || e));
    }
    var f = new File(OUT_PATH);
    f.encoding = "UTF-8";
    f.open("w");
    f.write(lines.join("\n"));
    f.close();
})();
