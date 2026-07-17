// 지문 제거 실행기 (W26) — 조판된 워크북 전체(C)에서 선택 지문의 모든 섹션
// 변형 유닛(단락 범위)을 제거하고 페이지를 정리한다 (lib.jsxinc concat).
//
// 입력 스펙(__SPEC_PATH__ JSON — engines/passage_remove/engine.py 생성):
//   { "stories": [ { "story": <dump idx>,
//                    "remove":   [{"start","end","p0"} ...],   // 단락 범위(포함)
//                    "renumber": [{"p0","label"} ...] } ...],  // 잔존 유닛 순서
//     "clear_numbers": ["20", ...] }                           // 제거 지문 라벨
//
// 스토리 인덱스는 dump_stories.jsx와 동일한 doc.stories.everyItem()
// .getElements() 순서 — 같은 파일 사본이므로 순서가 보존된다. 안전장치로
// 각 범위의 시작 단락 텍스트(p0 접두)를 대조하고, 불일치면 그 범위는
// 건드리지 않고 [경고]만 남긴다 (verify가 잔존을 잡아 ok=False).
//
// ExtendScript ES3 — let/const/화살표/템플릿 리터럴 금지.

var DOC_PATH = "__DOC_PATH__";
var SPEC_PATH = "__SPEC_PATH__";
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

var RE_BARE_NUM = /^\s*[\{\[]?\d{1,3}(?:\s*~\s*\d{1,3})?[\}\]]?\s*$/;

function normPrefix(s) {
    // 접두 대조용 정규화 — 개행/앵커/연속 공백 정리
    s = String(s || "");
    s = s.replace(/[\r\n￼]/g, " ");
    s = s.replace(/\s+/g, " ");
    s = s.replace(/^\s+|\s+$/g, "");
    return s;
}

function prefixMatches(paraText, p0) {
    var a = normPrefix(paraText);
    var b = normPrefix(p0);
    if (b.length === 0) { return a.length === 0; }
    var n = Math.min(a.length, b.length, 40);
    return a.substring(0, n) === b.substring(0, n);
}

function isBlankFrameContent(tf) {
    var c = "";
    try { c = String(tf.contents || ""); } catch (e) {}
    return c.replace(/[\s\r\n￼]+/g, "").length === 0;
}

// 스토리 꼬리의 overset 공백 제거 (workbook_flow trimWsOverset 이식 — 절단
// 후 공백 전용 꼬리가 overset '\r'로 남는 것 방지)
function trimWsOverset(story) {
    var conts = story.textContainers;
    if (!conts || conts.length === 0) { return 0; }
    var ov = false;
    try { ov = conts[conts.length - 1].overflows; } catch (e) {}
    if (!ov) { return 0; }
    var total = story.characters.length;
    var lastReal = total - 1;
    var scanned = 0;
    while (lastReal >= 0 && scanned < 500) {
        var ch = "";
        try { ch = String(story.characters[lastReal].contents); }
        catch (e) { return 0; }
        if (ch.replace(/[\s\r\n﻿￼]+/g, "").length > 0) { break; }
        lastReal--;
        scanned++;
    }
    if (lastReal < 0 || lastReal >= total - 1) { return 0; }
    var placedEnd = -1;
    for (var pe = 0; pe < conts.length; pe++) {
        try {
            var pcs = conts[pe].characters;
            if (pcs.length > 0) {
                var pl = pcs[-1].index;
                if (pl > placedEnd) { placedEnd = pl; }
            }
        } catch (e) {}
    }
    var from = (placedEnd + 1 > lastReal + 1) ? placedEnd + 1 : lastReal + 1;
    if (from > total - 1) { return 0; }
    try {
        story.characters.itemByRange(from, total - 1).remove();
        return total - from;
    } catch (e) { return 0; }
}

// 페이지의 단일 프레임 번호 스토리 찾기 (지문번호 프레임)
function bareNumFrameOnPage(pg) {
    var tfs = pg.textFrames;
    for (var i = 0; i < tfs.length; i++) {
        try {
            var st = tfs[i].parentStory;
            if (st.textContainers.length !== 1) { continue; }
            if (RE_BARE_NUM.test(String(st.contents || ""))) { return tfs[i]; }
        } catch (e) {}
    }
    return null;
}

function numOfBareFrame(tf) {
    var c = "";
    try { c = String(tf.parentStory.contents || ""); } catch (e) { return ""; }
    c = c.replace(/[^\d~]/g, "");
    return c;
}

