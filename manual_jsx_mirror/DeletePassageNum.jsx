// DeletePassageNum.jsx — [1] [2] [3] 등 지문 번호 단락 삭제
#target "InDesign"

(function () {
    var doc = app.activeDocument;
    var count = 0;
    var stories = doc.stories;

    for (var si = 0; si < stories.length; si++) {
        try {
            var s = stories[si];
            if (!s || !s.isValid) continue;
            try { if (!s.textContainers || s.textContainers.length === 0) continue; } catch (e) { continue; }

            var fb = app.findGrepPreferences.properties;
            var cb = app.changeGrepPreferences.properties;

            app.findGrepPreferences  = NothingEnum.NOTHING;
            app.changeGrepPreferences = NothingEnum.NOTHING;

            // [숫자] 단독 단락 (뒤 공백 허용, 단락기호 포함 삭제)
            app.findGrepPreferences.findWhat   = "^\\[\\d+\\][ \\t]*\\r";
            app.changeGrepPreferences.changeTo = "";

            var found = s.findGrep();
            count += found ? found.length : 0;
            s.changeGrep();

            app.findGrepPreferences  = NothingEnum.NOTHING;
            app.changeGrepPreferences = NothingEnum.NOTHING;
            try { app.findGrepPreferences.properties  = fb; } catch (e) {}
            try { app.changeGrepPreferences.properties = cb; } catch (e) {}
        } catch (e) {}
    }

    alert("[N] 단락 " + count + "개 삭제 완료");
})();
