// [ENGINE TEMPLATE] 워크북 선택 결합 — 짝 스텝 오버플로우 페이지 합치기
//
// 어법선택 섹션은 한 페이지에 상단(어법선택 지문) + 하단(문법 기본 문제)이
// 짝으로 들어간다. 그런데 문항 수가 템플릿 슬롯 수를 넘으면 core/jsx 의
// expandStoryOverflow 가 **스토리별로 따로** 페이지를 붙인다. 상단 스토리는
// 상단 프레임만, 하단 스토리는 하단 프레임만 있는 페이지가 생겨 짝이 깨진다.
//   실측 2026-08-08 (20문항 / 슬롯 18): p154·p155 = 하단만, p156·p157 = 상단만.
//   순서까지 하단이 앞선다.
//
// 고치는 방법: 프레임을 옮기지 않는다(스레드가 끊긴다). 상단만 있는 페이지에
// 하단 프레임을 새로 만들어 **체인 중간에 끼워 넣으면** 뒤 프레임의 내용이
// 앞으로 흘러온다. 꼬리 프레임은 비게 되고 그 페이지는 trim 이 지운다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";

    var logFile = new File(settingsPath.replace(/\.settings\.json$/,
                                                "pair_로그.txt"));
    logFile.encoding = "UTF-8";
    logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("짝 페이지 정리 시작");

    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8";
        sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        var d = app.open(new File(settings.indd_path), false);
        try { d.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}
        // 프레임 bounds 를 페이지 로컬 좌표로 읽는다
        try { d.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e1) {}

        var TOP_MAX = 100;     // 상단 프레임 y1 상한
        var BTM_MIN = 150;     // 하단(발문/문제) 프레임 y1 하한
        var i, j;

        // ── 1) 짝 스토리 찾기 ─────────────────────────────────────────
        // 하단 스토리 = 전 프레임이 하단 영역(y1>BTM_MIN)인 최장 스토리.
        //   이 조건은 문서에서 어법하단 하나뿐이라 유일하게 잡힌다.
        // 상단 스토리 = y1<TOP_MAX 스토리 중 **하단과 페이지를 가장 많이
        //   공유하는** 것. 단순히 "y1<TOP_MAX 최장"으로 고르면 STEP3 실전
        //   스토리(172프레임)가 잡혀 짝 정리가 통째로 헛돈다(2026-08-08 실측).
        function storiesWhere(pred) {
            var out = [];
            for (i = 0; i < d.stories.length; i++) {
                var st = d.stories[i];
                var tc = st.textContainers;
                if (tc.length < 3) continue;
                var hit = 0;
                for (j = 0; j < tc.length; j++) {
                    try { if (pred(tc[j].geometricBounds[0])) hit++; } catch (e2) {}
                }
                if (hit === tc.length) out.push(st);
            }
            return out;
        }
        function pageSet(st) {
            var s = {}, tc = st.textContainers;
            for (var k = 0; k < tc.length; k++) {
                try { s[tc[k].parentPage.documentOffset] = true; } catch (e7) {}
            }
            return s;
        }
        var btmCands = storiesWhere(function (y) { return y > BTM_MIN; });
        var btmStory = null;
        for (i = 0; i < btmCands.length; i++) {
            if (!btmStory ||
                    btmCands[i].textContainers.length >
                    btmStory.textContainers.length) {
                btmStory = btmCands[i];
            }
        }
        var topStory = null;
        if (btmStory) {
            var bset = pageSet(btmStory);
            var topCands = storiesWhere(function (y) { return y < TOP_MAX; });
            var bestOverlap = 0;
            for (i = 0; i < topCands.length; i++) {
                var tset = pageSet(topCands[i]), ov = 0;
                for (var pk in tset) {
                    if (tset.hasOwnProperty(pk) && bset[pk]) ov++;
                }
                if (ov > bestOverlap) { bestOverlap = ov; topStory = topCands[i]; }
            }
            W("짝 후보: 하단 " + btmStory.textContainers.length + "프레임 / "
              + "상단 후보 " + topCands.length + "개 중 페이지공유 "
              + bestOverlap + " 채택");
        }
        if (!topStory || !btmStory) {
            W("상단/하단 스토리를 찾지 못함 — 건너뜀");
            d.close(SaveOptions.NO);
            W("===== 짝 정리 완료 =====");
            return;
        }
        W("상단 프레임 " + topStory.textContainers.length
          + " / 하단 프레임 " + btmStory.textContainers.length);

        function pageNum(tf) {
            try { return tf.parentPage.documentOffset; } catch (e3) { return -1; }
        }
        function pagesOf(st) {
            var out = {}, tc = st.textContainers;
            for (var k = 0; k < tc.length; k++) {
                var p = pageNum(tc[k]);
                if (p >= 0) out[p] = tc[k];
            }
            return out;
        }
        var topPages = pagesOf(topStory);
        var btmPages = pagesOf(btmStory);

        // ── 2) 상단만 있는 페이지 / 하단만 있는 페이지 ────────────────
        var topOnly = [], btmOnly = [];
        for (var p in topPages) {
            if (topPages.hasOwnProperty(p) && !btmPages[p]) topOnly.push(parseInt(p, 10));
        }
        for (var q in btmPages) {
            if (btmPages.hasOwnProperty(q) && !topPages[q]) btmOnly.push(parseInt(q, 10));
        }
        topOnly.sort(function (a, b) { return a - b; });
        btmOnly.sort(function (a, b) { return a - b; });
        W("상단만 있는 페이지: " + topOnly.join(",") + " (" + topOnly.length + ")");
        W("하단만 있는 페이지: " + btmOnly.join(",") + " (" + btmOnly.length + ")");

        if (topOnly.length === 0 || btmOnly.length === 0) {
            W("짝 깨진 페이지 없음 — 변경 없음");
            d.close(SaveOptions.NO);
            W("===== 짝 정리 완료 =====");
            return;
        }

        // ── 3) 같은 side 의 정상 페이지에서 하단/발문 기하를 가져온다 ──
        function refFor(side) {
            for (var r in btmPages) {
                if (!btmPages.hasOwnProperty(r)) continue;
                if (!topPages[r]) continue;
                var pg = btmPages[r].parentPage;
                if (String(pg.side) !== String(side)) continue;
                return pg;
            }
            return null;
        }
        function promptFrameOn(pg) {
            // 발문 = 하단 영역의 짧은 단일 프레임(스레드 아님)
            var tfs = pg.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var gb = tfs[t].geometricBounds;
                    if (gb[0] > BTM_MIN && (gb[2] - gb[0]) < 20
                            && tfs[t].parentStory.textContainers.length === 1) {
                        return tfs[t];
                    }
                } catch (e4) {}
            }
            return null;
        }

        var n = Math.min(topOnly.length, btmOnly.length);
        var made = 0;
        // 삽입 기준점 = **첫 고아 하단 페이지 바로 앞** 프레임.
        // 상단만 있는 페이지보다 앞을 기준으로 잡으면(=체인 맨 뒤) 새 프레임이
        // 꼬리에 붙어 내용이 흘러오지 않는다 (2026-08-08 v9 실측: p156·p157
        // 에 빈 프레임만 생기고 p154·p155 가 그대로 남았다).
        var anchorPage = btmOnly[0];
        var chain = btmStory.textContainers;
        var prev = null;
        for (j = 0; j < chain.length; j++) {
            if (pageNum(chain[j]) < anchorPage) prev = chain[j];
        }
        if (prev === null) {
            W("[경고] 기준 프레임 없음 — 건너뜀");
            d.close(SaveOptions.NO);
            W("===== 짝 정리 완료 =====");
            return;
        }
        for (var m = 0; m < n; m++) {
            var tgtPage = d.pages[topOnly[m]];
            var ref = refFor(tgtPage.side);
            if (!ref) { W("[경고] 같은 side 기준 페이지 없음 — p"
                          + (topOnly[m] + 1) + " 건너뜀"); continue; }
            var refBtm = btmPages[ref.documentOffset];
            var rb = refBtm.geometricBounds;

            // 새 하단 프레임
            var ntf = tgtPage.textFrames.add();
            ntf.geometricBounds = rb;
            try {
                ntf.appliedObjectStyle = refBtm.appliedObjectStyle;
            } catch (e5) {}
            try {
                ntf.textFramePreferences.insetSpacing =
                    refBtm.textFramePreferences.insetSpacing;
            } catch (e6) {}

            // 체인 삽입: 기준 프레임 뒤에 이어 붙인다(순서 보존)
            var after = prev.nextTextFrame;
            prev.nextTextFrame = ntf;
            if (after) { ntf.nextTextFrame = after; }
            prev = ntf;

            // 발문 프레임 복제
            var pf = promptFrameOn(ref);
            if (pf) {
                try {
                    var np = pf.duplicate(tgtPage);
                    np.geometricBounds = pf.geometricBounds;
                } catch (e7) { W("[경고] 발문 복제 실패: " + e7); }
            }
            made++;
            W("  p" + (topOnly[m] + 1) + ": 하단 프레임 생성 + 체인 삽입"
              + (pf ? " + 발문 복제" : ""));
        }

        W("합친 페이지 " + made + "개 — 꼬리 빈 페이지는 trim 이 정리한다");
        if (made > 0) { d.save(); } else { W("변경 없음 — 저장 안 함"); }
        d.close(SaveOptions.NO);
        W("===== 짝 정리 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
    }
})();
