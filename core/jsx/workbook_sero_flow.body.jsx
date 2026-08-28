// 워크북 세로 v2 렌더 실행기 — wb-sero-cycles 플랜의 사이클 단위 배치
// (lib.jsxinc concat). v1 engines/workbook_sero/jsx/run.jsx의 페이지 의미론 이식:
//   - 사이클 수 조정(seroAdjustCycles): 14p 사이클을 문제 수만큼 복제/삭제
//   - 슬롯 기하 해석(seroBodyFrames/seroProcessCycle): 페이지 오프셋별 frame
//   - STEP3 오버플로우: 마지막 페이지 통째 복제 + 메인 frame 연결 (마스터 유지)
//   - STEP3 빈 페이지 → M 마스터
// 단락 배치(스타일/밑줄 runs/유닛 브레이크/아이콘 op)는 workbook_flow.body.jsx와
// 동일 의미론. 스타일 자동 생성 금지 — 없으면 [경고]만.
//
// 플랜: {"format":"wb-sero-cycles-v1","cycles":[{q_num,code,path(사이클 플랜
// 파일 — eval 1MB 제한 회피 분할),...}]}. 사이클 파일: {"q_num","code",
// "slots":[{"slot","step","units"|"clear",("ul_style")}],"qnum_slots":[...]}

var TEMPLATE = "__TEMPLATE_PATH__";
var PLAN = "__PLAN_PATH__";
var OUT_INDD = "__OUT_INDD__";
var OUT_PDF = "__OUT_PDF__";

// ── 사이클 구조 상수 (v1 run.jsx:2766~2773 — 실물 스펙 확인: 간지 3p +
//    정상 사이클 17개×14p(P4~P241) + 합본 사이클 + M 마스터 부속) ───────────
var HEADER_PAGES = 3;
var CYCLE_LENGTH = 14;
var ORIG_NORMAL_CYCLES = 17;
var STEP3_OFFSET = 10;      // 사이클 내 STEP3 시작 오프셋 (P+10 ~ P+13)

function readJSONFile(path) {
    var f = new File(path);
    f.encoding = "UTF-8";
    f.open("r");
    var s = f.read();
    f.close();
    return eval("(" + s + ")");
}

// 문서 내장 [기본 단락] — 플랜 센티널 "$BASIC" 해석용 (workbook_flow와 동일)
function basicParaOf(doc) {
    var s = null;
    try {
        s = doc.paragraphStyles.itemByName("$ID/NormalParagraphStyle");
        if (s && s.isValid) { return s; }
    } catch (e) {}
    try {
        s = doc.paragraphStyles.itemByName("[기본 단락]");
        if (s && s.isValid) { return s; }
    } catch (e) {}
    try {
        s = doc.paragraphStyles.itemByName("[Basic Paragraph]");
        if (s && s.isValid) { return s; }
    } catch (e) {}
    return doc.paragraphStyles[0];
}

