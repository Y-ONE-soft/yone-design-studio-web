// [ENGINE TEMPLATE] 세로→가로 후처리: 오버셋을 **프레임 안에서** 해소
//
// 가로는 단 폭이 좁아 지문 꼬리가 프레임 밖으로 밀린다. 글자는 남아 있어
// 문자수 검수·내용 대조는 통과하는데 **지면에서는 잘린다**.
//
// ⚠ 페이지를 끼워 넣어 해결하면 안 된다 — 워크북은 "한 지문 = 상단/하단 짝"
//    구조라 중간 삽입이 그 짝을 갈라놓는다(2026-08-25 실측: 66장 삽입 후
//    문장배열 상단이 비고 다음 장 하단이 빈 채로 밀림).
//    docs/워크북_섹션_지면규칙.md 참조.
//
// 그래서 여기서는 **프레임 크기도 페이지 구성도 건드리지 않고**, 그 프레임
// 안에서 담기게 만든다. 눈에 덜 띄는 순서로 단계를 올린다:
//   1) 문단 간격 (spaceBefore/After) — run.jsx 가 이미 하는 것과 같은 수단
//   2) 자간 (tracking)      — 최대 -20
//   3) 행간 (leading)       — 최대 -8%
//   4) 장평 (horizontalScale) — 최대 -4%
// 각 단계마다 해소 여부를 확인해 **필요한 만큼만** 쓴다. 어떤 수단을 어디까지
// 썼는지 프레임별로 로그에 남긴다 — 인쇄 밀도가 달라 보일 수 있으므로
// 조판자가 확인할 수 있어야 한다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "overflowfit_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    var _b = [];
    function W(s) {
        _b.push(String(s));
        logFile.open("w"); logFile.write(_b.join("\n") + "\n"); logFile.close();
    }
    W("오버셋 맞춤 시작 (프레임·페이지 불변)");
    var doc = null, ours = false;
    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8"; sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();
        var target = settings.output_indd || settings.indd_path;
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (String(app.documents[d].fullName) === String(new File(target))) {
                    doc = app.documents[d]; break;
                }
            } catch (e) {}
        }
        if (!doc) { doc = app.open(new File(target), false); ours = true; }
        try { doc.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}

        var pageCountBefore = doc.pages.length;
        var fixed = 0, failed = 0, scanned = 0;

        for (var si = 0; si < doc.stories.length; si++) {
            var st = doc.stories[si];
            var ov = false;
            try { ov = st.overflows; } catch (e1) { continue; }
            if (!ov) continue;
            scanned++;
            var tf = null, pg = "?";
            try { tf = st.textContainers[st.textContainers.length - 1]; } catch (e2) {}
            if (!tf) { failed++; continue; }
            try { pg = tf.parentPage ? tf.parentPage.name : "(붙임)"; } catch (e3) {}
            var ps = st.paragraphs;
            var used = [];

            // 1) 문단 간격
            var s1 = 0;
            while (s1 < 16 && st.overflows) {
                s1++;
                for (var i = 0; i < ps.length; i++) {
                    try {
                        if (ps[i].spaceBefore > 0) ps[i].spaceBefore = Math.max(0, ps[i].spaceBefore - 0.25);
                        if (ps[i].spaceAfter > 0) ps[i].spaceAfter = Math.max(0, ps[i].spaceAfter - 0.25);
                    } catch (e4) {}
                }
            }
            if (s1) used.push("문단간격 -" + (s1 * 0.25) + "pt");

            // 2) 자간
            var tr = 0;
            while (tr > -20 && st.overflows) {
                tr -= 5;
                for (var i2 = 0; i2 < ps.length; i2++) {
                    try { ps[i2].tracking = tr; } catch (e5) {}
                }
            }
            if (tr) used.push("자간 " + tr);

            // 3) 행간 (자동 행간 %를 줄인다 — 숫자 행간은 건드리지 않는다)
            var lead = 0;
            while (lead > -8 && st.overflows) {
                lead -= 2;
                for (var i3 = 0; i3 < ps.length; i3++) {
                    try {
                        var al = ps[i3].autoLeading;
                        if (al && al > 0) ps[i3].autoLeading = al + (-2);
                    } catch (e6) {}
                }
            }
            if (lead) used.push("행간 " + lead + "%");

            // 4) 장평
            var hs = 0;
            while (hs > -4 && st.overflows) {
                hs -= 1;
                for (var i4 = 0; i4 < ps.length; i4++) {
                    try { ps[i4].horizontalScale = 100 + hs; } catch (e7) {}
                }
            }
            if (hs) used.push("장평 " + (100 + hs) + "%");

            var still = true;
            try { still = st.overflows; } catch (e8) {}
            if (still) {
                failed++;
                W("  p" + pg + " : 미해소 — " + (used.join(" / ") || "수단 없음"));
            } else {
                fixed++;
                W("  p" + pg + " : 해소 (" + (used.join(" / ") || "변경 없음") + ")");
            }
        }

        // 페이지 수가 변하지 않았는지 확인 — 이 후처리의 계약이다
        var pageCountAfter = doc.pages.length;
        W("오버셋 스토리 " + scanned + "개 → 해소 " + fixed + " / 미해소 " + failed);
        W("[계약] 페이지 " + pageCountBefore + " → " + pageCountAfter +
          (pageCountBefore === pageCountAfter ? " (불변 OK)" : " ⚠ 변동!"));
        if (fixed > 0) { doc.save(); W("저장 완료"); }
        if (ours) doc.close(SaveOptions.NO);
        W("===== 오버셋 맞춤 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 오버셋 맞춤 완료 =====");
        try { if (doc && ours && doc.isValid) doc.close(SaveOptions.NO); } catch (e9) {}
    }
})();
