// 선택된 스토리 안에서
// 1~6번 작업을 순서대로 자동 실행하는 스크립트
// (인디자인 한글버전 / iMac 기준)

// --------------------------------------
// 기본 검사 : 문서 & 선택 여부
// --------------------------------------
if (app.documents.length === 0) {
    alert("열려 있는 문서가 없습니다.");
    exit();
}

if (app.selection.length === 0) {
    alert("텍스트(스토리)를 선택한 후 스크립트를 실행하세요.");
    exit();
}

var doc = app.activeDocument;
var sel = app.selection[0];
var story;

// selection 에서 story 가져오기
if (sel.hasOwnProperty("parentStory")) {
    story = sel.parentStory;
} else if (sel.constructor.name === "Story") {
    story = sel;
} else if (sel.constructor.name === "TextFrame") {
    story = sel.parentStory;
} else {
    alert("텍스트 프레임 안의 텍스트를 선택한 후 실행하세요.");
    exit();
}

// --------------------------------------
// 유틸 함수들
// --------------------------------------

// find/change 초기화
function resetFindChange() {
    app.findGrepPreferences  = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;
    app.findTextPreferences  = NothingEnum.nothing;
    app.changeTextPreferences = NothingEnum.nothing;
}

// 단락 스타일 가져오거나 없으면 생성
function getParagraphStyle(doc, name) {
    var s = doc.paragraphStyles.itemByName(name);
    if (!s.isValid) {
        s = doc.paragraphStyles.add({ name: name });
    }
    return s;
}

// --------------------------------------
// 사용할 단락 스타일 미리 준비
// (없는 경우 자동 생성됨)
// --------------------------------------
var ps_passage   = getParagraphStyle(doc, "지문");          // 1. 지문
var ps_qNumber   = getParagraphStyle(doc, "문제 번호");      // 2. 문제 번호
var ps_descNum   = getParagraphStyle(doc, "서술형 번호");    // 3. 서술형 번호
var ps_readIntro = getParagraphStyle(doc, "다음 글을 읽고"); // 4. '다음 글을 읽고' 문장
var ps_choice    = getParagraphStyle(doc, "선지");          // 5. 선지
var ps_vocab     = getParagraphStyle(doc, "영단어");        // 6. 영단어

// --------------------------------------
// 1. 선택된 스토리 전체를 '지문' 단락 스타일로
// --------------------------------------
for (var i = 0; i < story.paragraphs.length; i++) {
    story.paragraphs[i].appliedParagraphStyle = ps_passage;
}

// --------------------------------------
// 2. GREP [가-힣]\?  → 단락 스타일 '문제 번호'
// --------------------------------------
resetFindChange();
app.findGrepPreferences.findWhat = "[가-힣]\\?";    // 예: 가? 나? 다?
var foundQNum = story.findGrep();

for (i = 0; i < foundQNum.length; i++) {
    // 매치가 있는 첫 단락에 스타일 적용
    foundQNum[i].paragraphs[0].appliedParagraphStyle = ps_qNumber;
}

// --------------------------------------
// 3. 텍스트 '시오.' → 단락 스타일 '서술형 번호'
// --------------------------------------
resetFindChange();
app.findTextPreferences.findWhat = "시오.";
var foundDesc = story.findText();

for (i = 0; i < foundDesc.length; i++) {
    foundDesc[i].paragraphs[0].appliedParagraphStyle = ps_descNum;
}

// --------------------------------------
// 4. 텍스트 '다음 글을 읽고 물음에 답하시오'
//    → 단락 스타일 '다음 글을 읽고'
// --------------------------------------
resetFindChange();
app.findTextPreferences.findWhat = "다음 글을 읽고 물음에 답하시오";
var foundIntro = story.findText();

for (i = 0; i < foundIntro.length; i++) {
    foundIntro[i].paragraphs[0].appliedParagraphStyle = ps_readIntro;
}

// --------------------------------------
// 5. GREP [①-⑤] → 단락 스타일 '선지'
//    (선지 번호: ①②③④⑤)
// --------------------------------------
resetFindChange();
app.findGrepPreferences.findWhat = "[①-⑤]";
var foundChoice = story.findGrep();

for (i = 0; i < foundChoice.length; i++) {
    foundChoice[i].paragraphs[0].appliedParagraphStyle = ps_choice;
}

// --------------------------------------
// 6. 텍스트 '*' → 단락 스타일 '영단어'
//    (문단 어딘가에 * 가 들어있는 문단을 영단어 스타일로)
// --------------------------------------
resetFindChange();
app.findTextPreferences.findWhat = "*";
var foundVocab = story.findText();

for (i = 0; i < foundVocab.length; i++) {
    foundVocab[i].paragraphs[0].appliedParagraphStyle = ps_vocab;
}

// 마무리: 검색 환경 초기화
resetFindChange();

alert("단락 스타일 자동 지정(1~6단계)이 완료되었습니다.");
