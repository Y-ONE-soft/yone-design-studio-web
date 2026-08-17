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
    frames_grown: [], choice_layout: {}, warnings: []
};

function readJSONFile(path) {
    var f = new File(path);
    f.encoding = "UTF-8";
    f.open("r");
    var s = f.read();
    f.close();
    return eval("(" + s + ")");
}

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
        hdr.leftIndent = 0;
        hdr.firstLineIndent = Math.max(0, x1 - left);
        hdr.justification = Justification.LEFT_ALIGN;
        var ts = hdr.tabStops;
        while (ts.length > 0) { ts[0].remove(); ts = hdr.tabStops; }
        hdr.tabStops.add({ alignment: TabStopAlignment.LEFT_ALIGN,
                           position: Math.max(1, x2 - left) });
        var got = hdr.contents.replace(/[\r\n]/g, "");
        if (got !== "(A)\t(B)") {
            warn("(A)(B) 머리행 내용 이상: " + got.substr(0, 40));
            return false;
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
    var pats = ["\\x{3000}+(?=\\([A-Za-z0-9]\\))", "(?<=\\([A-Za-z0-9]\\))\\x{3000}+"];
    var total = 0;
    for (var i = 0; i < pats.length; i++) {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = pats[i];
        app.changeGrepPreferences.underline = true;
        try { total += story.changeGrep().length; } catch (e) {
            warn(label + " 빈칸 밑줄 오류: " + e.message);
        }
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
    }
    RESULTS.blanks_underlined += total;
    wlog(label + " 빈칸 밑줄: " + total + "건");
}

// ── 오버플로우 시 페이지·프레임 증설 ────────────────────────────────────
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
                var nf = null;
                try {
                    nf = proto.duplicate(pg2);
                    nf.geometricBounds = list[g].gb;
                    try { nf.contents = ""; } catch (e) {}
                } catch (e) { nf = null; }
                if (nf === null) {
                    try { nf = pg2.textFrames.add({ geometricBounds: list[g].gb }); }
                    catch (e2) { warn(label + " 프레임 생성 실패: " + e2.message); continue; }
                }
                try { lf.nextTextFrame = nf; lf = nf; added++; }
                catch (e3) { warn(label + " 스레드 연결 실패: " + e3.message); }
            }
        }
        lf = lastFrame();
    }
    if (added > 0) wlog(label + " 프레임 증설: " + added + "개 (총 " + story.textContainers.length + ")");
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
    var cs = findCharStyleAnywhere(doc, styleName);
    if (!cs) { warn("전각공백 보정용 '" + styleName + "' 문자스타일 없음"); return; }
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\x{3000}+";
    app.changeGrepPreferences.appliedCharacterStyle = cs;
    var n = 0;
    try { n = story.changeGrep().length; } catch (e) {}
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    RESULTS.wide_space_fixed += n;
    wlog(label + " 전각공백 보정: " + n + "건");
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

    var bodyRes = bodyFlow ? placeFlow(doc, bodyStory, bodyFlow, ops)
        : { labels: [], starts: [] };
    var bodyLabels = bodyRes.labels;
    expandStory(doc, bodyStory, "본문");

    var ansLabels = [];
    if (ansFlow && ansStory && ansFlow.units.length > 0) {
        var ansRes = placeFlow(doc, ansStory, ansFlow, ops);
        ansLabels = ansRes.labels;
        expandStory(doc, ansStory, "정답지");
    }

    if (ops.wide_space_style) {
        fixWideSpaces(doc, bodyStory, ops.wide_space_style, "본문");
        if (ansStory) fixWideSpaces(doc, ansStory, ops.wide_space_style, "정답지");
    }

    // 선지 머리행 정렬 + 3열 묶기 (전각공백 문자스타일 적용 뒤 = 실측 좌표 확정)
    try { doc.recompose(); } catch (e) {}
    if (bodyFlow) applyChoiceLayout(bodyStory, bodyFlow, bodyRes.starts);
    // 빈칸((X) 앞뒤 전각공백)에 밑줄 — 머리행을 탭으로 바꾼 뒤에 실행해야
    // 머리행의 칸 사이 공백이 밑줄로 오인되지 않는다
    underlineBlanks(bodyStory, "본문");
    expandStory(doc, bodyStory, "본문(레이아웃 후)");

    try { doc.recompose(); } catch (e) {}

    if (ops.keep_block_in_spread === "answers" && ansStory && ansLabels.length >= 0) {
        keepBlocksInSpread(doc, ansStory, "정답_문제 번호");
        expandStory(doc, ansStory, "정답지(블록 정리 후)");
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