// ── 사이클 수 조정 (v1 seroAdjustCycles 이식) ────────────────────────────────
function adjustCycles(doc, targetN) {
    var origPages = doc.pages.length;
    wlog("[조정] 원본 페이지 " + origPages + " / 목표 사이클 " + targetN);

    // 1) 부속(M 마스터) 페이지 인덱스 (뒤에서부터 첫 M)
    var trailStart = origPages;
    for (var p = origPages - 1; p >= HEADER_PAGES; p--) {
        try {
            var mm = doc.pages[p].appliedMaster;
            if (mm && mm.namePrefix === "M") { trailStart = p; break; }
        } catch (e) {}
    }
    for (var p2 = trailStart; p2 < origPages; p2++) {
        try {
            var mm2 = doc.pages[p2].appliedMaster;
            if (mm2 && mm2.namePrefix === "M") { trailStart = p2; break; }
        } catch (e) {}
    }

    // 2) 합본/잉여 사이클 영역 삭제 (정상 17개 사이클 영역만 유지)
    var normalEnd = HEADER_PAGES + ORIG_NORMAL_CYCLES * CYCLE_LENGTH;
    if (normalEnd > trailStart) { normalEnd = trailStart; }
    for (var rp = trailStart - 1; rp >= normalEnd; rp--) {
        try { doc.pages[rp].remove(); } catch (e) {}
    }

    // 3) 목표 사이클 수에 맞춰 삭제/복제
    if (targetN < ORIG_NORMAL_CYCLES) {
        var toRemove = ORIG_NORMAL_CYCLES - targetN;
        for (var rc = 0; rc < toRemove; rc++) {
            var pagesNow = doc.pages.length;
            var tail = pagesNow;
            for (var ts = pagesNow - 1; ts >= HEADER_PAGES; ts--) {
                try {
                    var mt = doc.pages[ts].appliedMaster;
                    if (mt && mt.namePrefix === "M") { tail = ts; break; }
                } catch (e) {}
            }
            var cycStart = tail - CYCLE_LENGTH;
            if (cycStart < HEADER_PAGES) { break; }
            for (var dp = tail - 1; dp >= cycStart; dp--) {
                try { doc.pages[dp].remove(); } catch (e) {}
            }
        }
    } else if (targetN > ORIG_NORMAL_CYCLES) {
        var toAdd = targetN - ORIG_NORMAL_CYCLES;
        for (var ac = 0; ac < toAdd; ac++) {
            var pagesNow2 = doc.pages.length;
            var tail2 = pagesNow2;
            for (var ts2 = pagesNow2 - 1; ts2 >= HEADER_PAGES; ts2--) {
                try {
                    var mt2 = doc.pages[ts2].appliedMaster;
                    if (mt2 && mt2.namePrefix === "M") { tail2 = ts2; break; }
                } catch (e) {}
            }
            var srcStart = tail2 - CYCLE_LENGTH;
            if (srcStart < HEADER_PAGES) { break; }
            var insertBeforePage = doc.pages[tail2];
            for (var sp = srcStart; sp < tail2; sp++) {
                try {
                    doc.pages[sp].duplicate(LocationOptions.BEFORE,
                                            insertBeforePage);
                } catch (e) {}
            }
        }
    }
    wlog("[조정] 완료 — 페이지 " + doc.pages.length);
}

// ── frame 기하 해석 (v1 seroIsLabelFrame/seroBodyFrames 이식) ────────────────
function isLabelFrame(fr) {
    try { return fr.geometricBounds[0] < 10; } catch (e) { return true; }
}

function bodyFrames(page) {
    var arr = [];
    var tfs = page.textFrames;
    for (var i = 0; i < tfs.length; i++) {
        if (isLabelFrame(tfs[i])) { continue; }
        try {
            var gb = tfs[i].geometricBounds;
            arr.push({ fr: tfs[i], y: gb[0], x: gb[1],
                       w: gb[3] - gb[1], h: gb[2] - gb[0] });
        } catch (e) {}
    }
    arr.sort(function (a, b) {
        if (Math.abs(a.y - b.y) > 1) { return a.y - b.y; }
        return a.x - b.x;
    });
    return arr;
}

function biggestFrame(bodies, skipFn) {
    var best = null;
    var bestH = 0;
    for (var i = 0; i < bodies.length; i++) {
        if (skipFn && skipFn(bodies[i])) { continue; }
        if (bodies[i].h > bestH) { bestH = bodies[i].h; best = bodies[i].fr; }
    }
    return best;
}

function smallFrame(bodies, matchFn) {
    for (var i = 0; i < bodies.length; i++) {
        if (matchFn(bodies[i])) { return bodies[i].fr; }
    }
    return null;
}

var _isNumSmall = function (b) { return b.w < 30 && b.h < 60; };     // P+5/P+8
var _isNumSmall7 = function (b) { return b.h < 15 && b.w < 50; };    // P+7

