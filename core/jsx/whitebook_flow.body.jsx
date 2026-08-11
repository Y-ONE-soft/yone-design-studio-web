// 화이트북 v2 렌더 실행기 — wbwt-flows 플랜을 영역별 스토리에 배치 (lib.jsxinc concat).
// 배치 의미론 = v1 engines/whitebook/jsx/run.jsx v3와 동일:
//   스토리 탐색(첫 단락 스타일 / 정답 시그니처 / F·C-마스터 프레임 기하)
//   → 유닛 i ↔ 스토리 i 통째 교체(replaceContent) + 유닛 ops
//   (expand_last/expand_move/numbering_restart/ans_char/icons/ans_frame_fix).
// GREP 2종(D박스 ①분할, <u>밑줄)은 파이썬 플랜 전처리로 대체됨 (runs/단락 분할).
// 스타일/문자스타일 자동 생성 금지 — 없으면 [경고] 로그만.
// 컬렉션 규칙: characters.everyItem() 일괄 대입 금지(texts[0]),
//   paragraphs는 everyItem().getElements() 1회 캐시.

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

// v1 autoSizingType 원시값 (HEIGHT_ONLY / OFF)
var HEIGHT_ONLY_VAL = 1751476583;
var AUTOSIZE_OFF_VAL = 1330005536;

// "그룹 > 이름" 전체 경로 → 이름만 (탐색은 v1처럼 style.name 단순명 비교)
function baseName(fullPath) {
    var parts = String(fullPath).split(">");
    var last = parts[parts.length - 1];
    return last.replace(/^\s+|\s+$/g, "");
}

// ── 스토리 탐색 (v1 이식) ────────────────────────────────────────────────────

// 첫 단락 스타일명으로 스토리 수집 (페이지 순서 = Day 순서)
function storiesByFirstStyle(doc, styleName) {
    var found = [];
    var seen = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var tfs = doc.pages[p].textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                var story = tfs[t].parentStory;
                if (seen[story.id]) { continue; }
                if (story.paragraphs.length > 0 &&
                        story.paragraphs[0].appliedParagraphStyle.name === styleName) {
                    seen[story.id] = true;
                    found.push(story);
                }
            } catch (e) {}
        }
    }
    return found;
}

// 정답 스토리: 첫 단락에 '정답' 포함 + 둘째 단락 스타일 secondStyle
function answerStories(doc, secondStyle) {
    var found = [];
    var seen = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var tfs = doc.pages[p].textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                var story = tfs[t].parentStory;
                if (seen[story.id]) { continue; }
                if (story.paragraphs.length > 1) {
                    var txt = story.paragraphs[0].contents
                        .replace(/￼/g, "").replace(/\r/g, "").replace(/^\s+/, "");
                    var secondSty = story.paragraphs[1].appliedParagraphStyle.name;
                    if (txt.indexOf("정답") >= 0 && secondSty === secondStyle) {
                        seen[story.id] = true;
                        found.push(story);
                    }
                }
            } catch (e) {}
        }
    }
    return found;
}

// 연습문제 본문 스토리: F-마스터 시작 페이지의 본문 TF (v1 기하 조건)
function practiceMainStories(doc) {
    var found = [];
    var seen = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var page = doc.pages[p];
        var mname = "";
        try { mname = page.appliedMaster ? page.appliedMaster.name : ""; } catch (e) {}
        if (mname !== "F-마스터") { continue; }
        var tfs = page.textFrames;
        var candidates = [];
        for (var t = 0; t < tfs.length; t++) {
            try {
                var gb = tfs[t].geometricBounds;
                if (gb[1] < 19.5) { continue; }        // 사이드바 제외
                if (gb[3] - gb[1] < 50) { continue; }  // 좁은 프레임 제외
                if (gb[2] - gb[0] < 50) { continue; }  // 높이 부족 제외
                candidates.push({ tf: tfs[t], gb: gb });
            } catch (e) {}
        }
        candidates.sort(function (a, b) {
            if (Math.abs(a.gb[0] - b.gb[0]) > 5) { return a.gb[0] - b.gb[0]; }
            return a.gb[1] - b.gb[1];
        });
        for (var ci = 0; ci < candidates.length; ci++) {
            var st = candidates[ci].tf.parentStory;
            if (seen[st.id]) { continue; }
            try {
                var firstContainer = st.textContainers[0];
                if (firstContainer && firstContainer.parentPage &&
                        firstContainer.parentPage.id !== page.id) { continue; }
            } catch (e) {}
            seen[st.id] = true;
            found.push(st);
            break;
        }
    }
    return found;
}

