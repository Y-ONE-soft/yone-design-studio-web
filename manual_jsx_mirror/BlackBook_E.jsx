/**
 * BlackExercise.jsx — 블랙북 영어 서술형 단락스타일 일괄 적용
 *
 * 적용 규칙:
 *  - [채점기준] / [채점] / [조건] 등 대괄호 단독 레이블 → 조건
 *  - 그 아래 1. 2. 3. 번호 항목 → 조건
 *  - 답: → 선지
 *  - ①~⑤ 로 시작 → 선지
 *  - (A) (B) (C) 등 → 선지
 *  - ? / 시오. 포함 → 문제
 *  - 나머지 → !박스_지문 (기본)
 *  - 문제마다 프레임 브레이크 (프레임 부족 시 자동 추가)
 */

(function () {
  if (app.documents.length === 0) { alert("문서가 없습니다."); return; }
  var doc = app.activeDocument;
  var sel = app.selection;
  if (!sel || sel.length === 0 || !sel[0].hasOwnProperty("parentStory")) {
    alert("문자 또는 텍스트 프레임을 선택한 후 실행하세요."); return;
  }
  var story = sel[0].parentStory;

  // ── 스타일 확보 ──────────────────────────────────────
  function ensureGroup(name) {
    var g = doc.paragraphStyleGroups.itemByName(name);
    if (!g.isValid) g = doc.paragraphStyleGroups.add({ name: name });
    return g;
  }
  function ensureStyle(groupName, styleName) {
    var g = ensureGroup(groupName);
    var s = g.paragraphStyles.itemByName(styleName);
    if (!s.isValid) s = g.paragraphStyles.add({ name: styleName });
    return s;
  }
  function ensureRootStyle(name) {
    var s = doc.paragraphStyles.itemByName(name);
    if (!s.isValid) s = doc.paragraphStyles.add({ name: name });
    return s;
  }

  var GRP       = "독해";
  var stProblem = ensureStyle(GRP, "문제");
  var stSeonji  = ensureStyle(GRP, "선지");
  var stJogon   = ensureStyle(GRP, "조건");
  var stBase    = ensureRootStyle("!박스_지문");

  app.doScript(function () {

    // 1) 중복 줄바꿈 압축
    app.findGrepPreferences  = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;
    app.findGrepPreferences.findWhat   = "\\r{2,}";
    app.changeGrepPreferences.changeTo = "\\r";
    story.changeGrep();
    app.findGrepPreferences  = NothingEnum.nothing;
    app.changeGrepPreferences = NothingEnum.nothing;

    // 2) 문자스타일·오버라이드 초기화
    var csNone = doc.characterStyles.item(0);
    try { story.texts[0].appliedCharacterStyle = csNone; } catch(e) {}
    try { story.texts[0].clearOverrides(OverrideType.CHARACTER_ONLY); } catch(e) {}

    // 3) 전체 기본화
    story.paragraphs.everyItem().appliedParagraphStyle = stBase;

    // 4) 단락스타일 적용
    var pars    = story.paragraphs;
    var inJogon = false;  // [채점기준] 이후 번호 항목 추적

    for (var i = 0; i < pars.length; i++) {
      var p = pars[i];
      var t = (p.contents || "").toString().replace(/\r/g, "");

      // 문제: ? 로 끝나거나 "시오." 포함
      if (/[?？]["''")\]]?\s*$/.test(t) || /시오\./.test(t)) {
        p.appliedParagraphStyle = stProblem;
        inJogon = false;
        continue;
      }

      // [채점기준] / [채점] / [조건] 등 — 대괄호만 있는 줄
      if (/^\s*\[[^\]]+\]\s*$/.test(t)) {
        p.appliedParagraphStyle = stJogon;
        inJogon = true;
        continue;
      }

      // 조건 구간 내 번호 항목: 1. / 2. / 1) 등
      if (inJogon && /^\s*\d+[\.)\s]/.test(t)) {
        p.appliedParagraphStyle = stJogon;
        continue;
      }

      // 답:
      if (/^\s*답\s*:/.test(t)) {
        p.appliedParagraphStyle = stSeonji;
        inJogon = false;
        continue;
      }

      // ①~⑤ 로 시작
      if (/^\s*[①②③④⑤]/.test(t)) {
        p.appliedParagraphStyle = stSeonji;
        continue;
      }

      // (A) (B) (C) (D) (E) — 대소문자 모두
      if (/^\s*\([A-Ea-e]\)/.test(t)) {
        p.appliedParagraphStyle = stSeonji;
        continue;
      }

      // 조건 구간 종료: 내용 있는 줄이 번호 항목이 아니면 구간 닫기
      if (inJogon && t.trim() !== "") {
        inJogon = false;
      }
    }

    // 5) 문제마다 프레임 브레이크 (두 번째 문제부터)
    pars = story.paragraphs;
    var problemParas = [];
    for (var i = 0; i < pars.length; i++) {
      if (pars[i].appliedParagraphStyle === stProblem) problemParas.push(pars[i]);
    }
    for (var k = problemParas.length - 1; k >= 1; k--) {
      try { problemParas[k].insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch(e) {}
    }

    // 6) 프레임 부족 시 자동 추가 및 스레딩
    var containers = story.textContainers;
    var needed     = problemParas.length - containers.length;
    if (needed > 0) {
      var lastCont  = containers[containers.length - 1];
      var lastPage  = lastCont.parentPage;
      var tmplBounds = [];
      for (var i = 0; i < containers.length; i++) {
        if (containers[i].parentPage === lastPage) {
          var b = containers[i].geometricBounds;
          tmplBounds.push([b[0], b[1], b[2], b[3]]);
        }
      }
      var fpp          = tmplBounds.length || 1;
      var masterPage   = lastPage.appliedMaster;
      var insertAfter  = lastPage;
      var curFrame     = lastCont;
      var added        = 0;
      while (added < needed) {
        var newPage = doc.pages.add(LocationOptions.AFTER, insertAfter);
        if (masterPage) { try { newPage.appliedMaster = masterPage; } catch(e) {} }
        insertAfter = newPage;
        for (var j = 0; j < fpp && added < needed; j++) {
          var newTF = newPage.textFrames.add();
          newTF.geometricBounds = tmplBounds[j] || [0, 0, 100, 80];
          curFrame.nextTextFrame = newTF;
          curFrame = newTF;
          added++;
        }
      }
    }

  }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "블랙북 영어 서술형 스타일 적용");

  alert("완료!");
})();