// 슬롯 → frame 해석 (v1 seroProcessCycle의 페이지 오프셋별 규칙)
function resolveSlotFrame(doc, cycleStart, slot) {
    function pg(off) {
        var idx = cycleStart + off;
        return (idx < doc.pages.length) ? doc.pages[idx] : null;
    }
    var page = null;
    var bodies = null;
    if (slot === "p0_top" || slot === "p0_bot") {
        page = pg(0);
        if (!page) { return null; }
        bodies = bodyFrames(page);
        if (slot === "p0_top") {
            return bodies.length >= 1 ? bodies[0].fr : null;
        }
        return bodies.length >= 2 ? bodies[bodies.length - 1].fr : null;
    }
    if (slot === "p6_sel" || slot === "p6_btm") {
        page = pg(6);
        if (!page) { return null; }
        bodies = bodyFrames(page);
        var bigs = [];
        for (var i = 0; i < bodies.length; i++) {
            if (bodies[i].h >= 50) { bigs.push(bodies[i]); }
        }
        bigs.sort(function (a, b) { return a.y - b.y; });
        if (slot === "p6_sel") { return bigs.length >= 1 ? bigs[0].fr : null; }
        return bigs.length >= 2 ? bigs[1].fr : null;
    }
    var m = slot.match(/^p(\d)_(main|num)$/);
    if (!m) { return null; }
    var off = parseInt(m[1], 10);
    page = pg(off);
    if (!page) { return null; }
    bodies = bodyFrames(page);
    var numFn = (off === 7) ? _isNumSmall7
              : (off === 5 || off === 8) ? _isNumSmall : null;
    if (m[2] === "num") {
        return numFn ? smallFrame(bodies, numFn) : null;
    }
    return biggestFrame(bodies, numFn);
}

// STEP3 통합 스토리 — O 마스터 4페이지에서 프레임 수 최다 스토리 (v1 이식)
function findStep3Story(doc, cycleStart) {
    var seen = {};
    var best = null;
    var bestFrames = 0;
    for (var off = STEP3_OFFSET; off < STEP3_OFFSET + 4; off++) {
        var idx = cycleStart + off;
        if (idx >= doc.pages.length) { break; }
        var tfs = doc.pages[idx].textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                var st = tfs[t].parentStory;
                var sid = String(st.id);
                if (seen[sid]) { continue; }
                seen[sid] = true;
                var n = st.textContainers.length;
                if (n > bestFrames) { bestFrames = n; best = st; }
            } catch (e) {}
        }
    }
    return best;
}

// ── 아이콘 op (workbook_flow.body.jsx와 동일 의미론) ─────────────────────────
var _iconDup = {};
var _iconLink = {};

function _iconSource(doc, label) {
    if (_iconDup[label]) { return _iconDup[label]; }
    var src = findLabeledItem(doc, label);
    if (!src) {
        _iconDup[label] = { missing: true };
        wlog("[경고] 아이콘 원본 없음: " + label);
        return _iconDup[label];
    }
    var state = { itemLocked: false, layerLocked: false };
    try { state.itemLocked = src.locked; src.locked = false; } catch (e) {}
    try {
        if (src.itemLayer) {
            state.layerLocked = src.itemLayer.locked;
            src.itemLayer.locked = false;
            src.itemLayer.visible = true;
        }
    } catch (e) {}
    _iconDup[label] = { src: src, state: state };
    return _iconDup[label];
}

function _iconLinkInfo(doc, label) {
    if (_iconLink[label]) { return _iconLink[label]; }
    var info = { missing: true };
    var gs = doc.allGraphics;
    for (var gi = 0; gi < gs.length; gi++) {
        try {
            var g = gs[gi];
            if (g.parent && g.parent.label === label && g.itemLink) {
                var gb = g.parent.geometricBounds;
                info = { path: g.itemLink.filePath, width: gb[3] - gb[1] };
                break;
            }
        } catch (e) {}
    }
    if (info.missing) { wlog("[경고] 아이콘 링크 없음: " + label); }
    _iconLink[label] = info;
    return info;
}

function relockIcons() {
    for (var k in _iconDup) {
        var e1 = _iconDup[k];
        if (!e1 || !e1.src) { continue; }
        try { e1.src.locked = e1.state.itemLocked; } catch (e) {}
        try {
            if (e1.src.itemLayer) {
                e1.src.itemLayer.locked = e1.state.layerLocked;
            }
        } catch (e) {}
    }
}

function _endIP(para) {
    var c = "";
    try { c = para.contents || ""; } catch (e) {}
    var endsCR = c.length > 0 && c.charAt(c.length - 1) === "\r";
    return endsCR ? para.insertionPoints[-2] : para.insertionPoints[-1];
}

function _ensureEndPad(para, ip, pad) {
    var c = "";
    try { c = (para.contents || "").replace(/\r$/, ""); } catch (e) {}
    if (c.length === 0 || c.charAt(c.length - 1) !== pad.charAt(pad.length - 1)) {
        ip.contents = pad;
        return _endIP(para);
    }
    return ip;
}

