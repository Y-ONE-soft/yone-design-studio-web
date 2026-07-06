#target "InDesign"

if (app.documents.length === 0) {
    alert("\ubb38\uc11c\ub97c \uc5f4\uc5b4\uc8fc\uc138\uc694.");
    exit();
}

var doc = app.activeDocument;
var START_PAGE = 40;

//--------------------------------------------------
// \uc2a4\ud0c0\uc77c \ucc38\uc870
//--------------------------------------------------

function getPStyle(name) {
    var all = doc.allParagraphStyles;
    for (var i = 0; i < all.length; i++) {
        if (all[i].name === name) return all[i];
    }
    return null;
}

var mundaeStyle    = getPStyle("\ubb38\uc81c");
var seonjiStyle    = getPStyle("\uc120\uc9c0");
var boxStyle       = getPStyle("!\ubc15\uc2a4-\ub0b4\uc6a9_");
var nextReadStyle  = getPStyle("\ub2e4\uc74c \uae00\uc744 \uc77d\uace0");
var smallBoxStyle  = getPStyle("!\uc791\uc740\ubc15\uc2a4");
var jogeonStyle    = getPStyle("\uc870\uac74");
var bogiStyle      = getPStyle("\ubcf4\uae30");
var noneCharStyle  = doc.characterStyles.itemByName("[\uc5c6\uc74c]");

if (!mundaeStyle)  { alert("'\ubb38\uc81c' \uc2a4\ud0c0\uc77c \ucc3e\uae30 \uc2e4\ud328"); exit(); }
if (!seonjiStyle)  { alert("'\uc120\uc9c0' \uc2a4\ud0c0\uc77c \ucc3e\uae30 \uc2e4\ud328"); exit(); }
if (!boxStyle)     { alert("'!\ubc15\uc2a4-\ub0b4\uc6a9_' \uc2a4\ud0c0\uc77c \ucc3e\uae30 \uc2e4\ud328"); exit(); }

var PRESERVE = {};
PRESERVE["\uc815\ub2f5_\ubb38\uc81c \ubc88\ud638"] = true;
PRESERVE["\uc815\ub2f5"]           = true;
PRESERVE["\uc815\ub2f5_"]          = true;
PRESERVE["\ud574\uc124_"]          = true;
PRESERVE["\ud574\uc124_\uc2dc\uc791"] = true;
PRESERVE["\ud574\uc11d"]           = true;
PRESERVE["\uc5b4\ud718"]           = true;


//--------------------------------------------------
// \ud504\ub808\uc784\ubcc4 \ub2e8\ub77d \uc2a4\ud0c0\uc77c \uc801\uc6a9
//--------------------------------------------------

