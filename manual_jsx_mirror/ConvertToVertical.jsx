(function() {

    var doc = app.activeDocument;
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    // 주의: enableRedraw=false는 STEP4.5 보존분리 "이후"에 켠다.
    //  redraw를 끄면 스레드 스토리 합성(composition)이 갱신되지 않아 texts[0] 캡처가
    //  비어버려 분리가 깨진다. 느린 STEP5 재배치 직전에만 끈다.

    function getContentFrames(page) {
        var all = page.textFrames.everyItem().getElements();
        var content = [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].geometricBounds[0] > 0) { content.push(all[i]); }
        }
        content.sort(function(a, b) { return a.geometricBounds[0] - b.geometricBounds[0]; });
        return content;
    }

    function getHeaderFrames(page) {
        var all = page.textFrames.everyItem().getElements();
        var headers = [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].geometricBounds[0] <= 0) { headers.push(all[i]); }
        }
        return headers;
    }

    // 페이지 선두 프레임에서 지문번호 추출
    //  - {YYMMQQ} 모의고사 코드 → 뒤 2자리(+선택적 ~NN)
    //  - [NN] / {NN} 짧은 마커 → 그대로
    // 없으면 null. arrange(영작배열)·O/M 그룹 매칭에만 사용.
    function leadPassageNum(pg) {
        var fr = pg.textFrames.everyItem().getElements();
        for (var f = 0; f < fr.length; f++) {
            var c = "";
            try { c = fr[f].contents; } catch (e) {}
            var m6 = c.match(/^\s*\{(\d{4})(\d{2}(?:~\d+)?)\}/);   // {YYMMQQ}
            if (m6) { return m6[2]; }
            var m = c.match(/^\s*[\[{]\s*(\d{1,3}(?:~\d+)?)\s*[\]}]/); // [NN] 또는 {NN}
            if (m) { return m[1]; }
        }
        return null;
    }

    function getPageContentX(pg) {
        // marginPreferences.left = inside (spine) margin = 22 for ALL pages
        // marginPreferences.right = outside margin = 20 for ALL pages
        // LEFT_HAND page: outside margin is on the physical left → use .right
        // RIGHT_HAND page: inside margin is on the physical left → use .left
        return (pg.side === PageSideOptions.LEFT_HAND)
            ? pg.marginPreferences.right
            : pg.marginPreferences.left;
    }

    function movePageWithFix(pg, locOpt, anchor) {
        var oldX = getPageContentX(pg);
        pg.move(locOpt, anchor);
        var newX = getPageContentX(pg);
        var shift = newX - oldX;
        if (Math.abs(shift) > 0.01) {
            var frames = pg.textFrames.everyItem().getElements();
            for (var fi = 0; fi < frames.length; fi++) {
                var fb = frames[fi].geometricBounds;
                if (fb[0] >= 0) {
                    frames[fi].geometricBounds = [fb[0], fb[1] + shift, fb[2], fb[3] + shift];
                }
            }
        }
    }

    function isMasterNone(page) {
        var ms = page.appliedMaster;
        if (!ms) { return true; }
        var n = ms.name;
        return (n === "[없음]" || n === "[None]" || n === "none" || n === "");
    }

    // ======================================================
    // STEP 1: 구분 페이지 탐지 및 삭제
    // none-master 페이지 그룹 중 index > 100 인 것 (앞뒤 표지 제외)
    // ======================================================
    var lastIdx = doc.pages.length - 1;
    var sepGroups = [];
    var inSep = false;
    var sepStart = -1;
    for (var i = 100; i < lastIdx; i++) {
        if (isMasterNone(doc.pages[i])) {
            if (!inSep) { inSep = true; sepStart = i; }
        } else {
            if (inSep) { inSep = false; sepGroups.push([sepStart, i - 1]); }
        }
    }
    if (inSep) { sepGroups.push([sepStart, lastIdx - 1]); }

    if (sepGroups.length < 2) {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
        alert("\uAD6C\uC870 \uC624\uB958: \uAD6C\uBD84 \uD398\uC774\uC9C0 2\uC138\uD2B8\uAC00 \uBD80\uC871\uD569\uB2C8\uB2E4 (" + sepGroups.length + "\uC138\uD2B8 \uBC1C\uACAC)");
        return;
    }

    var sep1 = sepGroups[0];                         // A↔C 경계, e.g. [111, 112]
    var sep2 = sepGroups[1];                         // C↔O/M 경계, e.g. [185, 186]

    // A-master sections: indices 21 ~ sep1[0]-1 = 90p → 5 sections × 18 problems
    var A_SECT_COUNT = sep1[0] - 21;                 // always 90
    var NUM_PROBLEMS = Math.round(A_SECT_COUNT / 5); // always 18

    // C-master sections: between sep1 and sep2
    var C_SIZE = sep2[0] - sep1[1] - 1;             // 64 or 72
    var C_SECT_SIZE = Math.round(C_SIZE / 4);        // 16 or 18

    // After deletion: sep1 removes 2 pages → C starts at sep1[0]
    var C_START = sep1[0];
    var OM_START_AFTER = C_START + C_SIZE;

    // 구분 페이지 삭제 (역순)
    var delPages = [];
    for (var g = sepGroups.length - 1; g >= 0; g--) {
        for (var j = sepGroups[g][1]; j >= sepGroups[g][0]; j--) {
            delPages.push(doc.pages[j]);
        }
    }
    for (var d = 0; d < delPages.length; d++) { delPages[d].remove(); }

    // ======================================================
    // STEP 2: 어휘 페이지 결합 (9쌍, 항상 indices 3-11 / 12-20)
    // ======================================================
    var aMaster = doc.masterSpreads.itemByName("A-\uB9C8\uC2A4\uD130");

    for (var pair = 0; pair < 9; pair++) {
        var pg1 = doc.pages[3 + pair];
        var pg2 = doc.pages[12 + pair];
        var cf1 = getContentFrames(pg1);
        var cf2 = getContentFrames(pg2);
        if (cf1.length < 2 || cf2.length < 2) { continue; }

        var hw1A = cf1[0]; var hw1B = cf1[1];
        var hw2A = cf2[0]; var hw2B = cf2[1];

        // Read ALL bounds before any move/resize
        var b1A = hw1A.geometricBounds;
        var b1B = hw1B.geometricBounds;
        var b2A = hw2A.geometricBounds;
        var b2B = hw2B.geometricBounds;

        var x1 = b1A[1];  // actual left-x of pg1 frames (outer margin for left page, inner for right)
        var x2 = b2B[1];  // actual left-x of pg2 frames

        // hw1A: stays on pg1 at top position (no change)

        // hw2A: move from pg2 → pg1 bottom position
        hw2A.move(pg1);
        hw2A.geometricBounds = [b1B[0], x1, b1B[0] + (b2A[2]-b2A[0]), x1 + (b2A[3]-b2A[1])];

        // hw1B: move from pg1 → pg2 top position
        hw1B.move(pg2);
        hw1B.geometricBounds = [b2A[0], x2, b2A[0] + (b1B[2]-b1B[0]), x2 + (b1B[3]-b1B[1])];

        // hw2B: stays on pg2 at bottom position (no change)

        var hdr1 = getHeaderFrames(pg1);
        var hdr2 = getHeaderFrames(pg2);
        for (var hh = 0; hh < hdr1.length; hh++) { hdr1[hh].remove(); }
        for (var hh = 0; hh < hdr2.length; hh++) { hdr2[hh].remove(); }

        if (aMaster.isValid) { pg2.appliedMaster = aMaster; }
    }

    // ======================================================
    // STEP 3: O/M 섹션 그룹화
    // OM_START_AFTER 이후부터 마지막-1 페이지까지 스캔
    // ======================================================
    var omGroups = [];
    var curGroup = null;
    for (var i = OM_START_AFTER; i < doc.pages.length - 1; i++) {
        var pg = doc.pages[i];
        var frames = pg.textFrames.everyItem().getElements();
        var hasCode = false;
        for (var f = 0; f < frames.length; f++) {
            try {
                if (/^\s*\{[^}]+\}/.test(frames[f].contents)) { hasCode = true; break; }
            } catch(e) {}
        }
        if (hasCode) {
            curGroup = [pg];
            omGroups.push(curGroup);
        } else if (curGroup) {
            curGroup.push(pg);
        }
    }

    // ======================================================
    // STEP 4: 페이지 레이블 설정 (재배치 추적용)
    // ======================================================
    var PFX = "__cv_";

    // 어휘 (9쌍 = 18문제)
    for (var i = 0; i < 9; i++) {
        doc.pages[3 + i].label = PFX + "hw_" + (i * 2);
        doc.pages[12 + i].label = PFX + "hw_" + (i * 2 + 1);
    }

    // A-master 5개 섹션 (각 NUM_PROBLEMS 페이지)
    var aSecNames = ["ox", "title", "content", "insert", "blank"];
    for (var s = 0; s < aSecNames.length; s++) {
        for (var k = 0; k < NUM_PROBLEMS; k++) {
            doc.pages[21 + s * NUM_PROBLEMS + k].label = PFX + aSecNames[s] + "_" + k;
        }
    }

    // C-master 섹션 라벨링
    //  - grammar / grammarox / blankgrammar: 각 NUM_PROBLEMS 페이지 (위치 매칭)
    //  - arrange(영작배열): 나머지 페이지. 지문마다 유무가 달라 가변 크기이므로
    //    선두 지문코드로 그룹화해 canonical 위치(k)에 매칭. 한 지문이 여러 페이지일 수 있음.
    //  (기존: C_SIZE/4 균등 분할 가정 → 하위섹션 크기가 다른 문서에서 arrange가 밀려
    //   "지문 20 블록에 다른 지문 영작배열이 들어오는" 문제 발생. 그 가정을 제거.)
    var cFullSecs = ["grammar", "grammarox", "blankgrammar"];
    for (var s = 0; s < cFullSecs.length; s++) {
        for (var k = 0; k < NUM_PROBLEMS; k++) {
            var cidx = C_START + s * NUM_PROBLEMS + k;
            if (cidx >= 0 && cidx < doc.pages.length) {
                doc.pages[cidx].label = PFX + cFullSecs[s] + "_" + k;
            }
        }
    }

    // canonical 지문번호 순서 (= 재배치 블록 순서).
    //  핵심: 위치 기반 블록 섹션인 grammar_k(=C_START+k)의 코드를 우선 사용한다.
    //   (O/M 그룹 순서는 문서에 따라 누락/역전될 수 있어 신뢰 불가 — 21년6월에서 31 누락 →
    //    arrange/om이 한 칸씩 밀려 "지문37에 38이 들어가는" 문제 발생.)
    //  grammar가 마커 없으면 ox_k(21+k)로, 그래도 불완전하면 O/M 그룹 코드로 폴백.
    var canonNums = [];
    var _nullCount = 0;
    for (var k = 0; k < NUM_PROBLEMS; k++) {
        var bn = null;
        var _gi = C_START + k;                        // grammar_k
        if (_gi >= 0 && _gi < doc.pages.length) { bn = leadPassageNum(doc.pages[_gi]); }
        if (bn === null) {                            // ox_k 폴백
            var _oi = 21 + k;
            if (_oi >= 0 && _oi < doc.pages.length) { bn = leadPassageNum(doc.pages[_oi]); }
        }
        if (bn === null) { _nullCount++; }
        canonNums.push(bn);
    }
    if (_nullCount > NUM_PROBLEMS / 2) {
        // grammar/ox 마커가 거의 없는 문서 → O/M 그룹 코드 순서로 재구성 (기존 방식)
        canonNums = [];
        for (var g0 = 0; g0 < omGroups.length && canonNums.length < NUM_PROBLEMS; g0++) {
            var c0 = _omCode(omGroups[g0]);
            if (c0 !== null) { canonNums.push(c0); }
        }
    } else if (_nullCount > 0) {
        // 일부만 null(예: 41~42 grammar 무코드)일 때 — 통째 폴백하면 31 누락처럼 밀리므로,
        //  grammar 기반은 유지하고 빠진 코드만 arrange/om에서 찾아 null 슬롯에 순서대로 채움.
        var _present = {};
        for (var pi = 0; pi < canonNums.length; pi++) { if (canonNums[pi] !== null) { _present[canonNums[pi]] = true; } }
        var _missing = [];
        function _addMissing(code) {
            if (code === null || _present[code]) { return; }
            for (var x = 0; x < _missing.length; x++) { if (_missing[x] === code) { return; } }
            _missing.push(code);
        }
        var _aS = C_START + 3 * NUM_PROBLEMS, _aE = C_START + C_SIZE - 1;
        for (var mi = _aS; mi <= _aE && mi < doc.pages.length; mi++) { if (mi >= 0) { _addMissing(leadPassageNum(doc.pages[mi])); } }
        for (var mg = 0; mg < omGroups.length; mg++) { _addMissing(_omCode(omGroups[mg])); }
        var _fi = 0;
        for (var fk = 0; fk < canonNums.length; fk++) {
            if (canonNums[fk] === null && _fi < _missing.length) { canonNums[fk] = _missing[_fi]; _fi++; }
        }
    }

    // om 그룹의 지문코드: 첫 페이지가 M-마스터 등 무코드일 수 있으므로 그룹 전체를 스캔.
    function _omCode(grp) {
        for (var gi = 0; gi < grp.length; gi++) {
            var gc = leadPassageNum(grp[gi]);
            if (gc !== null) { return gc; }
        }
        return null;
    }

    // O/M 페이지 라벨: 지문코드로 canon 위치(k)에 매칭 (위치 매칭 아님 — om 순서가 어긋날 수 있음).
    //  - 코드가 canon에 있으면 그 위치 k에 배치.
    //  - 코드가 아예 없는 그룹(예: 41~42 om이 무코드)은 비어있는 canon 위치에 문서순서대로 배정.
    //  - 코드는 있으나 canon에 없는 그룹(짤지문 18/19/25.. 등)은 미배치(고유키).
    function _labelOm(grp, key) {
        for (var p = 0; p < grp.length; p++) { grp[p].label = PFX + "om_" + key + "_" + p; }
    }
    var _omUsed = {};
    var _omNoCode = [];
    for (var g = 0; g < omGroups.length; g++) {
        var omCode = _omCode(omGroups[g]);
        var omK = -1;
        if (omCode !== null) {
            for (var ci0 = 0; ci0 < canonNums.length; ci0++) {
                if (canonNums[ci0] === omCode) { omK = ci0; break; }
            }
        }
        if (omK >= 0 && !_omUsed[omK]) {
            _omUsed[omK] = true;
            _labelOm(omGroups[g], "" + omK);
        } else if (omCode === null) {
            _omNoCode.push(g);                 // 코드 없음 → 빈 위치 배정 보류
        } else {
            _labelOm(omGroups[g], "u" + g);    // 짤지문 등 → 미배치
        }
    }
    var _uk = 0;
    for (var ui = 0; ui < _omNoCode.length; ui++) {
        while (_uk < NUM_PROBLEMS && _omUsed[_uk]) { _uk++; }
        var _gg = _omNoCode[ui];
        if (_uk < NUM_PROBLEMS) {
            _omUsed[_uk] = true;
            _labelOm(omGroups[_gg], "" + _uk);
        } else {
            _labelOm(omGroups[_gg], "u" + _gg);
        }
    }

    // arrange: C_START + 3*NUM_PROBLEMS .. C_START + C_SIZE - 1
    //  선두 코드가 있으면 새 그룹 시작 → 해당 코드의 canon 위치(k)에 매칭,
    //  코드 없는 페이지는 직전 그룹(같은 지문)에 이어붙임(arrange_k_seq).
    var arrStart = C_START + 3 * NUM_PROBLEMS;
    var arrEnd = C_START + C_SIZE - 1;
    var arrK = -1;
    var arrSeq = 0;
    for (var ai = arrStart; ai <= arrEnd && ai < doc.pages.length; ai++) {
        if (ai < 0) { continue; }
        var anum = leadPassageNum(doc.pages[ai]);
        if (anum !== null) {
            var kk = -1;
            for (var ci = 0; ci < canonNums.length; ci++) {
                if (canonNums[ci] === anum) { kk = ci; break; }
            }
            arrK = kk; arrSeq = 0;
        }
        if (arrK >= 0) {
            doc.pages[ai].label = PFX + "arrange_" + arrK + "_" + arrSeq;
            arrSeq++;
        }
    }

    function buildLabelMap() {
        var map = {};
        for (var i = 0; i < doc.pages.length; i++) {
            var lbl = doc.pages[i].label;
            if (lbl && lbl.indexOf(PFX) === 0) { map[lbl] = doc.pages[i]; }
        }
        return map;
    }

    // ======================================================
    // STEP 4.5: 연결된 스토리를 "내용 보존 분리" (재배치 이전에 수행)
    //  세로버전은 서로 다른 범위(예: 20번+23번)를 조합하므로 지문이 이어져 있으면 안 됨.
    //  대상: 페이지에 놓인 모든 교차-지문 스레드 스토리 — 어휘/내용/어법/영작배열뿐 아니라
    //   O-마스터 "실전문제"까지(지문을 가로질러 한 스토리로 연결됨). 마스터 스프레드 프레임은 제외.
    //  중요1: 재배치(pg.move)에서 연결 스토리 텍스트가 첫 지문으로 몰리므로 반드시 "이동 전"에 분리.
    //  중요2: 단순 nextTextFrame=null은 텍스트를 첫 프레임으로 몰아 붕괴 → 각 프레임의 표시 텍스트를
    //   서식 유지한 채 독립 프레임으로 복제 후 원본 제거.
    //  중요3: 분리는 enableRedraw ON 상태에서 해야 texts[0] 합성이 유효(redraw는 STEP5 직전에 끈다).
    // ======================================================
    (function () {
        function _onPage(cont) {
            try { return cont.parentPage ? true : false; } catch (e) { return false; }
        }
        function _splitAll() {
            try { app.scriptPreferences.enableRedraw = false; } catch (e) {}  // 속도 (문서는 이미 합성된 상태라 recompose 불필요)
            var stories = doc.stories.everyItem().getElements();
            for (var si = 0; si < stories.length; si++) {
                var conts;
                try { conts = stories[si].textContainers; } catch (e) { continue; }
                if (!conts || conts.length < 2) { continue; }   // 스레드 아닌 것은 그대로
                if (!_onPage(conts[0])) { continue; }            // 마스터/페이스트보드 스토리 제외
                var caps = [];
                for (var ci = 0; ci < conts.length; ci++) {
                    var c = conts[ci];
                    var cap = { frame: c, pg: null, gb: null, len: 0, os: null, tfp: null, lyr: null };
                    try { cap.pg = c.parentPage; } catch (e) {}
                    try { cap.gb = c.geometricBounds; } catch (e) {}
                    try { cap.len = c.texts[0].contents.length; } catch (e) {}
                    try { cap.os = c.appliedObjectStyle; } catch (e) {}
                    try { cap.tfp = c.textFramePreferences.properties; } catch (e) {}
                    try { cap.lyr = c.itemLayer; } catch (e) {}
                    caps.push(cap);
                }
                for (var ci = 0; ci < caps.length; ci++) {
                    var cp = caps[ci];
                    if (!cp.pg) { continue; }   // 페이지에 없는(앵커 등) 프레임은 유지
                    var nf = cp.pg.textFrames.add();
                    try { if (cp.lyr) nf.itemLayer = cp.lyr; } catch (e) {}
                    try { nf.geometricBounds = cp.gb; } catch (e) {}
                    try { if (cp.os) nf.appliedObjectStyle = cp.os; } catch (e) {}
                    try { if (cp.tfp) nf.textFramePreferences.properties = cp.tfp; } catch (e) {}
                    if (cp.len > 0) {
                        try { cp.frame.texts[0].duplicate(LocationOptions.AT_END, nf.insertionPoints[0]); } catch (e) {}
                    }
                }
                for (var ci = 0; ci < caps.length; ci++) {
                    if (!caps[ci].pg) { continue; }   // 페이지 프레임만 제거(앵커 보존)
                    try { caps[ci].frame.remove(); } catch (e) {}
                }
            }
        }
        // 대량 프레임 작업이라 FAST_ENTIRE_SCRIPT로 undo 기록을 생략해 가속(실패 시 직접 호출).
        //  종료 후 doc 참조가 무효화될 수 있어 아래에서 재취득한다.
        try {
            app.doScript(_splitAll, ScriptLanguage.JAVASCRIPT, undefined,
                UndoModes.FAST_ENTIRE_SCRIPT, "스토리 보존 분리");
        } catch (e) {
            _splitAll();
        }
    })();
    // 대량 프레임 추가/삭제 후 doc 참조가 stale 될 수 있어 재취득
    try { doc = app.activeDocument; } catch (e) {}

    // 분리가 끝났으니 이제 redraw를 꺼서 재배치 속도 확보 (5분 → 수십초)
    try { app.scriptPreferences.enableRedraw = false; } catch (e) {}

    // ======================================================
    // STEP 5: 페이지 재배치
    // 세로(C) 구조: 각 문제마다 [hw, ox, title, content, insert, blank,
    //                             grammar, grammarox, blankgrammar, arrange, om...]
    // ======================================================
    var insertAnchor = doc.pages[2];
    var locAfter = LocationOptions.AFTER;

    for (var k = 0; k < NUM_PROBLEMS; k++) {
        var lmap = buildLabelMap();
        var pages_k = [];
        pages_k.push(lmap[PFX + "hw_" + k]);
        pages_k.push(lmap[PFX + "ox_" + k]);
        pages_k.push(lmap[PFX + "title_" + k]);
        pages_k.push(lmap[PFX + "content_" + k]);
        pages_k.push(lmap[PFX + "insert_" + k]);
        pages_k.push(lmap[PFX + "blank_" + k]);
        pages_k.push(lmap[PFX + "grammar_" + k]);
        pages_k.push(lmap[PFX + "grammarox_" + k]);
        pages_k.push(lmap[PFX + "blankgrammar_" + k]);
        // arrange(영작배열)은 한 지문에 여러 페이지일 수 있음
        for (var aseq = 0; aseq < 30; aseq++) {
            var apg = lmap[PFX + "arrange_" + k + "_" + aseq];
            if (apg && apg.isValid) { pages_k.push(apg); } else { break; }
        }

        // om(실전문제)도 코드 매칭으로 om_<k>_<p> 라벨이 붙음 → 끝까지 수집
        for (var op = 0; op < 40; op++) {
            var omPage = lmap[PFX + "om_" + k + "_" + op];
            if (omPage && omPage.isValid) { pages_k.push(omPage); } else { break; }
        }

        // Forward-order insertion: each page placed AFTER the previous page.
        for (var j = 0; j < pages_k.length; j++) {
            var pg = pages_k[j];
            if (pg && pg.isValid) {
                pg.move(locAfter, insertAnchor);
                insertAnchor = pg;
            }
        }
    }

    // ======================================================
    // STEP 6.5: 프레임 x위치 보정
    // 원본: L페이지 x=20, R페이지 x=22. 목표: 복원
    // pg.move() 이후 InDesign 자동보정 결과:
    //   L: x≈22 → 20 (-2)
    //   R: x≈24 → 22 (-2), x≈20 → 22 (+2)
    // ======================================================
    for (var i = 0; i < doc.pages.length; i++) {
        var pg6 = doc.pages[i];
        var isL6 = (pg6.side === PageSideOptions.LEFT_HAND);
        var frames6 = pg6.textFrames.everyItem().getElements();
        for (var f6 = 0; f6 < frames6.length; f6++) {
            try {
                var fb6 = frames6[f6].geometricBounds;
                if (fb6[0] <= 0) { continue; }
                var x6 = fb6[1];
                var shift6 = 0;
                if (isL6  && x6 > 21.4 && x6 < 22.6) { shift6 = -2; }
                else if (!isL6 && x6 > 23.4 && x6 < 24.6) { shift6 = -2; }
                else if (!isL6 && x6 > 19.4 && x6 < 20.6) { shift6 =  2; }
                if (shift6 !== 0) {
                    frames6[f6].geometricBounds = [fb6[0], fb6[1]+shift6, fb6[2], fb6[3]+shift6];
                }
            } catch(e) {}
        }
    }

    // ======================================================
    // STEP 7 / STEP 8: (STEP 5 재배치 "이전"으로 이동됨 — _splitCMasterStories)
    //  재배치 과정에서 연결된 스토리 텍스트가 첫 지문으로 몰리므로,
    //  반드시 이동 전에 "내용 보존 분리"를 끝낸다. 자세한 내용은 STEP 5 위쪽 참조.
    // ======================================================

    // ======================================================
    // STEP 6: 레이블 정리 (STEP 8 이후로 이동됨)
    // ======================================================
    for (var i = 0; i < doc.pages.length; i++) {
        if (doc.pages[i].label && doc.pages[i].label.indexOf(PFX) === 0) {
            doc.pages[i].label = "";
        }
    }

    // ======================================================
    // STEP 9: STEP1.ai → STEP123.ai 링크 변경
    // ======================================================
    var step123File = new File("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\uB0B4 \uB4DC\uB77C\uC774\uBE0C/\uCF58\uD150\uCE20 \uAD00\uB9AC/\uB0B4\uC2E0\uB300\uBE44/\uC778\uB514\uC790\uC778 \uD30C\uC77C/\uC774\uBBF8\uC9C0/\uC6CC\uD06C\uBD81/C\uBC84\uC804/STEP123.ai");
    if (step123File.exists) {
        for (var lk = doc.links.length - 1; lk >= 0; lk--) {
            try {
                if (doc.links[lk].name === "STEP1.ai") {
                    doc.links[lk].relink(step123File);
                    doc.links[lk].update();
                }
            } catch(e) {}
        }
    }

    // ======================================================
    // STEP 10: Master 원본 열기 + 마스터/스타일 동기화
    // ======================================================
    var masterFile = new File("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\uB0B4 \uB4DC\uB77C\uC774\uBE0C/\uCF58\uD150\uCE20 \uAD00\uB9AC/\uB0B4\uC2E0\uB300\uBE44/\uC778\uB514\uC790\uC778 \uD30C\uC77C/\uC6CC\uD06C\uBD81/\uBAA8\uC758\uACE0\uC0AC/\uB0B4\uC9C0/[\uC6D0\uBCF8]\uC6CC\uD06C\uBD81_C\uC138\uB85C(\uBAA8\uC758\uACE0\uC0AC)_\uB0B4\uC9C0.indd");
    if (masterFile.exists) {
        var sourceDoc = app.open(masterFile);
        // MASTER_SOURCE 라벨 설정 (없을 경우만)
        if (sourceDoc.extractLabel("MASTER_SOURCE") !== "YES") {
            sourceDoc.insertLabel("MASTER_SOURCE", "YES");
        }

        // 대상 문서(변환된 파일)에 마스터/스타일 동기화
        try {
            _unlockEverything(sourceDoc);
            _unlockEverything(doc);
            _syncLayers(sourceDoc, doc);
            _finalPhysicalSync(sourceDoc, doc);
            _syncStyles(sourceDoc, doc);
            _applyCMasterExceptFirst(doc);
            _applyGanjiToFirstPage(doc);
            _remapGanjiCharacterStyles(doc);
            _setFirstPageItemsYToZero(doc);
            _relinkSpecialImages(doc);
        } catch(e) {}

        // 원본 닫기 (저장 안 함)
        sourceDoc.close(SaveOptions.NO);
    }

    try { app.scriptPreferences.enableRedraw = true; } catch (e) {}
    // \uBCF4\uC874 \uBD84\uB9AC\uB85C \uB9CC\uB4E0 \uB3C5\uB9BD \uD504\uB808\uC784\uC774 redraw=false \uB3D9\uC548 \uBBF8\uD569\uC131 \uC0C1\uD0DC\uC77C \uC218 \uC788\uC5B4 \uAC15\uC81C \uC7AC\uD569\uC131
    try { doc.recompose(); } catch (e) {}
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
    alert("\uBCC0\uD658 \uC644\uB8CC! \uD398\uC774\uC9C0 \uC218: " + doc.pages.length);

    // ======================================================
    // Master 동기화 헬퍼 함수들
    // ======================================================
    function _unlockEverything(d) {
        try { d.layers.everyItem().locked = false; } catch(e) {}
        try { d.layers.everyItem().visible = true; } catch(e) {}
        try { d.masterSpreads.everyItem().pageItems.everyItem().locked = false; } catch(e) {}
    }

    function _syncLayers(src, tgt) {
        for (var i = src.layers.length - 1; i >= 0; i--) {
            if (!tgt.layers.itemByName(src.layers[i].name).isValid) {
                tgt.layers.add({name: src.layers[i].name});
            }
        }
    }

    function _finalPhysicalSync(src, tgt) {
        var appliedBackup = [];
        for (var i = 0; i < tgt.pages.length; i++) {
            try {
                appliedBackup[i] = tgt.pages[i].appliedMaster
                    ? tgt.pages[i].appliedMaster.name : null;
            } catch(e) { appliedBackup[i] = null; }
        }
        try { tgt.loadMasters(src.fullName); } catch(e) { return; }

        var sourceNameMap = {};
        for (var s = 0; s < src.masterSpreads.length; s++) {
            var sM = src.masterSpreads[s];
            if (sM.name === "[None]" || sM.name === "[\uC5C6\uC74C]") continue;
            sourceNameMap[sM.name] = true;
        }
        for (var p = 0; p < tgt.pages.length; p++) {
            var oldName = appliedBackup[p];
            try {
                if (!oldName) {
                    tgt.pages[p].appliedMaster = NothingEnum.NOTHING;
                } else if (sourceNameMap[oldName]) {
                    var restored = tgt.masterSpreads.itemByName(oldName);
                    if (restored && restored.isValid) {
                        tgt.pages[p].appliedMaster = restored;
                    } else { tgt.pages[p].appliedMaster = NothingEnum.NOTHING; }
                } else { tgt.pages[p].appliedMaster = NothingEnum.NOTHING; }
            } catch(e) {}
        }
        for (var i = tgt.masterSpreads.length - 1; i >= 0; i--) {
            var m = tgt.masterSpreads[i];
            if (m.name === "[None]" || m.name === "[\uC5C6\uC74C]") continue;
            if (sourceNameMap[m.name]) continue;
            try { m.remove(); } catch(e) {}
        }
    }

    function _syncStyles(src, tgt) {
        try {
            tgt.importStyles(ImportFormat.PARAGRAPH_STYLES_FORMAT,
                src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
        } catch(e) {}
        try {
            tgt.importStyles(ImportFormat.CHARACTER_STYLES_FORMAT,
                src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
        } catch(e) {}
    }

    function _applyCMasterExceptFirst(d) {
        var cMaster = null;
        for (var i = 0; i < d.masterSpreads.length; i++) {
            if (/^C($|[\- _])/i.test(d.masterSpreads[i].name)) {
                cMaster = d.masterSpreads[i]; break;
            }
        }
        if (!cMaster) return;
        for (var p = 1; p < d.pages.length; p++) {
            try { d.pages[p].appliedMaster = cMaster; } catch(e) {}
        }
    }

    function _applyGanjiToFirstPage(d) {
        if (d.pages.length === 0) return;
        var firstPage = d.pages[0];
        var items = firstPage.pageItems.everyItem().getElements();
        for (var i = items.length - 1; i >= 0; i--) {
            try {
                var item = items[i];
                var keep = false;
                if (!(item instanceof TextFrame)) { item.remove(); continue; }
                if (item.texts.length > 0) {
                    var chars = item.texts[0].characters;
                    for (var c = 0; c < chars.length; c++) {
                        try {
                            var cs = chars[c].appliedCharacterStyle;
                            if (cs.parent && cs.parent.constructor.name === "CharacterStyleGroup"
                                && cs.parent.name === "\uAC04\uC9C0") { keep = true; break; }
                        } catch(e) {}
                    }
                }
                if (!keep) item.remove();
            } catch(e) {}
        }
        var ganjiMaster = null;
        for (var m = 0; m < d.masterSpreads.length; m++) {
            if (d.masterSpreads[m].name === "\uAC04\uC9C0-\uB9C8\uC2A4\uD130") {
                ganjiMaster = d.masterSpreads[m]; break;
            }
        }
        if (ganjiMaster) {
            try { firstPage.appliedMaster = ganjiMaster; } catch(e) {}
        }
    }

    function _remapGanjiCharacterStyles(d) {
        function getCS(gn, sn) {
            try {
                var grp = d.characterStyleGroups.itemByName(gn);
                if (!grp.isValid) return null;
                var st = grp.characterStyles.itemByName(sn);
                return st.isValid ? st : null;
            } catch(e) { return null; }
        }
        function replace(fromS, toS) {
            app.findTextPreferences = NothingEnum.NOTHING;
            app.changeTextPreferences = NothingEnum.NOTHING;
            app.findTextPreferences.appliedCharacterStyle = fromS;
            app.changeTextPreferences.appliedCharacterStyle = toS;
            try { d.changeText(); } catch(e) {}
            app.findTextPreferences = NothingEnum.NOTHING;
            app.changeTextPreferences = NothingEnum.NOTHING;
        }
        var f1 = getCS("\uAC04\uC9C0", "\uCE74\uD14C\uACE0\uB9AC");
        var t1 = getCS("\uAC04\uC9C0", "\uBC94\uC704");
        if (f1 && t1) replace(f1, t1);
        var f2 = getCS("\uAC04\uC9C0", "\uBD80\uC81C\uBAA9");
        var t2 = getCS("\uAC04\uC9C0", "\uBC94\uC704_\uCD94\uAC00\uB0B4\uC6A9");
        if (f2 && t2) replace(f2, t2);
    }

    function _setFirstPageItemsYToZero(d) {
        if (d.pages.length === 0) return;
        var p = d.pages[0];
        var items = p.pageItems.everyItem().getElements();
        for (var i = 0; i < items.length; i++) {
            try {
                try { items[i].locked = false; } catch(e) {}
                var gb = items[i].geometricBounds;
                if (!gb || gb.length !== 4) continue;
                var h = gb[2] - gb[0];
                items[i].geometricBounds = [0 - h, gb[1], 0, gb[3]];
            } catch(e) {}
        }
    }

    function _relinkSpecialImages(d) {
        var baseFolder = Folder("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\uB0B4 \uB4DC\uB77C\uC774\uBE0C/\uCF58\uD150\uCE20 \uAD00\uB9AC/\uB0B4\uC2E0\uB300\uBE44/\uC778\uB514\uC790\uC778 \uD30C\uC77C/\uC774\uBBF8\uC9C0/\uC6CC\uD06C\uBD81/C\uBC84\uC804");
        if (!baseFolder.exists) return;
        var allFiles = [];
        var stack = [baseFolder];
        while (stack.length > 0) {
            var cur = stack.pop();
            var items = cur.getFiles();
            for (var s = 0; s < items.length; s++) {
                if (items[s] instanceof Folder) stack.push(items[s]);
                else if (items[s] instanceof File) allFiles.push(items[s]);
            }
        }
        function normName(name) {
            var n = name;
            n = n.replace("(B)", "");
            n = n.replace(/^간지_/, "");
            n = n.replace(/간지(?=\.[^.]+$)/, "");
            n = n.replace(/^마지막P(?=\.[^.]+$)/, "LastP");
            return n;
        }
        var links = d.links;
        for (var i = 0; i < links.length; i++) {
            var lk = links[i];
            var origName = lk.name;
            var tgtName = normName(origName);
            for (var f = 0; f < allFiles.length; f++) {
                if (allFiles[f].name === origName || normName(allFiles[f].name) === tgtName) {
                    try { lk.relink(allFiles[f]); lk.update(); } catch(e) {}
                    break;
                }
            }
        }
    }

})();
