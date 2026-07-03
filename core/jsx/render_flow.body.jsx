// v2 렌더 실행기 — 렌더 플랜(JSON)을 메인 스토리에 흘려넣는다 (lib.jsxinc 뒤에 concat).
// 플랜: [{"t": 단락텍스트, "s": 스타일명, "runs": [{"t","ul"}]}]
// 정책: 스타일이 문서에 없으면 자동 생성하지 않고 [경고] 로그 + 기본 스타일 유지.

var TEMPLATE = "__TEMPLATE_PATH__";   // 사본 (원본 아님 — 파이썬이 safe_copy)
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

// v1 검증 로직 이식: 페이지 프레임 집계로 메인 스토리 탐색
function findMainStory(doc) {
    var votes = {};
    var byId = {};
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
    var best = null;
    var bestN = 0;
    for (var sid2 in votes) {
        if (votes[sid2] > bestN) { bestN = votes[sid2]; best = byId[sid2]; }
    }
    return best;
}

var doc = null;
try {
    wlog("v2 조판 시작: " + TEMPLATE);
    var plan = readJSONFile(PLAN);
    doc = app.open(File(TEMPLATE), false);

    var story = findMainStory(doc);
    if (!story) { throw "메인 스토리를 찾을 수 없음"; }

    // 1) 전체 텍스트
    var texts = [];
    for (var i = 0; i < plan.length; i++) { texts.push(plan[i].t); }
    story.contents = texts.join("\r");
    wlog("텍스트 배치: " + plan.length + "개 단락");

    // 2) 문자 스타일 초기화 — texts[0](스토리 전체 범위 단일 객체) 사용.
    //    characters.everyItem()는 세션 상태에 따라 간헐적으로 수 분간 행
    //    (2026-07-05 두 차례 관측 — 동일 지점).
    wlog("문자 스타일 초기화 시작 (" + story.characters.length + "자)");
    story.texts[0].appliedCharacterStyle = doc.characterStyles[0];
    wlog("문자 스타일 초기화 완료");

    // 3) 단락 스타일 (전체 경로 탐색, 자동 생성 금지)
    var cache = {};
    var missing = {};
    var csUL = doc.characterStyles.itemByName("밑줄");
    for (var si = 0; si < plan.length && si < story.paragraphs.length; si++) {
        var name = plan[si].s;
        if (name === null) { continue; }
        if (!cache[name] && !missing[name]) {
            var ps = findParagraphStyleByPath(doc, name);
            if (ps) { cache[name] = ps; }
            else {
                missing[name] = true;
                wlog("[경고] 스타일 없음(자동 생성 안 함): " + name);
            }
        }
        if (cache[name]) {
            story.paragraphs[si].appliedParagraphStyle = cache[name];
        }
        // 밑줄 runs
        var runs = plan[si].runs;
        if (runs && runs.length > 0 && csUL.isValid) {
            var para = story.paragraphs[si];
            var off = 0;
            for (var ri = 0; ri < runs.length; ri++) {
                var rl = runs[ri].t.length;
                if (rl > 0 && runs[ri].ul) {
                    var a = off;
                    var b = off + rl - 1;
                    if (a < para.characters.length && b < para.characters.length) {
                        para.characters.itemByRange(a, b).appliedCharacterStyle = csUL;
                    }
                }
                off += rl;
            }
        }
        if ((si + 1) % 25 === 0) {
            wlog("스타일 적용: " + (si + 1) + "/" + plan.length);
        }
    }

    // 4) 오버플로우 집계
    var ovf = 0;
    for (var s2 = 0; s2 < doc.stories.length; s2++) {
        try {
            var tc = doc.stories[s2].textContainers;
            if (tc.length > 0 && tc[tc.length - 1].overflows) { ovf++; }
        } catch (e) {}
    }
    wlog("오버플로우: " + ovf + "개");

    // 5) 저장 + PDF
    doc.save(File(OUT_INDD));
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT_PDF));
    wlog("PDF: 성공 -> " + OUT_PDF);
    doc.close(SaveOptions.NO);
    doc = null;
    wlog("v2 조판 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
