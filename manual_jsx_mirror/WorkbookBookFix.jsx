// WorkbookBookFix.jsx — STEP BY STEP 워크북 "합본" 점검·복구
//
// 왜 필요한가: 워크북 엔진(yone-design-web)은 **과 단위**로 .indd를 뽑고,
// 1·2·3과를 한 권으로 합치는 작업은 InDesign에서 사람이 한다. 스프레드를
// 복제해 붙이면 **문서 섹션(Section)은 따라오지 않는다** — 섹션 마커가
// 헤더 배지(A1/A2/B1/B2/C1/C2)와 홀수쪽 코너 러닝헤더를 그리기 때문에,
// 섹션이 빠진 과는 앞 과의 마커(예: C2)를 그대로 물려받아 인쇄된다.
// (배재2 워크북01 실측 2026-08-12: 3과 어휘 선택 2 배지가 C2로 납품)
//
// 하는 일
//   1) 섹션 마커 복구: 섹션 블록 첫 페이지마다 문서 섹션 생성/교정
//      (페이지 번호는 continueNumbering=true로 보존)
//   2) 빈 마스터 복구: 본문이 있는데 마스터가 M/없음인 페이지 → 이웃 마스터
//   3) 점검 보고: 순번만 남은 지문 라벨 {8}, 실전문제 머리 안내문 잔존
//
// 사용법: 합본 .indd를 연 뒤 실행. 기본은 **드라이런(보고만)**.
//         실제 적용하려면 아래 APPLY 를 true 로.
// 저장은 하지 않는다 (구글 드라이브 동기화는 사용자 판단).

#target "indesign"

var APPLY = false;          // true = 실제 수정, false = 보고만
var LOG_PATH = "/tmp/workbook_book_fix.txt";

// 섹션 제목(헤더 텍스트) → 배지 코드. 제목은 페이지 헤더 프레임의 텍스트.
var TITLE_CODE = [
    ["어휘 선택", "A1"],
    ["어법 선택", "A1"],
    ["본문 O/X", "A2"],
    ["본문 정리", "B1"],
    ["어법 O/X", "B1"],
    ["내용 종합", "B2"],
    ["문장 배열", "C1"],
    ["빈칸 어법", "C1"],
    ["빈칸 어휘", "C2"],
    ["영작 배열", "C2"]
];

var out = [];
function L(s) { out.push(s); }
function flush() {
    var f = File(LOG_PATH);
    f.encoding = "UTF-8";
    f.open("w");
    f.write(out.join("\n"));
    f.close();
}
function trim(s) { return String(s).replace(/^[\s ]+|[\s ]+$/g, ""); }
function squash(s) { return trim(s).replace(/\s+/g, " "); }

