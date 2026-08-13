// 워크북 v2 렌더 실행기 — wb-flows 플랜의 스텝별 스토리 배치 (lib.jsxinc concat).
// 스토리 탐색 = v1 mapStepToStory 의미론: marker 텍스트 페이지 → 메인 스토리,
// step3는 마스터 O 페이지들의 메인 스토리. 미지원 스텝은 건드리지 않는다.
// 스타일 자동 생성 금지. 유닛 경계 프레임브레이크(startParagraph NEXT_FRAME).
//
// W3: generic 인라인 아이콘 op — 플랜 단락의 선택 필드 icon
//   {label, pos: "end"|"start", pad, mode: "dup"(기본)|"place"}
// 스타일/밑줄/브레이크 적용이 끝난 뒤 마지막 패스에서 역순(뒤 단락부터)으로
// findLabeledItem(label) 원본을 duplicate 인라인 앵커 삽입 (v1 insertInlineIcon
// 의미론). mode "place"는 v1 processStep2B1의 itemLink 기반: 라벨 아이템의
// 링크 파일을 place하고 원본 너비로 스케일. 원본 없으면 [경고] 로그만.
//
// W4: 유닛 확장 형식 — 유닛이 단락 배열(기존) 또는
//   {"paras": [...], "page_break": true} dict. page_break 유닛 시작 단락은
//   startParagraph NEXT_PAGE (v1 processStep1C1의 헤더 = 새 페이지),
//   그 외 유닛 경계는 기존과 동일 NEXT_FRAME.

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

// 마스터 prefix 페이지들의 메인 스토리 (v1 findMainStoryOnMaster 의미론)
function mainStoryOnMaster(doc, prefix) {
    var votes = {};
    var byId = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var pg = doc.pages[p];
        var mp = null;
        try { mp = pg.appliedMaster; } catch (e) {}
        if (!mp || String(mp.namePrefix) !== prefix) { continue; }
        var tfs = pg.textFrames;
        for (var t = 0; t < tfs.length; t++) {
            try {
                var st = tfs[t].parentStory;
                var sid = String(st.id);
                votes[sid] = (votes[sid] || 0) + 1;
                byId[sid] = st;
            } catch (e) {}
        }
    }
    var best = null;
    var bestN = 0;
    for (var k in votes) {
        if (votes[k] > bestN) { bestN = votes[k]; best = byId[k]; }
    }
    return best;
}

// marker 페이지의 N번째 스토리 (rank — 같은 페이지 하단 스토리용)
// pos ("top"|"bottom", opt-in W11): 다중 프레임 스토리를 이 페이지 첫 프레임의
// 세로 좌표로 정렬해 기하로 선택. [원본]워크북_C p114는 page.textFrames 순서가
// [발문(1프레임), 하단, 상단]이라 프레임수 동률에서 rank/mainStoryOnPage가
// 상단(step2_a1)/하단(step2_a1_btm)을 뒤바꿨다 (supp 06f4b2c2 실증).
function storyByMarker(doc, marker, pageName, rank, pos) {
    var page = findPageByMarker(doc, marker);
    if (!page && pageName) {
        try { page = doc.pages.itemByName(pageName); } catch (e) {}
        if (page && !page.isValid) { page = null; }
    }
    if (!page) { return null; }
    if (pos === "top" || pos === "bottom") {
        var cands = [];
        var seenP = {};
        var pfs = page.textFrames;
        for (var ci = 0; ci < pfs.length; ci++) {
            try {
                var cst = pfs[ci].parentStory;
                if (cst.textContainers.length <= 1) { continue; }  // 라벨 스토리 제외 (v1 파리티)
                var top = pfs[ci].geometricBounds[0];
                var cid = String(cst.id);
                if (seenP[cid]) {
                    if (top < seenP[cid].top) { seenP[cid].top = top; }
                    continue;
                }
                seenP[cid] = { st: cst, top: top };
                cands.push(seenP[cid]);
            } catch (e) {}
        }
        if (cands.length > 0) {
            cands.sort(function (a, b) { return a.top - b.top; });
            return (pos === "top") ? cands[0].st : cands[cands.length - 1].st;
        }
        // 다중 프레임 스토리가 없으면 기존 경로로 폴백
    }
    if (!rank || rank <= 1) { return mainStoryOnPage(page); }
    // rank 2+: 프레임 수 순위 N번째 스토리
    var counts = [];
    var seen = {};
    var frames = page.textFrames;
    for (var fi = 0; fi < frames.length; fi++) {
        try {
            var st = frames[fi].parentStory;
            var sid = String(st.id);
            if (seen[sid]) { seen[sid].n++; continue; }
            seen[sid] = { st: st, n: 1 };
            counts.push(seen[sid]);
        } catch (e) {}
    }
    counts.sort(function (a, b) { return b.n - a.n; });
    return counts[rank - 1] ? counts[rank - 1].st : null;
}

// 문서 내장 [기본 단락] — 플랜 센티널 "$BASIC" 해석용 (v1 getBasicPara 이식)
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

// ── 아이콘 op (W3) ──────────────────────────────────────────────────────────
var _iconDup = {};    // label -> {src, state} 또는 {missing: true}
var _iconLink = {};   // label -> {path, width} 또는 {missing: true}

function _iconSource(doc, label) {
    if (_iconDup[label]) { return _iconDup[label]; }
    var src = findLabeledItem(doc, label);
    if (!src) {
        _iconDup[label] = { missing: true };
        wlog("[경고] 아이콘 원본 없음: " + label);
        return _iconDup[label];
    }
    // v1 unlockItem: 원본/레이어 잠금 해제 (종료 시 relockIcons가 복원)
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

// 단락 끝(\r 앞) 삽입점 — 스토리 마지막 단락(\r 없음)은 맨 끝
function _endIP(para) {
    var c = "";
    try { c = para.contents || ""; } catch (e) {}
    var endsCR = c.length > 0 && c.charAt(c.length - 1) === "\r";
    return endsCR ? para.insertionPoints[-2] : para.insertionPoints[-1];
}

// pad 보장 (v1 2B1: 마지막 문자가 pad가 아니면 삽입 후 삽입점 재취득)
function _ensureEndPad(para, ip, pad) {
    var c = "";
    try { c = (para.contents || "").replace(/\r$/, ""); } catch (e) {}
    if (c.length === 0 || c.charAt(c.length - 1) !== pad.charAt(pad.length - 1)) {
        ip.contents = pad;
        return _endIP(para);
    }
    return ip;
}

// W50: place 실패 추적 — 링크 파일이 GDrive 실경로라 실체화 지연/스톨 시
// place가 문항마다 조용히 실패해 아이콘이 통째로 빠졌다 (2026-08-11
// de909e4d 실증: step2_b1 OX 버튼 0/90, 경고 0). place 실패는 문서 내
// 원본 duplicate로 폴백하고, 건수를 [경고]로 남긴다 (침묵 금지).
var _iconPlaceFallback = {};   // label -> place 실패 → duplicate 폴백 건수

// 단락 1개에 아이콘 1개 삽입. 성공 1 / 실패 0.
// W58: 삽입 후 앵커 앞 공백 보정 — 경로(place/duplicate 폴백)에 따라
// pad가 앵커 뒤로 밀리는 케이스가 있어("Monday￼ " — 사용자 지적: 버튼이
// 본문에 딱 붙음) 삽입 결과를 직접 검사해 앵커 '앞'에 pad를 보장한다.
function _fixAnchorPad(para, pad) {
    if (!pad) { return; }
    try {
        var c = String(para.contents || "").replace(/\r$/, "");
        var ai = c.lastIndexOf("￼");
        if (ai > 0 && c.charAt(ai - 1) !== pad.charAt(pad.length - 1)) {
            para.insertionPoints[ai].contents = pad;
        }
        // 앵커 뒤에 남은 잉여 pad 제거 (pad가 뒤로 밀렸던 흔적)
        c = String(para.contents || "").replace(/\r$/, "");
        ai = c.lastIndexOf("￼");
        if (ai >= 0 && ai + 1 < c.length
                && c.substring(ai + 1) === pad) {
            para.characters.itemByRange(ai + 1, c.length - 1).contents = "";
        }
    } catch (e) {}
}

function insertIconAt(doc, story, para, ic) {
    var pos = (ic.pos === "start") ? "start" : "end";
    var pad = ic.pad || "";
    if (ic.mode === "place") {
        // v1 processStep2B1: 링크 파일 place + 원본 너비 스케일
        var info = _iconLinkInfo(doc, ic.label);
        var pf = null;
        if (!info.missing) {
            try { pf = File(info.path); } catch (ef) { pf = null; }
        }
        if (pf && pf.exists) {
            var ip = _endIP(para);
            if (pad) { ip = _ensureEndPad(para, ip, pad); }
            try {
                var placed = story.insertionPoints[ip.index].place(pf)[0];
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
                if (pos === "end") { _fixAnchorPad(para, pad); }
                return 1;
            } catch (e) { /* W50: 아래 duplicate 폴백으로 계속 */ }
        }
        _iconPlaceFallback[ic.label] = (_iconPlaceFallback[ic.label] || 0) + 1;
    }
    // 기본: duplicate 인라인 앵커 (v1 insertInlineIcon) — place 실패 폴백 겸용
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
        // 앵커(￼) 직후에 pad (v1 1B1: 아이콘 다음 탭)
        try { para.insertionPoints[1].contents = pad; } catch (e) {}
    }
    if (pos === "end") { _fixAnchorPad(para, pad); }   // W58
    return 1;
}

// ── W11 op: 독립 지문번호 프레임 갱신 (plan.passage_numbers가 있을 때만) ────
// 빈칸어휘/어법OX/빈칸어법 섹션은 지문번호가 메인 스토리 밖 단일 프레임
// 스토리("20" 등 모의고사 문항번호 잔재). 스텝 스토리의 k번째 콘텐츠 페이지의
// 순수 숫자 단일 프레임을 원고 지문번호 labels[k]로 갱신한다.
var RE_BARE_NUM = /^\s*\d{1,3}(?:\s*~\s*\d{1,3})?\s*$/;

// W30: 긴 한글 라벨(추가지문/외부지문형)의 본문 침범 교정 — 모의고사 내지의
// 지문번호 프레임은 박스 우측이 본문 프레임 좌변(x≈20)을 이미 넘는다
// (r13 실측: 라벨 [32, 9.6~27.2] vs 본문 좌변 20). 숫자 잔재("20")는 짧아
// 침범 구간에 글리프가 닿지 않지만, 긴 라벨은 첫 줄이 프레임 폭을 채워
// 문항 번호('1.'/'11.')와 겹친다 (r13 p14/15 시각 검수 실증). 라벨 프레임
// 우변을 본문 좌변 앞으로 클램프하고, 줄바꿈 증가로 생기는 overset은
// 하단 여백(왼쪽 마진 빈 공간)으로 프레임을 늘려 해소한다.
// 숫자 라벨(v1 파리티 경로)은 호출부에서 배제 — 기존 동작 무변경.
var LABEL_CLAMP_GAP = 1.5;   // 본문 좌변과의 간격 (mm)
var LABEL_MIN_W = 5;         // 클램프 후 최소 프레임 폭 (mm — 한글 12pt 1자)
function clampLabelFrame(tf, page, flowStory) {
    var bodyL = null;
    var conts = flowStory.textContainers;
    for (var i = 0; i < conts.length; i++) {
        var pg = null;
        try { pg = conts[i].parentPage; } catch (e) {}
        if (!pg || pg.documentOffset !== page.documentOffset) { continue; }
        var g = conts[i].geometricBounds;
        if (bodyL === null || g[1] < bodyL) { bodyL = g[1]; }
    }
    if (bodyL === null) { return false; }
    var gb = tf.geometricBounds;
    var newR = bodyL - LABEL_CLAMP_GAP;
    if (gb[3] <= newR + 0.01) { return false; }        // 침범 없음 — 무접촉
    if (newR - gb[1] < LABEL_MIN_W) { return false; }  // 무리한 축소 금지
    try { tf.geometricBounds = [gb[0], gb[1], gb[2], newR]; } catch (e1) { return false; }
    var guard = 0;
    while (guard < 40) {
        var ovf = false;
        try { ovf = tf.overflows; } catch (e2) { break; }
        if (!ovf) { break; }
        var g2 = tf.geometricBounds;
        try { tf.geometricBounds = [g2[0], g2[1], g2[2] + 5, g2[3]]; } catch (e3) { break; }
        guard++;
    }
    return true;
}

function storyPagesInOrder(story) {
    var pages = [];
    var seen = {};
    var conts = story.textContainers;
    for (var i = 0; i < conts.length; i++) {
        var pg = null;
        try { pg = conts[i].parentPage; } catch (e) {}
        if (!pg) { continue; }
        var key = String(pg.documentOffset);
        if (seen[key]) { continue; }
        seen[key] = true;
        pages.push(pg);
    }
    return pages;
}

// W60 (사용자 지시 2026-08-13): 긴 지문번호 라벨은 좁은 세로 라벨 프레임
// 안에서 자동 줄바꿈이 단어를 어중간하게 끊는다("Main Read/ing 1"). 단어
// 경계에 강제 줄바꿈(\n)을 넣어 끊는 자리를 결정한다. 숫자만인 꼬리 토큰
// ("1")은 앞 단어에 붙여 줄 수를 줄인다 — "Main Reading 1" → "Main /
// Reading 1"(2줄), "Critical Thinking" → "Critical / Thinking".
// 공백 없는 라벨(숫자 "20", 한글 "본문1")은 그대로 (기존 동작 무변경).
// W61 (사용자 지시 2026-08-13): 좁은 라벨 프레임을 넘는 긴 라벨은 **줄임말**
// 로 바꾼다 (프레임을 늘리지 않는다 — 템플릿 기하는 디자인이다).
//   영문 다단어 → 각 단어 이니셜 + 숫자 유지: "Main Reading 1"→"MR1",
//     "Read More"→"RM", "Critical Thinking"→"CT"
//   한글 다단어 → 첫 단어: "추가 본문"→"추가"
// 축약은 '프레임에 안 들어갈 때만' 적용한다 (짧은 라벨·기존 원고 무영향).
function abbreviateLabel(lab) {
    var s = String(lab === undefined || lab === null ? "" : lab).replace(
        /^\s+|\s+$/g, "");
    if (s.indexOf(" ") < 0) { return s; }
    var toks = s.split(/\s+/);
    if (/[가-힣]/.test(s)) { return toks[0]; }
    var ini = "", num = "";
    for (var i = 0; i < toks.length; i++) {
        if (/^[0-9]+$/.test(toks[i])) { num = toks[i]; continue; }
        var ch = toks[i].charAt(0);
        if (/[A-Za-z]/.test(ch)) { ini += ch.toUpperCase(); }
    }
    if (!ini) { return s; }
    return ini + num;
}

function labelWithBreaks(lab) {
    var s = String(lab === undefined || lab === null ? "" : lab);
    if (s.indexOf(" ") < 0) { return s; }
    // 한글 라벨("3과 추가지문")은 기존 자동 줄바꿈 유지 — 회귀 0
    if (/[가-힣]/.test(s)) { return s; }
    var raw = s.split(/\s+/);
    var toks = [];
    for (var i = 0; i < raw.length; i++) {
        if (raw[i] === "") { continue; }
        if (toks.length > 0 && /^[0-9]+$/.test(raw[i])) {
            toks[toks.length - 1] += " " + raw[i];   // 숫자 꼬리는 앞에 결합
        } else {
            toks.push(raw[i]);
        }
    }
    return toks.join("\n");
}

