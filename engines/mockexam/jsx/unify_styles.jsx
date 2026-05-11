// unify_styles.jsx
// 현재 열려 있는 동형모의고사 InDesign 템플릿의 단락 스타일을
// 표준 이름으로 rename한다. 시각적 서식(폰트, 크기 등)은 유지.
//
// 사용법: 각 학교 템플릿을 열고 이 스크립트를 실행
// 이미 표준 이름이면 스킵, 없는 스타일은 새로 생성
#target indesign

(function() {
    if (app.documents.length === 0) {
        alert("문서를 열고 실행하세요.");
        return;
    }
    var doc = app.activeDocument;

    // ── 표준 스타일 이름 및 학교별 매핑 ──────────────────────────────────────
    // key: 표준 이름, value: 이 이름으로 rename될 수 있는 기존 이름 목록
    var RENAME_MAP = {
        // 공통 (이미 모든 학교에서 동일)
        "지문":          [],
        "다음 글을 읽고":  [],
        "문제 번호":      [],
        "서술형 번호":    [],
        "선지":          [],
        "영단어":        [],

        // 순서 지문: (A) (B) (C) 문단
        "지문_순서":      ["순서", "영어지문-순서", "영어지문 순서"],

        // 대화 지문
        "지문_대화":      ["영어지문-대화", "영어지문 대화", "테두리_대화"],

        // 보기 테두리
        "테두리_보기":    ["보기 테두리", "보기 테두리_", "보기/조건/해석"],

        // 조건 테두리
        "테두리_조건":    [],

        // 요약 테두리
        "테두리_요약":    [],

        // 순서/삽입 테두리
        "테두리_순서삽입": ["순서&삽입&기준 테두리", "테두리"],

        // 다중선택
        "테두리_다중선택": ["다중 보기", "테두리X_다중선택", "테두리_다중선택"],

        // 서술형 답지 (빈칸 완성 라인)
        "서술형답지":     ["서답형_꼬리문제"],

        // 공통 (밑줄 없는 지문)
        "공통":           [],

        // 빈칸 답란
        "빈칸":           []
    };

    var renamed = [];
    var created = [];
    var skipped = [];

    for (var stdName in RENAME_MAP) {
        if (!RENAME_MAP.hasOwnProperty(stdName)) continue;

        var aliases = RENAME_MAP[stdName];

        // 1) 표준 이름이 이미 존재하면 스킵
        var existing = doc.paragraphStyles.itemByName(stdName);
        if (existing.isValid) {
            skipped.push(stdName);
            continue;
        }

        // 2) alias 중 존재하는 것 찾아서 rename
        var found = false;
        for (var a = 0; a < aliases.length; a++) {
            var alias = doc.paragraphStyles.itemByName(aliases[a]);
            if (alias.isValid) {
                alias.name = stdName;
                renamed.push(aliases[a] + " -> " + stdName);
                found = true;
                break;
            }
        }

        // 3) 없으면 새로 생성 (기본 단락 기반)
        if (!found) {
            doc.paragraphStyles.add({name: stdName});
            created.push(stdName);
        }
    }

    // ── 문자 스타일 "밑줄" 확인 ──────────────────────────────────────────────
    var csUnderline = doc.characterStyles.itemByName("밑줄");
    if (!csUnderline.isValid) {
        doc.characterStyles.add({name: "밑줄", underline: true});
        created.push("[문자] 밑줄");
    }

    var msg = "스타일 통일 완료!\n\n";
    if (renamed.length) msg += "Renamed (" + renamed.length + "):\n  " + renamed.join("\n  ") + "\n\n";
    if (created.length) msg += "Created (" + created.length + "):\n  " + created.join("\n  ") + "\n\n";
    if (skipped.length) msg += "Already OK (" + skipped.length + "):\n  " + skipped.join(", ");

    alert(msg);
})();
