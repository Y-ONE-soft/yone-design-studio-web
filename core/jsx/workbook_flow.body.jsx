// 워크북 v2 렌더 실행기 — wb-flows 플랜의 스텝별 스토리 배치 (lib.jsxinc concat).
// 스토리 탐색 = v1 mapStepToStory 의미론: marker 텍스트 페이지 → 메인 스토리,
// step3는 마스터 O 페이지들의 메인 스토리. 미지원 스텝은 건드리지 않는다.
// 스타일 자동 생성 금지. 유닛 경계 프레임브레이크(startParagraph NEXT_FRAME).

var TEMPLATE = "__TEMPLATE_PATH__";
var PLAN = "__PLAN_PATH__";
var OUT_INDD = "__OUT_INDD__";
var OUT_PDF = "__OUT_PDF__";

function readJSONFile(path) {
    var f = new File(path);
    f.encoding = "UTF-8";
    f.open("r");
    var s = f.read();
    f.close();
    return eval("(" + s + ")");
}

// 마스터 prefix 페이지들의 메인 스토리 (v1 findMainStoryOnMaster 의미론)
function mainStoryOnMaster(doc, prefix) {
    var votes = {};
    var byId = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var pg = doc.pages[p];
        var mp = null;
        try { mp = pg.appliedMaster; } catch (e) {}
        if (!mp || String(mp.namePrefix) !== prefix) { continue; }
        var tfs = pg.textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                var st = tfs[t].parentStory;
                var sid = String(st.id);
                votes[sid] = (votes[sid] || 0) + 1;
                byId[sid] = st;
            } catch (e) {}
        }
    }
    var best = null;
    var bestN = 0;
    for (var k in votes) {
        if (votes[k] > bestN) { bestN = votes[k]; best = byId[k]; }
    }
    return best;
}

// marker 페이지의 N번째 스토리 (rank — 같은 페이지 하단 스토리용)
function storyByMarker(doc, marker, pageName, rank) {
    var page = findPageByMarker(doc, marker);
    if (!page && pageName) {
        try { page = doc.pages.itemByName(pageName); } catch (e) {}
        if (page && !page.isValid) { page = null; }
    }
    if (!page) { return null; }
    if (!rank || rank <= 1) { return mainStoryOnPage(page); }
    // rank 2+: 프레임 수 순위 N번째 스토리
    var counts = [];
    var seen = {};
    var frames = page.textFrames;
    for (var fi = 0; fi < frames.length; fi++) {
        try {
            var st = frames[fi].parentStory;
            var sid = String(st.id);
            if (seen[sid]) { seen[sid].n++; continue; }
            seen[sid] = { st: st, n: 1 };
            counts.push(seen[sid]);
        } catch (e) {}
    }
    counts.sort(function (a, b) { return b.n - a.n; });
    return counts[rank - 1] ? counts[rank - 1].st : null;
}

var doc = null;
try {
    wlog("워크북 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);

    var styleCache = {};
    var missing = {};
    function styleOf(name) {
        if (styleCache[name]) { return styleCache[name]; }
        if (missing[name]) { return null; }
        var ps = findParagraphStyleByPath(doc, name);
        if (ps) { styleCache[name] = ps; return ps; }
        missing[name] = true;
        wlog("[경고] 스타일 없음(자동 생성 안 함): " + name);
        return null;
    }
    var csUL = doc.characterStyles.itemByName("밑줄");
    var noneCS = doc.characterStyles[0];

    for (var fi2 = 0; fi2 < plan.flows.length; fi2++) {
        var flow = plan.flows[fi2];
        var tgt = flow.target || {};
        var story = null;
        if (tgt.master) {
            story = mainStoryOnMaster(doc, tgt.master);
        } else if (tgt.marker) {
            story = storyByMarker(doc, tgt.marker, tgt.page, tgt.rank);
        }
        if (!story) { wlog("[경고] 스토리 못 찾음: " + flow.step); continue; }

        var flat = [];
        var unitStart = [];
        for (var u = 0; u < flow.units.length; u++) {
            unitStart.push(flat.length);
            for (var q = 0; q < flow.units[u].length; q++) {
                flat.push(flow.units[u][q]);
            }
        }
        var texts = [];
        for (var i2 = 0; i2 < flat.length; i2++) { texts.push(flat[i2].t); }
        story.contents = texts.join("\r");
        try { story.texts[0].appliedCharacterStyle = noneCS; } catch (e) {}
        wlog(flow.step + ": " + flat.length + "단락 배치 (유닛 " + flow.units.length + ")");

        var paras = story.paragraphs;
        var isStart = {};
        for (var us = 0; us < unitStart.length; us++) { isStart[unitStart[us]] = true; }
        for (var pi = 0; pi < flat.length && pi < paras.length; pi++) {
            var ps2 = styleOf(flat[pi].s);
            if (ps2) { paras[pi].appliedParagraphStyle = ps2; }
            if (flow.break_per_unit && pi > 0 && isStart[pi]) {
                try { paras[pi].startParagraph = StartParagraph.NEXT_FRAME; } catch (e) {}
            }
            var runs = flat[pi].runs;
            if (runs && runs.length > 0 && csUL.isValid) {
                var off = 0;
                for (var ri = 0; ri < runs.length; ri++) {
                    var rl = runs[ri].t ? runs[ri].t.length : 0;
                    if (rl > 0 && runs[ri].ul) {
                        var a = off, b = off + rl - 1;
                        if (a < paras[pi].characters.length && b < paras[pi].characters.length) {
                            paras[pi].characters.itemByRange(a, b).appliedCharacterStyle = csUL;
                        }
                    }
                    off += rl;
                }
            }
            if ((pi + 1) % 100 === 0) {
                wlog(flow.step + " 스타일: " + (pi + 1) + "/" + flat.length);
            }
        }

        // 스토리 오버플로우 시 마스터 유지 페이지 추가 (v1 ensureNoOverflow 의미론)
        var conts = story.textContainers;
        var lastF = conts[conts.length - 1];
        var safety = 0;
        while (lastF.overflows && safety < 10) {
            var lp = lastF.parentPage;
            var gb = lastF.geometricBounds;
            var np = doc.pages.add(LocationOptions.AFTER, lp);
            try { np.appliedMaster = lp.appliedMaster; } catch (e) {}
            var ntf = np.textFrames.add();
            ntf.geometricBounds = [gb[0], gb[1], gb[2], gb[3]];
            lastF.nextTextFrame = ntf;
            lastF = ntf;
            safety++;
        }
        if (safety > 0) { wlog(flow.step + ": 오버플로우 페이지 +" + safety); }
    }

    var ovf = 0;
    for (var s3 = 0; s3 < doc.stories.length; s3++) {
        try {
            var tc = doc.stories[s3].textContainers;
            if (tc.length > 0 && tc[tc.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("오버플로우: " + ovf + "개");

    doc.save(File(OUT_INDD));
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    wlog("워크북 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