function updatePassageNumbers(doc, flowStories, op) {
    var labels = op.labels || [];
    var steps = op.steps || [];
    var clearSteps = op.clear_steps || [];
    if ((labels.length === 0 || steps.length === 0)
            && clearSteps.length === 0) { return; }
    // W14 D3: clear_steps — 라벨 개념이 없는 스텝(교과서 step3 서술형 등)의
    // 콘텐츠 페이지에 남은 순수 숫자 단일 프레임(모의고사 문항번호 잔재)을
    // 삭제한다 (c03 실증: step3 단독 원고 페이지에 '20' 프레임 3개 잔존).
    var cleared = 0;
    for (var ci = 0; ci < clearSteps.length; ci++) {
        var recC = flowStories[clearSteps[ci]];
        if (!recC) { continue; }
        var pagesC = storyPagesInOrder(recC.story);
        for (var pc = 0; pc < pagesC.length; pc++) {
            var tfsC = pagesC[pc].textFrames;
            for (var fc = tfsC.length - 1; fc >= 0; fc--) {   // 삭제는 역순
                try {
                    var fstC = tfsC[fc].parentStory;
                    if (fstC.textContainers.length !== 1) { continue; }
                    if (!RE_BARE_NUM.test(String(fstC.contents || ""))) { continue; }
                    tfsC[fc].remove();
                    cleared++;
                } catch (e) {}
            }
        }
    }
    if (cleared > 0) { wlog("지문번호 잔재 프레임 삭제: " + cleared + "개"); }
    if (labels.length === 0 || steps.length === 0) { return; }
    var total = 0;
    for (var si = 0; si < steps.length; si++) {
        var rec = flowStories[steps[si]];
        if (!rec) { continue; }
        // 페이지 → 라벨 매핑.
        // 기본: '유닛 k 시작 페이지 ~ 유닛 k+1 시작 전' 구간 페이지 전부에
        // labels[k] (W13 c13 실증 — 지문이 페이지를 넘치면 '스토리 k번째
        // 페이지 = k번째 지문' 가정이 깨진다. 넘친 연속 페이지도 같은 지문
        // 번호로 갱신). unitStart가 없으면(하위호환) 옛 페이지 순서 매핑.
        var pageLabel = {};   // documentOffset(str) -> label
        var mapped = false;
        if (rec.unitStart && rec.unitStart.length > 0) {
            try {
                var paras = rec.story.paragraphs.everyItem().getElements();
                var startOffsets = [];
                for (var uk = 0; uk < rec.unitStart.length && uk < labels.length; uk++) {
                    var pIdx = rec.unitStart[uk];
                    if (pIdx >= paras.length) { break; }
                    var ptf = paras[pIdx].parentTextFrames;
                    if (ptf.length === 0) { continue; }
                    var upg = null;
                    try { upg = ptf[0].parentPage; } catch (e) {}
                    if (!upg) { continue; }
                    startOffsets.push({ off: upg.documentOffset, label: labels[uk] });
                }
                if (startOffsets.length > 0) {
                    var allPages = storyPagesInOrder(rec.story);
                    for (var ap = 0; ap < allPages.length; ap++) {
                        var poff = allPages[ap].documentOffset;
                        var lab = null;
                        for (var so = 0; so < startOffsets.length; so++) {
                            if (poff >= startOffsets[so].off) { lab = startOffsets[so].label; }
                        }
                        if (lab !== null) { pageLabel[String(poff)] = lab; }
                    }
                    mapped = true;
                }
            } catch (e) {}
        }
        if (!mapped) {
            var pagesFallback = storyPagesInOrder(rec.story);
            for (var k = 0; k < pagesFallback.length && k < labels.length; k++) {
                pageLabel[String(pagesFallback[k].documentOffset)] = labels[k];
            }
        }
        var n = 0;
        var clamped = 0;
        var widened = 0;
        var heightened = 0;   // W59: 라벨 프레임 세로 확장 건수
        var shrunkN = 0;      // W59: 라벨 글자 축소 건수
        var abbrN = 0;        // W61: 라벨 줄임말 대체 건수
        var labelFrames = [];   // W38: 좌/우 기하 정규화용 (숫자 아닌 라벨만)
        var pages = storyPagesInOrder(rec.story);
        for (var pk = 0; pk < pages.length; pk++) {
            var lab2 = pageLabel[String(pages[pk].documentOffset)];
            if (lab2 === undefined || lab2 === null) { continue; }
            var tfs = pages[pk].textFrames;
            for (var fi = 0; fi < tfs.length; fi++) {
                try {
                    var fst = tfs[fi].parentStory;
                    if (fst.textContainers.length !== 1) { continue; }
                    if (!RE_BARE_NUM.test(String(fst.contents || ""))) { continue; }
                    // W61: 원 라벨 → (넘치면) 줄임말. 프레임 기하는
                    // 손대지 않는다 (템플릿 디자인 보존 — 어법OX의 가로형
                    // 라벨 프레임을 세로로 늘려 조판을 망친 W60 반성).
                    fst.contents = labelWithBreaks(lab2);
                    try { fst.recompose(); } catch (eRC) {}
                    var ovfL = false;
                    try { ovfL = tfs[fi].overflows; } catch (eL0) {}
                    if (ovfL) {
                        var ab = abbreviateLabel(lab2);
                        if (ab && ab !== lab2) {
                            try {
                                fst.contents = ab;
                                fst.recompose();
                                abbrN++;
                            } catch (eL1) {}
                        }
                    }
                    n++;
                    // W40 결함 7b: 번호 프레임은 템플릿에서 2자리("20")용
                    // 폭이라, 다회차 선택 워크북의 6자리 코드("231133")를
                    // 넣으면 오버셋된다 (v16 실증: 오버플로우 34개 —
                    // 후처리 trim 이 이걸 메우려 페이지를 40개씩 추가).
                    // 라벨 프레임은 본문 좌변 바깥 여백에 있으므로 왼쪽으로
                    // 넓혀 수용한다 (오른쪽은 본문 침범 — clampLabelFrame 이
                    // 반대 방향으로 막는 경계).
                    var gN = 0;
                    while (gN < 30) {
                        try { tfs[fi].parentStory.recompose(); } catch (eRR) {}
                        var ovfN = false;
                        try { ovfN = tfs[fi].overflows; } catch (eN0) { break; }
                        if (!ovfN) { break; }
                        var gbN = tfs[fi].geometricBounds;
                        if (gbN[1] - 1.5 < 0) { break; }   // 페이지 밖 금지
                        try {
                            tfs[fi].geometricBounds = [gbN[0], gbN[1] - 1.5,
                                                       gbN[2], gbN[3]];
                        } catch (eN1) { break; }
                        gN++;
                    }
                    if (gN > 0) { widened++; }
                    // W30: 숫자 아닌 긴 라벨만 본문 침범 클램프 (숫자 라벨은
                    // v1 파리티 경로 — 프레임 무접촉)
                    if (!RE_BARE_NUM.test(String(lab2))) {
                        if (clampLabelFrame(tfs[fi], pages[pk], rec.story)) {
                            clamped++;
                        }
                        labelFrames.push({ tf: tfs[fi], pg: pages[pk] });
                    }
                } catch (e) {}
            }
        }
        // ── W38 (결함 2): 지문번호 라벨 프레임 좌/우 크기 정규화 ─────────
        // [원본]워크북_C의 빈칸어휘/빈칸어법 지문번호 프레임은 템플릿
        // 단계부터 왼쪽/오른쪽 페이지 기하가 다르다 (6b66b750 덤프 실측:
        // 클램프 후 L 폭 8.9mm vs R 폭 7.72mm — 템플릿 좌변 x1 9.6 vs
        // 12.78). 사용자 확정: 왼쪽 페이지 크기에 통일. 왼쪽 첫 프레임의
        // 폭/높이를 기준으로 오른쪽 프레임을 우변(클램프 결과)·상변 고정
        // 리사이즈한다. 숫자 라벨(v1 파리티)은 위에서 제외 — 무접촉.
        var canonW = null, canonH = null;
        for (var lf = 0; lf < labelFrames.length; lf++) {
            if (pageSideOf(doc, labelFrames[lf].pg) !== "L") { continue; }
            try {
                var gL = labelFrames[lf].tf.geometricBounds;
                canonW = gL[3] - gL[1];
                canonH = gL[2] - gL[0];
            } catch (eL) {}
            break;
        }
        var normalized = 0;
        if (canonW !== null) {
            for (var rf = 0; rf < labelFrames.length; rf++) {
                if (pageSideOf(doc, labelFrames[rf].pg) !== "R") { continue; }
                try {
                    var gR = labelFrames[rf].tf.geometricBounds;
                    var wR = gR[3] - gR[1];
                    var hR = gR[2] - gR[0];
                    if (Math.abs(wR - canonW) < 0.05
                            && Math.abs(hR - canonH) < 0.05) { continue; }
                    labelFrames[rf].tf.geometricBounds =
                        [gR[0], gR[3] - canonW, gR[0] + canonH, gR[3]];
                    normalized++;
                } catch (eR) {}
            }
        }
        // ── W59: 라벨 오버셋 최종 해소 (모든 크기 조정 이후) ─────────────
        // 갱신 직후의 폭/세로 확장은 뒤따르는 clampLabelFrame(우변 클램프)
        // 과 좌우 크기 통일(L 기준 리사이즈)이 되돌려, 긴 영문 라벨
        // ("Main Reading 1")이 최종본에서 "Main"만 보이고 잘렸다
        // (비상(황) 실증: 오버플로우 18 = 라벨 프레임 전량). 크기 계약을
        // 깨지 않도록 **글자 크기 축소만** 마지막에 적용한다.
        var fitN = 0, fitFail = 0;
        for (var qf = 0; qf < labelFrames.length; qf++) {
            var qtf = labelFrames[qf].tf;
            var base = null;
            try {
                qtf.parentStory.recompose();
                base = qtf.parentStory.texts[0].pointSize;
            } catch (eQ0) { continue; }
            var qg = 0;
            var did = false;
            while (qg < 40) {
                var qov = false;
                try {
                    qtf.parentStory.recompose();
                    qov = qtf.overflows;
                } catch (eQ1) { break; }
                if (!qov) { break; }
                try {
                    var qtx = qtf.parentStory.texts[0];
                    var qps = qtx.pointSize;
                    if (qps <= base * 0.4) { break; }
                    qtx.pointSize = qps * 0.94;
                    did = true;
                } catch (eQ2) { break; }
                qg++;
            }
            if (did) { fitN++; }
            var qleft = false;
            try { qleft = qtf.overflows; } catch (eQ3) {}
            if (qleft) { fitFail++; }
        }
        if (abbrN > 0) {
            wlog(steps[si] + " 라벨 줄임말 대체: " + abbrN + "개 (프레임 초과)");
        }
        if (fitN > 0) {
            wlog(steps[si] + " 라벨 글자 맞춤 축소: " + fitN + "개");
        }
        if (fitFail > 0) {
            wlog("[경고] " + steps[si] + " 지문번호 라벨 " + fitFail
                 + "개가 프레임에 안 담김 — 라벨 축약 필요 (예: MR1)");
        }
        if (n > 0) {
            wlog(steps[si] + " 지문번호 프레임 갱신: " + n + "개"
                 + (widened > 0 ? " (폭 확장 " + widened + "개)" : "")
                 + (heightened > 0 ? " (세로 확장 " + heightened + "개)" : "")
                 + (shrunkN > 0 ? " (글자 축소 " + shrunkN + "개)" : ""));
        }
        if (clamped > 0) {
            wlog(steps[si] + " 라벨 프레임 본문 침범 교정: " + clamped + "개");
        }
        if (normalized > 0) {
            wlog(steps[si] + " 라벨 프레임 좌우 크기 통일: " + normalized
                 + "개 (왼쪽 기준 " + Math.round(canonW * 100) / 100 + "x"
                 + Math.round(canonH * 100) / 100 + "mm)");
        }
        total += n;
    }
    wlog("지문번호 프레임 갱신 합계: " + total + "개 (" + labels.join(", ") + ")");
}

// ── W11 op: 페이지 정리 (plan.page_cleanup이 있을 때만) ─────────────────────
// 원고에 없는 스텝/남는 사이클의 페이지 삭제 + 빈 STEP3 페이지 M 마스터.
// v1 run.jsx 16.5(빈 페이지 삭제)의 완제품 확장: 판정 기준을 '다중 프레임
// 스토리(=사이클 본문) 프레임이 있는데 전부 비었는가'로 두어, 지문번호/발문
// 등 단일 프레임 장식 스토리에 내용이 남아 있어도 잔여 사이클 페이지를
// 삭제한다 (v1 16.5는 장식 내용 때문에 이런 페이지를 못 지웠음).
// 범위: 첫 콘텐츠 섹션(마커 플로우 스토리의 첫 페이지) ~ STEP3 시작 전.
// STEP3 영역은 v1 adjustStep3Pages 파리티 — 빈 페이지에 M 마스터 재할당.
function isBlankFrameContent(tf) {
    var c = "";
    try { c = String(tf.contents || ""); } catch (e) {}
    return c.replace(/[\s\r\n￼]+/g, "").length === 0;
}

// W22 r12: 장식(반복 발문/섹션 탭) 프레임 텍스트의 정규화 키 — 앵커(￼)/
// 공백류(em-space 포함) 정리. 플로우 콘텐츠가 있는 페이지에서 수집한 단일
// 프레임 장식 텍스트와 '같은 텍스트'만 남은 잔여 페이지를 빈 페이지로
// 판정하기 위한 것 (실사용 0e3108fd 재조판 실측: p34 어법선택 발문
// "다음 밑줄 친 부분 중 어법상 틀린 것은?", p47 영작배열 섹션 탭이
// '텍스트 있음'으로 삭제 판정을 비껴가 잔존). 120자 초과는 장식으로 보지
// 않는다 (본문 오인 방지).
function furnKeyOf(tf) {
    var c = "";
    try { c = String(tf.contents || ""); } catch (e) { return ""; }
    c = c.replace(/[\s\r\n ￼]+/g, " ");
    c = c.replace(/^\s+|\s+$/g, "");
    if (c.length === 0 || c.length > 120) { return ""; }
    return c;
}

