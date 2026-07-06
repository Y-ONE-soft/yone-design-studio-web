// STEP3_Test2.jsx
// 핵심 질문:
// 1) appliedParagraphStyle = style 은 로컬 오버라이드(밑줄)를 지우는가?
// 2) 지운다면, 스타일 적용 후 다시 underline = true 하면 유지되는가?
// ※ 실행 후 Cmd+Z로 되돌리기

var doc = app.activeDocument;
var story = app.selection[0].parentStory;

// styleDefault 찾기 (간략화)
var styleDefault = null;
(function() {
  try {
    var norm = function(s){ return String(s).replace(/[\s_\-()\[\]{}]+/g,'').toLowerCase(); };
    var groups = doc.paragraphStyleGroups.everyItem().getElements();
    for (var gi = 0; gi < groups.length && !styleDefault; gi++) {
      if (norm(groups[gi].name).indexOf("step03") === -1 && norm(groups[gi].name).indexOf("step 03") === -1) continue;
      var ss = groups[gi].paragraphStyles.everyItem().getElements();
      for (var si = 0; si < ss.length; si++) {
        if (norm(ss[si].name).indexOf("지문올림포스") !== -1) { styleDefault = ss[si]; break; }
      }
    }
  } catch(e) {}
})();

if (!styleDefault) { alert("실전 문제 지문 올림포스_ 스타일을 찾을 수 없습니다."); exit(); }

// 밑줄 있는 첫 번째 문자 찾기
var testChar = null;
var testParaIdx = -1;
var testCharIdx = -1;
(function() {
  var ps = story.paragraphs;
  for (var pi = 0; pi < ps.length && !testChar; pi++) {
    var chars = ps[pi].characters;
    for (var ci = 0; ci < chars.length; ci++) {
      try { if (chars[ci].underline === true) { testChar = chars[ci]; testParaIdx = pi; testCharIdx = ci; break; } } catch(e) {}
    }
  }
})();

if (!testChar) { alert("밑줄 있는 문자를 찾을 수 없습니다.\n텍스트 프레임에 밑줄 텍스트가 있는지 확인하세요."); exit(); }

var log = [];
var para = story.paragraphs[testParaIdx];

log.push("테스트 대상: " + testParaIdx + "번 문단 / " + testCharIdx + "번 문자 '" + testChar.contents + "'");
log.push("───────────────────────────────");
log.push("[A] 시작: underline = " + testChar.underline);

// Step 1: styleDefault 적용
para.appliedParagraphStyle = styleDefault;
log.push("[B] styleDefault 적용 후: underline = " + testChar.underline);

// Step 2: 로컬 오버라이드로 underline = true 설정
testChar.underline = true;
log.push("[C] underline=true 직접 설정 후: underline = " + testChar.underline);

// Step 3: 같은 styleDefault 다시 적용 (동일 스타일 재적용)
para.appliedParagraphStyle = styleDefault;
log.push("[D] styleDefault 재적용(동일 스타일) 후: underline = " + testChar.underline);

// Step 4: 다시 underline = true
testChar.underline = true;
log.push("[E] 다시 underline=true 설정 후: underline = " + testChar.underline);

// Step 5: 다른 스타일 적용 후 동일 스타일 복귀
var styleNum = null;
(function() {
  try {
    var norm = function(s){ return String(s).replace(/[\s_\-()\[\]{}]+/g,'').toLowerCase(); };
    var groups = doc.paragraphStyleGroups.everyItem().getElements();
    for (var gi = 0; gi < groups.length && !styleNum; gi++) {
      if (norm(groups[gi].name).indexOf("step03") === -1 && norm(groups[gi].name).indexOf("step 03") === -1) continue;
      var ss = groups[gi].paragraphStyles.everyItem().getElements();
      for (var si = 0; si < ss.length; si++) {
        if (norm(ss[si].name).indexOf("번호") !== -1 || norm(ss[si].name).indexOf("s실전문제") !== -1) { styleNum = ss[si]; break; }
      }
    }
  } catch(e) {}
})();

if (styleNum) {
  para.appliedParagraphStyle = styleNum;
  log.push("[F] 다른스타일(번호) 적용 후: underline = " + testChar.underline);
  para.appliedParagraphStyle = styleDefault;
  log.push("[G] styleDefault 재적용(다른스타일→지문) 후: underline = " + testChar.underline);
} else {
  log.push("[F-G] 번호 스타일 없음, 스킵");
}

log.push("───────────────────────────────");
log.push("결론:");
var bVal = log[3].indexOf("true") !== -1;
var cVal = log[4].indexOf("true") !== -1;
var dVal = log[5].indexOf("true") !== -1;
if (!bVal) log.push("→ appliedParagraphStyle가 로컬 오버라이드를 지움 (B=false)");
else       log.push("→ appliedParagraphStyle는 로컬 오버라이드를 지우지 않음 (B=true)");
if (cVal)  log.push("→ 직접 설정한 underline=true는 정상 작동");
if (!dVal) log.push("→ 동일 스타일 재적용도 오버라이드를 지움 (D=false)");
else       log.push("→ 동일 스타일 재적용은 오버라이드 유지 (D=true)");

alert(log.join("\n"));
