// 배N제 v2 렌더 실행기 — bj-flows-v1 플랜을 그대로 실행한다 (lib.jsxinc 뒤 concat).
// 정책: 스타일/마스터가 문서에 없으면 자동 생성하지 않고 [경고] 로그 + 결과 JSON에 기록.
//
// 플랜: {"format":"bj-flows-v1","flows":[{"area","units":[{no,paras,page_break,unit_label}]}],
//        "ops":{unit_masters, unit_char_style, wide_space_style, memo_master, keep_block_in_spread}}
//
// 배치 의미론
//   - 유닛(=문항) 경계 = 프레임 브레이크(NEXT_FRAME), page_break 유닛은 NEXT_PAGE
//   - unit_label 이 있는 유닛은 맨 앞에 보이지 않는 '유닛' 문자스타일 단락을 둔다
//     (마스터의 러닝헤드 텍스트 변수가 이 텍스트를 찾아 머리말로 표시)
//   - 오버플로우 시 2쪽(스프레드) 단위로 페이지 증설 + 프레임 복제 + 스레드 연결
//   - 유닛 시작 스프레드에 L0/L2(C0/C2), 나머지에 L1(C1)
//   - 정답지: 한 문항 블록이 펼침면을 넘지 않도록 번호 단락에 NEXT_PAGE

var TEMPLATE = "__TEMPLATE_PATH__";
var PLAN = "__PLAN_PATH__";
var OUT_INDD = "__OUT_INDD__";
var OUT_PDF = "__OUT_PDF__";
var RESULT = "__RESULT_PATH__";

var RESULTS = {
    areas: {}, missing_styles: [], missing_masters: [], header_texts: [],
    moved_blocks: [], overflow: 0, overflow_heads: [], pages: 0,
    memo_pages: [], wide_space_fixed: 0, blanks_underlined: 0,
    frames_grown: [], choice_layout: {}, mixed_format: [],
    oneline_fitted: 0, oneline_failed: [], credit_placed: [],
    answer_line_as_passage: [], trimmed_pages: 0, orphan_moved: [],
    recolored: 0, orphan_remaining: [], story_len_drift: [],
    stale_unit_purged: [], unit_label_sources: 0, warnings: []
};

function readJSONFile(path) {
    var f = new File(path);
    f.encoding = "UTF-8";
    f.open("r");
    var s = f.read();
    f.close();
    return eval("(" + s + ")");
}

function alen(st) { try { return st ? st.length : -1; } catch (e) { return -2; } }
function phase(tag, st) { wlog("[진단] " + tag + " 정답지길이=" + alen(st)); }

function warn(msg) {
    RESULTS.warnings.push(msg);
    wlog("[경고] " + msg);
}

// ── 스토리 판별: 페이지 프레임 투표 (render_flow.body.jsx 이식) ──────────
function storiesByFrameCount(doc) {
    var votes = {}, byId = {};
    for (var p = 0; p < doc.pages.length; p++) {
        var frames = doc.pages[p].textFrames;
        for (var t = 0; t < frames.length; t++) {
            try {
                var st = frames[t].parentStory;
                var sid = String(st.id);
                votes[sid] = (votes[sid] || 0) + 1;
                byId[sid] = st;
            } catch (e) {}
        }
    }
    var arr = [];
    for (var sid2 in votes) { arr.push({ n: votes[sid2], st: byId[sid2] }); }
    arr.sort(function (a, b) { return b.n - a.n; });
    return arr;
}

function pageOfFrame(fr) { try { return fr.parentPage; } catch (e) { return null; } }
function paraStartPage(p) { try { return p.parentTextFrames[0].parentPage; } catch (e) { return null; } }
function paraEndPage(p) {
    try { var tfs = p.parentTextFrames; return tfs[tfs.length - 1].parentPage; }
    catch (e) { return null; }
}

// 문자스타일: 전체 경로 → 실패 시 그룹 무관 이름 탐색 (v1 getPStyle 파리티)
function findCharStyleAnywhere(doc, name) {
    if (!name) return null;
    var st = findCharacterStyleByPath(doc, name);
    if (st) return st;
    var all = doc.allCharacterStyles;
    var leaf = name.split(">").pop().replace(/^\s+|\s+$/g, "");
    for (var i = 0; i < all.length; i++) {
        if (all[i].name === leaf) return all[i];
    }
    return null;
}

function findMaster(doc, prefix) {
    for (var i = 0; i < doc.masterSpreads.length; i++) {
        if (doc.masterSpreads[i].namePrefix === prefix) return doc.masterSpreads[i];
    }
    var alt = prefix.replace(/0$/, "");
    if (alt !== prefix) {
        for (var j = 0; j < doc.masterSpreads.length; j++) {
            if (doc.masterSpreads[j].namePrefix === alt) return doc.masterSpreads[j];
        }
    }
    return null;
}

// ── 묵은 유닛 라벨 제거 ─────────────────────────────────────────────────
// 머리말(러닝헤드 변수)의 소스는 이번 실행이 심은 라벨뿐이어야 한다.
// 템플릿에 지난 판의 라벨이 남아 있으면 변수가 그걸 먼저 찾아 옛 유닛명이 찍힌다
// (실측: 템플릿 2쪽에 남아 있던 'Lesson 1'이 새 판 머리말로 표시됨).
// 마스터 페이지의 라벨(실전문제/정답 및 해설 등)은 디자인이므로 건드리지 않는다.
function purgeStaleUnitLabels(doc, csName) {
    var cs = findCharStyleAnywhere(doc, csName || "유닛");
    if (!cs) return 0;
    app.findTextPreferences = NothingEnum.NOTHING;
    app.changeTextPreferences = NothingEnum.NOTHING;
    app.findTextPreferences.appliedCharacterStyle = cs;
    app.findChangeTextOptions.includeMasterPages = false;
    var found = [];
    try { found = doc.findText(); } catch (e) {}
    app.findTextPreferences = NothingEnum.NOTHING;
    app.changeTextPreferences = NothingEnum.NOTHING;
    var n = 0;
    for (var i = found.length - 1; i >= 0; i--) {
        var txt = "";
        try { txt = String(found[i].contents).replace(/[\r\n]/g, ""); } catch (e) {}
        try {
            var para = found[i].paragraphs[0];
            // 라벨만 담긴 단락이면 단락째, 아니면 문자스타일만 해제
            if (String(para.contents).replace(/[\r\n]/g, "") === txt) {
                para.remove();
            } else {
                found[i].appliedCharacterStyle = doc.characterStyles[0];
            }
            n++;
            RESULTS.stale_unit_purged.push(txt.substr(0, 40));
        } catch (e) {}
    }
    if (n > 0) wlog("묵은 유닛 라벨 제거: " + n + "건 (" +
                    RESULTS.stale_unit_purged.join(" / ") + ")");
    return n;
}

