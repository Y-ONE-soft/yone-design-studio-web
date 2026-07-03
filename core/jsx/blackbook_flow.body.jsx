// 블랙북 v2 렌더 실행기 — bb-flows 플랜을 영역별 스토리에 배치 (lib.jsxinc concat).
// 배치 의미론 = v1 engines/blackbook/jsx/run.jsx와 동일:
//   프레임 기하로 영역 감지(module/large/narrow) → 영역 스토리에 흘리기
//   + 유닛 경계 프레임브레이크(startParagraph NEXT_FRAME)
//   + 프레임 부족 시 영역 마지막 페이지 복제
// 스타일은 플랜의 전체경로 이름만 사용 — 자동 생성 금지([경고]).

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

// ── 영역 감지 (v1 categorizePage 이식) ───────────────────────────────────────
function frameCat(b) {
    var w = b[3] - b[1], h = b[2] - b[0];
    if (h < 30 || w < 50) { return null; }
    if (w >= 150 && h < 200) { return "module"; }
    if (w >= 150 && h >= 200) { return "large"; }
    if (w < 100 && h >= 200) { return "narrow"; }
    return null;
}

function pageCat(page) {
    var counts = {};
    var tfs = page.textFrames;
    for (var t = 0; t < tfs.length; t++) {
        var b;
        try { b = tfs[t].geometricBounds; } catch (e) { continue; }
        var c = frameCat(b);
        if (c) { counts[c] = (counts[c] || 0) + 1; }
    }
    if (counts.module) { return "module"; }
    if (counts.large) { return "large"; }
    if (counts.narrow) { return "narrow"; }
    return "empty";
}

// ── 플로우 대상 스토리 결정 (v1 의미론) ─────────────────────────────────────
//   part1 본문 스토리 = 첫 large 페이지 이전의 첫 module 프레임의 parentStory
//   part2 본문 스토리 = 첫 large 페이지 이후의 첫 module 프레임의 parentStory
//   어휘 스토리      = 첫 large 프레임의 parentStory
//   정답 스토리 1/2  = narrow 프레임들의 서로 다른 parentStory (등장 순)
function collectFrames(doc) {
    var out = [];
    for (var p = 0; p < doc.pages.length; p++) {
        var tfs = doc.pages[p].textFrames;
        for (var t = 0; t < tfs.length; t++) {
            var b;
            try { b = tfs[t].geometricBounds; } catch (e) { continue; }
            var c = frameCat(b);
            if (c) { out.push({ f: tfs[t], cat: c, pg: p }); }
        }
    }
    return out;
}

// 카테고리별 프레임 목록 (페이지·위치 순). part 분리는 첫 large 페이지 기준.
function framesByFlow(doc) {
    var all = collectFrames(doc);
    var firstLargePg = 999999;
    for (var i = 0; i < all.length; i++) {
        if (all[i].cat === "large" && all[i].pg < firstLargePg) {
            firstLargePg = all[i].pg;
        }
    }
    function sortFrames(arr) {
        arr.sort(function (a, b) {
            if (a.pg !== b.pg) { return a.pg - b.pg; }
            var ba = a.f.geometricBounds, bb = b.f.geometricBounds;
            return (ba[0] - bb[0]) || (ba[1] - bb[1]);
        });
        var out = [];
        for (var k = 0; k < arr.length; k++) { out.push(arr[k].f); }
        return out;
    }
    var m1 = [], m2 = [], lg = [], nr = [];
    for (var j = 0; j < all.length; j++) {
        var fr = all[j];
        if (fr.cat === "module") {
            if (fr.pg < firstLargePg) { m1.push(fr); } else { m2.push(fr); }
        } else if (fr.cat === "large") { lg.push(fr); }
        else { nr.push(fr); }
    }
    // narrow: 서로 다른 parentStory 순서대로 (정답 2단 스토리 2개)
    var narrowStories = [];
    var seen = {};
    var nrSorted = sortFrames(nr.slice());
    for (var n2 = 0; n2 < nrSorted.length; n2++) {
        try {
            var st = nrSorted[n2].parentStory;
            var sid = String(st.id);
            if (!seen[sid]) { seen[sid] = true; narrowStories.push(st); }
        } catch (e) {}
    }
    return { module_p1: sortFrames(m1), module_p2: sortFrames(m2),
             large: sortFrames(lg),
             narrow_1: narrowStories[0] || null,
             narrow_2: narrowStories[1] || null };
}

// 프레임 부족 시: 해당 그룹 마지막 프레임의 페이지를 복제 (독립 프레임 추가)
function ensureFramesPerUnit(doc, frames, needed, cat) {
    var guard = 0;
    while (frames.length < needed && guard < 80) {
        var lastPage = frames[frames.length - 1].parentPage;
        var np = lastPage.duplicate(LocationOptions.AFTER, lastPage);
        var tfs = np.textFrames;
        var added = [];
        for (var t = 0; t < tfs.length; t++) {
            var b;
            try { b = tfs[t].geometricBounds; } catch (e) { continue; }
            if (frameCat(b) === cat) { added.push({ f: tfs[t], top: b[0], left: b[1] }); }
        }
        added.sort(function (a, b2) { return (a.top - b2.top) || (a.left - b2.left); });
        for (var q = 0; q < added.length; q++) { frames.push(added[q].f); }
        guard++;
        if (added.length === 0) { break; }
    }
    wlog("프레임 확보: " + frames.length + "/" + needed);
    return frames;
}

