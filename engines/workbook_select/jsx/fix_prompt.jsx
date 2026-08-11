// [ENGINE TEMPLATE] 워크북 선택 결합 — 하단 문제 발문을 문항 유형에 맞춘다
//
// 어법선택 하단의 발문("다음 밑줄 친 부분 중 어법상 틀린 것은?")은 원고가
// 아니라 **InDesign 템플릿의 정적 프레임**이다. 그래서 네모형 문항
// ((A),(B),(C) 중 고르기)에도 밑줄형 발문이 그대로 붙는다.
//   실측 2026-08-08: 마더텅 26(230631)·32(220633) 두 문항이 네모형인데
//   발문은 밑줄형. 오버셋·링크·폰트·중복 검사 전부 통과한다.
//
// 발문 문구는 지어내지 않는다 — **원고에 있는 발문**을 쓴다.
// prompts.json: [{"match": "지문 앞부분", "prompt": "발문 전문"}]
// 하단 문제 프레임 내용이 match 로 시작하는 페이지의 발문 프레임만 바꾼다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";

    var logFile = new File(settingsPath.replace(/\.settings\.json$/,
                                                "prompt_로그.txt"));
    logFile.encoding = "UTF-8";
    logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("발문 교정 시작");

    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8";
        sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        var pf = new File(settingsPath.replace(/\.settings\.json$/,
                                               "prompts.json"));
        if (!pf.exists) {
            W("prompts.json 없음 — 교정 대상 없음");
            W("===== 발문 교정 완료 =====");
            return;
        }
        pf.encoding = "UTF-8";
        pf.open("r");
        var specs = eval("(" + pf.read() + ")");
        pf.close();
        if (!specs || !specs.length) {
            W("교정 대상 0건");
            W("===== 발문 교정 완료 =====");
            return;
        }
        W("교정 대상 " + specs.length + "건");

        var d = app.open(new File(settings.indd_path), false);
        try { d.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e0) {}

        function norm(s) {
            return String(s).replace(/\s+/g, " ")
                            .replace(/[^A-Za-z ]/g, "").toLowerCase();
        }

        var fixed = 0, i, j, k;
        for (i = 0; i < d.pages.length; i++) {
            var pg = d.pages[i];
            var tfs = pg.textFrames;
            var promptTf = null, bodyTxt = "";
            for (j = 0; j < tfs.length; j++) {
                var gb, c;
                try { gb = tfs[j].geometricBounds; } catch (e1) { continue; }
                if (gb[0] < 150) continue;              // 하단 영역만
                try { c = String(tfs[j].contents); } catch (e2) { continue; }
                if ((gb[2] - gb[0]) < 20) {
                    // 짧은 프레임 = 발문
                    if (/어법/.test(c)) promptTf = tfs[j];
                } else if (c.length > bodyTxt.length) {
                    bodyTxt = c;
                }
            }
            if (!promptTf || !bodyTxt) continue;

            var nb = norm(bodyTxt);
            for (k = 0; k < specs.length; k++) {
                var m = norm(specs[k].match);
                if (!m || nb.indexOf(m) !== 0) continue;
                var want = String(specs[k].prompt);
                var cur = String(promptTf.contents);
                if (cur.indexOf(want) >= 0) break;      // 이미 맞음
                // 앵커 아이콘(￼)은 보존하고 글자만 바꾼다
                var keep = "";
                if (cur.length && cur.charCodeAt(0) === 0xFFFC) {
                    keep = cur.charAt(0) + " ";
                }
                promptTf.contents = keep + want;
                fixed++;
                W("  p" + pg.name + ": 발문 교체 → " + want.substring(0, 40));
                break;
            }
        }
        W("발문 교체 " + fixed + "건");
        if (fixed > 0) { d.save(); }
        d.close(SaveOptions.NO);
        W("===== 발문 교정 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
    }
})();
