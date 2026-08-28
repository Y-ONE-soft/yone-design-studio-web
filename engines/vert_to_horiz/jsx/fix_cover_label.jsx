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

        // 간지 문구는 **마스터 페이지**에 있다(실측: 마스터 "간지").
        // 일반 페이지만 훑으면 0건이 된다. 마스터와 본문 페이지를 모두 본다.
        // 프레임 전체가 그 문구인 경우는 드물다 — 간지 프레임에는 다른
        // 문단도 함께 들어 있다(실측: 프레임 단위 검사 0건). **문단 단위**로
        // 완전 일치를 본다. 본문 발문은 긴 문장 안에 "고1 모의고사" 가
        // 포함될 뿐이라 문단 전체가 일치하지 않으므로 걸리지 않는다.
        function sweep(frames, where) {
            for (var i = 0; i < frames.length; i++) {
                var tf = frames[i];
                var ps;
                try { ps = tf.paragraphs; } catch (e1) { continue; }
                for (var j = 0; j < ps.length; j++) {
                    var c = "";
                    try { c = String(ps[j].contents); } catch (e2) { continue; }
                    scanned++;
                    if (!RE_ONLY.test(c)) continue;
                    try {
                        // 문단 끝 개행은 보존한다 — 통째로 대입하면 문단이 합쳐진다.
                        var tail = /[\r\n]$/.test(c) ? c.substring(c.length - 1) : "";
                        ps[j].contents = label + tail;
                        changed++;
                        W("  " + where + " : \"" + c.replace(/[\r\n]/g, " ") +
                          "\" → \"" + label + "\"");
                    } catch (e3) {
                        W("  [실패] " + where + " : " + (e3.message || e3));
                    }
                }
            }
        }
        for (var m = 0; m < doc.masterSpreads.length; m++) {
            var ms = doc.masterSpreads[m];
            sweep(ms.textFrames, "마스터[" + ms.name + "]");
        }
        for (var p2 = 0; p2 < doc.pages.length; p2++) {
            var pg2 = doc.pages[p2], sp2 = pg2.parent, own = [];
            for (var k = 0; k < sp2.textFrames.length; k++) {
                var t2 = sp2.textFrames[k];
                if (t2.parentPage && t2.parentPage.id === pg2.id) own.push(t2);
            }
            sweep(own, "p" + pg2.name);
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
