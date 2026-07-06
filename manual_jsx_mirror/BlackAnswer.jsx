// Blackbook_AnswerFormatter.jsx
// Description: Applies Blackbook answer-sheet formatting rules to the SELECTED story only.
// - Compresses multiple returns
// - Applies paragraph styles
// - Inserts frame breaks only before "본문2~본문5" (NOT before 본문1; markers are NOT deleted)
// - Styles TF lines only when (F)/(T) is at the END of the paragraph
// - If a TF paragraph follows an Answer paragraph, restart numbering on the first TF paragraph (start at 1)

(function () {
  if (app.documents.length === 0) { alert("Open a document."); return; }
  if (!app.selection || app.selection.length === 0) {
    alert("Select some text (or a text frame). The script applies ONLY to the selected story.");
    return;
  }

  var doc = app.activeDocument;

  // Resolve selected story
  var sel = app.selection[0], story;
  try {
    story = (sel.hasOwnProperty("parentStory")) ? sel.parentStory : sel.parent.parentStory;
  } catch (e) { alert("Select an object that contains text."); return; }
  if (!story) { alert("Couldn't resolve the story from the selection."); return; }

  // Helpers
  function ensureParaStyle(doc, groupName, styleName) {
    var group = doc.paragraphStyleGroups.itemByName(groupName);
    if (!group.isValid) group = doc.paragraphStyleGroups.add({ name: groupName });
    var style = group.paragraphStyles.itemByName(styleName);
    if (!style.isValid) style = group.paragraphStyles.add({ name: styleName });
    return style;
  }
  function getPrevPara(p) {
    if (!p || !p.isValid) return null;
    try { var prev = p.previousItem(p.constructor); return (prev && prev.isValid) ? prev : null; }
    catch (_) { return null; }
  }
  // Ensure / get a dedicated numbering list for TF paragraphs
  function ensureTfNumberingList(doc) {
    try {
      var lists = doc.numberingLists; // InDesign's NumberingList collection
      // Try to fetch by name; if not there, create
      var nl = lists.itemByName("BB_TF_List");
      if (!nl || !nl.isValid) nl = lists.add({ name: "BB_TF_List" });
      return nl;
    } catch (e) {
      // Fallback: some versions expose 'lists' instead of 'numberingLists'
      try {
        var lists2 = doc.lists;
        var nl2 = lists2.itemByName("BB_TF_List");
        if (!nl2 || !nl2.isValid) nl2 = lists2.add({ name: "BB_TF_List" });
        return nl2;
      } catch (e2) {
        return null; // we'll still try to restart with continue/startAt
      }
    }
  }

var baseStyle    = ensureParaStyle(doc, "정답지", "정답");
var tfStyle      = ensureParaStyle(doc, "정답지", "해설_TF");
var tfdStyle     = ensureParaStyle(doc, "정답지", "해설_TF뜻");
var explainStyle = ensureParaStyle(doc, "정답지", "해설");
var tfList       = ensureTfNumberingList(doc);

  app.doScript(function () {

    // 1) Compress multiple returns
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\r{2,}";
    app.changeGrepPreferences.changeTo = "\r";
    story.changeGrep();

    // 2) Default all paragraphs to '정답'
    var paras = story.paragraphs.everyItem().getElements();
    for (var i = 0; i < paras.length; i++) {
      try { paras[i].appliedParagraphStyle = baseStyle; } catch (e) {}
    }

    // 3) FRAME BREAK only before "본문2~본문5"
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "^\\s*본문(?:[2-5])\\s*$";
    var markerParas = story.findGrep();

    for (var j = 0; j < markerParas.length; j++) {
      var p = markerParas[j].paragraphs[0];
      if (!p || !p.isValid) continue;
      var prevPara = getPrevPara(p);
      if (prevPara) {
        try { prevPara.insertionPoints[-1].contents = SpecialCharacters.FRAME_BREAK; } catch (_) {}
      } else {
        try { p.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK; } catch (_) {}
      }
    }

    // 4) '(F)' or '(T)' at END -> apply 해설_TF
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "\\(\\s*[FT]\\s*\\)\\s*$";
    var tfHitsAtEnd = story.findGrep();
    for (var k = 0; k < tfHitsAtEnd.length; k++) {
      try { tfHitsAtEnd[k].paragraphs[0].appliedParagraphStyle = tfStyle; } catch (e) {}
    }

    // 5) '(T)/(F)' 문단 **다음** 문단에 괄호 내용이 **하나라도** 있으면 → 해설_TF뜻 적용
    //    (예: 문장 일부만 괄호여도 해당 문단 전체를 해설_TF뜻으로 분류)
    //    ※ 번호 매기기(6) 실행 전에 선반영
    try {
      for (var k2 = 0; k2 < tfHitsAtEnd.length; k2++) {
        var tfPara = tfHitsAtEnd[k2].paragraphs[0];
        if (!tfPara || !tfPara.isValid) continue;
        var nextP = null;
        try { nextP = tfPara.nextItem(tfPara.constructor); } catch (_np) { nextP = null; }
        if (!nextP || !nextP.isValid) continue;

        var raw = "";
        try { raw = String(nextP.contents || ""); } catch (_c) { raw = ""; }
        // 보이는 텍스트 기준 검사 (문단말 \r 제거)
        raw = raw.replace(/\r/g, "");

        // 괄호 안 내용이 하나라도 있으면 적용: \(.+?\)
        if (/\(.+?\)/.test(raw)) {
          try { nextP.appliedParagraphStyle = tfdStyle; } catch (_ap) {}
        }
      }
    } catch (_eTFD) {}

// 7) 해설_TF 문단 **다음** 문단에 괄호가 포함되어 있으면 → 정답지/해설 단락스타일로 변경
try {
  var parasAfterTF = story.paragraphs.everyItem().getElements();
  for (var z = 0; z < parasAfterTF.length - 1; z++) {
    var curPara = parasAfterTF[z];
    var nextPara = parasAfterTF[z + 1];
    if (!curPara.isValid || !nextPara.isValid) continue;
    if (curPara.appliedParagraphStyle == tfStyle) {
      // 다음 문단이 이미 해설_TF면 건너뜀
      if (nextPara.appliedParagraphStyle == tfStyle) continue;

      var rawText = "";
      try { rawText = String(nextPara.contents || ""); } catch (e) { rawText = ""; }
      rawText = rawText.replace(/\r/g, "");

      // 괄호가 포함되어 있고, 이미 해설_TF로 지정되지 않은 경우만 해설_TF뜻으로 변경
      if (/\(.+?\)/.test(rawText)) {
        try { nextPara.appliedParagraphStyle = tfdStyle; } catch (_) {}
      }
    }
  }
} catch (_errExplain) {}

    // [마지막 단계] '해설:' 포함 문단 → 정답지/해설 로 변경
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;
    app.findGrepPreferences.findWhat = "해설\\s*:";
    var explainHits = story.findGrep();
    for (var m = 0; m < explainHits.length; m++) {
      try { explainHits[m].paragraphs[0].appliedParagraphStyle = explainStyle; } catch (e) {}
    }

// 6) 모든 '정답' 뒤의 해설_TF 문단은 번호를 1부터 다시 시작
var allParas = story.paragraphs.everyItem().getElements();

var currentList = null;
var tfIndexInBlock = -1; // -1 means we're not inside a TF block yet

for (var n = 0; n < allParas.length; n++) {
  var cur = allParas[n];
  if (!cur || !cur.isValid) continue;

  // ① '정답'을 만나면: 새 리스트 만들고 블록 인덱스 초기화
  if (cur.appliedParagraphStyle == baseStyle) {
    tfIndexInBlock = -1;
    currentList = null;
    try {
      var listName = "TF_block_" + n + "_" + (new Date().getTime());
      try {
        currentList = doc.numberingLists.add({ name: listName });
      } catch (e1) {
        try { currentList = doc.lists.add({ name: listName }); } catch (e2) {}
      }
    } catch (_) {}
    continue;
  }

  // ② 해설_TF: 같은 블록 내에서 번호 이어주기
  if (cur.appliedParagraphStyle == tfStyle && currentList) {
    tfIndexInBlock++;
    try {
      // 번호목록 보정 + 리스트 지정
      cur.bulletsAndNumberingListType = ListType.NUMBERED_LIST;
      try { cur.numberingLevel = 0; } catch (_) {}
      try { cur.appliedNumberingList = currentList; } catch (_) {}

      if (tfIndexInBlock === 0) {
        // 블록의 첫 해설_TF → 1부터 시작
        cur.numberingContinue = false;
        cur.numberingStartAt = 1;
      } else {
        // 이후 해설_TF → 계속 번호
        cur.numberingContinue = true;
        // numberingStartAt는 건드리지 않음 (계속 번호가 자동 증가)
      }
    } catch (_) {}
  }
}

    // Force recomposition to update numbers on screen
    try { story.recompose(); } catch (_) {}

    // Reset GREP prefs
    app.findGrepPreferences = NothingEnum.NOTHING;
    app.changeGrepPreferences = NothingEnum.NOTHING;

  }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.autoUndo, "Blackbook Answer Formatting");

  alert("Done: Applied Blackbook rules to the selected story.");
})();
