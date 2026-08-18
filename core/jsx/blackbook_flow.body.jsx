// 블랙북 v2 렌더 실행기 — 과(강) 단위 플랜을 템플릿 블록에 배치.
//
// 템플릿 구조 (배재1 블랙북 Part 내지):
//   [어휘 블록(large) → 문제 블록(module)] × N  +  [해설 블록(narrow) × N]
// 한 과 = 어휘 블록 + 문제 블록 한 쌍(= 슬롯). 과가 슬롯보다 많으면 마지막
// 슬롯의 스프레드를 복제해 이어붙인다.
//
// 배치 의미론:
//   어휘/문제 — 블록 프레임을 하나의 스토리로 연결 + 유닛 경계 프레임브레이크
//   해설      — 과별 스토리에 흘리기 (오버플로우 시 블록 안에서 페이지 추가)
//   부제목    — 러닝 헤더(문자 스타일 '부제목') 변수용 슬롯 프레임을 과가
//               바뀌는 지점(어휘 블록 첫 페이지 / 해설 블록 첫 페이지)에 심는다.
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

function sortByPosition(arr) {
    arr.sort(function (a, b) {
        var ba = a.geometricBounds, bb = b.geometricBounds;
        return (ba[0] - bb[0]) || (ba[1] - bb[1]);
    });
    return arr;
}

// 페이지별 대표 영역 + 해당 프레임 목록
function pageInfo(page) {
    var tfs = page.textFrames;
    var byCat = { module: [], large: [], narrow: [] };
    for (var t = 0; t < tfs.length; t++) {
        var b;
        try { b = tfs[t].geometricBounds; } catch (e) { continue; }
        var c = frameCat(b);
        if (c) { byCat[c].push(tfs[t]); }
    }
    var cat = null;
    if (byCat.module.length) { cat = "module"; }
    else if (byCat.large.length) { cat = "large"; }
    else if (byCat.narrow.length) { cat = "narrow"; }
    return { cat: cat, frames: cat ? sortByPosition(byCat[cat]) : [] };
}

// 연속 같은 영역 페이지 = 한 블록
function buildBlocks(doc) {
    var blocks = [], cur = null;
    for (var p = 0; p < doc.pages.length; p++) {
        var info = pageInfo(doc.pages[p]);
        if (!info.cat) { cur = null; continue; }
        if (!cur || cur.cat !== info.cat) {
            cur = { cat: info.cat, pages: [], frames: [] };
            blocks.push(cur);
        }
        cur.pages.push(doc.pages[p]);
        for (var i = 0; i < info.frames.length; i++) { cur.frames.push(info.frames[i]); }
    }
    return blocks;
}

// 과 슬롯 = [어휘 블록 + 바로 뒤 문제 블록] 쌍
// (해설 앞 간지 large 페이지는 뒤가 narrow라서 슬롯이 되지 않는다)
function lessonSlots(blocks) {
    var slots = [];
    for (var i = 0; i < blocks.length - 1; i++) {
        if (blocks[i].cat === "large" && blocks[i + 1].cat === "module") {
            slots.push({ vocab: blocks[i], problems: blocks[i + 1] });
            i++;
        }
    }
    return slots;
}

// 해설 슬롯 = narrow 블록 안의 서로 다른 스토리 (등장 순)
// 한 스토리가 뒤쪽 페이지까지 감겨 있어도 슬롯 영역은 '다음 슬롯 시작 전'까지로 본다.
function answerSlots(blocks) {
    var slots = [], seen = {}, pages = [];
    for (var i = 0; i < blocks.length; i++) {
        if (blocks[i].cat !== "narrow") { continue; }
        for (var p = 0; p < blocks[i].pages.length; p++) { pages.push(blocks[i].pages[p]); }
        var frames = blocks[i].frames;
        for (var f = 0; f < frames.length; f++) {
            var st, sid;
            try { st = frames[f].parentStory; sid = String(st.id); } catch (e) { continue; }
            if (seen[sid]) { continue; }
            seen[sid] = true;
            slots.push({ story: st, firstPage: frames[f].parentPage,
                         lastPage: frames[f].parentPage });
        }
    }
    for (var s = 0; s < slots.length; s++) {
        var limit = (s + 1 < slots.length) ? pageIndexOf(slots[s + 1].firstPage) : 999999;
        var lastPg = slots[s].firstPage;
        for (var pi = 0; pi < pages.length; pi++) {
            var pg = pages[pi], idx = pageIndexOf(pg);
            if (idx < pageIndexOf(slots[s].firstPage) || idx >= limit) { continue; }
            if (frameStoryOnPage(pg, slots[s].story)) { lastPg = pg; }
        }
        slots[s].lastPage = lastPg;
    }
    return slots;
}

function pageIndexOf(page) {
    try { return page.documentOffset; } catch (e) { return -1; }
}

