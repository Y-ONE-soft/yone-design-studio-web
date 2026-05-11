// 단일 .indd 파일 분석 — 스트리밍 방식 JSON 출력 (stack overflow 회피).
// $.evalFile로 호출되거나 SOURCE/OUTPUT 환경변수 또는 직접 호출.
//
// /tmp/extract_one_target.txt에서 읽어 처리할 파일 목록 받음.
//   각 줄: "<source_indd_path>\t<output_json_path>"

#target indesign

(function() {
    var TARGET_LIST = "/tmp/extract_one_target.txt";

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

    function jsonEscape(s) {
        if (s === null || s === undefined) return "null";
        s = String(s);
        var out = '"';
        for (var i = 0; i < s.length; i++) {
            var c = s.charCodeAt(i);
            if (c === 0x22) out += '\\"';
            else if (c === 0x5C) out += '\\\\';
            else if (c === 0x0A) out += '\\n';
            else if (c === 0x0D) out += '\\r';
            else if (c === 0x09) out += '\\t';
            else if (c < 0x20) {
                var hex = c.toString(16);
                while (hex.length < 4) hex = "0" + hex;
                out += '\\u' + hex;
            } else {
                out += s.charAt(i);
            }
        }
        return out + '"';
    }

    function isMasterPage(page) {
        try {
            return page && page.parent && page.parent.constructor.name === "MasterSpread";
        } catch(e) { return false; }
    }

    function processOne(srcPath, outPath) {
        var f = new File(srcPath);
        if (!f.exists) return "ERR: 파일 없음";
        var doc = app.open(f, false);

        var out = new File(outPath);
        out.encoding = "UTF-8";
        if (!out.open("w")) return "ERR: open 실패";

        // 스트리밍 JSON 출력
        out.write('{\n');
        out.write('  "file": ' + jsonEscape(f.fsName) + ',\n');
        out.write('  "basename": ' + jsonEscape(decodeURI(f.name)) + ',\n');
        out.write('  "page_count": ' + doc.pages.length + ',\n');

        // 인벤토리 (단락스타일만, 폰트 등 생략)
        out.write('  "inventory": {\n');
        out.write('    "paragraph_styles": [');
        var allPs = doc.allParagraphStyles;
        for (var i = 0; i < allPs.length; i++) {
            if (i > 0) out.write(', ');
            try {
                out.write('{"name": ' + jsonEscape(getPStyleFullName(allPs[i])));
                try { out.write(', "font": ' + jsonEscape(allPs[i].appliedFont.name)); } catch(e) {}
                try { out.write(', "size": ' + allPs[i].pointSize); } catch(e) {}
                out.write('}');
            } catch(e) { out.write('{}'); }
        }
        out.write('],\n');
        out.write('    "character_styles": [');
        var allCs = doc.allCharacterStyles;
        for (var j = 0; j < allCs.length; j++) {
            if (j > 0) out.write(', ');
            try { out.write('{"name": ' + jsonEscape(allCs[j].name) + '}'); } catch(e) { out.write('{}'); }
        }
        out.write(']\n');
        out.write('  },\n');

        // 페이지별
        out.write('  "pages": [\n');
        var pageWritten = 0;
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            if (isMasterPage(page)) continue;
            if (pageWritten > 0) out.write(',\n');

            out.write('    {');
            out.write('"page_index": ' + page.documentOffset);
            try { out.write(', "page_name": ' + jsonEscape(page.name)); } catch(e) {}
            try {
                var sd = page.side;
                var sdStr = (sd === PageSideOptions.LEFT_HAND) ? "left" :
                            (sd === PageSideOptions.RIGHT_HAND) ? "right" : String(sd);
                out.write(', "side": ' + jsonEscape(sdStr));
            } catch(e) {}

            // 텍스트프레임만
            out.write(', "text_frames": [');
            var items;
            try { items = page.allPageItems; } catch(e) { items = []; }
            var tfWritten = 0;
            var otherCnt = 0;
            for (var k = 0; k < items.length; k++) {
                var it = items[k];
                var ctor = "";
                try { ctor = it.constructor.name; } catch(e) { continue; }
                if (ctor !== "TextFrame") {
                    otherCnt++;
                    continue;
                }
                if (tfWritten > 0) out.write(', ');
                out.write('{');
                try {
                    out.write('"bounds": [' + it.geometricBounds.join(",") + ']');
                } catch(e) { out.write('"bounds": []'); }
                try { out.write(', "label": ' + jsonEscape(it.label)); } catch(e) {}
                try { out.write(', "cols": ' + it.textFramePreferences.textColumnCount); } catch(e) {}
                try { out.write(', "threaded_prev": ' + (it.previousTextFrame ? "true" : "false")); } catch(e) {}
                try { out.write(', "threaded_next": ' + (it.nextTextFrame ? "true" : "false")); } catch(e) {}

                out.write(', "paragraphs": [');
                try {
                    var paras = it.paragraphs;
                    var paraWritten = 0;
                    for (var pi = 0; pi < paras.length; pi++) {
                        var pa = paras[pi];
                        var text = "";
                        try { text = pa.contents; } catch(e) { continue; }
                        if (typeof text !== "string") continue;
                        if (paraWritten > 0) out.write(', ');
                        out.write('{"text": ' + jsonEscape(text));
                        try {
                            out.write(', "pstyle": ' + jsonEscape(getPStyleFullName(pa.appliedParagraphStyle)));
                        } catch(e) { out.write(', "pstyle": ""'); }
                        out.write('}');
                        paraWritten++;
                    }
                } catch(e) {
                    out.write('{"_error": ' + jsonEscape(String(e)) + '}');
                }
                out.write(']}');
                tfWritten++;
            }
            out.write(']');
            out.write(', "other_count": ' + otherCnt);
            out.write('}');
            pageWritten++;
        }
        out.write('\n  ]\n');
        out.write('}\n');
        out.close();
        try { doc.close(SaveOptions.NO); } catch(e) {}
        return "OK pages=" + pageWritten;
    }

    // 메인
    var lf = new File(TARGET_LIST);
    if (!lf.exists) return;
    lf.encoding = "UTF-8";
    lf.open("r");
    var raw = lf.read();
    lf.close();

    var lines = raw.split("\n");
    var logFile = new File("/tmp/extract_one_log.txt");
    logFile.encoding = "UTF-8";
    logFile.open("w");

    for (var li = 0; li < lines.length; li++) {
        var line = lines[li];
        if (!line || !line.length) continue;
        var parts = line.split("\t");
        if (parts.length < 2) continue;
        var src = parts[0];
        var dst = parts[1];
        try {
            var t0 = (new Date()).getTime();
            var res = processOne(src, dst);
            var t1 = (new Date()).getTime();
            logFile.writeln("[" + (li+1) + "] " + decodeURI((new File(src)).name) + " → " + res + " (" + (t1-t0) + "ms)");
        } catch(e) {
            logFile.writeln("[" + (li+1) + "] ERR: " + (e.message || e));
        }
    }

    logFile.close();
})();
