#target "InDesign"

var doc = app.activeDocument;
var result = [];

// 1~39페이지 단락스타일 사용 현황
var styleCount = {};

for (var pi = 0; pi < 39 && pi < doc.pages.length; pi++) {
    var page = doc.pages[pi];
    var frames = page.textFrames;
    for (var fi = 0; fi < frames.length; fi++) {
        var paras = frames[fi].paragraphs;
        for (var i = 0; i < paras.length; i++) {
            var sname = paras[i].appliedParagraphStyle.name;
            styleCount[sname] = (styleCount[sname] || 0) + 1;
        }
    }
}

result.push("=== 1~39페이지 단락스타일 ===");
for (var k in styleCount) {
    result.push("[" + k + "]: " + styleCount[k] + "개");
}

// 40페이지 이후 분석
var styleCount2 = {};
for (var pi = 39; pi < doc.pages.length; pi++) {
    var page = doc.pages[pi];
    var frames = page.textFrames;
    for (var fi = 0; fi < frames.length; fi++) {
        var paras = frames[fi].paragraphs;
        for (var i = 0; i < paras.length; i++) {
            var sname = paras[i].appliedParagraphStyle.name;
            styleCount2[sname] = (styleCount2[sname] || 0) + 1;
        }
    }
}

result.push("\n=== 40~78페이지 단락스타일 ===");
for (var k in styleCount2) {
    result.push("[" + k + "]: " + styleCount2[k] + "개");
}

// 미주 확인
result.push("\n=== 미주 확인 ===");
var totalEndnotes = 0;
var stories = doc.stories;
for (var s = 0; s < stories.length; s++) {
    try {
        var en = stories[s].endnotes;
        if (en && en.length > 0) {
            totalEndnotes += en.length;
            result.push("스토리[" + s + "]: " + en.length + "개 미주");
            // 미주 텍스트 샘플
            for (var e = 0; e < Math.min(3, en.length); e++) {
                try {
                    result.push("  - " + en[e].storyOffset.contents.toString().substring(0, 30));
                } catch(ex) {}
            }
        }
    } catch(e2) {}
}
result.push("총 미주: " + totalEndnotes + "개");

// 1~5페이지 샘플 텍스트 (문제 형식 파악)
result.push("\n=== 1~5페이지 단락 샘플 ===");
for (var pi = 0; pi < 5 && pi < doc.pages.length; pi++) {
    result.push("-- " + (pi+1) + "페이지 --");
    var page = doc.pages[pi];
    var frames = page.textFrames;
    for (var fi = 0; fi < frames.length; fi++) {
        var paras = frames[fi].paragraphs;
        for (var i = 0; i < Math.min(5, paras.length); i++) {
            var txt = paras[i].contents.replace(/\r/g, "↵").substring(0, 50);
            var sname = paras[i].appliedParagraphStyle.name;
            result.push("  [" + sname + "] " + txt);
        }
    }
}

alert(result.join("\n"));