function frameStoryOnPage(page, story) {
    var tfs = page.textFrames;
    for (var t = 0; t < tfs.length; t++) {
        try { if (tfs[t].parentStory === story) { return true; } } catch (e) {}
    }
    return false;
}

// ── 페이지 추가 (블록 안에서만) ─────────────────────────────────────────────
// 기준 페이지를 복제해 바로 뒤에 넣고, 지정 영역 프레임들을 비워서 돌려준다.
function appendPageLike(refPage, cat) {
    var np;
    try { np = refPage.duplicate(LocationOptions.AFTER, refPage); }
    catch (e) { wlog("[경고] 페이지 복제 실패: " + e); return []; }
    var info = pageInfo(np);
    var out = [];
    for (var i = 0; i < info.frames.length; i++) {
        if (info.cat !== cat) { break; }
        var fr = info.frames[i];
        try { fr.previousTextFrame = null; } catch (e2) {}
        try { fr.nextTextFrame = null; } catch (e3) {}
        try { fr.contents = ""; } catch (e4) {}
        out.push(fr);
    }
    return out;
}

// ── 스토리 연결/배치 ────────────────────────────────────────────────────────
function chainFrames(frames) {
    for (var i = 0; i < frames.length; i++) {
        try { frames[i].previousTextFrame = null; } catch (e) {}
        try { frames[i].nextTextFrame = null; } catch (e2) {}
        try { frames[i].contents = ""; } catch (e3) {}
    }
    for (var j = 0; j < frames.length - 1; j++) {
        try { frames[j].nextTextFrame = frames[j + 1]; } catch (e4) {
            wlog("[경고] 프레임 연결 실패: " + e4);
        }
    }
    return frames.length ? frames[0].parentStory : null;
}

