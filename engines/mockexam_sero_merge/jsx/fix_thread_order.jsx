// [ENGINE TEMPLATE] 세로결합 후처리: 스레드 순서 ↔ 지면 읽기 순서 정렬
//
// run.jsx 는 rethreadGroup(426행)으로 스토리를 이은 **뒤에**
// moveLastPagesToEnd(433행)와 tailPageRef.move(435행)로 페이지를 옮긴다.
// 연결은 옮기기 전 페이지 순서로 맺혀 있어, 최종 지면 순서와 어긋난 채 남는다.
// (2026-08-29 실측: 13강 권2 — 23년 11월 37번 스토리 흐름이
//  p14왼→p15왼→p15오→p16왼→p16오→p14오. 마지막 덩어리가 p14 오른쪽 칸에 놓여,
//  세로 지면에서 이미 지문이 "changes in the texture" 에서 끊기고 뒷문장이
//  다음 페이지로 넘어갔다. 정본 고1_23년_11월_세로.indd 는 p196왼→p196오→…
//  로 정상이다 — 정본 탓이 아니라 결합이 만든다.)
//
// 이걸 그대로 두면 가로 변환에서 손실로 이어진다. rethread_step3.jsx 가
// 프레임 텍스트를 move(AT_END) 로 합치는데, 앞 프레임이 **문단 중간에서**
// 끝나면 다음 프레임 첫 문단이 그 문단에 그대로 붙는다. 게다가 재스레드
// 순서는 가로 읽기 순서라, 붙는 상대가 원래 이어지던 뒷부분이 아니라
// 엉뚱한 섹션이 된다 (실측: 지문 590자 + 한글 발문이 한 문단으로 엉킴).
//
// 그래서 세로 단계에서 미리 바로잡는다. 스토리의 텍스트 순서는 그대로고,
// 어느 프레임이 어느 대목을 담는지만 읽기 순서에 맞게 바뀐다.
// ⚠ 글자수·프레임수·페이지수가 그대로이고 오버셋이 늘지 않을 때만 저장한다.
#target indesign
(function () {
    // run_jsx 가 이 변수로 실행 경로를 잡는다 — 이름을 바꾸면 실행이 안 된다.
    var settingsPath = "__LOG__";
    var LOG = "__LOG__", SRC = "__SRC__";
    var logFile = new File(LOG);
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(String(s)); logFile.close(); }
    W("스레드 순서 점검 시작");

    var doc = null, ours = false;
    try {
        var fo = new File(SRC);
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (String(app.documents[d].fullName) === String(fo)) { doc = app.documents[d]; }
            } catch (e) {}
        }
        if (!doc) { doc = app.open(fo, false); ours = true; }
        try { doc.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}

        var pagesBefore = doc.pages.length, charsBefore = 0, ovBefore = 0;
        for (var s0 = 0; s0 < doc.stories.length; s0++) {
            charsBefore += doc.stories[s0].characters.length;
            if (doc.stories[s0].overflows) { ovBefore++; }
        }

        // 지면 읽기 순서 랭크 — 좌단→우단, 같은 단이면 위→아래
        var rank = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var pg = doc.pages[p], arr = [];
            for (var i = 0; i < pg.textFrames.length; i++) { arr.push(pg.textFrames[i]); }
            arr.sort(function (a, b) {
                var dx = a.geometricBounds[1] - b.geometricBounds[1];
                return Math.abs(dx) > 2 ? dx : (a.geometricBounds[0] - b.geometricBounds[0]);
            });
            for (var k = 0; k < arr.length; k++) { rank[arr[k].id] = p * 100 + k; }
        }

        var targets = [];
        for (var s = 0; s < doc.stories.length; s++) {
            var st = doc.stories[s], cs;
            try { cs = st.textContainers; } catch (e1) { continue; }
            if (cs.length < 2) { continue; }
            var seq = [], ids = [], pgs = [], ok = true;
            for (var c = 0; c < cs.length; c++) {
                var r = rank[cs[c].id];
                if (r === undefined) { ok = false; break; }   // 오버셋 프레임 등 — 건드리지 않는다
                seq.push(r); ids.push(cs[c].id);
                var pn = "-";
                try { pn = cs[c].parentPage ? cs[c].parentPage.name : "?"; } catch (e2) {}
                pgs.push(pn);
            }
            if (!ok) { continue; }
            var mono = true;
            for (var m = 1; m < seq.length; m++) { if (seq[m] < seq[m - 1]) { mono = false; break; } }
            if (!mono) {
                targets.push({ id: st.id, ids: ids, chars: st.characters.length,
                               ov: st.overflows, pgs: pgs });
            }
        }
        W("스레드 스토리 중 순서 어긋남 " + targets.length + "개");
        if (!targets.length) {
            W("===== 스레드 순서 점검 완료 =====");
            if (ours) { doc.close(SaveOptions.NO); }
            return;
        }

        var failed = 0;
        for (var t = 0; t < targets.length; t++) {
            var T = targets[t], frames = [];
            for (var f = 0; f < T.ids.length; f++) { frames.push(doc.textFrames.itemByID(T.ids[f])); }
            frames.sort(function (a, b) { return rank[a.id] - rank[b.id]; });
            W("  [교정] story=" + T.id + " 흐름=p" + T.pgs.join(" p"));
            try {
                for (var u = 0; u < frames.length; u++) {
                    try { frames[u].nextTextFrame = null; } catch (e3) {}
                }
                for (var u2 = 0; u2 + 1 < frames.length; u2++) {
                    frames[u2].nextTextFrame = frames[u2 + 1];
                }
                var st2 = frames[0].parentStory;
                var bad = (st2.characters.length !== T.chars)
                       || (st2.textContainers.length !== frames.length)
                       || (st2.overflows && !T.ov);
                W("     글자 " + T.chars + "→" + st2.characters.length
                  + " / 프레임 " + st2.textContainers.length + "/" + frames.length
                  + " / 오버셋 " + T.ov + "→" + st2.overflows
                  + (bad ? "  [실패]" : "  [정상]"));
                if (bad) { failed++; }
            } catch (eT) { W("     [오류] " + eT); failed++; }
        }

        var pagesAfter = doc.pages.length, charsAfter = 0, ovAfter = 0;
        for (var s1 = 0; s1 < doc.stories.length; s1++) {
            charsAfter += doc.stories[s1].characters.length;
            if (doc.stories[s1].overflows) { ovAfter++; }
        }
        W("[검수] " + pagesBefore + "p→" + pagesAfter + "p / 글자 " + charsBefore
          + "→" + charsAfter + " / 오버셋 " + ovBefore + "→" + ovAfter);
        if (failed === 0 && pagesAfter === pagesBefore
            && charsAfter === charsBefore && ovAfter <= ovBefore) {
            doc.save();
            W("저장 완료 — " + targets.length + "개 교정");
        } else {
            W("[미저장] 검증 실패 — 변경을 버린다");
            if (ours) { doc.close(SaveOptions.NO); doc = null; }
        }
        W("===== 스레드 순서 점검 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 스레드 순서 점검 완료 =====");
    }
    try { if (ours && doc && doc.isValid) { doc.close(SaveOptions.NO); } } catch (e4) {}
})();
