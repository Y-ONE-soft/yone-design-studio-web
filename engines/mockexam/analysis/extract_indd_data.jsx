// extract_indd_data.jsx
// 동형모의고사 최종 .indd 파일 일괄 분석.
// - 모든 페이지의 텍스트프레임에서 단락별 (텍스트, 적용 단락스타일, 적용 문자스타일) 추출
// - 별도 텍스트프레임/그룹/이미지(label, bounds) 추출
// - 각 .indd → 같은 폴더에 {파일명}_extract.json 저장
//
// 실행: InDesign Scripts 패널에서 실행 또는 osascript 통해 실행

#target indesign

(function() {
    var SOURCE_DIR = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/동형모의고사/최종파일";
    var OUTPUT_DIR = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/조판_자동화/engines/mockexam/analysis/indd_data";

    // ── 유틸 ─────────────────────────────────────────────────────────────────
    function ensureDir(path) {
        var f = new Folder(path);
        if (!f.exists) f.create();
        return f;
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

    function writeJSON(path, obj) {
        var f = new File(path);
        f.encoding = "UTF-8";
        f.open("w");
        f.write(stringify(obj));
        f.close();
    }

    function stringify(obj, depth) {
        depth = depth || 0;
        if (obj === null || obj === undefined) return "null";
        var t = typeof obj;
        if (t === "string") return jsonEscape(obj);
        if (t === "number" || t === "boolean") return String(obj);
        if (obj instanceof Array) {
            if (obj.length === 0) return "[]";
            var arr = [];
            for (var i = 0; i < obj.length; i++) arr.push(stringify(obj[i], depth + 1));
            return "[\n  " + arr.join(",\n  ") + "\n]";
        }
        if (t === "object") {
            var keys = [];
            for (var k in obj) if (obj.hasOwnProperty(k)) keys.push(k);
            if (keys.length === 0) return "{}";
            var arr2 = [];
            for (var ki = 0; ki < keys.length; ki++) {
                var k2 = keys[ki];
                arr2.push(jsonEscape(k2) + ": " + stringify(obj[k2], depth + 1));
            }
            return "{\n  " + arr2.join(",\n  ") + "\n}";
        }
        return "null";
    }

    function safeName(s) {
        try { return String(s); } catch(e) { return ""; }
    }

    // 단락 스타일 그룹 경로 포함한 풀네임 반환
    function getPStyleFullName(ps) {
        if (!ps || !ps.isValid) return "";
        var name = "";
        try { name = ps.name; } catch(e) { return ""; }
        var parent = null;
        try { parent = ps.parent; } catch(e) {}
        var groupPath = "";
        while (parent && parent.constructor && parent.constructor.name === "ParagraphStyleGroup") {
            try { groupPath = parent.name + "/" + groupPath; } catch(e) {}
            try { parent = parent.parent; } catch(e) { parent = null; }
        }
        return groupPath + name;
    }

    function getCStyleName(cs) {
        if (!cs || !cs.isValid) return "";
        try { return cs.name; } catch(e) { return ""; }
    }

    // 페이지가 마스터인지 체크
    function isMasterPage(page) {
        try {
            return page && page.parent && page.parent.constructor.name === "MasterSpread";
        } catch(e) { return false; }
    }

    // 텍스트프레임 → 단락 정보 배열 추출 (가벼운 버전: pstyle만)
    function extractFrameParagraphs(tf) {
        var paragraphs = [];
        try {
            var paras = tf.paragraphs;
            for (var i = 0; i < paras.length; i++) {
                var p = paras[i];
                var text = "";
                try { text = p.contents; } catch(e) {}
                if (typeof text !== "string") continue;
                var psName = "";
                try { psName = getPStyleFullName(p.appliedParagraphStyle); } catch(e) {}
                paragraphs.push({
                    text: text,
                    pstyle: psName
                });
            }
        } catch(e) {
            paragraphs.push({error: String(e.message || e)});
        }
        return paragraphs;
    }

    // 페이지의 모든 아이템 분류
    function extractPageItems(page) {
        var info = {
            page_index: -1,
            page_name: "",
            side: "",
            text_frames: [],
            other_items: []
        };
        try { info.page_index = page.documentOffset; } catch(e) {}
        try { info.page_name = page.name; } catch(e) {}
        try {
            var sideVal = page.side;
            // side 상수 → 문자열
            if (sideVal === PageSideOptions.LEFT_HAND) info.side = "left";
            else if (sideVal === PageSideOptions.RIGHT_HAND) info.side = "right";
            else info.side = String(sideVal);
        } catch(e) { info.side = "?"; }

        var items = [];
        try {
            // page.allPageItems는 그룹 안까지 전부 펼침
            items = page.allPageItems;
        } catch(e) {
            try { items = page.pageItems; } catch(e2) {}
        }

        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var ctor = "";
            try { ctor = it.constructor.name; } catch(e) {}
            var bounds = [];
            try { bounds = it.geometricBounds; } catch(e) {}
            var label = "";
            try { label = it.label || ""; } catch(e) {}

            if (ctor === "TextFrame") {
                var tfInfo = {
                    bounds: bounds,
                    label: label,
                    cols: 1,
                    threaded_prev: false,
                    threaded_next: false,
                    paragraphs: []
                };
                try { tfInfo.cols = it.textFramePreferences.textColumnCount; } catch(e) {}
                try { tfInfo.threaded_prev = !!it.previousTextFrame; } catch(e) {}
                try { tfInfo.threaded_next = !!it.nextTextFrame; } catch(e) {}
                tfInfo.paragraphs = extractFrameParagraphs(it);
                info.text_frames.push(tfInfo);
            } else {
                // 텍스트프레임 외 (Rectangle, Group, Polygon, Oval, Image 등)
                info.other_items.push({
                    type: ctor,
                    bounds: bounds,
                    label: label
                });
            }
        }
        return info;
    }

    // 문서 전체 스타일 인벤토리
    function extractStyleInventory(doc) {
        var ps_list = [];
        try {
            var allPs = doc.allParagraphStyles;
            for (var i = 0; i < allPs.length; i++) {
                var ps = allPs[i];
                var entry = { name: getPStyleFullName(ps) };
                try { entry.font = ps.appliedFont.name; } catch(e) { entry.font = "?"; }
                try { entry.size = ps.pointSize; } catch(e) {}
                try { entry.leading = String(ps.leading); } catch(e) {}
                try { entry.alignment = String(ps.justification); } catch(e) {}
                try { entry.space_before = ps.spaceBefore; } catch(e) {}
                try { entry.space_after = ps.spaceAfter; } catch(e) {}
                ps_list.push(entry);
            }
        } catch(e) {}

        var cs_list = [];
        try {
            var allCs = doc.allCharacterStyles;
            for (var j = 0; j < allCs.length; j++) {
                var cs = allCs[j];
                var c = { name: getCStyleName(cs) };
                try { c.underline = cs.underline === true; } catch(e) {}
                try { c.font = cs.appliedFont.name; } catch(e) {}
                cs_list.push(c);
            }
        } catch(e) {}
        return { paragraph_styles: ps_list, character_styles: cs_list };
    }

    // 단일 .indd 분석
    function analyzeDocument(file) {
        var doc = app.open(file, false);  // 화면 표시 안 함
        var result = {
            file: file.fsName,
            basename: decodeURI(file.name),
            page_count: doc.pages.length,
            inventory: extractStyleInventory(doc),
            pages: []
        };
        try {
            for (var p = 0; p < doc.pages.length; p++) {
                var page = doc.pages[p];
                if (isMasterPage(page)) continue;
                result.pages.push(extractPageItems(page));
            }
        } catch(e) {
            result.error = String(e.message || e);
        }
        try { doc.close(SaveOptions.NO); } catch(e) {}
        return result;
    }

    function logLine(logFile, msg) {
        logFile.open("a");
        var now = new Date();
        var ts = "[" + ("0" + now.getHours()).slice(-2) + ":" +
                 ("0" + now.getMinutes()).slice(-2) + ":" +
                 ("0" + now.getSeconds()).slice(-2) + "] ";
        logFile.writeln(ts + msg);
        logFile.close();
    }

    // ── 메인 ─────────────────────────────────────────────────────────────────
    try {
        ensureDir(OUTPUT_DIR);
        var srcFolder = new Folder(SOURCE_DIR);
        if (!srcFolder.exists) return;
        var files = srcFolder.getFiles("*.indd");
        if (!files || files.length === 0) return;

        var logFile = new File(OUTPUT_DIR + "/_progress.log");
        logFile.encoding = "UTF-8";

        // FILTER 환경변수: 특정 파일명만 처리 (콤마 구분)
        var filterEnv = "";
        try { filterEnv = $.getenv("EXTRACT_FILTER") || ""; } catch(e) {}
        var filterList = null;
        if (filterEnv) {
            filterList = {};
            var arr = filterEnv.split(",");
            for (var fi2 = 0; fi2 < arr.length; fi2++) {
                filterList[arr[fi2]] = true;
            }
        }

        // 시작 마커 (덮어쓰기)
        logFile.open("w");
        logFile.writeln("[start] 동형 최종파일 분석 - 총 " + files.length + "개" +
            (filterList ? " (필터: " + filterEnv + ")" : ""));
        logFile.close();

        var processedCount = 0;
        var skippedCount = 0;
        for (var fi = 0; fi < files.length; fi++) {
            var f = files[fi];
            var fname = decodeURI(f.name);

            if (filterList && !filterList[fname]) {
                skippedCount++;
                continue;
            }

            // 이미 분석된 JSON 건너뛰기 (FORCE=1 환경변수로 강제 재분석)
            var outName = fname.replace(/\.indd$/i, ".json");
            var outPath = OUTPUT_DIR + "/" + outName;
            var force = false;
            try { force = ($.getenv("EXTRACT_FORCE") === "1"); } catch(e) {}
            if (!force) {
                var existFile = new File(outPath);
                if (existFile.exists) {
                    logLine(logFile, "[" + (fi + 1) + "/" + files.length + "] 스킵 (이미 분석됨): " + fname);
                    skippedCount++;
                    continue;
                }
            }

            try {
                logLine(logFile, "[" + (fi + 1) + "/" + files.length + "] 시작: " + fname);
                var result = analyzeDocument(f);
                writeJSON(outPath, result);
                processedCount++;
                logLine(logFile, "[" + (fi + 1) + "] 완료: " +
                    result.page_count + "페이지, " +
                    result.inventory.paragraph_styles.length + "개 pStyle");
            } catch(e) {
                logLine(logFile, "[" + (fi + 1) + "] 오류: " + (e.message || e));
            }
        }
        logLine(logFile, "[end] 처리=" + processedCount + ", 스킵=" + skippedCount);
    } catch(e) {
        try {
            var errFile = new File(OUTPUT_DIR + "/_error.log");
            errFile.open("a");
            errFile.writeln("[전체 오류] " + (e.message || e));
            errFile.close();
        } catch(e2) {}
    }
})();
