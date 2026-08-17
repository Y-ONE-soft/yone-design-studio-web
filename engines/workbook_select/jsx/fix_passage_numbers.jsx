// [ENGINE TEMPLATE] 지문번호 프레임 보정 — 템플릿에 없는 지문의 번호를 만들어 붙인다
//
// 왜 필요한가 (실측 2026-08-17, 마더텅 11강 20문항):
//   템플릿에는 섹션당 지문번호 프레임이 **17개**뿐인데 문항은 20개다. 조판이
//   오버플로우 페이지를 붙여 지문 3개가 더 생기면 그 페이지엔 번호 프레임이
//   없고, 마지막 프레임에는 템플릿 잔재 "41-42"(장문 문항 범위)가 그대로
//   인쇄된다. workbook_v2 의 passage_numbers op 은 **있는 프레임만 갱신**하므로
//   (로그 "지문번호 프레임 갱신: 17개") 이 구멍을 못 메운다.
//
//   실측 결함: 빈칸어휘 p123 / 어법OX p165 / 빈칸어법 p185 에 "41-42",
//              그 뒤 각 2페이지는 번호 자체가 없음 → 섹션당 3지문 무번호.
//   오버셋·링크·폰트·프리플라이트가 전부 통과한다 — 렌더로만 잡힌다.
//
// 방법: 같은 섹션 · **같은 페이지 쪽(파리티)** 의 기존 번호 프레임을 복제해
//   대상 페이지로 옮기고 번호만 바꾼다. 기하·단락스타일·문자서식을 그대로
//   승계하므로 좌표를 하드코딩하지 않는다(좌/우 페이지는 x 가 다르다:
//   실측 빈칸어휘 LEFT x1=9.6 / RIGHT x1=12.8).
//   ⚠ 반대 파리티로 duplicate 하면 스프레드 좌표계 때문에 프레임이 페이지
//     밖으로 밀린다 — 반드시 같은 쪽에서 복제하고 bounds 를 다시 지정한다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";

    var logFile = new File(settingsPath.replace(/\.settings\.json$/,
                                                "passagenum_로그.txt"));
    logFile.encoding = "UTF-8";
    logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("지문번호 보정 시작");

    var doc = null;
    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8"; sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        var pf = new File(settings.plan_path);
        pf.encoding = "UTF-8"; pf.open("r");
        var plan = eval("(" + pf.read() + ")");
        pf.close();

        var pn = plan.passage_numbers;
        if (!pn || !pn.labels || !pn.labels.length) {
            W("plan 에 passage_numbers 없음 — 건너뜀");
            W("===== 지문번호 보정 완료 =====");
            return;
        }
        var labels = pn.labels;
        W("라벨 " + labels.length + "개: " + labels.join(","));

        // ☠ activeDocument / "문서 하나뿐이면 그것" 폴백 금지 — 남의 문서를
        //    대상 삼는 사고 패턴. 경로로 연다(이미 열려 있으면 그 참조 반환).
        doc = app.open(new File(settings.indd_path), false);
        try { doc.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}
        try { doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e1) {}

        // ── 러닝 라벨로 섹션 판별 (한쪽 페이지에만 있어 forward-fill) ──
        function sectionOf(pg) {
            var tfs = pg.textFrames, s = "";
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var gb = tfs[t].geometricBounds;
                    if (gb[0] > 10) { continue; }
                    var c = String(tfs[t].contents).replace(/[\r\n]/g, " ");
                    if (c.length < 30 && c.replace(/\s/g, "").length > 0) {
                        s = c.replace(/^\s+|\s+$/g, "");
                    }
                } catch (e) {}
            }
            return s;
        }
        function sectionKey(s) {
            var t = String(s).replace(/\s/g, "");
            if (t.indexOf("빈칸어휘") >= 0) { return "step1_c2"; }
            if (t.indexOf("빈칸어법") >= 0) { return "step2_c1"; }
            if (t.indexOf("어법O") >= 0) { return "step2_b1"; }
            return "";
        }
        // 번호 프레임 = 좌측 여백의 짧은 숫자 전용 프레임
        function numFrameOn(pg) {
            var tfs = pg.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var gb = tfs[t].geometricBounds;
                    if (gb[1] > 40) { continue; }
                    var cc = String(tfs[t].contents).replace(/[\r\n\s]/g, "");
                    if (cc.length && cc.length <= 7 && /^[\d~\-]+$/.test(cc)) {
                        return tfs[t];
                    }
                } catch (e) {}
            }
            return null;
        }
        function bodyLen(pg) {
            var tfs = pg.textFrames, n = 0;
            for (var t = 0; t < tfs.length; t++) {
                try {
                    var c = String(tfs[t].contents);
                    if (c.length > n) { n = c.length; }
                } catch (e) {}
            }
            return n;
        }

        // ── 섹션별 페이지 수집 (러닝 라벨 forward-fill) ──
        var bySec = {}, order = [], last = "";
        for (var i = 0; i < doc.pages.length; i++) {
            var pg = doc.pages[i];
            var s = sectionOf(pg);
            if (s.replace(/\s/g, "") !== "") { last = s; }
            var key = sectionKey(last);
            if (!key) { continue; }
            if (!bySec[key]) { bySec[key] = []; order.push(key); }
            bySec[key].push(pg);
        }

        var MIN_BODY = 300;      // 내용이 있는 지문 페이지 판정
        var made = 0, fixed = 0, k2;
        for (var oi = 0; oi < order.length; oi++) {
            var key = order[oi];
            var pages = bySec[key];
            // 내용 있는 페이지만 = 지문 1개당 1페이지
            var content = [];
            for (k2 = 0; k2 < pages.length; k2++) {
                if (bodyLen(pages[k2]) >= MIN_BODY) { content.push(pages[k2]); }
            }
            W("[" + key + "] 섹션 페이지 " + pages.length
              + " / 내용 페이지 " + content.length + " / 라벨 " + labels.length);
            if (content.length < labels.length) {
                W("  [경고] 내용 페이지가 라벨보다 적다 — 앞에서부터만 처리");
            }
            var n = Math.min(content.length, labels.length);

            // 같은 쪽(파리티) 도너 확보
            var donor = {};
            for (k2 = 0; k2 < n; k2++) {
                var f0 = numFrameOn(content[k2]);
                if (!f0) { continue; }
                var sd = String(content[k2].side);
                if (!donor[sd]) { donor[sd] = f0; }
            }

            for (k2 = 0; k2 < n; k2++) {
                var page = content[k2];
                var want = String(labels[k2]);
                var tf = numFrameOn(page);
                if (tf) {
                    var cur = String(tf.contents).replace(/[\r\n\s]/g, "");
                    if (cur === want) { continue; }
                    tf.contents = want;
                    fixed++;
                    W("  p" + page.name + ": 번호 교체 " + cur + " → " + want);
                    continue;
                }
                // 프레임 자체가 없다 → 같은 쪽 도너 복제
                var src = donor[String(page.side)];
                if (!src || !src.isValid) {
                    W("  [경고] p" + page.name + ": 같은 쪽 도너 없음 — 건너뜀");
                    continue;
                }
                var gb2 = src.geometricBounds;
                var ch0 = src.characters[0];
                var cs0 = ch0.appliedCharacterStyle;
                var fn0 = ch0.appliedFont;
                var sz0 = ch0.pointSize;
                var fc0 = ch0.fillColor;
                var ntf = src.duplicate(page);
                ntf.geometricBounds = gb2;      // 파리티가 같아도 명시 지정
                ntf.contents = want;
                try {
                    var all = ntf.texts[0];
                    all.appliedCharacterStyle = cs0;
                    all.appliedFont = fn0;
                    all.pointSize = sz0;
                    all.fillColor = fc0;
                } catch (eS) { W("  [경고] 서식 승계 실패: " + eS); }
                made++;
                W("  p" + page.name + ": 번호 프레임 생성 → " + want
                  + " (도너 p" + src.parentPage.name + ")");
            }
        }

        W("생성 " + made + "건 / 교체 " + fixed + "건");

        // ── 자체 검증 — 보정 후 실제로 찍힌 번호를 다시 읽어 기대치와 대조 ──
        //    프레임 개수는 템플릿마다 다르고(17 고정이 아니다) 지문이 2페이지에
        //    걸치는 배치도 있을 수 있어, "몇 개를 고쳤나"가 아니라 **결과가
        //    기대 순서와 같은가**로 판정한다. 어긋나면 로그에 FAIL 을 남겨
        //    파이썬 검수(verify)가 경고로 올린다.
        var allOk = true;
        for (var vi = 0; vi < order.length; vi++) {
            var vkey = order[vi], vpages = bySec[vkey], seen = [];
            for (var vp = 0; vp < vpages.length; vp++) {
                if (bodyLen(vpages[vp]) < MIN_BODY) { continue; }
                var vf = numFrameOn(vpages[vp]);
                seen.push(vf ? String(vf.contents).replace(/[\r\n\s]/g, "")
                             : "(없음)");
            }
            var want = labels.join(",");
            var got = seen.join(",");
            if (want === got) {
                W("[검증] " + vkey + " PASS — " + seen.length + "개 " + got);
            } else {
                allOk = false;
                W("[검증] " + vkey + " FAIL");
                W("   기대: " + want);
                W("   실제: " + got);
            }
        }
        W(allOk ? "[검증] 전체 PASS" : "[검증] 전체 FAIL — 지문번호 확인 필요");

        if (made > 0 || fixed > 0) { doc.save(); W("저장 완료"); }
        W("===== 지문번호 보정 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
        W("===== 지문번호 보정 완료 =====");
    }
})();
