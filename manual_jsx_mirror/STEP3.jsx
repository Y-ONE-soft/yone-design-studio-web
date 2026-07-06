// STEP3.jsx — InDesign ExtendScript

var doc = app.activeDocument;
var story = app.selection[0].parentStory;
var paras = story.paragraphs;

// 🔹 밑줄 위치 저장 + 문자스타일 전체 [없음] 초기화
// appliedParagraphStyle은 로컬 오버라이드를 지우므로,
// 복원은 스크립트 맨 끝(마지막 appliedParagraphStyle 이후)에서 실행
var _ulData = []; // [{pi, key, s, e}]
(function () {
  try {
    var noneChar = doc.characterStyles[0];
    var ps       = story.paragraphs;

    // 문단 시작 절대 인덱스 배열 구성
    var paraStarts = [];
    for (var pi = 0; pi < ps.length; pi++) {
      try { paraStarts.push(ps[pi].characters[0].index); }
      catch(_pi) { paraStarts.push(-1); }
    }

    // textStyleRanges 스냅샷: 밑줄 있는 구간 저장 + 모든 구간 문자스타일 초기화
    var snap = story.textStyleRanges.everyItem().getElements();
    for (var ri = 0; ri < snap.length; ri++) {
      try {
        if (snap[ri].underline === true) {
          var absStart = snap[ri].characters[0].index;
          var absEnd   = snap[ri].characters[snap[ri].characters.length - 1].index;
          // 어느 문단인지 찾기 (역순 탐색)
          for (var pi2 = paraStarts.length - 1; pi2 >= 0; pi2--) {
            if (paraStarts[pi2] >= 0 && paraStarts[pi2] <= absStart) {
              var paraKey = ps[pi2].contents.replace(/[\r\n]+$/, '').substring(0, 100);
              _ulData.push({
                pi: pi2,
                key: paraKey,
                s: absStart - paraStarts[pi2],
                e: absEnd   - paraStarts[pi2]
              });
              break;
            }
          }
        }
        snap[ri].appliedCharacterStyle = noneChar; // 문자스타일 [없음]
      } catch (_r) {}
    }
  } catch (e) {}
})();

// 🔹 BreakUp 로직 내장: 선택한 스토리에서 연속 개행(\r{2,})을 단일 개행(\r)으로 압축
(function () {
  // 기존 GREP 설정 백업
  var _findBackup = app.findGrepPreferences.properties;
  var _changeBackup = app.changeGrepPreferences.properties;

  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;

  // 2개 이상 연속한 문단기호를 1개로 변경
  app.findGrepPreferences.findWhat = "\\r{2,}";
  app.changeGrepPreferences.changeTo = "\\r";

  story.changeGrep();

  // GREP 설정 복구
  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;
  app.findGrepPreferences.properties = _findBackup;
  app.changeGrepPreferences.properties = _changeBackup;
})();

// 개행 정리 후 문단 배열 재획득

paras = story.paragraphs;

// 🔹 [보기] → <보기>, [조건] → <조건> 변환 로직 (기존 로직 건드리지 않음)
(function () {
  var _findBackup2 = app.findGrepPreferences.properties;
  var _changeBackup2 = app.changeGrepPreferences.properties;

  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;

  // [보기] / [ 보기 ] → <보기>
  app.findGrepPreferences.findWhat = "\\[\\s*보기\\s*\\]";
  app.changeGrepPreferences.changeTo = "<보기>";
  story.changeGrep();

  // [조건] / [ 조건 ] → <조건>
  app.findGrepPreferences.findWhat = "\\[\\s*조건\\s*\\]";
  app.changeGrepPreferences.changeTo = "<조건>";
  story.changeGrep();

  // ⦁ → • (bullet + space)
  app.findGrepPreferences.findWhat = "\u2981";
  app.changeGrepPreferences.changeTo = "\u2022 ";
  story.changeGrep();

  // GREP 설정 복구
  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;
  app.findGrepPreferences.properties = _findBackup2;
  app.changeGrepPreferences.properties = _changeBackup2;
})();