// 연습문제 정답 스토리: C-마스터 페이지 본문 TF 중 Day 정답 아닌 스토리
function practiceAnswerStories(doc, dayAnsStories) {
    var dayAnsIds = {};
    for (var i = 0; i < dayAnsStories.length; i++) {
        dayAnsIds[dayAnsStories[i].id] = true;
    }
    var found = [];
    var seen = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var page = doc.pages[p];
        var mname = "";
        try { mname = page.appliedMaster ? page.appliedMaster.name : ""; } catch (e) {}
        if (mname !== "C-마스터") { continue; }
        var tfs = page.textFrames;
        var candidates = [];
        for (var t = 0; t < tfs.length; t++) {
            try {
                var gb = tfs[t].geometricBounds;
                if (gb[1] < 19.5) { continue; }
                if (gb[3] - gb[1] < 100) { continue; }
                if (gb[2] - gb[0] < 100) { continue; }
                candidates.push({ tf: tfs[t], gb: gb });
            } catch (e) {}
        }
        candidates.sort(function (a, b) {
            if (Math.abs(a.gb[0] - b.gb[0]) > 5) { return a.gb[0] - b.gb[0]; }
            return a.gb[1] - b.gb[1];
        });
        for (var ci = 0; ci < candidates.length; ci++) {
            var st = candidates[ci].tf.parentStory;
            if (dayAnsIds[st.id]) { continue; }
            if (seen[st.id]) { continue; }
            try {
                var firstContainer = st.textContainers[0];
                if (firstContainer && firstContainer.parentPage &&
                        firstContainer.parentPage.id !== page.id) { continue; }
            } catch (e) {}
            seen[st.id] = true;
            found.push(st);
            break;
        }
    }
    return found;
}

// ── 프레임 기하 ops (v1 이식) ────────────────────────────────────────────────

function expandChainLastFrame(story) {
    if (!story || !story.isValid) { return; }
    try {
        var c = story.textContainers;
        if (c.length === 0) { return; }
        // 베타2 결함: 자동 크기 기준점이 CENTER면 프레임이 페이지 중앙으로
        // 수축한다(내용이 페이지 가운데 떠 있음). 체인 전체를 TOP 고정으로.
        for (var i = 0; i < c.length; i++) {
            try {
                var tfp = c[i].textFramePreferences;
                if (i === c.length - 1 || Number(tfp.autoSizingType) != AUTOSIZE_OFF_VAL) {
                    tfp.autoSizingReferencePoint =
                        AutoSizingReferenceEnum.TOP_CENTER_POINT;
                }
            } catch (e1) {}
        }
        c[c.length - 1].textFramePreferences.autoSizingType = HEIGHT_ONLY_VAL;
    } catch (e) {}
}

function expandFrameAndMoveBelow(story, moveStyles) {
    if (!story || !story.isValid) { return; }
    try {
        var c = story.textContainers;
        if (c.length === 0) { return; }
        var frame = c[0];
        var oldGb = frame.geometricBounds;
        var oldTop = oldGb[0], oldBot = oldGb[2];
        frame.textFramePreferences.autoSizingType = HEIGHT_ONLY_VAL;
        var measuredGb = frame.geometricBounds;
        var measuredHeight = measuredGb[2] - measuredGb[0];
        frame.textFramePreferences.autoSizingType = AUTOSIZE_OFF_VAL;
        frame.geometricBounds = [oldTop, oldGb[1], oldTop + measuredHeight, oldGb[3]];
        var newBot = oldTop + measuredHeight;
        var delta = newBot - oldBot;
        if (delta < 0.01) { return; }
        var pg = frame.parentPage;
        if (!pg) { return; }
        var tfs = pg.textFrames;
        for (var i = 0; i < tfs.length; i++) {
            try {
                var other = tfs[i];
                if (other.parentStory === story) { continue; }
                if (other.parentStory.paragraphs.length === 0) { continue; }
                var osty = other.parentStory.paragraphs[0].appliedParagraphStyle.name;
                for (var s = 0; s < moveStyles.length; s++) {
                    if (osty === baseName(moveStyles[s])) {
                        var ob = other.geometricBounds;
                        // 확장 프레임보다 위에 있는 프레임(같은 스타일의 상단
                        // 발문 등)은 밀지 않는다 — 아래쪽만 이동
                        if (ob[0] <= oldTop + 0.5) { break; }
                        other.geometricBounds = [ob[0] + delta, ob[1], ob[2] + delta, ob[3]];
                        break;
                    }
                }
            } catch (e2) {}
        }
    } catch (e) {}
}

