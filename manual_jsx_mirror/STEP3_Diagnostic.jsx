// STEP3_Diagnostic.jsx
// 각 단계 실행 후 밑줄 런 수를 추적 → 0이 된 줄이 원인
// ※ 실행하면 문서가 실제로 수정됨. 완료 후 Ctrl+Z로 되돌리기

var doc = app.activeDocument;
var story = app.selection[0].parentStory;

// ─── 헬퍼: 밑줄 런(연속 밑줄 구간) 수 카운트 ────────────────────────────
function countUnderlinedRuns(s) {
    var count = 0;
    try {
        var ranges = s.textStyleRanges;
        for (var ri = 0; ri < ranges.length; ri++) {
            try { if (ranges[ri].underline === true) count++; } catch(e) {}
        }
    } catch(e) {}
    return count;
}

// ─── 헬퍼: 단락스타일 안전하게 가져오기 (없으면 null, exit 없음) ──────────
function safeGetStyle(groupName, styleName) {
    try {
        var norm = function(s) {
            return String(s).replace(/[\u3000\s]+/g,"").replace(/[_\-()\[\]{}]/g,"").toLowerCase();
        };
        var allGroups = [];
        (function collect(root) {
            try {
                var subs = root.paragraphStyleGroups.everyItem().getElements();
                for (var i = 0; i < subs.length; i++) {
                    if (subs[i] && subs[i].isValid) { allGroups.push(subs[i]); collect(subs[i]); }
                }
            } catch(e) {}
        })(doc);
        var g = null;
        for (var gi = 0; gi < allGroups.length; gi++) {
            if (norm(allGroups[gi].name) === norm(groupName)) { g = allGroups[gi]; break; }
        }
        if (!g) return null;
        var all = [];
        (function cs(grp) {
            try {
                var ss = grp.paragraphStyles.everyItem().getElements();
                for (var i = 0; i < ss.length; i++) if (ss[i] && ss[i].isValid) all.push(ss[i]);
            } catch(e) {}
            try {
                var sg = grp.paragraphStyleGroups.everyItem().getElements();
                for (var i = 0; i < sg.length; i++) if (sg[i] && sg[i].isValid) cs(sg[i]);
            } catch(e) {}
        })(g);
        for (var ai = 0; ai < all.length; ai++) {
            if (norm(all[ai].name) === norm(styleName)) return all[ai];
        }
    } catch(e) {}
    return null;
}

// ═══════════════════════════════════════════════════════════
var log = [];

// [0] 시작 전
log.push("[0] 시작 전:            " + countUnderlinedRuns(story) + " 런");

// ─── [1] 문자스타일 초기화 블록 ────────────────────────────────────────────
(function () {
    try {
        var noneChar = doc.characterStyles[0];
        var ranges = story.textStyleRanges;
        for (var ri = 0; ri < ranges.length; ri++) {
            try {
                var ul = ranges[ri].underline;
                ranges[ri].appliedCharacterStyle = noneChar;
                if (ul === true) ranges[ri].underline = true;
            } catch (_r) {}
        }
    } catch (e) {}
})();
log.push("[1] 문자스타일 초기화:  " + countUnderlinedRuns(story) + " 런");

// ─── [2] 개행 압축 GREP ────────────────────────────────────────────────────
(function () {
    var _fb = app.findGrepPreferences.properties;
    var _cb = app.changeGrepPreferences.properties;
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\r{2,}";
    app.changeGrepPreferences.changeTo = "\\r";
    story.changeGrep();
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.properties = _fb;
    app.changeGrepPreferences.properties = _cb;
})();
log.push("[2] 개행 압축 GREP:     " + countUnderlinedRuns(story) + " 런");

// ─── [3] 보기/조건 변환 GREP ───────────────────────────────────────────────
(function () {
    var _fb = app.findGrepPreferences.properties;
    var _cb = app.changeGrepPreferences.properties;
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\[\\s*보기\\s*\\]";
    app.changeGrepPreferences.changeTo = "<보기>";
    story.changeGrep();
    app.findGrepPreferences.findWhat = "\\[\\s*조건\\s*\\]";
    app.changeGrepPreferences.changeTo = "<조건>";
    story.changeGrep();
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.properties = _fb;
    app.changeGrepPreferences.properties = _cb;
})();
log.push("[3] 보기/조건 변환:     " + countUnderlinedRuns(story) + " 런");

