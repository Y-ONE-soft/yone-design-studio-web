// PageInterleave.jsx — InDesign ExtendScript
//
// 색깔 그룹별 페이지를 1페이지씩 인터리브로 재배치
//
// 색깔 그룹 (각 18페이지):
//   분홍  4- 21  /  주황 22- 39  /  노랑 40- 57  /  연두  58- 75
//   파랑 76- 93  /  보라 94-111  /  빨강 112-129  /  갈색 130-147
//   초록 148-165  /  찐보라 166-183
//
// 각 라운드 k (1~18):
//   앵커: 분홍 k번째 페이지 바로 뒤
//   이동: 주황~찐보라 각 그룹의 k번째 페이지 (9페이지)
//
//   k=1:  22,40,58,76,94,112,130,148,166  →  4번 뒤
//   k=2:  23,41,59,77,95,113,131,149,167  →  5번 뒤
//   k=3:  24,42,60,78,96,114,132,150,168  →  6번 뒤
//   ...
//
// 184페이지 이후(O마스터)는 건드리지 않음
//
// [핵심] 인덱스 대신 레이블로 페이지 추적 →
//        InDesign 스프레드 자동 재배치로 인한 인덱스 오류 방지

#target indesign

(function () {
    var doc = app.activeDocument;

    if (doc.pages.length < 184) {
        alert("문서 페이지 수(" + doc.pages.length + ")가 184페이지 미만입니다.");
        return;
    }

    var PFX = "__pi_";

    // 1) 페이지 4~183에 원래 번호를 레이블로 기록 + 맵 생성
    var pageMap = {};
    for (var i = 3; i <= 182; i++) {   // 0-indexed: 3=p4, 182=p183
        var origNum = i + 1;
        doc.pages[i].label = PFX + origNum;
        pageMap[origNum] = doc.pages[i];
    }

    // 그룹 시작 오프셋: origPage = offset + k
    //   분홍 anchor: 3+k  (k=1→4, k=18→21)
    //   주황:  21+k  (k=1→22, k=18→39)
    //   노랑:  39+k
    //   연두:  57+k
    //   파랑:  75+k
    //   보라:  93+k
    //   빨강: 111+k
    //   갈색: 129+k
    //   초록: 147+k
    //   찐보라: 165+k
    var groupOffsets = [21, 39, 57, 75, 93, 111, 129, 147, 165];

    // 2) 18번 반복
    for (var k = 1; k <= 18; k++) {
        // 앵커: 분홍 k번째 페이지 (원래 번호 k+3)
        var anchor = pageMap[k + 3];
        if (!anchor || !anchor.isValid) {
            alert("앵커 페이지(원본 " + (k+3) + ")를 찾을 수 없습니다. 중단합니다.");
            break;
        }

        // 이동할 9개 페이지 객체 수집
        var toMove = [];
        for (var g = 0; g < groupOffsets.length; g++) {
            var origNum = groupOffsets[g] + k;
            var p = pageMap[origNum];
            if (!p || !p.isValid) {
                alert("페이지(원본 " + origNum + ")를 찾을 수 없습니다. 중단합니다.");
                break;
            }
            toMove.push(p);
        }

        // 역순 삽입 → 최종 순서: 주황→노랑→…→찐보라
        for (var j = toMove.length - 1; j >= 0; j--) {
            toMove[j].move(LocationOptions.AFTER, anchor);
        }
    }

    // 3) 레이블 제거
    for (var i = 0; i < doc.pages.length; i++) {
        if (doc.pages[i].label.indexOf(PFX) === 0) {
            doc.pages[i].label = "";
        }
    }

    alert("페이지 정리 완료!");
})();
