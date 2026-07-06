#target "InDesign"

if (app.documents.length === 0) {
    alert("문서를 열어주세요.");
    exit();
}

if (app.selection.length === 0) {
    alert("스토리를 선택하세요.");
    exit();
}

var doc = app.activeDocument;
var story = app.selection[0].parentStory;


//--------------------------------------------------
// 스타일 참조
//--------------------------------------------------

var problemStyle = doc.paragraphStyleGroups.itemByName("독해").paragraphStyles.itemByName("문제");
var 보기Style    = doc.paragraphStyleGroups.itemByName("독해").paragraphStyles.itemByName("보기");
var 선지Style    = doc.paragraphStyleGroups.itemByName("독해").paragraphStyles.itemByName("선지");
var boxStyle     = doc.paragraphStyleGroups.itemByName("독해").paragraphStyles.itemByName("!박스-내용");


//--------------------------------------------------
// 3. \r\r → \r
// 인덱스 수집 전에 실행하여 삭제로 인한 인덱스 혼란 방지
//--------------------------------------------------

app.findGrepPreferences = NothingEnum.NOTHING;
app.changeGrepPreferences = NothingEnum.NOTHING;
app.findGrepPreferences.findWhat = "\\r{2,}";
app.changeGrepPreferences.changeTo = "\\r";
story.changeGrep();
app.findGrepPreferences = NothingEnum.NOTHING;
app.changeGrepPreferences = NothingEnum.NOTHING;


//--------------------------------------------------
// 4. 헤더 단락 삭제
// 인덱스 수집 전에 실행
//--------------------------------------------------

var paras = story.paragraphs;
var firstQIdx = -1;
for (var i = 0; i < paras.length; i++) {
    var txt = paras[i].contents;
    if (/[가-힣]\?/.test(txt) || /고르시오\./.test(txt)) {
        firstQIdx = i;
        break;
    }
}
if (firstQIdx > 0) {
    for (var i = firstQIdx - 1; i >= 0; i--) {
        try { paras[i].remove(); } catch(e) {}
    }
    paras = story.paragraphs;
}


//--------------------------------------------------
// 6. ∙ → · 변환 (1:1 치환, 인덱스 변동 없음)
//--------------------------------------------------

app.findGrepPreferences = NothingEnum.NOTHING;
app.changeGrepPreferences = NothingEnum.NOTHING;
app.findGrepPreferences.findWhat = "∙";
app.changeGrepPreferences.changeTo = "·";
story.changeGrep();
app.findGrepPreferences = NothingEnum.NOTHING;
app.changeGrepPreferences = NothingEnum.NOTHING;


//--------------------------------------------------
// 11. [] → [                 ]
// 인덱스 수집 전에 실행 (인덱스 변동 있음)
//--------------------------------------------------

app.findGrepPreferences = NothingEnum.NOTHING;
app.changeGrepPreferences = NothingEnum.NOTHING;
app.findGrepPreferences.findWhat = "\\[\\s*\\]";
app.changeGrepPreferences.changeTo = "[                 ]";
story.changeGrep();
app.findGrepPreferences = NothingEnum.NOTHING;
app.changeGrepPreferences = NothingEnum.NOTHING;


//--------------------------------------------------
// 1. 밑줄 문자 인덱스 수집 (story-level 정수 인덱스)
//
// 텍스트 삭제/추가가 완료된 이 시점에서 수집 → 안정적인 인덱스
// textStyleRanges가 연속적으로 정렬되어 있음을 이용해
// 누적 카운트로 story-level 인덱스를 계산 (Character.index 속성 불필요)
//
// 이후 clearOverrides로 밑줄이 지워지지만 인덱스는 영향 없음
// frame break 삽입(step 13)으로 인한 shift는 복원 시 수학적으로 보정
//--------------------------------------------------

