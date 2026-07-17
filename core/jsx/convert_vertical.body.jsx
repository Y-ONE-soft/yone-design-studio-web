// 워크북 전체(C) → 세로버전 변환 실행기 (W27) — 수동 ConvertToVertical.jsx
// (manual_jsx_mirror, 2026-06-17 최신본) 웹 이식. lib.jsxinc concat 전제.
//
// 변환 의미론: 전체(C)는 "섹션별" 구성 (모든 지문의 어휘 → 모든 지문의 본문OX
// → ... ), 세로(C)는 "지문별" 구성 (지문 1개의 전 섹션 사이클 → 다음 지문).
// 이 스크립트는 전체(C)의 페이지를 라벨링해 지문 단위 사이클로 재배치하고,
// 세로 마스터 원본의 마스터/스타일을 동기화한다.
//
// 수동본과의 차이 (파리티 유지 + 웹 안전화):
//   - activeDocument 대신 자기 사본(app.open showingWindow=false)만 연다 —
//     사용자 열린 문서 무접촉. doc 재취득도 activeDocument가 아니라
//     documents.itemByName (사용자 문서 오염 방지).
//   - 하드코딩 구조 상수 외부화: front_pages(3) / sep_scan_start(100) /
//     margin_outside(20)·margin_inside(22). NUM_PROBLEMS(18)·A_SECT_COUNT(90)·
//     9쌍 어휘결합·21(A섹션 시작)은 전부 sep1 위치에서 유도한다:
//       NUM_PROBLEMS = (sep1[0] - front_pages) / 6
//       (구조: 어휘 NUM + A섹션 5*NUM = 6*NUM 페이지가 front 뒤에 옴)
//     수동본 공식 A_SECT_COUNT=sep1[0]-21, NUM=A/5 와 표준 문서(sep1=111)에서
//     동치. 6으로 나눠떨어지지 않으면 [오류]로 중단 (침묵 오배치 방지).
//   - GDrive 개인 경로(STEP123.ai / 세로 마스터 / 이미지 폴더) 설정 외부화 —
//     엔진이 마스터는 로컬 사본으로 전달.
//   - alert 제거, wlog 진행 로그 + 결과 JSON(result_json) 기록.
//   - 저장 + PDF export(정규화 — 사용자 UI 잔존 설정 상속 차단) 추가.
//
// ExtendScript ES3 — let/const/화살표/템플릿 리터럴 금지.

var CFG_PATH = "__CFG_PATH__";

function readJSONFile(path) {
    var f = new File(path);
    f.encoding = "UTF-8";
    if (!f.open("r")) { throw "설정 파일 open 실패: " + path; }
    var s = f.read();
    f.close();
    return eval("(" + s + ")");
}

// ── 프레임 분류 (수동본 동일) ────────────────────────────────────────────────
function getContentFrames(page) {
    var all = page.textFrames.everyItem().getElements();
    var content = [];
    for (var i = 0; i < all.length; i++) {
        if (all[i].geometricBounds[0] > 0) { content.push(all[i]); }
    }
    content.sort(function (a, b) { return a.geometricBounds[0] - b.geometricBounds[0]; });
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

// 페이지 선두 프레임에서 지문번호 추출 (수동본 동일)
//  - {YYMMQQ} 모의고사 코드 → 뒤 2자리(+선택적 ~NN)
//  - [NN] / {NN} 짧은 마커 → 그대로
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

function isMasterNone(page) {
    var ms = page.appliedMaster;
    if (!ms) { return true; }
    var n = ms.name;
    return (n === "[없음]" || n === "[None]" || n === "none" || n === "");
}

// ── STEP10 마스터/스타일 동기화 헬퍼 (수동본 동일) ──────────────────────────
function _unlockEverything(d) {
    try { d.layers.everyItem().locked = false; } catch (e) {}
    try { d.layers.everyItem().visible = true; } catch (e) {}
    try { d.masterSpreads.everyItem().pageItems.everyItem().locked = false; } catch (e) {}
}

function _syncLayers(src, tgt) {
    for (var i = src.layers.length - 1; i >= 0; i--) {
        if (!tgt.layers.itemByName(src.layers[i].name).isValid) {
            tgt.layers.add({ name: src.layers[i].name });
        }
    }
}

function _finalPhysicalSync(src, tgt) {
    var appliedBackup = [];
    for (var i = 0; i < tgt.pages.length; i++) {
        try {
            appliedBackup[i] = tgt.pages[i].appliedMaster
                ? tgt.pages[i].appliedMaster.name : null;
        } catch (e) { appliedBackup[i] = null; }
    }
    try { tgt.loadMasters(src.fullName); } catch (e) { return; }

    var sourceNameMap = {};
    for (var s = 0; s < src.masterSpreads.length; s++) {
        var sM = src.masterSpreads[s];
        if (sM.name === "[None]" || sM.name === "[없음]") { continue; }
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
        } catch (e) {}
    }
    for (var mi = tgt.masterSpreads.length - 1; mi >= 0; mi--) {
        var m = tgt.masterSpreads[mi];
        if (m.name === "[None]" || m.name === "[없음]") { continue; }
        if (sourceNameMap[m.name]) { continue; }
        try { m.remove(); } catch (e) {}
    }
}

