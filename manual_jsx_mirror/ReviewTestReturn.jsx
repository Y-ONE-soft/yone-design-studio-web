// InDesign GREP 치환 스크립트: 선택한 스토리에서 탭(\t)을 줄바꿈(\r)으로 치환

if (app.selection.length === 0 || !(app.selection[0] instanceof TextFrame)) {
  alert("⚠️ 먼저 텍스트 프레임을 선택하세요.");
} else {
  var selectedStory = app.selection[0].parentStory;

  app.findGrepPreferences = NothingEnum.nothing;
  app.changeGrepPreferences = NothingEnum.nothing;

  app.findGrepPreferences.findWhat = "\\t";
  app.changeGrepPreferences.changeTo = "\\r";

  var changed = selectedStory.changeGrep();

  app.findGrepPreferences = NothingEnum.nothing;
  app.changeGrepPreferences = NothingEnum.nothing;

  alert("✅ 선택한 스토리에서 탭 → 줄바꿈 치환 완료\n총 " + changed.length + "건 치환됨");
}