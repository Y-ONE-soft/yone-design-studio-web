// STEP3_AutoLayout.jsx v2
// RTF 워크북 전용 — 선택된 텍스트 프레임 스토리에 STEP3 단락 스타일 적용
// 사용법: 조판할 텍스트 프레임 선택 후 실행
// ExtendScript ES3 — Adobe InDesign

(function () {

    var doc = app.activeDocument;

    // ── 선택 확인 ─────────────────────────────────
    if (!app.selection || app.selection.length === 0) {
        alert("텍스트 프레임을 선택한 뒤 실행하세요.");
        exit();
    }
    var story;
    try { story = app.selection[0].parentStory; } catch (e) { story = null; }
    if (!story || !story.isValid) {
        alert("텍스트 스토리를 찾을 수 없습니다.\n텍스트 프레임을 선택해주세요.");
        exit();
    }

    // ════════════════════════════════════════════
    // 스타일 조회 유틸
    // ════════════════════════════════════════════
    function normStr(s) {
        return String(s).replace(/[\u3000\s]+/g,"").replace(/[_\-()\[\]{}]/g,"").toLowerCase();
    }
    function getAllGroupsUnder(root, out) {
        try {
            var subs = root.paragraphStyleGroups.everyItem().getElements();
            for (var i = 0; i < subs.length; i++)
                if (subs[i] && subs[i].isValid) { out.push(subs[i]); getAllGroupsUnder(subs[i], out); }
        } catch(e) {}
    }
    function getAllStylesIn(g, bucket) {
        try {
            var ss = g.paragraphStyles.everyItem().getElements();
            for (var i = 0; i < ss.length; i++) if (ss[i] && ss[i].isValid) bucket.push(ss[i]);
        } catch(e) {}
        try {
            var sg = g.paragraphStyleGroups.everyItem().getElements();
            for (var i = 0; i < sg.length; i++) if (sg[i] && sg[i].isValid) getAllStylesIn(sg[i], bucket);
        } catch(e) {}
    }

    // STEP 그룹 자동 감지 (28페이지+ 스캔)
    var ANALYZE_FROM = 28;
    var detectedGroup = null;
    var styleUsage = {};
    (function () {
        var aFrom = ANALYZE_FROM - 1;
        for (var pi = aFrom; pi < doc.pages.length && !detectedGroup; pi++) {
            try {
                var frames = doc.pages[pi].textFrames;
                for (var fi = 0; fi < frames.length && !detectedGroup; fi++) {
                    try {
                        var paras = frames[fi].paragraphs;
                        for (var i = 0; i < paras.length; i++) {
                            try {
                                var ps = paras[i].appliedParagraphStyle;
                                var sn = ps.name;
                                styleUsage[sn] = (styleUsage[sn] || 0) + 1;
                                if (!detectedGroup) {
                                    var par = ps.parent;
                                    while (par && par.isValid && par !== doc) {
                                        if (/step/i.test(par.name)) { detectedGroup = par.name; break; }
                                        par = par.parent;
                                    }
                                }
                            } catch(e) {}
                        }
                    } catch(e) {}
                }
            } catch(e) {}
        }
    })();
    var GROUP_NAME = detectedGroup || "STEP 03";

    function getStyle(sName) {
        // 그룹 탐색
        var tops;
        try { tops = doc.paragraphStyleGroups.everyItem().getElements(); } catch(e) { tops = []; }
        var allGroups = [];
        for (var t = 0; t < tops.length; t++) if (tops[t] && tops[t].isValid) getAllGroupsUnder(tops[t], allGroups);
        var g = null;
        var target = normStr(GROUP_NAME);
        for (var gi = 0; gi < allGroups.length; gi++) {
            if (allGroups[gi] && allGroups[gi].isValid && normStr(allGroups[gi].name) === target) { g = allGroups[gi]; break; }
        }
        for (var t2 = 0; t2 < tops.length && !g; t2++) {
            if (tops[t2] && tops[t2].isValid && normStr(tops[t2].name) === target) g = tops[t2];
        }
        if (!g) {
            var gnames = [];
            for (var t3 = 0; t3 < tops.length; t3++) if (tops[t3] && tops[t3].isValid) gnames.push(tops[t3].name);
            alert("스타일 그룹 '" + GROUP_NAME + "'을 찾을 수 없습니다.\n최상위 그룹: " + gnames.join(", "));
            exit();
        }
        try { var ex = g.paragraphStyles.itemByName(sName); if (ex && ex.isValid) return ex; } catch(e) {}
        var cands = [sName, /^S_/.test(sName) ? sName.replace(/^S_/,"") : "S_"+sName];
        var all = [];
        getAllStylesIn(g, all);
        var map = {};
        for (var i = 0; i < all.length; i++) map[normStr(all[i].name)] = all[i];
        for (var c = 0; c < cands.length; c++) {
            if (map.hasOwnProperty(normStr(cands[c]))) return map[normStr(cands[c])];
        }
        var names = [];
        for (var t = 0; t < all.length; t++) if (all[t] && all[t].isValid) names.push(all[t].name);
        alert("단락 스타일 '" + sName + "'을 찾을 수 없습니다.\n그룹: " + GROUP_NAME + "\n목록: " + names.join(", "));
        exit();
    }

    // 그룹 내에서 스타일 조회, 없으면 생성
    function getOrCreateStyle(sName) {
        var tops;
        try { tops = doc.paragraphStyleGroups.everyItem().getElements(); } catch(e) { tops = []; }
        var allGroups = [];
        for (var t = 0; t < tops.length; t++) if (tops[t] && tops[t].isValid) getAllGroupsUnder(tops[t], allGroups);
        var g = null;
        var target = normStr(GROUP_NAME);
        for (var gi = 0; gi < allGroups.length; gi++) {
            if (allGroups[gi] && allGroups[gi].isValid && normStr(allGroups[gi].name) === target) { g = allGroups[gi]; break; }
        }
        for (var t2 = 0; t2 < tops.length && !g; t2++) {
            if (tops[t2] && tops[t2].isValid && normStr(tops[t2].name) === target) g = tops[t2];
        }
        if (!g) return null;
        try { var ex = g.paragraphStyles.itemByName(sName); if (ex && ex.isValid) return ex; } catch(e) {}
        try { return g.paragraphStyles.add({ name: sName }); } catch(e) { return null; }
    }

    var sNum     = getStyle("S_실전문제 번호 수정 올림포스");
    var sChoices = getStyle("S_선지 올림포스");
    var sIntro   = getStyle("다음 글을 읽고");
    var sAst     = getStyle("영단어");
    var sBg      = getStyle("배경 올림포스");
    var sDef     = getStyle("실전 문제 지문 올림포스_");
    var sCond    = getStyle("조건 올림포스");
    var sView    = getStyle("보기 올림포스");
    var sTbl     = getOrCreateStyle("표 본문 올림포스");   // 표 셀 전용 (없으면 자동 생성)

    // ════════════════════════════════════════════
    // 빈 단락 삭제 (스타일 보존) 헬퍼
    // ════════════════════════════════════════════
    function nextNonEmptyStyle(ps, fromIdx) {
        for (var j = fromIdx + 1; j < ps.length; j++) {
            try {
                var c = (ps[j].contents || "").replace(/\r$/, "");
                if (!/^\s*$/.test(c)) return ps[j].appliedParagraphStyle;
            } catch(e) {}
        }
        return null;
    }

    function deleteEmptyParas(st) {
        var deleted = 0;
        for (var pass = 0; pass < 10; pass++) {
            var ps = st.paragraphs.everyItem().getElements();
            var n = ps.length;
            var toDelete = [];
            for (var i = n - 2; i >= 0; i--) {
                try {
                    var content = (ps[i].contents || "").replace(/\r$/, "");
                    if (!/^\s*$/.test(content)) continue;
                    var ns = nextNonEmptyStyle(ps, i);
                    toDelete.push({ idx: i, style: ns });
                } catch(e) {}
            }
            if (toDelete.length === 0) break;
            for (var di = 0; di < toDelete.length; di++) {
                try {
                    var item = toDelete[di];
                    var p = st.paragraphs[item.idx];
                    if (!p || !p.isValid) continue;
                    var c2 = (p.contents || "").replace(/\r$/, "");
                    if (!/^\s*$/.test(c2)) continue;
                    var chars = p.characters;
                    if (!chars || chars.length === 0) continue;
                    st.characters.itemByRange(
                        chars[0].index,
                        chars[chars.length - 1].index
                    ).remove();
                    if (item.style) {
                        try { st.paragraphs[item.idx].appliedParagraphStyle = item.style; } catch(e) {}
                    }
                    deleted++;
                } catch(e) {}
            }
        }
        return deleted;
    }

    // ════════════════════════════════════════════
    // GREP 헬퍼 (스토리 단위)
    // ════════════════════════════════════════════
    function grep(st, find, change) {
        var fb = app.findGrepPreferences.properties;
        var cb = app.changeGrepPreferences.properties;
        app.findGrepPreferences  = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat  = find;
        app.changeGrepPreferences.changeTo = change;
        try { st.changeGrep(); } catch(e) {}
        app.findGrepPreferences  = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        try { app.findGrepPreferences.properties  = fb; } catch(e) {}
        try { app.changeGrepPreferences.properties = cb; } catch(e) {}
    }

    // ════════════════════════════════════════════
    // "단원" 문자스타일 제거 (단락스타일 무력화 방지)
    // ════════════════════════════════════════════
    (function () {
        var danwon = null;
        try {
            var grps = doc.characterStyleGroups.everyItem().getElements();
            for (var g = 0; g < grps.length && !danwon; g++) {
                // 중첩 그룹까지 재귀 탐색
                function findInGroup(grp) {
                    if (danwon) return;
                    var ss = grp.characterStyles.everyItem().getElements();
                    for (var s = 0; s < ss.length; s++) {
                        if (ss[s].name === "단원") { danwon = ss[s]; return; }
                    }
                    try {
                        var sub = grp.characterStyleGroups.everyItem().getElements();
                        for (var sg = 0; sg < sub.length; sg++) findInGroup(sub[sg]);
                    } catch(e) {}
                }
                findInGroup(grps[g]);
            }
        } catch(e) {}
        if (!danwon) return;

        var fb = app.findGrepPreferences.properties, cb = app.changeGrepPreferences.properties;
        app.findGrepPreferences  = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.appliedCharacterStyle = danwon;
        app.findGrepPreferences.findWhat = ".+";
        app.changeGrepPreferences.appliedCharacterStyle = doc.characterStyles[0]; // [없음]
        try { story.changeGrep(); } catch(e) {}
        // \r (단락기호)에 남은 danwon도 제거
        app.findGrepPreferences  = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.appliedCharacterStyle = danwon;
        app.findGrepPreferences.findWhat = "\\r";
        app.changeGrepPreferences.appliedCharacterStyle = doc.characterStyles[0];
        try { story.changeGrep(); } catch(e) {}
        app.findGrepPreferences  = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        try { app.findGrepPreferences.properties  = fb; } catch(e) {}
        try { app.changeGrepPreferences.properties = cb; } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // 밑줄 보존 (임시 문자 스타일 마킹)
    // ════════════════════════════════════════════
    var UL_NM = "_ul_step3al_";
    var ulStyle = null;
    try {
        ulStyle = doc.characterStyles.itemByName(UL_NM);
        if (!ulStyle || !ulStyle.isValid) throw 0;
    } catch(e) {
        ulStyle = doc.characterStyles.add({ name: UL_NM, underline: true });
    }
    (function() {
        var fb = app.findGrepPreferences.properties, cb = app.changeGrepPreferences.properties;
        app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.underline = true;
        app.findGrepPreferences.findWhat = ".+";
        app.changeGrepPreferences.appliedCharacterStyle = ulStyle;
        try { story.changeGrep(); } catch(e) {}
        app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING;
        try { app.findGrepPreferences.properties = fb; } catch(e) {}
        try { app.changeGrepPreferences.properties = cb; } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // [N] 지문 번호 단락 삭제 (헬퍼 없이 직접 호출)
    // ════════════════════════════════════════════
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat   = "^\\[\\d+\\][ \\t]*\\r";
    app.changeGrepPreferences.changeTo = "";
    try { story.changeGrep(); } catch(e) {}
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;

    // ════════════════════════════════════════════
    // 텍스트 전처리
    // ════════════════════════════════════════════
    // [보기]/[조건] → <보기>/<조건> 변환
    grep(story, "\\[\\s*보기\\s*\\]", "<보기>");
    grep(story, "\\[\\s*조건\\s*\\]", "<조건>");

    // ════════════════════════════════════════════
    // 단락 스타일 분류 (1회 순회)
    // ════════════════════════════════════════════
    // 전체를 배열로 한 번에 읽기 (DOM 접근 최소화)
    var paras = story.paragraphs.everyItem().getElements();
    var total = paras.length;

    // 각 단락 내용 일괄 수집
    var texts = [];
    for (var i = 0; i < total; i++) {
        try { texts.push((paras[i].contents || "").replace(/[\r\n]+$/, "")); }
        catch(e) { texts.push(""); }
    }

    // 1단계: 전체 기본 스타일 적용
    for (var i = 0; i < total; i++) {
        try { paras[i].appliedParagraphStyle = sDef; } catch(e) {}
    }

    // 2단계: 분류 상태 배열 (나중에 한꺼번에 적용)
    var styles = [];
    for (var i = 0; i < total; i++) styles.push(null); // null = sDef 유지

    var mcqPending = 0;  // 남은 MCQ 선지 줄 수 (것은? 이후 5줄)

    for (var i = 0; i < total; i++) {
        var t = texts[i];
        var trimmed = t.replace(/^\s+|\s+$/g, "");

        // 빈 줄 → 건너뜀 (sDef 유지)
        if (!trimmed) { mcqPending = 0; continue; }

        // ─ MCQ 선지 대기 중이면 우선 처리
        if (mcqPending > 0) {
            styles[i] = sChoices;
            mcqPending--;
            continue;
        }

        // ─ [N] 지문 번호 단독 줄
        if (/^\[\d+\]$/.test(trimmed)) {
            styles[i] = sBg;
            continue;
        }

        // ─ ※ 지시문 (다음 글을 읽고 / 다음에 답하시오 류)
        if (trimmed.charAt(0) === "\uFF0E" || trimmed.charAt(0) === "※" || /^※/.test(trimmed)) {
            styles[i] = sIntro;
            continue;
        }

        // ─ ① ② ③ ④ ⑤ 한 줄에 모두 있는 삽입형 선지
        if (/①.*②.*③.*④.*⑤/.test(t)) {
            styles[i] = sChoices;
            continue;
        }

        // ─ ① 으로 시작하는 선지/항목 (①sold, ②packing 등)
        if (/^[①②③④⑤]/.test(trimmed)) {
            styles[i] = sChoices;
            continue;
        }

        // ─ 주어진 문장/글 → 다음 비어있지 않은 줄에 배경 예약
        if (/주어진\s*(문장|글)/.test(t) || /들어갈\s*위치/.test(t)) {
            for (var n = i + 1; n < total; n++) {
                if (texts[n].replace(/^\s+|\s+$/g,"")) { styles[n] = sBg; break; }
            }
        }

        // ─ 번호 문단: N. 으로 시작하는 한글 포함 줄
        //   단, <보기>/<조건> 항목 번호는 나중에 덮어씀
        if (/^\d+\.\s/.test(trimmed) && /[가-힣]/.test(t)) {
            styles[i] = sNum;
            // 것은? 으로 끝나는 MCQ → 다음 5개 비어있지 않은 줄 선지 예약
            if (/것은\s*\?/.test(t) || /것을\s*모두\s*고르면/.test(t)) {
                var count = 0;
                for (var n = i + 1; n < total && count < 5; n++) {
                    if (texts[n].replace(/^\s+|\s+$/g,"")) count++;
                }
                mcqPending = count; // 실제로는 루프에서 5개 만나면 소진
                // 정확히 5줄 예약
                var cnt2 = 0;
                for (var n2 = i + 1; n2 < total && cnt2 < 5; n2++) {
                    if (texts[n2].replace(/^\s+|\s+$/g,"")) { styles[n2] = sChoices; cnt2++; }
                }
                mcqPending = 0; // 이미 직접 처리했으므로 리셋
            }
            continue;
        }

        // ─ 기존 STEP3 패턴
        // 한글 + ? (것은?, 등)
        if (/[가-힣]\?/.test(t)) { styles[i] = sNum; continue; }
        // 시오 포함
        if (t.indexOf("시오") !== -1) { styles[i] = sNum; continue; }
        // 다음 글을 읽고
        if (t.indexOf("다음 글을 읽고 물음에 답하시오.") !== -1) { styles[i] = sIntro; continue; }
        // * 주석
        if (t.indexOf("*") !== -1) { styles[i] = sAst; continue; }
        // (A) 선지
        if (/\(A\)[ \t]/.test(t)) { styles[i] = sChoices; continue; }
        // 우리말: → 배경
        if (/우리말[\s\u3000]*:/.test(t)) { styles[i] = sBg; continue; }
    }

    // 3단계: <보기>/<조건> 마커 처리 (위 결과 덮어쓰기)
    for (var i = 0; i < total; i++) {
        var t = texts[i];
        if (!t.replace(/^\s+|\s+$/g,"")) continue;
        if (/^[\s\u3000]*<보기>/.test(t) && styles[i] !== sNum) {
            styles[i] = sView;
        }
        if (t.indexOf("<조건>") !== -1 && styles[i] !== sNum) {
            styles[i] = sCond;
        }
    }

    // 4단계: 조건 이후 번호 항목 전파 (1. •. ① 으로 시작하는 연속 기본 줄)
    for (var i = 0; i < total - 1; i++) {
        if (styles[i] !== sCond) continue;
        if (texts[i].indexOf("<조건>") === -1) continue;
        for (var j = i + 1; j < total; j++) {
            if (styles[j] !== null && styles[j] !== sDef) break;
            if (!texts[j].replace(/^\s+|\s+$/g,"")) continue;
            if (/^[\s\u3000\t]*(\d+\.\s*|\(\d+\)\s*|•|[①②③④⑤⑥⑦⑧⑨⑩])/.test(texts[j])) {
                styles[j] = sCond;
            } else {
                break;
            }
        }
    }

    // 5단계: 보기 이후 연속 전파 (/ 또는 , 포함 줄)
    for (var i = 0; i < total - 1; i++) {
        if (styles[i] !== sView) continue;
        for (var j = i + 1; j < total; j++) {
            if (styles[j] !== null && styles[j] !== sDef) break;
            var tv = texts[j];
            if (!tv.replace(/^\s+|\s+$/g,"")) continue;
            if (tv.indexOf("/") !== -1 || tv.indexOf(",") !== -1) {
                styles[j] = sView;
            } else {
                break;
            }
        }
    }

    // 6단계: 배경(sBg) 다음에 ①~⑤ 포함 줄 → sDef 복원
    for (var i = 0; i < total - 1; i++) {
        if (styles[i] === sBg && /[①②③④⑤]/.test(texts[i+1])) {
            styles[i+1] = sDef;
        }
    }

    // ════════════════════════════════════════════
    // 스타일 일괄 적용
    // ════════════════════════════════════════════
    for (var i = 0; i < total; i++) {
        if (styles[i] !== null) {
            try { paras[i].appliedParagraphStyle = styles[i]; } catch(e) {}
        }
    }

    // ════════════════════════════════════════════
    // 표 셀 단락 스타일 적용
    // ════════════════════════════════════════════
    if (sTbl) {
        var tables = story.tables;
        for (var ti = 0; ti < tables.length; ti++) {
            try {
                var tbl = tables[ti];
                if (!tbl || !tbl.isValid) continue;
                var cells = tbl.cells.everyItem().getElements();
                for (var ci = 0; ci < cells.length; ci++) {
                    try {
                        cells[ci].paragraphs.everyItem().appliedParagraphStyle = sTbl;
                    } catch(e) {}
                }
            } catch(e) {}
        }
    }

    // ════════════════════════════════════════════
    // 표 너비 조정 (문서 전체 스토리 대상)
    // ════════════════════════════════════════════
    (function () {
        var origUnit;
        try { origUnit = app.scriptPreferences.measurementUnit; app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS; } catch(e) {}

        var allStories = doc.stories;
        for (var si = 0; si < allStories.length; si++) {
            try {
                var st = allStories[si];
                if (!st || !st.isValid) continue;
                var containers;
                try { containers = st.textContainers; } catch(e) { continue; }
                if (!containers || containers.length === 0) continue;
                var tables = st.tables;
                if (!tables || tables.length === 0) continue;

                var contentWidth = 0;
                for (var ci = 0; ci < containers.length; ci++) {
                    try {
                        var fr = containers[ci];
                        if (!fr || !fr.isValid) continue;
                        var b = fr.geometricBounds;
                        var fw = b[3] - b[1];
                        if (fw <= 0) continue;
                        var ins = fr.textFramePreferences.insetSpacing;
                        var iL = (ins && ins[1] != null) ? Number(ins[1]) : 0;
                        var iR = (ins && ins[3] != null) ? Number(ins[3]) : 0;
                        var cw = fw - iL - iR;
                        if (cw > 0) { contentWidth = cw; break; }
                    } catch(e) {}
                }
                if (contentWidth <= 0) continue;

                for (var ti = 0; ti < tables.length; ti++) {
                    try {
                        var tbl = tables[ti];
                        if (!tbl || !tbl.isValid) continue;
                        var curW = 0;
                        for (var c = 0; c < tbl.columns.length; c++) {
                            try { curW += tbl.columns[c].width; } catch(e) {}
                        }
                        if (curW <= 0 || Math.abs(curW - contentWidth) <= 0.5) continue;
                        var scale = contentWidth / curW;
                        for (var c = 0; c < tbl.columns.length; c++) {
                            try { tbl.columns[c].width = tbl.columns[c].width * scale; } catch(e) {}
                        }
                    } catch(e) {}
                }
            } catch(e) {}
        }

        try { app.scriptPreferences.measurementUnit = origUnit; } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // 표 행 높이 최소화 (문서 전체 스토리 대상)
    // ════════════════════════════════════════════
    (function () {
        var origUnit;
        try { origUnit = app.scriptPreferences.measurementUnit; app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS; } catch(e) {}

        var allStories = doc.stories;
        for (var si = 0; si < allStories.length; si++) {
            try {
                var st = allStories[si];
                if (!st || !st.isValid) continue;
                var tables = st.tables;
                if (!tables || tables.length === 0) continue;

                for (var ti = 0; ti < tables.length; ti++) {
                    try {
                        var tbl = tables[ti];
                        if (!tbl || !tbl.isValid) continue;
                        var rows = tbl.rows;
                        for (var ri = 0; ri < rows.length; ri++) {
                            try {
                                var row = rows[ri];
                                if (!row || !row.isValid) continue;
                                var minH = row.minimumHeight;
                                var curH = row.height;
                                if (minH <= 0 || curH <= minH + 0.5) continue;
                                // autoGrow=true 행은 먼저 false로 설정 후 height 지정
                                try { row.autoGrow = false; } catch(e) {}
                                try { row.height = minH; } catch(e) {}
                            } catch(e) {}
                        }
                    } catch(e) {}
                }
            } catch(e) {}
        }

        try { app.scriptPreferences.measurementUnit = origUnit; } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // 표 컬럼 너비 내용 맞춤
    // ════════════════════════════════════════════
    (function () {
        var origUnit;
        try { origUnit = app.scriptPreferences.measurementUnit; app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS; } catch(e) {}

        // MCQ 표 판별: 6행×(3|4)열 + row0이 병합되지 않음(columnSpan==1)
        function isMCQTable(tbl) {
            var nr = tbl.rows.length, nc = tbl.columns.length;
            if (!(nr === 6 && (nc === 3 || nc === 4))) return false;
            try {
                var c0 = tbl.cells[0];
                if (c0 && c0.isValid && c0.columnSpan > 1) return false;
            } catch(e) {}
            return true;
        }

        // 지문 요약 표 판별: row0 첫 셀이 병합(columnSpan > 1)
        function isSummaryTable(tbl) {
            try {
                var c0 = tbl.cells[0];
                if (c0 && c0.isValid && c0.columnSpan > 1) return true;
            } catch(e) {}
            return false;
        }

        var allStories = doc.stories;
        for (var si = 0; si < allStories.length; si++) {
            try {
                var st = allStories[si];
                if (!st || !st.isValid) continue;
                var tables = st.tables;
                if (!tables || tables.length === 0) continue;

                for (var ti = 0; ti < tables.length; ti++) {
                    try {
                        var tbl = tables[ti];
                        if (!tbl || !tbl.isValid || tbl.rows.length < 2) continue;
                        var nr = tbl.rows.length, nc = tbl.columns.length;

                        // 현재 총 너비
                        var totalW = 0;
                        for (var ci = 0; ci < nc; ci++) totalW += tbl.columns[ci].width;
                        if (totalW <= 0) continue;

                        // 1단계: 깨진 행(모든 행이 2pt 미만) 복구
                        var allBroken = true;
                        for (var ri = 0; ri < nr; ri++) {
                            if (tbl.rows[ri].height >= 2) { allBroken = false; break; }
                        }
                        if (allBroken) {
                            for (var ri = 0; ri < nr; ri++) {
                                try { tbl.rows[ri].autoGrow = true; tbl.rows[ri].height = 18.8; } catch(e) {}
                            }
                            continue;
                        }

                        // 2단계: MCQ 표 (6행×3열 or 6행×4열, row0 비병합) → col0 고정(13pt) + 나머지 균등
                        if (isMCQTable(tbl)) {
                            var col0Fixed = 13;
                            var restEach = Math.round((totalW - col0Fixed) / (nc - 1) * 10) / 10;
                            var lastColW = Math.round((totalW - col0Fixed - restEach * (nc - 2)) * 10) / 10;
                            tbl.columns[0].width = col0Fixed;
                            for (var ci2 = 1; ci2 < nc - 1; ci2++) tbl.columns[ci2].width = restEach;
                            if (nc > 1) tbl.columns[nc - 1].width = lastColW;
                            continue;
                        }

                        // 3단계: 지문 요약 표 (row0 병합) → 균등 컬럼 + 모든 행 높이 최소화(18.8pt)
                        if (isSummaryTable(tbl)) {
                            var eachW = Math.round(totalW / nc * 10) / 10;
                            var lastW = Math.round((totalW - eachW * (nc - 1)) * 10) / 10;
                            for (var ci3 = 0; ci3 < nc - 1; ci3++) tbl.columns[ci3].width = eachW;
                            tbl.columns[nc - 1].width = lastW;
                            for (var ri3 = 0; ri3 < nr; ri3++) {
                                try {
                                    try { tbl.rows[ri3].minimumHeight = 18.8; } catch(e) {}
                                    try { tbl.rows[ri3].autoGrow = true; } catch(e) {}
                                    try { tbl.rows[ri3].height = 18.8; } catch(e) {}
                                } catch(e) {}
                            }
                            continue;
                        }

                    } catch(e) {}
                }
            } catch(e) {}
        }

        try { app.scriptPreferences.measurementUnit = origUnit; } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // 빈 단락 삭제 (스타일 일괄 적용 후)
    // ════════════════════════════════════════════
    var deletedParas = deleteEmptyParas(story);

    // ════════════════════════════════════════════
    // 후처리 GREP
    // ════════════════════════════════════════════
    // 번호 문단 앞 "숫자. " 제거
    (function() {
        var fb = app.findGrepPreferences.properties, cb = app.changeGrepPreferences.properties;
        app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.appliedParagraphStyle = sNum;
        app.findGrepPreferences.findWhat = "^\\d+\\.\\s";
        app.changeGrepPreferences.changeTo = "";
        try { story.changeGrep(); } catch(e) {}
        app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING;
        try { app.findGrepPreferences.properties = fb; } catch(e) {}
        try { app.changeGrepPreferences.properties = cb; } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // 밑줄 복원
    // ════════════════════════════════════════════
    (function() {
        if (!ulStyle || !ulStyle.isValid) return;
        var fb = app.findGrepPreferences.properties, cb = app.changeGrepPreferences.properties;
        app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.appliedCharacterStyle = ulStyle;
        app.findGrepPreferences.findWhat = ".+";
        app.changeGrepPreferences.appliedCharacterStyle = doc.characterStyles[0];
        app.changeGrepPreferences.underline = true;
        try { story.changeGrep(); } catch(e) {}
        app.findGrepPreferences = NothingEnum.NOTHING; app.changeGrepPreferences = NothingEnum.NOTHING;
        try { app.findGrepPreferences.properties = fb; } catch(e) {}
        try { app.changeGrepPreferences.properties = cb; } catch(e) {}
        try { ulStyle.remove(); } catch(e) {}
    })();

    // ════════════════════════════════════════════
    // 완료 리포트
    // ════════════════════════════════════════════
    var numCount = 0, choiceCount = 0, bgCount = 0, defCount = 0, viewCount = 0, condCount = 0;
    for (var i = 0; i < total; i++) {
        var s = styles[i] || sDef;
        if (s === sNum)     numCount++;
        else if (s === sChoices) choiceCount++;
        else if (s === sBg)   bgCount++;
        else if (s === sView)  viewCount++;
        else if (s === sCond)  condCount++;
        else defCount++;
    }
    alert("STEP3 조판 완료\n" +
          "총 단락: " + total + "개\n" +
          "번호: " + numCount + " / 선지: " + choiceCount + " / 배경: " + bgCount +
          " / 보기: " + viewCount + " / 조건: " + condCount + " / 지문: " + defCount + "\n" +
          "빈 단락 삭제: " + deletedParas + "개\n\n" +
          "감지 그룹: " + GROUP_NAME + (detectedGroup ? " (자동)" : " (기본값)"));

})();
