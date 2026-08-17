// [ENGINE TEMPLATE] 워크북 선택 결합 — 하단 문제 발문을 문항 유형에 맞춘다
//
// 어법선택 하단의 발문("다음 밑줄 친 부분 중 어법상 틀린 것은?")은 원고가
// 아니라 **InDesign 템플릿의 정적 프레임**이다. 그래서 네모형 문항
// ((A),(B),(C) 중 고르기)에도 밑줄형 발문이 그대로 붙는다.
//   실측 2026-08-08: 마더텅 26(230631)·32(220633) 두 문항이 네모형인데
//   발문은 밑줄형. 오버셋·링크·폰트·중복 검사 전부 통과한다.
//
// 발문 문구는 지어내지 않는다 — **원고에 있는 발문**을 쓴다.
// prompts.json: [{"match": "지문 앞부분", "prompt": "발문 전문"}]
// 하단 문제 프레임 내용이 match 로 시작하는 페이지의 발문 프레임만 바꾼다.
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";

    var logFile = new File(settingsPath.replace(/\.settings\.json$/,
                                                "prompt_로그.txt"));
    logFile.encoding = "UTF-8";
    logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("발문 교정 시작");

    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8";
        sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        var pf = new File(settingsPath.replace(/\.settings\.json$/,
                                               "prompts.json"));
        if (!pf.exists) {
            W("prompts.json 없음 — 교정 대상 없음");
            W("===== 발문 교정 완료 =====");
            return;
        }
        pf.encoding = "UTF-8";
        pf.open("r");
        var specs = eval("(" + pf.read() + ")");
        pf.close();
        if (!specs || !specs.length) {
            W("교정 대상 0건");
            W("===== 발문 교정 완료 =====");
            return;
        }
        W("교정 대상 " + specs.length + "건");

        var d = app.open(new File(settings.indd_path), false);
        try { d.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN; } catch (e0) {}

        function norm(s) {
            return String(s).replace(/\s+/g, " ")
                            .replace(/[^A-Za-z ]/g, "").toLowerCase();
        }

        var fixed = 0, sized = 0, iconed = 0, i, j, k;

        // ── 괄호가 사라지는 문제 ────────────────────────────────────────
        // 발문 프레임은 **본문 스타일(A1_어휘 선택)** 을 쓰는데, 그 스타일의
        // GREP 스타일이 `\(.+?\)` 를 문자스타일 "투명"(0.9pt)으로 만든다.
        // 원래 정적 발문에는 괄호가 없어 아무도 몰랐지만, 네모형 발문
        // "(A), (B), (C)의 각 네모 안에서…" 를 주입하면 (A)(B)(C) 가 지면에서
        // 사라진다(", , 의 각 네모…"). 글자는 남아 있어 텍스트 대조·오버셋·
        // 프리플라이트가 전부 통과한다 — 렌더 육안으로만 잡힌다.
        //
        // 실측(2026-08-17, 사본 대조):
        //   · 명시 문자스타일 적용 → GREP 을 못 이긴다 (여전히 0.9pt)
        //   · 단락 수준 nestedGrepStyles 제거 → "개체가 없다" 예외
        //   · **GREP 만 뺀 전용 단락스타일 복제 후 적용 → 9.0pt 정상**  ← 채택
        function promptStyle(doc, para) {
            var src = para.appliedParagraphStyle;
            if (/_발문$/.test(src.name)) { return src; }   // 이미 적용됨
            var nm = src.name + "_발문";
            var grp = src.parent;
            var ns = grp.paragraphStyles.itemByName(nm);
            if (!ns.isValid) {
                ns = src.duplicate();
                ns.name = nm;
            }
            // everyItem().remove() 는 순회 중 컬렉션이 무너져 실패한다 → 역순
            for (var g = ns.nestedGrepStyles.length - 1; g >= 0; g--) {
                ns.nestedGrepStyles[g].remove();
            }
            return ns;
        }

        // ── 앵커 아이콘(☑) 복구 ──────────────────────────────────────────
        // U+FFFC 는 앵커 개체의 자리표시 문자일 뿐이라, 문자열로 다시 써도
        // 개체가 생기지 않는다. contents 통짜 대입으로 아이콘을 잃은 발문에
        // 다른 발문의 아이콘을 복제해 넣는다.
        function donorIcon(doc, exclude) {
            for (var p = 0; p < doc.pages.length; p++) {
                var t2 = doc.pages[p].textFrames;
                for (var q = 0; q < t2.length; q++) {
                    if (t2[q] === exclude) { continue; }
                    var cc;
                    try { cc = String(t2[q].contents); } catch (eD) { continue; }
                    if (cc.length > 120 || cc.charCodeAt(0) !== 0xFFFC) { continue; }
                    if (cc.indexOf("것은?") < 0 && cc.indexOf("고르") < 0) { continue; }
                    try {
                        if (t2[q].characters[0].pageItems.length) {
                            return t2[q].characters[0].pageItems[0];
                        }
                    } catch (eD2) {}
                }
            }
            return null;
        }
        for (i = 0; i < d.pages.length; i++) {
            var pg = d.pages[i];
            var tfs = pg.textFrames;
            var promptTf = null, bodyTxt = "";
            for (j = 0; j < tfs.length; j++) {
                var gb, c;
                try { gb = tfs[j].geometricBounds; } catch (e1) { continue; }
                if (gb[0] < 150) continue;              // 하단 영역만
                try { c = String(tfs[j].contents); } catch (e2) { continue; }
                if ((gb[2] - gb[0]) < 20) {
                    // 짧은 프레임 = 발문
                    if (/어법/.test(c)) promptTf = tfs[j];
                } else if (c.length > bodyTxt.length) {
                    bodyTxt = c;
                }
            }
            if (!promptTf || !bodyTxt) continue;

            var nb = norm(bodyTxt);
            for (k = 0; k < specs.length; k++) {
                var m = norm(specs[k].match);
                if (!m || nb.indexOf(m) !== 0) continue;
                var want = String(specs[k].prompt);
                var cur = String(promptTf.contents);
                var already = (cur.indexOf(want) >= 0);
                if (!already) {
                    // 앵커 아이콘(￼)은 **문자로 다시 쓸 수 없다** — 개체가
                    // 아니라 자리표시 문자만 생긴다. 아이콘 뒤 글자만 바꾼다.
                    var hasIcon = (cur.length &&
                                   cur.charCodeAt(0) === 0xFFFC);
                    if (hasIcon && promptTf.characters.length > 1) {
                        promptTf.characters.itemByRange(
                            1, promptTf.characters.length - 1
                        ).contents = " " + want;
                    } else {
                        promptTf.contents = want;
                    }
                    fixed++;
                    W("  p" + pg.name + ": 발문 교체 → "
                      + want.substring(0, 40));
                }
                // ⚠ 크기 교정은 **교체를 건너뛴 경우에도** 반드시 돈다.
                //    통짜 contents 대입은 기존 문자 서식 범위를 새 글자에
                //    물려준다. 실측 2026-08-17: 템플릿 발문에 남아 있던
                //    0.9pt 런이 새 문구 앞부분에 걸려 "(A), (B), (C)" 가
                //    0.9pt 로 찍혀 지면에서 사라졌다(", , 의 각 네모…").
                //    글자는 남아 있어 텍스트 대조·오버셋·프리플라이트가 전부
                //    통과한다 — 렌더 육안으로만 잡히는 종류다. 그래서 "이미
                //    문구가 맞음"으로 빠져나가면 영영 안 고쳐진다.
                // 괄호가 있는 발문만 전용 스타일로 (없으면 GREP 이 안 걸려
                // 손댈 이유가 없다 — 변경 범위를 최소로)
                if (want.indexOf("(") >= 0) {
                    try {
                        var para0 = promptTf.paragraphs[0];
                        var before = para0.appliedParagraphStyle.name;
                        var st2 = promptStyle(d, para0);
                        if (st2.name !== before) {
                            para0.appliedParagraphStyle = st2;
                            sized++;
                            W("  p" + pg.name + ": [GREP회피] 단락스타일 "
                              + before + " → " + st2.name);
                        }
                    } catch (eSt) { W("  [경고] 스타일 교정 실패: " + eSt); }
                }
                // 아이콘이 없으면 다른 발문에서 복제해 넣는다
                try {
                    var now = String(promptTf.contents);
                    if (now.charCodeAt(0) !== 0xFFFC) {
                        var src2 = donorIcon(d, promptTf);
                        if (src2) {
                            var cl = src2.duplicate();
                            cl.anchoredObjectSettings.insertAnchoredObject(
                                promptTf.insertionPoints[0],
                                AnchorPosition.INLINE_POSITION);
                            iconed++;
                            W("  p" + pg.name + ": [아이콘] 앵커 아이콘 복구");
                        } else {
                            W("  p" + pg.name + ": [아이콘] 도너 없음 — 건너뜀");
                        }
                    }
                } catch (eIc) { W("  [경고] 아이콘 복구 실패: " + eIc); }
                break;
            }
        }
        W("발문 교체 " + fixed + "건 / GREP회피 스타일 " + sized
          + "건 / 아이콘 복구 " + iconed + "건");
        if (fixed > 0 || sized > 0 || iconed > 0) { d.save(); }
        d.close(SaveOptions.NO);
        W("===== 발문 교정 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
    }
})();
