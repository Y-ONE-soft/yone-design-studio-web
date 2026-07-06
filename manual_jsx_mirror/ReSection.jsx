#target "InDesign"

var doc = app.activeDocument;

//--------------------------------------------------
// 텍스트 → 섹션 코드 매핑
//--------------------------------------------------
var sectionMap = {
    "어휘선택": "A1",
    "어법선택": "A1",

    "본문O/X": "A2",

    "본문정리": "B1",
    "어법O/X": "B1",

    "내용종합": "B2",

    "문장배열": "C1",
    "빈칸어법": "C1",

    "빈칸어휘": "C2",
    "영작배열": "C2"
};

//--------------------------------------------------
// 마스터페이지 폴더 찾기
//--------------------------------------------------
var masterGroup = doc.characterStyleGroups.itemByName("마스터페이지");

if (!masterGroup || !masterGroup.isValid) {
    alert("'마스터페이지' 문자스타일 폴더를 찾지 못했습니다.");
    exit();
}

//--------------------------------------------------
// 단원 문자스타일 찾기 (폴더 아님, 스타일)
//--------------------------------------------------
var unitStyle = masterGroup.characterStyles.itemByName("단원");

if (!unitStyle || !unitStyle.isValid) {
    alert("마스터페이지 폴더 안에 '단원' 문자스타일이 없습니다.");
    exit();
}

//--------------------------------------------------
// 공백 제거
//--------------------------------------------------
function normalize(str){
    return str.replace(/\s+/g,"");
}

//--------------------------------------------------
// 페이지별 섹션 코드 계산
//--------------------------------------------------
var pageSection = {};
var pages = doc.pages;

for (var p = 0; p < pages.length; p++){

    var page = pages[p];
    var frames = page.textFrames;

    for (var f = 0; f < frames.length; f++){

        var paras = frames[f].paragraphs;

        for (var i = 0; i < paras.length; i++){

            var para = paras[i];
            var chars = para.characters;

            if (chars.length === 0) continue;

            if (chars[0].appliedCharacterStyle != unitStyle) continue;

            var txt = normalize(para.contents);

            for (var key in sectionMap){

                if (txt.indexOf(key) !== -1){
                    pageSection[p] = sectionMap[key];
                    break;
                }

            }

            if (pageSection[p]) break;

        }

        if (pageSection[p]) break;
    }
}

//--------------------------------------------------
// 섹션 생성 (연속 코드 방지)
//--------------------------------------------------
var lastCode = null;

for (var p = 0; p < pages.length; p++){

    if (!pageSection[p]) continue;

    var code = pageSection[p];

    if (code === lastCode) continue;

    var page = pages[p];

    var sec;

    // 이미 이 페이지에서 시작하는 섹션이 있으면 그것을 사용
    if (page.appliedSection && page.appliedSection.pageStart == page) {
        sec = page.appliedSection;
    } else {
        sec = doc.sections.add(page);
    }

    sec.continueNumbering = true;
    sec.sectionPrefix = code;
    sec.marker = code;

    lastCode = code;
}

alert("섹션 지정 완료");