// 페이지 헤더 제목 프레임: 페이지 상단(짧은 한 줄 한글 텍스트).
// 짝수쪽만 제목을 갖는 내지가 있어 없으면 null (블록 이어짐으로 처리).
function pageTitle(pg) {
    var items;
    try { items = pg.allPageItems; } catch (e) { return null; }
    for (var i = 0; i < items.length; i++) {
        if (!(items[i] instanceof TextFrame)) { continue; }
        var c = "";
        try { c = String(items[i].contents); } catch (e2) { continue; }
        if (!c || c.length > 24 || c.indexOf("\r") !== -1) { continue; }
        if (items[i].geometricBounds[0] > 20) { continue; }   // 상단만
        var t = squash(c);
        for (var k = 0; k < TITLE_CODE.length; k++) {
            if (t.indexOf(TITLE_CODE[k][0]) !== -1) { return t; }
        }
    }
    return null;
}
function codeOfTitle(t) {
    for (var k = 0; k < TITLE_CODE.length; k++) {
        if (t.indexOf(TITLE_CODE[k][0]) !== -1) { return TITLE_CODE[k][1]; }
    }
    return null;
}
function masterNameOf(pg) {
    try { return pg.appliedMaster ? String(pg.appliedMaster.name) : ""; }
    catch (e) { return ""; }
}
function isEmptyMaster(doc, nm) {
    if (!nm) { return true; }
    try { return String(doc.masterSpreads.itemByName(nm).namePrefix) === "M"; }
    catch (e) { return false; }
}
// 검정 밑줄의 최빈 규격(굵기/오프셋/종류) — 발문 인용구 밑줄의 기준.
// 빨강(어법 표시용) 밑줄을 기준으로 삼지 않기 위해 색을 Black으로 한정한다.
function blackUnderlineRef(doc) {
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "[A-Za-z]{5,}";
    app.findGrepPreferences.underline = true;
    var g = [];
    try { g = doc.findGrep(); } catch (e) {}
    app.findGrepPreferences = NothingEnum.NOTHING;
    var tally = {}, sample = {}, best = null, bestN = 0;
    for (var i = 0; i < g.length && i < 500; i++) {
        var cn = "";
        try { cn = String(g[i].underlineColor.name); } catch (e2) { continue; }
        if (cn !== "Black") { continue; }
        var key = "";
        try {
            key = String(g[i].underlineWeight) + "|"
                + String(g[i].underlineOffset) + "|"
                + String(g[i].underlineType.name);
        } catch (e3) { continue; }
        tally[key] = (tally[key] || 0) + 1;
        if (!sample[key]) { sample[key] = g[i]; }
        if (tally[key] > bestN) { bestN = tally[key]; best = key; }
    }
    if (!best) { return null; }
    var t = sample[best];
    return { key: best, n: bestN, type: t.underlineType,
             weight: t.underlineWeight, offset: t.underlineOffset,
             color: t.underlineColor, tint: t.underlineTint,
             gap: t.underlineGapColor };
}

function hasBodyText(pg) {
    var tfs;
    try { tfs = pg.textFrames; } catch (e) { return false; }
    for (var i = 0; i < tfs.length; i++) {
        var c = "";
        try { c = String(tfs[i].contents); } catch (e2) {}
        if (trim(c).length > 40) { return true; }     // 헤더/라벨 프레임 제외
    }
    return false;
}