var ulIndices = [];
var tsr = story.textStyleRanges;
var cumIdx = 0;
for (var u = 0; u < tsr.length; u++) {
    var rangeLen = tsr[u].characters.length;
    if (tsr[u].characters[0].underline === true) {
        for (var j = 0; j < rangeLen; j++) {
            ulIndices.push(cumIdx + j);
        }
    }
    cumIdx += rangeLen;
}


//--------------------------------------------------
// 2. 문자스타일 + 로컬 오버라이드 완전 초기화
// story.texts[0] → 스토리 본문 텍스트 (D번호 등)
// 표 셀 내부 텍스트는 story.texts에 포함되지 않으므로 별도 처리
//--------------------------------------------------

try {
    story.texts[0].appliedCharacterStyle = doc.characterStyles.itemByName("[없음]");
} catch(e) {}

try {
    story.texts[0].clearOverrides(OverrideType.CHARACTER_ONLY);
} catch(e) {}

// 표 셀 내부 문자스타일 + 오버라이드 초기화
var noneStyle = doc.characterStyles.itemByName("[없음]");
var tbls = story.tables;
for (var ti = 0; ti < tbls.length; ti++) {
    var cells = tbls[ti].cells;
    for (var ci = 0; ci < cells.length; ci++) {
        try {
            cells[ci].texts[0].appliedCharacterStyle = noneStyle;
            cells[ci].texts[0].clearOverrides(OverrideType.CHARACTER_ONLY);
        } catch(e) {}
    }
}


//--------------------------------------------------
// 5. 한글 뒤 물음표 / 고르시오. → 문제 단락스타일
//--------------------------------------------------

for (var i = 0; i < paras.length; i++) {
    var txt = paras[i].contents;
    if (/[가-힣]\?/.test(txt) || /고르시오\./.test(txt)) {
        paras[i].appliedParagraphStyle = problemStyle;
    }
}


//--------------------------------------------------
// 7. <보기> / · → 보기 단락스타일
//--------------------------------------------------

for (var i = 0; i < paras.length; i++) {
    var p = paras[i];
    var txt = p.contents;
    if (p.appliedParagraphStyle == problemStyle) continue;
    if (/^\s*<\uBCF4\uAE30>/.test(txt)) { p.appliedParagraphStyle = 보기Style; continue; }
    if (/^\s*·/.test(txt)) { p.appliedParagraphStyle = 보기Style; continue; }
}


//--------------------------------------------------
// 8. ①~⑤ / — → 선지 단락스타일
//--------------------------------------------------

for (var i = 0; i < paras.length; i++) {
    var txt = paras[i].contents;
    if (/^[\s]*[①②③④⑤]/.test(txt) || /^\s*—/.test(txt)) {
        paras[i].appliedParagraphStyle = 선지Style;
    }
}


//--------------------------------------------------
// 9. (a)~(e) / → → !박스-내용 단락스타일
//--------------------------------------------------

if (boxStyle && boxStyle.isValid) {
    for (var i = 0; i < paras.length; i++) {
        var txt = paras[i].contents;
        if (/^\s*\([a-e]\)/.test(txt) || /^\s*→/.test(txt)) {
            paras[i].appliedParagraphStyle = boxStyle;
        }
    }
}


//--------------------------------------------------
// 12. 표 너비 → 텍스트 프레임 컬럼 너비에 맞춤
//     + !박스-셀 / !박스-표 스타일 생성 후 적용
//     색상·테두리 변경 시 스타일만 수정하면 됨
//--------------------------------------------------

// 배경색 확보 (없으면 생성)
var noneColor    = doc.swatches.itemByName("None");
var boxFillColor = doc.colors.itemByName("C=0 M=0 Y=14 K=5");
if (!boxFillColor || !boxFillColor.isValid) {
    boxFillColor = doc.colors.add({
        model: ColorModel.PROCESS,
        space: ColorSpace.CMYK,
        colorValue: [0, 0, 14, 5],
        name: "C=0 M=0 Y=14 K=5"
    });
}

