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

// 단락 1개에 아이콘 1개 삽입. 성공 1 / 실패 0.
function insertIconAt(doc, story, para, ic) {
    var pos = (ic.pos === "start") ? "start" : "end";
    var pad = ic.pad || "";
    if (ic.mode === "place") {
        // v1 processStep2B1: 링크 파일 place + 원본 너비 스케일
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
    // 기본: duplicate 인라인 앵커 (v1 insertInlineIcon)
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
    return 1;
}

// ── W11 op: 독립 지문번호 프레임 갱신 (plan.passage_numbers가 있을 때만) ────
// 빈칸어휘/어법OX/빈칸어법 섹션은 지문번호가 메인 스토리 밖 단일 프레임
// 스토리("20" 등 모의고사 문항번호 잔재). 스텝 스토리의 k번째 콘텐츠 페이지의
// 순수 숫자 단일 프레임을 원고 지문번호 labels[k]로 갱신한다.
var RE_BARE_NUM = /^\s*\d{1,3}(?:\s*~\s*\d{1,3})?\s*$/;

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
                    fst.contents = lab2;
                    n++;
                } catch (e) {}
            }
        }
        if (n > 0) { wlog(steps[si] + " 지문번호 프레임 갱신: " + n + "개"); }
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

function cleanupPages(doc, flowStories, op) {
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
        if (rec2.isMaster) { continue; }   // STEP3는 M 마스터 경로에서 관리
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
    var removed = 0;
    var scanned = 0;
    for (var dp = doc.pages.length - 1; dp >= 0; dp--) {
        if (dp < cleanStart || dp >= step3Start) { continue; }
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
        for (var tf = 0; tf < tfs.length; tf++) {
            var pst = null;
            var nConts = 0;
            try {
                pst = tfs[tf].parentStory;
                nConts = pst.textContainers.length;
            } catch (e) { continue; }
            if (nConts > 1) {
                hasLocal = true;
                if (!isBlankFrameContent(tfs[tf])) { allBlank = false; }
            } else if (RE_BARE_NUM.test(String(pst.contents || ""))) {
                hasBareNum = true;
            }
            try {
                if (flowIds[String(pst.id)]
                        && !isBlankFrameContent(tfs[tf])) {
                    hasFlowContent = true;
                }
            } catch (e2) {}
        }
        if ((hasLocal && allBlank && !hasFlowContent)
                || (hasBareNum && !hasFlowContent)) {
            try { pg.remove(); removed++; } catch (e) {}
        }
    }
    wlog("페이지 정리: 잔여 스텝/사이클 페이지 " + removed + "개 삭제");

    // 3) STEP3 영역 — 빈 페이지 M 마스터 재할당 (v1 adjustStep3Pages 파리티)
    if (!step3Story) { return; }
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

// ── 간지 텍스트 업데이트 (v1 run.jsx 16.7 이식 — plan.divider가 있을 때만) ──
// 간지 페이지 = 마스터 [None](또는 없음) + 오른쪽 + 텍스트프레임 1개 +
// 첫 단락에 한글. 1단락=line1, 2단락=line2.
function updateDividerPages(doc, line1, line2) {
    var n = 0;
    for (var dpi = 0; dpi < doc.pages.length; dpi++) {
        var dpg = doc.pages[dpi];
        var masterName = "";
        try { masterName = dpg.appliedMaster ? dpg.appliedMaster.name : ""; } catch (e) {}
        if (masterName !== "" && masterName !== "[None]") { continue; }
        // Enumerator 엄격 비교 신뢰 불가 (W7 교훈) — == 비교 사용
        if (!(dpg.side == PageSideOptions.RIGHT_HAND)) { continue; }
        if (dpg.textFrames.length !== 1) { continue; }
        var divTf = dpg.textFrames[0];
        var divParas = divTf.paragraphs;
        if (divParas.length < 2) { continue; }
        var p1 = String(divParas[0].contents || "").replace(/[\r\n]+$/, "");
        if (!/[가-힣]/.test(p1)) { continue; }
        try {
            divParas[0].contents = line1 + "\r";
            divParas[1].contents = line2 + "\r";
            n++;
        } catch (e) {}
    }
    wlog("간지 텍스트 업데이트: " + n + "개 (" + line1 + " / " + line2 + ")");
}

// ── 교과서 후처리 (v1 run.jsx 16.8 이식 — plan.textbook_postprocess) ────────
// 빈 A-마스터 페이지 → B-마스터, 빈 C-마스터 페이지 → D-마스터.
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
                                   unitStart: unitStart.slice(0) };
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
            if (ps2) { paras[pi].appliedParagraphStyle = ps2; }
            if (flow.break_per_unit && pi > 0 && isStart[pi]) {
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
                wlog(flow.step + " 스타일: " + (pi + 1) + "/" + flat.length);
            }
        }

        // 아이콘 패스 — 밑줄 runs·프레임브레이크 적용 이후 마지막, 역순
        // (아이콘 삽입은 텍스트 길이를 바꾸므로 뒤 단락부터 → 인덱스 안정)
        var iconCounts = {};
        var iconDone = 0;
        for (var xi = flat.length - 1; xi >= 0; xi--) {
            var ic = flat[xi].icon;
            if (!ic || xi >= paras.length) { continue; }
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
        var conts = story.textContainers;
        var lastF = conts[conts.length - 1];
        var safety = 0;
        while (lastF.overflows && safety < 60) {
            var lp = lastF.parentPage;
            var gb = lastF.geometricBounds;
            var np = doc.pages.add(LocationOptions.AFTER, lp);
            try { np.appliedMaster = lp.appliedMaster; } catch (e) {}
            var ntf = np.textFrames.add();
            ntf.geometricBounds = [gb[0], gb[1], gb[2], gb[3]];
            lastF.nextTextFrame = ntf;
            lastF = ntf;
            safety++;
            if (safety % 10 === 0) {
                wlog(flow.step + " 오버플로우 페이지 확장 진행: +" + safety);
            }
        }
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