// ── 플로우 배치 ─────────────────────────────────────────────────────────
// 반환: {labelParas: [단락], count: 배치 단락 수}
function placeFlow(doc, story, flow, ops) {
    var texts = [], meta = [], unitStarts = [];
    var units = flow.units;
    // 유닛 경계마다 프레임을 분리할지 (본문=문항 1개 1프레임, 정답지=이어 흘림)
    var perUnit = (flow.break_per_unit !== false);
    for (var u = 0; u < units.length; u++) {
        var unit = units[u];
        var first = true;
        unitStarts.push(texts.length);      // 유닛 첫 단락(라벨 포함) 인덱스
        if (unit.unit_label) {
            texts.push(unit.unit_label);
            meta.push({ s: null, isLabel: true, unitIdx: u, unitStart: true,
                        brk: unit.page_break ? "page"
                             : ((perUnit && u > 0) ? "frame" : null) });
            first = false;
        }
        for (var i = 0; i < unit.paras.length; i++) {
            var p = unit.paras[i];
            texts.push(p.t);
            meta.push({
                s: p.s, runs: p.runs || null, align: p.align || null,
                isLabel: false, unitIdx: u, unitStart: first,
                brk: first ? (unit.page_break ? "page"
                              : ((perUnit && u > 0) ? "frame" : null)) : null
            });
            first = false;
        }
    }
    story.contents = texts.join("\r");
    wlog(flow.area + " 텍스트 배치: " + texts.length + "단락");

    // 문자 스타일 초기화 — texts[0](스토리 전체 단일 객체)
    try { story.texts[0].appliedCharacterStyle = doc.characterStyles[0]; } catch (e) {}

    var cache = {}, missing = {};
    var csUL = findCharStyleAnywhere(doc, "밑줄");
    var csUnit = findCharStyleAnywhere(doc, ops.unit_char_style || "유닛");
    if (!csUnit) {
        warn("'" + (ops.unit_char_style || "유닛") + "' 문자스타일 없음 — 머리말 비활성");
        RESULTS.missing_styles.push(ops.unit_char_style || "유닛");
    }
    // 유닛 라벨 단락은 자동번호가 없는 중립 스타일이어야 한다.
    // (정답지 스토리의 기본 스타일이 '해설_시작'이면 라벨 자리에 '해설 |' 라벨이
    //  그대로 찍힌다 — 문자 크기/색 override로는 안 감춰짐)
    var psLabel = findParagraphStyleByPath(doc, ops.label_style || "[기본 단락]");
    if (!psLabel) { try { psLabel = doc.paragraphStyles[0]; } catch (e) {} }
    var labelParas = [];
    var paras = story.paragraphs;
    var n = Math.min(meta.length, paras.length);
    if (meta.length !== paras.length) {
        warn(flow.area + " 단락 수 불일치: 플랜 " + meta.length + " vs 문서 " + paras.length);
    }

    for (var k = 0; k < n; k++) {
        var m = meta[k], para = paras[k];
        if (m.isLabel) {
            // 보이지 않는 유닛 라벨 (러닝헤드 변수 소스)
            if (csUnit) {
                try { if (psLabel) para.appliedParagraphStyle = psLabel; } catch (e) {}
                try { para.appliedCharacterStyle = csUnit; } catch (e) {}
                try { para.pointSize = 0.1; } catch (e) {}
                try { para.leading = 0.1; } catch (e) {}
                try { para.fillColor = "None"; } catch (e) {}
                try { para.spaceBefore = 0; para.spaceAfter = 0; } catch (e) {}
                try { para.justification = Justification.LEFT_ALIGN; } catch (e) {}
            }
            labelParas.push(para);
        } else if (m.s !== null) {
            if (!cache[m.s] && !missing[m.s]) {
                var ps = findParagraphStyleByPath(doc, m.s);
                if (ps) { cache[m.s] = ps; }
                else {
                    missing[m.s] = true;
                    RESULTS.missing_styles.push(m.s);
                    warn("스타일 없음(자동 생성 안 함): " + m.s);
                }
            }
            if (cache[m.s]) { try { para.appliedParagraphStyle = cache[m.s]; } catch (e) {} }
            if (m.align === "left") {
                try { para.justification = Justification.LEFT_ALIGN; } catch (e) {}
            }
            if (m.runs && csUL) {
                var off = 0;
                for (var ri = 0; ri < m.runs.length; ri++) {
                    var rl = m.runs[ri].t.length;
                    if (rl > 0 && m.runs[ri].ul) {
                        var a = off, b = off + rl - 1;
                        if (a < para.characters.length && b < para.characters.length) {
                            try {
                                para.characters.itemByRange(a, b).appliedCharacterStyle = csUL;
                            } catch (e) {}
                        }
                    }
                    off += rl;
                }
            }
        }
        if ((k + 1) % 50 === 0) { wlog(flow.area + " 스타일 적용: " + (k + 1) + "/" + n); }
    }

    // 브레이크는 스타일 적용 뒤에 (스타일 대입이 startParagraph를 초기화한다)
    for (var k2 = 0; k2 < n; k2++) {
        if (!meta[k2].brk) continue;
        try {
            paras[k2].startParagraph = (meta[k2].brk === "page")
                ? StartParagraph.NEXT_PAGE : StartParagraph.NEXT_FRAME;
        } catch (e) {}
    }
    RESULTS.areas[flow.area] = { paras: n, units: units.length,
                                 labels: labelParas.length };
    return { labels: labelParas, starts: unitStarts };
}

// ── 선지 레이아웃 보정 ──────────────────────────────────────────────────
// (1) "(A)   (B)" 머리행: 아래 선지의 두 칸 x좌표를 실측해 들여쓰기/탭으로 정렬
// (2) 조합형 짧은 선지: 3열로 묶어 배치 (프레임이 모자라면 하단을 조금 늘림)
var _RE_SEP = /[·⋯…]{2,}/;

// 우리가 다시 쓴 단락은 문자 서식이 균일해야 한다.
// (전각공백에 입힌 한글 문자스타일이 남아 (B)만 다른 폰트로 찍히는 사고 방지)
function resetCharFormat(doc, para) {
    try { para.texts[0].appliedCharacterStyle = doc.characterStyles[0]; } catch (e) {}
    try { para.texts[0].clearOverrides(OverrideType.CHARACTER_ONLY); } catch (e) {}
}

function fontSignature(para) {
    var sig = null, mixed = false;
    try {
        var tsr = para.textStyleRanges;
        for (var i = 0; i < tsr.length; i++) {
            var t = tsr[i].contents.replace(/[\s\r\n\t]/g, "");
            if (t.length === 0) continue;      // 공백/탭만 있는 런은 무시
            var k = String(tsr[i].appliedFont) + "|" + tsr[i].fontStyle + "|" +
                    tsr[i].pointSize;
            if (sig === null) sig = k;
            else if (k !== sig) mixed = true;
        }
    } catch (e) {}
    return { sig: sig, mixed: mixed };
}

function skipSpaces(text, from) {
    var i = from;
    while (i < text.length) {
        var ch = text.charAt(i);
        if (ch !== " " && ch !== "\u3000" && ch !== "\t") break;
        i++;
    }
    return i;
}

function charX(para, idx) {
    try { return para.characters[idx].horizontalOffset; } catch (e) { return null; }
}

function frameTextLeft(para) {
    try {
        var tf = para.parentTextFrames[0];
        var gb = tf.geometricBounds;
        var inset = 0;
        try { inset = tf.textFramePreferences.insetSpacing[1]; } catch (e) {}
        return gb[1] + inset;
    } catch (e) { return null; }
}