// 단락 스타일 유효성 검사 함수
function getStyle(name) {
  // 모든 단락스타일은 반드시 "STEP 03" 폴더(스타일 그룹) 안에서만 찾는다
  return getStyleFromGroup("STEP 03", name);
}

// 단락 스타일 그룹에서 스타일 찾기
function getStyleFromGroup(groupName, name) {
  // 그룹 탐색: 이름 정규화 후 전체 그룹 재귀 검색
  function _normGroupName(s){
    return String(s).replace(/[\u3000\s]+/g, "").replace(/[_\-]/g, "").toLowerCase();
  }
  function _collectGroups(root, out){
    try {
      var subs = root.paragraphStyleGroups.everyItem().getElements();
      for (var i=0;i<subs.length;i++) if (subs[i] && subs[i].isValid) {
        out.push(subs[i]);
        _collectGroups(subs[i], out);
      }
    } catch(_cg){}
  }
  var g = null;
  (function(){
    var target = _normGroupName(groupName);
    // 1) 최상위 그룹들부터
    try {
      var top = doc.paragraphStyleGroups.everyItem().getElements();
      for (var t=0;t<top.length;t++) {
        var gg = top[t];
        if (!gg || !gg.isValid) continue;
        if (_normGroupName(gg.name) === target) { g = gg; return; }
      }
      // 2) 모든 하위 그룹 재귀 탐색
      var all = [];
      for (var t2=0;t2<top.length;t2++) if (top[t2] && top[t2].isValid) _collectGroups(top[t2], all);
      for (var a=0;a<all.length;a++) {
        var gg2 = all[a];
        if (_normGroupName(gg2.name) === target) { g = gg2; return; }
      }
    } catch(_scan){}
  })();
  if (!g || !g.isValid) {
    // 사용 가능한 그룹 이름 안내
    try {
      var names = [];
      var tops = doc.paragraphStyleGroups.everyItem().getElements();
      for (var i=0;i<tops.length;i++) if (tops[i] && tops[i].isValid) {
        names.push(tops[i].name);
        try {
          var subs = tops[i].paragraphStyleGroups.everyItem().getElements();
          for (var j=0;j<subs.length;j++) if (subs[j] && subs[j].isValid) names.push(tops[i].name + "/" + subs[j].name);
        } catch(_sg){}
      }
      alert("단락 스타일 그룹 '" + groupName + "' 을(를) 찾을 수 없습니다.\n사용 가능한 그룹: \n- " + names.join("\n- "));
    } catch(_list) {
      alert("단락 스타일 그룹 '" + groupName + "' 이 존재하지 않습니다.");
    }
    exit();
  }

  // 정규화 함수(공백/언더스코어/하이픈/괄호/전각 공백 제거, 소문자)
  function norm(str){
    return String(str)
      .replace(/[\u3000\s]+/g, "")   // half/full-width spaces
      .replace(/[_\-()\[\]{}]/g, "")
      .toLowerCase();
  }

  // 후보 이름 생성: 원본, S_ 추가/제거
  var candidates = [name];
  if (/^S_/.test(name)) candidates.push(name.replace(/^S_/, ""));
  else candidates.push("S_" + name);

  // 그룹 및 모든 하위 그룹의 스타일을 수집
  function collectStyles(group, bucket){
    try {
      var styles = group.paragraphStyles.everyItem().getElements();
      for (var i=0;i<styles.length;i++) if (styles[i] && styles[i].isValid) bucket.push(styles[i]);
    } catch(_s){}
    try {
      var subs = group.paragraphStyleGroups.everyItem().getElements();
      for (var j=0;j<subs.length;j++) if (subs[j] && subs[j].isValid) collectStyles(subs[j], bucket);
    } catch(_g){}
  }

  // 1) 정확 매칭(최상위 그룹 직속)
  try {
    var exact = g.paragraphStyles.itemByName(name);
    if (exact && exact.isValid) return exact;
  } catch(_ex){}

  // 2) 정규화 매칭(모든 하위 그룹 포함)
  var all = [];
  collectStyles(g, all);
  var map = {};
  for (var k=0;k<all.length;k++) map[norm(all[k].name)] = all[k];
  for (var c=0;c<candidates.length;c++) {
    var key = norm(candidates[c]);
    if (map.hasOwnProperty(key)) return map[key];
  }

  // 3) 실패 시 목록 제공
  try {
    var names = [];
    for (var t=0;t<all.length;t++) if (all[t] && all[t].isValid) names.push(all[t].name);
    alert("단락 스타일 '" + groupName + "/" + name + "' 을(를) 찾을 수 없습니다.\n사용 가능한 이름: \n- " + names.join("\n- "));
  } catch(_list) {
    alert("단락 스타일 '" + groupName + "/" + name + "' 이(가) 존재하지 않습니다.");
  }
  exit();
}