var doc = null;
try {
    wlog("블랙북 v2 조판 시작: " + TEMPLATE);
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

    var flows = framesByFlow(doc);
    var noneCS2 = noneCS;

    function placeUnit(story, unit) {
        var texts = [];
        for (var i3 = 0; i3 < unit.length; i3++) { texts.push(unit[i3].t); }
        story.contents = texts.join("\r");
        try { story.texts[0].appliedCharacterStyle = noneCS2; } catch (e) {}
        var paras = story.paragraphs;
        for (var pi = 0; pi < unit.length && pi < paras.length; pi++) {
            var ps2 = styleOf(unit[pi].s);
            if (ps2) { paras[pi].appliedParagraphStyle = ps2; }
            var runs = unit[pi].runs;
            if (runs && runs.length > 0 && csUL.isValid) {
                var off = 0;
                for (var ri = 0; ri < runs.length; ri++) {
                    var rl = runs[ri].t ? runs[ri].t.length : 0;
                    if (rl > 0 && runs[ri].ul) {
                        var a2 = off, b3 = off + rl - 1;
                        if (a2 < paras[pi].characters.length && b3 < paras[pi].characters.length) {
                            paras[pi].characters.itemByRange(a2, b3).appliedCharacterStyle = csUL;
                        }
                    }
                    off += rl;
                }
            }
        }
    }

    for (var fi = 0; fi < plan.flows.length; fi++) {
        var flow = plan.flows[fi];

        if (flow.break_per_unit) {
            // 고유 스토리당 1유닛 — 링크된 다중 프레임 스토리(긴 문항용)는
            // 하나로 취급 (프레임 1:1 대입은 링크 스토리를 이중 덮어써 누락 유발)
            var frames = flows[flow.area];
            if (!frames || frames.length === 0) {
                wlog("[경고] 프레임 없음: " + flow.area);
                continue;
            }
            var cat = flow.area.indexOf("large") === 0 ? "large" : "module";

            function distinctStories(frs) {
                var seen2 = {};
                var out2 = [];
                for (var d = 0; d < frs.length; d++) {
                    try {
                        var st2 = frs[d].parentStory;
                        var sid2 = String(st2.id);
                        if (!seen2[sid2]) { seen2[sid2] = true; out2.push(st2); }
                    } catch (e) {}
                }
                return out2;
            }
            var stories = distinctStories(frames);
            var guard2 = 0;
            while (stories.length < flow.units.length && guard2 < 80) {
                frames = ensureFramesPerUnit(doc, frames,
                                             frames.length + 1, cat);
                stories = distinctStories(frames);
                guard2++;
            }
            wlog(flow.area + ": 스토리 " + stories.length + " / 유닛 " + flow.units.length);
            var nPlace = Math.min(stories.length, flow.units.length);
            for (var u = 0; u < nPlace; u++) {
                try { placeUnit(stories[u], flow.units[u]); }
                catch (e) { wlog("[경고] " + flow.area + " 유닛 " + u + " 배치 실패: " + e); }
                if ((u + 1) % 25 === 0) {
                    wlog(flow.area + " 배치: " + (u + 1) + "/" + flow.units.length);
                }
            }
            if (flow.units.length > stories.length) {
                wlog("[경고] " + flow.area + ": 유닛 " + (flow.units.length - stories.length) + "개 스토리 부족");
            }
            // 남는 스토리의 견본 텍스트 제거
            for (var x = flow.units.length; x < stories.length; x++) {
                try { stories[x].contents = ""; } catch (e) {}
            }
        } else {
            // 정답 스토리 흘리기 (narrow — 연결 스토리)
            var story = flows[flow.area];
            if (!story) { wlog("[경고] 대상 스토리 없음: " + flow.area); continue; }
            var flat = flow.units[0] || [];
            placeUnit(story, flat);
            wlog(flow.area + ": " + flat.length + "단락 배치");

            // 오버플로우 시 페이지+프레임 추가 (v1 run.jsx:540~551 parity, 최대 3페이지)
            var safety = 0;
            var conts = story.textContainers;
            var lastF = conts[conts.length - 1];
            while (lastF.overflows && safety < 3) {
                var lp = lastF.parentPage;
                var tb = [];
                for (var c2 = 0; c2 < conts.length; c2++) {
                    if (conts[c2].parentPage === lp) {
                        var bb = conts[c2].geometricBounds;
                        tb.push([bb[0], bb[1], bb[2], bb[3]]);
                    }
                }
                tb.sort(function (a, b4) { return a[1] - b4[1]; });
                var npg = doc.pages.add(LocationOptions.AFTER, lp);
                try { npg.appliedMaster = lp.appliedMaster; } catch (e) {}
                for (var j2 = 0; j2 < (tb.length || 1); j2++) {
                    var ntf = npg.textFrames.add();
                    ntf.geometricBounds = tb[j2] || [10, 10, 270, 90];
                    lastF.nextTextFrame = ntf;
                    lastF = ntf;
                }
                conts = story.textContainers;
                safety++;
                wlog(flow.area + ": 오버플로우 — 페이지 추가 (" + safety + ")");
            }
        }
    }

    // 오버플로우 집계
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
    wlog("블랙북 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
