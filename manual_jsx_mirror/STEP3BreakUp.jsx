// InDesign ExtendScript — 선택한 스토리에서만 ^p^p → ^p (연속 개행 압축)
(function () {
  if (!app.documents.length) { alert("열린 문서가 없습니다."); return; }
  if (!app.selection.length) { alert("텍스트 커서를 스토리 안에 두거나 텍스트 프레임을 선택하세요."); return; }

  // 선택에서 스토리 얻기
  var story = null;
  var s = app.selection[0];
  try { story = s.parentStory; } catch (_) {}
  if (!story) {
    if (s instanceof Story) story = s;
    else if (s instanceof TextFrame) story = s.parentStory;
  }
  if (!story) { alert("선택한 항목에서 스토리를 찾을 수 없습니다."); return; }

  // 기존 GREP 설정 보관
  var f0 = app.findGrepPreferences.properties;
  var c0 = app.changeGrepPreferences.properties;

  // 초기화
  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;

  // 2개 이상 연속한 문단기호를 1개로
  app.findGrepPreferences.findWhat = "\\r{2,}";
  app.changeGrepPreferences.changeTo = "\\r";

  // 선택한 스토리에서만 실행
  var n = story.changeGrep();

  // 복구
  app.findGrepPreferences = NothingEnum.NOTHING;
  app.changeGrepPreferences = NothingEnum.NOTHING;
  app.findGrepPreferences.properties = f0;
  app.changeGrepPreferences.properties = c0;

})();