// 셀스타일 "!박스-셀" 확보 (없으면 생성, 있으면 재사용)
var boxCellStyle = doc.cellStyles.itemByName("!\ubc15\uc2a4-\uc14c");
if (!boxCellStyle || !boxCellStyle.isValid) {
    boxCellStyle = doc.cellStyles.add({ name: "!\ubc15\uc2a4-\uc14c" });
}
boxCellStyle.fillColor = boxFillColor;
boxCellStyle.fillTint  = 50;
boxCellStyle.topEdgeStrokeWeight    = 0;
boxCellStyle.bottomEdgeStrokeWeight = 0;
boxCellStyle.leftEdgeStrokeWeight   = 0;
boxCellStyle.rightEdgeStrokeWeight  = 0;
try { boxCellStyle.topEdgeStrokeColor    = noneColor; } catch(e) {}
try { boxCellStyle.bottomEdgeStrokeColor = noneColor; } catch(e) {}
try { boxCellStyle.leftEdgeStrokeColor   = noneColor; } catch(e) {}
try { boxCellStyle.rightEdgeStrokeColor  = noneColor; } catch(e) {}

// 표스타일 "!박스-표" 확보 (없으면 생성, 있으면 재사용)
var boxTableStyle = doc.tableStyles.itemByName("!\ubc15\uc2a4-\ud45c");
if (!boxTableStyle || !boxTableStyle.isValid) {
    boxTableStyle = doc.tableStyles.add({ name: "!\ubc15\uc2a4-\ud45c" });
}
boxTableStyle.topBorderStrokeWeight    = 0;
boxTableStyle.bottomBorderStrokeWeight = 0;
boxTableStyle.leftBorderStrokeWeight   = 0;
boxTableStyle.rightBorderStrokeWeight  = 0;
try { boxTableStyle.topBorderStrokeColor    = noneColor; } catch(e) {}
try { boxTableStyle.bottomBorderStrokeColor = noneColor; } catch(e) {}
try { boxTableStyle.leftBorderStrokeColor   = noneColor; } catch(e) {}
try { boxTableStyle.rightBorderStrokeColor  = noneColor; } catch(e) {}
try { boxTableStyle.bodyRegionCellStyle = boxCellStyle; } catch(e) {}

var tables = story.tables;
for (var i = 0; i < tables.length; i++) {
    try {
        var tbl = tables[i];

        // 너비 조정
        var frame = null;
        try {
            var anchor = tbl.storyOffset;
            if (anchor && anchor.isValid) { frame = anchor.parentTextFrames[0]; }
        } catch(e2) {}
        if (!frame || !frame.isValid) frame = story.textContainers[0];
        var bounds  = frame.geometricBounds;
        var insets  = frame.textFramePreferences.insetSpacing;
        var numCols = frame.textFramePreferences.textColumnCount;
        var gutter  = frame.textFramePreferences.textColumnGutter;
        var total   = (bounds[3] - bounds[1]) - insets[1] - insets[3];
        var colW    = (total - gutter * (numCols - 1)) / numCols;
        tbl.width = colW;

        // 표스타일 적용
        tbl.appliedTableStyle = boxTableStyle;

        // 셀스타일 적용 + 로컬 오버라이드 제거 (RTF 임포트 잔존값 제거)
        var cells = tbl.cells;
        for (var c = 0; c < cells.length; c++) {
            try {
                cells[c].appliedCellStyle = boxCellStyle;
                cells[c].clearCellStyleOverrides();
            } catch(e3) {}
        }
    } catch(e) {}
}


//--------------------------------------------------
// 13. 문제별 프레임 나누기
//
// frame break 삽입 전에 삽입 위치(story-level index)를 기록
// → 밑줄 복원 시 shift 보정에 사용
//
// 역순(마지막→두 번째)으로 삽입:
//   앞쪽 삽입이 뒤쪽 위치에 영향을 주지 않으므로
//   pre-insertion index가 그대로 유효
//--------------------------------------------------

paras = story.paragraphs;
var problemParas = [];
for (var i = 0; i < paras.length; i++) {
    if (paras[i].appliedParagraphStyle.name === problemStyle.name) {
        problemParas.push(paras[i]);
    }
}