// 2단 선지("① word1 ······ word2")의 둘째 칸을 탭으로 정렬한다.
// 구분자가 인라인 텍스트라 칸 시작 x가 선지마다 들쭉날쭉 → 머리행을 맞출 기준이 없다.
function alignAbOptions(story, absIdx) {
    var ps = story.paragraphs;
    var idxs = [], sepX = null;
    var left = frameTextLeft(ps[absIdx]);
    if (left === null) return [];
    for (var k = absIdx + 1; k < Math.min(absIdx + 8, ps.length); k++) {
        var t = ps[k].contents.replace(/[\r\n]/g, "");
        if (!/^[①-⑳]/.test(t)) break;
        var m = _RE_SEP.exec(t);
        if (!m) continue;
        var x = charX(ps[k], m.index);
        if (x !== null && (sepX === null || x > sepX)) sepX = x;
        idxs.push(k);
    }
    if (idxs.length === 0 || sepX === null) return [];
    var pos = Math.max(1, sepX - left + 0.8);      // 가장 긴 첫 칸 + 여백(mm)
    // 구분자 앞 공백 → 탭
    for (var i = idxs.length - 1; i >= 0; i--) {
        ps = story.paragraphs;
        var para = ps[idxs[i]];
        var txt = para.contents.replace(/[\r\n]/g, "");
        var mm = _RE_SEP.exec(txt);
        if (!mm) continue;
        var st = mm.index;
        while (st > 0 && (txt.charAt(st - 1) === " " || txt.charAt(st - 1) === "\u3000")) st--;
        if (st <= 0) continue;
        try {
            var rng = story.characters.itemByRange(para.characters[st].index,
                                                   para.characters[mm.index - 1].index);
            if (rng.isValid) rng.contents = "\t";
        } catch (e) { warn("2단 선지 탭 변환 실패: " + e.message); }
    }
    ps = story.paragraphs;
    for (var j = 0; j < idxs.length; j++) {
        try {
            var pp = ps[idxs[j]];
            var ts = pp.tabStops;
            while (ts.length > 0) { ts[0].remove(); ts = pp.tabStops; }
            pp.tabStops.add({ alignment: TabStopAlignment.LEFT_ALIGN, position: pos });
        } catch (e) {}
    }
    try { doc.recompose(); } catch (e) {}
    return idxs;
}

function alignAbHeader(story, absIdx) {
    var ps = story.paragraphs;
    if (absIdx < 0 || absIdx >= ps.length) return false;
    var hdr = ps[absIdx];
    if (!/^\(A\)/.test(hdr.contents)) return false;
    // 뒤따르는 선지 줄에서 1칸/2칸 시작 x 실측
    var left = frameTextLeft(hdr);
    if (left === null) return false;
    var x1 = null, x2 = null;
    for (var k = absIdx + 1; k < Math.min(absIdx + 7, ps.length); k++) {
        var t = ps[k].contents.replace(/[\r\n]/g, "");
        if (!/^[①-⑳]/.test(t)) break;
        var m = _RE_SEP.exec(t);
        if (!m) continue;
        // 마커/구분자 뒤의 공백을 건너뛴 '첫 글자' 위치를 실측한다
        var ia = skipSpaces(t, 1);                        // ① 다음
        var ib = skipSpaces(t, m.index + m[0].length);    // 구분자 다음
        var a = charX(ps[k], ia);
        var b = charX(ps[k], ib);
        if (a === null || b === null) continue;
        if (x1 === null || a < x1) x1 = a;
        if (x2 === null || b < x2) x2 = b;
    }
    if (x1 === null || x2 === null) return false;
    try {
        // 단락 객체에 contents를 대입하면 끝의 단락기호까지 교체돼 다음 선지가
        // 병합된다 → 단락기호를 뺀 문자 범위만 교체
        var hLen = hdr.characters.length;
        var hLast = "";
        try { hLast = hdr.characters[hLen - 1].contents; } catch (e) {}
        var hEnd = (hLast === "\r" && hLen >= 2) ? hLen - 2 : hLen - 1;
        var hRange = story.characters.itemByRange(hdr.characters[0].index,
                                                 hdr.characters[hEnd].index);
        if (!hRange.isValid) return false;
        hRange.contents = "(A)\t(B)";
        ps = story.paragraphs;
        hdr = ps[absIdx];
        resetCharFormat(doc, hdr);
        hdr.leftIndent = 0;
        hdr.firstLineIndent = Math.max(0, x1 - left);
        hdr.justification = Justification.LEFT_ALIGN;
        var ts = hdr.tabStops;
        while (ts.length > 0) { ts[0].remove(); ts = hdr.tabStops; }
        hdr.tabStops.add({ alignment: TabStopAlignment.LEFT_ALIGN,
                           position: Math.max(1, x2 - left) });
        var fs = fontSignature(hdr);
        if (fs.mixed) {
            RESULTS.mixed_format.push("(A)(B) 머리행");
            warn("(A)(B) 머리행 문자 서식 불균일");
        }
        var got = hdr.contents.replace(/[\r\n]/g, "");
        if (got !== "(A)\t(B)") {
            warn("(A)(B) 머리행 내용 이상: " + got.substr(0, 40));
            return false;
        }
        // 실측 보정: 조판 결과의 실제 x가 목표(x1/x2)와 어긋나면 그만큼 당긴다
        // (탭/들여쓰기 기준점이 프레임 인셋과 다를 수 있어 좌표 계산만으론 부족)
        for (var it = 0; it < 4; it++) {
            try { doc.recompose(); } catch (e) {}
            ps = story.paragraphs;
            hdr = ps[absIdx];
            var curA = charX(hdr, 0);
            var curB = charX(hdr, 4);
            if (curA === null || curB === null) break;
            var dA = x1 - curA, dB = x2 - curB;
            if (Math.abs(dA) < 0.2 && Math.abs(dB) < 0.2) break;
            try {
                if (Math.abs(dA) >= 0.2) hdr.firstLineIndent = hdr.firstLineIndent + dA;
                if (Math.abs(dB) >= 0.2) {
                    var t0 = hdr.tabStops[0];
                    t0.position = t0.position + dB - (Math.abs(dA) >= 0.2 ? dA : 0);
                }
            } catch (e) { break; }
        }
        return true;
    } catch (e) { warn("(A)(B) 머리행 정렬 실패: " + e.message); return false; }
}

function packChoices(story, absIdxList, columns) {
    if (!absIdxList || absIdxList.length === 0) return false;
    var ps = story.paragraphs;
    var first = absIdxList[0], last = absIdxList[absIdxList.length - 1];
    if (last >= ps.length) return false;
    var items = [];
    for (var i = 0; i < absIdxList.length; i++) {
        items.push(ps[absIdxList[i]].contents.replace(/[\r\n]/g, ""));
    }
    var width = 0;
    try {
        var tf = ps[first].parentTextFrames[0];
        var gb = tf.geometricBounds;
        var ins = [0, 0, 0, 0];
        try { ins = tf.textFramePreferences.insetSpacing; } catch (e) {}
        width = (gb[3] - gb[1]) - ins[1] - ins[3];
    } catch (e) { return false; }
    if (width <= 0) return false;

    var rows = [];
    for (var r = 0; r < items.length; r += columns) {
        rows.push(items.slice(r, r + columns).join("\t"));
    }
    var style = ps[first].appliedParagraphStyle;
    try {
        var sChar = ps[first].characters[0].index;
        var eP = ps[last];
        var eLen = eP.characters.length;
        var lastCh = "";
        try { lastCh = eP.characters[eLen - 1].contents; } catch (e) {}
        var eIdx = (lastCh === "\r" && eLen >= 2) ? eLen - 2 : eLen - 1;
        var eChar = eP.characters[eIdx].index;
        var rng = story.characters.itemByRange(sChar, eChar);
        if (!rng.isValid) return false;
        rng.contents = rows.join("\r");
    } catch (e) { warn("선지 3열 묶기 실패: " + e.message); return false; }

    // 새로 만들어진 행에 스타일 + 탭 정지
    ps = story.paragraphs;
    var step = width / columns;
    for (var q = 0; q < rows.length; q++) {
        var para = ps[first + q];
        try { para.appliedParagraphStyle = style; } catch (e) {}
        resetCharFormat(doc, para);
        var fq = fontSignature(para);
        if (fq.mixed) RESULTS.mixed_format.push("3열 선지행");
        try {
            var ts = para.tabStops;
            while (ts.length > 0) { ts[0].remove(); ts = para.tabStops; }
            for (var cnum = 1; cnum < columns; cnum++) {
                para.tabStops.add({ alignment: TabStopAlignment.LEFT_ALIGN,
                                    position: step * cnum });
            }
        } catch (e) {}
    }
    return true;
}

