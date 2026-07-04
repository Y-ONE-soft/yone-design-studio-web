// 세서특필 v2 렌더 실행기 — ss-flows 플랜을 3개 스토리에 배치 (lib.jsxinc concat).
// 배치 의미론 = v1 engines/seseospecial/jsx/run.jsx와 동일:
//   part1  = plan.part1_page(1-기준) 페이지의 최대 스토리에 흘리기
//            (오버플로우 시 스프레드 추가 + 고정 기하 프레임)
//   part2  = part1/정답 제외 최대 스토리 — 프레임 1개(마진박스)로 정리 후
//            흘리고 유닛 경계 프레임 분리, 오버플로우 시 페이지/스프레드 확장
//   answers= 해설_번호 사본/정답 사본 시그니처 스토리에 흘리기
//   마지막에 part2 끝 ~ 정답 시작 사이 빈 페이지 제거 (v1 cleanup 이식)
// 프레임 분리: v1은 FRAME_BREAK 문자 삽입(단락 수 증가) — v2는 스타일 적용
// 후 startParagraph NEXT_FRAME (텍스트 무변형; 스타일 재적용이 로컬 오버라이드를
// 지우는 2026 회귀 대응으로 반드시 스타일 이후에 적용).
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

// ── 스토리 탐색 (v1 이식) ────────────────────────────────────────────────────
function findBiggestStory(page) {
    var items = page.textFrames;
    var maxP = 0;
    var best = null;
    for (var i = 0; i < items.length; i++) {
        try {
            var st = items[i].parentStory;
            if (st.paragraphs.length > maxP) { maxP = st.paragraphs.length; best = st; }
        } catch (e) {}
    }
    return best;
}

// 정답 스토리: 해설_번호 사본/정답 사본 단락이 앞쪽(첫 6단락)에 있는 스토리
function findAnswerStory(doc) {
    for (var s = 0; s < doc.stories.length; s++) {
        var st = doc.stories[s];
        if (st.paragraphs.length < 8) { continue; }
        var lim = Math.min(st.paragraphs.length, 6);
        for (var p = 0; p < lim; p++) {
            try {
                var nm = st.paragraphs[p].appliedParagraphStyle.name;
                if (nm === "해설_번호 사본" || nm === "정답 사본") { return st; }
            } catch (e) {}
        }
    }
    return null;
}

// part2 스토리 = part1/정답 제외 최대 스토리 (v1 typesetPart2Main 이식)
function findPart2Story(doc, p1Story, ansStory) {
    var best = null;
    var maxP = 0;
    for (var s = 0; s < doc.stories.length; s++) {
        var st = doc.stories[s];
        if (st === p1Story || st === ansStory) { continue; }
        try {
            if (st.paragraphs.length > maxP && st.paragraphs.length < 9000) {
                maxP = st.paragraphs.length;
                best = st;
            }
        } catch (e) {}
    }
    return best;
}

// 1단(전면) 프레임 = 페이지 마진박스 (v1 marginBox — 양쪽 페이지 자동 대응)
function marginBox(page) {
    var b = page.bounds;                 // [y1,x1,y2,x2] (spread 좌표)
    var m = page.marginPreferences;
    var pw = b[3] - b[1];
    var ph = b[2] - b[0];
    return [b[0] + m.top, m.left, b[0] + ph - m.bottom, pw - m.right];
}

// v1 고정 기하 (part1: [20,*,277,*], answers: [17,*,280,*])
function sideBounds(page, top, bottom) {
    // 주의: 엄격 비교(===)는 Enumerator 객체에서 신뢰 불가 — == 사용
    var isR = (page.side == PageSideOptions.RIGHT_HAND);
    var l = isR ? 233 : 20;
    var r = isR ? 400 : 187;
    return [top, l, bottom, r];
}

function spreadIndexOf(doc, spread) {
    for (var s = 0; s < doc.spreads.length; s++) {
        if (doc.spreads[s].id === spread.id) { return s; }
    }
    return -1;
}