function insertIconAt(doc, story, para, ic) {
    var pos = (ic.pos === "start") ? "start" : "end";
    var pad = ic.pad || "";
    if (ic.mode === "place") {
        var info = _iconLinkInfo(doc, ic.label);
        if (info.missing) { return 0; }
        var ip = _endIP(para);
        if (pad) { ip = _ensureEndPad(para, ip, pad); }
        try {
            var placed = story.insertionPoints[ip.index].place(File(info.path))[0];
            try { placed.anchoredObjectSettings.anchorType = AnchorPosition.INLINE_POSITION; } catch (e) {}
            try {
                placed.fit(FitOptions.FRAME_TO_CONTENT);
                var pgb = placed.geometricBounds;
                var pw = pgb[3] - pgb[1];
                if (pw > 0 && info.width) {
                    var sc = (info.width / pw) * 100;
                    placed.absoluteHorizontalScale = sc;
                    placed.absoluteVerticalScale = sc;
                }
            } catch (e) {}
            return 1;
        } catch (e) { return 0; }
    }
    var entry = _iconSource(doc, ic.label);
    if (entry.missing) { return 0; }
    var ip2 = (pos === "start") ? para.insertionPoints[0] : _endIP(para);
    if (pos === "end" && pad) { ip2 = _ensureEndPad(para, ip2, pad); }
    var clone = null;
    try {
        clone = entry.src.duplicate();
        try { clone.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION; } catch (e) {}
        try { clone.textWrapPreferences.textWrapMode = TextWrapModes.NONE; } catch (e) {}
        clone.anchoredObjectSettings.insertAnchoredObject(ip2, AnchorPosition.INLINE_POSITION);
        try { clone.fit(FitOptions.FRAME_TO_CONTENT); } catch (e) {}
    } catch (e) {
        try { if (clone) { clone.remove(); } } catch (e2) {}
        return 0;
    }
    if (pos === "start" && pad) {
        try { para.insertionPoints[1].contents = pad; } catch (e) {}
    }
    return 1;
}