// 묶은 뒤에도 문항이 한 프레임에 안 들어가면 프레임 하단을 조금 늘린다
function growFrameIfSpills(story, startIdx, endIdx, maxGrowMm) {
    var ps = story.paragraphs;
    if (startIdx >= ps.length || endIdx >= ps.length) return 0;
    function sameFrame() {
        var a = paraStartPage(ps[startIdx]), b = paraEndPage(ps[endIdx]);
        if (!a || !b) return true;
        var fa = null, fb = null;
        try { fa = ps[startIdx].parentTextFrames[0]; } catch (e) {}
        try {
            var tfs = ps[endIdx].parentTextFrames;
            fb = tfs[tfs.length - 1];
        } catch (e) {}
        return (fa && fb && fa === fb);
    }
    if (sameFrame()) return 0;
    var tf = null;
    try { tf = ps[startIdx].parentTextFrames[0]; } catch (e) { return 0; }
    if (!tf) return 0;
    var gb0 = tf.geometricBounds.slice ? tf.geometricBounds.slice(0)
        : [tf.geometricBounds[0], tf.geometricBounds[1],
           tf.geometricBounds[2], tf.geometricBounds[3]];
    var grown = 0;
    while (grown < maxGrowMm) {
        grown += 2;
        try {
            tf.geometricBounds = [gb0[0], gb0[1], gb0[2] + grown, gb0[3]];
            doc.recompose();
        } catch (e) { break; }
        ps = story.paragraphs;
        if (sameFrame()) { return grown; }
    }
    try { tf.geometricBounds = gb0; doc.recompose(); } catch (e) {}
    return 0;
}

function countStyle(story, styleName) {
    var n = 0, ps = story.paragraphs;
    for (var i = 0; i < ps.length; i++) {
        if (ps[i].appliedParagraphStyle.name === styleName) n++;
    }
    return n;
}

function applyChoiceLayout(story, flow, starts) {
    var aligned = 0, packed = 0, grown = 0;
    // 인덱스 변동을 피해 뒤 유닛부터 처리
    for (var u = flow.units.length - 1; u >= 0; u--) {
        var unit = flow.units[u];
        var base = starts[u] + (unit.unit_label ? 1 : 0);
        if (unit.ab_header !== undefined && unit.ab_header !== null) {
            alignAbOptions(story, base + unit.ab_header);
            if (alignAbHeader(story, base + unit.ab_header)) aligned++;
        }
        if (unit.choice_pack && unit.choice_pack.idx.length > 0) {
            var abs = [];
            for (var i = 0; i < unit.choice_pack.idx.length; i++) {
                abs.push(base + unit.choice_pack.idx[i]);
            }
            if (packChoices(story, abs, unit.choice_pack.columns || 3)) {
                packed++;
                try { doc.recompose(); } catch (e) {}
                var rows = Math.ceil(unit.choice_pack.idx.length /
                                     (unit.choice_pack.columns || 3));
                var endIdx = abs[0] + rows - 1;
                var g = growFrameIfSpills(story, starts[u], endIdx, 10);
                if (g > 0) { grown++; RESULTS.frames_grown.push(unit.no + "번 +" + g + "mm"); }
            }
        }
    }
    wlog("선지 레이아웃: 머리행 정렬 " + aligned + " / 3열 묶기 " + packed +
         " / 프레임 확장 " + grown);
    var stems = countStyle(story, "문제");
    RESULTS.choice_layout = { aligned: aligned, packed: packed, grown: grown,
                              stems: stems, units: flow.units.length };
    if (stems !== flow.units.length) {
        warn("레이아웃 후 발문 단락 수 불일치: " + stems + " vs 유닛 " +
             flow.units.length + " (자동번호 밀림 위험)");
    }
}

// ── 빈칸(전각 공백) 밑줄 ────────────────────────────────────────────────
// "is 　(A)　 for" 처럼 (X) 앞뒤의 전각 공백은 학생이 답을 쓰는 빈칸이다.
// 한글 문자스타일(.notdef 방지) 위에 밑줄을 얹어 빈칸이 보이게 한다.
function underlineBlanks(story, label) {
    // 빈칸은 라벨((A))까지 포함해 하나의 연속 밑줄이어야 빈칸으로 읽힌다.
    var pats = [" {3,}\\([A-Za-z0-9]\\) {3,}",     // ___(A)___ 통짜
                " {3,}(?=\\([A-Za-z0-9]\\))",
                "(?<=\\([A-Za-z0-9]\\)) {3,}"];
    var total = 0;
    for (var i = 0; i < pats.length; i++) {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = pats[i];
        var found = [];
        try { found = story.findGrep(); } catch (e) {
            warn(label + " 빈칸 탐색 오류: " + e.message);
        }
        app.findGrepPreferences = NothingEnum.NOTHING;
        for (var k = 0; k < found.length; k++) {
            try { found[k].underline = true; total++; } catch (e) {}
            // 밑줄 높이/두께를 명시해 폰트가 섞여도 한 줄로 이어지게
            try { found[k].underlineOffset = 1.2; } catch (e) {}
            try { found[k].underlineWeight = 0.5; } catch (e) {}
        }
        app.changeGrepPreferences = NothingEnum.NOTHING;
    }
    // 전각 밑줄문자(＿)는 글리프 자체가 빈칸 선이다 — 공백으로 바꾸면 줄바꿈에서
    // 사라지므로 그대로 두고, 폰트만 한글 폰트로 바꿔 .notdef를 막는다.
    var csK = findCharStyleAnywhere(doc, "한글");
    if (csK) {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "\\x{FF3F}+";
        var uf = [];
        try { uf = story.findGrep(); } catch (e) {}
        app.findGrepPreferences = NothingEnum.NOTHING;
        var fixedU = 0;
        for (var u2 = 0; u2 < uf.length; u2++) {
            var size = null;
            try { size = uf[u2].paragraphs[0].appliedParagraphStyle.pointSize; } catch (e) {}
            try { uf[u2].appliedCharacterStyle = csK; } catch (e) { continue; }
            if (size) { try { uf[u2].pointSize = size; } catch (e) {} }
            fixedU++;
        }
        wlog(label + " 전각 밑줄문자 폰트 보정: " + fixedU + "건");
    }
    RESULTS.blanks_underlined += total;
    wlog(label + " 빈칸 밑줄: " + total + "건");
}