var doc = null;
try {
    wlog("세서특필 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);
    app.scriptPreferences.enableRedraw = false;

    var styleCache = {};
    var missingStyles = {};
    function styleOf(name) {
        if (!name) { return null; }
        if (styleCache[name]) { return styleCache[name]; }
        if (missingStyles[name]) { return null; }
        var ps = findParagraphStyleByPath(doc, name);
        if (ps) { styleCache[name] = ps; return ps; }
        missingStyles[name] = true;
        wlog("[경고] 스타일 없음(자동 생성 안 함): " + name);
        return null;
    }
    var noneCS = doc.characterStyles[0];

    // ── 스토리 선탐색 (배치 전 문서 상태 기준 — v1 순서 의미론 유지) ────────
    var p1PageIdx = (plan.part1_page || 6) - 1;
    var p1Story = null;
    try { p1Story = findBiggestStory(doc.pages[p1PageIdx]); } catch (e) {}
    var ansStory = findAnswerStory(doc);
    var p2Story = findPart2Story(doc, p1Story, ansStory);

    // ── 공통 배치 (텍스트 + 문자스타일 초기화 + 단락스타일 + 밑줄 + 브레이크) ──
    function placeFlow(story, flow) {
        var flat = [];
        var unitStart = [];
        for (var u = 0; u < flow.units.length; u++) {
            var uParas = flow.units[u].paras || [];
            unitStart.push(flat.length);
            for (var q = 0; q < uParas.length; q++) { flat.push(uParas[q]); }
        }
        var texts = [];
        for (var i = 0; i < flat.length; i++) { texts.push(flat[i].t); }
        var joined = texts.join("\r");
        // 마지막 단락이 빈 문자열이면 단락 객체가 생기지 않아 정렬이 어긋남
        if (texts.length > 0 && texts[texts.length - 1] === "") { joined += "\r"; }
        story.contents = joined;
        try { story.texts[0].appliedCharacterStyle = noneCS; } catch (e) {}

        // 대형 스토리 필수: 컬렉션 인덱싱 대신 getElements() 1회 캐시
        var paras = story.paragraphs.everyItem().getElements();
        var isStart = {};
        if (flow.break_per_unit) {
            for (var us = 0; us < unitStart.length; us++) { isStart[unitStart[us]] = true; }
        }
        for (var pi = 0; pi < flat.length && pi < paras.length; pi++) {
            var ps2 = styleOf(flat[pi].s);
            if (ps2) { paras[pi].appliedParagraphStyle = ps2; }
            if (flow.break_per_unit && pi > 0 && isStart[pi]) {
                // 스타일 적용 후에 브레이크 (스타일 재적용이 오버라이드를 지움)
                try { paras[pi].startParagraph = StartParagraph.NEXT_FRAME; } catch (e) {}
            }
            var runs = flat[pi].runs;
            if (runs && runs.length > 0) {
                // v1 밑줄 이식: 문자스타일 아님 — underline 속성 직접 적용
                var off = 0;
                for (var ri = 0; ri < runs.length; ri++) {
                    var rl = runs[ri].t ? runs[ri].t.length : 0;
                    if (rl > 0 && runs[ri].ul) {
                        var a = off;
                        var b = off + rl - 1;
                        if (a < paras[pi].characters.length && b < paras[pi].characters.length) {
                            var rg = paras[pi].characters.itemByRange(a, b);
                            rg.underline = true;
                            rg.underlineWeight = 0.5;
                            rg.underlineOffset = 1.5;
                        }
                    }
                    off += rl;
                }
            }
            if ((pi + 1) % 50 === 0) {
                wlog(flow.area + " 스타일: " + (pi + 1) + "/" + flat.length);
            }
        }
        wlog("배치완료 " + flow.area + ": " + flat.length + "단락 (유닛 " + flow.units.length + ")");
        return flat.length;
    }

    // ── 오버플로우 확장: 스프레드 추가 + 고정 기하 프레임 (v1 part1/answers) ──
    function expandFixed(story, top, bottom, maxSpreads) {
        if (!story.overflows) { return; }
        var conts = story.textContainers;
        var lastFrame = conts[conts.length - 1];
        var lastSpread = lastFrame.parentPage.parent;
        var prevFrame = lastFrame;
        var cnt = 0;
        while (story.overflows && cnt < maxSpreads) {
            var si = spreadIndexOf(doc, lastSpread);
            lastSpread = doc.spreads.add(LocationOptions.AFTER, doc.spreads[si]);
            for (var pp = 0; pp < lastSpread.pages.length; pp++) {
                if (!story.overflows) { break; }
                var tf = lastSpread.pages[pp].textFrames.add();
                tf.geometricBounds = sideBounds(lastSpread.pages[pp], top, bottom);
                prevFrame.nextTextFrame = tf;
                prevFrame = tf;
            }
            cnt++;
            if (cnt % 10 === 0) { wlog("오버플로우 확장: 스프레드 +" + cnt); }
        }
        if (cnt > 0) { wlog("오버플로우 확장: 스프레드 +" + cnt); }
    }

    // ── part1 ───────────────────────────────────────────────────────────────
    var fi;
    var flowByArea = {};
    for (fi = 0; fi < plan.flows.length; fi++) { flowByArea[plan.flows[fi].area] = plan.flows[fi]; }

    if (flowByArea.part1) {
        if (!p1Story) {
            wlog("[경고] part1: " + (p1PageIdx + 1) + "페이지 스토리 없음 - 스킵");
        } else {
            app.doScript(function () {
                placeFlow(p1Story, flowByArea.part1);
                expandFixed(p1Story, 20, 277, 100);
            }, ScriptLanguage.JAVASCRIPT, undefined,
               UndoModes.ENTIRE_SCRIPT, "ss_v2 part1");
        }
    }

    // ── part2 ───────────────────────────────────────────────────────────────
    var p2BasePage = null;
    if (flowByArea.part2) {
        if (!p2Story || p2Story.paragraphs.length < 10) {
            wlog("[경고] part2: 실전문제 스토리 없음 - 스킵");
            p2Story = null;
        } else {
            app.doScript(function () {
                // 클리어 + 프레임 1개만 남기고 마진박스로 (v1 이식)
                p2Story.contents = "";
                while (p2Story.textContainers.length > 1) {
                    p2Story.textContainers[p2Story.textContainers.length - 1].remove();
                }
                var baseFrame = p2Story.textContainers[0];
                p2BasePage = baseFrame.parentPage;
                var currentSpread = p2BasePage.parent;
                baseFrame.geometricBounds = marginBox(p2BasePage);
                var prevFrame = baseFrame;

                placeFlow(p2Story, flowByArea.part2);

                // 오버플로우: 현재 스프레드 나머지 페이지 → 새 스프레드 (v1 이식)
                function addFrame(page) {
                    var tf = page.textFrames.add();
                    tf.geometricBounds = marginBox(page);
                    prevFrame.nextTextFrame = tf;
                    prevFrame = tf;
                }
                for (var pp = 0; pp < currentSpread.pages.length; pp++) {
                    if (!p2Story.overflows) { break; }
                    // v1은 객체 !== 비교 — 스펙파이어 재현마다 다른 객체라
                    // 신뢰 불가. id 비교로 기지 페이지 중복 프레임 방지.
                    if (currentSpread.pages[pp].id !== p2BasePage.id) { addFrame(currentSpread.pages[pp]); }
                }
                var safety = 0;
                while (p2Story.overflows && safety < 400) {
                    var si = spreadIndexOf(doc, currentSpread);
                    currentSpread = doc.spreads.add(LocationOptions.AFTER, doc.spreads[si]);
                    for (var pp2 = 0; pp2 < currentSpread.pages.length; pp2++) {
                        if (!p2Story.overflows) { break; }
                        addFrame(currentSpread.pages[pp2]);
                    }
                    safety++;
                    if (safety % 20 === 0) { wlog("part2 확장: 스프레드 +" + safety); }
                }
                if (safety > 0) { wlog("part2 확장: 스프레드 +" + safety); }
            }, ScriptLanguage.JAVASCRIPT, undefined,
               UndoModes.ENTIRE_SCRIPT, "ss_v2 part2");
        }
    }

    // ── answers (플랜에 없으면 v1처럼 기존 정답 스토리 보존) ─────────────────
    if (flowByArea.answers) {
        if (!ansStory) {
            wlog("[경고] answers: 정답지 스토리 없음 - 스킵");
        } else {
            app.doScript(function () {
                placeFlow(ansStory, flowByArea.answers);
                expandFixed(ansStory, 17, 280, 40);
            }, ScriptLanguage.JAVASCRIPT, undefined,
               UndoModes.ENTIRE_SCRIPT, "ss_v2 answers");
        }
    } else {
        wlog("answers: 입력 없음 - 기존 정답 스토리 보존(스킵)");
    }

    // ── 빈 페이지 정리: part2 끝 ~ 정답 시작 사이 (v1 cleanup 이식) ──────────
    try {
        function lastPg(st) {
            var tc = st.textContainers;
            var pg = tc[tc.length - 1].parentPage;
            return pg ? pg.documentOffset : -1;
        }
        function firstPg(st) {
            var pg = st.textContainers[0].parentPage;
            return pg ? pg.documentOffset : -1;
        }
        var from = p2Story ? lastPg(p2Story) : -1;
        var to = ansStory ? firstPg(ansStory) : doc.pages.length;
        var removed = 0;
        if (from >= 0 && to > from + 1) {
            var lo = from + 1;
            var hi = to - 1;
            var allEmpty = true;
            for (var pi2 = lo; pi2 <= hi; pi2++) {
                if (doc.pages[pi2].pageItems.length !== 0) { allEmpty = false; break; }
            }
            if (allEmpty) {
                doc.pages.itemByRange(doc.pages[lo], doc.pages[hi]).remove();
                removed = hi - lo + 1;
            } else {
                for (var pi3 = hi; pi3 >= lo; pi3--) {
                    try {
                        if (doc.pages[pi3].pageItems.length === 0) {
                            doc.pages[pi3].remove();
                            removed++;
                        }
                    } catch (e) {}
                }
            }
        }
        wlog("빈 페이지 제거: " + removed + "개");
    } catch (e) {
        wlog("[경고] 빈 페이지 정리 오류: " + e);
    }

    // ── 오버플로우 집계 ──────────────────────────────────────────────────────
    var ovf = 0;
    for (var s3 = 0; s3 < doc.stories.length; s3++) {
        try {
            var tc2 = doc.stories[s3].textContainers;
            if (tc2.length > 0 && tc2[tc2.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("오버플로우: " + ovf + "개");

    doc.save(File(OUT_INDD));
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    try { app.scriptPreferences.enableRedraw = true; } catch (e4) {}
    wlog("세서특필 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    try { app.scriptPreferences.enableRedraw = true; } catch (e5) {}
}