function run() {
    var doc = app.activeDocument;
    L("문서: " + doc.name + " (" + doc.pages.length + "쪽)  APPLY=" + APPLY);

    // ── 1) 섹션 마커 ────────────────────────────────────────────────────
    var blocks = [];            // {page, title, code}
    var cur = null;
    for (var p = 0; p < doc.pages.length; p++) {
        var t = pageTitle(doc.pages[p]);
        if (!t) { continue; }                 // 제목 없는 쪽 = 블록 이어짐
        if (t === cur) { continue; }
        cur = t;
        var code = codeOfTitle(t);
        if (code) { blocks.push({ pg: doc.pages[p], title: t, code: code }); }
    }
    L("\n[1] 섹션 블록 " + blocks.length + "개");
    // 그 페이지를 지배하는 섹션(= 앞쪽에서 가장 가까운 섹션 시작)의 마커.
    // 배지는 이 마커로 그려지므로, 블록에 자체 섹션이 없어도 지배 마커가
    // 기대 코드와 같으면 정상이다 (앞 블록과 코드가 같은 경우 — 배재1
    // '어휘 선택 1' 다음의 '어휘 선택 2'가 둘 다 A1이라 배지는 정상).
    function governingMarker(pgIndex) {
        var best = null, bestIdx = -1;
        for (var gi = 0; gi < doc.sections.length; gi++) {
            var si = -1;
            try { si = doc.sections[gi].pageStart.documentOffset; } catch (e) {}
            if (si >= 0 && si <= pgIndex && si > bestIdx) {
                bestIdx = si;
                best = doc.sections[gi];
            }
        }
        return best ? String(best.marker) : "";
    }
    var added = 0, retagged = 0, okCount = 0;
    for (var b = 0; b < blocks.length; b++) {
        var pg = blocks[b].pg, want = blocks[b].code;
        var sec = null;
        for (var s = 0; s < doc.sections.length; s++) {
            try {
                if (doc.sections[s].pageStart.id === pg.id) {
                    sec = doc.sections[s];
                    break;
                }
            } catch (e) {}
        }
        if (sec && String(sec.marker) === want) { okCount++; continue; }
        // 자체 섹션이 없더라도 지배 마커가 기대 코드와 같으면 배지는 정상
        if (!sec && governingMarker(pg.documentOffset) === want) {
            okCount++;
            continue;
        }
        if (!sec) {
            L("  [없음] p" + pg.name + " " + blocks[b].title
              + " → 섹션 신설 marker=" + want);
            if (APPLY) {
                try {
                    sec = doc.sections.add(pg);
                    sec.continueNumbering = true;
                    try { sec.includeSectionPrefix = false; } catch (e1) {}
                    try { sec.sectionPrefix = ""; } catch (e2) {}
                    try { sec.name = ""; } catch (e3) {}
                    sec.marker = want;
                    added++;
                } catch (e4) { L("    [실패] " + e4); }
            }
        } else {
            L("  [불일치] p" + pg.name + " " + blocks[b].title
              + " marker='" + sec.marker + "' → '" + want + "'");
            if (APPLY) {
                try { sec.marker = want; retagged++; } catch (e5) {
                    L("    [실패] " + e5);
                }
            }
        }
    }
    L("  정상 " + okCount + "개 / 신설 " + added + "개 / 교정 " + retagged + "개");
    if (APPLY) {
        L("  페이지 번호 확인: 첫쪽=" + doc.pages[0].name
          + " 끝쪽=" + doc.pages[doc.pages.length - 1].name
          + " (총 " + doc.pages.length + "쪽 — 번호가 밀렸으면 되돌릴 것)");
    }

    // ── 2) 본문 있는데 빈(M) 마스터 ──────────────────────────────────────
    L("\n[2] 빈 마스터 본문 페이지");
    var repaired = 0, found2 = 0;
    for (var q = 0; q < doc.pages.length; q++) {
        var pgq = doc.pages[q];
        var mn = masterNameOf(pgq);
        if (!isEmptyMaster(doc, mn)) { continue; }
        if (!hasBodyText(pgq)) { continue; }        // 의도된 빈 쪽/간지
        found2++;
        // 이웃(같은 쪽면) 마스터 채택: 앞쪽 우선, 없으면 뒤쪽
        var want2 = "";
        for (var d = 1; d <= 4 && !want2; d++) {
            var prev = (q - 2 * d >= 0) ? doc.pages[q - 2 * d] : null;
            var next = (q + 2 * d < doc.pages.length)
                ? doc.pages[q + 2 * d] : null;
            if (prev && !isEmptyMaster(doc, masterNameOf(prev))) {
                want2 = masterNameOf(prev);
            } else if (next && !isEmptyMaster(doc, masterNameOf(next))) {
                want2 = masterNameOf(next);
            }
        }
        L("  p" + pgq.name + " 마스터='" + (mn || "없음") + "' → "
          + (want2 || "(이웃 못 찾음)"));
        if (APPLY && want2) {
            try {
                pgq.appliedMaster = doc.masterSpreads.itemByName(want2);
                repaired++;
            } catch (e6) { L("    [실패] " + e6); }
        }
    }
    L("  대상 " + found2 + "개 / 복구 " + repaired + "개");

    // ── 3) 발문 인용구 밑줄 ─────────────────────────────────────────────
    // "밑줄 친 <영어 인용문>가 다음 글에서 의미하는 바…" 발문은 인용문 자체에
    // 밑줄이 들어가야 한다 (배재1 워크북01 검수 21건). 한글 조사 앞에서
    // 끊기므로 조사·마침표는 자연히 빠진다. 이미 밑줄이면 무접촉.
    L("\n[3] 발문 인용구 밑줄");
    // 참조 밑줄 규격: **검정 밑줄의 최빈값**. 아무 밑줄이나 잡으면 어법
    // 표시용 빨강(C15 M100 Y100)을 복제해 발문이 빨간 밑줄로 나온다
    // (2026-08-12 실측 — 능률(민)1과·창현1에서 실제로 발생).
    var ref = blackUnderlineRef(doc);
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "(?<=밑줄 친 )[A-Za-z][^가-힣\\r]{1,120}";
    var hits = doc.findGrep();
    var ulDone = 0, ulNeed = 0;
    for (var h = 0; h < hits.length; h++) {
        var t = hits[h];
        var s = String(t.contents);
        // 뒤쪽 공백만 제거. 여는 큰따옴표가 있으면 닫는 따옴표까지 인용문이라
        // 남긴다 (the “mother of forensic science.” 실측).
        var keep = s.replace(/\s+$/, "");
        var hasQuote = /[“"]/.test(keep);
        if (!hasQuote) { keep = keep.replace(/[”’']+$/, ""); }
        if (keep.length < 2 || !/[A-Za-z]{2}/.test(keep)) { continue; }
        var rng = t;
        try {
            if (keep.length < s.length) {
                rng = t.characters.itemByRange(0, keep.length - 1);
            }
        } catch (e9) { rng = t; }
        var state = null;
        try { state = rng.underline; } catch (e10) {}
        // 인용부호는 InDesign 특수문자(DOUBLE_RIGHT_QUOTE)라 범위의 underline
        // 판정에서 빠진다 — 따옴표 인용문은 상태와 무관하게 재적용(idempotent).
        if (state === true && !hasQuote) { continue; }
        ulNeed++;
        var pgn = "?";
        try { pgn = t.parentTextFrames[0].parentPage.name; } catch (e11) {}
        L("  p" + pgn + " 밑줄 없음: " + keep.substring(0, 50));
        if (APPLY) {
            try {
                rng.underline = true;
                if (ref) {
                    rng.underlineType = ref.type;
                    rng.underlineWeight = ref.weight;
                    rng.underlineOffset = ref.offset;
                    rng.underlineColor = ref.color;
                    rng.underlineTint = ref.tint;
                    rng.underlineGapColor = ref.gap;
                }
                ulDone++;
            } catch (e12) { L("    [실패] " + e12); }
        }
    }
    app.findGrepPreferences = NothingEnum.NOTHING;
    L("  인용구 " + hits.length + "건 중 밑줄 누락 " + ulNeed + "건 / 적용 "
      + ulDone + "건"
      + (ref ? " (검정 밑줄 규격 " + ref.key + ", 표본 " + ref.n + "건)"
             : " (검정 밑줄 표본 없음 — 기본 밑줄)"));

    // ── 4) 점검 보고 (자동 수정 안 함) ───────────────────────────────────
    L("\n[4] 점검 보고");
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^\\{\\d+\\}$";
    var num = doc.findGrep();
    var numPg = [];
    for (var n = 0; n < num.length; n++) {
        var pn = "?";
        try { pn = num[n].parentTextFrames[0].parentPage.name; } catch (e7) {}
        numPg.push("p" + pn + String(num[n].contents));
    }
    L("  순번만 남은 지문 라벨 " + num.length + "건"
      + (num.length ? ": " + numPg.join(" ") : "")
      + (num.length ? "  ← 보충지문이면 {Further Reading 1} 류로" : ""));
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "다음 글을 읽고 물음에 답하시오\\.";
    var intro = doc.findGrep();
    var introPg = [];
    for (var i2 = 0; i2 < intro.length; i2++) {
        var pn2 = "?";
        try { pn2 = intro[i2].parentTextFrames[0].parentPage.name; }
        catch (e8) {}
        introPg.push("p" + pn2);
    }
    L("  '다음 글을 읽고 물음에 답하시오.' " + intro.length + "건"
      + (intro.length ? ": " + introPg.join(",") : "")
      + "  ← 한 지문에 여러 문제가 달린 세트가 아니면 삭제");
    app.findGrepPreferences = NothingEnum.NOTHING;
    var ovf = 0;
    for (var st = 0; st < doc.stories.length; st++) {
        if (doc.stories[st].overflows) { ovf++; }
    }
    L("  오버플로우 스토리 " + ovf + "개");
    L("\n저장하지 않음 — 확인 후 사용자가 저장.");
}

try { run(); } catch (e) { L("FATAL: " + e + " line=" + e.line); }
app.findGrepPreferences = NothingEnum.NOTHING;
flush();
// 결과는 로그 파일로만 — alert()는 자동 실행(osascript)에서 모달로 멈춘다.
out.join("\n");