var doc = null;
try {
    wlog("블랙북 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);
    try { doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e) {}

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

    // 단락 배열을 스토리에 넣고 스타일 적용 (유닛 경계는 호출자가 처리)
    function placeParagraphs(story, paras) {
        var texts = [];
        for (var i = 0; i < paras.length; i++) { texts.push(paras[i].t); }
        story.contents = texts.join("\r");
        try { story.texts[0].appliedCharacterStyle = noneCS; } catch (e) {}
        var sp = story.paragraphs;
        for (var pi = 0; pi < paras.length && pi < sp.length; pi++) {
            var ps2 = styleOf(paras[pi].s);
            if (ps2) { sp[pi].appliedParagraphStyle = ps2; }
            var runs = paras[pi].runs;
            if (runs && runs.length > 0 && csUL.isValid) {
                var off = 0;
                for (var ri = 0; ri < runs.length; ri++) {
                    var rl = runs[ri].t ? runs[ri].t.length : 0;
                    if (rl > 0 && runs[ri].ul) {
                        var a2 = off, b3 = off + rl - 1;
                        if (a2 < sp[pi].characters.length && b3 < sp[pi].characters.length) {
                            sp[pi].characters.itemByRange(a2, b3).appliedCharacterStyle = csUL;
                        }
                    }
                    off += rl;
                }
            }
        }
        return sp;
    }

    // 블록에 유닛 배치 — 연결 스토리 + 유닛마다 프레임브레이크
    function placeUnitsInBlock(block, units, label) {
        if (!units.length) { return; }
        if (!block || !block.frames.length) {
            wlog("[경고] " + label + ": 배치할 프레임 없음");
            return;
        }
        var frames = block.frames.slice();
        var story = chainFrames(frames);
        if (!story) { wlog("[경고] " + label + ": 스토리 없음"); return; }

        var flat = [], starts = [];
        for (var u = 0; u < units.length; u++) {
            starts.push(flat.length);
            for (var k = 0; k < units[u].length; k++) { flat.push(units[u][k]); }
        }
        var sp = placeParagraphs(story, flat);
        // 프레임브레이크는 스타일 적용 뒤에 (InDesign 2026에서 스타일 대입이
        // startParagraph override를 ANYWHERE로 되돌림)
        for (var s = 1; s < starts.length; s++) {
            if (starts[s] < sp.length) {
                try { sp[starts[s]].startParagraph = StartParagraph.NEXT_FRAME; } catch (e) {}
            }
        }
        // 프레임 부족 → 블록 마지막 페이지 복제해서 이어붙임
        var guard = 0;
        var lastFrame = story.textContainers[story.textContainers.length - 1];
        while (lastFrame && lastFrame.overflows && guard < 60) {
            var refPage = lastFrame.parentPage;
            var added = appendPageLike(refPage, block.cat);
            if (!added.length) { break; }
            for (var a = 0; a < added.length; a++) {
                try { lastFrame.nextTextFrame = added[a]; lastFrame = added[a]; }
                catch (e5) { wlog("[경고] " + label + " 프레임 연결 실패: " + e5); }
                block.pages.push(added[a].parentPage);
                block.frames.push(added[a]);
            }
            lastFrame = story.textContainers[story.textContainers.length - 1];
            guard++;
        }
        wlog(label + ": 유닛 " + units.length + " / 프레임 " +
             story.textContainers.length + (guard ? " (페이지 추가 " + guard + ")" : ""));
    }

    // 해설 — 슬롯 스토리에 흘리고, 넘치면 슬롯 영역 안에 페이지 삽입
    function placeAnswers(slot, paras, label) {
        if (!paras.length) { return; }
        var story = slot.story;
        placeParagraphs(story, paras);
        var guard = 0;
        function lastFrameInRegion() {
            var conts = story.textContainers, best = null;
            for (var c = 0; c < conts.length; c++) {
                var pg = conts[c].parentPage;
                if (!pg) { continue; }
                if (pageIndexOf(pg) <= pageIndexOf(slot.lastPage)) { best = conts[c]; }
            }
            return best || story.textContainers[story.textContainers.length - 1];
        }
        var tail = story.textContainers[story.textContainers.length - 1];
        while (tail && tail.overflows && guard < 60) {
            var anchor = lastFrameInRegion();
            var after = null;
            try { after = anchor.nextTextFrame; } catch (e) {}
            var added = appendPageLike(anchor.parentPage, "narrow");
            if (!added.length) { break; }
            var prev = anchor;
            for (var a = 0; a < added.length; a++) {
                try { prev.nextTextFrame = added[a]; prev = added[a]; } catch (e2) {}
            }
            if (after && after.isValid) {
                try { prev.nextTextFrame = after; } catch (e3) {}
            }
            slot.lastPage = added[added.length - 1].parentPage;
            tail = story.textContainers[story.textContainers.length - 1];
            guard++;
        }
        wlog(label + ": 단락 " + paras.length + " / 프레임 " +
             story.textContainers.length + (guard ? " (페이지 추가 " + guard + ")" : ""));
    }

    // ── 부제목(러닝 헤더) 슬롯 ──────────────────────────────────────────────
    var subtitleCS = null, subtitleSrc = null;
    try {
        var tvSub = doc.textVariables.itemByName("부제목");
        if (tvSub.isValid) { subtitleCS = tvSub.variableOptions.appliedCharacterStyle; }
    } catch (e) {}
    if (subtitleCS) {
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findChangeTextOptions.includeMasterPages = false;
        app.findTextPreferences.appliedCharacterStyle = subtitleCS;
        var hits = doc.findText();
        for (var h = 0; h < hits.length; h++) {
            try {
                var tf0 = hits[h].parentTextFrames[0];
                if (tf0 && tf0.parentPage) { subtitleSrc = tf0; break; }
            } catch (e2) {}
        }
        app.findTextPreferences = NothingEnum.NOTHING;
    }
    if (!subtitleSrc) { wlog("[경고] 부제목 입력칸을 찾지 못함 — 부제목 미기입"); }

    function setSubtitle(page, text) {
        if (!subtitleSrc || !page || !text) { return; }
        var target = null;
        // 이미 그 페이지에 입력칸이 있으면 재사용
        var tfs = page.textFrames;
        for (var t = 0; t < tfs.length; t++) {
            if (tfs[t] === subtitleSrc) { target = tfs[t]; break; }
            try {
                if (tfs[t].texts.length &&
                    tfs[t].texts[0].appliedCharacterStyle === subtitleCS) {
                    target = tfs[t]; break;
                }
            } catch (e) {}
        }
        if (!target) {
            var gb = subtitleSrc.geometricBounds;
            try {
                target = subtitleSrc.duplicate(page);
                target.geometricBounds = gb;
            } catch (e2) { wlog("[경고] 부제목 슬롯 복제 실패: " + e2); return; }
        }
        try {
            target.contents = text;
            target.texts[0].appliedCharacterStyle = subtitleCS;
        } catch (e3) { wlog("[경고] 부제목 기입 실패: " + e3); }
    }

    // ── 슬롯 준비 ───────────────────────────────────────────────────────────
    var blocks = buildBlocks(doc);
    var slots = lessonSlots(blocks);
    var aSlots = answerSlots(blocks);
    var lessons = plan.lessons || [];
    wlog("템플릿 슬롯: 과 " + slots.length + " / 해설 " + aSlots.length +
         " · 원고 과 " + lessons.length + "개");

    // 과가 슬롯보다 많으면 마지막 슬롯 스프레드를 복제해 이어붙임
    function duplicateSlot(srcSlot) {
        var pages = srcSlot.vocab.pages.concat(srcSlot.problems.pages);
        var spreads = [], seenSp = {};
        for (var p = 0; p < pages.length; p++) {
            var sp = pages[p].parent;
            var sid = String(sp.id);
            if (!seenSp[sid]) { seenSp[sid] = true; spreads.push(sp); }
        }
        var after = spreads[spreads.length - 1];
        var newSpreads = [];
        for (var s = 0; s < spreads.length; s++) {
            try {
                var ns = spreads[s].duplicate(LocationOptions.AFTER, after);
                after = ns;
                newSpreads.push(ns);
            } catch (e) { wlog("[경고] 슬롯 복제 실패: " + e); return null; }
        }
        var vocFrames = [], modFrames = [], vocPages = [], modPages = [];
        for (var n = 0; n < newSpreads.length; n++) {
            for (var q = 0; q < newSpreads[n].pages.length; q++) {
                var pg = newSpreads[n].pages[q];
                var info = pageInfo(pg);
                if (info.cat === "large") {
                    vocPages.push(pg);
                    for (var v = 0; v < info.frames.length; v++) { vocFrames.push(info.frames[v]); }
                } else if (info.cat === "module") {
                    modPages.push(pg);
                    for (var m = 0; m < info.frames.length; m++) { modFrames.push(info.frames[m]); }
                }
            }
        }
        return { vocab: { cat: "large", pages: vocPages, frames: vocFrames },
                 problems: { cat: "module", pages: modPages, frames: modFrames } };
    }

    function duplicateAnswerSlot(srcSlot) {
        var spreads = [], seenSp = {};
        var conts = srcSlot.story.textContainers;
        for (var c = 0; c < conts.length; c++) {
            var pg = conts[c].parentPage;
            if (!pg || pageIndexOf(pg) > pageIndexOf(srcSlot.lastPage)) { continue; }
            var sp = pg.parent, sid = String(sp.id);
            if (!seenSp[sid]) { seenSp[sid] = true; spreads.push(sp); }
        }
        if (!spreads.length) { return null; }
        var after = spreads[spreads.length - 1];
        var frames = [], firstPage = null, lastPage = null;
        for (var s = 0; s < spreads.length; s++) {
            var ns;
            try { ns = spreads[s].duplicate(LocationOptions.AFTER, after); }
            catch (e) { wlog("[경고] 해설 슬롯 복제 실패: " + e); return null; }
            after = ns;
            for (var q = 0; q < ns.pages.length; q++) {
                var info = pageInfo(ns.pages[q]);
                if (info.cat !== "narrow") { continue; }
                if (!firstPage) { firstPage = ns.pages[q]; }
                lastPage = ns.pages[q];
                for (var f = 0; f < info.frames.length; f++) { frames.push(info.frames[f]); }
            }
        }
        var story = chainFrames(frames);
        if (!story) { return null; }
        return { story: story, firstPage: firstPage, lastPage: lastPage };
    }

    while (slots.length < lessons.length && slots.length > 0) {
        var ns2 = duplicateSlot(slots[slots.length - 1]);
        if (!ns2) { break; }
        slots.push(ns2);
        wlog("과 슬롯 복제: " + slots.length + "번째 세트 추가");
    }
    while (aSlots.length < lessons.length && aSlots.length > 0) {
        var na = duplicateAnswerSlot(aSlots[aSlots.length - 1]);
        if (!na) { break; }
        aSlots.push(na);
        wlog("해설 슬롯 복제: " + aSlots.length + "번째 추가");
    }

    // ── 과별 배치 ───────────────────────────────────────────────────────────
    for (var li = 0; li < lessons.length; li++) {
        var les = lessons[li];
        var tag = les.label || ("과" + (li + 1));
        if (li < slots.length) {
            var slot = slots[li];
            if (les.subtitle) {
                var subPage = (slot.vocab.pages.length ? slot.vocab.pages[0]
                                                       : slot.problems.pages[0]);
                setSubtitle(subPage, les.subtitle);
            }
            placeUnitsInBlock(slot.vocab, les.vocab || [], tag + " 어휘");
            placeUnitsInBlock(slot.problems, les.problems || [], tag + " 문제");
        } else {
            wlog("[경고] " + tag + ": 배치할 과 슬롯 없음 — 미조판");
        }
        if ((les.answers || []).length) {
            if (li < aSlots.length) {
                if (les.subtitle) { setSubtitle(aSlots[li].firstPage, les.subtitle); }
                placeAnswers(aSlots[li], les.answers, tag + " 해설");
            } else {
                wlog("[경고] " + tag + ": 해설 슬롯 없음 — 미조판");
            }
        }
    }

    // 남는 슬롯의 견본 텍스트 제거
    for (var r = lessons.length; r < slots.length; r++) {
        var rest = slots[r].vocab.frames.concat(slots[r].problems.frames);
        for (var rf = 0; rf < rest.length; rf++) {
            try { rest[rf].contents = ""; } catch (e) {}
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