function _syncStyles(src, tgt) {
    try {
        tgt.importStyles(ImportFormat.PARAGRAPH_STYLES_FORMAT,
            src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
    } catch (e) {}
    try {
        tgt.importStyles(ImportFormat.CHARACTER_STYLES_FORMAT,
            src.fullName, GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE);
    } catch (e) {}
}

function _applyCMasterExceptFirst(d) {
    var cMaster = null;
    for (var i = 0; i < d.masterSpreads.length; i++) {
        if (/^C($|[\- _])/i.test(d.masterSpreads[i].name)) {
            cMaster = d.masterSpreads[i]; break;
        }
    }
    if (!cMaster) { return; }
    for (var p = 1; p < d.pages.length; p++) {
        try { d.pages[p].appliedMaster = cMaster; } catch (e) {}
    }
}

function _applyGanjiToFirstPage(d) {
    if (d.pages.length === 0) { return; }
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
                            && cs.parent.name === "간지") { keep = true; break; }
                    } catch (e) {}
                }
            }
            if (!keep) { item.remove(); }
        } catch (e) {}
    }
    var ganjiMaster = null;
    for (var m = 0; m < d.masterSpreads.length; m++) {
        if (d.masterSpreads[m].name === "간지-마스터") {
            ganjiMaster = d.masterSpreads[m]; break;
        }
    }
    if (ganjiMaster) {
        try { firstPage.appliedMaster = ganjiMaster; } catch (e) {}
    }
}

function _remapGanjiCharacterStyles(d) {
    function getCS(gn, sn) {
        try {
            var grp = d.characterStyleGroups.itemByName(gn);
            if (!grp.isValid) { return null; }
            var st = grp.characterStyles.itemByName(sn);
            return st.isValid ? st : null;
        } catch (e) { return null; }
    }
    function replaceCS(fromS, toS) {
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findTextPreferences.appliedCharacterStyle = fromS;
        app.changeTextPreferences.appliedCharacterStyle = toS;
        try { d.changeText(); } catch (e) {}
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
    }
    var f1 = getCS("간지", "카테고리");
    var t1 = getCS("간지", "범위");
    if (f1 && t1) { replaceCS(f1, t1); }
    var f2 = getCS("간지", "부제목");
    var t2 = getCS("간지", "범위_추가내용");
    if (f2 && t2) { replaceCS(f2, t2); }
}

function _setFirstPageItemsYToZero(d) {
    if (d.pages.length === 0) { return; }
    var p = d.pages[0];
    var items = p.pageItems.everyItem().getElements();
    for (var i = 0; i < items.length; i++) {
        try {
            try { items[i].locked = false; } catch (e) {}
            var gb = items[i].geometricBounds;
            if (!gb || gb.length !== 4) { continue; }
            var h = gb[2] - gb[0];
            items[i].geometricBounds = [0 - h, gb[1], 0, gb[3]];
        } catch (e) {}
    }
}

