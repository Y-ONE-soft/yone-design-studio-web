// [ENGINE TEMPLATE] 세로→가로 후처리: 오버셋 해소
//
// 가로 프레임이 세로 내용을 다 담지 못하면 꼬리가 프레임 밖으로 숨는다.
// 파일 안에는 텍스트가 있으니 문자수 검수도, 내용 대조도 통과하는데
// **지면에는 안 나온다** (2026-08-25 실측, 13강 17~32권:
//   p39  24/31줄  — 주제 문항 선지 ①~⑤ 가 통째로 숨음
//   p186 38/321줄, p195 38/304줄, p202 44/273줄 — 페이지가 거의 백지).
//
// 여기서는 넘친 프레임 뒤에 **페이지를 추가하고 같은 자리에 프레임을 만들어
// 스레드로 잇는다**. 지면은 늘지만 내용은 전부 보인다. 내용이 안 보이는
// 것보다 페이지가 느는 쪽이 낫다는 판단(사용자 지시: 내용 유실은 완료 불가).
//
// 순서 주의: trim_unused(빈 페이지 제거) **뒤**, fix_passage_numbers(지문번호)
// **앞**에 돌린다 — 페이지가 늘어난 뒤에 번호를 매겨야 순서가 맞는다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "overflow_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    var _b = [];
    function W(s) {
        _b.push(String(s));
        logFile.open("w"); logFile.write(_b.join("\n") + "\n"); logFile.close();
    }
    var MAX_PER_FRAME = 6;      // 한 프레임이 만들 수 있는 최대 후속 페이지
    var MAX_TOTAL = 60;         // 문서 전체 추가 페이지 상한 (폭주 방지)
    W("오버셋 해소 시작");
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

        // 오버셋 프레임 수집 — 페이지 추가로 인덱스가 밀리므로 **객체 참조**로
        var targets = [];
        for (var p = 0; p < doc.pages.length; p++) {
            var pg = doc.pages[p], sp = pg.parent;
            for (var i = 0; i < sp.textFrames.length; i++) {
                var tf = sp.textFrames[i];
                if (!tf.parentPage || tf.parentPage.id !== pg.id) continue;
                var ov = false;
                try { ov = tf.overflows; } catch (e1) { continue; }
                // 이미 다음 프레임으로 이어져 있으면 그쪽 끝에서 처리된다
                if (ov) {
                    var hasNext = false;
                    try { hasNext = (tf.nextTextFrame !== null); } catch (e2) {}
                    if (!hasNext) targets.push(tf);
                }
            }
        }
        W("오버셋 프레임 " + targets.length + "개");

        var added = 0;
        for (var t = 0; t < targets.length; t++) {
            var cur = targets[t];
            var startPg = "?";
            try { startPg = cur.parentPage.name; } catch (e3) {}
            var shown0 = 0, all0 = 0;
            try { shown0 = cur.lines.length; all0 = cur.parentStory.lines.length; } catch (e4) {}
            var made = 0;
            while (made < MAX_PER_FRAME && added < MAX_TOTAL) {
                var still = false;
                try { still = cur.overflows; } catch (e5) { break; }
                if (!still) break;
                var basePg = null;
                try { basePg = cur.parentPage; } catch (e6) { break; }
                if (!basePg) break;
                var np;
                try {
                    np = doc.pages.add(LocationOptions.AFTER, basePg);
                    try { np.appliedMaster = basePg.appliedMaster; } catch (e7) {}
                } catch (e8) { W("  [실패] 페이지 추가: " + (e8.message || e8)); break; }
                var gb = cur.geometricBounds;
                var ntf;
                try {
                    ntf = np.textFrames.add({ geometricBounds: [gb[0], gb[1], gb[2], gb[3]] });
                    cur.nextTextFrame = ntf;
                } catch (e9) {
                    W("  [실패] 프레임 연결: " + (e9.message || e9));
                    try { np.remove(); } catch (e10) {}
                    break;
                }
                cur = ntf; made++; added++;
            }
            var rest = "?";
            try { rest = cur.overflows ? "여전히 넘침" : "해소"; } catch (e11) {}
            W("  p" + startPg + " : " + shown0 + "/" + all0 + "줄 → 페이지 " +
              made + "장 추가 → " + rest);
        }
        W("추가한 페이지 " + added + "장 / 총 페이지 " + doc.pages.length);

        // 남은 오버셋 확인 — 침묵 금지
        var left = 0;
        for (var s2 = 0; s2 < doc.stories.length; s2++) {
            try { if (doc.stories[s2].overflows) left++; } catch (e12) {}
        }
        W("[검수] 남은 오버셋 스토리 " + left + "개");
        if (added > 0) { doc.save(); W("저장 완료"); }
        if (ours) doc.close(SaveOptions.NO);
        W("===== 오버셋 해소 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 오버셋 해소 완료 =====");
        try { if (doc && ours && doc.isValid) doc.close(SaveOptions.NO); } catch (e13) {}
    }
})();
