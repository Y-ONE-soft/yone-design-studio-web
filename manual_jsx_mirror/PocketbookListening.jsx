#target indesign

/*
 * PocketbookListening.jsx
 * [ENGINE TEMPLATE]
 *
 * K마스터 2x2 그리드에 듣기 내용 배치.
 * 오버라이드 -> 4프레임 체이닝 -> 텍스트+프레임브레이크 삽입 -> 단락스타일 적용.
 */

var TEXT_FILE = "PLACEHOLDER_PATH";
var CLEAR_EXISTING = false;
var FLAG_FILE = "/tmp/jsx_listening_done.txt";

(function() {
    function log(msg) {
        var ff = new File(FLAG_FILE);
        ff.open("a"); ff.encoding = "UTF-8";
        ff.writeln(msg);
        ff.close();
    }

    var ff0 = new File(FLAG_FILE);
    ff0.open("w"); ff0.encoding = "UTF-8";
    ff0.writeln("START"); ff0.close();

    try {
        main();
    } catch(e) {
        log("ERROR: " + e.message + " line " + e.line);
    }

    function main() {
        var f = new File(TEXT_FILE);
        if (!f.exists) { log("File not found: " + TEXT_FILE); return; }
        f.open("r"); f.encoding = "UTF-8";
        var raw = f.read(); f.close();
        var lines = raw.split(/\r\n|\r|\n/);

        var doc = app.activeDocument;

        var svH = doc.viewPreferences.horizontalMeasurementUnits;
        var svV = doc.viewPreferences.verticalMeasurementUnits;
        doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
        doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;

        // --- 스타일 찾기/생성 ---
        var psDugi = null, psScr = null;
        var dugiGroup = null;
        try { dugiGroup = doc.paragraphStyleGroups.itemByName("\uB4E3\uAE30_"); dugiGroup.name; } catch(e) { dugiGroup = null; }
        if (!dugiGroup) {
            try { dugiGroup = doc.paragraphStyleGroups.add({name: "\uB4E3\uAE30_"}); } catch(e) {}
        }

        for (var i = 0; i < doc.allParagraphStyles.length; i++) {
            var sn = doc.allParagraphStyles[i].name;
            if (sn === "\uB4E3\uAE30") psDugi = doc.allParagraphStyles[i];
            if (sn === "\uC2A4\uD06C\uB9BD\uD2B8") psScr = doc.allParagraphStyles[i];
        }

        if (!psDugi) {
            var notoFont = null;
            try { notoFont = app.fonts.itemByName("Noto Sans CJK KR\tRegular"); } catch(e) {}
            var props = {name: "\uB4E3\uAE30", pointSize: 7, leading: 10, tracking: -20};
            if (notoFont && notoFont.isValid) props.appliedFont = notoFont;
            if (dugiGroup) {
                psDugi = dugiGroup.paragraphStyles.add(props);
            } else {
                psDugi = doc.paragraphStyles.add(props);
            }
        }
        if (!psScr) {
            var scrProps = {name: "\uC2A4\uD06C\uB9BD\uD2B8", basedOn: psDugi};
            if (dugiGroup) {
                psScr = dugiGroup.paragraphStyles.add(scrProps);
            } else {
                psScr = doc.paragraphStyles.add(scrProps);
            }
        }

        // --- K마스터 찾기 ---
        var kM = null;
        for (var i = 0; i < doc.masterSpreads.length; i++) {
            if (doc.masterSpreads[i].name.indexOf("K-") === 0) { kM = doc.masterSpreads[i]; break; }
        }
        if (!kM) { log("K master not found"); done(); return; }

        // --- 텍스트 파일 파싱 ---
        // 형식: ===SECTION===이름 / ===PASSAGE===이름 / ===SCRIPT=== / ===KOREAN===
        var sections = [];
        var curSec = null, curPsg = null, mode = "";

        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i];
            if (ln.indexOf("===SECTION===") === 0) {
                if (curPsg && curSec) curSec.passages.push(curPsg);
                if (curSec) sections.push(curSec);
                curSec = {name: ln.substring(13), passages: []};
                curPsg = null; mode = "";
                continue;
            }
            if (ln.indexOf("===PASSAGE===") === 0) {
                if (curPsg && curSec) curSec.passages.push(curPsg);
                curPsg = {name: ln.substring(13), script: [], korean: []};
                mode = "";
                continue;
            }
            if (ln === "===SCRIPT===") { mode = "script"; continue; }
            if (ln === "===KOREAN===") { mode = "korean"; continue; }
            if (!curPsg || !curSec) continue;
            if (mode === "script" && ln !== "") curPsg.script.push(ln);
            if (mode === "korean" && ln !== "") curPsg.korean.push(ln);
        }
        if (curPsg && curSec) curSec.passages.push(curPsg);
        if (curSec) sections.push(curSec);

        if (sections.length === 0) { log("No sections"); done(); return; }
        log("Sections: " + sections.length);

        // --- 헬퍼: 페이지에서 콘텐츠 프레임 4개 가져오기 ---
        function getContentFrames(pg) {
            // 텍스트 프레임만 오버라이드 (GraphicLine, Group, Polygon, Rectangle 제외)
            var mi = pg.masterPageItems;
            for (var j = mi.length - 1; j >= 0; j--) {
                try {
                    if (mi[j] instanceof TextFrame) {
                        var mgb = mi[j].geometricBounds;
                        if ((mgb[2] - mgb[0]) > 50 && (mgb[3] - mgb[1]) > 40) {
                            mi[j].override(pg);
                        }
                    }
                } catch(e) {}
            }
            var frames = [];
            for (var i = 0; i < pg.textFrames.length; i++) {
                try {
                    var tf = pg.textFrames[i];
                    if (!tf.isValid) continue;
                    var gb = tf.geometricBounds;
                    if ((gb[2] - gb[0]) > 50 && (gb[3] - gb[1]) > 40) {
                        frames.push(tf);
                    }
                } catch(e) { continue; }
            }
            // 프레임이 4개 안 되면 직접 생성
            if (frames.length < 4) {
                var side = (pg.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
                var positions = side === "L" ?
                    [[15,15,103,72.5],[15,72.5,103,130],[107,15,195,72.5],[107,72.5,195,130]] :
                    [[15,18,103,75.5],[15,75.5,103,133],[107,18,195,75.5],[107,75.5,195,133]];
                while (frames.length < 4) {
                    var ntf = pg.textFrames.add();
                    ntf.geometricBounds = positions[frames.length];
                    frames.push(ntf);
                }
            }
            // 정렬: Y 먼저(20mm 이상 차이), 그다음 X
            frames.sort(function(a, b) {
                var ag = a.geometricBounds, bg = b.geometricBounds;
                if (Math.abs(ag[0] - bg[0]) > 20) return ag[0] - bg[0];
                return ag[1] - bg[1];
            });
            return frames;
        }

        // --- 전체 passages를 하나로 합침 (섹션 구분 없이 연속 배치) ---
        var oldSpreadCount = doc.spreads.length;
        var allPassages = [];
        // 각 passage에 섹션 시작 여부 태깅
        for (var s = 0; s < sections.length; s++) {
            log("Section: " + sections[s].name + " (" + sections[s].passages.length + " passages)");
            for (var p = 0; p < sections[s].passages.length; p++) {
                var psg = sections[s].passages[p];
                if (p === 0) {
                    psg.sectionStart = true;
                    psg.sectionName = sections[s].name;
                }
                allPassages.push(psg);
            }
        }
        log("Total passages: " + allPassages.length);

        var pIdx = 0;
        var sectionPages = []; // {page, name} - 섹션 시작 페이지 기록용

        while (pIdx < allPassages.length) {
            var spr = doc.spreads.add(LocationOptions.AT_END);
            spr.appliedMaster = kM;
            if (spr.pages.length < 2) {
                try { spr.pages.add(LocationOptions.AT_END); } catch(e) {}
                spr.appliedMaster = kM;
            }

            for (var pi = 0; pi < spr.pages.length && pIdx < allPassages.length; pi++) {
                    var pg = spr.pages[pi];

                    // p1이 섹션 시작이면 기록
                    if (allPassages[pIdx].sectionStart) {
                        sectionPages.push({page: pg, name: allPassages[pIdx].sectionName});
                    }
                    var frames = getContentFrames(pg);

                    if (frames.length < 4) {
                        log("  Warning: page " + pg.name + " has only " + frames.length + " content frames");
                        continue;
                    }

                    // 4개 프레임 체이닝
                    frames[0].nextTextFrame = frames[1];
                    frames[1].nextTextFrame = frames[2];
                    frames[2].nextTextFrame = frames[3];

                    // 텍스트 조립: passage1 + FB + passage2 (있으면)
                    var textParts = [];
                    var fbPositions = []; // 프레임브레이크 삽입할 위치 (몇번째 파트 앞에)

                    // Passage 1
                    var p1 = allPassages[pIdx];
                    // 스크립트 (TL)
                    textParts.push(p1.name);
                    if (p1.script.length > 0) {
                        textParts.push("[Script]");
                        for (var li = 0; li < p1.script.length; li++) textParts.push(p1.script[li]);
                    }

                    // FB -> 해석 (TR)
                    fbPositions.push(textParts.length);
                    if (p1.korean.length > 0) {
                        textParts.push("[\uD574\uC11D]");
                        for (var li = 0; li < p1.korean.length; li++) textParts.push(p1.korean[li]);
                    } else {
                        textParts.push(""); // 빈 프레임
                    }

                    pIdx++;

                    // Passage 2 (있으면)
                    if (pIdx < allPassages.length) {
                        var p2 = allPassages[pIdx];

                        // p2가 섹션 시작이면 기록
                        if (p2.sectionStart) {
                            sectionPages.push({page: pg, name: p2.sectionName});
                        }

                        // FB -> 스크립트 (BL)
                        fbPositions.push(textParts.length);
                        textParts.push(p2.name);
                        if (p2.script.length > 0) {
                            textParts.push("[Script]");
                            for (var li = 0; li < p2.script.length; li++) textParts.push(p2.script[li]);
                        }

                        // FB -> 해석 (BR)
                        fbPositions.push(textParts.length);
                        if (p2.korean.length > 0) {
                            textParts.push("[\uD574\uC11D]");
                            for (var li = 0; li < p2.korean.length; li++) textParts.push(p2.korean[li]);
                        } else {
                            textParts.push("");
                        }

                        pIdx++;
                    } else {
                        // passage 1개만 - 나머지 프레임 비우기 위해 FB 추가
                        fbPositions.push(textParts.length);
                        textParts.push("");
                        fbPositions.push(textParts.length);
                        textParts.push("");
                    }

                    // 텍스트 배치
                    frames[0].contents = textParts.join("\r");
                    var story = frames[0].parentStory;

                    // 프레임브레이크 삽입 (뒤에서부터)
                    var paraCount = story.paragraphs.length;
                    for (var fb = fbPositions.length - 1; fb >= 0; fb--) {
                        var paraIdx = fbPositions[fb];
                        if (paraIdx > 0 && paraIdx < paraCount) {
                            try {
                                // paraIdx번째 단락 앞의 \r을 프레임브레이크로 교체
                                var ci = story.paragraphs[paraIdx].characters[0].index;
                                story.characters[ci - 1].contents = SpecialCharacters.FRAME_BREAK;
                            } catch(e) {
                                log("  FB warning at para " + paraIdx + ": " + e.message);
                            }
                        }
                    }

                    // 단락스타일 적용
                    for (var i = 0; i < story.paragraphs.length; i++) {
                        var para = story.paragraphs[i];
                        var t = para.contents.replace(/[\r\n\u0003]/g, "");
                        if (t === "[Script]") {
                            para.applyParagraphStyle(psScr, true);
                        } else {
                            para.applyParagraphStyle(psDugi, true);
                        }
                        para.clearOverrides();
                    }
                }
            }
        log("Done: " + allPassages.length + " passages placed");

        // 섹션 마커 일괄 추가 (배치 완료 후)
        for (var si = 0; si < sectionPages.length; si++) {
            try {
                var sp = sectionPages[si];
                var newSec = doc.sections.add(sp.page);
                newSec.continueNumbering = true;
                newSec.name = sp.name.replace(/\s+/g, "").substring(0, 5);
                newSec.marker = sp.name;
                log("  Section: " + sp.name + " -> page " + sp.page.name);
            } catch(e) {
                log("  Section error: " + e.message);
            }
        }

        // 기존 페이지 삭제
        if (CLEAR_EXISTING) {
            for (var i = oldSpreadCount - 1; i >= 0; i--) {
                try { doc.spreads[i].remove(); } catch(e) {}
            }
        }

        done();
        log("COMPLETE");

        function done() {
            doc.viewPreferences.horizontalMeasurementUnits = svH;
            doc.viewPreferences.verticalMeasurementUnits = svV;
        }
    }
})();