var doc = null;
try {
    wlog("지문 제거 시작: " + DOC_PATH);
    var spec = readJSONFile(SPEC_PATH);
    doc = app.open(File(DOC_PATH), false);
    app.scriptPreferences.enableRedraw = false;

    var allStories = doc.stories.everyItem().getElements();
    wlog("스토리 " + allStories.length + "개");

    var affected = [];   // {story(obj), spec(entry)}
    var skipped = 0;
    var removedRanges = 0;

    // ── 1) 단락 범위 삭제 (스토리별, 문자 인덱스 선계산 → 내림차순 삭제) ──
    for (var si = 0; si < spec.stories.length; si++) {
        var entry = spec.stories[si];
        if (entry.story < 0 || entry.story >= allStories.length) {
            wlog("[경고] 스토리 인덱스 범위 밖: " + entry.story);
            skipped += (entry.remove || []).length;
            continue;
        }
        var story = allStories[entry.story];
        affected.push({ story: story, spec: entry });
        var rem = entry.remove || [];
        if (rem.length === 0) { continue; }

        app.doScript((function (storyC, remC, entryC) {
            return function () {
                var paras = storyC.paragraphs.everyItem().getElements();
                var ranges = [];
                for (var ri = 0; ri < remC.length; ri++) {
                    var r = remC[ri];
                    if (r.start < 0 || r.end >= paras.length || r.start > r.end) {
                        wlog("[경고] 단락 범위 밖 (story " + entryC.story + "): "
                             + r.start + "~" + r.end + " / " + paras.length);
                        skipped++;
                        continue;
                    }
                    var t0 = "";
                    try { t0 = String(paras[r.start].contents); } catch (e) {}
                    if (!prefixMatches(t0, r.p0)) {
                        wlog("[경고] 접두 불일치 — 범위 보류 (story "
                             + entryC.story + " " + r.start + "~" + r.end
                             + "): '" + normPrefix(t0).substring(0, 30) + "'");
                        skipped++;
                        continue;
                    }
                    var c0 = -1;
                    var c1 = -1;
                    try {
                        c0 = paras[r.start].characters[0].index;
                        var lastP = paras[r.end];
                        if (lastP.characters.length > 0) {
                            c1 = lastP.characters[-1].index;
                        } else if (r.end > r.start) {
                            var prevP = paras[r.end - 1];
                            c1 = prevP.characters[-1].index;
                        }
                    } catch (e) {
                        wlog("[경고] 문자 인덱스 계산 실패 (story "
                             + entryC.story + "): " + e);
                    }
                    if (c0 < 0 || c1 < c0) { skipped++; continue; }
                    ranges.push([c0, c1]);
                }
                // 내림차순 삭제 — 앞 범위 인덱스 불변
                ranges.sort(function (a, b) { return b[0] - a[0]; });
                for (var di = 0; di < ranges.length; di++) {
                    storyC.characters.itemByRange(
                        ranges[di][0], ranges[di][1]).remove();
                    removedRanges++;
                    if (removedRanges % 10 === 0) {
                        wlog("삭제 진행: " + removedRanges + "개 범위");
                    }
                }
                wlog("story " + entryC.story + ": " + ranges.length
                     + "개 범위 삭제");
            };
        })(story, rem, entry), ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "passage_remove del s" + entry.story);
    }
    wlog("단락 범위 삭제: " + removedRanges + "개 (보류 " + skipped + ")");

    // ── 1b) 페이지 정리 후보 수집 — 반드시 스레드 절단 *전* (절단하면 빈
    //        꼬리 프레임이 스토리에서 분리돼 textContainers로 못 찾는다 —
    //        1차 E2E 실측: 절단 후 수집 시 후보 0 → 페이지 삭제 0) ────────
    var candPages = {};   // documentOffset → true
    for (var cb = 0; cb < affected.length; cb++) {
        try {
            var contsB = affected[cb].story.textContainers;
            for (var cbi = 0; cbi < contsB.length; cbi++) {
                var pgB = null;
                try { pgB = contsB[cbi].parentPage; } catch (e) {}
                if (pgB) { candPages[pgB.documentOffset] = true; }
            }
        } catch (e) {}
    }

    // ── 2) 잔여 빈 꼬리 프레임 스레드 절단 + overset 공백 정리 (W13/W19) ──
    var unthreaded = 0;
    for (var ai = 0; ai < affected.length; ai++) {
        var stA = affected[ai].story;
        try {
            var conts = stA.textContainers;
            var lastWithText = -1;
            for (var ci = 0; ci < conts.length; ci++) {
                var cc = "";
                try { cc = String(conts[ci].contents || ""); } catch (e) {}
                if (cc.replace(/[\s\r\n￼]+/g, "").length > 0) {
                    lastWithText = ci;
                }
            }
            if (lastWithText >= 0 && lastWithText < conts.length - 1) {
                try {
                    conts[lastWithText].nextTextFrame = NothingEnum.NOTHING;
                } catch (eN) {
                    conts[lastWithText].nextTextFrame = null;
                }
                unthreaded++;
                var tr = trimWsOverset(stA);
                if (tr > 0) {
                    wlog("꼬리 공백 overset " + tr + "자 정리 (story "
                         + affected[ai].spec.story + ")");
                }
            }
        } catch (e) {}
    }
    if (unthreaded > 0) { wlog("빈 꼬리 스레드 절단: " + unthreaded + "개 스토리"); }

    // ── 3) 지문번호 프레임 갱신 (잔존 유닛 시작 페이지 기준) ─────────────
    var renumbered = 0;
    var renumberMiss = 0;
    var pageWritten = {};   // 페이지 name → true (갱신된 페이지)
    app.doScript(function () {
        for (var ai2 = 0; ai2 < affected.length; ai2++) {
            var entry2 = affected[ai2].spec;
            var list = entry2.renumber || [];
            if (list.length === 0) { continue; }
            var story2 = affected[ai2].story;
            var paras2 = story2.paragraphs.everyItem().getElements();
            var k = 0;
            for (var pi = 0; pi < paras2.length && k < list.length; pi++) {
                var pt = "";
                try { pt = String(paras2[pi].contents); } catch (e) { continue; }
                if (!prefixMatches(pt, list[k].p0)) { continue; }
                var ppg = null;
                try {
                    var ptf = paras2[pi].parentTextFrames;
                    if (ptf.length > 0) { ppg = ptf[0].parentPage; }
                } catch (e) {}
                if (ppg && !pageWritten[String(ppg.name)]) {
                    var nf = bareNumFrameOnPage(ppg);
                    if (nf) {
                        var cur = String(nf.parentStory.contents || "");
                        var neu = cur.replace(/\d{1,3}(\s*~\s*\d{1,3})?/,
                                              String(list[k].label));
                        if (neu !== cur) {
                            nf.parentStory.contents = neu;
                            renumbered++;
                        }
                        pageWritten[String(ppg.name)] = true;
                    }
                }
                k++;
            }
            if (k < list.length) {
                renumberMiss += (list.length - k);
                wlog("[경고] 번호 갱신 유닛 못 찾음 " + (list.length - k)
                     + "개 (story " + entry2.story + ")");
            }
        }
    }, ScriptLanguage.JAVASCRIPT, undefined,
       UndoModes.ENTIRE_SCRIPT, "passage_remove renumber");
    wlog("지문번호 프레임 갱신: " + renumbered + "개 (미발견 " + renumberMiss + ")");

    // ── 4) 페이지 정리 — 영향 스토리 프레임이 놓인 페이지(1b에서 절단 전
    //      수집) 중 전부 빈/번호/장식 프레임뿐인 페이지 삭제
    //      (workbook_flow cleanupPages delete 모드의 판정을 영향 페이지로
    //      한정 이식 — 간지/표지는 후보가 아님) ────────────────────────────
    var affectedIds = {};
    for (var ai3 = 0; ai3 < affected.length; ai3++) {
        try { affectedIds[String(affected[ai3].story.id)] = true; } catch (e) {}
    }
    var offs = [];
    for (var off in candPages) {
        if (candPages.hasOwnProperty(off)) { offs.push(parseInt(off, 10)); }
    }
    offs.sort(function (a, b) { return b - a; });   // 역순 삭제

    // W22 장식 텍스트 수집 (workbook_flow furnKeyOf 이식): 플로우 콘텐츠가
    // 있는 후보 페이지의 단일 프레임 비-플로우 텍스트(반복 발문/섹션 탭).
    // 잔여 페이지에 같은 텍스트 장식만 남으면 빈 프레임 취급해야 삭제된다.
    function furnKeyOf(tf) {
        var c = "";
        try { c = String(tf.contents || ""); } catch (e) { return ""; }
        c = c.replace(/[\s\r\n ￼]+/g, " ");
        c = c.replace(/^\s+|\s+$/g, "");
        if (c.length === 0 || c.length > 120) { return ""; }
        return c;
    }
    var furn = {};
    for (var fo = 0; fo < offs.length; fo++) {
        var pgF = null;
        try { pgF = doc.pages[offs[fo]]; } catch (e) { continue; }
        if (!pgF || !pgF.isValid) { continue; }
        var tfsF = pgF.textFrames;
        var hasFlowF = false;
        for (var ff = 0; ff < tfsF.length; ff++) {
            try {
                if (affectedIds[String(tfsF[ff].parentStory.id)]
                        && !isBlankFrameContent(tfsF[ff])) {
                    hasFlowF = true;
                    break;
                }
            } catch (e) {}
        }
        if (!hasFlowF) { continue; }
        for (var fg = 0; fg < tfsF.length; fg++) {
            try {
                var stF = tfsF[fg].parentStory;
                if (affectedIds[String(stF.id)]) { continue; }
                if (stF.textContainers.length !== 1) { continue; }
                var fk = furnKeyOf(tfsF[fg]);
                if (fk) { furn[fk] = true; }
            } catch (e) {}
        }
    }
    var removedPages = 0;
    var clearNums = {};
    var cn = spec.clear_numbers || [];
    for (var cni = 0; cni < cn.length; cni++) { clearNums[String(cn[cni])] = true; }
    var clearedFrames = 0;
    app.doScript(function () {
        for (var oi = 0; oi < offs.length; oi++) {
            if (oi > 0 && oi % 20 === 0) {
                wlog("페이지 정리 진행: " + oi + "/" + offs.length
                     + " (" + removedPages + "개 삭제)");
            }
            var pg4 = null;
            try { pg4 = doc.pages[offs[oi]]; } catch (e) { continue; }
            if (!pg4 || !pg4.isValid) { continue; }
            var tfs4 = pg4.textFrames;
            var anyFrame = tfs4.length > 0;
            var allBlankOrNum = anyFrame;
            var hasFlowContent = false;
            for (var tf4 = 0; tf4 < tfs4.length; tf4++) {
                var pst4 = null;
                var nConts4 = 0;
                try {
                    pst4 = tfs4[tf4].parentStory;
                    nConts4 = pst4.textContainers.length;
                } catch (e) { allBlankOrNum = false; continue; }
                var blank4 = isBlankFrameContent(tfs4[tf4]);
                var bare4 = (nConts4 === 1
                             && RE_BARE_NUM.test(String(pst4.contents || "")));
                // W22 장식 판정: 수집된 반복 발문/섹션 탭과 같은 단일
                // 프레임은 빈 프레임 취급
                var furn4 = false;
                if (!blank4 && !bare4 && nConts4 === 1) {
                    try {
                        if (!affectedIds[String(pst4.id)]) {
                            var fk4 = furnKeyOf(tfs4[tf4]);
                            furn4 = !!(fk4 && furn[fk4]);
                        }
                    } catch (eF4) {}
                }
                if (!blank4 && !bare4 && !furn4) { allBlankOrNum = false; }
                try {
                    if (affectedIds[String(pst4.id)] && !blank4) {
                        hasFlowContent = true;
                    }
                } catch (e2) {}
            }
            if (anyFrame && allBlankOrNum && !hasFlowContent) {
                try { pg4.remove(); removedPages++; } catch (e) {}
                continue;
            }
            // 잔존 페이지: 제거 지문 라벨의 번호 프레임 정리 (번호 갱신
            // 패스가 안 쓴 페이지에 옛 번호가 남은 경우)
            var nf4 = bareNumFrameOnPage(pg4);
            if (nf4 && !pageWritten[String(pg4.name)]) {
                var num4 = numOfBareFrame(nf4);
                if (num4 && clearNums[num4]) {
                    try {
                        nf4.remove();
                        clearedFrames++;
                        wlog("잔존 번호 프레임 제거: " + num4
                             + " (p" + pg4.name + ")");
                    } catch (e) {}
                }
            }
        }
    }, ScriptLanguage.JAVASCRIPT, undefined,
       UndoModes.ENTIRE_SCRIPT, "passage_remove cleanup");
    wlog("페이지 정리: " + removedPages + "개 삭제, 잔존 번호 프레임 "
         + clearedFrames + "개 제거");
    if (removedPages % 2 === 1) {
        wlog("[경고] 홀수(" + removedPages + ") 페이지 삭제 — 이후 좌/우 "
             + "마스터 정렬 확인 필요");
    }

    // ── 5) 오버플로우 집계 + 저장/Export ─────────────────────────────────
    var ovf = 0;
    for (var s5 = 0; s5 < doc.stories.length; s5++) {
        try {
            var tc5 = doc.stories[s5].textContainers;
            if (tc5.length > 0 && tc5[tc5.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("오버플로우: " + ovf + "개");

    wlog("문서 저장 시작 (로그 무갱신 수 분 가능)");
    doc.save(File(OUT_INDD));
    // 스크립트 export가 사용자 UI 잔존 설정을 상속하는 문제 (2026-07-17
    // 실측 — 페이지별 분할 등) → export 직전 정규화 필수
    try {
        app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;
        app.pdfExportPreferences.exportAsSinglePages = false;
        app.pdfExportPreferences.viewPDF = false;
    } catch (ePref) {}
    wlog("PDF export 시작 (대형 문서는 로그 무갱신 20분+ 가능)");
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    try { app.scriptPreferences.enableRedraw = true; } catch (e4) {}
    wlog("지문 제거 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    try { app.scriptPreferences.enableRedraw = true; } catch (e5) {}
}