// ── 섹션 아이콘 A~E ─────────────────────────────────────────────────────────
// 베타2 결함 수정: 프레임을 새로 만들면 문서 기본 단락스타일("D 단어 박스
// new" 상속 — 고정행간 16pt)이 붙어 글자가 전량 오버셋되고 사각형으로
// 보인다(원본 아이콘은 원형). 템플릿 워크시트 발문에 이미 있는 원형 아이콘
// (낱자 A~E, [기본 단락], 오버셋 없음)을 글자별로 복제해 앵커한다.

var ICON_LETTERS = ["A", "B", "C", "D", "E"];

// 템플릿 원형 아이콘 은행: 낱자 A~E + [기본 단락] + 오버셋 없음인
// 앵커 프레임을 글자별 1개 수집 (배치 전 1회 스캔)
function buildIconBank(doc) {
    var bank = {};
    var need = 5;
    var stories = doc.stories;
    for (var s = 0; s < stories.length && need > 0; s++) {
        try {
            var st = stories[s];
            if (st.paragraphs.length !== 1) { continue; }
            var t = String(st.contents).replace(/[\s\r﻿￼]+/g, "");
            if (t.length !== 1 || "ABCDE".indexOf(t) === -1) { continue; }
            if (bank[t]) { continue; }
            if (st.paragraphs[0].appliedParagraphStyle.name !== "[기본 단락]") { continue; }
            var tf = st.textContainers[0];
            if (tf.overflows) { continue; }
            bank[t] = tf;
            need--;
        } catch (e) {}
    }
    return bank;
}

function insertSectionIcon(doc, para, sectionIdx, iconBank) {
    var letter = ICON_LETTERS[sectionIdx];
    var src = iconBank ? iconBank[letter] : null;
    if (!src || !src.isValid) {
        throw "템플릿 원형 아이콘(" + letter + ") 없음 — 복제 불가";
    }
    var page = para.parentTextFrames[0].parentPage;
    var tf = null;
    try { tf = src.duplicate(page); } catch (eDup) { tf = src.duplicate(); }
    try {
        // v1 v3: A=pos0, B/C/D/E=pos1 (사용자 수정본 규칙)
        var ipIdx = (sectionIdx === 0) ? 0 : 1;
        var ip = para.insertionPoints[ipIdx];
        tf.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
    } catch (eAnchor) {
        // 앵커 실패 시 페이지 구석에 프레임을 남기지 않는다(위치 이상 방지)
        try { tf.remove(); } catch (eRm) {}
        throw eAnchor;
    }
}

