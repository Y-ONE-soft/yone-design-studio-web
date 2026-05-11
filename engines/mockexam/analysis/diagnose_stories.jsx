// 다른 학교 indd 템플릿의 스토리 구조 진단
// /tmp/diagnose_target.txt에서 indd 경로 목록 읽음

#target indesign

(function() {
    // 대화상자 자동 dismiss (누락 폰트/링크 등 경고)
    try {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    } catch(e) {}

    var TARGET_LIST = "/tmp/diagnose_target.txt";
    var OUTPUT = "/tmp/diagnose_stories.txt";

    function escapeText(s) {
        if (!s) return "";
        return String(s).replace(/[\r\n\t]/g, " ").substring(0, 80);
    }

    function diagnoseOne(srcPath, w) {
        var f = new File(srcPath);
        if (!f.exists) {
            w.writeln("[ERR] 파일 없음: " + srcPath);
            return;
        }
        var doc = app.open(f, false);

        w.writeln("=== " + decodeURI(srcPath.split("/").pop()) + " ===");
        w.writeln("페이지 수: " + doc.pages.length);
        w.writeln("스프레드 수: " + doc.spreads.length);
        w.writeln("전체 stories: " + doc.stories.length);
        w.writeln("");

        // 모든 stories 정보
        w.writeln("[전체 stories 인벤토리]");
        for (var i = 0; i < doc.stories.length; i++) {
            var st = doc.stories[i];
            var tfCount = 0;
            try { tfCount = st.textFrames.length; } catch(e) {}
            var paraCount = 0;
            try { paraCount = st.paragraphs.length; } catch(e) {}
            var contentLen = 0;
            try { contentLen = st.contents.length; } catch(e) {}
            var firstText = "";
            try { firstText = escapeText(st.contents.substring(0, 80)); } catch(e) {}
            w.writeln("  story[" + i + "]: " + tfCount + "frames, " + paraCount + "paras, " + contentLen + "chars | " + firstText);
        }
        w.writeln("");

        // 페이지별 textframes
        w.writeln("[페이지별 텍스트프레임]");
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            var pageName = "p" + (p + 1);
            try { pageName = "p" + page.name; } catch(e) {}
            w.writeln("  " + pageName + ": " + page.textFrames.length + "개 TF");
            for (var t = 0; t < page.textFrames.length; t++) {
                var tf = page.textFrames[t];
                var label = "";
                try { label = tf.label || ""; } catch(e) {}
                var contents = "";
                try { contents = escapeText(tf.contents.substring(0, 60)); } catch(e) {}
                var bnds = "?";
                try {
                    var b = tf.geometricBounds;
                    bnds = "[" + Math.round(b[0]) + "," + Math.round(b[1]) + "," + Math.round(b[2]) + "," + Math.round(b[3]) + "]";
                } catch(e) {}
                var storyId = "?";
                try {
                    if (tf.parentStory) storyId = tf.parentStory.id;
                } catch(e) {}
                w.writeln("    TF" + t + " " + bnds + " story=" + storyId + " label='" + label + "' | " + contents);
            }
        }
        w.writeln("");

        doc.close(SaveOptions.NO);
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

        var output = new File(OUTPUT);
        output.encoding = "UTF-8";
        output.open("w");
        for (var i = 0; i < lines.length; i++) {
            try {
                diagnoseOne(lines[i], output);
            } catch(e) {
                output.writeln("[ERR] " + lines[i] + ": " + e.message);
            }
        }
        output.close();
    }

    processList();
})();
