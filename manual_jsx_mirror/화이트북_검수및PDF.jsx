// 화이트북_검수및PDF.jsx
// 화이트북 조판 완료 후 검수 체크 및 PDF 내보내기
// 검수 항목: 오버플로우, 누락 섹션, 스타일 불일치, 빈 프레임

#target indesign

(function () {

    // ─────────────────────────────────────────────
    // 검수 설정
    // ─────────────────────────────────────────────
    var REQUIRED_STYLES = [
        'A 어휘', 'C 예문', 'C 예문 사본',
        'C 단어 박스', 'D 영영사전',
        'D 단어 박스 new', 'E 전치사'
    ];

    var FILL_MARKERS = ['______', '___'];  // 빈칸 마커 (원고 내 채워야 할 부분 표시용)

    // ─────────────────────────────────────────────
    // 검수 실행
    // ─────────────────────────────────────────────
    function runVerification(doc) {
        var issues = [];
        var summary = {};

        // 1. 오버플로우 체크
        var overflowCount = 0;
        var tfs = doc.textFrames;
        for (var i = 0; i < tfs.length; i++) {
            try {
                if (tfs[i].overflows) {
                    var pg = tfs[i].parentPage;
                    var pgNum = pg ? pg.name : '?';
                    issues.push('[오버플로우] 페이지 ' + pgNum);
                    overflowCount++;
                }
            } catch(e) {}
        }
        summary['오버플로우'] = overflowCount + '개';

        // 2. 각 스타일별 스토리 수 카운트 (섹션 수 검증)
        var styleCounts = {};
        var seenStories = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var pageTFs = doc.pages[p].textFrames;
            for (var t = 0; t < pageTFs.length; t++) {
                var story = pageTFs[t].parentStory;
                if (seenStories[story.id]) continue;
                if (story.paragraphs.length > 0) {
                    var sn = story.paragraphs[0].appliedParagraphStyle.name;
                    styleCounts[sn] = (styleCounts[sn] || 0) + 1;
                    seenStories[story.id] = true;
                }
            }
        }

        for (var i = 0; i < REQUIRED_STYLES.length; i++) {
            var sty = REQUIRED_STYLES[i];
            var cnt = styleCounts[sty] || 0;
            summary[sty + ' 섹션 수'] = cnt + '개';
            if (cnt === 0) {
                issues.push('[누락 섹션] ' + sty + ' 스타일 스토리가 없음');
            }
        }

        // 3. 빈 프레임 (A 어휘, C 예문 스타일이지만 내용이 짧거나 없음)
        var emptyFrames = 0;
        seenStories = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var pageTFs = doc.pages[p].textFrames;
            for (var t = 0; t < pageTFs.length; t++) {
                var story = pageTFs[t].parentStory;
                if (seenStories[story.id]) continue;
                seenStories[story.id] = true;
                if (story.paragraphs.length > 0) {
                    var sn = story.paragraphs[0].appliedParagraphStyle.name;
                    if (sn === 'A 어휘' || sn === 'C 예문' || sn === 'E 전치사') {
                        var cnt = story.paragraphs.length;
                        if (cnt <= 1 && story.contents.replace(/\r/g, '').length < 5) {
                            var pg = pageTFs[t].parentPage;
                            var pgNum = pg ? pg.name : '?';
                            issues.push('[빈 프레임] 페이지 ' + pgNum + ' - ' + sn);
                            emptyFrames++;
                        }
                    }
                }
            }
        }
        summary['빈 프레임'] = emptyFrames + '개';

        // 4. 원고 단어 수 검증 (A 어휘: 각 스토리 30단락이어야 함)
        var aWordIssues = 0;
        var aFound = [];
        seenStories = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var pageTFs = doc.pages[p].textFrames;
            for (var t = 0; t < pageTFs.length; t++) {
                var story = pageTFs[t].parentStory;
                if (seenStories[story.id]) continue;
                if (story.paragraphs.length > 0 &&
                    story.paragraphs[0].appliedParagraphStyle.name === 'A 어휘') {
                    seenStories[story.id] = true;
                    aFound.push(story);
                }
            }
        }
        for (var i = 0; i < aFound.length; i++) {
            var cnt = aFound[i].paragraphs.length;
            if (cnt !== 30) {
                issues.push('[단어 수 오류] A 어휘 스토리 #' + (i+1) + ': ' + cnt + '단락 (30이어야 함)');
                aWordIssues++;
            }
        }
        summary['A 어휘 단어 수 오류'] = aWordIssues + '개';

        return {issues: issues, summary: summary};
    }

    // ─────────────────────────────────────────────
    // PDF 내보내기
    // ─────────────────────────────────────────────
    function exportPDF(doc, pdfPath) {
        var pdfFile = new File(pdfPath);

        // PDF 내보내기 프리셋 (기본값 사용)
        var preset = app.pdfExportPresets.itemByName('[고품질 인쇄]');
        if (!preset.isValid) {
            preset = app.pdfExportPresets.itemByName('[High Quality Print]');
        }

        try {
            if (preset.isValid) {
                doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false, preset);
            } else {
                // 프리셋 없으면 기본 옵션 사용
                doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false);
            }
            return true;
        } catch(e) {
            alert('PDF 내보내기 실패: ' + e.message);
            return false;
        }
    }

    // ─────────────────────────────────────────────
    // 검수 보고서 저장
    // ─────────────────────────────────────────────
    function saveReport(reportPath, result, pdfSuccess) {
        var lines = [];
        lines.push('화이트북 조판 검수 보고서');
        lines.push('생성 일시: ' + new Date().toString());
        lines.push('');
        lines.push('── 요약 ──');
        for (var key in result.summary) {
            lines.push('  ' + key + ': ' + result.summary[key]);
        }
        lines.push('');
        if (result.issues.length === 0) {
            lines.push('✅ 문제 없음');
        } else {
            lines.push('⚠️ 발견된 문제 (' + result.issues.length + '개):');
            for (var i = 0; i < result.issues.length; i++) {
                lines.push('  ' + result.issues[i]);
            }
        }
        lines.push('');
        lines.push('PDF 내보내기: ' + (pdfSuccess ? '성공' : '실패'));

        var f = new File(reportPath);
        f.encoding = 'UTF-8';
        f.open('w');
        f.write(lines.join('\n'));
        f.close();
        return lines.join('\n');
    }

    // ─────────────────────────────────────────────
    // 메인
    // ─────────────────────────────────────────────
    function main() {
        var doc = app.activeDocument;
        if (!doc) {
            alert('열린 InDesign 문서가 없습니다.');
            return;
        }

        // 저장 경로 설정 (문서와 같은 폴더)
        var docPath = doc.filePath.fsName;
        var docName = doc.name.replace(/\.indd$/i, '');
        var outputDir = docPath + '/auto/output';
        var pdfPath = outputDir + '/' + docName + '.pdf';
        var reportPath = outputDir + '/검수보고서.txt';

        // output 폴더 확인/생성
        var outFolder = new Folder(outputDir);
        if (!outFolder.exists) outFolder.create();

        // 검수 실행
        $.writeln('검수 시작...');
        var result = runVerification(doc);

        // PDF 내보내기
        $.writeln('PDF 내보내기: ' + pdfPath);
        var pdfSuccess = exportPDF(doc, pdfPath);

        // 보고서 저장
        var reportText = saveReport(reportPath, result, pdfSuccess);

        // 완료 알림
        var msg = '검수 및 PDF 내보내기 완료\n\n';
        msg += '문제: ' + result.issues.length + '개\n';
        msg += 'PDF: ' + (pdfSuccess ? '성공' : '실패') + '\n\n';
        if (result.issues.length > 0) {
            msg += '주요 문제:\n';
            for (var i = 0; i < Math.min(5, result.issues.length); i++) {
                msg += '  ' + result.issues[i] + '\n';
            }
            if (result.issues.length > 5) msg += '  ... 외 ' + (result.issues.length - 5) + '개';
        }
        msg += '\n보고서 저장: ' + reportPath;
        alert(msg);
    }

    main();

})();