// 스토리 꼬리의 '배치 밖(overset) 공백' 제거 (W19 c19 실증): 플랜 꼬리의
// 빈 단락(\r)이 마지막 프레임을 정확히 채운 스토리에서 overset으로 남거나,
// cleanupPages의 스레드 절단(1b)이 공백 전용 꼬리 프레임을 끊으면서
// overset('\r')을 만든다 — 확장이 공백 전용 페이지를 만들고 정리가 그
// 페이지를 지우며 재발하는 순환. 배치된(보이는) 텍스트/프레임 안 여백은
// 보존하고 overset 구간의 공백만 제거한다 (본문 무손실). 반환: 제거 문자 수.
function trimWsOverset(story) {
    var conts = story.textContainers;
    if (!conts || conts.length === 0) { return 0; }
    var ov = false;
    try { ov = conts[conts.length - 1].overflows; } catch (e) {}
    if (!ov) { return 0; }
    var total = story.characters.length;
    // 스토리 끝에서 마지막 실질 문자 위치 (공백/개행/앵커만 건너뜀 — 상한
    // 500자: 그 이상의 꼬리 공백은 비정상 플랜, 손대지 않음)
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
    // 배치 마지막 문자 위치 — 이 뒤(overset)만 제거 대상
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

// 스토리 오버플로우 시 마스터 유지 페이지 추가 (v1 ensureNoOverflow 의미론
// — W4 processFlow 인라인을 W23에서 함수화: 문제단위킵 밀기 패스도 공용).
// safety 상한 60 (W12): 123문제 변형문제 문제모음이 상한 10을 넘겨 초과분이
// overset(미인쇄)으로 잘렸다. 상한은 무한 루프 가드일 뿐 실제 반복 수는
// 오버플로우 해소 시점이 결정 — 기존 케이스 무영향. 반환 = 추가 페이지 수.
// W30-r15 (결함 6): 소스 페이지의 '이 스토리' 프레임 전체를 스레드 순서로
// 복제한다 — 기존 구현은 마지막 프레임 1개만 복제해 2단 템플릿(O-마스터,
// 페이지당 2프레임)의 확장 페이지가 1단(오른쪽 단 1개)으로 열화됐다
// (실서비스 376b34d0 p95~98 실측, 게이트 G31). 좌/우 여백 비대칭(교과서
// 내지 실측 1.5mm)은 새 페이지와 같은 물리 사이드의 스토리 페이지에서
// 기하 템플릿을 얻어 보존하고, 없으면 소스 페이지 상대좌표 폴백.
function framesOfStoryOnPage(story, pg) {
    var out = [];
    var conts = story.textContainers;
    for (var i = 0; i < conts.length; i++) {
        try {
            if (conts[i].parentPage
                    && conts[i].parentPage.id === pg.id) {
                out.push(conts[i]);
            }
        } catch (e) {}
    }
    return out;
}

function relBoundsOfFrames(pg, frames) {
    var pb = pg.bounds;
    var out = [];
    for (var i = 0; i < frames.length; i++) {
        var gb = frames[i].geometricBounds;
        out.push([gb[0] - pb[0], gb[1] - pb[1],
                  gb[2] - pb[0], gb[3] - pb[1]]);
    }
    return out;
}

function expandStoryOverflow(doc, label, story) {
    var conts = story.textContainers;
    var lastF = conts[conts.length - 1];
    var safety = 0;
    while (lastF.overflows && safety < 60) {
        var lp = lastF.parentPage;
        var srcPage = lp;
        var srcFrames = framesOfStoryOnPage(story, lp);
        if (srcFrames.length === 0) { srcFrames = [lastF]; }
        var np = doc.pages.add(LocationOptions.AFTER, lp);
        try { np.appliedMaster = lp.appliedMaster; } catch (e) {}
        // 사이드 매칭 기하 템플릿: 새 페이지와 같은 물리 사이드의 스토리
        // 페이지(뒤에서부터, 프레임 수 동등 이상)를 찾는다
        if (pageSideOf(doc, np) !== pageSideOf(doc, srcPage)) {
            try {
                var spgs = storyPagesInOrder(story);
                for (var si = spgs.length - 1; si >= 0; si--) {
                    if (pageSideOf(doc, spgs[si])
                            !== pageSideOf(doc, np)) { continue; }
                    var cand = framesOfStoryOnPage(story, spgs[si]);
                    if (cand.length >= srcFrames.length) {
                        srcPage = spgs[si];
                        srcFrames = cand;
                        break;
                    }
                }
            } catch (e6) {}
        }
        var rel = relBoundsOfFrames(srcPage, srcFrames);
        var npb = np.bounds;
        for (var fi = 0; fi < rel.length; fi++) {
            var ntf = np.textFrames.add();
            ntf.geometricBounds = [npb[0] + rel[fi][0], npb[1] + rel[fi][1],
                                   npb[0] + rel[fi][2], npb[1] + rel[fi][3]];
            lastF.nextTextFrame = ntf;
            lastF = ntf;
        }
        safety++;
        if (safety % 10 === 0) {
            wlog(label + " 오버플로우 페이지 확장 진행: +" + safety);
        }
    }
    return safety;
}

function cleanupPages(doc, flowStories, op) {
    // W21 r11: op.empty === "delete" — 빈 STEP3 페이지를 M 마스터 재할당
    // 대신 삭제한다 (실사용 0e3108fd: 빈 M 페이지 84개 잔존이 사용자 지목
    // 결함. 'M 마스터 보존'은 v1 관행이었으나 완제품 기준으로 폐기 확정).
    var deleteEmpty = (op.empty === "delete");
    // W51: 제외/미지원 스텝의 섹션 마커 텍스트 — 이 텍스트만 남은 단일
    // 프레임은 빈 프레임 취급 (제외 섹션 첫 페이지의 러닝헤더 마커
    // '내용 종합'이 '텍스트 있음'으로 삭제 판정을 비껴가 잔존 —
    // job 0645d4a7 실증. 배치 섹션의 같은 마커 페이지는 플로우 콘텐츠가
    // 있어 삭제 판정에 애초에 안 걸린다).
    var exMarkers = {};
    if (op.excluded_markers && op.excluded_markers.length) {
        for (var xm = 0; xm < op.excluded_markers.length; xm++) {
            exMarkers[String(op.excluded_markers[xm])] = true;
        }
    }
    function isExcludedMarkerFrame(tf, pst, nConts) {
        if (nConts !== 1) { return false; }
        var c = "";
        try { c = String(pst.contents || ""); } catch (e) { return false; }
        c = c.replace(/^[\s\r\n ￼]+|[\s\r\n ￼]+$/g, "");
        return !!(c && exMarkers[c]);
    }
    // 1) 보호 경계 계산
    var cleanStart = -1;      // 첫 콘텐츠 섹션 페이지 offset
    var step3Story = null;
    var step3Start = doc.pages.length;
    for (var step in flowStories) {
        var rec = flowStories[step];
        var pages = storyPagesInOrder(rec.story);
        if (pages.length === 0) { continue; }
        var first = pages[0].documentOffset;
        if (rec.isMaster) {
            step3Story = rec.story;
            if (first < step3Start) { step3Start = first; }
        } else if (cleanStart < 0 || first < cleanStart) {
            cleanStart = first;
        }
    }
    if (cleanStart < 0 && step3Story) {
        // STEP3만 있는 원고 (변형문제 문제모음 등, W12): STEP1/2 콘텐츠
        // 플로우가 없으면 STEP3 이전 전 구간을 정리 대상으로 잡는다.
        // 표지/간지 등 단일 프레임 장식 페이지는 아래 '다중 프레임 스토리
        // 전부 빈 페이지' 판정에 걸리지 않아 보존된다.
        cleanStart = 0;
    }
    if (cleanStart < 0) { wlog("페이지 정리: 대상 없음"); return; }

    // 1b) 스레드 절단 (W13 성능 — c15 실기 실증): 콘텐츠 섹션 스토리가
    // 잔여 빈 프레임 수백 개에 연결된 채로 페이지를 지우면 pg.remove()마다
    // 전체 스토리 recompose가 돌아 삭제 루프가 사실상 정지한다 (c15에서
    // 삭제 26개 후 70분+ 무진행 — 앵커 아이콘 137개 문서). 삭제 전에 각
    // 콘텐츠 스토리의 '마지막 텍스트 프레임' 뒤 연결을 끊으면 빈 프레임은
    // 독립 프레임이 되어 삭제가 recompose를 유발하지 않는다. 잘린 프레임은
    // 어차피 아래 루프의 삭제 대상 페이지에만 존재한다.
    var unthreaded = 0;
    for (var st2 in flowStories) {
        var rec2 = flowStories[st2];
        // STEP3(isMaster)는 M 재할당 경로에서 관리 — 단, delete 모드에선
        // STEP1/2와 동일하게 절단해 빈 꼬리 페이지를 삭제 가능하게 한다 (W21)
        if (rec2.isMaster && !deleteEmpty) { continue; }
        try {
            var conts = rec2.story.textContainers;
            var lastWithText = -1;
            for (var ci = 0; ci < conts.length; ci++) {
                var cc = "";
                try { cc = String(conts[ci].contents || ""); } catch (e) {}
                if (cc.replace(/[\s\r\n\uFFFC]+/g, "").length > 0) {
                    lastWithText = ci;
                }
            }
            if (lastWithText >= 0 && lastWithText < conts.length - 1) {
                // W30-r15 (결함 6 잔여): 절단은 페이지 경계에서 — 마지막
                // 텍스트 프레임과 같은 페이지의 뒤 칼럼 프레임은 스레드에
                // 남긴다. 프레임 중간 절단이면 이후 문제단위킵 밀기가
                // 그 페이지의 남은 칼럼(빈 독립 스토리로 분리됨)을
                // 건너뛰고 확장 페이지로 흘러 우단 공백이 남는다
                // (r15 1차 재조판 실측: p96 좌단만 스토리, 우단은 빈
                // 별도 스토리 — G31 [프레임결손] 검출).
                try {
                    var lwPage = conts[lastWithText].parentPage;
                    while (lastWithText < conts.length - 1) {
                        var nxtPg = null;
                        try {
                            nxtPg = conts[lastWithText + 1].parentPage;
                        } catch (ePg) {}
                        if (!(lwPage && nxtPg
                                && nxtPg.id === lwPage.id)) { break; }
                        lastWithText++;
                    }
                } catch (eQ) {}
            }
            if (lastWithText >= 0 && lastWithText < conts.length - 1) {
                try {
                    conts[lastWithText].nextTextFrame = NothingEnum.NOTHING;
                } catch (eN) {
                    conts[lastWithText].nextTextFrame = null;
                }
                unthreaded++;
                // 절단이 공백 전용 꼬리(빈 단락)를 overset으로 만들면 즉시
                // 정리 — 본문 무손실, overset '\r' 잔존 방지 (W19 c19).
                var cutTrim = trimWsOverset(rec2.story);
                if (cutTrim > 0) {
                    wlog("페이지 정리: " + st2 + " 꼬리 공백 overset "
                         + cutTrim + "자 정리");
                }
            }
        } catch (e) {}
    }
    if (unthreaded > 0) {
        wlog("페이지 정리: 잔여 빈 프레임 스레드 절단 " + unthreaded + "개 스토리");
    }

    // 2) STEP1/2 영역 — 다중 프레임 스토리 프레임 전부 빈 페이지 삭제 (역순)
    // 하트비트 필수 (W12 실증): 페이지 삭제는 건당 리플로우로 느려서 수백
    // 페이지 문서에선 로그 무갱신이 stall_limit(900초)를 넘고, 러너가 정상
    // 진행 중인 InDesign을 행(hang)으로 오탐해 강제 종료했다 (스타일 루프
    // 50단락 하트비트 철칙과 동일 사유).
    // W14 D3: 고아 번호 페이지 판정용 — 배치된 플로우 스토리 id 집합.
    // 번호(지문/문항) 프레임은 있는데 이 페이지에 플로우 콘텐츠가 전혀
    // 없으면 원고 없는 스텝의 섹션 머리/예시 페이지(c03 '20' 3p) 또는
    // 스레드 절단(W13) 이후 단일 프레임이 된 빈 꼬리 페이지(c15 '5' 3p)다.
    // 간지/표지는 번호 프레임이 없어 이 판정에 걸리지 않는다.
    var flowIds = {};
    for (var fk in flowStories) {
        try { flowIds[String(flowStories[fk].story.id)] = true; } catch (e) {}
    }
    // W22 r12 (delete 모드): 장식 텍스트 수집 — 플로우 콘텐츠가 있는
    // 페이지의 단일 프레임 비-플로우 스토리 텍스트. 잔여 페이지에 같은
    // 텍스트의 반복 장식(페이지마다 얹히는 발문/섹션 탭)만 남으면 아래
    // 삭제 판정에서 빈 프레임으로 취급한다 (r11 재조판 실측: p34 어법선택
    // 발문 / p47 영작배열 탭이 '텍스트 있음'으로 판정을 비껴가 잔존 —
    // 사용자 지목 결함). 간지/표지 텍스트는 플로우 콘텐츠 페이지에
    // 등장하지 않으므로 수집되지 않는다 (보존 — 기존 동작 무변경).
    var furn = {};
    if (deleteEmpty) {
        for (var gp = cleanStart; gp < doc.pages.length; gp++) {
            var gtfs = doc.pages[gp].textFrames;
            var gHasFlow = false;
            for (var gi = 0; gi < gtfs.length; gi++) {
                try {
                    if (flowIds[String(gtfs[gi].parentStory.id)]
                            && !isBlankFrameContent(gtfs[gi])) {
                        gHasFlow = true;
                        break;
                    }
                } catch (e) {}
            }
            if (!gHasFlow) { continue; }
            for (var gj = 0; gj < gtfs.length; gj++) {
                try {
                    var gst = gtfs[gj].parentStory;
                    if (flowIds[String(gst.id)]) { continue; }
                    if (gst.textContainers.length !== 1) { continue; }
                    var gk = furnKeyOf(gtfs[gj]);
                    if (gk) { furn[gk] = true; }
                } catch (e) {}
            }
        }
    }
    var removed = 0;
    var scanned = 0;
    for (var dp = doc.pages.length - 1; dp >= 0; dp--) {
        if (dp < cleanStart) { continue; }
        var inStep3 = (dp >= step3Start);
        if (inStep3 && !deleteEmpty) { continue; }
        scanned++;
        if (scanned % 20 === 0) {
            wlog("페이지 정리 진행: " + scanned + "페이지 검사 / " + removed + "개 삭제");
        }
        var pg = doc.pages[dp];
        var tfs = pg.textFrames;
        var hasLocal = false;
        var allBlank = true;
        var hasBareNum = false;
        var hasFlowContent = false;
        var anyFrame = tfs.length > 0;
        var allBlankOrNum = anyFrame;   // delete 모드 STEP3 영역 판정 (W21)
        for (var tf = 0; tf < tfs.length; tf++) {
            var pst = null;
            var nConts = 0;
            try {
                pst = tfs[tf].parentStory;
                nConts = pst.textContainers.length;
            } catch (e) { allBlankOrNum = false; continue; }
            var frameBlank = isBlankFrameContent(tfs[tf]);
            var frameBareNum = (nConts === 1
                                && RE_BARE_NUM.test(String(pst.contents || "")));
            // W51: 제외 섹션 마커만 남은 단일 프레임 = 빈 프레임 취급
            if (!frameBlank && isExcludedMarkerFrame(tfs[tf], pst, nConts)) {
                frameBlank = true;
            }
            // W22 r12 (delete 모드): 수집된 반복 장식 텍스트와 같은 단일
            // 프레임(발문/섹션 탭)은 빈 프레임 취급 — p34/p47류 잔존 교정
            var frameFurn = false;
            if (deleteEmpty && !frameBlank && nConts === 1) {
                var fkey = "";
                try {
                    if (!flowIds[String(pst.id)]) { fkey = furnKeyOf(tfs[tf]); }
                } catch (eF) {}
                frameFurn = !!(fkey && furn[fkey]);
            }
            if (!frameBlank && !frameBareNum && !frameFurn) {
                allBlankOrNum = false;
            }
            if (nConts > 1) {
                hasLocal = true;
                if (!frameBlank) { allBlank = false; }
            } else if (frameBareNum) {
                hasBareNum = true;
            }
            try {
                if (flowIds[String(pst.id)] && !frameBlank) {
                    hasFlowContent = true;
                }
            } catch (e2) {}
        }
        if (inStep3) {
            // W21 delete 모드: 빈 STEP3 페이지 삭제 — 프레임이 있고 전부
            // 공백(또는 문항번호 잔재 단일 프레임)이며 스텝 콘텐츠가 없는
            // 페이지. 간지/짤지문 라벨 페이지는 한글 텍스트가 있어 보존.
            if (anyFrame && allBlankOrNum && !hasFlowContent) {
                try { pg.remove(); removed++; } catch (e) {}
            }
            continue;
        }
        if ((hasLocal && allBlank && !hasFlowContent)
                || (hasBareNum && !hasFlowContent)
                // W21 delete 모드: STEP1/2 영역도 완전 정리 — 스레드 절단
                // (1b) 후 단일 프레임이 된 빈 꼬리 페이지가 기존 판정
                // (다중 프레임/번호 프레임)을 비껴가 잔존 (r11 재조판 1차
                // 실측 p12/p21 — v1 실물 STEP1/2 영역엔 빈 페이지 0).
                // 발문/예시/간지 등 텍스트 있는 프레임 페이지는 보존.
                || (deleteEmpty && anyFrame && allBlankOrNum
                    && !hasFlowContent)) {
            try { pg.remove(); removed++; } catch (e) {}
        }
    }
    wlog("페이지 정리: 잔여 스텝/사이클 페이지 " + removed + "개 삭제"
         + (deleteEmpty ? " (STEP3 빈 페이지 포함 — delete 모드)" : ""));

    // 2a-2) W23 r13 (delete 모드): 고아 간지 스프레드 삭제 — 간지 라벨 뒤에
    // 다음 간지/문서 끝까지 플로우 콘텐츠가 없으면 사용되지 않는 섹션의
    // 간지 잔재다 (r13 피드백 F2: 짤지문 간지 p34~35 잔존 — 짤지문 섹션은
    // v2가 콘텐츠를 배치하지 않는 템플릿 영역. 이 라벨 페이지는 섹션
    // 마스터(O)가 적용돼 있어 isDividerLabelPage/updateDividerPages의
    // 마스터-없음 판정을 전부 비껴간다 — [원본]워크북_C p263 실측).
    if (deleteEmpty) {
        removeOrphanDividers(doc, flowIds, !!op.divider_solo);
    }

    // 2b) W22 r12 (delete 모드): 파트 경계 정렬 — 페이지 삭제로 간지
    // 라벨이 물리 왼쪽 페이지로 밀렸으면 간지 스프레드 앞에 M(메모)
    // 마스터 채움 페이지 1장을 삽입해 복원한다 (사용자 확정 스펙:
    // 파트 경계의 오른쪽 채움 페이지는 삭제가 아니라 M 마스터).
    if (deleteEmpty) { alignPartFillers(doc); }

    // 3) STEP3 영역 — 빈 페이지 M 마스터 재할당 (v1 adjustStep3Pages 파리티,
    //    delete 모드에선 위에서 삭제 완료 — 재할당 생략)
    if (!step3Story || deleteEmpty) { return; }
    var emptyMasterPrefix = op.empty_master || "M";
    var mMaster = null;
    try {
        var ms = doc.masterSpreads.everyItem().getElements();
        for (var mi = 0; mi < ms.length; mi++) {
            if (String(ms[mi].namePrefix) === emptyMasterPrefix) {
                mMaster = ms[mi];
                break;
            }
        }
    } catch (e) {}
    if (!mMaster) { wlog("[경고] " + emptyMasterPrefix + " 마스터 없음 — STEP3 빈 페이지 재할당 생략"); return; }
    try { step3Story.recompose(); } catch (e) {}
    var s3pages = storyPagesInOrder(step3Story);
    var reassigned = 0;
    for (var sp = 0; sp < s3pages.length; sp++) {
        if (sp > 0 && sp % 40 === 0) {
            wlog("페이지 정리 진행(STEP3): " + sp + "/" + s3pages.length);
        }
        var spg = s3pages[sp];
        var hasContent = false;
        var stfs = spg.textFrames;
        for (var st2 = 0; st2 < stfs.length; st2++) {
            try {
                // 스펙파이어 === 비교 신뢰 불가 (W7 교훈) — id로 비교
                if (String(stfs[st2].parentStory.id) === String(step3Story.id)
                        && !isBlankFrameContent(stfs[st2])) {
                    hasContent = true;
                    break;
                }
            } catch (e) {}
        }
        if (!hasContent) {
            try { spg.appliedMaster = mMaster; reassigned++; } catch (e) {}
        }
    }
    wlog("페이지 정리: 빈 STEP3 페이지 " + emptyMasterPrefix + " 마스터 " + reassigned + "개");
}

// ── W22 op: 파트 경계 채움 페이지 (delete 모드의 cleanupPages가 호출) ───────
// [원본]워크북_C 실측 정렬: 간지 스프레드 = 왼쪽(마스터 없음, 프레임 0) +
// 오른쪽(마스터 없음, 라벨 프레임 1). 페이지 삭제로 파트 콘텐츠가 홀수
// 페이지로 끝나면 간지 라벨이 왼쪽으로 밀린다 — 간지 스프레드 시작 앞에
// M(메모) 마스터 페이지 1장을 삽입해 라벨을 오른쪽으로 복원한다 (r12
// 사용자 확정 스펙: 파트 경계에 필요한 오른쪽 채움 페이지는 M 마스터).
// [W22 파트경계 유틸 시작] — scripts/e2e_round12_filler_probe.py가 이 구간을
// 추출해 실제 InDesign에서 단독 실측한다. 마커 주석 제거 금지.
function pageSideOf(doc, pg) {
    // 비대면(facing 아님) 문서는 pg.side가 전부 RIGHT_HAND ([원본]워크북_C
    // W21 실측) — 인쇄 물리 좌/우는 documentOffset 홀짝 (offset 0 = p1 =
    // 오른쪽). facing 문서만 pg.side를 신뢰 (fixSectionMasters와 동일 판정).
    var facing = false;
    try { facing = doc.documentPreferences.facingPages; } catch (e) {}
    if (facing) {
        try {
            return (pg.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
        } catch (e2) { return "R"; }
    }
    try { return (pg.documentOffset % 2 === 0) ? "R" : "L"; } catch (e3) {}
    return "R";
}

function isDividerLabelPage(pg) {
    // 간지 라벨 페이지 = 마스터 [None](또는 없음) + 텍스트 프레임 1개 +
    // 첫 단락에 한글 (updateDividerPages와 동일 판정 — W19 D5 주석 참조).
    var mn = "";
    try { mn = pg.appliedMaster ? String(pg.appliedMaster.name) : ""; } catch (e) {}
    if (mn !== "" && mn !== "[None]") { return false; }
    if (pg.textFrames.length !== 1) { return false; }
    var ps = null;
    try { ps = pg.textFrames[0].paragraphs; } catch (e2) { return false; }
    if (!ps || ps.length < 2) { return false; }
    var t1 = "";
    try { t1 = String(ps[0].contents || ""); } catch (e3) {}
    return /[가-힣]/.test(t1);
}

function alignPartFillers(doc) {
    // W24 r14: M 마스터 lookup은 첫 삽입 필요 시점으로 지연 — M 마스터가
    // 없는 내지(수능특강 분석/문제 등)에서 간지 정렬이 애초에 필요 없는데
    // '[경고] M 마스터 없음'이 항상 찍히던 노이즈 제거 (동작 동일 — M이
    // 있는 내지([원본]워크북_C/EBS리딩파워)는 기존 경로 그대로).
    var mMaster = null;
    var mLooked = false;
    function lookupM() {
        if (mLooked) { return mMaster; }
        mLooked = true;
        try {
            var ms = doc.masterSpreads.everyItem().getElements();
            for (var mi = 0; mi < ms.length; mi++) {
                if (String(ms[mi].namePrefix) === "M") {
                    mMaster = ms[mi];
                    break;
                }
            }
        } catch (e) {}
        if (!mMaster) {
            wlog("[경고] M 마스터 없음 — 파트 경계 채움 페이지 생략");
        }
        return mMaster;
    }
    var inserted = 0;
    for (var pi = 0; pi < doc.pages.length; pi++) {
        var pg = doc.pages[pi];
        if (!isDividerLabelPage(pg)) { continue; }
        if (pageSideOf(doc, pg) === "R") { continue; }   // 정렬 정상
        if (!lookupM()) { return; }
        // 간지 스프레드 시작(왼쪽 빈 동반 페이지 — 마스터 없음/프레임 0)
        // 앞에 삽입. 동반 페이지가 없으면 라벨 페이지 앞에 삽입.
        var ref = pg;
        if (pi > 0) {
            var prev = doc.pages[pi - 1];
            var pmn = "";
            try {
                pmn = prev.appliedMaster ? String(prev.appliedMaster.name) : "";
            } catch (e2) {}
            if ((pmn === "" || pmn === "[None]")
                    && prev.textFrames.length === 0) {
                ref = prev;
            }
        }
        try {
            // pages.add(BEFORE, page)는 스프레드 단위로 삽입돼 목표보다
            // 한 칸 앞(왼쪽)에 끼어든다 (r12 프로브 실측). 끝에 추가 후
            // page.move(BEFORE, ref) — move는 페이지 단위로 정확하다.
            var np = doc.pages.add(LocationOptions.AT_END);
            np.appliedMaster = mMaster;
            np.move(LocationOptions.BEFORE, ref);
            inserted++;
            wlog("파트 경계 채움: 간지 p" + pg.name
                 + " 앞 M 마스터 페이지 삽입");
        } catch (e3) {
            wlog("[경고] 파트 경계 채움 페이지 삽입 실패: " + e3);
        }
    }
    if (inserted > 0) {
        wlog("파트 경계 채움 페이지: " + inserted + "개 삽입 (M 마스터)");
    }
}
// [W22 파트경계 유틸 끝]

// ── W30-r15 op: 크레딧(판권) 페이지 정렬 (delete 모드 — 결함 7) ─────────────
// 사용자 확정 스펙 (W38 정정): 크레딧 페이지는 항상 왼쪽 + **문서의 마지막
// 페이지** — 책은 오른쪽에서 시작해 왼쪽(크레딧)에서 끝난다. W30의
// "크레딧 뒤 오른쪽 메모(M) 추가"는 잘못된 스펙으로 폐기 (6b66b750 실증:
// 크레딧-L 뒤 M-R이 붙어 책이 오른쪽으로 끝남). 크레딧 = 문서 마지막
// 페이지가 마스터 없음 + 텍스트 프레임 0 (그래픽 전용 판권 — [원본]
// 워크북_C 말미 페이지. 페이지 정리는 프레임 기반이라 이 페이지는 항상
// 살아남고, 간지 왼쪽 동반 페이지는 라벨이 뒤따르므로 '마지막'이 될 수
// 없다 — 전 코퍼스 덤프 sweep 실측). 크레딧이 오른쪽이면 앞에 M 1장을
// 삽입해 왼쪽으로 보낸다 (376b34d0 실증: 문제단위킵 페이지 확장 +3이
// 홀짝을 뒤집어 판권 p99가 오른쪽 단독). 페이지 수를 바꾸는 모든 op
// 이후 1회 호출.
function alignCreditPage(doc) {
    if (doc.pages.length < 2) { return; }
    var last = doc.pages[doc.pages.length - 1];
    var mn = "";
    try {
        mn = last.appliedMaster ? String(last.appliedMaster.name) : "";
    } catch (e) {}
    if (mn !== "" && mn !== "[None]") { return; }   // 크레딧 아님 (M 등)
    if (last.textFrames.length !== 0) { return; }   // 간지 라벨/콘텐츠 아님
    var mMaster = null;
    try {
        var ms = doc.masterSpreads.everyItem().getElements();
        for (var mi = 0; mi < ms.length; mi++) {
            if (String(ms[mi].namePrefix) === "M") {
                mMaster = ms[mi];
                break;
            }
        }
    } catch (e2) {}
    if (!mMaster) {
        wlog("[경고] M 마스터 없음 — 크레딧 정렬 생략");
        return;
    }
    try {
        if (pageSideOf(doc, last) === "R") {
            // pages.add(BEFORE)는 스프레드 단위 삽입 (W22 프로브 실측) —
            // 끝에 추가 후 move(BEFORE)로 정확히 크레딧 앞에 끼운다
            var np = doc.pages.add(LocationOptions.AT_END);
            np.appliedMaster = mMaster;
            np.move(LocationOptions.BEFORE, last);
            wlog("크레딧 정렬: 판권 p" + last.name
                 + " 앞 M 마스터 페이지 삽입 (왼쪽 정렬 — 책 끝)");
        }
        // W38: 크레딧이 마지막 페이지 — 뒤에 메모(M)를 붙이지 않는다
        // (책은 왼쪽(크레딧)에서 끝난다. 사용자 확정 스펙 정정).
    } catch (e3) {
        wlog("[경고] 크레딧 정렬 실패: " + e3);
    }
}

// ── W23 r13: 고아 간지 스프레드 삭제 (delete 모드의 cleanupPages가 호출) ────
// 간지 라벨 후보 = 로컬 프레임 1개 + 비-플로우 단일 프레임 스토리 + 단락
// 2개 이상 + 첫 단락 한글 + 전체 40자 미만 (마스터 불문 — 짤지문 간지는
// 섹션 마스터(O)가 적용된 채 존재. 게이트 G28③과 동일 부류). 발문/장식
// 프레임은 단락 1개, 본문은 40자 초과라 걸리지 않는다.
function isDividerLabelLike(pg, flowIds, allowSolo) {
    if (pg.textFrames.length !== 1) { return false; }
    var tf = pg.textFrames[0];
    var st = null;
    try { st = tf.parentStory; } catch (e) { return false; }
    if (flowIds && flowIds[String(st.id)]) { return false; }
    try { if (st.textContainers.length !== 1) { return false; } }
    catch (e2) { return false; }
    var ps = null;
    try { ps = tf.paragraphs; } catch (e3) { return false; }
    if (!ps || ps.length < 1) { return false; }
    if (ps.length < 2) {
        // W24 r14 (수능특강 문제 내지 opt-in — page_cleanup.divider_solo):
        // 다강 셸 간지는 'N강' 단독 단락 1개 ([원본]수능특강(문제) p27
        // '2강' 실측). 단락 1개 라벨은 발문/장식 프레임과 구분이 안 돼
        // 'N강' 정확 패턴 + opt-in일 때만 허용한다 (supp/본가 무영향 —
        // 그쪽 간지는 2단락 라벨이라 기존 경로 그대로).
        var solo = "";
        try { solo = String(st.contents || ""); } catch (e6) {}
        solo = solo.replace(/[\s\r\n￼]+/g, "");
        if (!allowSolo || !/^\d+강$/.test(solo)) { return false; }
    }
    var whole = "";
    try { whole = String(st.contents || ""); } catch (e4) {}
    if (whole.replace(/[\s\r\n￼]+/g, "").length === 0) { return false; }
    if (whole.length > 40) { return false; }
    var t1 = "";
    try { t1 = String(ps[0].contents || ""); } catch (e5) {}
    return /[가-힣]/.test(t1);
}

function removeOrphanDividers(doc, flowIds, allowSolo) {
    var pagesArr = doc.pages.everyItem().getElements();
    var info = [];
    for (var i = 0; i < pagesArr.length; i++) {
        var pg = pagesArr[i];
        var hasFlow = false;
        var tfs = pg.textFrames;
        for (var j = 0; j < tfs.length; j++) {
            try {
                if (flowIds[String(tfs[j].parentStory.id)]
                        && !isBlankFrameContent(tfs[j])) {
                    hasFlow = true;
                    break;
                }
            } catch (e) {}
        }
        info.push({ pg: pg, label: isDividerLabelLike(pg, flowIds, allowSolo),
                    flow: hasFlow });
        if ((i + 1) % 40 === 0) {
            wlog("고아 간지 검사 진행: " + (i + 1) + "/" + pagesArr.length);
        }
    }
    var removed = 0;
    for (var k = info.length - 1; k >= 0; k--) {
        if (!info[k].label) { continue; }
        var orphan = true;
        for (var m = k + 1; m < info.length; m++) {
            if (info[m].label) { break; }
            if (info[m].flow) { orphan = false; break; }
        }
        if (!orphan) { continue; }
        // 동반 왼쪽 빈 페이지(프레임 0 또는 전부 공백, 라벨/플로우 아님)도
        // 함께 삭제 — 스프레드 좌우 짝수 유지 (뒤 간지 정렬 무영향).
        var names = [String(info[k].pg.name)];
        var companion = null;
        if (k > 0 && !info[k - 1].label && !info[k - 1].flow) {
            var ptfs = info[k - 1].pg.textFrames;
            var blank = true;
            for (var q = 0; q < ptfs.length; q++) {
                if (!isBlankFrameContent(ptfs[q])) { blank = false; break; }
            }
            if (blank) {
                companion = info[k - 1].pg;
                names.unshift(String(companion.name));
            }
        }
        try {
            info[k].pg.remove();
            if (companion) { companion.remove(); }
            removed++;
            wlog("고아 간지 스프레드 삭제: p" + names.join(", p")
                 + " (뒤따르는 콘텐츠 없음)");
        } catch (e6) {
            wlog("[경고] 고아 간지 삭제 실패: " + e6);
        }
    }
    wlog("고아 간지 스프레드: " + removed + "개 삭제");
}

// ── W23 op: 문제 단위 펼침면 킵 (plan.question_keep — opt-in) ───────────────
// 사용자 확정 스펙 (r13 피드백 F4): 한 문제(발문+지문+선지 전체)가 왼쪽→
// 오른쪽 페이지로 이어지는 것은 허용, 오른쪽 페이지에서 잘려 다음 장
// (스프레드 넘김)으로 이어지는 것은 금지 — 그 문제 전체를 다음 페이지로
// 민다. 문제 시작 인덱스는 플랜이 계산(question_keep.flows[step].starts —
// plan.question_keep_op, 발문/그룹 인트로 스타일 단락. 인덱스 0 제외).
// 밀기 = NEXT_PAGE startParagraph (텍스트 무삽입 — 검수 1:1 대조 유지).
// 캐스케이드: 한 건 밀 때마다 recompose + 재실측, 상한 = 시작점 수×2+10.
// 왼쪽에서 시작하고도 스프레드를 넘는 문제(한 문제가 2페이지 초과)는
// 밀어도 해소 불가 — 경고 지목만. 밀어낸 결과 생기는 페이지 하단 공백은
// 허용(스펙), 스토리 끝 오버플로우는 expandStoryOverflow로 즉시 확장.
function spreadIdOf(doc, pg) {
    // 물리 스프레드 번호 — 비대면 문서는 documentOffset 홀짝 (offset 0 =
    // p1 = 오른쪽 단독 스프레드 0). pageSideOf와 동일 판정 계열.
    try { return Math.floor((pg.documentOffset + 1) / 2); } catch (e) {}
    return -1;
}

function enforceQuestionKeep(doc, flowStories, op) {
    var flowsCfg = (op && op.flows) || {};
    var totalPushed = 0;
    for (var step in flowsCfg) {
        var rec = flowStories[step];
        if (!rec) { continue; }
        var story = rec.story;
        var starts = flowsCfg[step].starts || [];
        if (starts.length === 0) { continue; }
        var pushed = 0;
        var skipped = 0;
        var iter = 0;
        var noFix = {};
        var limit = starts.length * 2 + 10;
        while (iter < limit) {
            iter++;
            try { story.recompose(); } catch (e0) {}
            var paras = story.paragraphs.everyItem().getElements();
            var hit = -1;
            for (var k = 0; k < starts.length; k++) {
                if ((k + 1) % 40 === 0) {
                    wlog("문제단위킵 검사 진행: " + step + " "
                         + (k + 1) + "/" + starts.length);
                }
                var si = starts[k];
                if (si <= 0 || si >= paras.length || noFix[si]) { continue; }
                var ei = (k + 1 < starts.length
                          && starts[k + 1] <= paras.length)
                    ? starts[k + 1] - 1 : paras.length - 1;
                var sf = null, ef = null;
                try { sf = paras[si].parentTextFrames[0]; } catch (e1) {}
                try {
                    var efs = paras[ei].parentTextFrames;
                    ef = efs[efs.length - 1];
                } catch (e2) {}
                if (!sf || !ef) { continue; }   // overset — 확장이 처리
                var sp = null, ep = null;
                try { sp = sf.parentPage; ep = ef.parentPage; } catch (e3) {}
                if (!sp || !ep) { continue; }
                if (spreadIdOf(doc, ep) <= spreadIdOf(doc, sp)) { continue; }
                if (pageSideOf(doc, sp) !== "R") {
                    // 왼쪽 시작 + 스프레드 초과 — 밀어도 해소 불가
                    noFix[si] = true;
                    skipped++;
                    wlog("[경고] 문제단위킵: " + step + " 단락 " + si
                         + " 문제가 스프레드 초과 (왼쪽 시작) — 밀기로 해소"
                         + " 불가, 수동 확인");
                    continue;
                }
                hit = k;
                break;
            }
            if (hit < 0) { break; }
            try {
                paras[starts[hit]].startParagraph = StartParagraph.NEXT_PAGE;
                pushed++;
                wlog("문제단위킵: " + step + " 단락 " + starts[hit]
                     + " 다음 페이지로 밀기 (" + pushed + "건째)");
            } catch (e4) {
                noFix[starts[hit]] = true;
                wlog("[경고] 문제단위킵 밀기 실패(단락 " + starts[hit]
                     + "): " + e4);
            }
            var grew = expandStoryOverflow(doc, step + " 문제단위킵", story);
            if (grew > 0) {
                wlog(step + " 문제단위킵: 오버플로우 페이지 +" + grew);
            }
        }
        wlog("문제단위킵: " + step + " 밀기 " + pushed + "건 / 해소 불가 "
             + skipped + "건");
        totalPushed += pushed;
    }
    return totalPushed;
}

// ── W55: 문제단위킵 밀기 완화 (ratchet 해제) ────────────────────────────────
// 밀기(NEXT_PAGE)는 단락 속성이라 이후 다른 밀기/리플로우로 위치가 바뀌어
// 밀 필요가 없어져도 남는다 — 앞 문제가 왼쪽 페이지 1단에서 끝나는데 다음
// 문제가 강제로 새 페이지로 가며 2단이 통째로 빈다 (local_mrk_refix1 실증:
// p68 2단 공백 — 단락 263이 1라운드에 밀린 뒤 15건의 후속 밀기로 무효화.
// 사용자 지적 "문제가 붙어도 되는 부분에 왜 떨어져 있어").
// 수렴 후 문서 순서로: NEXT_PAGE 발문을 시험 삼아 풀고(ANYWHERE) 재조판해
// 스프레드 걸침이 재발하면 복원, 아니면 완화 확정. 완화로 뒤가 당겨지면
// 다음 후보들은 갱신된 상태에서 재평가된다.
// W56: 발문고아킵(NEXT_FRAME) 완화 — 발문 밀기도 단락 속성이라 후속
// 리플로우로 무효화돼도 남아 단 하나가 반쯤 비는 구멍을 만든다
// (v2_5 실증: 50번 조건박스 아래·80번 지문 아래 단 하단 대공백 —
// 사용자 재재지적). 시험 완화 후 고아 조건(발문고아)·스프레드 걸침이
// 재발하면 복원한다.
function _stemOrphanAt(paras, starts, k, minLines) {
    var si = starts[k];
    if (si <= 0 || si >= paras.length) { return false; }
    var ei = (k + 1 < starts.length && starts[k + 1] <= paras.length)
        ? starts[k + 1] - 1 : paras.length - 1;
    var stemOnly = (ei <= si);
    var stem = paras[si];
    var f = null;
    try { f = stem.parentTextFrames[0]; } catch (e1) {}
    if (!f) { return true; }   // overset 상태 — 복원이 안전
    var fLines = [];
    try { fLines = f.lines.everyItem().getElements(); } catch (e2) {}
    if (!fLines || fLines.length === 0) { return false; }
    var stemStart = -1, stemLen = 0;
    try {
        stemStart = stem.characters[0].index;
        stemLen = stem.characters.length;
    } catch (e3) { return false; }
    var stemEnd = stemStart + stemLen;
    var bodyLines = 0;
    var lastEnd = -1;
    for (var li = 0; li < fLines.length; li++) {
        var c0 = -1, cn = 0;
        try {
            c0 = fLines[li].characters[0].index;
            cn = fLines[li].characters.length;
        } catch (e5) { continue; }
        if (c0 + cn - 1 > lastEnd) { lastEnd = c0 + cn - 1; }
        if (c0 >= stemEnd) { bodyLines++; }
    }
    if (stemOnly) { return lastEnd <= stemEnd - 1; }
    var qEnd = -1;
    try {
        var eP = paras[ei];
        qEnd = eP.characters[0].index + eP.characters.length - 1;
    } catch (e6) { return false; }
    if (qEnd <= lastEnd) { return false; }   // 문항이 프레임 안에서 끝남
    return bodyLines < minLines;
}

function relaxStemKeep(doc, flowStories, op) {
    var minLines = (op.stem_keep && op.stem_keep.min_lines) || 2;
    var flowsCfg = (op && op.flows) || {};
    var totalRelaxed = 0;
    for (var step in flowsCfg) {
        var rec = flowStories[step];
        if (!rec) { continue; }
        var story = rec.story;
        var starts = flowsCfg[step].stem_starts
            || flowsCfg[step].starts || [];
        if (starts.length === 0) { continue; }
        var relaxed = 0;
        for (var k = 0; k < starts.length; k++) {
            if ((k + 1) % 40 === 0) {
                wlog("발문고아 완화 진행: " + step + " "
                     + (k + 1) + "/" + starts.length);
            }
            var si = starts[k];
            try { story.recompose(); } catch (e0) {}
            var paras = story.paragraphs.everyItem().getElements();
            if (si <= 0 || si >= paras.length) { continue; }
            var cur = null;
            try { cur = paras[si].startParagraph; } catch (e1) { continue; }
            if (cur !== StartParagraph.NEXT_FRAME) { continue; }
            try {
                paras[si].startParagraph = StartParagraph.ANYWHERE;
                story.recompose();
            } catch (e2) { continue; }
            paras = story.paragraphs.everyItem().getElements();
            var bad = _stemOrphanAt(paras, starts, k, minLines);
            if (!bad) {
                // 스프레드 걸침 재발 검사 (당겨진 시작이 오른쪽 페이지로
                // 올라가며 문항이 다음 장에 걸칠 수 있다)
                var ei = (k + 1 < starts.length
                          && starts[k + 1] <= paras.length)
                    ? starts[k + 1] - 1 : paras.length - 1;
                try {
                    var sf = paras[si].parentTextFrames[0];
                    var efs = paras[ei].parentTextFrames;
                    var ef = efs[efs.length - 1];
                    var sp = sf.parentPage, ep = ef.parentPage;
                    if (!sp || !ep) { bad = true; }
                    else if (spreadIdOf(doc, ep) > spreadIdOf(doc, sp)) {
                        bad = true;
                    }
                } catch (e3) { bad = true; }
            }
            if (bad) {
                try {
                    paras[si].startParagraph = StartParagraph.NEXT_FRAME;
                    story.recompose();
                } catch (e4) {}
            } else {
                relaxed++;
            }
        }
        if (relaxed > 0) {
            wlog("발문고아 완화: " + step + " 불필요 밀기 " + relaxed
                 + "건 해제");
        }
        totalRelaxed += relaxed;
    }
    return totalRelaxed;
}

function relaxQuestionKeep(doc, flowStories, op) {
    var flowsCfg = (op && op.flows) || {};
    var totalRelaxed = 0;
    for (var step in flowsCfg) {
        var rec = flowStories[step];
        if (!rec) { continue; }
        var story = rec.story;
        var starts = flowsCfg[step].starts || [];
        if (starts.length === 0) { continue; }
        var relaxed = 0;
        for (var k = 0; k < starts.length; k++) {
            if ((k + 1) % 40 === 0) {
                wlog("문제단위킵 완화 진행: " + step + " "
                     + (k + 1) + "/" + starts.length);
            }
            var si = starts[k];
            try { story.recompose(); } catch (e0) {}
            var paras = story.paragraphs.everyItem().getElements();
            if (si <= 0 || si >= paras.length) { continue; }
            var cur = null;
            try { cur = paras[si].startParagraph; } catch (e1) { continue; }
            if (cur !== StartParagraph.NEXT_PAGE) { continue; }
            try {
                paras[si].startParagraph = StartParagraph.ANYWHERE;
                story.recompose();
            } catch (e2) { continue; }
            // 재평가 — 스프레드 걸침이면 복원
            paras = story.paragraphs.everyItem().getElements();
            var ei = (k + 1 < starts.length && starts[k + 1] <= paras.length)
                ? starts[k + 1] - 1 : paras.length - 1;
            var bad = false;
            try {
                var sf = paras[si].parentTextFrames[0];
                var efs = paras[ei].parentTextFrames;
                var ef = efs[efs.length - 1];
                var sp = sf.parentPage, ep = ef.parentPage;
                if (!sp || !ep) { bad = true; }
                else if (spreadIdOf(doc, ep) > spreadIdOf(doc, sp)) { bad = true; }
            } catch (e3) { bad = true; }
            if (bad) {
                try {
                    paras[si].startParagraph = StartParagraph.NEXT_PAGE;
                    story.recompose();
                } catch (e4) {}
            } else {
                relaxed++;
            }
        }
        if (relaxed > 0) {
            wlog("문제단위킵 완화: " + step + " 불필요 밀기 " + relaxed
                 + "건 해제");
            // 완화로 뒤가 당겨지며 빈 꼬리 페이지가 생길 수 있다 — 스토리
            // 마지막 페이지부터 스토리 프레임이 전부 빈 페이지를 제거.
            var trimmed = 0;
            var guard = 0;
            while (guard < 30) {
                guard++;
                var spgs = storyPagesInOrder(story);
                if (spgs.length === 0) { break; }
                var lastPg = spgs[spgs.length - 1];
                var fs = framesOfStoryOnPage(story, lastPg);
                var allBlank = fs.length > 0;
                for (var fi = 0; fi < fs.length; fi++) {
                    if (!isBlankFrameContent(fs[fi])) { allBlank = false; break; }
                }
                if (!allBlank) { break; }
                var others = false;
                try {
                    var tfsAll = lastPg.textFrames;
                    for (var ti = 0; ti < tfsAll.length; ti++) {
                        var stId = null;
                        try { stId = tfsAll[ti].parentStory.id; } catch (eT) {}
                        if (stId !== story.id
                                && !isBlankFrameContent(tfsAll[ti])) {
                            others = true;
                            break;
                        }
                    }
                } catch (e5) {}
                if (others) { break; }
                try { lastPg.remove(); trimmed++; } catch (e6) { break; }
            }
            if (trimmed > 0) {
                wlog("문제단위킵 완화: 빈 꼬리 페이지 " + trimmed + "개 정리");
            }
        }
        totalRelaxed += relaxed;
    }
    return totalRelaxed;
}

// ── W40 결함 2: 발문 고아 방지 (프레임판 question_keep) ─────────────────────
// 프레임 하단에 발문만 남거나 발문+본문 minLines-1줄 이하만 남고 문제가
// 다음 프레임으로 이어지면, 발문(문제 시작)을 다음 프레임으로 민다.
// starts는 question_keep 계약(문제 시작 단락 인덱스)을 재사용. 반드시
// enforceQuestionKeep(스프레드 킵) 이후 호출 — step3 페이지는 프레임
// 1개라 NEXT_FRAME 밀기가 스프레드를 새로 넘길 수 있는 케이스(오른쪽
// 페이지 하단)는 스프레드 킵이 먼저 NEXT_PAGE로 해소한 상태다.
function enforceStemKeep(doc, flowStories, op) {
    var minLines = (op.stem_keep && op.stem_keep.min_lines) || 2;
    var flowsCfg = (op && op.flows) || {};
    var totalPushed = 0;
    for (var step in flowsCfg) {
        var rec = flowStories[step];
        if (!rec) { continue; }
        var story = rec.story;
        // W52: 세트 킵(starts)과 별개로 발문 고아 방지는 모든 발문 대상
        var starts = flowsCfg[step].stem_starts
            || flowsCfg[step].starts || [];
        if (starts.length === 0) { continue; }
        var pushed = 0;
        var iter = 0;
        var noFix = {};
        var limit = starts.length + 10;
        while (iter < limit) {
            iter++;
            try { story.recompose(); } catch (e0) {}
            var paras = story.paragraphs.everyItem().getElements();
            var hit = -1;
            for (var k = 0; k < starts.length; k++) {
                if ((k + 1) % 40 === 0) {
                    wlog("발문고아 검사 진행: " + step + " " + (k + 1)
                         + "/" + starts.length);
                }
                var si = starts[k];
                if (si <= 0 || si >= paras.length || noFix[si]) { continue; }
                var ei = (k + 1 < starts.length
                          && starts[k + 1] <= paras.length)
                    ? starts[k + 1] - 1 : paras.length - 1;
                // W40 r2 — 발문 단독(뒤따르는 답란/본문 단락 0개. 원고에
                // 답란이 빠진 문항)도 프레임 최하단이면 고아다. 기존 계약은
                // ei<=si 를 통째로 건너뛰어 이 케이스를 못 밀었다.
                var stemOnly = (ei <= si);
                if (stemOnly && k + 1 >= starts.length) { continue; }
                var stem = paras[si];
                var f = null;
                try { f = stem.parentTextFrames[0]; } catch (e1) {}
                if (!f) { continue; }   // overset — 확장이 처리
                var fLines = [];
                try { fLines = f.lines.everyItem().getElements(); }
                catch (e2) { fLines = []; }
                if (!fLines || fLines.length === 0) { continue; }
                var stemStart = -1, stemLen = 0;
                try {
                    stemStart = stem.characters[0].index;
                    stemLen = stem.characters.length;
                } catch (e3) { continue; }
                var stemEnd = stemStart + stemLen;
                // 프레임 첫 라인이 이미 발문이면(프레임 최상단) 밀어도
                // 해소 불가 — 스킵 (무한 밀기 방지)
                var firstIdx = -1;
                try { firstIdx = fLines[0].characters[0].index; }
                catch (e4) {}
                if (firstIdx >= stemStart) { noFix[si] = true; continue; }
                var bodyLines = 0;
                var lastEnd = -1;
                for (var li = 0; li < fLines.length; li++) {
                    var c0 = -1, cn = 0;
                    try {
                        c0 = fLines[li].characters[0].index;
                        cn = fLines[li].characters.length;
                    } catch (e5) { continue; }
                    if (c0 + cn - 1 > lastEnd) { lastEnd = c0 + cn - 1; }
                    if (c0 >= stemEnd) { bodyLines++; }
                }
                if (stemOnly) {
                    // 프레임의 마지막 줄이 이 발문이면 고아 — 다음 프레임으로
                    // 민다. 뒤에 다른 내용이 남아 있으면 고아가 아니다.
                    if (lastEnd > stemEnd - 1) { continue; }
                    hit = si;
                    break;
                }
                var qEnd = -1;
                try {
                    var eP = paras[ei];
                    qEnd = eP.characters[0].index + eP.characters.length - 1;
                } catch (e6) { continue; }
                if (qEnd <= lastEnd) { continue; }   // 문제가 프레임 안에서 끝남
                if (bodyLines >= minLines) { continue; }
                hit = si;
                break;
            }
            if (hit < 0) { break; }
            try {
                paras[hit].startParagraph = StartParagraph.NEXT_FRAME;
                pushed++;
                noFix[hit] = true;
                wlog("발문고아킵: " + step + " 단락 " + hit
                     + " 다음 프레임으로 밀기 (" + pushed + "건째)");
            } catch (e7) {
                noFix[hit] = true;
                wlog("[경고] 발문고아킵 밀기 실패(단락 " + hit + "): " + e7);
            }
            var grew = expandStoryOverflow(doc, step + " 발문고아킵", story);
            if (grew > 0) {
                wlog(step + " 발문고아킵: 오버플로우 페이지 +" + grew);
            }
        }
        wlog("발문고아킵: " + step + " 밀기 " + pushed + "건");
        totalPushed += pushed;
    }
    return totalPushed;
}

// ── W21 op: 섹션 시작 좌/우 마스터 정합 (plan.section_masters가 있을 때만) ──
// 페이지 정리로 섹션 시작이 좌→우(또는 우→좌)로 밀리면 시작 페이지 마스터를
// 좌/우 변형으로 교체한다. [원본]워크북_C 실측: STEP1 섹션이 오른쪽에서
// 시작하면 B-마스터(어휘 선택 2, p13), 왼쪽이면 A-마스터. STEP2는 C/D 쌍.
// 쌍 데이터는 flow.target.master_pair (step_map.json 계약) — 계약 없는
// 플로우/내지는 무접촉. 반드시 page_cleanup 이후 호출 (좌/우 확정 후).
// ── W52: 스텝3 콘텐츠 페이지 마스터 정규화 ──────────────────────────────────
// 문제단위킵 밀기/확장으로 스텝3 본문이 템플릿의 MEMO(M) 여백 페이지까지
// 흘러들면, 내용이 있는 페이지에 MEMO 헤더·점 그리드가 그대로 남는다
// (0645d4a7 v2_6 실증: p51 — 사용자 지적 '빈 페이지가 아닌데 왜 메모
// 마스터'). 스텝3 스토리 페이지들의 다수 마스터(최빈값)를 기준으로,
// 내용이 실린 소수 마스터 페이지를 다수 마스터로 재할당한다.
function normalizeStep3ContentMasters(doc, flowStories) {
    for (var step in flowStories) {
        var rec = flowStories[step];
        if (!rec || !rec.isMaster) { continue; }
        var pages = [];
        try { pages = storyPagesInOrder(rec.story); } catch (e0) { continue; }
        if (pages.length < 2) { continue; }
        var counts = {};
        var best = null;
        for (var pi = 0; pi < pages.length; pi++) {
            var mn = "";
            try {
                mn = pages[pi].appliedMaster ? pages[pi].appliedMaster.name : "";
            } catch (e1) {}
            if (!mn) { continue; }
            counts[mn] = (counts[mn] || 0) + 1;
            if (!best || counts[mn] > counts[best]) { best = mn; }
        }
        if (!best || counts[best] < 2) { continue; }
        var fixed = 0;
        for (var pj = 0; pj < pages.length; pj++) {
            var mn2 = "";
            try {
                mn2 = pages[pj].appliedMaster ? pages[pj].appliedMaster.name : "";
            } catch (e2) {}
            if (mn2 === best) { continue; }
            // 내용이 실린 페이지만 (빈 꼬리 페이지는 page_cleanup 소관)
            var hasContent = false;
            try {
                var pfs = framesOfStoryOnPage(rec.story, pages[pj]);
                for (var fi = 0; fi < pfs.length; fi++) {
                    if (!isBlankFrameContent(pfs[fi])) { hasContent = true; break; }
                }
            } catch (e3) {}
            if (!hasContent) { continue; }
            try {
                pages[pj].appliedMaster = doc.masterSpreads.itemByName(best);
                fixed++;
            } catch (e4) {}
        }
        if (fixed > 0) {
            wlog(step + " 콘텐츠 페이지 마스터 정규화: " + fixed + "개 → " + best);
        }
    }
}

function fixSectionMasters(doc, flowStories) {
    var n = 0;
    var masterCache = {};
    // 비대면(facing 아님) 문서는 pg.side가 전부 RIGHT_HAND ([원본]워크북_C
    // 실측) — 인쇄 물리 좌/우는 페이지 순서 홀짝으로 판정 (offset 0 = p1 =
    // 오른쪽). facing 문서만 pg.side를 신뢰한다.
    var facing = false;
    try { facing = doc.documentPreferences.facingPages; } catch (e) {}
    function sideOf(pg) {
        if (facing) {
            try {
                return (pg.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
            } catch (e) { return "R"; }
        }
        try {
            return (pg.documentOffset % 2 === 0) ? "R" : "L";
        } catch (e) { return "R"; }
    }
    function masterByName(name) {
        if (masterCache[name] !== undefined) { return masterCache[name]; }
        var m = null;
        try { m = doc.masterSpreads.itemByName(name); m.name; } catch (e) { m = null; }
        masterCache[name] = m;
        if (!m) { wlog("[경고] 섹션 마스터 없음: " + name); }
        return m;
    }
    for (var step in flowStories) {
        var rec = flowStories[step];
        var pair = rec.masterPair;
        if (!pair || rec.isMaster) { continue; }
        var pages = storyPagesInOrder(rec.story);
        if (pages.length === 0) { continue; }
        var pg = pages[0];
        var want = (sideOf(pg) === "R") ? pair.right : pair.left;
        if (!want) { continue; }
        var cur = "";
        try { cur = pg.appliedMaster ? String(pg.appliedMaster.name) : ""; } catch (e) {}
        if (cur === want) { continue; }
        var m2 = masterByName(want);
        if (!m2) { continue; }
        try {
            pg.appliedMaster = m2;
            n++;
            wlog("섹션 마스터: " + step + " p" + pg.name + " (" + cur + " → " + want + ")");
        } catch (e) {}
    }
    wlog("섹션 시작 마스터 정합: " + n + "개 교체");
}

// ── W53 op: 스텝 콘텐츠 페이지의 빈(M) 마스터 복구 ──────────────────────────
// 배재2 워크북01 실측 (검수자 지적 "머리 부분 디자인이 안 입혀 있습니다"):
// STEP1 C2(빈칸 어휘) 스토리가 템플릿 MEMO(M) 여백 페이지까지 흘러들어
// p106만 헤더 바·사이드탭·페이지번호가 통째로 없이 납품됐다. W52
// normalizeStep3ContentMasters는 스텝3 메인 스토리(rec.isMaster)만 대상이라
// 섹션 스토리는 무방비였다.
//   대상: 콘텐츠가 실린 페이지 & 마스터가 M/없음 (그 외 소수 마스터는
//         무접촉 — 좌/우 변형(A/B·C/D)을 다수결로 뭉개지 않는다)
//   제외: 섹션 시작 페이지(pages[0]) — 좌/우 계약은 fixSectionMasters 소관
//   게이트: master_pair 계약이 있는 스토리만 (계약 없는 커스텀 내지 무접촉)
function repairStepContentMasters(doc, flowStories) {
    var fixed = 0;
    for (var step in flowStories) {
        var rec = flowStories[step];
        if (!rec || rec.isMaster || !rec.masterPair) { continue; }
        var pages = [];
        try { pages = storyPagesInOrder(rec.story); } catch (e0) { continue; }
        if (pages.length < 2) { continue; }
        // 다수 마스터 (섹션 시작 페이지 제외 — 좌/우 변형이 최빈값을 흔든다)
        var counts = {};
        var best = null;
        for (var pi = 1; pi < pages.length; pi++) {
            var mn = "";
            try {
                mn = pages[pi].appliedMaster
                    ? String(pages[pi].appliedMaster.name) : "";
            } catch (e1) {}
            if (!mn || isEmptyMasterName(doc, mn)) { continue; }
            counts[mn] = (counts[mn] || 0) + 1;
            if (!best || counts[mn] > counts[best]) { best = mn; }
        }
        if (!best) { continue; }
        for (var pj = 1; pj < pages.length; pj++) {
            var cur = "";
            try {
                cur = pages[pj].appliedMaster
                    ? String(pages[pj].appliedMaster.name) : "";
            } catch (e2) {}
            if (cur && !isEmptyMasterName(doc, cur)) { continue; }
            var hasContent = false;
            try {
                var pfs = framesOfStoryOnPage(rec.story, pages[pj]);
                for (var fi = 0; fi < pfs.length; fi++) {
                    if (!isBlankFrameContent(pfs[fi])) {
                        hasContent = true;
                        break;
                    }
                }
            } catch (e3) {}
            if (!hasContent) { continue; }   // 빈 꼬리 페이지는 정리 소관
            try {
                pages[pj].appliedMaster = doc.masterSpreads.itemByName(best);
                fixed++;
                wlog("콘텐츠 마스터 복구: " + step + " p" + pages[pj].name
                     + " (" + (cur || "없음") + " → " + best + ")");
            } catch (e4) {}
        }
    }
    wlog("스텝 콘텐츠 페이지 빈 마스터 복구: " + fixed + "개");
}

// 빈(메모) 마스터 판정 — namePrefix "M" (내지 공통 규약. 이름 문자열은
// 한글 NFD라 접두만 비교한다).
function isEmptyMasterName(doc, name) {
    if (!name || name === "[None]") { return true; }
    var pfx = "";
    try { pfx = String(doc.masterSpreads.itemByName(name).namePrefix); }
    catch (e) { return false; }
    return pfx === "M";
}

// ── 간지 텍스트 업데이트 (v1 run.jsx 16.7 이식 — plan.divider가 있을 때만) ──
// 간지 페이지 = 마스터 [None](또는 없음) + 텍스트프레임 1개 + 첫 단락에
// 한글. 1단락=line1, 2단락=line2.
// v1과 달리 오른쪽(RIGHT_HAND) 조건을 걸지 않는다 (W19 결함 D5): 앞선
// 페이지 삭제(page_cleanup)로 간지가 왼쪽 페이지로 밀릴 수 있고(c05 실측
// p122 잔재 — v1 16.7도 같은 조건이라 실물 동일), 이 계열 내지에서 마스터
// [None]+프레임 1개+한글 첫 단락 조합은 간지뿐이라 좌우 무관하게 안전
// (c04/c05/c20 덤프 실측 — 매칭 스토리 전부 간지 라벨).
// W51 (job 0645d4a7 수특라이트 실증): 커스텀 내지의 간지 프레임이 그룹
// 안에 있거나 페이지에 장식 프레임이 더 있으면 기존 '직속 텍스트프레임
// 정확히 1개' 조건이 실패해 업데이트 0개 — 원본 문구('26년 3월')가 그대로
// 인쇄됐다. 프레임 열거를 allPageItems(그룹 내부 포함)로 넓히고, 판정을
// 프레임 수가 아니라 '간지 프레임 구조'(단락 2+ / 첫 단락 한글 / 2행이
// 기수 표기(YY년 M월·N강·N과·Unit N) 또는 후보 유일)로 바꾼다.
var RE_DIVIDER_LINE2 = /^\s*(?:\d+\s*년\s*\d+\s*월|\d+\s*강|\d+\s*과|Unit\s*\.?\s*\d*)\s*$/i;

function updateDividerPages(doc, line1, line2) {
    var n = 0;
    var diag = [];   // W51 진단: 후보 탈락 상태 (0개일 때만 로그)
    // W51 3차 (refix3/4 진단 실증): 페이지→프레임 열거 자체를 폐기하고
    // **문서 전역 스토리**를 훑는다. 실행 시점의 간지 텍스트는 페이지
    // 프레임이 아니라 '간지' 마스터 스프레드의 프레임에 있을 수 있고
    // (page.allPageItems에 안 잡힘 — [None] 게이트/프레임 열거가 전부
    // 헛돎), doc.stories는 마스터 프레임 스토리까지 포함한다. 마스터
    // 원본을 갱신하면 그 마스터를 쓰는 간지 페이지 전부가 갱신된다.
    // 간지 스토리 판정(내용 구조): 2~3행 + 첫 행 한글 + 2행이 기수 표기
    // (YY년 M월·N강·N과·Unit N) — 발문/러닝헤더류와 충돌하지 않는다.
    for (var si = 0; si < doc.stories.length; si++) {
        var st = doc.stories[si];
        var whole = "";
        try { whole = String(st.contents || ""); } catch (eW) { continue; }
        if (whole.length > 120) { continue; }
        var segs = whole.replace(/[\r\n]+$/, "").split(/[\r\n]/);
        if (segs.length < 2 || segs.length > 3) { continue; }
        if (!/[가-힣]/.test(segs[0])) { continue; }
        if (!RE_DIVIDER_LINE2.test(segs[1])) {
            if (diag.length < 4 && /[년월강과]|Unit/i.test(segs[1])) {
                diag.push("l2미매치=" + String(segs[1]).substr(0, 16));
            }
            continue;
        }
        try {
            var cps = st.paragraphs;
            if (cps.length >= 2) {
                // 단락 2개형 (모의고사 원본 내지)
                cps[0].contents = line1 + "\r";
                cps[1].contents = line2 + "\r";
            } else {
                // 강제 줄바꿈 1단락형 (수특라이트 커스텀 내지 실측) —
                // 행별 문자 범위 교체 (서식 보존)
                var t0 = String(st.contents || "");
                var b0 = t0.search(/[\n\r]/);
                if (b0 <= 0) { continue; }
                st.characters.itemByRange(0, b0 - 1).contents = line1;
                var t1 = String(st.contents || "");
                var b1 = t1.search(/[\n\r]/);
                var tail = t1.replace(/[\r\n]+$/, "");
                if (b1 >= 0 && b1 + 1 <= tail.length - 1) {
                    st.characters.itemByRange(b1 + 1, tail.length - 1)
                        .contents = line2;
                }
            }
            n++;
        } catch (e) {}
    }
    wlog("간지 텍스트 업데이트: " + n + "개 (" + line1 + " / " + line2 + ")");
    if (n === 0) {
        // W51: 침묵 금지 — 간지를 하나도 못 찾으면 [경고]로 지목
        wlog("[경고] 간지 텍스트 업데이트 0개 — 간지 프레임 구조가 "
             + "기대(마스터 없음 페이지 + 한글 2행 프레임)와 다름"
             + (diag.length ? " | 진단: " + diag.join(" / ") : ""));
    }
}

// ── 교과서 후처리 (v1 run.jsx 16.8 이식 — plan.textbook_postprocess) ────────
// 빈 A-마스터 페이지 → B-마스터, 빈 C-마스터 페이지 → D-마스터.
// ── W40 결함 1: 다열 선지 열 정렬 — 자동 탭스톱 (v1 실물 실측 관행) ─────────
// v1 손마무리 실물(배재2_워크북01 실측 120단락): 명시 탭스톱 없이 기본
// 12.7mm 탭 그리드에 열을 앉히고, 열이 어긋나면 탭/공백을 손으로 추가해
// 모든 행이 같은 그리드 스톱에 정렬되게 맞춘다 (헤더 (A)는 열 내용 위에
// 공백으로 눈대중 센터링). 자동화: 그룹(연속 탭 선지 단락)별로 열 최장
// 항목을 실측해 다음 그리드 스톱(최장 끝 + min_gap 이상)에 명시 LEFT
// 탭스톱을 부여 — 손 결과와 같은 기하를 결정적으로 재현한다. 헤더 행은
// 각 열 중앙에 라벨이 오도록 자체 스톱/들여쓰기 부여. 그리드로 프레임을
// 넘치면 비그리드 최소 간격으로 폴백, 그래도 넘치면 [경고].
function applyChoiceTabs(doc, flowStories, op) {
    var grid = op.grid || 12.7;
    var minGap = (op.min_gap === undefined || op.min_gap === null)
        ? 2 : op.min_gap;
    var styleTok = op.style_contains || "선지";   // "선지"
    var steps = op.steps || [];
    var groups = 0, warned = 0;

    function cellWidths(para, txt) {
        // 탭 구분 셀별 렌더 폭 실측 (문자 단위 — 줄바꿈 무관)
        var widths = [];
        var cur = 0;
        var chars = para.characters;
        var n = Math.min(chars.length, txt.length);
        for (var ci = 0; ci < n; ci++) {
            var ch = txt.charAt(ci);
            if (ch == "\t") { widths.push(cur); cur = 0; continue; }
            if (ch == "\r" || ch == "\n") { break; }
            try {
                cur += chars[ci].endHorizontalOffset
                    - chars[ci].horizontalOffset;
            } catch (e) {}
        }
        widths.push(cur);
        return widths;
    }

    function isHeaderRow(t) {
        var s = t.replace(/^[\s ]+/, "");
        return s.charAt(0) == "(" && s.indexOf("_") < 0;
    }

    for (var sti = 0; sti < steps.length; sti++) {
        var rec = flowStories[steps[sti]];
        if (!rec) { continue; }
        var story = rec.story;
        try { story.recompose(); } catch (e0) {}
        var texts = [], styles = [], paras = null;
        try {
            texts = story.paragraphs.everyItem().contents;
            styles = story.paragraphs.everyItem().appliedParagraphStyle;
            if (!(texts instanceof Array)) { texts = [texts]; }
            if (!(styles instanceof Array)) { styles = [styles]; }
        } catch (e1) { continue; }

        function isTabRow(x) {
            if (String(texts[x]).indexOf("\t") < 0) { return false; }
            var nm = "";
            try { nm = styles[x].name; } catch (e) {}
            return nm.indexOf(styleTok) >= 0;
        }

        var i = 0;
        while (i < texts.length) {
            if (!isTabRow(i)) { i++; continue; }
            var j = i;
            while (j < texts.length && isTabRow(j)) { j++; }
            // ── 그룹 [i, j) 처리 ──
            if (paras === null) {
                try { paras = story.paragraphs.everyItem().getElements(); }
                catch (e2) { break; }
            }
            var rows = [];
            var maxTabs = 0;
            for (var r = i; r < j; r++) {
                var t = String(texts[r]);
                var w = cellWidths(paras[r], t);
                var nTabs = w.length - 1;
                if (nTabs > maxTabs) { maxTabs = nTabs; }
                rows.push({ idx: r, txt: t, w: w,
                            header: isHeaderRow(t) });
            }
            if (maxTabs === 0) { i = j; continue; }
            // 열 최장 폭 (헤더 제외 — 헤더는 자체 스톱)
            var colw = [];
            var hasItem = false;
            for (var r2 = 0; r2 < rows.length; r2++) {
                if (rows[r2].header) { continue; }
                hasItem = true;
                for (var c = 0; c < rows[r2].w.length; c++) {
                    if (colw[c] === undefined || rows[r2].w[c] > colw[c]) {
                        colw[c] = rows[r2].w[c];
                    }
                }
            }
            if (!hasItem) {
                for (var r3 = 0; r3 < rows.length; r3++) {
                    for (var c3 = 0; c3 < rows[r3].w.length; c3++) {
                        if (colw[c3] === undefined
                                || rows[r3].w[c3] > colw[c3]) {
                            colw[c3] = rows[r3].w[c3];
                        }
                    }
                }
            }
            // 프레임 텍스트 폭 + 시작 들여쓰기 (0열 시작 = 첫 줄 위치:
            // 선지 스타일은 내어쓰기(fli<0)라 lind가 아니라 lind+fli)
            var lind = 0, fli = 0, frameW = null;
            var itemRow = null;
            for (var r4 = 0; r4 < rows.length; r4++) {
                if (!rows[r4].header) { itemRow = rows[r4]; break; }
            }
            if (itemRow === null) { itemRow = rows[0]; }
            try { lind = paras[itemRow.idx].leftIndent; } catch (e3) {}
            try { fli = paras[itemRow.idx].firstLineIndent; } catch (e3b) {}
            try {
                var tf = paras[itemRow.idx].parentTextFrames[0];
                var gbT = tf.geometricBounds;
                var inL = 0, inR = 0;
                try {
                    var insT = tf.textFramePreferences.insetSpacing;
                    if (insT instanceof Array) {
                        inL = insT[1]; inR = insT[3];
                    } else { inL = insT; inR = insT; }
                } catch (e4) {}
                frameW = (gbT[3] - inR) - (gbT[1] + inL);
            } catch (e5) {}
            // 열 스톱 계산 (텍스트 영역 왼쪽 = 0 기준, 그리드 스냅)
            var col0 = lind + fli;          // 0열 시작 (첫 줄 실제 위치)
            if (col0 < 0) { col0 = 0; }
            var stops = [];       // stops[c] = c열(1~) 시작 위치
            var end = col0 + (colw[0] || 0);
            var overflow = false;
            for (var c2 = 1; c2 <= maxTabs; c2++) {
                var pos = Math.ceil((end + minGap) / grid) * grid;
                stops.push(pos);
                end = pos + (colw[c2] || 0);
            }
            if (frameW !== null && end > frameW + 0.2) {
                // 비그리드 폴백 (최소 간격 패킹)
                stops = [];
                end = col0 + (colw[0] || 0);
                for (var c4 = 1; c4 <= maxTabs; c4++) {
                    var pos2 = end + minGap;
                    stops.push(pos2);
                    end = pos2 + (colw[c4] || 0);
                }
                if (end > frameW + 0.2) {
                    warned++;
                    wlog("[경고] 선지열정렬: 열 합계가 프레임 폭 초과 ("
                         + (Math.round(end * 10) / 10) + " > "
                         + (Math.round(frameW * 10) / 10) + "mm): "
                         + rows[0].txt.substr(0, 30));
                }
            }
            // 적용 — 항목 행: LEFT 스톱, 헤더 행: 열 중앙 정렬 스톱
            for (var r5 = 0; r5 < rows.length; r5++) {
                var p5 = paras[rows[r5].idx];
                try {
                    // 상한 가드 — remove()가 침묵 no-op이 되는 DOM 변이
                    // 사고 이력(dev guide) 대비 무한 루프 방지
                    var rmGuard = 0;
                    while (p5.tabStops.length > 0 && rmGuard < 40) {
                        rmGuard++;
                        p5.tabStops[0].remove();
                    }
                } catch (e6) {}
                var rStops = stops;
                if (rows[r5].header && hasItem) {
                    rStops = [];
                    for (var c5 = 1; c5 <= maxTabs; c5++) {
                        var base5 = stops[c5 - 1];
                        var shift = ((colw[c5] || 0)
                                     - (rows[r5].w[c5] || 0)) / 2;
                        rStops.push(base5 + Math.max(0, shift));
                    }
                    // 첫 라벨(탭 없음)은 첫줄 들여쓰기로 열 중앙 정렬.
                    // leftIndent를 올리면 내어쓰기(fli<0) 스타일에서 왼쪽
                    // 들여쓰기 위치의 암묵 탭스톱이 명시 스톱보다 먼저
                    // 걸려 (B)가 붙어버린다 (1차 재조판 실측) —
                    // firstLineIndent만 조정 (leftIndent 무접촉).
                    var h0 = ((colw[0] || 0) - (rows[r5].w[0] || 0)) / 2;
                    if (h0 > 0) {
                        try {
                            p5.firstLineIndent = col0 + h0 - lind;
                        } catch (e7) {}
                    }
                }
                for (var c6 = 0; c6 < rStops.length; c6++) {
                    try {
                        p5.tabStops.add({
                            alignment: TabStopAlignment.LEFT_ALIGN,
                            position: rStops[c6]
                        });
                    } catch (e8) {}
                }
            }
            groups++;
            if (groups % 20 === 0) {
                wlog("선지열정렬 진행: " + groups + "그룹");
            }
            i = j;
        }
    }
    wlog("선지열정렬: " + groups + "그룹 탭스톱 적용 / 프레임 초과 [경고] "
         + warned + "건");
}

// ── W40 결함 6: 밑줄 빈칸 라인 프레임 넘침 — 자간 축소로 수용 ───────────────
// 밑줄 런("_{6,}")은 줄바꿈 기회가 없어 프레임 오른쪽 경계 밖으로
// 삐져나온다 (0a5da924 실증). 해당 단락 자간(tracking)을 -10씩 낮춰
// 프레임 내로 수용 — 한도(op.max_tracking, 기본 -50) 초과가 필요하면
// 과도 축소 대신 [경고]로 지목한다 (사용자 확정 스펙).
function fixBlankOverflow(doc, op) {
    var maxNeg = -50;
    if (op && typeof op === "object" && op.max_tracking !== undefined
            && op.max_tracking !== null) {
        maxNeg = op.max_tracking;
    }
    var fixed = 0, warned = 0, checked = 0;
    try {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "_{6,}";
        var hits = doc.findGrep();
        var seen = {};
        for (var hi = 0; hi < hits.length; hi++) {
            var para = null;
            try { para = hits[hi].paragraphs[0]; } catch (e) { continue; }
            if (!para) { continue; }
            var key = "";
            try {
                key = String(hits[hi].parentStory.id) + ":"
                    + para.characters[0].index;
            } catch (e) { key = "k" + hi; }
            if (seen[key]) { continue; }
            seen[key] = true;
            checked++;
            var guard = 0;
            var applied = false;
            var capped = false;
            var origTr = null;      // 한도 도달 시 원복용 (과도 축소 금지)
            while (guard < 30) {
                guard++;
                var overAmt = 0;
                var lines = null;
                try { lines = para.lines.everyItem().getElements(); }
                catch (e) { break; }
                if (!lines || lines.length === 0) { break; }
                for (var li = 0; li < lines.length; li++) {
                    var rim = null, endX = null;
                    try {
                        var lf = lines[li].parentTextFrames[0];
                        var gb = lf.geometricBounds;
                        var rIn = 0;
                        try {
                            var ins = lf.textFramePreferences.insetSpacing;
                            rIn = (ins instanceof Array) ? ins[3] : ins;
                        } catch (eIn) {}
                        rim = gb[3] - rIn;
                        endX = lines[li].endHorizontalOffset;
                    } catch (eL) { continue; }
                    if (endX - rim > overAmt) { overAmt = endX - rim; }
                }
                // 허용 0.8mm — 양끝 정렬/시각적 여백 정렬의 행 끝 돌출
                // (~0.5mm 상수 — 1차 재조판 실측 18건 전부 +0.51mm)은
                // 결함이 아니다. 실제 빈칸 넘침(수 mm)만 보정.
                if (overAmt <= 0.8) { break; }
                var cur = 0;
                try {
                    cur = para.tracking;
                    if (typeof cur != "number") { cur = 0; }
                } catch (eT) { cur = 0; }
                if (origTr === null) { origTr = cur; }
                if (cur <= maxNeg) {
                    capped = true;
                    warned++;
                    wlog("[경고] 빈칸넘침: 자간 한도(" + maxNeg
                         + ")로도 프레임 수용 불가 (초과 "
                         + (Math.round(overAmt * 100) / 100) + "mm): "
                         + String(para.contents).substr(0, 30));
                    // 과도 축소 금지 (사용자 확정 스펙) — 원래 자간 복원
                    try {
                        para.tracking = origTr;
                        para.parentStory.recompose();
                    } catch (eRe) {}
                    break;
                }
                try {
                    para.tracking = Math.max(maxNeg, cur - 10);
                    applied = true;
                } catch (eA) { break; }
                try { para.parentStory.recompose(); } catch (eR) {}
            }
            if (applied && !capped) { fixed++; }
        }
        app.findGrepPreferences = NothingEnum.NOTHING;
    } catch (e) {
        wlog("[경고] 빈칸넘침 보정 실패: " + e);
        try { app.findGrepPreferences = NothingEnum.NOTHING; } catch (e2) {}
    }
    wlog("빈칸넘침 보정: 검사 " + checked + "단락 / 자간 조정 " + fixed
         + "건 / 한도 초과 [경고] " + warned + "건");
}

function textbookPostprocess(doc) {
    var bMaster = null, dMaster = null;
    try { bMaster = doc.masterSpreads.itemByName("B-마스터"); bMaster.name; } catch (e) { bMaster = null; }
    try { dMaster = doc.masterSpreads.itemByName("D-마스터"); dMaster.name; } catch (e) { dMaster = null; }
    var n = 0;
    for (var tpi = doc.pages.length - 1; tpi >= 0; tpi--) {
        var tpg = doc.pages[tpi];
        var tfs2 = tpg.textFrames;
        var tHasContent = false;
        for (var ttf = 0; ttf < tfs2.length; ttf++) {
            var tc2 = "";
            try { tc2 = (tfs2[ttf].contents || ""); } catch (e) {}
            if (String(tc2).replace(/[\s\r\n￼]+/g, "").length > 0) {
                tHasContent = true;
                break;
            }
        }
        if (tHasContent) { continue; }
        var curMaster = "";
        try { curMaster = tpg.appliedMaster ? tpg.appliedMaster.name : ""; } catch (e) {}
        if (curMaster === "A-마스터" && bMaster) {
            try { tpg.appliedMaster = bMaster; n++; } catch (e) {}
        }
        if (curMaster === "C-마스터" && dMaster) {
            try { tpg.appliedMaster = dMaster; n++; } catch (e) {}
        }
    }
    wlog("교과서 후처리: 빈 페이지 마스터 재할당 " + n + "개");
}

var doc = null;
try {
    wlog("워크북 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);
    app.scriptPreferences.enableRedraw = false;   // v1 run.jsx:111 파리티

    var styleCache = {};
    var missing = {};
    function styleOf(name) {
        if (styleCache[name]) { return styleCache[name]; }
        if (missing[name]) { return null; }
        if (name === "$BASIC") {
            styleCache[name] = basicParaOf(doc);
            return styleCache[name];
        }
        var ps = findParagraphStyleByPath(doc, name);
        if (ps) { styleCache[name] = ps; return ps; }
        missing[name] = true;
        wlog("[경고] 스타일 없음(자동 생성 안 함): " + name);
        return null;
    }
    // ── W45 답란(S_답란) 폴백 + 들여쓰기 0 브릿지 ──────────────────────────
    // 플랜의 답란 단락은 s="… > S_답란"(1선) + s_fb="… > S_선지 …"(폴백) +
    // ind0=true 를 갖는다. 템플릿에 S_답란이 아직 없으면 선지로 폴백하되,
    // 선지 스타일의 들여쓰기 때문에 답란 정렬이 깨지므로(사용자 지목 —
    // 완성본에서 손으로 지문 스타일로 바꾸던 회피의 원인) **그 단락에만**
    // firstLineIndent/leftIndent 로컬 오버라이드 0을 건다. 스타일 자체는
    // 건드리지 않고(문서 전역 무영향), 원값을 캡처해 로그에 남긴다(W28
    // 서식 유실 전례 — 침묵 변경 금지).
    var fbCount = 0;        // 폴백(선지)로 인쇄된 답란 단락 수
    var ind0Count = 0;      // 들여쓰기 0 로컬 오버라이드를 건 단락 수
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
    // 밑줄 문자스타일 — 플로우별 ul_style 우선, 폴백은 v1 CS_UNDERLINE 순서
    var ulCache = {};
    function ulStyleFor(flow) {
        var names = [];
        if (flow.ul_style) { names.push(flow.ul_style); }
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

    // 플로우 1개 처리 — v1 processStep* 대응. 반드시 app.doScript
    // UndoModes.ENTIRE_SCRIPT로 감싸 호출한다 (아래 루프): 수천 개의 개별
    // undo 트랜잭션이 앵커/추가 페이지가 누적된 문서에서 단락당 수 초의
    // 감속(행 유사)을 유발 (W3 실측 — v1 run.jsx도 스텝마다 동일 패턴).
    // 플로우별 배치 스토리 기록 — 후처리 op(passage_numbers/page_cleanup)용
    var flowStories = {};   // step -> {story, isMaster}

    function processFlow(flow) {
        var tgt = flow.target || {};
        var story = null;
        if (tgt.master) {
            story = mainStoryOnMaster(doc, tgt.master);
        } else if (tgt.marker) {
            story = storyByMarker(doc, tgt.marker, tgt.page, tgt.rank, tgt.pos);
        }
        if (!story) { wlog("[경고] 스토리 못 찾음: " + flow.step); return; }
        var csUL = ulStyleFor(flow);

        var flat = [];
        var unitStart = [];
        var unitPageBreak = [];
        for (var u = 0; u < flow.units.length; u++) {
            var unitObj = flow.units[u];
            var uParas = unitObj.paras || unitObj;   // dict 형식(W4) 겸용
            unitStart.push(flat.length);
            unitPageBreak.push(unitObj.page_break ? true : false);
            for (var q = 0; q < uParas.length; q++) {
                flat.push(uParas[q]);
            }
        }
        var texts = [];
        for (var i2 = 0; i2 < flat.length; i2++) { texts.push(flat[i2].t); }
        var joined = texts.join("\r");
        // 마지막 단락이 빈 문자열이면 스토리 끝 \r 뒤에 단락 객체가 생기지
        // 않아 flat↔paras 정렬이 1개 어긋난다 (꼬리 아이콘 단락 누락 원인).
        // \r 하나를 덧붙여 마지막 빈 단락을 실체화한다.
        if (texts.length > 0 && texts[texts.length - 1] === "") {
            joined += "\r";
        }
        story.contents = joined;
        try { story.texts[0].appliedCharacterStyle = noneCS; } catch (e) {}
        // unitStart(유닛 첫 단락 인덱스)를 함께 기록 — passage_numbers op가
        // '유닛 시작 페이지' 기준으로 번호 프레임을 갱신하는 데 쓴다 (W13
        // c13 실증: 지문이 페이지를 넘치면 '스토리 k번째 페이지 = k번째
        // 지문' 가정이 깨져 오갱신/잔존 발생). 아이콘은 앵커/기존 단락
        // 재사용이라 단락 인덱스를 바꾸지 않는다.
        flowStories[flow.step] = { story: story, isMaster: !!tgt.master,
                                   unitStart: unitStart.slice(0),
                                   masterPair: tgt.master_pair || null };
        wlog(flow.step + ": " + flat.length + "단락 배치 (유닛 " + flow.units.length + ")");

        // 대형 스토리 필수 최적화: 컬렉션 인덱싱 대신 getElements() 1회 캐시
        // (v1 blackbook run.jsx:197 주석 — 매번 재조회는 2,000단락에서 행 유발)
        var paras = story.paragraphs.everyItem().getElements();
        var isStart = {};
        for (var us = 0; us < unitStart.length; us++) {
            // "page" = NEXT_PAGE (W4 page_break 유닛), "frame" = NEXT_FRAME
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
            if (flow.break_per_unit && pi > 0 && isStart[pi]) {
                try {
                    paras[pi].startParagraph = (isStart[pi] === "page")
                        ? StartParagraph.NEXT_PAGE
                        : StartParagraph.NEXT_FRAME;
                } catch (e) {}
            }
            var runs = flat[pi].runs;
            if (runs && runs.length > 0) {
                var off = 0;
                for (var ri = 0; ri < runs.length; ri++) {
                    var rl = runs[ri].t ? runs[ri].t.length : 0;
                    if (rl > 0 && (runs[ri].ul || runs[ri].sub)) {
                        var a = off, b = off + rl - 1;
                        if (a < paras[pi].characters.length && b < paras[pi].characters.length) {
                            if (runs[ri].ul && csUL) {
                                paras[pi].characters.itemByRange(a, b).appliedCharacterStyle = csUL;
                            }
                            // W23 F3: 아래첨자 run — Position 속성 직접
                            // 적용 (문자스타일 아님, 자동 생성 금지 규칙
                            // 무관. 플랜 SUBSCRIPT_PRINT_TABLE의 ₂→2 치환
                            // 짝 — 어떤 폰트에서든 렌더 가능).
                            if (runs[ri].sub) {
                                try {
                                    paras[pi].characters.itemByRange(a, b).position = Position.SUBSCRIPT;
                                } catch (eSub) {}
                            }
                        }
                    }
                    off += rl;
                }
            }
            if ((pi + 1) % 50 === 0) {
                wlog(flow.step + " 스타일: " + (pi + 1) + "/" + flat.length);
            }
        }

        // 아이콘 패스 — 밑줄 runs·프레임브레이크 적용 이후 마지막, 역순
        // (아이콘 삽입은 텍스트 길이를 바꾸므로 뒤 단락부터 → 인덱스 안정)
        var iconCounts = {};
        var iconWant = {};
        var iconDone = 0;
        _iconPlaceFallback = {};   // W50: 플로우 단위 폴백 집계
        for (var xi = flat.length - 1; xi >= 0; xi--) {
            var ic = flat[xi].icon;
            if (!ic || xi >= paras.length) { continue; }
            iconWant[ic.label] = (iconWant[ic.label] || 0) + 1;
            if (insertIconAt(doc, story, paras[xi], ic)) {
                iconCounts[ic.label] = (iconCounts[ic.label] || 0) + 1;
            }
            iconDone++;
            if (iconDone % 50 === 0) {
                // 진행 로그 — 러너의 300초 무갱신 행 판정(pkill) 방지용
                wlog(flow.step + " 아이콘 진행: " + iconDone);
            }
        }
        for (var lb in iconCounts) {
            wlog(flow.step + " 아이콘 삽입: " + iconCounts[lb] + "개 (" + lb + ")");
        }
        // W50: 침묵 금지 — 지시 대비 미달/폴백을 [경고]로 남긴다
        for (var lbw in iconWant) {
            var fbn = _iconPlaceFallback[lbw] || 0;
            if (fbn > 0) {
                wlog("[경고] " + flow.step + " 아이콘 place 실패 " + fbn
                     + "건 → duplicate 폴백 (" + lbw + ")");
            }
            var gotN = iconCounts[lbw] || 0;
            if (gotN < iconWant[lbw]) {
                wlog("[경고] " + flow.step + " 아이콘 누락: "
                     + (iconWant[lbw] - gotN) + "/" + iconWant[lbw]
                     + "개 (" + lbw + ")");
            }
        }

        // 스토리 오버플로우 시 마스터 유지 페이지 추가 (v1 ensureNoOverflow 의미론)
        // safety 상한 60 (W12): 123문제 변형문제 문제모음이 상한 10을 넘겨
        // 초과분이 overset(미인쇄)으로 잘렸다. 상한은 무한 루프 가드일 뿐
        // 실제 반복 수는 오버플로우 해소 시점이 결정 — 기존 케이스 무영향.
        // 꼬리 공백 전용 overset은 페이지를 늘리지 않고 정리 (W19 c19):
        // 공백 전용 확장 페이지는 page_cleanup 스레드 절단에서 다시 잘려
        // overset('\r')이 재발한다. 실질 오버플로우는 아래 확장이 그대로.
        var wsTrim = trimWsOverset(story);
        if (wsTrim > 0) {
            wlog(flow.step + ": 꼬리 공백 overset " + wsTrim + "자 정리");
        }
        var safety = expandStoryOverflow(doc, flow.step, story);
        if (safety > 0) { wlog(flow.step + ": 오버플로우 페이지 +" + safety); }
    }

    for (var fi2 = 0; fi2 < plan.flows.length; fi2++) {
        // 플로우(스텝) 단위 Undo 그룹화 — v1 파리티 (UndoModes.ENTIRE_SCRIPT)
        (function (fl) {
            app.doScript(function () { processFlow(fl); },
                         ScriptLanguage.JAVASCRIPT, undefined,
                         UndoModes.ENTIRE_SCRIPT, "wb_v2 " + fl.step);
        })(plan.flows[fi2]);
    }

    // W45 답란 폴백 결산 (침묵 금지 — 템플릿에 S_답란이 없으면 여기 남는다)
    if (fbCount > 0) {
        wlog("[답란] S_답란 없음 → 선지 폴백 " + fbCount + "개 단락"
             + (ind0Count > 0
                ? " / 들여쓰기 0 로컬 오버라이드 " + ind0Count + "개 ("
                  + ind0Sample + ")"
                : ""));
    }

    relockIcons();   // v1 relockItem — 아이콘 원본/레이어 잠금 복원

    // opt-in 후처리 op (plan 키가 있을 때만 — 기존 플랜은 무변경)
    if (plan.passage_numbers) {
        app.doScript(function () {
            updatePassageNumbers(doc, flowStories, plan.passage_numbers);
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wb_v2 passage_numbers");
    }
    if (plan.page_cleanup) {
        app.doScript(function () {
            cleanupPages(doc, flowStories,
                         (typeof plan.page_cleanup === "object")
                             ? plan.page_cleanup : {});
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wb_v2 page_cleanup");
    }
    if (plan.question_keep && plan.question_keep.flows) {
        // W23 r13 F4 — 반드시 page_cleanup 이후 (삭제 전에 밀면 push로 빈
        // 페이지가 생기고 정리가 그 페이지를 지우며 좌우가 되밀리는 순환).
        // 밀기/확장으로 뒤 간지 정렬이 변할 수 있어 delete 모드는
        // alignPartFillers를 재실행한다 (멱등 — 라벨이 왼쪽일 때만 삽입).
        app.doScript(function () {
            enforceQuestionKeep(doc, flowStories, plan.question_keep);
            if (plan.question_keep.stem_keep) {
                // W40 결함 2 — 프레임판 발문 고아 방지 (스프레드 킵 이후.
                // 밀기로 스프레드 걸침이 새로 생길 수 있어 재검 1회)
                enforceStemKeep(doc, flowStories, plan.question_keep);
                enforceQuestionKeep(doc, flowStories, plan.question_keep);
            }
            // W55: 수렴 후 불필요해진 밀기 해제 (컬럼/페이지 공백 회수).
            // 완화가 지면을 당기면 새 걸침이 생겨 enforce가 다시 밀고, 그
            // 밀기들이 서로를 다시 무효화한다(refix3 실증: 완화 15건 해제
            // 직후 enforce가 11건 재밀기 → p95 구멍). 완화↔강제를
            // 고정점(둘 다 0건)까지 반복한다 (상한 4라운드 — 진동 가드,
            // 마지막 연산은 항상 enforce라 스프레드 걸침 0은 보장).
            // 완화로 당겨진 배치가 발문 고아를 새로 만들 수 있어(refix2
            // 실증 3건) 발문고아킵 후에도 한 쌍 더 돈다.
            // W56: 페이지 밀기(NEXT_PAGE)와 단 밀기(NEXT_FRAME) 둘 다
            // 톱니라 두 완화·두 강제를 한 고정점 루프로 통합한다 —
            // 라운드의 마지막 연산이 항상 강제라 스프레드 걸침·발문
            // 고아 0은 보장되고, 불필요 밀기(공백)는 다음 라운드가
            // 회수한다. 전부 0건이면 수렴.
            var kkRound = 0;
            while (kkRound < 5) {
                kkRound++;
                var kkRQ = relaxQuestionKeep(doc, flowStories,
                                             plan.question_keep);
                var kkRS = plan.question_keep.stem_keep
                    ? relaxStemKeep(doc, flowStories, plan.question_keep)
                    : 0;
                var kkPQ = enforceQuestionKeep(doc, flowStories,
                                               plan.question_keep);
                var kkPS = plan.question_keep.stem_keep
                    ? enforceStemKeep(doc, flowStories, plan.question_keep)
                    : 0;
                var kkPQ2 = (kkPS > 0)
                    ? enforceQuestionKeep(doc, flowStories,
                                          plan.question_keep)
                    : 0;
                wlog("문제단위킵 라운드 " + kkRound + ": 완화 "
                     + (kkRQ + kkRS) + " (P" + kkRQ + "/F" + kkRS
                     + ") / 재밀기 " + (kkPQ + kkPS + kkPQ2));
                if (kkRQ + kkRS + kkPQ + kkPS + kkPQ2 === 0) { break; }
            }
            if (plan.page_cleanup
                    && (typeof plan.page_cleanup === "object")
                    && plan.page_cleanup.empty === "delete") {
                alignPartFillers(doc);
            }
            normalizeStep3ContentMasters(doc, flowStories);
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wb_v2 question_keep");
    }
    if (plan.page_cleanup && (typeof plan.page_cleanup === "object")) {
        // W40 결함 8: 호출 조건을 empty==="delete" 에서 page_cleanup 전반으로
        // 넓힌다. 본가(모의고사)는 empty_master:"M" 모드라 이 op 가 한 번도
        // 돌지 않아 판권이 오른쪽으로 납품됐다 (게이트 G28④ v15 실증:
        // 크레딧 p235 오른쪽). 크레딧 정렬은 빈 페이지 삭제 여부와 무관하고,
        // 함수 자체가 마지막 페이지 셰이프(마스터 없음+프레임 0)로 대상을
        // 좁히므로 비대상 문서에서는 no-op 이다.
        // W30-r15 (결함 7): 크레딧(판권) 정렬 — 페이지 수를 바꾸는 모든
        // op(page_cleanup 삭제·간지 채움·question_keep 오버플로우 확장)
        // 이후 1회. 376b34d0 실증: 문제단위킵 확장 +3이 홀짝을 뒤집어
        // 판권이 오른쪽 단독(p99)으로 납품됐다 — cleanupPages 시점 정렬은
        // 이후 확장에 다시 깨질 수 있어 여기서만 수행한다.
        app.doScript(function () { alignCreditPage(doc); },
                     ScriptLanguage.JAVASCRIPT, undefined,
                     UndoModes.ENTIRE_SCRIPT, "wb_v2 credit_align");
    }
    if (plan.section_masters) {
        app.doScript(function () { fixSectionMasters(doc, flowStories); },
                     ScriptLanguage.JAVASCRIPT, undefined,
                     UndoModes.ENTIRE_SCRIPT, "wb_v2 section_masters");
        // W53: 섹션 시작 마스터 확정 이후 — 스텝 콘텐츠 페이지의 빈(M)
        // 마스터 복구 (헤더 없는 본문 페이지 방지). 반드시 이 순서.
        app.doScript(function () {
            repairStepContentMasters(doc, flowStories);
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wb_v2 step_content_masters");
    }
    if (plan.divider && plan.divider.line1) {
        app.doScript(function () {
            updateDividerPages(doc, plan.divider.line1,
                               plan.divider.line2 || "");
        }, ScriptLanguage.JAVASCRIPT, undefined,
           UndoModes.ENTIRE_SCRIPT, "wb_v2 divider");
    }
    if (plan.textbook_postprocess) {
        app.doScript(function () { textbookPostprocess(doc); },
                     ScriptLanguage.JAVASCRIPT, undefined,
                     UndoModes.ENTIRE_SCRIPT, "wb_v2 textbook_post");
    }
    if (plan.blank_fit) {
        // W40 결함 6 — 페이지 수를 바꾸는 모든 op 이후, 저장 직전
        app.doScript(function () { fixBlankOverflow(doc, plan.blank_fit); },
                     ScriptLanguage.JAVASCRIPT, undefined,
                     UndoModes.ENTIRE_SCRIPT, "wb_v2 blank_fit");
    }
    if (plan.choice_tabs) {
        // W40 결함 1 — 다열 선지 열 정렬 (탭스톱 자동 적용)
        app.doScript(function () { applyChoiceTabs(doc, flowStories, plan.choice_tabs); },
                     ScriptLanguage.JAVASCRIPT, undefined,
                     UndoModes.ENTIRE_SCRIPT, "wb_v2 choice_tabs");
    }

    var ovf = 0;
    for (var s3 = 0; s3 < doc.stories.length; s3++) {
        try {
            var tc = doc.stories[s3].textContainers;
            if (tc.length > 0 && tc[tc.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("오버플로우: " + ovf + "개");

    // 저장/export 직전 하트비트 — 러너 stall 시계를 리셋해 무갱신 구간이
    // '해당 단계 소요'만큼만 되도록 (W13 c05 실측: 284p 전량 콘텐츠 문서의
    // PDF export가 로그 무갱신 20분+. 900초 stall이면 정상 export 중
    // 강제종료 = 유령 모달 사고 재발 경로 — 엔진 stall_limit 상향과 세트)
    wlog("문서 저장 시작 (로그 무갱신 수 분 가능)");
    doc.save(File(OUT_INDD));
    wlog("PDF export 시작 (대형 문서는 로그 무갱신 20분+ 가능)");
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    try { app.scriptPreferences.enableRedraw = true; } catch (e4) {}
    wlog("워크북 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { relockIcons(); } catch (e3) {}
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    try { app.scriptPreferences.enableRedraw = true; } catch (e5) {}
}