// frame break 삽입 위치 기록 (index = 단락 첫 문자의 story-level 위치)
var fbPositions = [];
for (var k = 1; k < problemParas.length; k++) {
    try {
        // 누적 카운트로 문제 단락의 story-level 시작 인덱스를 계산
        var paraStartIdx = 0;
        var allParas = story.paragraphs;
        for (var pi = 0; pi < allParas.length; pi++) {
            if (allParas[pi] === problemParas[k]) break;
            paraStartIdx += allParas[pi].characters.length;
        }
        fbPositions.push(paraStartIdx);
    } catch(e) {}
}

// 역순 삽입
for (var k = problemParas.length - 1; k >= 1; k--) {
    try {
        problemParas[k].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
    } catch(e) {}
}


//--------------------------------------------------
// 14. 프레임 부족 시 새 페이지·프레임 자동 추가 및 스레딩
//--------------------------------------------------

paras = story.paragraphs;
var totalProblems = 0;
for (var i = 0; i < paras.length; i++) {
    if (paras[i].appliedParagraphStyle.name === problemStyle.name) totalProblems++;
}

var storyContainers = story.textContainers;
var needed = totalProblems - storyContainers.length;

if (needed > 0) {
    var lastCont = storyContainers[storyContainers.length - 1];
    var lastStoryPage = lastCont.parentPage;

    var templateBounds = [];
    for (var i = 0; i < storyContainers.length; i++) {
        if (storyContainers[i].parentPage === lastStoryPage) {
            var b = storyContainers[i].geometricBounds;
            templateBounds.push([b[0], b[1], b[2], b[3]]);
        }
    }
    var framesPerPage = templateBounds.length || 4;
    var masterPage = lastStoryPage.appliedMaster;
    var insertAfterPage = lastStoryPage;
    var currentLastFrame = lastCont;
    var framesAdded = 0;

    while (framesAdded < needed) {
        var newPage = doc.pages.add(LocationOptions.AFTER, insertAfterPage);
        if (masterPage) {
            try { newPage.appliedMaster = masterPage; } catch(e) {}
        }
        insertAfterPage = newPage;

        for (var j = 0; j < framesPerPage && framesAdded < needed; j++) {
            var newTF = newPage.textFrames.add();
            newTF.geometricBounds = templateBounds[j];
            currentLastFrame.nextTextFrame = newTF;
            currentLastFrame = newTF;
            framesAdded++;
        }
    }
}


//--------------------------------------------------
// 밑줄 복원
//
// frame break 삽입으로 인한 story-level 인덱스 shift 보정:
//   역순으로 삽입했으므로 pre-insertion fbPositions가 그대로 유효
//   각 ulIndex에 대해 "fbPositions 중 ≤ ulIndex인 것의 수"만큼 shift
//
// story.characters[adjustedIdx]로 정확한 문자에 밑줄 적용
//--------------------------------------------------

for (var u = 0; u < ulIndices.length; u++) {
    var idx = ulIndices[u];
    var shift = 0;
    for (var f = 0; f < fbPositions.length; f++) {
        if (fbPositions[f] <= idx) shift++;
    }
    try {
        story.characters[idx + shift].underline = true;
    } catch(e) {}
}


//--------------------------------------------------
// !박스-내용 단락의 em dash(—) + 앞뒤 공백 밑줄 제거
// "word1 — word2" 형태에서 단어에만 밑줄, 구분자에는 밑줄 없음
//--------------------------------------------------

paras = story.paragraphs;
for (var i = 0; i < paras.length; i++) {
    if (!boxStyle || !boxStyle.isValid) break;
    if (paras[i].appliedParagraphStyle.name !== boxStyle.name) continue;
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat   = " *\u2014 *";
    app.changeGrepPreferences.underline = false;
    try { paras[i].changeGrep(); } catch(e) {}
    app.findGrepPreferences  = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
}


// alert("완료");
