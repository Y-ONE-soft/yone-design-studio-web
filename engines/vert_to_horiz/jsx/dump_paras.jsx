// [ENGINE TEMPLATE] 문서의 모든 문단을 덤프 — 세로↔가로 내용 대조용.
//
// 세로→가로는 **내용 보존 변환**이다. 세로에 있던 문단은 가로에 전부 있어야
// 한다. 로그가 "오버셋 0 / 슬롯 검수 OK" 여도 프레임 매칭에서 빠진 내용은
// 조용히 사라진다(2026-08-25: STEP3 문항이 선지 중간에서 끊김, 문장배열
// 상단 카드 통째 소실). 그래서 지면 텍스트를 직접 대조한다.
#target indesign
(function () {
    // 러너가 SETTINGS_PATH 를 요구한다 (core/indesign/runner._run_jsx_once)
    var SETTINGS_PATH = "__OUT__";
    var SRC = "__SRC__";
    var OUT = "__OUT__";
    var LOG = "__LOG__";
    var _b = [];
    function W(s) {
        _b.push(String(s));
        var f = new File(LOG);
        f.encoding = "UTF-8"; f.lineFeed = "Unix";
        f.open("w"); f.write(_b.join("\n") + "\n"); f.close();
    }
    W("덤프 시작");
    var doc = null, ours = false;
    try {
        var fo = new File(SRC);
        if (!fo.exists) { W("[오류] 파일 없음: " + SRC); W("===== 덤프 완료 ====="); return; }
        for (var d = 0; d < app.documents.length; d++) {
            try { if (String(app.documents[d].fullName) === String(fo)) { doc = app.documents[d]; ours = false; break; } } catch (e) {}
        }
        if (!doc) { doc = app.open(fo, false); ours = true; }
        var out = new File(OUT);
        out.encoding = "UTF-8"; out.lineFeed = "Unix"; out.open("w");
        var n = 0;
        for (var s = 0; s < doc.stories.length; s++) {
            var st = doc.stories[s];
            var ps;
            try { ps = st.paragraphs; } catch (e1) { continue; }
            for (var p = 0; p < ps.length; p++) {
                var t = "";
                try { t = String(ps[p].contents); } catch (e2) { continue; }
                t = t.replace(/[\r\n\t]+/g, " ");
                if (t.replace(/\s/g, "").length === 0) { continue; }
                // 문단이 놓인 페이지 (첫 컨테이너 기준)
                var pg = "?";
                try {
                    var tf = ps[p].parentTextFrames[0];
                    if (tf && tf.parentPage) { pg = String(tf.parentPage.name); }
                } catch (e3) {}
                out.writeln(pg + "\t" + t);
                n++;
            }
        }
        out.close();
        W("문단 " + n + "개 덤프");
        if (ours) { doc.close(SaveOptions.NO); }
        W("===== 덤프 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 덤프 완료 =====");
        try { if (doc && ours && doc.isValid) { doc.close(SaveOptions.NO); } } catch (e4) {}
    }
})();