function processFrame(frame) {
    try { if (frame.texts[0].length === 0) return; } catch(e) { return; }
    var ft = frame.texts[0];

    // 0-a. \uc5f0\uc18d \ube48 \ub2e8\ub77d \uc81c\uac70
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat   = "\\r{2,}";
    app.changeGrepPreferences.changeTo = "\\r";
    try { ft.changeGrep(); } catch (e) {}
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;

    // 0-b. \ubc11\uc904 \uae38\uc774 \uc815\uaddc\ud654
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat   = "_{10,}";
    app.changeGrepPreferences.changeTo = "_________________________";
    try { ft.changeGrep(); } catch (e) {}
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;

    // 1. \ubc11\uc904 \ubc94\uc704 \uc218\uc9d1
    var ulRanges = [];
    var tsr = ft.textStyleRanges;
    var cumIdx = 0;
    for (var u = 0; u < tsr.length; u++) {
        var rng = tsr[u];
        var rLen = rng.contents.length;
        if (rng.underline === true) {
            ulRanges.push({s: cumIdx, e: cumIdx + rLen - 1});
        }
        cumIdx += rLen;
    }

    // 2. \ubb38\uc790\uc2a4\ud0c0\uc77c + \uc624\ubc84\ub77c\uc774\ub4dc \ucd08\uae30\ud654
    try { ft.appliedCharacterStyle = noneCharStyle; } catch (e) {}
    try { ft.clearOverrides(OverrideType.CHARACTER_ONLY); } catch (e) {}

    var tbls = ft.tables;
    for (var ti = 0; ti < tbls.length; ti++) {
        var cells = tbls[ti].cells;
        for (var ci = 0; ci < cells.length; ci++) {
            try {
                cells[ci].texts[0].appliedCharacterStyle = noneCharStyle;
                cells[ci].texts[0].clearOverrides(OverrideType.CHARACTER_ONLY);
            } catch (e) {}
        }
    }

    // 3. \ub2e8\ub77d \uc2a4\ud0c0\uc77c \uc801\uc6a9 (\uc0c1\ud0dc \uba38\uc2e0 \u2014 \ud504\ub808\uc784\ub9c8\ub2e4 \ucd08\uae30\ud654)
    var inBogi = false, inJogon = false, inYoyak = false, nextIsGivenSent = false;

    var paras = ft.paragraphs;
    for (var i = 0; i < paras.length; i++) {
        var p   = paras[i];
        var txt = p.contents;

        if (PRESERVE[p.appliedParagraphStyle.name]) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
            continue;
        }

        if (txt.replace(/[\r\n\t \u0020]/g, "").length === 0) continue;

        var cc = txt.replace(/[\r\n]/g, "");

        // \u2193 \ub2e8\ub3c5
        if (/^\s*\u2193\s*$/.test(cc)) {
            p.appliedParagraphStyle = boxStyle;
            try { p.justification = Justification.CENTER_ALIGN; } catch (e) {}
            continue;
        }

        var isBogiHeader = /^\s*<\ubcf4\uae30>\s*$/.test(cc) || /^\s*\[\ubcf4\uae30\]\s*$/.test(cc);

        // \ubb38\uc81c \ub2e8\ub77d
        var isMundae = (
            /[\uAC00-\uD7A3]\?/.test(txt) ||
            /\uc2dc\uc624\./.test(txt) ||
            (/(\uc717\uae00|\uc704 \uae00)/.test(txt) && /\?/.test(txt))
        );
        if (isMundae) {
            inBogi = false; inJogon = false; inYoyak = false;
            nextIsGivenSent = /\uc8fc\uc5b4\uc9c4 \ubb38\uc7a5/.test(txt);
            p.appliedParagraphStyle = mundaeStyle;
            continue;
        }

        // inJogon
        if (inJogon) {
            if (isBogiHeader) {
                inJogon = false; inBogi = true;
                if (bogiStyle) p.appliedParagraphStyle = bogiStyle;
                continue;
            }
            if (/ \/ /.test(txt)) {
                p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
                continue;
            }
            if (jogeonStyle) { p.appliedParagraphStyle = jogeonStyle; continue; }
        }

        // <\ubcf4\uae30> \ud5e4\ub354
        if (isBogiHeader) {
            inBogi = true; inJogon = false; inYoyak = false;
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            continue;
        }

        // \ub2e4\uc74c \uae00\uc744 \uc77d\uace0
        if (/\ub2e4\uc74c \uae00\uc744 \uc77d\uace0/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
            if (nextReadStyle) p.appliedParagraphStyle = nextReadStyle;
            continue;
        }

        // <\uc870\uac74>
        if (/^\s*<\uc870\uac74>/.test(txt) || /^\s*\[\uc870\uac74\]/.test(txt)) {
            inBogi = false; inJogon = true; inYoyak = false;
            if (jogeonStyle) p.appliedParagraphStyle = jogeonStyle;
            continue;
        }

        // <\uc694\uc57d>
        if (/^\s*<\uc694\uc57d>/.test(txt) || /^\s*\[\uc694\uc57d\ubb38\]/.test(txt) || /^\s*\[\uc694\uc57d\]/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = true;
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            continue;
        }

        // \u2460~\u2464
        if (/^[\s\r\n]*[\u2460-\u2464]/.test(txt)) {
            inBogi = false; inJogon = false; inYoyak = false; nextIsGivenSent = false;
            p.appliedParagraphStyle = seonjiStyle;
            continue;
        }

        // inBogi
        if (inBogi) {
            if (/ \/ /.test(txt) || /\/ $/.test(cc)) {
                p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
                continue;
            }
            inBogi = false;
        }

        // inYoyak
        if (inYoyak) {
            if (/^\s*\([AB]\)/.test(txt)) {
                p.appliedParagraphStyle = seonjiStyle; continue;
            }
            if (smallBoxStyle) { p.appliedParagraphStyle = smallBoxStyle; continue; }
        }

        // \uc8fc\uc5b4\uc9c4 \ubb38\uc7a5
        if (nextIsGivenSent && /^\s*[A-Za-z("]/.test(txt) && !/^\s*\([A-E]\)/.test(txt)) {
            if (smallBoxStyle) p.appliedParagraphStyle = smallBoxStyle;
            nextIsGivenSent = false;
            continue;
        }

        // (A)~(E): \uc9c0\ubb38 vs \ub2f5\uc548\uce78
        if (/^\s*\([A-E]\)/.test(txt)) {
            var rest = cc.replace(/^\s*\([A-E]\)[\s:]*/, "");
            if (rest.length >= 25 && /^[A-Za-z"'\u201c\u2018]/.test(rest)) {
                p.appliedParagraphStyle = boxStyle;
            } else {
                p.appliedParagraphStyle = seonjiStyle;
            }
            continue;
        }

        // \ub2f5:
        if (/^\s*\ub2f5\s*:/.test(txt)) {
            p.appliedParagraphStyle = seonjiStyle; continue;
        }

        // \ub2e8\uc5b4 / \ub2e8\uc5b4 (\ubcf4\uae30 \ub2e8\uc5b4\ubaa9\ub85d)
        if (/ \/ /.test(txt)) {
            p.appliedParagraphStyle = bogiStyle || smallBoxStyle || boxStyle;
            continue;
        }

        // \ub098\uba38\uc9c0
        p.appliedParagraphStyle = boxStyle;
    }

    // 4. \ubc11\uc904 \ubcf5\uc6d0
    for (var r = 0; r < ulRanges.length; r++) {
        try {
            ft.characters.itemByRange(ulRanges[r].s, ulRanges[r].e).underline = true;
        } catch (e) {}
    }
}


//--------------------------------------------------
// \uba54\uc778
//--------------------------------------------------

function runMain() {
    var startPageIdx = START_PAGE - 1;

    // \uac01\uc8fc/\ubbf8\uc8fc \uc0ad\uc81c
    var deletedStories = {};
    for (var pi = startPageIdx; pi < doc.pages.length; pi++) {
        var frames = doc.pages[pi].textFrames;
        for (var fi = 0; fi < frames.length; fi++) {
            var frame = frames[fi];
            if (!frame.isValid) continue;
            var st = frame.parentStory;
            var sid = st.id;
            if (deletedStories[sid]) continue;
            deletedStories[sid] = true;
            try {
                var fnArr = st.footnotes;
                for (var f = fnArr.length - 1; f >= 0; f--) { try { fnArr[f].remove(); } catch(ex) {} }
            } catch(e1) {}
            try {
                var enArr = st.endnotes;
                for (var en = enArr.length - 1; en >= 0; en--) { try { enArr[en].remove(); } catch(ex) {} }
            } catch(e2) {}
        }
    }

    // \ud504\ub808\uc784\ubcc4 \uc2a4\ud0c0\uc77c \uc801\uc6a9
    for (var pi2 = startPageIdx; pi2 < doc.pages.length; pi2++) {
        var frames2 = doc.pages[pi2].textFrames;
        for (var fi2 = 0; fi2 < frames2.length; fi2++) {
            var frame2 = frames2[fi2];
            if (!frame2.isValid) continue;
            try { processFrame(frame2); } catch(e) {}
        }
    }

    // \uc624\ubc84\ud50c\ub85c\uc6b0 \ub2e8\ub3c5 \ud504\ub808\uc784 \uc790\ub3d9 \ub192\uc774 \uc870\uc808
    for (var pi3 = startPageIdx; pi3 < doc.pages.length; pi3++) {
        var frames3 = doc.pages[pi3].textFrames;
        for (var fi3 = 0; fi3 < frames3.length; fi3++) {
            var frame3 = frames3[fi3];
            if (!frame3.isValid) continue;
            if (!frame3.overflows) continue;
            if (frame3.parentStory.textContainers.length > 1) continue;
            try {
                frame3.textFramePreferences.autoSizingType = AutoSizingType.HEIGHT_ONLY;
                frame3.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.TOP_LEFT_POINT;
            } catch(e) {}
        }
    }
}

app.doScript(runMain, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "WhiteBook_E2");

// \ubb38\uc81c \ub2e8\ub77d\uc5d0 startParagraph NEXT_FRAME \uc124\uc815 (doScript \ubc14\uae65\uc5d0\uc11c\ub9cc \uc815\uc0c1 \ub3d9\uc791)
var kStartIdx = START_PAGE - 1;
for (var kpi = kStartIdx; kpi < doc.pages.length; kpi++) {
    var kfrs = doc.pages[kpi].textFrames;
    for (var kfi = 0; kfi < kfrs.length; kfi++) {
        var kfr = kfrs[kfi];
        if (!kfr.isValid) continue;
        if (kfr.parentStory.textContainers.length <= 1) continue;
        try {
            var kft = kfr.texts[0];
            if (kft.length === 0) continue;
            var kparas = kft.paragraphs;
            for (var ki = 0; ki < kparas.length; ki++) {
                var kp = kparas[ki];
                var ktxt = kp.contents.replace(/[\r\n]/g, "");
                var kIsMundae = (
                    /[\uAC00-\uD7A3]\?/.test(ktxt) ||
                    /\uc2dc\uc624\./.test(ktxt) ||
                    (/(\uc717\uae00|\uc704 \uae00)/.test(ktxt) && /\?/.test(ktxt))
                );
                if (kIsMundae) {
                    try { kp.startParagraph = StartParagraph.NEXT_FRAME; } catch(e) {}
                }
            }
        } catch(e) {}
    }
}