// ─── [4] 전체 단락에 기본스타일(실전 문제 지문 올림포스_) 적용 ─────────────
var styleDefault = safeGetStyle("STEP 03", "실전 문제 지문 올림포스_");
if (styleDefault) {
    var ps4 = story.paragraphs;
    for (var d = 0; d < ps4.length; d++) {
        try { ps4[d].appliedParagraphStyle = styleDefault; } catch(e) {}
    }
    log.push("[4] 단락스타일 전체 적용: " + countUnderlinedRuns(story) + " 런");
} else {
    log.push("[4] 단락스타일 못찾음 → 스킵");
}

// ─── [5] 1차 분류(번호/선지/지문/배경 등 조건 분기) 적용 ────────────────────
var styleNum        = safeGetStyle("STEP 03", "S_실전문제 번호 수정 올림포스");
var styleChoices    = safeGetStyle("STEP 03", "S_선지 올림포스");
var styleIntro      = safeGetStyle("STEP 03", "다음 글을 읽고");
var styleAsterisk   = safeGetStyle("STEP 03", "영단어");
var styleBackground = safeGetStyle("STEP 03", "배경 올림포스");
var styleCond       = safeGetStyle("STEP 03", "조건 올림포스");
var styleView       = safeGetStyle("STEP 03", "보기 올림포스");

if (styleNum && styleChoices && styleDefault) {
    var ps5 = story.paragraphs;
    for (var i5 = 0; i5 < ps5.length; i5++) {
        var text = ps5[i5].contents.replace(/[\r\n]+$/, "");
        if (/주어진\s*(문장|글)/.test(text) || /들어갈\s*위치/.test(text)) {
            var n = i5 + 1;
            while (n < ps5.length) {
                var t2 = (ps5[n].contents || "").replace(/[\r\n]+$/, "");
                if (!/^\s*$/.test(t2)) { if (styleBackground) ps5[n].appliedParagraphStyle = styleBackground; break; }
                n++;
            }
        }
        if (/[가-힣]\?/.test(text))                               { ps5[i5].appliedParagraphStyle = styleNum;        continue; }
        if (/[①②③④⑤] /.test(text))                              { ps5[i5].appliedParagraphStyle = styleChoices;    continue; }
        if (text.indexOf("다음 글을 읽고 물음에 답하시오.") !== -1) { if (styleIntro) ps5[i5].appliedParagraphStyle = styleIntro; continue; }
        if (text.indexOf("시오") !== -1)                           { ps5[i5].appliedParagraphStyle = styleNum;        continue; }
        if (text.indexOf("*") !== -1)                              { if (styleAsterisk) ps5[i5].appliedParagraphStyle = styleAsterisk; continue; }
        if (/\(A\)  /.test(text))                                  { ps5[i5].appliedParagraphStyle = styleChoices;    continue; }
        if (/\(A\)\t/.test(text))                                  { ps5[i5].appliedParagraphStyle = styleChoices;    continue; }
    }
    log.push("[5] 1차 분류 적용:      " + countUnderlinedRuns(story) + " 런");
} else {
    log.push("[5] 일부 스타일 없음 → 스킵");
}

// ─── 결과 출력 ─────────────────────────────────────────────────────────────
var result = "=== 밑줄 소실 진단 결과 ===\n\n" + log.join("\n");

// 처음으로 0이 된 단계 강조
var prev = -1;
for (var li = 0; li < log.join("\n").split("\n").length; li++) {
    var m = log[li].match(/(\d+) 런/);
    if (m) {
        var cur = parseInt(m[1], 10);
        if (prev > 0 && cur === 0) {
            result += "\n\n▶ [" + li + "] 단계에서 밑줄이 사라짐";
        }
        prev = cur;
    }
}

if (prev === 0 && parseInt((log[0].match(/(\d+) 런/) || [0,0])[1], 10) === 0) {
    result += "\n\n※ 시작 전부터 밑줄이 없습니다. 선택한 텍스트 프레임을 확인하세요.";
}

alert(result);