// ── 메인 ─────────────────────────────────────────────────────────────────────
var doc = null;
try {
    wlog("워크북 세로 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    var cycles = plan.cycles || [];
    doc = app.open(File(TEMPLATE), false);
    app.scriptPreferences.enableRedraw = false;

    var styleCache = {};
    var missingStyle = {};
    function styleOf(name) {
        if (styleCache[name]) { return styleCache[name]; }
        if (missingStyle[name]) { return null; }
        if (name === "$BASIC") {
            styleCache[name] = basicParaOf(doc);
            return styleCache[name];
        }
        var ps = findParagraphStyleByPath(doc, name);
        if (ps) { styleCache[name] = ps; return ps; }
        missingStyle[name] = true;
        wlog("[경고] 스타일 없음(자동 생성 안 함): " + name);
        return null;
    }
    // W45 답란(S_답란) 폴백 + 들여쓰기 0 브릿지 — workbook_flow와 동일 의미론
    var fbCount = 0;
    var ind0Count = 0;
    var ind0Sample = "";
    function applyAnslineIndentZero(para) {
        var fli = null, lind = null;
        try { fli = Number(para.firstLineIndent); } catch (e) {}
        try { lind = Number(para.leftIndent); } catch (e) {}
        try { para.firstLineIndent = 0; } catch (e) {}
        try { para.leftIndent = 0; } catch (e) {}
        ind0Count++;
        if (ind0Sample === "") {
            ind0Sample = "원값 " + fli + "/" + lind + " → 0/0";
        }
    }

    var noneCS = doc.characterStyles[0];
    var ulCache = {};
    function ulStyleFor(entry) {
        var names = [];
        if (entry.ul_style) { names.push(entry.ul_style); }
        names.push("문제_밑줄");
        names.push("밑줄");
        for (var ni = 0; ni < names.length; ni++) {
            var nm = names[ni];
            if (ulCache[nm] === undefined) {
                ulCache[nm] = findCharacterStyleByPath(doc, nm);
            }
            if (ulCache[nm]) { return ulCache[nm]; }
        }
        return null;
    }

    // 슬롯 1개 배치 — workbook_flow processFlow의 배치부와 동일 의미론
    function placeSlot(story, entry, tag) {
        var flat = [];
        var unitStart = [];
        var unitPageBreak = [];
        for (var u = 0; u < entry.units.length; u++) {
            var unitObj = entry.units[u];
            var uParas = unitObj.paras || unitObj;
            unitStart.push(flat.length);
            unitPageBreak.push(unitObj.page_break ? true : false);
            for (var q = 0; q < uParas.length; q++) { flat.push(uParas[q]); }
        }
        if (flat.length === 0) { return; }
        var texts = [];
        for (var i2 = 0; i2 < flat.length; i2++) { texts.push(flat[i2].t); }
        var joined = texts.join("\r");
        // 마지막 빈 단락 실체화 (workbook_flow와 동일 — 꼬리 아이콘 정렬)
        if (texts.length > 0 && texts[texts.length - 1] === "") {
            joined += "\r";
        }
        story.contents = joined;
        try { story.texts[0].appliedCharacterStyle = noneCS; } catch (e) {}

        var csUL = ulStyleFor(entry);
        var paras = story.paragraphs.everyItem().getElements();
        var isStart = {};
        for (var us = 0; us < unitStart.length; us++) {
            isStart[unitStart[us]] = unitPageBreak[us] ? "page" : "frame";
        }
        for (var pi = 0; pi < flat.length && pi < paras.length; pi++) {
            var ps2 = styleOf(flat[pi].s);
            var usedFb = false;
            if (!ps2 && flat[pi].s_fb) {          // W45: S_답란 없음 → 선지
                ps2 = styleOf(flat[pi].s_fb);
                usedFb = !!ps2;
            }
            if (ps2) {
                paras[pi].appliedParagraphStyle = ps2;
                if (usedFb) {
                    fbCount++;
                    if (flat[pi].ind0) { applyAnslineIndentZero(paras[pi]); }
                }
            }
            if (pi > 0 && isStart[pi]) {
                try {
                    paras[pi].startParagraph = (isStart[pi] === "page")
                        ? StartParagraph.NEXT_PAGE
                        : StartParagraph.NEXT_FRAME;
                } catch (e) {}
            }
            var runs = flat[pi].runs;
            if (runs && runs.length > 0 && csUL) {
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
            if ((pi + 1) % 50 === 0) {
                wlog(tag + " 스타일: " + (pi + 1) + "/" + flat.length);
            }
        }

        // 아이콘 패스 — 역순 (텍스트 길이 변화로부터 인덱스 보호)
        var iconDone = 0;
        for (var xi = flat.length - 1; xi >= 0; xi--) {
            var ic = flat[xi].icon;
            if (!ic || xi >= paras.length) { continue; }
            insertIconAt(doc, story, paras[xi], ic);
            iconDone++;
            if (iconDone % 50 === 0) { wlog(tag + " 아이콘 진행: " + iconDone); }
        }
    }

    // STEP3 오버플로우 — 마지막 페이지 통째 복제 + 메인 frame 연결 (v1 이식:
    // pages.add + 마스터 override는 페이지 헤더가 깨지므로 페이지 복제 사용)
    function fixStep3Overflow(story, tag) {
        try { story.recompose(); } catch (e) {}
        for (var t = 0; t < 20; t++) {
            var conts = story.textContainers;
            var lastTF = conts[conts.length - 1];
            if (!lastTF.overflows) { break; }
            var lastPage = null;
            try { lastPage = lastTF.parentPage; } catch (e) {}
            if (!lastPage) {
                wlog("[경고] " + tag + " 오버플로우 페이지 식별 실패");
                break;
            }
            var newPage = null;
            try {
                newPage = lastPage.duplicate(LocationOptions.AFTER, lastPage);
            } catch (e) {
                wlog("[경고] " + tag + " 페이지 복제 실패: " + e);
                break;
            }
            var newTFs = newPage.textFrames;
            var bestTF = null;
            var bestArea = 0;
            for (var nt = 0; nt < newTFs.length; nt++) {
                try {
                    var gb = newTFs[nt].geometricBounds;
                    var area = (gb[3] - gb[1]) * (gb[2] - gb[0]);
                    if (area > bestArea) { bestArea = area; bestTF = newTFs[nt]; }
                } catch (e) {}
            }
            if (!bestTF) {
                wlog("[경고] " + tag + " 복제 페이지 메인 frame 식별 실패");
                break;
            }
            try { bestTF.parentStory.contents = ""; } catch (e) {}
            try { lastTF.nextTextFrame = bestTF; } catch (e) {}
            try { story.recompose(); } catch (e) {}
            wlog(tag + " 오버플로우 — 페이지 복제 (+" + (t + 1) + ")");
        }
    }

    // STEP3 빈 페이지 → M 마스터 (v1 이식)
    var MASTER_M = null;
    for (var mi = 0; mi < doc.masterSpreads.length; mi++) {
        if (doc.masterSpreads[mi].namePrefix === "M") {
            MASTER_M = doc.masterSpreads[mi];
            break;
        }
    }
    function applyMToEmptyStep3(story) {
        if (!MASTER_M) { return; }
        try { story.recompose(); } catch (e) {}
        var conts = story.textContainers;
        if (conts.length === 0) { return; }
        var firstPg = null, lastPg = null;
        try { firstPg = conts[0].parentPage; } catch (e) {}
        try { lastPg = conts[conts.length - 1].parentPage; } catch (e) {}
        if (!firstPg || !lastPg) { return; }
        for (var off = firstPg.documentOffset; off <= lastPg.documentOffset; off++) {
            try {
                var pg = doc.pages[off];
                var hasContent = false;
                var tfs = pg.textFrames;
                for (var pt = 0; pt < tfs.length; pt++) {
                    if (tfs[pt].parentStory === story) {
                        var c = (tfs[pt].contents || "").replace(/[\s\r\n￼]+/g, "");
                        if (c.length > 0) { hasContent = true; break; }
                    }
                }
                if (!hasContent) {
                    try { pg.appliedMaster = MASTER_M; } catch (e) {}
                }
            } catch (e) {}
        }
    }

    // 사이클 1개 처리 (v1 seroProcessCycle 이식 — 슬롯은 플랜이 결정)
    function processCycle(cyc, cycleStart) {
        var qn = String(cyc.q_num || "?");
        for (var si = 0; si < cyc.slots.length; si++) {
            var entry = cyc.slots[si];
            var tag = "Q" + qn + " " + entry.slot;
            var story = null;
            if (entry.slot === "step3") {
                story = findStep3Story(doc, cycleStart);
            } else {
                var fr = resolveSlotFrame(doc, cycleStart, entry.slot);
                if (fr) { try { story = fr.parentStory; } catch (e) {} }
            }
            if (!story || !story.isValid) {
                wlog("[경고] " + tag + ": 스토리 못 찾음");
                continue;
            }
            if (entry.clear) {
                // v1 seroClearFrame — 원본 잔존 데이터 비움
                try { story.contents = ""; } catch (e) {}
                continue;
            }
            try {
                placeSlot(story, entry, tag);
            } catch (ePl) {
                wlog("[경고] " + tag + " 배치 오류: " + ePl);
            }
            if (entry.slot === "step3") {
                fixStep3Overflow(story, tag);
                applyMToEmptyStep3(story);
            }
        }
        // 페이지번호 frame — q_num 표기 (v1: P+5/P+7/P+8)
        var qslots = cyc.qnum_slots || [];
        for (var qi = 0; qi < qslots.length; qi++) {
            var nfr = resolveSlotFrame(doc, cycleStart, qslots[qi]);
            if (nfr) {
                try { nfr.parentStory.contents = qn; } catch (e) {}
            }
        }
        // 빈 슬롯 페이지 수집 (W18 D9, plan.page_cleanup opt-in) — 플랜
        // 기준: 한 페이지의 모든 슬롯이 clear(원고 없음)이면 삭제 대상.
        // 페이지 ID로 기록 (이후 페이지 복제로 오프셋이 밀려도 안전).
        // 템플릿 장식(섹션 타이틀/데모 예시)은 지오메트리로 구분 불가 —
        // 플랜이 진실 (1차 재조판에서 지오메트리 스캔이 데모 페이지 10개를
        // 남긴 실증).
        if (plan.page_cleanup) {
            var offSlots = {};
            for (var ki = 0; ki < cyc.slots.length; ki++) {
                var ke = cyc.slots[ki];
                var mm = String(ke.slot).match(/^p(\d)_/);
                if (!mm) { continue; }
                var koff = mm[1];
                if (!offSlots[koff]) { offSlots[koff] = []; }
                offSlots[koff].push(ke);
            }
            for (var ko in offSlots) {
                var allClear = true;
                for (var kj = 0; kj < offSlots[ko].length; kj++) {
                    if (!offSlots[ko][kj].clear) { allClear = false; break; }
                }
                if (!allClear) { continue; }
                var kpIdx = cycleStart + parseInt(ko, 10);
                if (kpIdx < doc.pages.length) {
                    try {
                        cleanupPageIds[cleanupPageIds.length] =
                            doc.pages[kpIdx].id;
                    } catch (e) {}
                }
            }
        }
        // pN_main 슬롯 오버플로우 — 페이지 복제 (W18 D8, plan.overflow_dup
        // opt-in). 슬롯 배치가 전부 끝난 뒤 2차 패스: 대상 스토리를 먼저
        // 전부 확보(페이지 복제로 오프셋이 밀려도 스토리 객체는 유효) 후
        // 복제한다. 메인 프레임 단독 페이지(pN_main)에 한정 — p0/p6 공유
        // 페이지는 복제 시 이웃 프레임 내용이 중복 인쇄되므로 제외.
        if (plan.overflow_dup) {
            var pend = [];
            for (var oi = 0; oi < cyc.slots.length; oi++) {
                var oe = cyc.slots[oi];
                if (oe.clear || oe.slot === "step3") { continue; }
                if (!/_main$/.test(String(oe.slot))) { continue; }
                var ofr = resolveSlotFrame(doc, cycleStart, oe.slot);
                if (!ofr) { continue; }
                var ost = null;
                try { ost = ofr.parentStory; } catch (e) {}
                if (!ost || !ost.isValid) { continue; }
                try { ost.recompose(); } catch (e) {}
                var otc = ost.textContainers;
                if (otc.length > 0 && otc[otc.length - 1].overflows) {
                    pend.push({ story: ost,
                                tag: "Q" + qn + " " + oe.slot });
                }
            }
            for (var pi2 = 0; pi2 < pend.length; pi2++) {
                fixStep3Overflow(pend[pi2].story, pend[pi2].tag);
            }
        }
    }

    // ── 실행 ─────────────────────────────────────────────────────────────────
    adjustCycles(doc, cycles.length);

    var cleanupPageIds = [];    // W18 D9 — 빈 슬롯 페이지 ID (플랜 기준)
    var cyclesDone = 0;
    var currentStart = HEADER_PAGES;
    for (var ci = 0; ci < cycles.length; ci++) {
        var cyc = null;
        try {
            cyc = readJSONFile(cycles[ci].path);
        } catch (eR) {
            wlog("[경고] 사이클 " + (ci + 1) + " 플랜 로드 실패: " + eR);
            currentStart += CYCLE_LENGTH;
            continue;
        }
        wlog("사이클 " + (ci + 1) + "/" + cycles.length + " Q" + cyc.q_num
             + " (시작 P" + (currentStart + 1) + ")");
        var beforePages = doc.pages.length;
        (function (c, start) {
            app.doScript(function () { processCycle(c, start); },
                         ScriptLanguage.JAVASCRIPT, undefined,
                         UndoModes.ENTIRE_SCRIPT,
                         "sero_v2 Q" + c.q_num);
        })(cyc, currentStart);
        var added = doc.pages.length - beforePages;
        wlog("사이클 " + (ci + 1) + " 완료 (+" + added + "p)");
        currentStart += CYCLE_LENGTH + added;
        cyclesDone++;
    }

    // 빈 슬롯 페이지 삭제 (W18 D9, plan.page_cleanup opt-in) — processCycle
    // 에서 플랜 기준으로 수집한 페이지 ID를 역순 삭제. 원고 없는 스텝의
    // 사이클 페이지가 번호 프레임/템플릿 데모만 남아 인쇄되던 잔재(G4b)
    // 해소. 하트비트 유지 (W12 D7 — 무로그 삭제 루프의 러너 행 오탐 방지).
    if (plan.page_cleanup && cleanupPageIds.length > 0) {
        var idSet = {};
        for (var ci2 = 0; ci2 < cleanupPageIds.length; ci2++) {
            idSet[cleanupPageIds[ci2]] = true;
        }
        var removed = 0;
        for (var dp = doc.pages.length - 1; dp >= HEADER_PAGES; dp--) {
            try {
                if (!idSet[doc.pages[dp].id]) { continue; }
                doc.pages[dp].remove();
                removed++;
                if (removed % 10 === 0) {
                    wlog("[정리] 빈 슬롯 페이지 삭제 진행: " + removed);
                }
            } catch (eDp) {}
        }
        wlog("[정리] 빈 슬롯 페이지 삭제: " + removed + "개 (대상 "
             + cleanupPageIds.length + ")");
    }

    // ── 간지 라벨 갱신 (W20 — plan.divider가 있을 때만; G22 소급 c17) ────
    // 가로 실행기 updateDividerPages(마스터 [None]+프레임 1개 휴리스틱)와
    // 달리 세로 내지의 간지는 '간지' 섹션의 2단락 스토리로 존재 — 라벨
    // 내용 정확 매칭('고N 모의고사' + 'YY년 M월' 연속 2단락)으로만 갱신
    // ('…월 짤지문' 라벨은 비매치 = v1 관행 보존, G22 제외와 동일).
    if (plan.divider && plan.divider.line1) {
        app.doScript(function () {
            var dn = 0;
            var reL1 = /^고\d\s*모의고사\s*$/;
            var reL2 = /^\d{1,2}년\s*\d{1,2}월\s*$/;
            var allStories = doc.stories.everyItem().getElements();
            for (var dvi = 0; dvi < allStories.length; dvi++) {
                var dvParas;
                try {
                    dvParas = allStories[dvi].paragraphs
                        .everyItem().getElements();
                } catch (eDv0) { continue; }
                if (dvParas.length < 2 || dvParas.length > 3) { continue; }
                var dvT1 = String(dvParas[0].contents || "")
                    .replace(/[\r\n]+$/, "");
                var dvT2 = String(dvParas[1].contents || "")
                    .replace(/[\r\n]+$/, "");
                if (!reL1.test(dvT1) || !reL2.test(dvT2)) { continue; }
                try {
                    var dvTail2 = (String(dvParas[1].contents || "")
                        .slice(-1) === "\r") ? "\r" : "";
                    dvParas[0].contents = plan.divider.line1 + "\r";
                    dvParas[1].contents = (plan.divider.line2 || "")
                        + dvTail2;
                    dn++;
                } catch (eDv) {}
            }
            wlog("간지 텍스트 업데이트: " + dn + "개 ("
                 + plan.divider.line1 + " / "
                 + (plan.divider.line2 || "") + ")");
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wb_sero_v2 divider");
    }

    // W45 답란 폴백 결산 (침묵 금지)
    if (fbCount > 0) {
        wlog("[답란] S_답란 없음 → 선지 폴백 " + fbCount + "개 단락"
             + (ind0Count > 0
                ? " / 들여쓰기 0 로컬 오버라이드 " + ind0Count + "개 ("
                  + ind0Sample + ")"
                : ""));
    }

    relockIcons();

    var ovf = 0;
    for (var s3 = 0; s3 < doc.stories.length; s3++) {
        try {
            var tc = doc.stories[s3].textContainers;
            if (tc.length > 0 && tc[tc.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("사이클완료: " + cyclesDone + "개");
    wlog("오버플로우: " + ovf + "개");

    doc.save(File(OUT_INDD));
    // PDF 페이지 범위는 **앱 전역 설정**이라 이전 수동 export의 범위가
    // 그대로 남는다 (2026-08-28 실측: 92쪽 문서가 3쪽짜리 PDF로 나왔다 —
    // INDD 는 정상, PDF 만 잘림). export 직전에 전체 페이지로 못 박는다
    // (convert_vertical / passage_remove 는 이미 이렇게 한다).
    try { app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES; }
    catch (ePR) {}
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    try { app.scriptPreferences.enableRedraw = true; } catch (e4) {}
    wlog("워크북 세로 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { relockIcons(); } catch (e3) {}
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    try { app.scriptPreferences.enableRedraw = true; } catch (e5) {}
}