// 필요한 스타일들
var styleNum        = getStyleFromGroup("STEP 03", "S_실전문제 번호 수정 올림포스");
var styleChoices    = getStyleFromGroup("STEP 03", "S_선지 올림포스");
var styleIntro      = getStyleFromGroup("STEP 03", "다음 글을 읽고");
var styleAsterisk   = getStyleFromGroup("STEP 03", "영단어");
var styleBackground = getStyleFromGroup("STEP 03", "배경 올림포스");
var styleDefault    = getStyleFromGroup("STEP 03", "실전 문제 지문 올림포스_");
var styleCond       = getStyleFromGroup("STEP 03", "조건 올림포스");
var styleView       = getStyleFromGroup("STEP 03", "보기 올림포스");

// 0. 전체 단락에 기본 스타일(실전 문제 지문 올림포스_) 선적용
for (var d = 0; d < paras.length; d++) {
  paras[d].appliedParagraphStyle = styleDefault;
}

// 1차 분류
for (var i = 0; i < paras.length; i++) {
  var text = paras[i].contents.replace(/[\r\n]+$/, "");

  // (FIX) '주어진 문장/주어진 글/들어갈 위치' 탐지 → 다음 "비어있지 않은" 문단에 스타일 관계없이 항상 배경 올림포스 적용
  if (/주어진\s*(문장|글)/.test(text) || /들어갈\s*위치/.test(text)) {
    var n = i + 1;
    while (n < paras.length) {
      var t2 = (paras[n].contents || "").replace(/[\r\n]+$/, "");
      var isBlank = /^\s*$/.test(t2);

      if (!isBlank) {
        // 다음 실제 문단은 스타일 관계없이 배경 적용
        paras[n].appliedParagraphStyle = styleBackground;
        break;
      }
      n++;
    }
  }

  // 1) 번호 문단 검출:
  //    a) 한글 + ? (기본 패턴)
  //    b) 것은 + (최대 5글자 아무 문자) + 숫자/[/? — 물음표 누락 + 제어문자 사이 끼는 케이스
  //       예: "것은27[11-3]", "것은\u0004[11-1]", "것은 [11-3]"
  //    c) 숫자[챕터-번호] 마커 (예: "27[11-3]")
  if (/[가-힣]\?/.test(text) || /것은.{0,5}[\d\[?]/.test(text) || /\d+\[\d+-\d+\]/.test(text)) {
    paras[i].appliedParagraphStyle = styleNum;
    continue;
  }

  // 2) ①~⑤ 가 문단 맨 앞(앞 공백·탭 허용)에 있을 때만 선지 적용
  // 지문 본문 중간에 ①②③이 나오는 경우(예: "I use ① analogy")는 제외
  if (/^[\s\u3000\t]*[①②③④⑤][\s\t]/.test(text)) {
    paras[i].appliedParagraphStyle = styleChoices;
    continue;
  }

  // 3) "다음 글을 읽고 물음에 답하시오." 포함
  if (text.indexOf("다음 글을 읽고 물음에 답하시오.") !== -1) {
    paras[i].appliedParagraphStyle = styleIntro;
    continue;
  }

  // 4) "시오" 포함
  if (text.indexOf("시오") !== -1) {
    paras[i].appliedParagraphStyle = styleNum;
    continue;
  }

  // 5) "*" 포함
  if (text.indexOf("*") !== -1) {
    paras[i].appliedParagraphStyle = styleAsterisk;
    continue;
  }

  // 6) (A) + 공백
  if (/\(A\)  /.test(text)) {
    paras[i].appliedParagraphStyle = styleChoices;
    continue;
  }

  // 7) (A) + 탭 문자
  if (/\(A\)\t/.test(text)) {
    paras[i].appliedParagraphStyle = styleChoices;
    continue;
  }
}


// 최종 전처리(동일 문단 내 마커):
// 1) <보기> → 보기 올림포스 (단, S_실전문제 번호 수정 올림포스 스타일 문단은 제외)
for (var k = 0; k < paras.length; k++) {
  var txtV = (paras[k].contents || "").replace(/[\r\n]+$/, "");

  // 문단 시작(공백 허용)에 <보기>가 있을 때만 적용, S_실전문제 번호 수정 올림포스 스타일은 제외
  if (/^[\s\u3000]*<보기>/.test(txtV) && paras[k].appliedParagraphStyle != styleNum) {
    paras[k].appliedParagraphStyle = styleView;
  }
}

// 2) <조건> → 조건 올림포스 (단, S_실전문제 번호 수정 올림포스 제외)
for (var k2 = 0; k2 < paras.length; k2++) {
  var txtC = (paras[k2].contents || "").replace(/[\r\n]+$/, "");
  if (txtC.indexOf("<조건>") !== -1 && paras[k2].appliedParagraphStyle != styleNum) {
    paras[k2].appliedParagraphStyle = styleCond;
  }
}

// 추가 후처리: 조건/보기 문단 바로 아래 연속 기본 단락에 전파
for (var m = 0; m < paras.length - 1; m++) {
  var curTxt = paras[m].contents.replace(/[\r\n]+$/, "");

  // 1) 조건 문단(이미 조건 올림포스 적용된 문단) 이후에만 적용
  if (paras[m].appliedParagraphStyle == styleCond) {
    var n = m + 1;
    while (n < paras.length) {
      var p = paras[n];
      var pTxt = p.contents.replace(/[\r\n]+$/, "");
      var pTrim = pTxt.replace(/^[\s\u3000]+/, "");
      // 글머리표/대시/꺾쇠 시작만 허용 (앞에 공백/전각공백 허용)
      if (p.appliedParagraphStyle != styleDefault) break; // 다른 스타일이 오면 중단
      if (!/^(•|-|<)/.test(pTrim)) break;
      p.appliedParagraphStyle = styleCond; // 조건 올림포스 적용
      n++;
    }
  }

  // 2) 보기 문단(이미 보기 올림포스 적용된 문단) 이후에만 적용
  if (paras[m].appliedParagraphStyle == styleView) {
    var n2 = m + 1;
    while (n2 < paras.length) {
      var p2 = paras[n2];
      var p2Txt = p2.contents.replace(/[\r\n]+$/, "");
      if (p2.appliedParagraphStyle != styleDefault) break; // 다른 스타일이 오면 중단
      // 문장 어디에든 ',' 또는 '/' 포함 시 허용
      if (p2Txt.indexOf("/") === -1 && p2Txt.indexOf(",") === -1) break;
      p2.appliedParagraphStyle = styleView; // 보기 올림포스 적용
      n2++;
    }
  }
}

// 🔹 후처리: S_실전문제 번호 수정 올림포스 스타일 문단에서 "숫자. " 패턴 제거 (문단 맨 앞에만 한정)
(function () {
  var _findBackup3 = app.findGrepPreferences.properties;
  var _changeBackup3 = app.changeGrepPreferences.properties;

  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;

  // 해당 단락스타일에만 한정
  app.findGrepPreferences.appliedParagraphStyle = styleNum;

  // 문단 맨 앞 ^ 에서 숫자 + 마침표 + 공백 이 정확히 있는 경우만
  app.findGrepPreferences.findWhat = "^\\d+\\.\\s";
  app.changeGrepPreferences.changeTo = "";

  story.changeGrep();

  // GREP 설정 복구
  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;
  app.findGrepPreferences.properties = _findBackup3;
  app.changeGrepPreferences.properties = _changeBackup3;
})();

// 🔹 화살표 단독 문단 처리: ⇩ 또는 ↓ 만 단독으로 있는 경우 가운데 정렬 + 다음 단락 배경 적용
(function () {
  for (var i = 0; i < paras.length; i++) {
    var raw = paras[i].contents.replace(/[\r\n]+$/, "");
    var trimmed = raw.replace(/^\s+|\s+$/g, "");

    // 화살표가 단독으로 있는 경우만
    if (trimmed === "⇩" || trimmed === "↓") {

      // 해당 단락만 가운데 정렬
      paras[i].justification = Justification.CENTER_ALIGN;

      // 다음 단락이 존재하면 배경 올림포스 스타일 적용
      if (i + 1 < paras.length) {
        paras[i + 1].appliedParagraphStyle = styleBackground;
      }
    }
  }
})();

// 🔹 배경 올림포스 다음 단락에 ①~⑤가 포함되어 있으면 기본 지문 스타일로 복원
(function () {
  for (var i = 0; i < paras.length - 1; i++) {
    // 현재 단락이 배경 올림포스일 때만 검사
    if (paras[i].appliedParagraphStyle == styleBackground) {
      var nextPara = paras[i + 1];
      var nextText = nextPara.contents.replace(/[\r\n]+$/, "");
      // 다음 단락 안에 ①~⑤ 이 포함되어 있으면 (위치 무관)
      if (/[①②③④⑤]/.test(nextText)) {
        nextPara.appliedParagraphStyle = styleDefault; // 실전 문제 지문 올림포스_
      }
    }
  }
})();

// 🔹 후처리 추가: S_실전문제 번호 수정 올림포스 문단에 "다음 밑줄 친 부분 중" 포함 시
// 그 다음 단락을 실전 문제 지문 올림포스_ 스타일로 변경
(function () {
  for (var i = 0; i < paras.length - 1; i++) {
    if (paras[i].appliedParagraphStyle == styleNum) {
      var curText = paras[i].contents.replace(/[\r\n]+$/, "");
      if (curText.indexOf("다음 밑줄 친 부분 중") !== -1) {
        paras[i + 1].appliedParagraphStyle = styleDefault;
      }
    }
  }
})();

// 🔹 최종 후처리 추가(요청):
// '조건 올림포스' 문단 중 <조건> 마커가 있는 문단 다음에서,
// 다음 문단이 기본(실전 문제 지문 올림포스_)이면
// 연속 기본 스타일 구간이 끝날 때(기본이 아닌 스타일이 나올 때)까지 스캔하여
// "숫자." 또는 "•"로 시작하는 문단을 조건 올림포스로 변경
(function () {
  // 최신 단락 배열 재획득 (앞선 변경 이후에도 안전)
  var ps = story.paragraphs;

  for (var i = 0; i < ps.length - 1; i++) {

    // 1) 현재 문단이 조건 올림포스인지
    if (ps[i].appliedParagraphStyle != styleCond) continue;

    // 2) 현재 문단에 <조건> 마커가 실제로 포함되어 있는지
    var headTxt = (ps[i].contents || "").replace(/[\r\n]+$/, "");
    if (headTxt.indexOf("<조건>") === -1) continue;

    // 3) 바로 다음 문단이 기본 지문 스타일일 때만 실행
    if (ps[i + 1].appliedParagraphStyle != styleDefault) continue;

    // 4) 연속 '기본 지문 스타일' 구간의 끝을 먼저 계산 (변경으로 루프가 끊기지 않게)
    var start = i + 1;
    var end = start;
    while (end < ps.length && ps[end].appliedParagraphStyle == styleDefault) {
      end++;
    }

    // 5) 해당 구간에서 '숫자.' 또는 '•' 로 시작하면 조건 올림포스로 변경
    for (var j = start; j < end; j++) {
      var bodyTxt = (ps[j].contents || "").replace(/[\r\n]+$/, "");
      var trimL = bodyTxt.replace(/^[\s\u3000]+/, "");

      // 숫자 + 마침표 조합 (예: "1. ", "2.")
      var isNumDot = /^[\s\u3000\t]*\d+\.\s*/.test(bodyTxt);

      // 괄호 숫자 목록 (예: "(1) ", "(2)")
      var isParenNum = /^[\s\u3000\t]*\(\d+\)\s*/.test(bodyTxt);

      // 글리프 bullet
      var isBullet = /^[\s\u3000\t]*•/.test(bodyTxt);

      // 동그라미 숫자 글리프 (① ② ③ ...)
      var isCircledNum = /^[\s\u3000\t]*[①②③④⑤⑥⑦⑧⑨⑩]/.test(bodyTxt);

      if (isNumDot || isParenNum || isBullet || isCircledNum) {
        ps[j].appliedParagraphStyle = styleCond;
      }
    }
  }
})();

// 🔹 최종 텍스트 정리: "⇩↵" 또는 "↓↵" 삭제
(function () {
  var _findBackup4 = app.findGrepPreferences.properties;
  var _changeBackup4 = app.changeGrepPreferences.properties;

  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;

  // 화살표 + 개행 삭제 (⇩엔터 / ↓엔터)
  app.findGrepPreferences.findWhat = "[⇩↓]\\r";
  app.changeGrepPreferences.changeTo = "";

  story.changeGrep();

  // GREP 설정 복구
  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;
  app.findGrepPreferences.properties = _findBackup4;
  app.changeGrepPreferences.properties = _changeBackup4;
})();

/* 🔹 최종 후처리: "우리말:" 포함 문단 → 배경 올림포스
   (단락 스타일 관계없이 마지막에 강제 적용) */
(function () {
  var ps = story.paragraphs;

  for (var i = 0; i < ps.length; i++) {
    var txt = (ps[i].contents || "").replace(/[\r\n]+$/, "");

    // "우리말:" 또는 "우리말 :" 등 공백 변형 허용
    if (/우리말[\s\u3000]*:/.test(txt)) {
      ps[i].appliedParagraphStyle = styleBackground;
    }
  }
})();

// 🔹 2열 선지 (탭 or ……글리프) → 3열 표 자동 변환
// ① ②③④⑤ 5줄만 표로 변환. 헤더(A)(B)는 건드리지 않음 (contents 수정 시 \r 유실 문제 방지)
// 공백만 있는 경우는 감지 불가 → 건너뜀
(function () {
  var DOT_RE = /[\u00B7\u2025\u2026\u22EF\.]{2,}/;
  var CIRCLED = ['\u2460','\u2461','\u2462','\u2463','\u2464']; // ①②③④⑤

  function getSepType(txt) {
    if (txt.indexOf('\t') !== -1) return 'tab';
    if (DOT_RE.test(txt)) return 'dot';
    return null;
  }
  function isChoiceLine(txt, n) {
    return txt.indexOf(CIRCLED[n]) !== -1 && getSepType(txt) !== null;
  }

  // 마지막 그룹 하나를 찾아 변환 후 true 반환. 그룹 없으면 false.
  function findAndConvertLast() {
    var ps = story.paragraphs;
    for (var i = ps.length - 1; i >= 4; i--) {
      var txt5 = (ps[i].contents || '').replace(/[\r\n]+$/, '');
      // ⑤로 끝나는 줄인지 확인
      if (txt5.indexOf(CIRCLED[4]) === -1) continue;
      var st = getSepType(txt5);
      if (!st) continue;

      // ①②③④ 확인
      var ok = true;
      for (var j = 0; j < 4; j++) {
        var ct = (ps[i - 4 + j].contents || '').replace(/[\r\n]+$/, '');
        if (!isChoiceLine(ct, j) || getSepType(ct) !== st) { ok = false; break; }
      }
      if (!ok) continue;

      // 그룹 확정: ① = i-4, ⑤ = i
      var choiceStart = i - 4;
      var choiceEnd   = i;

      // dot → 탭 삽입 (높은 인덱스부터)
      if (st === 'dot') {
        for (var k = choiceEnd; k >= choiceStart; k--) {
          try {
            var para = ps[k];
            var lt = (para.contents || '').replace(/[\r\n]+$/, '');
            var m = DOT_RE.exec(lt);
            if (!m) continue;
            var base = para.characters[0].index;
            story.characters[base + m.index + m[0].length].insertionPoints[0].contents = '\t';
            story.characters[base + m.index].insertionPoints[0].contents = '\t';
          } catch (_dk) {}
        }
        ps = story.paragraphs;
      }

      // ①~⑤ 5줄만 표로 변환 (헤더 제외)
      try {
        var sPara = ps[choiceStart];
        var ePara = ps[choiceEnd];
        var s0  = sPara.characters[0].index;
        var eLen = ePara.characters.length;
        // 마지막 \r 제외 (빈 행 방지)
        var e0 = ePara.characters[eLen >= 2 ? eLen - 2 : 0].index;
        var tbl = story.characters.itemByRange(s0, e0).convertToTable('\t', '\r');
        // 열 너비: 12mm / 4mm(……) / 10mm
        if (tbl && tbl.isValid && tbl.columns.length >= 3) {
          tbl.columns[0].width = 34;
          tbl.columns[1].width = 11;
          tbl.columns[2].width = 28;
        }
      } catch (_t) {}

      return true; // 하나 처리 완료
    }
    return false;
  }

  // 그룹이 없을 때까지 반복 (최대 30회 안전장치)
  var limit = 30;
  while (limit-- > 0 && findAndConvertLast()) {}
})();

// 🔹 표(Table) 안 셀 단락스타일 처리 — story.paragraphs가 표 셀을 포함하지 않으므로 별도 처리
(function () {
  var tables = story.tables;
  if (!tables || tables.length === 0) return;
  for (var t = 0; t < tables.length; t++) {
    try {
      var tbl = tables[t];
      for (var r = 0; r < tbl.rows.length; r++) {
        try {
          var row = tbl.rows[r];
          for (var c = 0; c < row.cells.length; c++) {
            try {
              var cellParas = row.cells[c].paragraphs;
              for (var p = 0; p < cellParas.length; p++) {
                try {
                  cellParas[p].appliedParagraphStyle = styleChoices;
                } catch (_cp) {}
              }
            } catch (_c) {}
          }
        } catch (_r) {}
      }
    } catch (_t) {}
  }
})();

// 🔹 빈 단락(페이지 배치용 엔터/프레임 브레이크)을 기본 단락 스타일로 설정
(function () {
  var basicStyle = null;
  var bNames = ["$ID/NormalParagraphStyle", "[기본 단락]", "[Basic Paragraph]"];
  for (var bi = 0; bi < bNames.length; bi++) {
    try {
      var cand = doc.paragraphStyles.itemByName(bNames[bi]);
      if (cand && cand.isValid) { basicStyle = cand; break; }
    } catch (_bs) {}
  }
  if (!basicStyle) basicStyle = doc.paragraphStyles[0];

  var ps = story.paragraphs;
  for (var i = 0; i < ps.length; i++) {
    var txt = (ps[i].contents || "").replace(/[\r\n]+$/, "");
    if (/^\s*$/.test(txt)) {
      ps[i].appliedParagraphStyle = basicStyle;
    }
  }
})();

// 🔹 밑줄 복원 — 모든 appliedParagraphStyle 호출이 끝난 뒤 실행
// underline=true 직접 설정은 현재 단락스타일 위에서 정상 작동함(Test2 결과 확인)
(function () {
  if (!_ulData || _ulData.length === 0) return;
  var ps = story.paragraphs;
  for (var i = 0; i < _ulData.length; i++) {
    try {
      var d = _ulData[i];
      var found = false;
      // 저장된 인덱스 기준으로 ±5 범위 탐색 (화살표 문단 삭제로 인한 인덱스 이동 대응)
      for (var delta = 0; delta <= 5 && !found; delta++) {
        var candidates = (delta === 0) ? [d.pi] : [d.pi - delta, d.pi + delta];
        for (var ci = 0; ci < candidates.length && !found; ci++) {
          var pi = candidates[ci];
          if (pi < 0 || pi >= ps.length) continue;
          try {
            var content = ps[pi].contents.replace(/[\r\n]+$/, '');
            if (content.substring(0, 100) !== d.key) continue;
            var chars = ps[pi].characters;
            if (d.e < chars.length) {
              chars.itemByRange(d.s, d.e).underline = true;
              found = true;
            }
          } catch (_pi) {}
        }
      }
    } catch (_u) {}
  }
})();

// 완료 (alert 제거 — 결과는 MCP로 직접 확인)
