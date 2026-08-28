// [ENGINE TEMPLATE] 세로→가로 후처리: 간지 라벨 교체
//
// 가로 템플릿의 간지에는 "고2 모의고사" 같은 표기가 박혀 있다. 템플릿이
// 어느 학년/교재로 만들어졌든 그대로 인쇄되므로, 마더텅 워크북에서는
// "마더텅 13강, 17~32번" 처럼 그 권의 실제 범위로 바꿔야 한다
// (2026-08-25 실측: 고1 워크북 4곳에 "고2 모의고사" 인쇄).
//
// settings 의 cover_label 이 있을 때만 동작한다 — 없으면 아무것도 하지
// 않고 끝낸다(기존 동작 보존).
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "coverlabel_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    var _b = [];
    function W(s) {
        _b.push(String(s));
        logFile.open("w"); logFile.write(_b.join("\n") + "\n"); logFile.close();
    }
    W("간지 라벨 교체 시작");
    var doc = null;
    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8"; sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();
        var label = settings.cover_label;
        if (!label) {
            W("cover_label 없음 — 건너뜀");
            W("===== 간지 라벨 완료 =====");
            return;
        }
        var target = settings.output_indd || settings.indd_path;
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (String(app.documents[d].fullName) === String(new File(target))) {
                    doc = app.documents[d]; break;
                }
            } catch (e) {}
        }
        var ours = false;
        if (!doc) { doc = app.open(new File(target), false); ours = true; }

        // "고N 모의고사" 형태를 찾아 교체한다. 학년 숫자는 고정하지 않는다 —
        // 템플릿이 바뀌어도 잡히도록.
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "고\\d+\\s*모의고사";
        var found = doc.findGrep();
        W("찾음 " + found.length + "곳 → \"" + label + "\"");
        for (var i = 0; i < found.length; i++) {
            try {
                var pg = "?";
                try { pg = found[i].parentTextFrames[0].parentPage.name; } catch (e2) {}
                W("  p" + pg + " : \"" + found[i].contents + "\"");
            } catch (e3) {}
        }
        app.changeGrepPreferences.changeTo = label;
        var changed = doc.changeGrep();
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        W("교체 " + changed.length + "곳");
        if (changed.length > 0) { doc.save(); W("저장 완료"); }
        if (ours) doc.close(SaveOptions.NO);
        W("===== 간지 라벨 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 간지 라벨 완료 =====");
    }
})();
