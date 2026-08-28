// [ENGINE TEMPLATE] 세로본 수정: 페이지 경계에 걸친 문단을 다음 프레임으로
//
// STEP3(실전) 스토리는 여러 페이지에 걸친다. 그때 **한 문단이 페이지 경계를
// 넘어 걸치면**, 가로 변환이 페이지를 한 장씩 복제할 때 그 문단이 잘린다
// (2026-08-25 실측: 13강 2권차 유실 3건이 걸친 문단 3개와 1:1 일치).
//
// 걸친 문단에 startParagraph = NEXT_FRAME 을 주면 문단이 통째로 다음 프레임
// 에서 시작해 경계에 걸치지 않는다. 내용은 그대로고 위치만 밀린다.
//
// ⚠ 뒤 내용이 밀리므로 마지막 프레임이 넘칠 수 있다. 수정 후 오버셋을 세어
//    보고한다. 늘어난 오버셋이 있으면 조판자가 확인해야 한다.
//
// 토큰: __SRC__ / __OUT__ / __DRY__
#target indesign
(function () {
    var settingsPath = "__OUT__";
    var SRC = "__SRC__", OUT = "__OUT__", DRY = __DRY__;
    var buf = [];
    function W(s) {
        buf.push(String(s));
        var f = new File(OUT); f.encoding = "UTF-8"; f.lineFeed = "Unix";
        f.open("w"); f.write(buf.join("\n") + "\n"); f.close();
    }
    var doc = null, ours = false;
    try {
        var fo = new File(SRC);
        if (!fo.exists) { W("[오류] 파일 없음: " + SRC); W("===== 수정 완료 ====="); return; }
        for (var d = 0; d < app.documents.length; d++) {
            try { if (String(app.documents[d].fullName) === String(fo)) doc = app.documents[d]; } catch (e) {}
        }
        if (!doc) { doc = app.open(fo, false); ours = true; }
        try { doc.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}
        W("문서: " + decodeURI(fo.name) + (DRY ? " (모의 실행)" : ""));

        function countOverset() {
            var n = 0;
            for (var s = 0; s < doc.stories.length; s++) {
                try { if (doc.stories[s].overflows) n++; } catch (e) {}
            }
            return n;
        }
        var ovBefore = countOverset();

        // 걸친 문단 수집 — 프레임 경계만 훑는다(문단 전수 조회는 너무 무겁다)
        var hits = [];
        for (var si = 0; si < doc.stories.length; si++) {
            var st = doc.stories[si];
            var conts;
            try { conts = st.textContainers; } catch (e1) { continue; }
            if (!conts || conts.length < 2) continue;
            for (var c = 0; c + 1 < conts.length; c++) {
                var fa = conts[c], fb = conts[c + 1];
                var pa = null, pb = null;
                try { pa = fa.parentPage; pb = fb.parentPage; } catch (e2) {}
                if (!pa || !pb || pa.id === pb.id) continue;   // 같은 페이지 안이면 무해
                var lastA = "", firstB = "";
                try {
                    var ps1 = fa.paragraphs;
                    if (!ps1.length) continue;
                    lastA = String(ps1[ps1.length - 1].contents);
                    var ps2 = fb.paragraphs;
                    if (!ps2.length) continue;
                    firstB = String(ps2[0].contents);
                } catch (e3) { continue; }
                if (lastA !== firstB) continue;
                if (lastA.replace(/\s/g, "").length < 12) continue;
                hits.push({ para: fb.paragraphs[0], from: pa.name, to: pb.name,
                            txt: lastA.replace(/[\r\n]/g, " ").substring(0, 58) });
            }
        }
        W("페이지 경계에 걸친 문단 " + hits.length + "개");
        var fixed = 0;
        for (var h = 0; h < hits.length; h++) {
            W("  p" + hits[h].from + " → p" + hits[h].to + " | " + hits[h].txt);
            if (DRY) continue;
            try {
                hits[h].para.startParagraph = StartParagraph.NEXT_FRAME;
                fixed++;
            } catch (e4) {
                W("    [실패] " + (e4.message || e4));
            }
        }
        var ovAfter = countOverset();
        W("수정 " + fixed + "개 / 오버셋 " + ovBefore + " → " + ovAfter +
          (ovAfter > ovBefore ? "  ⚠ 늘어남 — 확인 필요" : ""));
        if (!DRY && fixed > 0) { doc.save(); W("저장 완료"); }
        if (ours) doc.close(DRY ? SaveOptions.NO : SaveOptions.YES);
        W("===== 수정 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 수정 완료 =====");
        try { if (doc && ours && doc.isValid) doc.close(SaveOptions.NO); } catch (e5) {}
    }
})();
