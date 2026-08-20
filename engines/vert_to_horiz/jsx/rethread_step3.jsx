// [ENGINE TEMPLATE] 세로→가로 후처리: STEP3(실전) 스토리 재스레드
//
// 본 변환은 세로 프레임을 하나씩 `duplicate` 해 가로로 옮긴다. 이때
// **스레드가 끊겨** 프레임마다 독립 스토리가 된다. 결과:
//   - 편집해도 리플로우가 안 된다 (뒤 내용이 안 밀림)
//   - 문항 자동번호가 프레임마다 01 로 재시작 → 한 지문 안에 번호 중복
//     (2026-08-18 실측: 번호 138개 중 9개 중복. 세로 원본은 129개 연속)
//   - 가로 단이 세로보다 좁으면 꼬리가 프레임 밖으로 숨는다(오버셋)
//
// 세로 원본의 스레드 스토리를 기준으로 대응 가로 프레임을 찾아 다시 잇는다.
// ⚠ 잇는 순서는 **가로 지면의 읽기 순서**(좌단→우단, 페이지순)다. 세로 흐름
//   순서로 이으면 자동번호가 05,06,01,02… 로 어긋난다(실측).
// ⚠ 텍스트 이동은 `contents` 대입이 아니라 `move()` — 문단스타일이 보존된다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "rethread_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("STEP3 재스레드 시작");

    function key(tf) {
        var c = "";
        try { c = String(tf.contents); } catch (e) { return ""; }
        var z = c.replace(/[\r\n\s]/g, ""), n = 0;
        try { n = tf.characters.length; } catch (e2) {}
        return z.substring(0, 30) + "#" + z.substring(Math.max(0, z.length - 20)) + "#" + n;
    }

    var v = null, h = null;
    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8"; sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();
        if (!settings.verti_path) {
            W("세로 경로 없음 — 건너뜀");
            W("===== 재스레드 완료 =====");
            return;
        }

        v = app.open(new File(settings.verti_path), false);
        var groups = [];
        for (var i = 0; i < v.stories.length; i++) {
            var st = v.stories[i];
            if (st.textContainers.length < 2) { continue; }
            var ks = [];
            for (var j = 0; j < st.textContainers.length; j++) {
                ks.push(key(st.textContainers[j]));
            }
            groups.push(ks);
        }
        v.close(SaveOptions.NO); v = null;
        W("세로 스레드 스토리 " + groups.length + "개");

        h = app.open(new File(settings.output_indd || settings.indd_path), false);
        try { h.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}
        try { h.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e1) {}
        var before = 0;
        for (var s0 = 0; s0 < h.stories.length; s0++) { before += h.stories[s0].characters.length; }

        var idx = {}, ord = {};
        for (var p = 0; p < h.pages.length; p++) {
            var pg = h.pages[p], arr = [];
            for (var j2 = 0; j2 < pg.textFrames.length; j2++) { arr.push(pg.textFrames[j2]); }
            arr.sort(function (a, b) {
                var dx = a.geometricBounds[1] - b.geometricBounds[1];
                return Math.abs(dx) > 2 ? dx : (a.geometricBounds[0] - b.geometricBounds[0]);
            });
            for (var j3 = 0; j3 < arr.length; j3++) {
                var k = key(arr[j3]);
                if (!idx[k]) { idx[k] = []; }
                idx[k].push(arr[j3].id);
                ord[arr[j3].id] = p * 100 + j3;
            }
        }

        // 이미 스레드된 스토리 수 — 재실행 판정용
        var alreadyThreaded = 0;
        for (var a0 = 0; a0 < h.stories.length; a0++) {
            if (h.stories[a0].textContainers.length > 1) { alreadyThreaded++; }
        }
        var done = 0, skip = 0;
        for (var g = 0; g < groups.length; g++) {
            var ks2 = groups[g], ids = [], ok = true;
            for (var f = 0; f < ks2.length; f++) {
                var m = idx[ks2[f]];
                if (!m || m.length !== 1) { ok = false; break; }
                ids.push(m[0]);
            }
            if (!ok) {
                // 빈 프레임(내용 1자)은 키가 "##1" 로 같아 후보가 여러 개다.
                // 유일하게 잡힌 프레임들의 **페이지 범위 안**에서, 아직 안 쓴
                // 후보만 남기면 대개 하나로 좁혀진다
                // (2026-08-18: 이 1건 때문에 지문 하나가 매번 안 이어졌다).
                ids = [];
                var uniq = [], lo = 1e9, hi = -1;
                for (var u = 0; u < ks2.length; u++) {
                    var mu = idx[ks2[u]];
                    if (mu && mu.length === 1) {
                        uniq.push(mu[0]);
                        var pgu = Math.floor(ord[mu[0]] / 100);
                        if (pgu < lo) { lo = pgu; }
                        if (pgu > hi) { hi = pgu; }
                    }
                }
                if (uniq.length >= 2) {
                    var used = {}, ok2 = true;
                    for (var u2 = 0; u2 < uniq.length; u2++) { used[uniq[u2]] = 1; }
                    for (var f5 = 0; f5 < ks2.length; f5++) {
                        var mm = idx[ks2[f5]];
                        if (!mm) { ok2 = false; break; }
                        if (mm.length === 1) { ids.push(mm[0]); continue; }
                        var cand = [];
                        for (var c5 = 0; c5 < mm.length; c5++) {
                            var pgc = Math.floor(ord[mm[c5]] / 100);
                            if (!used[mm[c5]] && pgc >= lo - 1 && pgc <= hi + 1) {
                                cand.push(mm[c5]);
                            }
                        }
                        if (cand.length !== 1) { ok2 = false; break; }
                        ids.push(cand[0]);
                        used[cand[0]] = 1;
                    }
                    if (ok2) {
                        W("  [보정] 빈 프레임 후보를 페이지 범위(p" + (lo + 1)
                          + "~p" + (hi + 1) + ")로 좁혀 매핑");
                        ok = true;
                    }
                }
                if (!ok) {
                    skip++;
                    // 이미 스레드된 문서를 다시 돌리면 프레임의 contents 가
                    // **스토리 전체**를 반환해 키가 전부 같아진다 → 매핑 실패로
                    // 보이지만 실은 할 일이 없는 것. 재실행 시 오해를 막는다.
                    W("  [건너뜀] " + ks2.length + "프레임 — 매핑 불완전"
                      + (alreadyThreaded >= groups.length
                         ? " (이미 스레드된 문서로 보임)" : ""));
                    continue;
                }
            }
            ids.sort(function (a, b) { return ord[a] - ord[b]; });
            var frames = [];
            for (var f2 = 0; f2 < ids.length; f2++) { frames.push(h.textFrames.itemByID(ids[f2])); }
            if (frames[0].parentStory.textContainers.length === frames.length) { skip++; continue; }
            var sum = 0;
            for (var f3 = 0; f3 < frames.length; f3++) { sum += frames[f3].characters.length; }
            try {
                for (var f4 = 1; f4 < frames.length; f4++) {
                    var ss = frames[f4].parentStory;
                    if (ss.id === frames[0].parentStory.id) { continue; }
                    if (ss.characters.length > 0) {
                        ss.texts[0].move(LocationOptions.AT_END,
                                         frames[0].parentStory.texts[0]);
                    }
                    frames[f4 - 1].nextTextFrame = frames[f4];
                }
                var r = frames[0].parentStory;
                if (r.characters.length !== sum) {
                    W("  [경고] 문자수 불일치 " + sum + " → " + r.characters.length);
                }
                done++;
            } catch (eT) { W("  [실패] " + eT); }
        }

        var after = 0, ov = 0;
        for (var s1 = 0; s1 < h.stories.length; s1++) {
            after += h.stories[s1].characters.length;
            if (h.stories[s1].overflows) { ov++; }
        }
        W("재스레드 " + done + " / 건너뜀 " + skip);
        W("[검수] 전체 문자 " + before + " → " + after + " (차이 " + (after - before)
          + ") / 오버셋 " + ov);
        if (after !== before) { W("[경고] 문자수가 변했다 — 내용 확인 필요"); }
        if (done > 0) { h.save(); W("저장 완료"); }
        W("===== 재스레드 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 재스레드 완료 =====");
    }
    try { if (v && v.isValid) { v.close(SaveOptions.NO); } } catch (e3) {}
    try { if (h && h.isValid) { h.close(SaveOptions.NO); } } catch (e4) {}
})();
