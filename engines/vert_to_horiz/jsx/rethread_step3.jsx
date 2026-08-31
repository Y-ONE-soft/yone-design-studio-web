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
//
// ── 왜 프레임 1:1 키 매칭을 버렸나 (2026-08-31 실측) ────────────────────
// 종전에는 프레임을 `key(tf)`(앞30자+뒤20자+**그 프레임에 보이는 글자수**)로
// 짝지어, 후보가 정확히 1개가 아니면 그 스토리를 통째로 건너뛰었다.
// 13강 권2 에서 **재스레드 10 / 건너뜀 14**. 건너뛴 스토리는 프레임마다
// 독립 스토리로 남아, 세로에서 페이지를 걸친 문단이 가로에서 두 문단으로
// 갈라진다(내용 자체는 보존).
//
// 건너뛴 14건을 덤프해 보니 원인은 "같은 지문이 18~23번 반복돼 키가 충돌"
// 만이 아니었다. 실제 내역은:
//   · 후보 0 (키가 아예 없음) 11건  ← 지배적
//   · 후보 다수 (반복 지문 충돌)   3건
// 후보가 0이 되는 이유는 **가로가 이미 부분적으로 병합돼 있기 때문**이다.
// 세로 6프레임 지문이 가로에서는 2프레임짜리 스토리 3개로 들어가 있고,
// 끊는 지점이 세로와 다르다 — 그래서 프레임 단위 글자수가 어긋나 키가
// 영영 안 맞는다 (실측: 세로 f0 2222자 ↔ 가로 첫 프레임 2249자, 대신
// 가로 스토리 전체는 4823자 = 세로 f0+f1). 프레임 경계는 판면이 정하는
// 것이라 애초에 대응의 기준이 될 수 없었다.
//
// 그래서 대응 단위를 **프레임 → 스토리**로 올렸다:
//   1) 세로 스토리 본문(공백 제거)을 Z 라 하고, 가로 스토리들을 읽기 순서로
//      늘어놓은 뒤 **본문이 Z 를 정확히 이어 만드는 연속 구간(런)**을 찾는다.
//      사이에 낀 다른 스토리(사이드 라벨 "S 실전 문제" 7자 등)는 건너뛴다.
//   2) 그룹은 **세로 지면 순서**로 처리하고 전역 `used` 를 유지한다 —
//      반복 지문의 n 번째 그룹은 남아 있는 앞쪽 런을 가져간다(cursor 우선).
//   3) 배정은 **검증을 통과할 때만** 실행한다:
//        · 이어붙인 본문이 Z 와 **글자 하나까지 일치**할 것
//          (문자수 합 일치는 여기에 포함된다)
//        · 읽기 순서로 정렬했을 때 이웃 프레임의 페이지 간격 ≤ 2 일 것
//          (반복 지문의 **다른 회차**를 집으면 여기서 걸린다 — 본문이 같아
//           내용 비교로는 못 잡는다)
//      어긋나면 그 그룹은 건너뛴다(옛 동작과 같음).
// 결과(13강 권2): 재스레드 10 → 16 / 건너뜀 14 → 8.
// 남은 8건은 **이을 것이 없는 정당한 건너뜀**이다 — 세로에서 2프레임에
// 걸친 지문이 가로에서는 한 프레임에 들어가 있거나(=이미 안 끊김),
// 지문번호가 마더텅 번호로 바뀌어([36] → [18]) 같은 내용이 아니다.
//
// 스토리 런이 안 잡히면 **옛 프레임 키 방식으로 폴백**한다(다른 교재·다른
// 코퍼스에서 종전에 되던 것이 조용히 안 되게 만들지 않기 위해서다).
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "rethread_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("STEP3 재스레드 시작");

    // 이어지는 두 프레임 사이에 허용하는 페이지 간격. 한 스토리는 같은
    // 페이지 좌우 단이나 다음 페이지로 이어진다 — 사이에 빈 슬롯이 한 장
    // 낄 수 있어 2.
    var MAX_PAGE_GAP = 2;
    // 런 중간에 낀 무관한 스토리를 몇 개까지 건너뛰며 이어볼지.
    // 실측으로 끼는 것은 사이드 라벨(7자)·빈 프레임(0~1자) 정도다.
    var MAX_SKIP = 4;

    function norm(s) { return String(s).replace(/[\r\n\s]/g, ""); }

    // 폴백(옛 방식)용 프레임 키
    function key(tf) {
        var c = "";
        try { c = String(tf.contents); } catch (e) { return ""; }
        var z = norm(c), n = 0;
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

        // ── 세로: 스레드된 스토리를 지면 순서로 ────────────────────────
        v = app.open(new File(settings.verti_path), false);
        var groups = [];
        for (var i = 0; i < v.stories.length; i++) {
            var st = v.stories[i];
            if (st.textContainers.length < 2) { continue; }
            var ks = [], vp = 1e9;
            for (var j = 0; j < st.textContainers.length; j++) {
                ks.push(key(st.textContainers[j]));
                var pn = 1e9;
                try { pn = st.textContainers[j].parentPage.documentOffset; } catch (e3) {}
                if (pn < vp) { vp = pn; }
            }
            groups.push({ z: norm(st.contents), chars: st.characters.length,
                          vpage: vp, nc: st.textContainers.length, k: ks });
        }
        v.close(SaveOptions.NO); v = null;
        groups.sort(function (a, b) { return a.vpage - b.vpage; });
        W("세로 스레드 스토리 " + groups.length + "개");

        // ── 가로: 프레임 읽기 순서 + 스토리 목록 ───────────────────────
        h = app.open(new File(settings.output_indd || settings.indd_path), false);
        try { h.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}
        try { h.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e1) {}

        var idx = {}, ord = {}, pageOf = {}, storyOf = {};
        for (var p = 0; p < h.pages.length; p++) {
            var pg = h.pages[p], arr = [];
            for (var j2 = 0; j2 < pg.textFrames.length; j2++) { arr.push(pg.textFrames[j2]); }
            arr.sort(function (a, b) {
                var dx = a.geometricBounds[1] - b.geometricBounds[1];
                return Math.abs(dx) > 2 ? dx : (a.geometricBounds[0] - b.geometricBounds[0]);
            });
            for (var j3 = 0; j3 < arr.length; j3++) {
                var k = key(arr[j3]), id = arr[j3].id;
                if (!idx[k]) { idx[k] = []; }
                idx[k].push(id);
                ord[id] = p * 100 + j3;
                pageOf[id] = p;
                storyOf[id] = arr[j3].parentStory.id;
            }
        }

        var before = 0, storyChars = {}, alreadyThreaded = 0, stories = [];
        for (var s0 = 0; s0 < h.stories.length; s0++) {
            var hs = h.stories[s0], sc = hs.characters.length;
            before += sc;
            storyChars[hs.id] = sc;
            if (hs.textContainers.length > 1) { alreadyThreaded++; }
            var ids = [], mo = 1e9, pmin = 1e9, pmax = -1, onPage = true;
            for (var c0 = 0; c0 < hs.textContainers.length; c0++) {
                var cid = hs.textContainers[c0].id;
                if (ord[cid] === undefined) { onPage = false; break; }
                ids.push(cid);
                if (ord[cid] < mo) { mo = ord[cid]; }
                if (pageOf[cid] < pmin) { pmin = pageOf[cid]; }
                if (pageOf[cid] > pmax) { pmax = pageOf[cid]; }
            }
            // 지면 밖(대지·마스터) 스토리는 대응 대상이 아니다.
            if (!onPage || !ids.length) { continue; }
            ids.sort(function (a, b) { return ord[a] - ord[b]; });
            stories.push({ id: hs.id, z: norm(hs.contents), chars: sc, ids: ids,
                           ord: mo, pmin: pmin, pmax: pmax });
        }
        stories.sort(function (a, b) { return a.ord - b.ord; });

        // ── 배정 1) 스토리 본문 런 ────────────────────────────────────
        // 읽기 순서로 늘어놓은 가로 스토리에서 세로 본문 Z 를 정확히
        // 이어 만드는 구간을 찾는다. 못 찾으면 null.
        function matchRun(G, usedStory, cursor, note) {
            var Z = G.z, i, m;
            if (!Z.length) { note.why = "세로 본문 비어 있음"; return null; }
            // 시작 후보: 본문이 Z 의 머리와 일치하는 스토리. cursor 뒤를 먼저.
            var head = [], tail = [];
            for (i = 0; i < stories.length; i++) {
                var s = stories[i];
                if (usedStory[s.id] || !s.z.length || s.z.length > Z.length) { continue; }
                if (Z.substring(0, s.z.length) !== s.z) { continue; }
                if (s.ord > cursor) { head.push(i); } else { tail.push(i); }
            }
            var starts = head.concat(tail);
            if (!starts.length) { note.why = "시작 스토리 없음"; return null; }
            for (var q = 0; q < starts.length; q++) {
                var k0 = starts[q], pos = stories[k0].z.length, run = [k0];
                var last = stories[k0], skipped = 0, okrun = false;
                for (m = k0 + 1; m < stories.length && skipped <= MAX_SKIP; m++) {
                    if (pos === Z.length) { break; }
                    var t = stories[m];
                    if (usedStory[t.id] || !t.z.length
                        || Z.substring(pos, pos + t.z.length) !== t.z
                        || t.pmin - last.pmax > MAX_PAGE_GAP) {
                        skipped++;
                        continue;
                    }
                    pos += t.z.length; run.push(m); last = t; skipped = 0;
                }
                if (pos !== Z.length) { continue; }
                // 지면 연속성 — 반복 지문의 다른 회차를 집으면 여기서 걸린다.
                var frames = [], r;
                for (r = 0; r < run.length; r++) {
                    for (i = 0; i < stories[run[r]].ids.length; i++) {
                        frames.push(stories[run[r]].ids[i]);
                    }
                }
                frames.sort(function (a, b) { return ord[a] - ord[b]; });
                okrun = true;
                for (i = 1; i < frames.length; i++) {
                    if (pageOf[frames[i]] - pageOf[frames[i - 1]] > MAX_PAGE_GAP) {
                        okrun = false; break;
                    }
                }
                if (!okrun) { continue; }
                note.run = run;
                return frames;
            }
            note.why = "본문이 이어지는 스토리 조합 없음";
            return null;
        }

        // ── 배정 2) 폴백: 옛 프레임 키 1:1 ────────────────────────────
        // 스토리 런이 안 잡히는 문서에서 종전 동작을 유지한다.
        function matchKeys(G, usedFrame, note) {
            var ids = [], f, m, ok = true;
            for (f = 0; f < G.k.length; f++) {
                m = idx[G.k[f]];
                if (!m || m.length !== 1 || usedFrame[m[0]]) { ok = false; break; }
                ids.push(m[0]);
            }
            if (ok) { return ids; }
            // 빈 프레임(내용 1자)은 키가 "##1" 로 같아 후보가 여러 개다.
            // 유일하게 잡힌 프레임들의 **페이지 범위 안**에서, 아직 안 쓴
            // 후보만 남기면 대개 하나로 좁혀진다
            // (2026-08-18: 이 1건 때문에 지문 하나가 매번 안 이어졌다).
            ids = [];
            var uniq = [], lo = 1e9, hi = -1, u;
            for (u = 0; u < G.k.length; u++) {
                var mu = idx[G.k[u]];
                if (mu && mu.length === 1 && !usedFrame[mu[0]]) {
                    uniq.push(mu[0]);
                    var pgu = pageOf[mu[0]];
                    if (pgu < lo) { lo = pgu; }
                    if (pgu > hi) { hi = pgu; }
                }
            }
            if (uniq.length < 2) { note.why = "매핑 불완전"; return null; }
            var taken = {};
            for (u = 0; u < uniq.length; u++) { taken[uniq[u]] = 1; }
            for (f = 0; f < G.k.length; f++) {
                m = idx[G.k[f]];
                if (!m) { note.why = "매핑 불완전"; return null; }
                if (m.length === 1 && !usedFrame[m[0]]) { ids.push(m[0]); continue; }
                var cand = [];
                for (var c5 = 0; c5 < m.length; c5++) {
                    if (!usedFrame[m[c5]] && !taken[m[c5]]
                        && pageOf[m[c5]] >= lo - 1 && pageOf[m[c5]] <= hi + 1) {
                        cand.push(m[c5]);
                    }
                }
                if (cand.length !== 1) { note.why = "매핑 불완전"; return null; }
                ids.push(cand[0]);
                taken[cand[0]] = 1;
            }
            note.why = null;
            note.narrowed = "p" + (lo + 1) + "~p" + (hi + 1);
            return ids;
        }

        // ── 실행 ─────────────────────────────────────────────────────
        var done = 0, skip = 0, already = 0, byRun = 0, byKey = 0;
        var usedFrame = {}, usedStory = {}, cursor = -1;
        for (var g = 0; g < groups.length; g++) {
            var G2 = groups[g], note = {}, via = "런";
            var fids = matchRun(G2, usedStory, cursor, note);
            if (!fids) {
                var note2 = {};
                fids = matchKeys(G2, usedFrame, note2);
                via = "키";
                if (!fids) { note.why = note.why + " / 폴백도 " + note2.why; }
            }
            if (!fids) {
                skip++;
                // 이미 스레드된 문서를 다시 돌리면 세로 스토리 하나가
                // 가로 스토리 하나에 통째로 들어가 있어 런이 1개로 잡힌다.
                // 그때는 아래 [이미완료] 로 빠지지 여기로 오지 않는다.
                W("  [건너뜀] 세로 p" + (G2.vpage + 1) + " " + G2.nc + "프레임 "
                  + G2.chars + "자 — " + (note.why || "매핑 불완전"));
                continue;
            }
            var f2, frames = [], sum = 0, sdone = {};
            for (f2 = 0; f2 < fids.length; f2++) {
                frames.push(h.textFrames.itemByID(fids[f2]));
                var sid = storyOf[fids[f2]];
                if (!sdone[sid]) { sdone[sid] = 1; sum += storyChars[sid]; }
            }
            for (f2 = 0; f2 < fids.length; f2++) { usedFrame[fids[f2]] = 1; }
            for (var sk in sdone) { usedStory[sk] = 1; }
            if (ord[fids[fids.length - 1]] > cursor) {
                cursor = ord[fids[fids.length - 1]];
            }
            if (frames[0].parentStory.textContainers.length === frames.length) {
                already++;
                continue;
            }
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
                var r2 = frames[0].parentStory;
                // 예상 문자수는 프레임이 아니라 **스토리** 문자수 합이다.
                // 프레임 문자수는 오버셋(프레임 밖으로 숨은 꼬리)을 빼고 세므로,
                // 합쳐 놓고 비교하면 멀쩡한 결합도 "불일치" 로 경고됐다
                // (2026-08-29 실측: 12380 → 12419 등 3건이 전부 이 오탐).
                if (r2.characters.length !== sum) {
                    W("  [경고] 문자수 불일치 " + sum + " → " + r2.characters.length);
                }
                if (via === "런" && norm(r2.contents) !== G2.z) {
                    W("  [경고] 이은 본문이 세로와 다르다 (세로 " + G2.z.length
                      + "자 / 가로 " + norm(r2.contents).length + "자)");
                }
                done++;
                if (via === "런") { byRun++; } else { byKey++; }
                W("  [재스레드] 세로 p" + (G2.vpage + 1) + " " + G2.nc + "프레임 "
                  + G2.chars + "자 → 가로 p" + (pageOf[fids[0]] + 1)
                  + "~p" + (pageOf[fids[fids.length - 1]] + 1) + " "
                  + frames.length + "프레임"
                  + (via === "런" ? " (스토리 " + note.run.length + "개 결합)"
                                  : " (키 매핑" + (note2 && note2.narrowed
                                     ? ", 후보를 " + note2.narrowed + " 로 좁힘" : "") + ")"));
            } catch (eT) { W("  [실패] " + eT); }
        }

        var after = 0, ov = 0;
        for (var s1 = 0; s1 < h.stories.length; s1++) {
            after += h.stories[s1].characters.length;
            if (h.stories[s1].overflows) { ov++; }
        }
        W("재스레드 " + done + " / 건너뜀 " + skip
          + (already ? " / 이미완료 " + already : "")
          + " (스토리 런 " + byRun + " · 키 폴백 " + byKey + ")");
        // 이미 재스레드된 문서를 다시 돌리면 세로 스토리가 가로 스토리 하나에
        // 통째로 들어가 있어 [이미완료] 로 빠진다. 하나도 못 붙였는데 건너뜀만
        // 남았다면 대응 문서가 아닐 가능성이 크다 — 오해하지 않도록 적어 둔다.
        if (done === 0 && already === 0 && skip === groups.length && groups.length) {
            W("  (하나도 매핑되지 않았다 — 세로/가로 짝이 맞는 문서인지 확인할 것)");
        }
        W("[검수] 전체 문자 " + before + " → " + after + " (차이 " + (after - before)
          + ") / 오버셋 " + ov);
        if (after !== before) { W("[경고] 문자수가 변했다 — 내용 확인 필요"); }
        if (done > 0) { h.save(); W("저장 완료"); }
        W("===== 재스레드 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 재스레드 완료 =====");
    }
    try { if (v && v.isValid) { v.close(SaveOptions.NO); } } catch (e4) {}
    try { if (h && h.isValid) { h.close(SaveOptions.NO); } } catch (e5) {}
})();