// ── (4) 답란류 단락이 두 줄로 넘치면 자간을 줄여 한 줄에 맞춘다 ──────────
// 대상: 괄호/빈칸만으로 이뤄진 답란 (내용 글자가 없어 자간 축소가 안전)
function fitAnswerLinesToOneLine(story, label) {
    var fixed = 0, failed = [];
    var ps = story.paragraphs;
    for (var i = 0; i < ps.length; i++) {
        var t = ps[i].contents.replace(/[\r\n]/g, "");
        if (t.replace(/[\s　]/g, "").length === 0) continue;
        // 괄호·빈칸·구분자만 있는 줄 (예: "（   ）－（   ）－…")
        if (/[A-Za-z가-힣]/.test(t)) continue;
        if (!/[（(]|[＿_]/.test(t)) continue;
        var lines = 0;
        try { lines = ps[i].lines.length; } catch (e) { continue; }
        if (lines <= 1) continue;
        var tr = 0;
        while (lines > 1 && tr > -80) {
            tr -= 10;
            try { ps[i].tracking = tr; } catch (e) { break; }
            try { doc.recompose(); } catch (e) {}
            ps = story.paragraphs;
            try { lines = ps[i].lines.length; } catch (e) { break; }
        }
        if (lines <= 1) { fixed++; }
        else { failed.push(t.substr(0, 30)); try { ps[i].tracking = 0; } catch (e) {} }
    }
    RESULTS.oneline_fitted += fixed;
    if (failed.length) RESULTS.oneline_failed = RESULTS.oneline_failed.concat(failed);
    wlog(label + " 답란 한 줄 맞춤: " + fixed + "건" +
         (failed.length ? " / 실패 " + failed.length : ""));
}

// ── (5) 마지막 페이지 크레딧 (스니펫 배치) ──────────────────────────────
function placeCredit(doc, credit) {
    if (!credit || !credit.items) return;
    var last = doc.pages[doc.pages.length - 1];
    for (var i = 0; i < credit.items.length; i++) {
        var it = credit.items[i];
        var f = new File(it.file);
        if (!f.exists) { warn("크레딧 스니펫 없음: " + it.file); continue; }
        var placed = null;
        try { placed = last.place(f); } catch (e) { warn("크레딧 배치 실패: " + e.message); continue; }
        var obj = (placed instanceof Array) ? placed[0] : placed;
        if (!obj) continue;
        try {
            var gb = obj.geometricBounds;
            var h = gb[2] - gb[0], w = gb[3] - gb[1];
            obj.geometricBounds = [it.y, it.x, it.y + h, it.x + w];
        } catch (e) { warn("크레딧 위치 지정 실패: " + e.message); }
        RESULTS.credit_placed.push(it.file.split("/").pop());
    }
    // 라벨(Writer/Assistant/…)이 옅어 잘 안 보인다 → 본문 메인 색으로
    if (credit.label_color) {
        var col = null;
        try { col = doc.colors.itemByName(credit.label_color); if (!col.isValid) col = null; } catch (e) {}
        if (col) {
            var n = 0;
            var labels = credit.labels || ["Writer", "Assistant", "Design",
                                           "Production", "Marketer"];
            var frames = last.textFrames;
            for (var t = 0; t < frames.length; t++) {
                var ps2;
                try { ps2 = frames[t].paragraphs; } catch (e) { continue; }
                for (var q = 0; q < ps2.length; q++) {
                    var txt = ps2[q].contents.replace(/[\r\n\s]/g, "");
                    for (var L = 0; L < labels.length; L++) {
                        if (txt === labels[L]) {
                            try { ps2[q].fillColor = col; n++; } catch (e) {}
                        }
                    }
                }
            }
            wlog("크레딧 라벨 색: " + n + "개 → " + credit.label_color);
        } else { warn("크레딧 라벨 색 없음: " + credit.label_color); }
    }
    wlog("크레딧 배치: " + RESULTS.credit_placed.length + "건 (p" + last.name + ")");
}

// 마지막 페이지 장식(N 그래픽) 색을 본문 마스터 팔레트로 맞춘다
function recolorLastPage(doc, mapping) {
    if (!mapping) return;
    var last = doc.pages[doc.pages.length - 1];
    var items = last.allPageItems, n = 0;
    for (var i = 0; i < items.length; i++) {
        for (var from in mapping) {
            var to = null;
            try { to = doc.colors.itemByName(mapping[from]); if (!to.isValid) to = null; } catch (e) {}
            if (!to) continue;
            try {
                if (items[i].fillColor && items[i].fillColor.name === from) {
                    items[i].fillColor = to; n++;
                }
            } catch (e) {}
            try {
                if (items[i].strokeColor && items[i].strokeColor.name === from) {
                    items[i].strokeColor = to; n++;
                }
            } catch (e) {}
        }
    }
    RESULTS.recolored = n;
    wlog("마지막 페이지 색 정합: " + n + "개 항목");
}

// ── 오버플로우 시 페이지·프레임 증설 ────────────────────────────────────
// 프레임 속성 이식 (텍스트는 옮기지 않는다)
function copyFrameProps(src, dst) {
    var tp = ["insetSpacing", "textColumnCount", "textColumnGutter",
              "verticalJustification", "firstBaselineOffset",
              "autoSizingType", "autoSizingReferencePoint",
              "ignoreWrap", "useFlexibleColumnWidth"];
    for (var i = 0; i < tp.length; i++) {
        try { dst.textFramePreferences[tp[i]] = src.textFramePreferences[tp[i]]; }
        catch (e) {}
    }
    var fp = ["strokeWeight", "strokeColor", "fillColor", "strokeTint",
              "fillTint", "cornerRadius", "textWrapPreferences"];
    for (var j = 0; j < fp.length; j++) {
        try { dst[fp[j]] = src[fp[j]]; } catch (e) {}
    }
    try { dst.appliedObjectStyle = src.appliedObjectStyle; } catch (e) {}
}

function frameGeomOfPage(pg) {
    var arr = [], tfs = pg.textFrames;
    for (var i = 0; i < tfs.length; i++) {
        var gb = tfs[i].geometricBounds;
        if ((gb[2] - gb[0]) < 100) continue;
        arr.push({ gb: gb, tf: tfs[i] });
    }
    arr.sort(function (a, b) { return a.gb[1] - b.gb[1]; });
    return arr;
}

function expandStory(doc, story, label) {
    var _len0 = -1;
    try { _len0 = story.length; } catch (e) {}
    var left = null, right = null;
    var tc = story.textContainers;
    for (var i = 0; i < tc.length; i++) {
        var pg = pageOfFrame(tc[i]);
        if (!pg) continue;
        if (pg.side === PageSideOptions.LEFT_HAND) { if (!left) left = frameGeomOfPage(pg); }
        else if (!right) { right = frameGeomOfPage(pg); }
    }
    if (!left || !right) { warn(label + " 기하 정보 부족 — 증설 생략"); return 0; }
    var protoL = left[0].tf, protoR = right[0].tf;

    function lastFrame() {
        var t = story.textContainers;
        return t.length ? t[t.length - 1] : null;
    }
    var lf = lastFrame(), added = 0, guard = 0;
    while (lf && lf.isValid && lf.overflows && guard < 200) {
        guard++;
        var anchor = pageOfFrame(lf);
        if (!anchor) break;
        var newPages = [];
        for (var k = 0; k < 2; k++) {
            var np;
            try {
                np = doc.pages.add(LocationOptions.AFTER, anchor);
                if (anchor.appliedMaster) np.appliedMaster = anchor.appliedMaster;
            } catch (e) { warn(label + " 페이지 추가 실패: " + e.message); break; }
            newPages.push(np);
            anchor = np;
        }
        if (newPages.length === 0) break;
        for (var q = 0; q < newPages.length; q++) {
            var pg2 = newPages[q];
            var isLeft = (pg2.side === PageSideOptions.LEFT_HAND);
            var list = isLeft ? left : right;
            var proto = isLeft ? protoL : protoR;
            for (var g = 0; g < list.length; g++) {
                // 프레임 복제(duplicate)는 원본의 '보이는 텍스트'까지 복사해
                // 스레드에 붙는 순간 스토리에 그 조각이 끼어든다(실측: 정답지 +70자).
                // → 빈 프레임을 새로 만들고 속성만 옮긴다.
                var nf = null;
                try { nf = pg2.textFrames.add({ geometricBounds: list[g].gb }); }
                catch (e2) { warn(label + " 프레임 생성 실패: " + e2.message); continue; }
                copyFrameProps(proto, nf);
                try { lf.nextTextFrame = nf; lf = nf; added++; }
                catch (e3) { warn(label + " 스레드 연결 실패: " + e3.message); }
            }
        }
        lf = lastFrame();
    }
    if (added > 0) wlog(label + " 프레임 증설: " + added + "개 (총 " + story.textContainers.length + ")");
    var _len1 = -1;
    try { _len1 = story.length; } catch (e) {}
    if (_len0 >= 0 && _len1 >= 0 && _len1 !== _len0) {
        RESULTS.story_len_drift.push(label + ": " + _len0 + "→" + _len1);
        warn(label + " 페이지 증설 중 스토리 길이 변동 " + _len0 + "→" + _len1 +
             " (프레임 복제가 텍스트를 끌고 왔을 가능성)");
    }
    return added;
}

// ── 정답지: 한 문항 블록이 스프레드를 넘지 않게 ─────────────────────────
function keepBlocksInSpread(doc, story, numStyleName) {
    var moved = 0, guard = 0, movedKey = {};
    while (guard < 300) {
        guard++;
        try { doc.recompose(); } catch (e) {}
        var ps = story.paragraphs;
        var starts = [];
        for (var i = 0; i < ps.length; i++) {
            if (ps[i].appliedParagraphStyle.name === numStyleName) starts.push(i);
        }
        var did = false;
        for (var b = 0; b < starts.length; b++) {
            var s = starts[b];
            var e = (b + 1 < starts.length) ? starts[b + 1] - 1 : ps.length - 1;
            while (e > s && ps[e].contents.replace(/[\s\r\n]/g, "").length === 0) e--;
            var sp = paraStartPage(ps[s]), ep = paraEndPage(ps[e]);
            if (!sp || !ep || sp.parent === ep.parent) continue;
            var key = ps[s].contents.replace(/[\r\n]/g, "");
            if (movedKey[key]) continue;
            try { ps[s].startParagraph = StartParagraph.NEXT_PAGE; }
            catch (e2) { continue; }
            movedKey[key] = true;
            moved++;
            RESULTS.moved_blocks.push(key);
            did = true;
            break;
        }
        if (!did) break;
    }
    wlog("정답지 펼침면 걸침 정리: " + moved + "블록");
    return moved;
}

// 블록 시작이 프레임 하단에 몰려 몇 줄만 걸치면 통째로 다음 칼럼으로 민다.
// (번호만 덩그러니 남거나 한두 줄만 남는 꼴 방지 — 옆 칼럼/페이지가 비어 있다)
function blockLinesInStartFrame(ps, s0, e0) {
    // 블록 시작 프레임에 담긴 '번호 이후' 줄 수와, 다음 프레임으로 넘어가는지 반환
    var startFrame = null;
    try { startFrame = ps[s0].parentTextFrames[0]; } catch (e) { return null; }
    if (!startFrame) return null;
    var after = 0, spills = false;
    for (var q = s0; q <= e0; q++) {
        var lns;
        try { lns = ps[q].lines; } catch (e) { continue; }
        for (var li = 0; li < lns.length; li++) {
            var f = null;
            try { f = lns[li].parentTextFrames[0]; } catch (e) {}
            if (f === startFrame) { if (q > s0) after++; }
            else spills = true;
        }
    }
    return { after: after, spills: spills, frame: startFrame };
}

// 블록 시작이 프레임 하단에 몰려 번호+한두 줄만 걸치면 통째로 다음 칼럼으로 민다.
function pushOrphanBlocks(doc, story, numStyleName, minAfter) {
    var moved = 0, guard = 0, movedKey = {};
    while (guard < 300) {
        guard++;
        try { doc.recompose(); } catch (e) {}
        var ps = story.paragraphs;
        var starts = [];
        for (var i = 0; i < ps.length; i++) {
            if (ps[i].appliedParagraphStyle.name === numStyleName) starts.push(i);
        }
        var did = false;
        for (var b = 0; b < starts.length; b++) {
            var s0 = starts[b];
            var e0 = (b + 1 < starts.length) ? starts[b + 1] - 1 : ps.length - 1;
            var info = blockLinesInStartFrame(ps, s0, e0);
            if (!info || !info.spills || info.after >= minAfter) continue;
            var key = ps[s0].contents.replace(/[\r\n]/g, "");
            if (movedKey[key]) continue;
            try { ps[s0].startParagraph = StartParagraph.NEXT_FRAME; }
            catch (e2) { continue; }
            movedKey[key] = true;
            moved++;
            RESULTS.orphan_moved.push(key);
            did = true;
            break;
        }
        if (!did) break;
    }
    if (moved > 0) wlog("정답지 고아 블록 이동: " + moved + "건");
    return moved;
}

// 남아 있는 고아 블록 목록 (검수 게이트 근거)
function orphanBlocksRemaining(story, numStyleName, minAfter) {
    var out = [];
    var ps = story.paragraphs;
    var starts = [];
    for (var i = 0; i < ps.length; i++) {
        if (ps[i].appliedParagraphStyle.name === numStyleName) starts.push(i);
    }
    for (var b = 0; b < starts.length; b++) {
        var s0 = starts[b];
        var e0 = (b + 1 < starts.length) ? starts[b + 1] - 1 : ps.length - 1;
        var info = blockLinesInStartFrame(ps, s0, e0);
        if (!info || !info.spills || info.after >= minAfter) continue;
        out.push(ps[s0].contents.replace(/[\r\n]/g, "") + "번(" + info.after + "줄)");
    }
    return out;
}

// 잔존 걸침 재검사 (검수 게이트 B3의 근거)
function blocksCrossingSpread(story, numStyleName) {
    var out = [];
    var ps = story.paragraphs;
    var starts = [];
    for (var i = 0; i < ps.length; i++) {
        if (ps[i].appliedParagraphStyle.name === numStyleName) starts.push(i);
    }
    for (var b = 0; b < starts.length; b++) {
        var s = starts[b];
        var e = (b + 1 < starts.length) ? starts[b + 1] - 1 : ps.length - 1;
        while (e > s && ps[e].contents.replace(/[\s\r\n]/g, "").length === 0) e--;
        var sp = paraStartPage(ps[s]), ep = paraEndPage(ps[e]);
        if (!sp || !ep || sp.parent === ep.parent) continue;
        out.push(ps[s].contents.replace(/[\r\n]/g, "") + "번(p" + sp.name + "→p" + ep.name + ")");
    }
    return out;
}

// ── 유닛 시작 스프레드 마스터 ───────────────────────────────────────────
function applyUnitMasters(doc, story, labelParas, prefixes, label) {
    var mL = findMaster(doc, prefixes.left);
    var mR = findMaster(doc, prefixes.right);
    var mC = findMaster(doc, prefixes.cont);
    if (!mC) {
        RESULTS.missing_masters.push(prefixes.cont);
        warn(label + " 마스터 없음: " + prefixes.cont);
        return;
    }
    if (!mL) { RESULTS.missing_masters.push(prefixes.left); }
    if (!mR) { RESULTS.missing_masters.push(prefixes.right); }

    var startInfo = {};
    for (var u = 0; u < labelParas.length; u++) {
        var pg = paraStartPage(labelParas[u]);
        if (!pg) { warn(label + " 유닛 라벨 페이지 판정 실패"); continue; }
        startInfo[pg.parent.id] = (pg.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
        RESULTS.header_texts.push({
            area: label, page: pg.name,
            side: (pg.side === PageSideOptions.LEFT_HAND) ? "L" : "R",
            text: labelParas[u].contents.replace(/[\r\n]/g, "")
        });
    }
    var seen = {}, n0 = 0, n1 = 0, n2 = 0;
    var tc = story.textContainers;
    for (var i = 0; i < tc.length; i++) {
        var pg2 = pageOfFrame(tc[i]);
        if (!pg2) continue;
        var sp = pg2.parent;
        if (seen[sp.id]) continue;
        seen[sp.id] = true;
        var kind = startInfo[sp.id];
        var m = mC;
        if (kind === "L" && mL) { m = mL; n0++; }
        else if (kind === "R" && mR) { m = mR; n2++; }
        else n1++;
        for (var q = 0; q < sp.pages.length; q++) {
            try { sp.pages[q].appliedMaster = m; } catch (e) {}
        }
    }
    wlog(label + " 마스터: 시작(좌) " + n0 + " / 시작(우) " + n2 + " / 계속 " + n1);
}

// ── 전각 공백(U+3000) — 영문 문자스타일에서 .notdef 방지 ────────────────
function fixWideSpaces(doc, story, styleName, label) {
    // 전각공백(U+3000)은 영문 폰트에 글리프가 없어 .notdef 상자가 되고,
    // 한글 폰트를 섞으면 밑줄이 폰트마다 다른 높이로 끊긴다.
    // → 같은 폭의 일반 공백으로 바꿔 '한 폰트 한 런'으로 만든다 (빈칸 밑줄이 한 줄로 이어짐).
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\x{3000}";
    app.changeGrepPreferences.changeTo = "    ";      // 전각 1칸 ≈ 일반 4칸
    var n = 0;
    try { n = story.changeGrep().length; } catch (e) {
        warn(label + " 전각공백 치환 오류: " + e.message);
    }
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    RESULTS.wide_space_fixed += n;
    wlog(label + " 전각공백 → 일반공백: " + n + "건");
}

// ── 출력물 불변식 계측 (파서/플랜과 독립 — gate.py 원칙) ────────────────
// 긴 빈칸이 들어간 짧은 단락이 '지문' 스타일이면 서술형 답란이 지문처럼 조판된 것.
function auditAnswerLines(story, passageStyleLeaf) {
    var ps = story.paragraphs;
    for (var i = 0; i < ps.length; i++) {
        var t = ps[i].contents.replace(/[\r\n]/g, "");
        if (t.length > 200) continue;
        if (!/[＿_]{5,}/.test(t)) continue;
        var nm = ps[i].appliedParagraphStyle.name;
        if (nm === passageStyleLeaf) {
            RESULTS.answer_line_as_passage.push(t.substr(0, 40));
        }
    }
    if (RESULTS.answer_line_as_passage.length > 0) {
        warn("답란이 지문 스타일로 조판됨: " +
             RESULTS.answer_line_as_passage.length + "건");
    }
}

// ── 뒤쪽 빈 페이지 제거 (짝수 유지에 필요한 만큼만 남긴다) ───────────────
// 프레임 증설이 2쪽 단위라 본문/정답지 끝에 빈 스프레드가 남을 수 있다.
function trimTrailingEmptyPages(doc, story, label) {
    function isEmptyFrame(tf) {
        try { return tf.contents.replace(/[\s\r\n]/g, "").length === 0; }
        catch (e) { return false; }
    }
    var removed = 0, guard = 0;
    while (guard < 60) {
        guard++;
        var tc = story.textContainers;
        if (tc.length <= 2) break;
        var last = tc[tc.length - 1];
        if (!isEmptyFrame(last)) break;
        var pg = pageOfFrame(last);
        if (!pg) break;
        // 이 페이지의 본문 칼럼이 전부 비어 있어야 삭제
        var tfs = pg.textFrames, allEmpty = true, counted = 0;
        for (var i = 0; i < tfs.length; i++) {
            var gb;
            try { gb = tfs[i].geometricBounds; } catch (e) { continue; }
            if ((gb[2] - gb[0]) < 100) continue;
            counted++;
            if (!isEmptyFrame(tfs[i])) { allEmpty = false; break; }
        }
        if (!allEmpty || counted === 0) break;
        try { pg.remove(); removed++; } catch (e) { break; }
    }
    if (removed > 0) {
        // 짝수 페이지 유지: 홀수 개 지웠으면 한 쪽 되돌린다
        if (doc.pages.length % 2 !== 0) {
            try {
                var tc2 = story.textContainers;
                var anchor = pageOfFrame(tc2[tc2.length - 1]);
                if (anchor) { doc.pages.add(LocationOptions.AFTER, anchor); removed--; }
            } catch (e) {}
        }
        wlog(label + " 뒤쪽 빈 페이지 제거: " + removed + "쪽 (총 " + doc.pages.length + "쪽)");
    }
    RESULTS.trimmed_pages += removed;
    return removed;
}

// ── 뒤쪽 빈 페이지 → 메모 마스터 ────────────────────────────────────────
function memoizeBlankPages(doc, memoPrefix, unitPrefixes) {
    var memo = findMaster(doc, memoPrefix);
    if (!memo) { warn("메모 마스터 없음: " + memoPrefix); return; }
    var isUnit = {};
    for (var i = 0; i < unitPrefixes.length; i++) { isUnit[unitPrefixes[i]] = true; }
    for (var p = 0; p < doc.pages.length; p++) {
        var pg = doc.pages[p], mn = "";
        try { mn = pg.appliedMaster ? pg.appliedMaster.namePrefix : ""; } catch (e) {}
        if (!isUnit[mn]) continue;
        var tfs = pg.textFrames, counted = 0, empty = true;
        for (var t = 0; t < tfs.length; t++) {
            var gb;
            try { gb = tfs[t].geometricBounds; } catch (e) { continue; }
            if ((gb[2] - gb[0]) < 100) continue;
            counted++;
            var txt = "";
            try { txt = tfs[t].contents.replace(/[\s\r\n]/g, ""); } catch (e) {}
            if (txt.length > 0) { empty = false; break; }
        }
        if (!empty || counted === 0) continue;
        try { pg.appliedMaster = memo; RESULTS.memo_pages.push(pg.name); } catch (e) {}
    }
    wlog("빈 페이지 → 메모: " + RESULTS.memo_pages.length + "쪽");
}

// ── 실행 ────────────────────────────────────────────────────────────────
var doc = null;
try {
    wlog("배N제 v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    var ops = plan.ops || {};
    doc = app.open(File(TEMPLATE), false);

    var _origRuler = doc.viewPreferences.rulerOrigin;
    doc.viewPreferences.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;
    try { doc.textPreferences.smartTextReflow = false; } catch (e) {}

    var ranked = storiesByFrameCount(doc);
    if (ranked.length === 0) { throw "본문 스토리를 찾을 수 없음"; }
    var bodyStory = ranked[0].st;
    var ansStory = ranked.length > 1 ? ranked[1].st : null;
    wlog("스토리: 본문 프레임 " + ranked[0].n +
         (ansStory ? " / 정답지 " + ranked[1].n : " / 정답지 없음"));

    var bodyFlow = null, ansFlow = null;
    for (var f = 0; f < plan.flows.length; f++) {
        if (plan.flows[f].area === "body") bodyFlow = plan.flows[f];
        if (plan.flows[f].area === "answers") ansFlow = plan.flows[f];
    }

    purgeStaleUnitLabels(doc, ops.unit_char_style);

    var bodyRes = bodyFlow ? placeFlow(doc, bodyStory, bodyFlow, ops)
        : { labels: [], starts: [] };
    var bodyLabels = bodyRes.labels;
    expandStory(doc, bodyStory, "본문");

    var ansLabels = [];
    if (ansFlow && ansStory && ansFlow.units.length > 0) {
        var ansRes = placeFlow(doc, ansStory, ansFlow, ops);
        ansLabels = ansRes.labels;
    phase("A-배치후", ansStory);
        expandStory(doc, ansStory, "정답지");
    }

    if (ops.wide_space_style) {
    phase("B-전각공백전", ansStory);
        fixWideSpaces(doc, bodyStory, ops.wide_space_style, "본문");
        if (ansStory) fixWideSpaces(doc, ansStory, ops.wide_space_style, "정답지");
    }

    // 선지 머리행 정렬 + 3열 묶기 (전각공백 문자스타일 적용 뒤 = 실측 좌표 확정)
    try { doc.recompose(); } catch (e) {}
    phase("C-선지레이아웃전", ansStory);
    if (bodyFlow) applyChoiceLayout(bodyStory, bodyFlow, bodyRes.starts);
    // 빈칸((X) 앞뒤 전각공백)에 밑줄 — 머리행을 탭으로 바꾼 뒤에 실행해야
    // 머리행의 칸 사이 공백이 밑줄로 오인되지 않는다
    phase("D-밑줄전", ansStory);
    underlineBlanks(bodyStory, "본문");
    phase("E-한줄맞춤전", ansStory);
    fitAnswerLinesToOneLine(bodyStory, "본문");
    expandStory(doc, bodyStory, "본문(레이아웃 후)");

    try { doc.recompose(); } catch (e) {}

    if (ops.keep_block_in_spread === "answers" && ansStory && ansLabels.length >= 0) {
        // 두 규칙(펼침면 걸침 / 고아)은 서로 배치를 바꾸므로 안정될 때까지 번갈아 적용
        for (var rd = 0; rd < 6; rd++) {
            var m1 = pushOrphanBlocks(doc, ansStory, "정답_문제 번호", 3);
            var m2 = keepBlocksInSpread(doc, ansStory, "정답_문제 번호");
            expandStory(doc, ansStory, "정답지(블록 정리 " + (rd + 1) + "회)");
            if (m1 === 0 && m2 === 0) break;
        }
        try { doc.recompose(); } catch (e) {}
        RESULTS.orphan_remaining = orphanBlocksRemaining(ansStory, "정답_문제 번호", 3);
        if (RESULTS.orphan_remaining.length > 0) {
            warn("정답지 고아 블록 잔존 " + RESULTS.orphan_remaining.length + "건: " +
                 RESULTS.orphan_remaining.join(", "));
        }
        try { doc.recompose(); } catch (e) {}
        RESULTS.blocks_crossing_after = blocksCrossingSpread(ansStory, "정답_문제 번호");
        if (RESULTS.blocks_crossing_after.length > 0) {
            warn("정답지 펼침면 걸침 잔존 " + RESULTS.blocks_crossing_after.length + "건 "
                 + "(한 펼침면보다 긴 블록)");
        }
    }

    var um = ops.unit_masters || {};
    if (um.body) applyUnitMasters(doc, bodyStory, bodyLabels, um.body, "본문");
    if (um.answers && ansStory) applyUnitMasters(doc, ansStory, ansLabels, um.answers, "정답지");

    auditAnswerLines(bodyStory, "!박스-내용_");

    trimTrailingEmptyPages(doc, bodyStory, "본문");
    if (ansStory) trimTrailingEmptyPages(doc, ansStory, "정답지");

    phase("F-크레딧전", ansStory);
    if (ops.credit) placeCredit(doc, ops.credit);
    phase("G-크레딧후", ansStory);
    if (ops.last_page_colors) recolorLastPage(doc, ops.last_page_colors);

    if (ops.memo_master) {
        var prefixes = [];
        if (um.body) { prefixes.push(um.body.left); prefixes.push(um.body.right); prefixes.push(um.body.cont); }
        if (um.answers) { prefixes.push(um.answers.left); prefixes.push(um.answers.right); prefixes.push(um.answers.cont); }
        memoizeBlankPages(doc, ops.memo_master, prefixes);
    }

    try { doc.recompose(); } catch (e) {}

    // 오버플로우 집계 (본문/정답지만 — 장식 스토리는 템플릿 상태 그대로)
    var checkStories = [bodyStory];
    if (ansStory) checkStories.push(ansStory);
    for (var s2 = 0; s2 < checkStories.length; s2++) {
        var tcs = checkStories[s2].textContainers;
        for (var t2 = 0; t2 < tcs.length; t2++) {
            if (tcs[t2].isValid && tcs[t2].overflows) {
                RESULTS.overflow++;
                try { RESULTS.overflow_heads.push(tcs[t2].contents.substr(0, 40)); } catch (e) {}
            }
        }
    }
    // 머리말 소스 개수 = 심은 라벨 수 여야 한다 (묵은 라벨 잔존 감지)
    (function () {
        var cs = findCharStyleAnywhere(doc, ops.unit_char_style || "유닛");
        if (!cs) return;
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findTextPreferences.appliedCharacterStyle = cs;
        app.findChangeTextOptions.includeMasterPages = false;
        try { RESULTS.unit_label_sources = doc.findText().length; } catch (e) {}
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
    })();
    phase("H-최종", ansStory);
    RESULTS.pages = doc.pages.length;
    wlog("오버플로우: " + RESULTS.overflow + "개 / 페이지: " + RESULTS.pages);

    try { doc.viewPreferences.rulerOrigin = _origRuler; } catch (e) {}
    try { doc.recompose(); } catch (e) {}
    doc.save(File(OUT_INDD));
    try { doc.recompose(); } catch (e) {}
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    writeJSON(RESULT, RESULTS);
    doc.close(SaveOptions.NO);
    doc = null;
    wlog("배N제 v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { RESULTS.warnings.push("[오류] " + e); writeJSON(RESULT, RESULTS); } catch (e3) {}
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
