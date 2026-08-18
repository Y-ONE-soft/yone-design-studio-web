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

// InDesign에서 인덱스로 얻은 개체(doc.pages[3] 등)는 '지정자'라서,
// 앞쪽 페이지가 삭제되면 같은 참조가 다른 페이지를 가리킨다.
// 스캔 시점에 ID 기반 참조로 바꿔 고정한다.
function byIdPage(doc, page) {
    try { return doc.pages.itemByID(page.id); } catch (e) { return page; }
}
function byIdFrame(doc, frame) {
    try {
        var f = doc.textFrames.itemByID(frame.id);
        return (f && f.isValid) ? f : frame;
    } catch (e) { return frame; }
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
        cur.pages.push(byIdPage(doc, doc.pages[p]));
        for (var i = 0; i < info.frames.length; i++) {
            cur.frames.push(byIdFrame(doc, info.frames[i]));
        }
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

function blockRange(block) {
    var names = [];
    for (var i = 0; i < block.pages.length; i++) {
        try { if (block.pages[i].isValid) { names.push(block.pages[i].name); } else { names.push("삭제됨"); } }
        catch (e) { names.push("?"); }
    }
    if (names.length <= 4) { return names.join(","); }
    return names[0] + "~" + names[names.length - 1] + "(" + names.length + "쪽)";
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
// 기준 페이지가 속한 '스프레드'를 복제해 바로 뒤에 넣는다.
// 한 장씩 넣으면 홀수 장이 추가된 순간 이후 페이지의 좌/우가 뒤집혀
// 좌우 전용 마스터(헤더 있는 쪽/없는 쪽)가 어긋난다.
function appendPageLike(refPage, cat) {
    var sp, ns;
    try { sp = refPage.parent; } catch (e0) { return []; }
    try { ns = sp.duplicate(LocationOptions.AFTER, sp); }
    catch (e) { wlog("[경고] 스프레드 복제 실패: " + e); return []; }
    var out = [];
    for (var q = 0; q < ns.pages.length; q++) {
        var info = pageInfo(ns.pages[q]);
        if (info.cat !== cat) { continue; }
        for (var i = 0; i < info.frames.length; i++) {
            var fr = info.frames[i];
            try { fr.previousTextFrame = null; } catch (e2) {}
            try { fr.nextTextFrame = null; } catch (e3) {}
            try { fr.contents = ""; } catch (e4) {}
            out.push(fr);
        }
    }
    return out;
}

// 내용이 하나도 안 들어간 스프레드 삭제 (한쪽만 비는 일이 없도록 스프레드 단위)
// keepPage(블록 첫 페이지 — 부제목 슬롯이 있는 페이지)는 항상 남긴다.
function trimBlankSpreads(pages, cat, keepPage) {
    var groups = {}, order = [], seenPg = {};
    for (var i = 0; i < pages.length; i++) {
        var pg = pages[i];
        if (!pg || !pg.isValid) { continue; }
        var pid = String(pg.id);
        if (seenPg[pid]) { continue; }   // 프레임 수만큼 중복 push된 페이지 제거
        seenPg[pid] = true;
        var sp = pg.parent, sid = String(sp.id);
        if (!groups[sid]) { groups[sid] = { spread: sp, pages: [] }; order.push(sid); }
        groups[sid].pages.push(pg);
    }
    var removed = 0;
    for (var o = 0; o < order.length; o++) {
        var ent = groups[order[o]];
        if (ent.pages.length !== ent.spread.pages.length) { continue; }
        var blank = true, hasFrame = false;
        for (var p = 0; p < ent.pages.length && blank; p++) {
            if (ent.pages[p] === keepPage) { blank = false; break; }
            var info = pageInfo(ent.pages[p]);
            if (info.cat !== cat) { blank = false; break; }
            hasFrame = true;
            for (var f = 0; f < info.frames.length; f++) {
                var c = "";
                try { c = String(info.frames[f].contents); } catch (e) {}
                if (c.replace(/\s/g, "").length > 0) { blank = false; break; }
            }
        }
        if (blank && hasFrame) {
            var nm = [];
            for (var q = 0; q < ent.spread.pages.length; q++) {
                try { nm.push(ent.spread.pages[q].name); } catch (e3) { nm.push("?"); }
            }
            try { ent.spread.remove(); removed++; wlog("   삭제: 스프레드[" + nm.join(",") + "]"); }
            catch (e2) { wlog("[경고] 빈 스프레드 삭제 실패: " + e2); }
        }
    }
    return removed;
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

// ── 시간 예산 워치독 ────────────────────────────────────────────────────────
// 어떤 이유로든 한 구간이 길어지면 스스로 중단하고 문서를 닫는다.
// (InDesign이 붙잡힌 채 사용자가 Esc를 눌러야 하는 상황을 만들지 않기 위함)
var T0 = new Date().getTime();
var BUDGET_MS = 15 * 60 * 1000;   // 전체 상한
var STEP_MS = 120 * 1000;        // 한 구간이 진전 없이 지속되는 상한
var tStep = T0;
function stepStart() { tStep = new Date().getTime(); }
function checkBudget(where) {
    var now = new Date().getTime();
    if (now - T0 > BUDGET_MS) {
        throw new Error("시간 예산 초과(전체 " + Math.round((now - T0) / 1000) + "초) — " + where);
    }
    if (now - tStep > STEP_MS) {
        throw new Error("구간 지연(" + Math.round((now - tStep) / 1000) + "초) — " + where);
    }
}

var doc = null;
try {
    wlog("블랙북 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);
    try { doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e) {}
    try { app.scriptPreferences.enableRedraw = false; } catch (e) {}
    // 스마트 텍스트 리플로우가 켜져 있으면 배치 중 InDesign이 제멋대로
    // 페이지를 붙였다 떼며 매번 재조판한다 (블록 경계도 무너짐)
    try { doc.textPreferences.smartTextReflow = false; } catch (e) {}

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
        // 유닛마다 프레임 하나를 쓰므로(프레임브레이크) 텍스트를 넣기 전에
        // 필요한 만큼 페이지를 미리 확보한다. 배치 뒤에 한 장씩 늘리면
        // 그때마다 스토리 전체가 재조판돼 급격히 느려진다.
        // 유닛 수와 프레임 수가 빠듯하면(오버셋 상태) 프레임브레이크를 걸 때마다
        // 스토리 전체가 재조판되며 급격히 느려진다. 넉넉히 확보한 뒤,
        // 배치가 끝나면 안 쓴 스프레드를 지운다.
        var frames = block.frames.slice();
        wlog(label + ": 블록 페이지 " + blockRange(block) + " / 프레임 " + frames.length);
        var want = Math.ceil(units.length * 1.7) + 2;
        var pre = 0;
        while (frames.length < want && pre < 80) {
            var pgAdd = appendPageLike(frames[frames.length - 1].parentPage, block.cat);
            if (!pgAdd.length) { break; }
            for (var pa = 0; pa < pgAdd.length; pa++) {
                checkBudget(label + " 페이지 선확보");
                stepStart();   // 페이지가 늘고 있으면 진전으로 인정
                frames.push(pgAdd[pa]);
                block.pages.push(pgAdd[pa].parentPage);
                block.frames.push(pgAdd[pa]);
            }
            pre++;
        }
        if (pre) { wlog(label + ": 스프레드 " + pre + "개 선확보 (프레임 " + frames.length + ")"); }
        var story = chainFrames(frames);
        if (!story) { wlog("[경고] " + label + ": 스토리 없음"); return; }

        var flat = [], starts = [];
        for (var u = 0; u < units.length; u++) {
            starts.push(flat.length);
            for (var k = 0; k < units[u].length; k++) { flat.push(units[u][k]); }
        }
        stepStart();
        wlog(label + ": 배치 시작 (단락 " + flat.length + ")");
        var sp = placeParagraphs(story, flat);
        wlog(label + ": 스타일 적용 완료");
        checkBudget(label + " 스타일 적용");
        stepStart();
        // 프레임브레이크는 스타일 적용 뒤에 (InDesign 2026에서 스타일 대입이
        // startParagraph override를 ANYWHERE로 되돌림)
        for (var s = 1; s < starts.length; s++) {
            if (starts[s] < sp.length) {
                try { sp[starts[s]].startParagraph = StartParagraph.NEXT_FRAME; } catch (e) {}
            }
            if (s % 20 === 0) {
                wlog(label + ": 프레임브레이크 " + s + "/" + (starts.length - 1));
                checkBudget(label + " 프레임브레이크");
                stepStart();
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
            checkBudget(label + " 페이지 추가");
        }
        wlog(label + ": 프레임브레이크 완료" + (guard ? " / 페이지 추가 " + guard : ""));
        var stPages = [];
        var stConts = story.textContainers;
        for (var sc = 0; sc < stConts.length; sc++) {
            try { if (stConts[sc].parentPage) { stPages.push(stConts[sc].parentPage.name); } } catch (e) {}
        }
        wlog(label + ": 스토리 프레임 페이지 " + (stPages.length > 4
             ? stPages[0] + "~" + stPages[stPages.length - 1] + "(" + stPages.length + ")"
             : stPages.join(",")));
        var trimmed = trimBlankSpreads(block.pages, block.cat, block.pages[0]);
        wlog(label + ": 유닛 " + units.length + " / 프레임 " +
             story.textContainers.length + (guard ? " (페이지 추가 " + guard + ")" : "") +
             (trimmed ? " (빈 스프레드 " + trimmed + "개 삭제)" : ""));
    }

    // 해설 — 슬롯 스토리에 흘리고, 넘치면 슬롯 영역 안에 페이지 삽입
    function placeAnswers(slot, paras, label, limitPage) {
        if (!paras.length) { return; }
        var story = slot.story;
        // 해설 프레임이 모자라면 오버셋 상태로 스타일이 적용돼 극단적으로 느려진다.
        // 단락 4개당 프레임 1개로 넉넉히 잡아 미리 확보하고, 끝나면 빈 스프레드 삭제.
        var want = Math.ceil(paras.length / 4) + 4;
        var have = story.textContainers.length;
        var pre = 0;
        while (have < want && pre < 60) {
            var anchorPg = slot.lastPage;
            var addedPre = appendPageLike(anchorPg, "narrow");
            if (!addedPre.length) { break; }
            var tailF = null;
            var contsPre = story.textContainers;
            for (var c0 = 0; c0 < contsPre.length; c0++) {
                var pg0 = contsPre[c0].parentPage;
                if (pg0 && pageIndexOf(pg0) <= pageIndexOf(slot.lastPage)) { tailF = contsPre[c0]; }
            }
            if (!tailF) { tailF = contsPre[contsPre.length - 1]; }
            var afterF = null;
            try { afterF = tailF.nextTextFrame; } catch (e0) {}
            var prevF = tailF;
            for (var a0 = 0; a0 < addedPre.length; a0++) {
                try { prevF.nextTextFrame = addedPre[a0]; prevF = addedPre[a0]; } catch (e1) {}
            }
            if (afterF && afterF.isValid) {
                try { prevF.nextTextFrame = afterF; } catch (e2) {}
            }
            slot.lastPage = addedPre[addedPre.length - 1].parentPage;
            have = story.textContainers.length;
            pre++;
            checkBudget(label + " 해설 페이지 선확보");
            stepStart();
        }
        if (pre) { wlog(label + ": 스프레드 " + pre + "개 선확보 (프레임 " + have + ")"); }
        stepStart();
        wlog(label + ": 배치 시작 (단락 " + paras.length + ")");
        placeParagraphs(story, paras);
        wlog(label + ": 스타일 적용 완료");
        checkBudget(label + " 해설 스타일 적용");
        stepStart();
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
            checkBudget(label + " 해설 페이지 추가");
        }
        applyHeaderMaster(slot.firstPage, label);
        // 정리 범위: 이 슬롯 시작부터 다음 해설 슬롯 직전(또는 해설 구간 끝)까지 —
        // 스토리가 안 닿은 뒤쪽 빈 페이지까지 지워야 빈 장이 남지 않는다
        var regionPages = [];
        var startIdx = pageIndexOf(slot.firstPage);
        var stopIdx = limitPage ? pageIndexOf(limitPage) : doc.pages.length;
        for (var rp = startIdx; rp < stopIdx && rp < doc.pages.length; rp++) {
            var pgR = doc.pages[rp];
            if (pageInfo(pgR).cat !== "narrow") { break; }
            regionPages.push(pgR);
        }
        var trimmedA = trimBlankSpreads(regionPages, "narrow", slot.firstPage);
        wlog(label + ": 단락 " + paras.length + " / 프레임 " +
             story.textContainers.length + (guard ? " (페이지 추가 " + guard + ")" : "") +
             (trimmedA ? " (빈 스프레드 " + trimmedA + "개 삭제)" : ""));
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

    // 러닝 헤더가 읽을 부제목 슬롯을 해당 페이지에 심는다(있으면 재사용).
    function setSubtitle(page, text) {
        if (!subtitleSrc || !page || !page.isValid || !text) { return; }
        var target = null;
        var tfs = page.textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                if (tfs[t] === subtitleSrc) { target = tfs[t]; break; }
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

    // 부제목 헤더가 있는 마스터 찾기.
    // 반드시 '그 페이지가 지금 쓰는 마스터와 같은 계열(기반 마스터가 같은)'
    // 안에서만 고른다 — 계열이 다르면(예: 문제용 A2) 페이지 디자인이 통째로 바뀐다.
    function masterBaseName(ms) {
        try {
            if (ms.appliedMaster && ms.appliedMaster.isValid) { return ms.appliedMaster.name; }
        } catch (e) {}
        return ms ? ms.name : "";
    }

    function masterHasSubtitleOnSide(ms, side) {
        var items;
        try { items = ms.allPageItems; } catch (e) { return false; }
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            try {
                if (it.constructor.name !== "TextFrame") { continue; }
                var ins = it.parentStory.textVariableInstances;
                var hit = false;
                for (var k = 0; k < ins.length; k++) {
                    if (ins[k].associatedTextVariable.name === "부제목") { hit = true; break; }
                }
                if (!hit) { continue; }
                var pp = it.parentPage;
                var sd = (pp && pp.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
                if (sd === side) { return true; }
            } catch (e2) {}
        }
        return false;
    }

    function applyHeaderMaster(page, label) {
        if (!page || !page.isValid) { return; }
        var side, cur;
        try {
            side = (page.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
            cur = page.appliedMaster;
        } catch (e) { return; }
        if (!cur || !cur.isValid) { return; }
        if (masterHasSubtitleOnSide(cur, side)) { return; }   // 이미 헤더 있음
        var base = masterBaseName(cur);
        for (var m = 0; m < doc.masterSpreads.length; m++) {
            var ms = doc.masterSpreads[m];
            if (ms.name === cur.name) { continue; }
            if (masterBaseName(ms) !== base && ms.name !== base) { continue; }
            if (!masterHasSubtitleOnSide(ms, side)) { continue; }
            try {
                page.appliedMaster = ms;
                wlog(label + ": 헤더 마스터 적용(" + ms.name + ", " + page.name + "쪽)");
            } catch (e2) { wlog("[경고] " + label + " 헤더 마스터 적용 실패: " + e2); }
            return;
        }
        wlog("[경고] " + label + ": " + page.name + "쪽에 맞는 헤더 마스터 없음 — 부제목이 안 보일 수 있음");
    }

    // ── 슬롯 복제 (원고 과가 템플릿 세트보다 많을 때) ───────────────────────
    function spreadsOfPages(pages) {
        var out = [], seen = {};
        for (var i = 0; i < pages.length; i++) {
            try {
                if (!pages[i].isValid) { continue; }
                var sp = pages[i].parent, sid = String(sp.id);
                if (!seen[sid]) { seen[sid] = true; out.push(sp); }
            } catch (e) {}
        }
        return out;
    }

    function duplicateSlot(srcSlot) {
        var spreads = spreadsOfPages(srcSlot.vocab.pages.concat(srcSlot.problems.pages));
        if (!spreads.length) { return false; }
        var after = spreads[spreads.length - 1];
        for (var s = 0; s < spreads.length; s++) {
            try { after = spreads[s].duplicate(LocationOptions.AFTER, after); }
            catch (e) { wlog("[경고] 슬롯 복제 실패: " + e); return false; }
        }
        return true;
    }

    function duplicateAnswerSlot(srcSlot) {
        var pages = [];
        var conts = srcSlot.story.textContainers;
        for (var c = 0; c < conts.length; c++) {
            var pg = conts[c].parentPage;
            if (pg && pageIndexOf(pg) <= pageIndexOf(srcSlot.lastPage)) { pages.push(pg); }
        }
        var spreads = spreadsOfPages(pages);
        if (!spreads.length) { return false; }
        var after = spreads[spreads.length - 1];
        var newSpreads = [];
        for (var s2 = 0; s2 < spreads.length; s2++) {
            try {
                after = spreads[s2].duplicate(LocationOptions.AFTER, after);
                newSpreads.push(after);
            } catch (e2) { wlog("[경고] 해설 슬롯 복제 실패: " + e2); return false; }
        }
        // 복제된 해설 프레임을 하나의 새 스토리로 연결 (과별 독립 스토리 유지)
        var frames = [];
        for (var n = 0; n < newSpreads.length; n++) {
            for (var q = 0; q < newSpreads[n].pages.length; q++) {
                var info = pageInfo(newSpreads[n].pages[q]);
                if (info.cat !== "narrow") { continue; }
                for (var f = 0; f < info.frames.length; f++) { frames.push(info.frames[f]); }
            }
        }
        chainFrames(frames);
        return true;
    }

    // ── 과별 배치 ───────────────────────────────────────────────────────────
    // 배치·정리로 페이지가 지워지면 앞서 스캔해 둔 참조가 어긋나므로,
    // 과를 시작할 때마다 문서를 다시 스캔한다.
    var lessons = plan.lessons || [];
    var scan0 = buildBlocks(doc);
    wlog("템플릿 슬롯: 과 " + lessonSlots(scan0).length +
         " / 해설 " + answerSlots(scan0).length + " · 원고 과 " + lessons.length + "개");

    for (var li = 0; li < lessons.length; li++) {
        var les = lessons[li];
        var tag = les.label || ("과" + (li + 1));
        var blocks = buildBlocks(doc);
        var slots = lessonSlots(blocks);
        var aSlots = answerSlots(blocks);

        // 과가 템플릿 슬롯보다 많으면 마지막 세트를 복제해 이어붙인다
        var dupGuard = 0;
        while (slots.length < li + 1 && slots.length > 0 && dupGuard < 20) {
            if (!duplicateSlot(slots[slots.length - 1])) { break; }
            wlog("과 슬롯 복제: " + (slots.length + 1) + "번째 세트 추가");
            blocks = buildBlocks(doc);
            slots = lessonSlots(blocks);
            dupGuard++;
        }
        dupGuard = 0;
        while (aSlots.length < li + 1 && aSlots.length > 0 && dupGuard < 20) {
            if (!duplicateAnswerSlot(aSlots[aSlots.length - 1])) { break; }
            wlog("해설 슬롯 복제: " + (aSlots.length + 1) + "번째 추가");
            blocks = buildBlocks(doc);
            aSlots = answerSlots(blocks);
            dupGuard++;
        }

        if (li < slots.length) {
            var slot = slots[li];
            if (les.subtitle) {
                var subPage = (slot.vocab.pages.length ? slot.vocab.pages[0]
                                                       : slot.problems.pages[0]);
                setSubtitle(subPage, les.subtitle);
            }
            placeUnitsInBlock(slot.vocab, les.vocab || [], tag + " 어휘");
            // 어휘 배치로 페이지가 늘거나 줄었을 수 있어 문제 블록은 다시 잡는다
            var slots2 = lessonSlots(buildBlocks(doc));
            var probBlock = (li < slots2.length) ? slots2[li].problems : slot.problems;
            placeUnitsInBlock(probBlock, les.problems || [], tag + " 문제");
        } else {
            wlog("[경고] " + tag + ": 배치할 과 슬롯 없음 — 미조판");
        }

        if ((les.answers || []).length) {
            var aSlots2 = answerSlots(buildBlocks(doc));
            if (li < aSlots2.length) {
                if (les.subtitle) { setSubtitle(aSlots2[li].firstPage, les.subtitle); }
                var limitPg = (li + 1 < aSlots2.length) ? aSlots2[li + 1].firstPage : null;
                placeAnswers(aSlots2[li], les.answers, tag + " 해설", limitPg);
            } else {
                wlog("[경고] " + tag + ": 해설 슬롯 없음 — 미조판");
            }
        }
    }

    // 남는 슬롯의 견본 텍스트 제거
    var restSlots = lessonSlots(buildBlocks(doc));
    for (var r = lessons.length; r < restSlots.length; r++) {
        var rest = restSlots[r].vocab.frames.concat(restSlots[r].problems.frames);
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
    try { app.scriptPreferences.enableRedraw = true; } catch (e3) {}
    wlog("블랙북 v2 조판 중단");
}
