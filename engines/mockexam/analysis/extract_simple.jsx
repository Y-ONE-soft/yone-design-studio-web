// 단락별 (페이지, 스타일, 텍스트 80자) 만 추출 — JSON 안전.
// /tmp/extract_simple_target.txt에서 indd 경로 + 출력 경로 읽음.

#target indesign

(function() {
    try {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    } catch(e) {}

    var TARGET_LIST = "/tmp/extract_simple_target.txt";

    function getStyleName(ps) {
        if (!ps || !ps.isValid) return "";
        try { return ps.name || ""; } catch(e) { return ""; }
    }

    function escForTSV(s) {
        if (!s) return "";
        s = String(s).substring(0, 100);
        return s.replace(/[\r\n\t]/g, " ");
    }

    function processOne(srcPath, outPath) {
        var f = new File(srcPath);
        if (!f.exists) return "ERR: 파일 없음";
        var doc = app.open(f, false);

        var out = new File(outPath);
        out.encoding = "UTF-8";
        out.open("w");

        // 페이지별 텍스트프레임 별 단락
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            var pageName = "p" + (p + 1);
            try { pageName = "p" + page.name; } catch(e) {}

            for (var t = 0; t < page.textFrames.length; t++) {
                var tf = page.textFrames[t];
                try {
                    if (tf.parentPage && tf.parentPage.parent &&
                        tf.parentPage.parent.constructor.name === "MasterSpread") continue;
                } catch(e) {}

                for (var pi = 0; pi < tf.paragraphs.length; pi++) {
                    var para = tf.paragraphs[pi];
                    var pstyle = "";
                    try { pstyle = getStyleName(para.appliedParagraphStyle); } catch(e) {}
                    var content = "";
                    try { content = escForTSV(para.contents); } catch(e) {}
                    out.writeln(pageName + "\t" + t + "\t" + pi + "\t" + pstyle + "\t" + content);
                }
            }
        }

        out.close();
        doc.close(SaveOptions.NO);
        return "OK";
    }

    function processList() {
        var listFile = new File(TARGET_LIST);
        if (!listFile.exists) return;
        listFile.encoding = "UTF-8";
        listFile.open("r");
        var lines = [];
        while (!listFile.eof) {
            var line = listFile.readln();
            if (line && line.length > 0) lines.push(line);
        }
        listFile.close();

        for (var i = 0; i < lines.length; i++) {
            var parts = lines[i].split("\t");
            if (parts.length < 2) continue;
            try {
                processOne(parts[0], parts[1]);
            } catch(e) {
                $.writeln("[ERR] " + parts[0] + ": " + e.message);
            }
        }
    }

    processList();
})();