var doc = null;
try {
    wlog("화이트북 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);
    app.scriptPreferences.enableRedraw = false;

    var styleCache = {};
    var missingStyles = {};
    function styleOf(name) {
        if (styleCache[name]) { return styleCache[name]; }
        if (missingStyles[name]) { return null; }
        var ps = findParagraphStyleByPath(doc, name);
        if (ps) { styleCache[name] = ps; return ps; }
        missingStyles[name] = true;
        wlog("[경고] 스타일 없음(자동 생성 안 함): " + name);
        return null;
    }
    var charCache = {};
    function charStyleOf(name) {
        if (charCache[name] !== undefined) { return charCache[name]; }
        var cs = findCharacterStyleByPath(doc, name);
        if (!cs) { wlog("[경고] 문자스타일 없음: " + name); }
        charCache[name] = cs;
        return cs;
    }
    var noneCS = doc.characterStyles[0];
    var csUL = charStyleOf(plan.ul_style || "밑줄");

    // ── 스토리 탐색 (전부 선행 — v1은 배치 전에 모두 탐색) ─────────────────
    var storiesByArea = {};
    var ansStories = [];
    for (var di = 0; di < plan.flows.length; di++) {
        var fl0 = plan.flows[di];
        var fd = fl0.find || {};
        var st0 = [];
        if (fd.first_style) {
            st0 = storiesByFirstStyle(doc, baseName(fd.first_style));
        } else if (fd.answer) {
            st0 = answerStories(doc, baseName(fd.answer.second_style));
            ansStories = st0;
        } else if (fd.practice_main) {
            st0 = practiceMainStories(doc);
        } else if (fd.practice_answer) {
            st0 = practiceAnswerStories(doc, ansStories);
        }
        storiesByArea[fl0.area] = st0;
        wlog("스토리수 " + fl0.area + ": " + st0.length);
    }

    // 섹션 아이콘 은행 (배치 전 1회 — 정답지 아이콘은 템플릿 원형 복제)
    var ICON_BANK = buildIconBank(doc);
    var bankLetters = [];
    for (var bl = 0; bl < ICON_LETTERS.length; bl++) {
        if (ICON_BANK[ICON_LETTERS[bl]]) { bankLetters.push(ICON_LETTERS[bl]); }
    }
    wlog("아이콘 은행: " + bankLetters.join("") +
         (bankLetters.length < 5 ? " [경고] 일부 글자 원형 아이콘 미발견" : ""));

    // ── 주차 텍스트 치환 (v1 issueNum GREP — 마스터 + 본문) ────────────────
    if (plan.week_text) {
        app.doScript(function () {
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = "\\d+주.?차";
            app.changeGrepPreferences.changeTo = plan.week_text;
            for (var mi = 0; mi < doc.masterSpreads.length; mi++) {
                var ms = doc.masterSpreads[mi];
                for (var mp = 0; mp < ms.pages.length; mp++) {
                    var mtfs = ms.pages[mp].textFrames;
                    for (var mt = 0; mt < mtfs.length; mt++) {
                        try { mtfs[mt].parentStory.changeGrep(); } catch (e) {}
                    }
                }
            }
            doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wbwt_v2 주차 치환");
        wlog("주차 텍스트 치환: " + plan.week_text);
    }

    // ── 유닛 배치 (v1 replaceContent + ops) ─────────────────────────────────
    function placeUnit(story, unit, area, idx) {
        var uParas = unit.paras || [];
        if (uParas.length === 0) { return; }
        var texts = [];
        for (var i = 0; i < uParas.length; i++) { texts.push(uParas[i].t); }
        var joined = texts.join("\r");
        // 마지막 단락이 빈 문자열이면 \r 하나로 실체화 (flat↔paras 정렬 보전)
        if (texts.length > 0 && texts[texts.length - 1] === "") {
            joined += "\r";
        }
        story.contents = joined;
        try { story.texts[0].appliedCharacterStyle = noneCS; } catch (e) {}

        var paras = story.paragraphs.everyItem().getElements();
        for (var pi = 0; pi < uParas.length && pi < paras.length; pi++) {
            var ps = styleOf(uParas[pi].s);
            if (ps) { paras[pi].appliedParagraphStyle = ps; }
            var runs = uParas[pi].runs;
            if (runs && runs.length > 0 && csUL) {
                var off = 0;
                for (var ri = 0; ri < runs.length; ri++) {
                    var rl = runs[ri].t ? runs[ri].t.length : 0;
                    if (rl > 0 && runs[ri].ul) {
                        var a = off, b = off + rl - 1;
                        if (a < paras[pi].characters.length &&
                                b < paras[pi].characters.length) {
                            paras[pi].characters.itemByRange(a, b)
                                .appliedCharacterStyle = csUL;
                        }
                    }
                    off += rl;
                }
            }
            if ((pi + 1) % 50 === 0) {
                wlog(area + "[" + idx + "] 스타일: " + (pi + 1) + "/" + uParas.length);
            }
        }

        var ops = unit.ops || {};

        // numberingContinue=false (v1 postProcessAnswerStory)
        var nr = ops.numbering_restart || [];
        for (var ni = 0; ni < nr.length; ni++) {
            if (nr[ni] < paras.length) {
                try { paras[nr[ni]].numberingContinue = false; } catch (e) {}
            }
        }

        // '정답' 문자스타일 (헤더 단락 스캔 — v1 동일)
        if (ops.ans_char) {
            var acs = charStyleOf(ops.ans_char.style);
            if (acs) {
                var hp = ops.ans_char.paras || [];
                for (var hi = 0; hi < hp.length; hi++) {
                    if (hp[hi] >= paras.length) { continue; }
                    var para = paras[hp[hi]];
                    var content = para.contents;
                    for (var c = 0; c < content.length - 1; c++) {
                        if (content.charAt(c) === "정" && content.charAt(c + 1) === "답") {
                            try {
                                para.characters[c].appliedCharacterStyle = acs;
                                para.characters[c + 1].appliedCharacterStyle = acs;
                            } catch (e) {}
                        }
                    }
                }
            }
        }

        // 섹션 아이콘 (v1: numbering/문자스타일 뒤) — 템플릿 원형 복제
        var icons = ops.icons || [];
        var iconOk = 0;
        for (var ii = 0; ii < icons.length; ii++) {
            if (icons[ii].p >= paras.length) { continue; }
            try {
                insertSectionIcon(doc, paras[icons[ii].p], icons[ii].sec, ICON_BANK);
                iconOk++;
            }
            catch (e) { wlog("[경고] " + area + "[" + idx + "] 아이콘 실패: " + e); }
        }

        // 프레임 ops
        if (ops.expand_last) { expandChainLastFrame(story); }

        // 문항-해석 쌍 페이지 분리 방지 (베타2 결함) — keep 옵션은 자동크기
        // 프레임과 맞물려 컴포저 무한루프(UI 정지)를 유발해 금지. 대신
        // 조판 확정 후 갈라진 쌍의 영문 단락만 다음 프레임으로 브레이크
        // (일회성 하드 브레이크 — 루프 불가). expand_last 뒤에 실행해야
        // 마지막 프레임이 늘어난 상태에서 판정한다.
        var pb = ops.pair_break;
        if (pb) {
            var pbEng = pb.eng || [];
            var pbKor = pb.kor || [];
            var pbN = Math.min(pbEng.length, pbKor.length);
            var broke = 0;
            for (var pi2 = 0; pi2 < pbN; pi2++) {
                try {
                    if (pbKor[pi2] >= paras.length) { continue; }
                    var pe = paras[pbEng[pi2]];
                    var pk = paras[pbKor[pi2]];
                    var ef = pe.parentTextFrames;
                    var kf = pk.parentTextFrames;
                    if (ef.length === 0 || kf.length === 0) { continue; }
                    if (ef[ef.length - 1].id !== kf[0].id) {
                        pe.startParagraph = StartParagraph.NEXT_FRAME;
                        broke++;
                    }
                } catch (ePb) {}
            }
            if (broke > 0) {
                wlog(area + "[" + idx + "] 문항-해석 쌍 프레임브레이크: " + broke);
                // 브레이크 후 내용이 늘어난 마지막 프레임 재확장
                if (ops.expand_last) { expandChainLastFrame(story); }
            }
        }
        if (ops.expand_move) { expandFrameAndMoveBelow(story, ops.expand_move); }
        if (ops.ans_frame_fix) {
            try {
                var conts = story.textContainers;
                if (conts.length > 1) {
                    var f1 = conts[1];
                    var gb1 = f1.geometricBounds;
                    f1.geometricBounds = [20, 23, gb1[2], 190];
                    f1.textFramePreferences.autoSizingType = AUTOSIZE_OFF_VAL;
                }
            } catch (e) {}
        }
        return iconOk;
    }

    function processFlow(flow) {
        var stories = storiesByArea[flow.area] || [];
        var units = flow.units || [];
        var placed = 0;
        var iconTotal = 0;
        var n = Math.min(stories.length, units.length);
        for (var u = 0; u < n; u++) {
            if (!units[u] || units[u].skip) { continue; }
            try {
                iconTotal += placeUnit(stories[u], units[u], flow.area, u);
                placed++;
            } catch (e) {
                wlog("[경고] " + flow.area + " 유닛 " + u + " 배치 실패: " + e);
            }
        }
        if (units.length > stories.length) {
            wlog("[경고] " + flow.area + ": 유닛 " +
                 (units.length - stories.length) + "개 스토리 부족");
        }
        wlog("배치완료 " + flow.area + ": " + placed + "유닛 (유닛 " + units.length +
             " / 스토리 " + stories.length + ")");
        if (iconTotal > 0) { wlog("아이콘삽입 " + flow.area + ": " + iconTotal); }
    }

    for (var fi = 0; fi < plan.flows.length; fi++) {
        // 플로우 단위 Undo 그룹화 (개별 undo 트랜잭션 감속 방지 — workbook_v2 실측)
        (function (fl) {
            app.doScript(function () { processFlow(fl); },
                         ScriptLanguage.JAVASCRIPT, undefined,
                         UndoModes.ENTIRE_SCRIPT, "wbwt_v2 " + fl.area);
        })(plan.flows[fi]);
    }

    // 페이스트보드 스트레이 정리 — 템플릿에 남아 있던 페이지 밖(오버셋)
    // 프레임은 프리플라이트 오류만 만들고 인쇄에는 안 나온다 → 제거
    var strayRemoved = 0;
    var allTfs0 = doc.textFrames.everyItem().getElements();
    for (var sr = 0; sr < allTfs0.length; sr++) {
        try {
            if (allTfs0[sr].overflows && allTfs0[sr].parentPage === null) {
                var srTxt = "";
                try {
                    srTxt = String(allTfs0[sr].parentStory.paragraphs[0].contents)
                        .substr(0, 20).replace(/\r/g, "");
                } catch (eS) {}
                allTfs0[sr].remove();
                strayRemoved++;
                wlog("페이스트보드 오버셋 프레임 제거: \"" + srTxt + "...\"");
            }
        } catch (e) {}
    }
    if (strayRemoved > 0) { wlog("페이스트보드 정리: " + strayRemoved + "개 제거"); }

    // 리플로우를 한 번에 확정(keep/자동크기/앵커 삽입 뒤 개별 recompose 반복 방지)
    try { doc.recompose(); } catch (eRc) {}
    wlog("오버플로우 집계 시작");

    // 오버플로우 집계 — v1 파리티: doc.textFrames 순회 (앵커된 아이콘 소형
    // 프레임의 의사 오버플로우 제외 — 앵커 프레임은 doc.textFrames에 없음).
    // 라이브 컬렉션 인덱싱은 위 remove() 후 길이/인덱스가 흔들려 스크립트가
    // 조용히 죽을 수 있다(2026-08-11 실측) → 스냅샷 순회
    var ovf = 0;
    var ovfPages = [];
    var allTfs = doc.textFrames.everyItem().getElements();
    for (var s3 = 0; s3 < allTfs.length; s3++) {
        try {
            if (allTfs[s3].overflows) {
                ovf++;
                var opg = allTfs[s3].parentPage;
                ovfPages.push("P" + (opg ? opg.name : "?"));
            }
        } catch (e) {}
    }
    wlog("오버플로우: " + ovf + "개");
    if (ovfPages.length > 0) { wlog("  페이지: " + ovfPages.join(", ")); }

    doc.save(File(OUT_INDD));
    // PDF: v1 파리티 — [고품질 인쇄] 프리셋 우선
    var preset = app.pdfExportPresets.itemByName("[고품질 인쇄]");
    if (!preset.isValid) { preset = app.pdfExportPresets.itemByName("[High Quality Print]"); }
    if (preset.isValid) {
        doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF), false, preset);
    } else {
        doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    }
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    try { app.scriptPreferences.enableRedraw = true; } catch (e4) {}
    wlog("화이트북 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    try { app.scriptPreferences.enableRedraw = true; } catch (e5) {}
}
