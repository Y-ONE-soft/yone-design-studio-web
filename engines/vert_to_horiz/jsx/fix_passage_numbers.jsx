// [ENGINE TEMPLATE] 세로→가로 후처리: 독립 지문번호 프레임 교정
//
// 가로 템플릿의 지문번호는 본문과 별개인 작은 텍스트프레임이라, 변환이
// 본문만 옮기면 **템플릿 잔재 번호가 그대로 인쇄된다**
// (2026-08-18 실측: 요청은 21,22,23,24,29~40 인데 빈칸어휘 20~39 /
//  어법O/X 22~41-42 / 빈칸어법 20~39 — 세 섹션 모두 어긋남. 선택하지도 않은
//  "41-42" 까지 찍혔다). 오버셋·링크·폰트 검사는 전부 통과한다.
//
// 정답 순서는 **문서에서 직접** 뽑는다: 실전의 {YYMMQQ} 마커 등장 순서가
// 지문 순서이고, 지문번호는 그 코드의 뒤 2자리(문항번호)다. 요청 목록을
// 밖에서 받지 않으므로 회차·문항이 무엇이든 자동으로 맞는다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "passagenum_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("지문번호 교정 시작");

    var d = null;
    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8"; sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();
        d = app.open(new File(settings.output_indd || settings.indd_path), false);
        try { d.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}
        try { d.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e1) {}

        // 1) 지문 순서 = 실전 {코드} 등장 순서
        var order = [], seen = {};
        for (var p = 0; p < d.pages.length; p++) {
            var pg = d.pages[p];
            for (var j = 0; j < pg.textFrames.length; j++) {
                var c = "";
                try { c = String(pg.textFrames[j].contents); } catch (e2) { continue; }
                var m = c.match(/\{(\d{6})\}/g);
                if (!m) { continue; }
                for (var k = 0; k < m.length; k++) {
                    var code = m[k].replace(/[{}]/g, "");
                    if (!seen[code]) { seen[code] = 1; order.push(code); }
                }
            }
        }
        if (!order.length) {
            W("[경고] 실전 {코드} 마커를 못 찾음 — 교정 생략");
            W("===== 지문번호 교정 완료 =====");
            return;
        }
        // 지문번호는 **마더텅 강이면 마더텅 지문번호**, 아니면 원 문항번호.
        // 사용자 확정(2026-08-25): "마더텅 작업은 어떤 걸로 진행하든 마더텅
        // 지문 번호로 교체해야 한다". settings.sources_list 는 그 강의 코드가
        // **마더텅 번호 순서**로 들어 있으므로 인덱스+1 이 지문번호다.
        // sources_list 가 없으면(일반 모의고사 결합) 종전대로 문항번호를 쓴다.
        var src = settings.sources_list || [];
        function mtNo(code) {
            for (var q = 0; q < src.length; q++) {
                if (String(src[q]) === String(code)) { return q + 1; }
            }
            return -1;
        }
        // 마더텅 강 job 이면 **그 강에 속하지 않는 코드는 제외**한다.
        // 세로중간본에 다른 회차 마커가 섞여 있으면 지문이 하나 더 잡혀
        // 번호가 통째로 한 칸씩 밀린다(실측 2026-08-25: 17개로 잡혀
        // "01,02,03,38,04,…" 로 어긋남 + "번호프레임 16개 ≠ 지문 17개" 경고).
        // 제외한 코드는 조용히 버리지 않고 로그에 남긴다 — 세로중간본에
        // 남의 지문이 섞였다는 신호일 수 있다.
        var want = [], usedMT = 0, dropped = [];
        for (var i = 0; i < order.length; i++) {
            var n = mtNo(order[i]);
            if (n > 0) {
                usedMT++;
                want.push(n < 10 ? "0" + n : String(n));
            } else if (src.length) {
                dropped.push(order[i]);          // 이 강의 코드가 아니다
            } else {
                want.push(String(parseInt(order[i].substring(4), 10)));
            }
        }
        W("번호 체계: " + (usedMT ? "마더텅 지문번호 " + usedMT + "개" : "원 문항번호"));
        if (dropped.length) {
            W("[경고] 이 강에 없는 코드 " + dropped.length + "개 제외: " +
              dropped.join(",") + " — 세로중간본에 다른 회차가 섞였는지 확인할 것");
        }
        W("지문 " + want.length + "개: " + want.join(","));

        // 2) 섹션(러닝 라벨) 별 번호 프레임을 페이지 순서로 모아 교체
        var sec = "", cur = null, secs = [];
        for (var p2 = 0; p2 < d.pages.length; p2++) {
            var pg2 = d.pages[p2], lab = "", num = null;
            for (var j2 = 0; j2 < pg2.textFrames.length; j2++) {
                var tf = pg2.textFrames[j2], c2 = "";
                try { c2 = String(tf.contents); } catch (e3) { continue; }
                var z = c2.replace(/[\r\n\s]/g, "");
                var gb = tf.geometricBounds;
                if (z.length && z.length < 20 && /[가-힣]/.test(z) && gb[0] < 15) { lab = z; }
                if (z.length && z.length <= 8 && /^[\d~\-]+$/.test(z)) { num = tf; }
            }
            if (lab && lab !== sec) { sec = lab; cur = { name: sec, items: [] }; secs.push(cur); }
            if (num && cur) { cur.items.push({ pg: pg2.name, tf: num }); }
        }

        var fixed = 0, secN = 0;
        for (var s = 0; s < secs.length; s++) {
            var it = secs[s].items;
            if (!it.length) { continue; }
            secN++;
            if (it.length !== want.length) {
                W("[경고] " + secs[s].name + ": 번호프레임 " + it.length
                  + "개 ≠ 지문 " + want.length + "개 — 앞에서부터만 교정");
            }
            var n = Math.min(it.length, want.length), before = [];
            for (var t = 0; t < n; t++) {
                var oldV = String(it[t].tf.contents).replace(/[\r\n\s]/g, "");
                before.push(oldV);
                if (oldV !== want[t]) {
                    var ch0 = it[t].tf.characters[0];
                    var cs = ch0.appliedCharacterStyle, fn = ch0.appliedFont;
                    var sz = ch0.pointSize, fc = ch0.fillColor;
                    it[t].tf.contents = want[t];
                    try {
                        var all = it[t].tf.texts[0];
                        all.appliedCharacterStyle = cs;
                        all.appliedFont = fn;
                        all.pointSize = sz;
                        all.fillColor = fc;
                    } catch (e4) {}
                    fixed++;
                }
            }
            W("  " + secs[s].name + ": [" + before.join(",") + "] → ["
              + want.slice(0, n).join(",") + "]");
        }
        W("교정 " + fixed + "곳 / 섹션 " + secN + "개");

        // 3) 자체 검증 — 다시 읽어 기대와 대조
        var allOk = true;
        for (var s2 = 0; s2 < secs.length; s2++) {
            var it2 = secs[s2].items;
            if (!it2.length) { continue; }
            var got = [];
            for (var t2 = 0; t2 < it2.length; t2++) {
                got.push(String(it2[t2].tf.contents).replace(/[\r\n\s]/g, ""));
            }
            var okS = (got.join(",") === want.slice(0, it2.length).join(","));
            if (!okS) { allOk = false; W("[검증] " + secs[s2].name + " FAIL — [" + got.join(",") + "]"); }
            else { W("[검증] " + secs[s2].name + " PASS"); }
        }
        W(allOk ? "[검증] 전체 PASS" : "[검증] 전체 FAIL");
        if (fixed > 0) { d.save(); W("저장 완료"); }
        W("===== 지문번호 교정 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 지문번호 교정 완료 =====");
    }
    try { if (d && d.isValid) { d.close(SaveOptions.NO); } } catch (eC) {}
})();
