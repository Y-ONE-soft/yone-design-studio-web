// [ENGINE TEMPLATE] 세로→가로 후처리: 겹쳐 남은 빈 프레임 제거
//
// 복제는 세로 프레임과 **짝이 맞은** 가로 프레임만 제거하고, 짝을 못 찾은
// 가로 프레임은 그대로 둔다(run.jsx copyPageContent 주석 참조). 그 결과
// 내용이 든 프레임 **위에 빈 프레임이 겹쳐** 남는다
// (2026-08-25 실측: p29 는 같은 좌표에 빈 프레임과 내용 프레임이 겹침,
//  p46 은 페이지 전체를 덮는 빈 프레임이 상·하단 내용 위에 덮여 있었다).
//
// 여기서는 **겹치는 빈 프레임만** 지운다. 겹치지 않는 빈 프레임은 그 강에
// 그 문항이 없어 비는 정상 슬롯일 수 있으므로 손대지 않고 수만 보고한다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "cleanup_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    var _b = [];
    function W(s) {
        _b.push(String(s));
        logFile.open("w"); logFile.write(_b.join("\n") + "\n"); logFile.close();
    }
    W("겹친 빈 프레임 정리 시작");
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

        function isEmpty(tf) {
            var c = "";
            try { c = String(tf.contents); } catch (e1) { return false; }
            return c.replace(/[\s\r\n￼]/g, "").length === 0;
        }
        function overlaps(a, b) {
            // 면적이 실제로 겹치는가 (경계선만 닿는 건 제외)
            return !(a[2] <= b[0] + 1 || b[2] <= a[0] + 1 ||
                     a[3] <= b[1] + 1 || b[3] <= a[1] + 1);
        }

        var removed = 0, keptEmpty = 0, pagesBefore = doc.pages.length;
        for (var p = 0; p < doc.pages.length; p++) {
            var pg = doc.pages[p], sp = pg.parent, own = [];
            for (var i = 0; i < sp.textFrames.length; i++) {
                var tf = sp.textFrames[i];
                if (!tf.parentPage || tf.parentPage.id !== pg.id) continue;
                var gb = tf.geometricBounds;
                if (gb[0] < 0) continue;                   // 사이드 라벨
                if ((gb[2] - gb[0]) < 60) continue;        // 작은 장식
                own.push(tf);
            }
            // 지울 후보를 먼저 모으고 나중에 제거 (순회 중 삭제 금지)
            var kill = [];
            for (var a = 0; a < own.length; a++) {
                if (!isEmpty(own[a])) continue;
                var ga = own[a].geometricBounds, hit = false;
                for (var b = 0; b < own.length; b++) {
                    if (a === b || isEmpty(own[b])) continue;
                    if (overlaps(ga, own[b].geometricBounds)) { hit = true; break; }
                }
                if (hit) kill.push(own[a]); else keptEmpty++;
            }
            for (var k = kill.length - 1; k >= 0; k--) {
                try {
                    var g = kill[k].geometricBounds;
                    kill[k].remove();
                    removed++;
                    W("  p" + pg.name + " 겹친 빈 프레임 제거 y" +
                      Math.round(g[0]) + "~" + Math.round(g[2]) +
                      " x" + Math.round(g[1]) + "~" + Math.round(g[3]));
                } catch (e2) {
                    W("  p" + pg.name + " [실패] " + (e2.message || e2));
                }
            }
        }
        // 페이지 전체가 백지인 경우 — 본문 프레임이 모두 비었고 다른 개체도
        // 없으면 그 페이지는 인쇄물에 있으면 안 된다. trim_unused 가 지우지
        // 못하고 남긴 것이다(실측 2026-08-25: p171·p182·p211·p223 백지).
        var blankPages = [];
        for (var bp = doc.pages.length - 1; bp >= 0; bp--) {
            var bpg = doc.pages[bp], bsp = bpg.parent;
            var hasContent = false, ownCount = 0;
            for (var bi = 0; bi < bsp.textFrames.length && !hasContent; bi++) {
                var btf = bsp.textFrames[bi];
                if (!btf.parentPage || btf.parentPage.id !== bpg.id) continue;
                ownCount++;
                if (!isEmpty(btf)) hasContent = true;
            }
            if (hasContent || ownCount === 0) continue;
            // 텍스트 외 개체(이미지·도형)가 있으면 백지가 아니다
            var others = 0;
            try {
                for (var bo = 0; bo < bsp.pageItems.length; bo++) {
                    var it = bsp.pageItems[bo];
                    if (!it.parentPage || it.parentPage.id !== bpg.id) continue;
                    if (it.constructor.name !== "TextFrame") others++;
                }
            } catch (eB) {}
            if (others > 0) continue;
            blankPages.push(bpg);
        }
        var blankRemoved = 0;
        for (var bk = 0; bk < blankPages.length; bk++) {
            try {
                var nm = blankPages[bk].name;
                blankPages[bk].remove();
                blankRemoved++;
                W("  백지 페이지 제거: p" + nm);
            } catch (eB2) {
                W("  [실패] 백지 페이지 제거: " + (eB2.message || eB2));
            }
        }
        W("제거 " + removed + "개 / 겹치지 않아 남긴 빈 프레임 " + keptEmpty + "개");
        W("백지 페이지 제거 " + blankRemoved + "개");
        W("[계약] 페이지 " + pagesBefore + " → " + doc.pages.length +
          " (백지 " + blankRemoved + "장 제거분만 줄어야 정상)");
        if (removed > 0 || blankRemoved > 0) { doc.save(); W("저장 완료"); }
        if (ours) doc.close(SaveOptions.NO);
        W("===== 빈 프레임 정리 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 빈 프레임 정리 완료 =====");
        try { if (doc && ours && doc.isValid) doc.close(SaveOptions.NO); } catch (e3) {}
    }
})();
