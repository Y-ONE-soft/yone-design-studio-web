// 학교별 .indd의 페이스트보드(페이지 밖) 영역 개체 분석.
// /tmp/pasteboard_target.txt 의 한 파일씩 (탭 구분: src \t out)
//
// 출력: 각 indd의 spread 단위 페이스트보드 개체 카탈로그

#target indesign

(function() {
    var TARGET_LIST = "/tmp/pasteboard_target.txt";

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
            } else { out += s.charAt(i); }
        }
        return out + '"';
    }

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

    function processOne(srcPath, outPath) {
        var f = new File(srcPath);
        if (!f.exists) return "ERR: 파일 없음";
        var doc = app.open(f, false);
        var out = new File(outPath);
        out.encoding = "UTF-8";
        out.open("w");

        out.write('{\n');
        out.write('  "file": ' + jsonEscape(decodeURI(f.name)) + ',\n');
        out.write('  "spreads": [\n');
        var sw = 0;
        for (var s = 0; s < doc.spreads.length; s++) {
            var spread = doc.spreads[s];
            var pageBounds = [];
            // 모든 페이지 bounds 수집
            for (var pi = 0; pi < spread.pages.length; pi++) {
                try { pageBounds.push(spread.pages[pi].bounds); } catch(e) {}
            }

            if (sw > 0) out.write(',\n');
            out.write('    {');
            out.write('"index": ' + s);
            try { out.write(', "page_count": ' + spread.pages.length); } catch(e) {}
            out.write(', "items_outside_pages": [');

            // spread.allPageItems → 페이지 안 vs 밖 구분
            var items;
            try { items = spread.allPageItems; } catch(e) { items = []; }
            var iw = 0;
            for (var k = 0; k < items.length; k++) {
                var it = items[k];
                var ctor = "";
                try { ctor = it.constructor.name; } catch(e) { continue; }
                var bnds = null;
                try { bnds = it.geometricBounds; } catch(e) { continue; }
                if (!bnds || bnds.length < 4) continue;
                // 페이지 안에 포함되는지 확인 (bounds: [y1, x1, y2, x2])
                var inAnyPage = false;
                var cy = (bnds[0] + bnds[2]) / 2;
                var cx = (bnds[1] + bnds[3]) / 2;
                for (var pi2 = 0; pi2 < pageBounds.length; pi2++) {
                    var pb = pageBounds[pi2];
                    if (cy >= pb[0] && cy <= pb[2] && cx >= pb[1] && cx <= pb[3]) {
                        inAnyPage = true;
                        break;
                    }
                }
                if (inAnyPage) continue;

                // 페이지 밖 개체 (Rectangle, Group, TextFrame, Polygon, Oval, Image 모두)
                if (iw > 0) out.write(', ');
                out.write('{"type": ' + jsonEscape(ctor));
                out.write(', "bounds": [' + bnds.join(",") + ']');
                try { out.write(', "label": ' + jsonEscape(it.label)); } catch(e) {}

                // 채우기/스트로크 색 (박스인지 판별)
                try {
                    if (it.fillColor && it.fillColor.name) {
                        out.write(', "fill": ' + jsonEscape(it.fillColor.name));
                    }
                } catch(e) {}
                try {
                    if (it.strokeColor && it.strokeColor.name) {
                        out.write(', "stroke": ' + jsonEscape(it.strokeColor.name));
                    }
                } catch(e) {}
                try { out.write(', "stroke_weight": ' + it.strokeWeight); } catch(e) {}

                if (ctor === "TextFrame") {
                    var preview = "";
                    try { preview = it.contents.substring(0, 200); } catch(e) {}
                    out.write(', "text_preview": ' + jsonEscape(preview));
                    out.write(', "is_empty": ' + (preview ? "false" : "true"));
                    // 단락 스타일 첫 5개
                    try {
                        var paras = it.paragraphs;
                        out.write(', "paragraph_styles": [');
                        var pw = 0;
                        for (var p2 = 0; p2 < Math.min(paras.length, 10); p2++) {
                            if (pw > 0) out.write(', ');
                            try {
                                out.write(jsonEscape(getPStyleFullName(paras[p2].appliedParagraphStyle)));
                            } catch(e) { out.write('""'); }
                            pw++;
                        }
                        out.write(']');
                    } catch(e) {}
                } else if (ctor === "Group") {
                    try {
                        out.write(', "items_count": ' + it.pageItems.length);
                        // 그룹 내부 아이템 타입
                        out.write(', "items": [');
                        for (var gi = 0; gi < Math.min(it.pageItems.length, 10); gi++) {
                            if (gi > 0) out.write(', ');
                            var gitem = it.pageItems[gi];
                            var gtype = "";
                            try { gtype = gitem.constructor.name; } catch(e) {}
                            var gtxt = "";
                            if (gtype === "TextFrame") {
                                try { gtxt = gitem.contents.substring(0, 80); } catch(e) {}
                            }
                            out.write('{"type": ' + jsonEscape(gtype) + ', "preview": ' + jsonEscape(gtxt) + '}');
                        }
                        out.write(']');
                    } catch(e) {}
                }
                out.write('}');
                iw++;
            }
            out.write(']');
            out.write('}');
            sw++;
        }
        out.write('\n  ]\n}\n');
        out.close();
        try { doc.close(SaveOptions.NO); } catch(e) {}
        return "OK pasteboard items processed";
    }

    var lf = new File(TARGET_LIST);
    if (!lf.exists) return;
    lf.encoding = "UTF-8";
    lf.open("r");
    var raw = lf.read();
    lf.close();
    var lines = raw.split("\n");
    var logFile = new File("/tmp/extract_pasteboard_log.txt");
    logFile.encoding = "UTF-8";
    logFile.open("w");
    for (var li = 0; li < lines.length; li++) {
        var line = lines[li];
        if (!line || !line.length) continue;
        var parts = line.split("\t");
        if (parts.length < 2) continue;
        try {
            var t0 = (new Date()).getTime();
            var res = processOne(parts[0], parts[1]);
            var t1 = (new Date()).getTime();
            logFile.writeln("[" + (li+1) + "] " + decodeURI((new File(parts[0])).name) + " → " + res + " (" + (t1-t0) + "ms)");
        } catch(e) {
            logFile.writeln("[" + (li+1) + "] ERR: " + (e.message || e));
        }
    }
    logFile.close();
})();
