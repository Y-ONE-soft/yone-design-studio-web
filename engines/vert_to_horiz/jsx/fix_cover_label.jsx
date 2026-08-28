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

        // ⚠ 문서 전체 findGrep 으로 "고N 모의고사" 를 바꾸면 **본문 발문까지**
        //    바뀐다. 실측(2026-08-25): 실전 문항 발문
        //    "[2017 9월 고1 모의고사 36번]" 이 "[2017 9월 마더텅 13강, … 36번]"
        //    으로 훼손됐다. 간지는 프레임 내용이 그 문구 **뿐**이므로,
        //    프레임 단위로 완전 일치할 때만 바꾼다.
        var RE_ONLY = /^\s*고\s*\d+\s*모의고사\s*$/;
        var changed = 0, scanned = 0;
        for (var p2 = 0; p2 < doc.pages.length; p2++) {
            var pg2 = doc.pages[p2], sp2 = pg2.parent;
            for (var i = 0; i < sp2.textFrames.length; i++) {
                var tf = sp2.textFrames[i];
                if (!tf.parentPage || tf.parentPage.id !== pg2.id) continue;
                var c = "";
                try { c = String(tf.contents); } catch (e2) { continue; }
                scanned++;
                if (!RE_ONLY.test(c)) continue;
                try {
                    // contents 대입은 서식을 유지한다(문단·문자 스타일 보존).
                    tf.contents = label;
                    changed++;
                    W("  p" + pg2.name + " : \"" + c.replace(/[\r\n]/g, " ") +
                      "\" → \"" + label + "\"");
                } catch (e3) {
                    W("  [실패] p" + pg2.name + " : " + (e3.message || e3));
                }
            }
        }
        W("프레임 " + scanned + "개 검사 / 교체 " + changed + "곳");
        if (changed > 0) { doc.save(); W("저장 완료"); }
        if (ours) doc.close(SaveOptions.NO);
        W("===== 간지 라벨 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 간지 라벨 완료 =====");
    }
})();