function _relinkSpecialImages(d, imageBase) {
    if (!imageBase) { return; }
    var baseFolder = Folder(imageBase);
    if (!baseFolder.exists) {
        wlog("[경고] 이미지 폴더 없음 — 특수 이미지 재링크 생략: " + imageBase);
        return;
    }
    var allFiles = [];
    var stack = [baseFolder];
    while (stack.length > 0) {
        var cur = stack.pop();
        var items = cur.getFiles();
        for (var s = 0; s < items.length; s++) {
            if (items[s] instanceof Folder) { stack.push(items[s]); }
            else if (items[s] instanceof File) { allFiles.push(items[s]); }
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
    var relinked = 0;
    for (var i = 0; i < links.length; i++) {
        var lk = links[i];
        var origName = lk.name;
        var tgtName = normName(origName);
        for (var f = 0; f < allFiles.length; f++) {
            if (allFiles[f].name === origName || normName(allFiles[f].name) === tgtName) {
                try { lk.relink(allFiles[f]); lk.update(); relinked++; } catch (e) {}
                break;
            }
        }
    }
    wlog("특수 이미지 재링크: " + relinked + "건");
}

// ── 메인 ────────────────────────────────────────────────────────────────────
var doc = null;
var __uilPrev = null;
try {
    wlog("세로 변환 시작 (설정: " + CFG_PATH + ")");
    var cfg = readJSONFile(CFG_PATH);   // 부트스트랩 실패도 로그에 남김 (감사 패턴)
    var DOC_PATH = cfg.doc_path;
    var OUT_INDD = cfg.out_indd;
    var OUT_PDF = cfg.out_pdf;
    var FRONT = (cfg.front_pages !== undefined) ? cfg.front_pages : 3;
    var SEP_SCAN_START = (cfg.sep_scan_start !== undefined) ? cfg.sep_scan_start : 100;
    var M_OUT = (cfg.margin_outside !== undefined) ? cfg.margin_outside : 20;
    var M_IN = (cfg.margin_inside !== undefined) ? cfg.margin_inside : 22;
    var M_SHIFT = M_IN - M_OUT;   // 표준 템플릿 2

    try { __uilPrev = app.scriptPreferences.userInteractionLevel; } catch (e) {}
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    // 주의: enableRedraw=false는 STEP4.5 보존분리 "이후"에 켠다 (수동본 교훈 —
    //  redraw를 끄면 스레드 스토리 합성이 갱신되지 않아 texts[0] 캡처가 비어버림).

    wlog("문서 열기: " + DOC_PATH + " (대형 문서 수 분 가능)");
    doc = app.open(File(DOC_PATH), false);
    var __docName = doc.name;
    wlog("페이지 " + doc.pages.length + "개, 스토리 " + doc.stories.length + "개");

    var result = { pages_before: doc.pages.length };

    // ==================================================
    // STEP 1: 구분 페이지 탐지 및 삭제
    // none-master 페이지 그룹 중 index > SEP_SCAN_START (앞뒤 표지 제외)
    // ==================================================
    var lastIdx = doc.pages.length - 1;
    var sepGroups = [];
    var inSep = false;
    var sepStart = -1;
    for (var i = SEP_SCAN_START; i < lastIdx; i++) {
        if (isMasterNone(doc.pages[i])) {
            if (!inSep) { inSep = true; sepStart = i; }
        } else {
            if (inSep) { inSep = false; sepGroups.push([sepStart, i - 1]); }
        }
    }
    if (inSep) { sepGroups.push([sepStart, lastIdx - 1]); }

    if (sepGroups.length < 2) {
        throw "구조 오류: 구분 페이지 2세트가 부족합니다 (" + sepGroups.length + "세트 발견)";
    }

    var sep1 = sepGroups[0];                         // A↔C 경계 (표준: [111, 112])
    var sep2 = sepGroups[1];                         // C↔O/M 경계

    // 구조 상수 유도 (수동본 하드코딩 21/90/18/9쌍의 외부화):
    //  front 뒤 = 어휘 NUM_PROBLEMS 페이지 + A섹션 5*NUM_PROBLEMS 페이지
    if ((sep1[0] - FRONT) % 6 !== 0) {
        throw "구조 오류: sep1=" + sep1[0] + ", front=" + FRONT +
              " — (sep1-front)가 6의 배수가 아님 (표준 전체(C) 구조 아님)";
    }
    var NUM_PROBLEMS = (sep1[0] - FRONT) / 6;        // 표준: 18
    var A_START = FRONT + NUM_PROBLEMS;              // 표준: 21
    var A_SECT_COUNT = 5 * NUM_PROBLEMS;             // 표준: 90 (수동본 sep1[0]-21과 동치)
    if (NUM_PROBLEMS % 2 !== 0) {
        throw "구조 오류: NUM_PROBLEMS=" + NUM_PROBLEMS + " — 어휘 페이지 결합(2쪽→1쌍) 불가";
    }
    var HW_PAIRS = NUM_PROBLEMS / 2;                 // 표준: 9

    // C-master sections: between sep1 and sep2
    var C_SIZE = sep2[0] - sep1[1] - 1;              // 표준: 64 or 72

    // After deletion: sep1 removes 2 pages → C starts at sep1[0]
    var C_START = sep1[0];
    var OM_START_AFTER = C_START + C_SIZE;

    wlog("STEP1: sep1=[" + sep1 + "] sep2=[" + sep2 + "] → 문제 " + NUM_PROBLEMS +
         "개, A섹션 " + A_SECT_COUNT + "p, C구간 " + C_SIZE + "p" +
         (NUM_PROBLEMS !== 18 ? " ([경고] 표준 18문제 아님 — 파리티 미검증 구조)" : ""));
    if (NUM_PROBLEMS !== 18) {
        wlog("[경고] NUM_PROBLEMS=" + NUM_PROBLEMS + " — 수동본은 18문제 문서만 검증됨");
    }
    result.sep1 = sep1; result.sep2 = sep2;
    result.num_problems = NUM_PROBLEMS;
    result.a_sect_count = A_SECT_COUNT;
    result.c_size = C_SIZE;
    result.sep_groups = sepGroups.length;

    // 구분 페이지 삭제 (역순 — 수동본 동일: 모든 sep 그룹 삭제)
    var delPages = [];
    for (var g = sepGroups.length - 1; g >= 0; g--) {
        for (var j = sepGroups[g][1]; j >= sepGroups[g][0]; j--) {
            delPages.push(doc.pages[j]);
        }
    }
    for (var d0 = 0; d0 < delPages.length; d0++) { delPages[d0].remove(); }
    wlog("STEP1: 구분 페이지 " + delPages.length + "개 삭제");
    result.sep_pages_deleted = delPages.length;

    // ==================================================
    // STEP 2: 어휘 페이지 결합 (HW_PAIRS쌍 — 표준 9쌍, indices FRONT..)
    // ==================================================
    var aMaster = doc.masterSpreads.itemByName("A-마스터");

    for (var pair = 0; pair < HW_PAIRS; pair++) {
        var pg1 = doc.pages[FRONT + pair];
        var pg2 = doc.pages[FRONT + HW_PAIRS + pair];
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

        var x1 = b1A[1];
        var x2 = b2B[1];

        // hw1A: stays on pg1 top / hw2A: pg2 → pg1 bottom
        hw2A.move(pg1);
        hw2A.geometricBounds = [b1B[0], x1, b1B[0] + (b2A[2] - b2A[0]), x1 + (b2A[3] - b2A[1])];

        // hw1B: pg1 → pg2 top / hw2B: stays pg2 bottom
        hw1B.move(pg2);
        hw1B.geometricBounds = [b2A[0], x2, b2A[0] + (b1B[2] - b1B[0]), x2 + (b1B[3] - b1B[1])];

        var hdr1 = getHeaderFrames(pg1);
        var hdr2 = getHeaderFrames(pg2);
        for (var h1 = 0; h1 < hdr1.length; h1++) { hdr1[h1].remove(); }
        for (var h2 = 0; h2 < hdr2.length; h2++) { hdr2[h2].remove(); }

        if (aMaster.isValid) { pg2.appliedMaster = aMaster; }
    }
    wlog("STEP2: 어휘 페이지 " + HW_PAIRS + "쌍 결합");

    // ==================================================
    // STEP 3: O/M 섹션 그룹화 (OM_START_AFTER 이후 ~ 마지막-1)
    // ==================================================
    var omGroups = [];
    var curGroup = null;
    for (var oi = OM_START_AFTER; oi < doc.pages.length - 1; oi++) {
        var opg = doc.pages[oi];
        var oframes = opg.textFrames.everyItem().getElements();
        var hasCode = false;
        for (var of = 0; of < oframes.length; of++) {
            try {
                if (/^\s*\{[^}]+\}/.test(oframes[of].contents)) { hasCode = true; break; }
            } catch (e) {}
        }
        if (hasCode) {
            curGroup = [opg];
            omGroups.push(curGroup);
        } else if (curGroup) {
            curGroup.push(opg);
        }
    }
    wlog("STEP3: O/M 그룹 " + omGroups.length + "개");
    result.om_groups = omGroups.length;

    // om 그룹의 지문코드: 그룹 전체 스캔 (첫 페이지가 M-마스터 등 무코드 가능)
    function _omCode(grp) {
        for (var gi = 0; gi < grp.length; gi++) {
            var gc = leadPassageNum(grp[gi]);
            if (gc !== null) { return gc; }
        }
        return null;
    }

    // ==================================================
    // STEP 4: 페이지 레이블 설정 (재배치 추적용)
    // ==================================================
    var PFX = "__cv_";

    // 어휘 (HW_PAIRS쌍 = NUM_PROBLEMS문제)
    for (var hi = 0; hi < HW_PAIRS; hi++) {
        doc.pages[FRONT + hi].label = PFX + "hw_" + (hi * 2);
        doc.pages[FRONT + HW_PAIRS + hi].label = PFX + "hw_" + (hi * 2 + 1);
    }

    // A-master 5개 섹션 (각 NUM_PROBLEMS 페이지)
    var aSecNames = ["ox", "title", "content", "insert", "blank"];
    for (var s = 0; s < aSecNames.length; s++) {
        for (var k = 0; k < NUM_PROBLEMS; k++) {
            doc.pages[A_START + s * NUM_PROBLEMS + k].label = PFX + aSecNames[s] + "_" + k;
        }
    }

    // C-master 위치 기반 3개 풀섹션 (arrange는 코드 매칭 — 수동본 06-17 개선 동일)
    var cFullSecs = ["grammar", "grammarox", "blankgrammar"];
    for (var cs = 0; cs < cFullSecs.length; cs++) {
        for (var ck = 0; ck < NUM_PROBLEMS; ck++) {
            var cidx = C_START + cs * NUM_PROBLEMS + ck;
            if (cidx >= 0 && cidx < doc.pages.length) {
                doc.pages[cidx].label = PFX + cFullSecs[cs] + "_" + ck;
            }
        }
    }

    // canonical 지문번호 순서 — grammar_k 코드 우선, ox_k 폴백, 과반 null이면
    // O/M 그룹 순서 폴백, 일부 null이면 arrange/om에서 빠진 코드만 채움
    var canonNums = [];
    var _nullCount = 0;
    for (var ck2 = 0; ck2 < NUM_PROBLEMS; ck2++) {
        var bn = null;
        var _gi2 = C_START + ck2;                     // grammar_k
        if (_gi2 >= 0 && _gi2 < doc.pages.length) { bn = leadPassageNum(doc.pages[_gi2]); }
        if (bn === null) {                            // ox_k 폴백
            var _oi2 = A_START + ck2;
            if (_oi2 >= 0 && _oi2 < doc.pages.length) { bn = leadPassageNum(doc.pages[_oi2]); }
        }
        if (bn === null) { _nullCount++; }
        canonNums.push(bn);
    }
    if (_nullCount > NUM_PROBLEMS / 2) {
        wlog("[경고] grammar/ox 마커 과반 없음 (" + _nullCount + "/" + NUM_PROBLEMS +
             ") — O/M 그룹 코드 순서 폴백");
        canonNums = [];
        for (var g0 = 0; g0 < omGroups.length && canonNums.length < NUM_PROBLEMS; g0++) {
            var c0 = _omCode(omGroups[g0]);
            if (c0 !== null) { canonNums.push(c0); }
        }
    } else if (_nullCount > 0) {
        var _present = {};
        for (var pi = 0; pi < canonNums.length; pi++) {
            if (canonNums[pi] !== null) { _present[canonNums[pi]] = true; }
        }
        var _missing = [];
        function _addMissing(code) {
            if (code === null || _present[code]) { return; }
            for (var x = 0; x < _missing.length; x++) { if (_missing[x] === code) { return; } }
            _missing.push(code);
        }
        var _aS = C_START + 3 * NUM_PROBLEMS, _aE = C_START + C_SIZE - 1;
        for (var mi2 = _aS; mi2 <= _aE && mi2 < doc.pages.length; mi2++) {
            if (mi2 >= 0) { _addMissing(leadPassageNum(doc.pages[mi2])); }
        }
        for (var mg = 0; mg < omGroups.length; mg++) { _addMissing(_omCode(omGroups[mg])); }
        var _fi = 0;
        for (var fk = 0; fk < canonNums.length; fk++) {
            if (canonNums[fk] === null && _fi < _missing.length) {
                canonNums[fk] = _missing[_fi]; _fi++;
            }
        }
    }
    wlog("STEP4: canonical 지문 순서 [" + canonNums.join(",") + "]");
    result.canon = canonNums;

    // O/M 페이지 라벨: 코드로 canon 위치(k)에 매칭
    function _labelOm(grp, key) {
        for (var p = 0; p < grp.length; p++) { grp[p].label = PFX + "om_" + key + "_" + p; }
    }
    var _omUsed = {};
    var _omNoCode = [];
    var _omUnmatched = 0;
    for (var og = 0; og < omGroups.length; og++) {
        var omCode = _omCode(omGroups[og]);
        var omK = -1;
        if (omCode !== null) {
            for (var ci0 = 0; ci0 < canonNums.length; ci0++) {
                if (canonNums[ci0] === omCode) { omK = ci0; break; }
            }
        }
        if (omK >= 0 && !_omUsed[omK]) {
            _omUsed[omK] = true;
            _labelOm(omGroups[og], "" + omK);
        } else if (omCode === null) {
            _omNoCode.push(og);                 // 코드 없음 → 빈 위치 배정 보류
        } else {
            _labelOm(omGroups[og], "u" + og);   // 짤지문 등 → 미배치
            _omUnmatched++;
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
            _omUnmatched++;
        }
    }
    result.om_unmatched = _omUnmatched;
    if (_omUnmatched > 0) {
        wlog("O/M 미배치 그룹 " + _omUnmatched + "개 (짤지문 등 — canon 외 코드, 원위치 유지)");
    }

    // arrange(영작배열): 선두 코드로 그룹화해 canon 위치 매칭 (가변 크기)
    var arrStart = C_START + 3 * NUM_PROBLEMS;
    var arrEnd = C_START + C_SIZE - 1;
    var arrK = -1;
    var arrSeq = 0;
    var arrLabeled = 0;
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
            arrLabeled++;
        }
    }
    wlog("STEP4: arrange " + arrLabeled + "p 라벨링");
    result.arrange_pages = arrLabeled;

    function buildLabelMap() {
        var map = {};
        for (var bi = 0; bi < doc.pages.length; bi++) {
            var lbl = doc.pages[bi].label;
            if (lbl && lbl.indexOf(PFX) === 0) { map[lbl] = doc.pages[bi]; }
        }
        return map;
    }

    // ==================================================
    // STEP 4.5: 연결된 스토리 "내용 보존 분리" (재배치 이전 — 수동본 동일)
    //  재배치(pg.move)에서 연결 스토리 텍스트가 첫 지문으로 몰리므로 이동 전에
    //  각 프레임의 표시 텍스트를 서식 유지한 채 독립 프레임으로 복제 후 원본 제거.
    // ==================================================
    var _splitCount = 0;
    (function () {
        function _onPage(cont) {
            try { return cont.parentPage ? true : false; } catch (e) { return false; }
        }
        function _splitAll() {
            try { app.scriptPreferences.enableRedraw = false; } catch (e) {}
            var stories = doc.stories.everyItem().getElements();
            wlog("STEP4.5: 스토리 보존 분리 시작 (" + stories.length + "개 스캔)");
            for (var si = 0; si < stories.length; si++) {
                if (si % 50 === 0) {
                    wlog("STEP4.5 진행: " + si + "/" + stories.length);
                }
                var conts;
                try { conts = stories[si].textContainers; } catch (e) { continue; }
                if (!conts || conts.length < 2) { continue; }
                if (!_onPage(conts[0])) { continue; }
                var caps = [];
                for (var ci2 = 0; ci2 < conts.length; ci2++) {
                    var c = conts[ci2];
                    var cap = { frame: c, pg: null, gb: null, len: 0, os: null, tfp: null, lyr: null };
                    try { cap.pg = c.parentPage; } catch (e) {}
                    try { cap.gb = c.geometricBounds; } catch (e) {}
                    try { cap.len = c.texts[0].contents.length; } catch (e) {}
                    try { cap.os = c.appliedObjectStyle; } catch (e) {}
                    try { cap.tfp = c.textFramePreferences.properties; } catch (e) {}
                    try { cap.lyr = c.itemLayer; } catch (e) {}
                    caps.push(cap);
                }
                for (var ci3 = 0; ci3 < caps.length; ci3++) {
                    var cp = caps[ci3];
                    if (!cp.pg) { continue; }
                    var nf = cp.pg.textFrames.add();
                    try { if (cp.lyr) { nf.itemLayer = cp.lyr; } } catch (e) {}
                    try { nf.geometricBounds = cp.gb; } catch (e) {}
                    try { if (cp.os) { nf.appliedObjectStyle = cp.os; } } catch (e) {}
                    try { if (cp.tfp) { nf.textFramePreferences.properties = cp.tfp; } } catch (e) {}
                    if (cp.len > 0) {
                        try { cp.frame.texts[0].duplicate(LocationOptions.AT_END, nf.insertionPoints[0]); } catch (e) {}
                    }
                }
                for (var ci4 = 0; ci4 < caps.length; ci4++) {
                    if (!caps[ci4].pg) { continue; }
                    try { caps[ci4].frame.remove(); } catch (e) {}
                }
                _splitCount++;
            }
        }
        try {
            app.doScript(_splitAll, ScriptLanguage.JAVASCRIPT, undefined,
                UndoModes.FAST_ENTIRE_SCRIPT, "스토리 보존 분리");
        } catch (e) {
            _splitAll();
        }
    })();
    // 대량 프레임 추가/삭제 후 doc 참조 stale 가능 — 자기 문서명으로 재취득
    // (수동본은 activeDocument — 웹에선 사용자 문서 오염 위험이라 이름 재취득)
    try {
        var _re = app.documents.itemByName(__docName);
        if (_re.isValid) { doc = _re; }
    } catch (e) {}
    wlog("STEP4.5: 스레드 스토리 " + _splitCount + "개 분리 완료");
    result.split_stories = _splitCount;

    // 분리가 끝났으니 redraw를 꺼서 재배치 속도 확보
    try { app.scriptPreferences.enableRedraw = false; } catch (e) {}

    // ==================================================
    // STEP 5: 페이지 재배치 — 문제별 사이클
    //  [hw, ox, title, content, insert, blank, grammar, grammarox,
    //   blankgrammar, arrange..., om...]
    // ==================================================
    var insertAnchor = doc.pages[FRONT - 1];
    var locAfter = LocationOptions.AFTER;

    for (var k5 = 0; k5 < NUM_PROBLEMS; k5++) {
        var lmap = buildLabelMap();
        var pages_k = [];
        pages_k.push(lmap[PFX + "hw_" + k5]);
        pages_k.push(lmap[PFX + "ox_" + k5]);
        pages_k.push(lmap[PFX + "title_" + k5]);
        pages_k.push(lmap[PFX + "content_" + k5]);
        pages_k.push(lmap[PFX + "insert_" + k5]);
        pages_k.push(lmap[PFX + "blank_" + k5]);
        pages_k.push(lmap[PFX + "grammar_" + k5]);
        pages_k.push(lmap[PFX + "grammarox_" + k5]);
        pages_k.push(lmap[PFX + "blankgrammar_" + k5]);
        for (var aseq = 0; aseq < 30; aseq++) {
            var apg = lmap[PFX + "arrange_" + k5 + "_" + aseq];
            if (apg && apg.isValid) { pages_k.push(apg); } else { break; }
        }
        for (var op = 0; op < 40; op++) {
            var omPage = lmap[PFX + "om_" + k5 + "_" + op];
            if (omPage && omPage.isValid) { pages_k.push(omPage); } else { break; }
        }

        for (var j5 = 0; j5 < pages_k.length; j5++) {
            var pg5 = pages_k[j5];
            if (pg5 && pg5.isValid) {
                pg5.move(locAfter, insertAnchor);
                insertAnchor = pg5;
            }
        }
        wlog("STEP5: 문제 " + (k5 + 1) + "/" + NUM_PROBLEMS +
             " (" + (canonNums[k5] !== null ? canonNums[k5] : "?") + "번) — " +
             pages_k.length + "p 재배치");
    }

    // ==================================================
    // STEP 6.5: 프레임 x위치 보정 (L: out / R: in 마진 복원 — 수동본 동일)
    // ==================================================
    for (var p6 = 0; p6 < doc.pages.length; p6++) {
        var pg6 = doc.pages[p6];
        var isL6 = (pg6.side === PageSideOptions.LEFT_HAND);
        var frames6 = pg6.textFrames.everyItem().getElements();
        for (var f6 = 0; f6 < frames6.length; f6++) {
            try {
                var fb6 = frames6[f6].geometricBounds;
                if (fb6[0] <= 0) { continue; }
                var x6 = fb6[1];
                var shift6 = 0;
                if (isL6 && x6 > M_IN - 0.6 && x6 < M_IN + 0.6) { shift6 = -M_SHIFT; }
                else if (!isL6 && x6 > M_IN + M_SHIFT - 0.6 && x6 < M_IN + M_SHIFT + 0.6) { shift6 = -M_SHIFT; }
                else if (!isL6 && x6 > M_OUT - 0.6 && x6 < M_OUT + 0.6) { shift6 = M_SHIFT; }
                if (shift6 !== 0) {
                    frames6[f6].geometricBounds = [fb6[0], fb6[1] + shift6, fb6[2], fb6[3] + shift6];
                }
            } catch (e) {}
        }
    }
    wlog("STEP6.5: 프레임 x위치 보정 완료");

    // ==================================================
    // STEP 6: 레이블 정리
    // ==================================================
    for (var l6 = 0; l6 < doc.pages.length; l6++) {
        if (doc.pages[l6].label && doc.pages[l6].label.indexOf(PFX) === 0) {
            doc.pages[l6].label = "";
        }
    }

    // ==================================================
    // STEP 9: STEP1.ai → STEP123.ai 링크 변경 (경로 설정 외부화)
    // ==================================================
    if (cfg.step123_ai) {
        var step123File = new File(cfg.step123_ai);
        if (step123File.exists) {
            var relinked9 = 0;
            for (var lk = doc.links.length - 1; lk >= 0; lk--) {
                try {
                    if (doc.links[lk].name === "STEP1.ai") {
                        doc.links[lk].relink(step123File);
                        doc.links[lk].update();
                        relinked9++;
                    }
                } catch (e) {}
            }
            wlog("STEP9: STEP1.ai → STEP123.ai 재링크 " + relinked9 + "건");
        } else {
            wlog("[경고] STEP123.ai 없음 — 링크 변경 생략: " + cfg.step123_ai);
        }
    }

    // ==================================================
    // STEP 10: 세로 마스터 원본 열기 + 마스터/스타일 동기화 + 간지 처리
    // ==================================================
    if (cfg.master_indd) {
        var masterFile = new File(cfg.master_indd);
        if (masterFile.exists) {
            wlog("STEP10: 세로 마스터 열기 — " + cfg.master_indd);
            var sourceDoc = app.open(masterFile, false);
            if (sourceDoc.extractLabel("MASTER_SOURCE") !== "YES") {
                sourceDoc.insertLabel("MASTER_SOURCE", "YES");
            }
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
                _relinkSpecialImages(doc, cfg.image_base);
                wlog("STEP10: 마스터/스타일 동기화 + 간지 처리 완료");
            } catch (e10) {
                wlog("[경고] STEP10 동기화 중 오류 (계속 진행): " + e10);
            }
            sourceDoc.close(SaveOptions.NO);
        } else {
            wlog("[경고] 세로 마스터 원본 없음 — STEP10 생략: " + cfg.master_indd);
        }
    } else {
        wlog("[경고] master_indd 미설정 — STEP10 생략");
    }

    try { app.scriptPreferences.enableRedraw = true; } catch (e) {}
    // 보존 분리로 만든 독립 프레임이 redraw=false 동안 미합성일 수 있어 강제 재합성
    try { doc.recompose(); } catch (e) {}

    // ── 오버플로우 집계 + 저장/Export ────────────────────────────────────────
    var ovf = 0;
    var _sts = doc.stories.everyItem().getElements();
    for (var s5 = 0; s5 < _sts.length; s5++) {
        try {
            var tc5 = _sts[s5].textContainers;
            if (tc5.length > 0 && tc5[tc5.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("오버플로우 스토리: " + ovf + "개");
    result.overflow_stories = ovf;
    result.pages_after = doc.pages.length;

    if (cfg.result_json) {
        try { writeJSON(cfg.result_json, result); } catch (eRJ) {
            wlog("[경고] 결과 JSON 기록 실패: " + eRJ);
        }
    }

    wlog("문서 저장 시작 (대형 문서 로그 무갱신 수 분 가능)");
    doc.save(File(OUT_INDD));
    if (OUT_PDF) {
        // 스크립트 export가 사용자 UI 잔존 설정을 상속하는 문제 → 직전 정규화 필수
        try {
            app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;
            app.pdfExportPreferences.exportAsSinglePages = false;
            app.pdfExportPreferences.viewPDF = false;
        } catch (ePref) {}
        wlog("PDF export 시작 (대형 문서는 로그 무갱신 20분+ 가능)");
        doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
        wlog("PDF: 성공 -> " + OUT_PDF);
    }
    doc.close(SaveOptions.NO);
    doc = null;
    try {
        if (__uilPrev !== null) { app.scriptPreferences.userInteractionLevel = __uilPrev; }
        else { app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL; }
    } catch (e) {}
    wlog("세로 변환 완료 — 페이지 " + result.pages_after + "개");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    try { app.scriptPreferences.enableRedraw = true; } catch (e3) {}
    try { app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL; } catch (e4) {}
}
