"""한영보카 InDesign 단계별 실행기 v4.

핵심 원칙:
- 마스터 페이지 절대 변경하지 않음 (세로형 섹션 시작 I-마스터만 예외)
- 원본 레이아웃 보존, 셀 내용만 교체
- 가로형: 각 섹션(Day)은 반드시 하나의 테이블에만 배치 (경계 넘김 방지)
- 오버플로우 발생 시 autoGrow + 프레임 높이 확장으로 해소
"""

import json
import os
import subprocess
import time

_jsx_counter = [0]


def _find_app():
    for ver in ["2026", "2025", "2024"]:
        if os.path.isdir(f"/Applications/Adobe InDesign {ver}"):
            return f"Adobe InDesign {ver}"
    raise RuntimeError("InDesign 없음")


def _jsx(app, code, timeout=30, retries=3):
    """JSX를 파일로 저장 후 osascript로 실행."""
    time.sleep(0.3)  # InDesign 안정성을 위한 호출 간 지연
    _jsx_counter[0] += 1
    n = _jsx_counter[0]
    jf = f"/tmp/_stp_{n}.jsx"
    af = f"/tmp/_stp_{n}.scpt"
    with open(jf, "w", encoding="utf-8") as f:
        f.write(code)
    with open(af, "w") as f:
        f.write(f'tell application "{app}" to do script POSIX file "{jf}" language javascript\n')

    for attempt in range(retries):
        if attempt > 0:
            _dismiss(app)
            time.sleep(2)
        try:
            r = subprocess.run(["osascript", af], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            time.sleep(3)
            continue
        if r.returncode == 0:
            return r.stdout.strip()
        err = r.stderr.strip()
        if "30486" in err:
            _dismiss(app)
            time.sleep(3)
            continue
        if "-609" in err:
            time.sleep(5)
            continue
        raise RuntimeError(f"JSX: {err[:200]}")
    raise RuntimeError("JSX 재시도 초과")


def _dismiss(app):
    try:
        subprocess.run(["osascript", "-e", '''
            tell application "Adobe InDesign 2026" to activate
            delay 0.5
            try
                tell application "System Events"
                    tell process "Adobe InDesign 2026"
                        set frontmost to true
                        delay 0.5
                        click button 1 of window 1
                    end tell
                end tell
            on error
                try
                    tell application "System Events" to key code 36
                end try
            end try
        '''], capture_output=True, text=True, timeout=10)
    except Exception:
        pass


def run_typeset(settings_path, log):
    app = _find_app()
    log(f"[InDesign] {app}")

    _dismiss(app)
    # 작업 중인 다른 문서 보호: 전체 문서 닫기(close-all) 제거.
    # 조판 대상은 매 실행 safe_copy_indd가 새 경로(_2, _3…)로 생성하므로 충돌 없음.

    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)

    log_lines = []
    for job in settings.get("jobs", []):
        try:
            _run_job(app, job, settings_path, log, log_lines)
        except Exception as e:
            _log(log, log_lines, f"[오류] {e}")

    log_path = settings_path.replace(".settings.json", "typeset_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))


def _run_single_jsx(app, job, content, is_sero, settings_path, log, log_lines):
    """단일 JSX로 데이터 채우기 + 정리 + PDF 내보내기 (세로형/가로형 공통)."""
    import shutil
    chapters = content.get("chapters", [])
    total = content.get("total_entries", 0)
    layout = "세로형" if is_sero else "가로형"
    _log(log, log_lines, f"단원: {len(chapters)} | 단어: {total}")

    # 영문 경로에 복사
    eng = "sero" if is_sero else "garo"
    tmp_indd = f"/tmp/hanyoung_{eng}.indd"
    # 이전 실행에서 열어 둔 동일 이름 임시 결과 문서가 있으면 닫는다.
    # (고정 임시 경로 재사용 — 열린 채로 두면 덮어쓰기/스테일 재오픈 충돌. 이름으로만 매칭해 정리)
    _close_old = (
        'for(var i=app.documents.length-1;i>=0;i--){'
        'try{if(app.documents[i].name=="hanyoung_%s.indd")'
        'app.documents[i].close(SaveOptions.NO);}catch(e){}}'
    ) % eng
    _jsx(app, _close_old)
    shutil.copy2(job["indd_path"], tmp_indd)

    # 전체 데이터를 JSON으로 저장
    # 세로형: chapters 구조 유지 (단원별 테이블 분리)
    # 가로형: 섹션별 테이블 분리
    if is_sero:
        data_for_jsx = []
        for ch in chapters:
            ch_sections = []
            for sec in ch.get("sections", []):
                entries = [{"w": e.get("word",""), "m": e.get("meaning",""),
                            "s": e.get("synonym",""), "a": e.get("antonym",""),
                            "d": e.get("definition","")} for e in sec.get("entries", [])]
                ch_sections.append({"name": sec["name"], "entries": entries})
            data_for_jsx.append({"name": ch["name"], "sections": ch_sections})
    else:
        data_for_jsx = []
        for ch in chapters:
            for sec in ch.get("sections", []):
                entries = [{"w": e.get("word",""), "m": e.get("meaning",""),
                            "s": e.get("synonym",""), "a": e.get("antonym",""),
                            "d": e.get("definition","")} for e in sec.get("entries", [])]
                data_for_jsx.append({"name": sec["name"], "entries": entries, "chapter": ch["name"]})

    data_file = f"/tmp/_hanyoung_{eng}_data.json"
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump({"layout": layout, "is_sero": is_sero, "data": data_for_jsx}, f, ensure_ascii=False)

    ch_name = chapters[0]["name"] if chapters else ""
    ch_safe = ch_name.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

    # 단일 JSX 실행
    _jsx(app, 'app.scriptPreferences.userInteractionLevel=UserInteractionLevels.NEVER_INTERACT;')
    _jsx(app, f'app.open(File("{tmp_indd}"));', timeout=120)
    _log(log, log_lines, "문서 열기 완료")

    # 모든 테이블 데이터 셀 초기화 (원본 템플릿에 이전 데이터가 남아있을 수 있음)
    _jsx(app, '''
        var doc=app.activeDocument;
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++){
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0){
                    var tbl=tf.tables[0];
                    var cc=tbl.columns.length;
                    for(var r=1;r<tbl.rows.length;r++)
                        for(var c=0;c<cc;c++)
                            try{tbl.cells.item(r*cc+c).contents="";}catch(e){}
                } else if(!tf.previousTextFrame) {
                    try{tf.contents="";}catch(e){}
                }
            }
    ''', timeout=300)
    _log(log, log_lines, "데이터 초기화 완료")

    # 세로형: 용량 체크 + 부족 시 페이지 추가 (단원별 테이블 할당 시뮬레이션)
    if is_sero:
        # 현재 테이블 행 수 확인
        table_info = _jsx(app, '''
            var doc=app.activeDocument;var r=[];
            for(var i=0;i<doc.pages.length;i++)
                for(var j=0;j<doc.pages[i].textFrames.length;j++)
                    if(doc.pages[i].textFrames[j].tables.length>0)
                        r.push(doc.pages[i].textFrames[j].tables[0].rows.length-1);
            r.join(",");
        ''')
        table_rows_list = [int(x) for x in table_info.split(",") if x]
        # 단원별 테이블 할당 시뮬레이션
        needed_extra = 0
        ti_sim, ri_sim = 0, 1
        current_ch_sim = None
        for ch in chapters:
            if ch["name"] != current_ch_sim and current_ch_sim is not None and ri_sim > 1:
                ti_sim += 1; ri_sim = 1
            current_ch_sim = ch["name"]
            for sec in ch.get("sections", []):
                count = sec.get("count", len(sec.get("entries", [])))
                for _ in range(count):
                    if ti_sim < len(table_rows_list) and ri_sim > table_rows_list[ti_sim]:
                        ti_sim += 1; ri_sim = 1
                    if ti_sim >= len(table_rows_list):
                        needed_extra += 1
                    ri_sim += 1
        if needed_extra > 0:
            extra = needed_extra
            last_rows = table_rows_list[-1] if table_rows_list else 40
            pages_needed = (extra + last_rows - 1) // last_rows
            _log(log, log_lines, f"표 부족: {extra}행 → 마지막 테이블에 {extra}행 추가")
            _jsx(app, f'''
                var doc=app.activeDocument;
                var lastTbl=null;
                for(var i=doc.pages.length-1;i>=0&&!lastTbl;i--)
                    for(var j=0;j<doc.pages[i].textFrames.length;j++)
                        if(doc.pages[i].textFrames[j].tables.length>0){{lastTbl=doc.pages[i].textFrames[j].tables[0];break;}}
                if(lastTbl){{
                    for(var r=0;r<{extra};r++)
                        try{{lastTbl.rows.add();}}catch(e){{break;}}
                }}
            ''', timeout=120)

    result = _jsx(app, f'''
        var doc=app.activeDocument;
        var df=new File("{data_file}");
        df.encoding="UTF-8";df.open("r");
        var raw=eval("("+df.read()+")");
        df.close();
        var isSero=raw.is_sero;
        var data=raw.data;

        // 섹션 초기화
        while(doc.sections.length>1)
            try{{doc.sections[doc.sections.length-1].remove();}}catch(e){{break;}}
        doc.sections[0].marker="";

        // 마스터 페이지
        var masterI=null,masterA=null;
        for(var mi=0;mi<doc.masterSpreads.length;mi++){{
            var mn=doc.masterSpreads[mi].name;
            if(mn.charAt(0)==="I") masterI=doc.masterSpreads[mi];
            if(mn.charAt(0)==="A") masterA=doc.masterSpreads[mi];
        }}

        // 단원 문자스타일
        var csChapter=null;
        try{{csChapter=doc.characterStyles.itemByName("단원");if(!csChapter.isValid)csChapter=null;}}catch(e){{}}

        // 테이블 수집
        var tables=[],tablePages=[],tableTFs=[];
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++)
                if(doc.pages[i].textFrames[j].tables.length>0){{
                    tables.push(doc.pages[i].textFrames[j].tables[0]);
                    tablePages.push(doc.pages[i]);
                    tableTFs.push(doc.pages[i].textFrames[j]);
                }}

        var filled=0;
        var usedTableIndices={{}};
        var lastUsedRow={{}};  // 테이블별 마지막 사용 행 추적

        if(isSero){{
            // 세로형: chapters > sections > entries
            var ti=0,ri=1;
            var currentCh="";
            for(var chi=0;chi<data.length;chi++){{
                var ch=data[chi];
                // 단원 변경 → 다음 테이블
                if(ch.name!==currentCh&&currentCh!==""&&ri>1){{ti++;ri=1;}}
                currentCh=ch.name;
                if(ti>=tables.length) break;
                usedTableIndices[ti]=true;

                // I-마스터 + 단원 텍스트
                var pg=tablePages[ti];
                if(masterI) try{{pg.appliedMaster=masterI;}}catch(e){{}}
                for(var fi=0;fi<pg.textFrames.length;fi++){{
                    if(pg.textFrames[fi].tables.length===0){{
                        pg.textFrames[fi].contents=ch.name;
                        if(csChapter)
                            for(var ci=0;ci<pg.textFrames[fi].characters.length;ci++)
                                pg.textFrames[fi].characters[ci].appliedCharacterStyle=csChapter;
                        break;
                    }}
                }}

                for(var si=0;si<ch.sections.length;si++){{
                    var sec=ch.sections[si];
                    if(ti>=tables.length) break;

                    // 섹션 마커 (같은 페이지에 이미 있으면 건너뜀)
                    var spg=tablePages[ti];
                    var secExists=false;
                    for(var k=0;k<doc.sections.length;k++)
                        if(doc.sections[k].pageStart===spg&&doc.sections[k].marker!==""){{secExists=true;break;}}
                    if(!secExists){{
                        try{{var ns=doc.sections.add(spg);ns.marker=sec.name;ns.continueNumbering=true;}}
                        catch(e){{for(var k2=0;k2<doc.sections.length;k2++)
                            if(doc.sections[k2].pageStart===spg){{doc.sections[k2].marker=sec.name;break;}}}}
                    }}

                    // 데이터 채우기
                    for(var ei=0;ei<sec.entries.length;ei++){{
                        if(ti>=tables.length) break;
                        var tbl=tables[ti];var cc=tbl.columns.length;
                        if(ri>=tbl.rows.length){{lastUsedRow[ti]=ri;ti++;ri=1;if(ti>=tables.length)break;tbl=tables[ti];cc=tbl.columns.length;usedTableIndices[ti]=true;}}
                        var b=ri*cc;
                        try{{
                            tbl.cells.item(b+0).contents=sec.entries[ei].w||"";
                            tbl.cells.item(b+1).contents=sec.entries[ei].m||"";
                            tbl.cells.item(b+2).contents=sec.entries[ei].s||"";
                            tbl.cells.item(b+3).contents=sec.entries[ei].a||"";
                        }}catch(e){{}}
                        lastUsedRow[ti]=ri+1;
                        ri++;filled++;
                    }}
                }}
            }}
        }}else{{
            // 가로형: 섹션별 테이블 1:1 매핑
            for(var si=0;si<data.length&&si<tables.length;si++){{
                var sec=data[si];
                var tbl=tables[si];var cc=tbl.columns.length;
                var pg=tablePages[si];
                usedTableIndices[si]=true;

                // 섹션 마커
                try{{var ns=doc.sections.add(pg);ns.marker=sec.name;ns.continueNumbering=true;}}
                catch(e){{for(var k=0;k<doc.sections.length;k++)
                    if(doc.sections[k].pageStart===pg){{doc.sections[k].marker=sec.name;break;}}}}

                // 단원 텍스트 (첫 섹션 또는 단원 변경 시)
                var garoChNew=(si===0)||(si>0&&data[si].chapter!==data[si-1].chapter);
                if(garoChNew){{
                    for(var fi=0;fi<pg.textFrames.length;fi++){{
                        if(pg.textFrames[fi].tables.length===0){{
                            pg.textFrames[fi].contents=sec.chapter||"";
                            if(csChapter) for(var ci=0;ci<pg.textFrames[fi].characters.length;ci++)
                                pg.textFrames[fi].characters[ci].appliedCharacterStyle=csChapter;
                            break;
                        }}
                    }}
                }}

                // 데이터 채우기
                for(var ei=0;ei<sec.entries.length;ei++){{
                    var ri=ei+1;
                    if(ri>=tbl.rows.length){{try{{tbl.rows.add();}}catch(e){{break;}}}}
                    var b=ri*cc;
                    try{{
                        tbl.cells.item(b+0).contents=sec.entries[ei].w||"";
                        tbl.cells.item(b+1).contents=sec.entries[ei].m||"";
                        if(cc>=6) tbl.cells.item(b+2).contents=sec.entries[ei].d||"";
                        tbl.cells.item(b+(cc>=6?3:2)).contents=sec.entries[ei].s||"";
                        tbl.cells.item(b+(cc>=6?4:3)).contents=sec.entries[ei].a||"";
                    }}catch(e){{}}
                    filled++;
                }}

                // 미사용 행 삭제
                var lastRi=sec.entries.length+1;
                for(var r=tbl.rows.length-1;r>=lastRi;r--)
                    try{{tbl.rows[r].remove();}}catch(e){{}}
            }}
        }}

        // 미사용 행 삭제 (세로형)
        if(isSero){{
            // 사용된 테이블의 미사용 행 삭제
            for(var k in usedTableIndices){{
                var ki=parseInt(k);
                if(ki<tables.length&&lastUsedRow[ki]){{
                    var tbl7=tables[ki];
                    var cutRow=lastUsedRow[ki];
                    for(var rr=tbl7.rows.length-1;rr>=cutRow;rr--)
                        try{{tbl7.rows[rr].remove();}}catch(e){{}}
                }}
            }}
            // 미사용 테이블의 데이터 행 전부 삭제
            for(var tti=0;tti<tables.length;tti++){{
                if(!usedTableIndices[tti]){{
                    var tbl8=tables[tti];
                    for(var rr=tbl8.rows.length-1;rr>=1;rr--)
                        try{{tbl8.rows[rr].remove();}}catch(e){{}}
                }}
            }}
        }}

        // 페이지 정리: 사용된 테이블 + 스레드 체인만 보존
        var keepPages={{}};
        for(var k in usedTableIndices){{
            var idx=parseInt(k);
            if(idx<tableTFs.length){{
                keepPages[tablePages[idx].id]=true;
                var cur=tableTFs[idx];
                while(cur.nextTextFrame){{cur=cur.nextTextFrame;try{{keepPages[cur.parentPage.id]=true;}}catch(e){{}}}}
                cur=tableTFs[idx];
                while(cur.previousTextFrame){{cur=cur.previousTextFrame;try{{keepPages[cur.parentPage.id]=true;}}catch(e){{}}}}
            }}
        }}
        // 미사용 테이블 페이지만 삭제 (스레드 체인 연속 페이지는 보존)
        for(var i=doc.pages.length-1;i>=0;i--){{
            if(!keepPages[doc.pages[i].id]&&doc.pages.length>1)
                try{{doc.pages[i].remove();}}catch(e){{}}
        }}

        // 프레임 확장 + autoGrow(세로형만)
        for(var i=0;i<doc.pages.length;i++){{
            for(var j=0;j<doc.pages[i].textFrames.length;j++){{
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0||tf.previousTextFrame){{
                    var gb=tf.geometricBounds;
                    var pgB=doc.pages[i].bounds;
                    var margin=doc.pages[i].marginPreferences;
                    var maxBot=pgB[2]-margin.bottom;
                    if(gb[2]<maxBot) tf.geometricBounds=[gb[0],gb[1],maxBot,gb[3]];
                }}
                if(isSero&&tf.tables.length>0){{
                    var tbl4=tf.tables[0];
                    for(var r=1;r<tbl4.rows.length;r++)
                        try{{tbl4.rows[r].autoGrow=true;}}catch(e){{}}
                }}
            }}
        }}

        // 셀 오버플로우 폰트 축소
        for(var i=0;i<doc.pages.length;i++){{
            for(var j=0;j<doc.pages[i].textFrames.length;j++){{
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0){{
                    var tbl5=tf.tables[0];var cc5=tbl5.columns.length;
                    for(var r=1;r<tbl5.rows.length;r++)
                        for(var c=0;c<cc5;c++){{
                            try{{
                                var cell=tbl5.cells.item(r*cc5+c);
                                if(cell.overflows&&cell.texts[0].characters.length>0){{
                                    var sz=cell.texts[0].characters[0].pointSize;
                                    for(;sz>=4&&cell.overflows;sz-=0.5)
                                        cell.texts[0].characters.everyItem().pointSize=sz;
                                }}
                            }}catch(e){{}}
                        }}
                }}
            }}
        }}

        filled;
    ''', timeout=600)

    _log(log, log_lines, f"채우기: {result}/{total}")

    # 빈 연속 페이지 정리: 사용된 테이블의 빈 스레드 체인 프레임을 역순 제거
    # (메인 JSX 외부에서 별도 실행하여 Object is invalid 방지)
    if is_sero:
        _jsx(app, '''
            var doc=app.activeDocument;
            // 테이블이 있는 텍스트 프레임 수집
            var tblFrames=[];
            for(var i=0;i<doc.pages.length;i++)
                for(var j=0;j<doc.pages[i].textFrames.length;j++)
                    if(doc.pages[i].textFrames[j].tables.length>0)
                        tblFrames.push(doc.pages[i].textFrames[j]);
            // 각 테이블 프레임에서 빈 연속 프레임 역순 제거
            for(var t=0;t<tblFrames.length;t++){
                var tf=tblFrames[t];
                for(var pass=0;pass<200;pass++){
                    if(!tf.nextTextFrame) break;
                    // 스토리가 오버플로우 안 하면 마지막 연속 프레임 불필요
                    if(tf.parentStory.overflows) break;
                    var last=tf;
                    while(last.nextTextFrame) last=last.nextTextFrame;
                    var pg=null;
                    try{pg=last.parentPage;}catch(e){}
                    try{last.remove();}catch(e){break;}
                    // 프레임 삭제 후 페이지에 다른 프레임이 없으면 페이지도 삭제
                    if(pg&&doc.pages.length>1){
                        try{
                            if(pg.textFrames.length===0) pg.remove();
                        }catch(e){}
                    }
                }
                // 삭제 후 오버플로우 발생하면 연속 페이지 1개 추가
                if(tf.parentStory.overflows){
                    try{
                        var lastTf=tf;
                        while(lastTf.nextTextFrame) lastTf=lastTf.nextTextFrame;
                        var np=doc.pages.add(LocationOptions.AFTER,lastTf.parentPage);
                        var masterA=null;
                        for(var mi=0;mi<doc.masterSpreads.length;mi++)
                            if(doc.masterSpreads[mi].name.charAt(0)==="A"){masterA=doc.masterSpreads[mi];break;}
                        if(masterA) np.appliedMaster=masterA;
                        var gb=lastTf.geometricBounds;
                        var m=np.marginPreferences;var b=np.bounds;
                        var nf=np.textFrames.add();
                        nf.geometricBounds=[m.top,gb[1],b[2]-m.bottom,gb[3]];
                        lastTf.nextTextFrame=nf;
                    }catch(e){}
                }
            }
        ''', timeout=300)
        _log(log, log_lines, "빈 페이지 정리 완료")

    # PDF
    pdf_name = os.path.basename(job["indd_path"]).replace(".indd", ".pdf")
    _jsx(app, f'''
        var doc=app.activeDocument;
        doc.exportFile(ExportFormat.PDF_TYPE,
            new File(Folder.temp.fsName+"/hanyoung_{eng}.pdf"));
    ''', timeout=120)
    _log(log, log_lines, f"PDF: 성공 ({pdf_name})")

    # 저장 (결과는 닫지 않고 열어 둠 — 결과 즉시 확인용)
    _jsx(app, f'''
        var doc=app.activeDocument;
        doc.save(new File(Folder.temp.fsName+"/hanyoung_{eng}.indd"));
        app.scriptPreferences.userInteractionLevel=UserInteractionLevels.INTERACT_WITH_ALL;
    ''', timeout=60)

    # 결과 파일 복사
    import tempfile as _tmp
    search = [_tmp.gettempdir(), os.environ.get("TMPDIR", "").rstrip("/"), "/tmp", "/private/tmp"]
    final_pdf = settings_path.replace(".settings.json", pdf_name)
    for d in search:
        if not d:
            continue
        src = os.path.join(d, f"hanyoung_{eng}.pdf")
        if os.path.exists(src):
            shutil.copy2(src, final_pdf)
            _log(log, log_lines, f"PDF 복사: {pdf_name}")
            break
    for d in search:
        if not d:
            continue
        src = os.path.join(d, f"hanyoung_{eng}.indd")
        if os.path.exists(src):
            shutil.copy2(src, job["indd_path"])
            break


def _run_job(app, job, settings_path, log, log_lines):
    with open(job["json_path"], encoding="utf-8") as f:
        content = json.load(f)

    layout = content.get("layout", "?")
    is_sero = layout == "세로형"
    chapters = content.get("chapters", [])
    total = content.get("total_entries", 0)
    _log(log, log_lines, f"\n--- {layout} ---")

    # 모든 레이아웃: 단일 JSX로 전체 처리 (AppleScript 호출 최소화)
    return _run_single_jsx(app, job, content, is_sero, settings_path, log, log_lines)
    _log(log, log_lines, f"단원: {len(chapters)} | 단어: {total}")

    # 영문 경로에 복사
    import shutil
    eng = "sero" if is_sero else "garo"
    tmp_indd = f"/tmp/hanyoung_{eng}.indd"
    shutil.copy2(job["indd_path"], tmp_indd)

    # Step 1: 열기
    _jsx(app, 'app.scriptPreferences.userInteractionLevel=UserInteractionLevels.NEVER_INTERACT;')
    _jsx(app, f'app.open(File("{tmp_indd}"));', timeout=120)
    _log(log, log_lines, "문서 열기 완료")

    # Step 2: 표 정보
    info = _jsx(app, '''
        var doc=app.activeDocument;
        var r=[];
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++)
                if(doc.pages[i].textFrames[j].tables.length>0)
                    r.push(doc.pages[i].textFrames[j].tables[0].rows.length-1);
        r.join(",");
    ''')
    table_rows = [int(x) for x in info.split(",") if x]
    col_count = 6 if not is_sero else 5
    last_col = 4 if col_count >= 6 else 3

    # 표준 행 높이 캡처
    std_h = _jsx(app, '''
        var doc=app.activeDocument;
        var tbl=null;
        for(var i=0;i<doc.pages.length&&!tbl;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++)
                if(doc.pages[i].textFrames[j].tables.length>0){
                    tbl=doc.pages[i].textFrames[j].tables[0]; break;
                }
        tbl&&tbl.rows.length>1 ? tbl.rows[1].height : 7;
    ''')
    try:
        std_height = float(std_h)
    except (ValueError, TypeError):
        std_height = 7.0
    _log(log, log_lines, f"표: {len(table_rows)} | 열: {col_count} | 행높이: {std_height}")

    # Step 3: 전체 초기화 건너뜀 — 데이터 채우기에서 직접 덮어씀
    _log(log, log_lines, "초기화 건너뜀 (덮어쓰기 방식)")

    # Step 3a: 기존 섹션 마커 초기화 (원본 템플릿의 잔여 마커 제거)
    _jsx(app, '''
        var doc=app.activeDocument;
        while(doc.sections.length>1)
            try{doc.sections[doc.sections.length-1].remove();}catch(e){break;}
        doc.sections[0].marker="";
    ''')

    # Step 3b: 용량 체크 — 단원 분리 후 표가 부족하면 페이지 추가
    # 단원별로 표를 배정하고 부족한 행 수 계산
    needed_extra = 0
    ti_sim = 0
    ri_sim = 1
    sim_first = True
    for ci, ch in enumerate(chapters):
        for si, sec in enumerate(ch.get("sections", [])):
            if is_sero:
                # 세로형: 테이블 꽉 차면 다음 테이블
                if ti_sim < len(table_rows) and ri_sim > table_rows[ti_sim]:
                    ti_sim += 1
                    ri_sim = 1
                # 세로형: 단원 변경 → 다음 표
                if ci > 0 and si == 0 and ri_sim > 1:
                    ti_sim += 1
                    ri_sim = 1
            else:
                # 가로형: 각 섹션마다 새 테이블
                if not sim_first:
                    ti_sim += 1
                    ri_sim = 1
            sim_first = False
            for _ in range(sec["count"]):
                if is_sero and ti_sim < len(table_rows) and ri_sim > table_rows[ti_sim]:
                    ti_sim += 1
                    ri_sim = 1
                if ti_sim >= len(table_rows):
                    needed_extra += 1
                ri_sim += 1

    if needed_extra > 0:
        # 마지막 표의 행 수를 기준으로 추가 페이지 수 계산
        last_rows = table_rows[-1] if table_rows else 40
        pages_needed = (needed_extra + last_rows - 1) // last_rows
        _log(log, log_lines, f"표 부족: {needed_extra}행 → {pages_needed}페이지 추가")

        for _ in range(pages_needed):
            _jsx(app, f'''
                var doc=app.activeDocument;
                var lastTF=null;
                for(var i=doc.pages.length-1;i>=0&&!lastTF;i--)
                    for(var j=0;j<doc.pages[i].textFrames.length;j++)
                        if(doc.pages[i].textFrames[j].tables.length>0){{lastTF=doc.pages[i].textFrames[j];break;}}
                if(lastTF){{
                    var np=doc.pages.add(LocationOptions.AT_END);
                    var masterA=null;
                    for(var mi=0;mi<doc.masterSpreads.length;mi++)
                        if(doc.masterSpreads[mi].name.charAt(0)==="A") masterA=doc.masterSpreads[mi];
                    if(masterA) np.appliedMaster=masterA;
                    var dup=lastTF.duplicate();
                    dup.move(np);
                    dup.geometricBounds=lastTF.geometricBounds;
                    var tbl=dup.tables[0];
                    var cc=tbl.columns.length;
                    for(var r=1;r<tbl.rows.length;r++)
                        for(var c=0;c<cc-1;c++)
                            try{{tbl.cells.item(r*cc+c).contents="";}}catch(e){{}}
                }}
            ''', timeout=60)

        # 표 정보 재수집
        info = _jsx(app, '''
            var doc=app.activeDocument;
            var r=[];
            for(var i=0;i<doc.pages.length;i++)
                for(var j=0;j<doc.pages[i].textFrames.length;j++)
                    if(doc.pages[i].textFrames[j].tables.length>0)
                        r.push(doc.pages[i].textFrames[j].tables[0].rows.length-1);
            r.join(",");
        ''')
        table_rows = [int(x) for x in info.split(",") if x]
        _log(log, log_lines, f"표 재수집: {len(table_rows)}개")

    # Step 4: 데이터 채우기
    col_w, col_m = 0, 1
    col_d = 2 if col_count >= 6 else -1
    col_s = 3 if col_count >= 6 else 2
    col_a = 4 if col_count >= 6 else 3

    table_idx = 0
    row_idx = 1
    filled = 0
    is_first = True
    current_ch = None
    CHUNK = 50
    table_used_rows = {}  # {table_idx: last_row_idx}

    for ch in chapters:
        ch_name = ch["name"]
        ch_safe = ch_name.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        _log(log, log_lines, f"{ch_name} ({ch['total']}개)")

        for sec in ch.get("sections", []):
            sec_name = sec["name"]
            sec_safe = sec_name.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

            if is_sero:
                # 세로형: 테이블이 꽉 차면 다음 테이블로
                if table_idx < len(table_rows) and row_idx > table_rows[table_idx]:
                    table_idx += 1
                    row_idx = 1
                # 세로형: 단원 변경 → 다음 표로 이동
                if ch_name != current_ch and current_ch is not None and row_idx > 1:
                    table_idx += 1
                    row_idx = 1
            else:
                # 가로형: 각 섹션마다 새 테이블 (JSX가 경계를 넘지 않으므로 단순 인크리먼트)
                if not is_first:
                    table_idx += 1
                    row_idx = 1
            is_first = False

            if table_idx >= len(table_rows):
                _log(log, log_lines, "  [경고] 표 부족!")
                break

            # 단원 변경 → I-마스터 적용 (세로형) + 단원 텍스트 프레임 입력
            if ch_name != current_ch:
                current_ch = ch_name

                # 세로형: 단원 시작 페이지에 I-마스터 적용
                if is_sero:
                    _jsx(app, f'''
                        var doc=app.activeDocument; var idx=0;
                        for(var i=0;i<doc.pages.length;i++)
                            for(var j=0;j<doc.pages[i].textFrames.length;j++)
                                if(doc.pages[i].textFrames[j].tables.length>0){{
                                    if(idx=={table_idx}){{
                                        var masterI=null;
                                        for(var mi=0;mi<doc.masterSpreads.length;mi++)
                                            if(doc.masterSpreads[mi].name.charAt(0)==="I")
                                                masterI=doc.masterSpreads[mi];
                                        if(masterI) try{{doc.pages[i].appliedMaster=masterI;}}catch(e){{}}
                                    }}
                                    idx++;
                                }}
                    ''')

                # 단원 텍스트 프레임에 단원명 입력 + "단원" 문자스타일
                # 텍스트 프레임이 없으면 첫 번째 표 페이지의 텍스트 프레임을 복사해서 생성
                _jsx(app, f'''
                    var doc=app.activeDocument; var idx=0;
                    for(var i=0;i<doc.pages.length;i++)
                        for(var j=0;j<doc.pages[i].textFrames.length;j++)
                            if(doc.pages[i].textFrames[j].tables.length>0){{
                                if(idx=={table_idx}){{
                                    var pg=doc.pages[i];
                                    var found=false;
                                    for(var k=0;k<pg.textFrames.length;k++){{
                                        if(pg.textFrames[k].tables.length===0){{
                                            pg.textFrames[k].contents="{ch_safe}";
                                            var cs=null;
                                            try{{cs=doc.characterStyles.itemByName("단원");cs.name;}}catch(e){{cs=null;}}
                                            if(cs) for(var ci=0;ci<pg.textFrames[k].characters.length;ci++)
                                                pg.textFrames[k].characters[ci].appliedCharacterStyle=cs;
                                            found=true; break;
                                        }}
                                    }}
                                    if(!found){{
                                        var srcTf=null;
                                        for(var pi=0;pi<doc.pages.length;pi++)
                                            for(var pj=0;pj<doc.pages[pi].textFrames.length;pj++)
                                                if(doc.pages[pi].textFrames[pj].tables.length===0 && doc.pages[pi].textFrames[pj].contents.length>0){{
                                                    srcTf=doc.pages[pi].textFrames[pj]; break;
                                                }}
                                        if(!srcTf)
                                            for(var pi=0;pi<doc.pages.length;pi++)
                                                for(var pj=0;pj<doc.pages[pi].textFrames.length;pj++)
                                                    if(doc.pages[pi].textFrames[pj].tables.length===0){{
                                                        srcTf=doc.pages[pi].textFrames[pj]; break;
                                                    }}
                                        if(srcTf){{
                                            var dup=srcTf.duplicate();
                                            dup.move(pg);
                                            dup.geometricBounds=srcTf.geometricBounds;
                                            dup.contents="{ch_safe}";
                                            var cs=null;
                                            try{{cs=doc.characterStyles.itemByName("단원");cs.name;}}catch(e){{cs=null;}}
                                            if(cs) for(var ci=0;ci<dup.characters.length;ci++)
                                                dup.characters[ci].appliedCharacterStyle=cs;
                                        }}
                                    }}
                                }}
                                idx++;
                            }}
                ''')
                _log(log, log_lines, f"  [단원] {ch_name}")

            # 섹션 표시자 — 이미 섹션이 있는 페이지는 덮어쓰지 않음
            _jsx(app, f'''
                var doc=app.activeDocument;
                var idx=0;
                for(var i=0;i<doc.pages.length;i++)
                    for(var j=0;j<doc.pages[i].textFrames.length;j++)
                        if(doc.pages[i].textFrames[j].tables.length>0){{
                            if(idx=={table_idx}){{
                                var pg=doc.pages[i];
                                // 이미 이 페이지에 섹션이 있는지 확인
                                var exists=false;
                                for(var k=0;k<doc.sections.length;k++)
                                    if(doc.sections[k].pageStart===pg&&doc.sections[k].marker!==""){{exists=true;break;}}
                                if(!exists){{
                                    try{{
                                        var ns=doc.sections.add(pg);
                                        ns.marker="{sec_safe}";
                                        ns.continueNumbering=true;
                                    }}catch(e){{
                                        for(var k2=0;k2<doc.sections.length;k2++)
                                            if(doc.sections[k2].pageStart===pg){{
                                                doc.sections[k2].marker="{sec_safe}";
                                                break;
                                            }}
                                    }}
                                }}
                            }}
                            idx++;
                        }}
            ''')

            _log(log, log_lines, f"  [{sec_name}] {sec['count']}개 (t{table_idx})")

            # 데이터 채우기 (50개씩)
            entries = sec.get("entries", [])
            for cs_idx in range(0, len(entries), CHUNK):
                chunk = entries[cs_idx:cs_idx + CHUNK]
                chunk_file = f"/tmp/_stp_data_{_jsx_counter[0]}.json"
                with open(chunk_file, "w", encoding="utf-8") as cf:
                    json.dump([{
                        "w": e.get("word", ""),
                        "m": e.get("meaning", ""),
                        "s": e.get("synonym", ""),
                        "a": e.get("antonym", ""),
                        "d": e.get("definition", ""),
                    } for e in chunk], cf, ensure_ascii=False)

                # 가로형: 한 섹션은 하나의 테이블에만 채움 (경계 넘김 방지)
                max_ti_js = "tables.length" if is_sero else str(table_idx + 1)
                result = _jsx(app, f'''
                    var doc=app.activeDocument;
                    var cf=new File("{chunk_file}");
                    cf.encoding="UTF-8";cf.open("r");
                    var data=eval("("+cf.read()+")");
                    cf.close();
                    var tables=[];
                    for(var i=0;i<doc.pages.length;i++)
                        for(var j=0;j<doc.pages[i].textFrames.length;j++)
                            if(doc.pages[i].textFrames[j].tables.length>0)
                                tables.push(doc.pages[i].textFrames[j].tables[0]);
                    var ti={table_idx},ri={row_idx},cc=tables[0].columns.length;
                    var maxTi={max_ti_js};
                    var pages=[];
                    for(var pi=0;pi<doc.pages.length;pi++)
                        for(var pj=0;pj<doc.pages[pi].textFrames.length;pj++)
                            if(doc.pages[pi].textFrames[pj].tables.length>0)
                                pages.push(doc.pages[pi]);
                    var skipped=0;
                    for(var i=0;i<data.length;i++){{
                        if(ti>=tables.length){{skipped=data.length-i;break;}}
                        var tbl=tables[ti];
                        if(ri>=tbl.rows.length){{
                            if(ti+1>=maxTi){{
                                // 가로형: 현재 테이블에 행 추가 / 세로형: 마지막 테이블에 행 추가
                                try{{tbl.rows.add();}}catch(e){{skipped=data.length-i;break;}}
                            }}else{{
                                // 세로형: 다음 테이블로 이동
                                ti++;ri=1;
                                if(ti>=tables.length){{skipped=data.length-i;break;}}
                                tbl=tables[ti];
                                if(ti<pages.length){{
                                    try{{var ns=doc.sections.add(pages[ti]);ns.marker="{sec_safe}";ns.continueNumbering=true;}}catch(e){{
                                        for(var sk2=0;sk2<doc.sections.length;sk2++)
                                            if(doc.sections[sk2].pageStart===pages[ti]){{doc.sections[sk2].marker="{sec_safe}";break;}}
                                    }}
                                }}
                            }}
                        }}
                        var b=ri*cc;
                        try{{
                            tbl.cells.item(b+{col_w}).contents=data[i].w||"";
                            tbl.cells.item(b+{col_m}).contents=data[i].m||"";
                            {"tbl.cells.item(b+"+str(col_d)+").contents=data[i].d||'';" if col_d >= 0 else ""}
                            tbl.cells.item(b+{col_s}).contents=data[i].s||"";
                            tbl.cells.item(b+{col_a}).contents=data[i].a||"";
                        }}catch(e){{}}
                        ri++;
                    }}
                    ti+"|"+ri+"|"+skipped+"|tbl="+tables.length+"_r="+(ti<tables.length?tables[ti].rows.length:"?");
                ''', timeout=60)

                if "|" in result:
                    p = result.split("|")
                    new_ti = int(p[0])
                    new_ri = int(p[1])
                    skipped_str = p[2] if len(p) > 2 else "0"
                    skipped = int(skipped_str.split("|")[0]) if skipped_str else 0
                    debug_info = p[3] if len(p) > 3 else ""
                    # 테이블이 넘어갔으면, 이전 테이블들은 완전 사용으로 표시
                    # (삭제할 행 없음 → last_ri = table_rows[t]+1)
                    for t in range(table_idx, new_ti):
                        if t < len(table_rows):
                            table_used_rows[t] = table_rows[t] + 1
                    table_idx = new_ti
                    row_idx = new_ri
                    table_used_rows[table_idx] = max(table_used_rows.get(table_idx, 0), row_idx)
                    if skipped > 0:
                        _log(log, log_lines, f"    [경고] 행 부족 → {skipped}개 미배치 (ti={new_ti} ri={new_ri} {debug_info})")
                filled += len(chunk)

    _log(log, log_lines, f"채우기: {filled}/{total}")
    _log(log, log_lines, f"사용 행: {table_used_rows} | 표 행수: {table_rows}")



    # Step 4a-2: 제거됨 — 원본 템플릿을 매번 새로 복사하므로 clearOverrides 불필요
    # (clearOverrides가 앵커 객체를 파괴하는 부작용이 있었음)

    # Step 4b: 제거됨 — 섹션 마커 정리가 3강 등 유효 섹션을 잘못 삭제하는 문제
    # 빈 페이지 삭제 시 섹션도 자동 정리됨

    # Step 4c: 미사용 행 삭제 (단일 JSX로 모든 테이블 한 번에 처리)
    _log(log, log_lines, "미사용 행 정리 중...")
    used_rows_json = json.dumps({str(k): v for k, v in table_used_rows.items()})
    _jsx(app, f'''
        var doc=app.activeDocument;
        var usedRows={used_rows_json};
        var idx=0;
        for(var i=0;i<doc.pages.length;i++){{
            for(var j=0;j<doc.pages[i].textFrames.length;j++){{
                if(doc.pages[i].textFrames[j].tables.length>0){{
                    var key=""+idx;
                    if(usedRows[key]!==undefined){{
                        var lastRi=usedRows[key];
                        var tbl=doc.pages[i].textFrames[j].tables[0];
                        if(lastRi<tbl.rows.length){{
                            for(var r=tbl.rows.length-1;r>=lastRi;r--)
                                try{{tbl.rows[r].remove();}}catch(e){{}}
                        }}
                    }}
                    idx++;
                }}
            }}
        }}
    ''', timeout=300)
    _log(log, log_lines, "미사용 행 정리 완료")

    # Step 4d: autoGrow 설정 (원본 행 높이 유지, 오버플로우 셀만 자동 확장)
    _jsx(app, '''
        var doc=app.activeDocument;
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++){
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0){
                    var tbl=tf.tables[0];
                    for(var r=1;r<tbl.rows.length;r++)
                        try{tbl.rows[r].autoGrow=true;}catch(e){}
                }
            }
    ''', timeout=120)
    _log(log, log_lines, "autoGrow 설정")

    # Step 5: 빈 페이지 삭제 — 사용된 테이블 + 스레드 체인 보존
    used_indices = sorted(table_used_rows.keys())
    used_json = json.dumps(used_indices)
    _jsx(app, f'''
        var doc=app.activeDocument;
        var used={used_json};
        // 테이블 인덱스 → 텍스트 프레임 매핑
        var tblFrames=[];
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++)
                if(doc.pages[i].textFrames[j].tables.length>0)
                    tblFrames.push(doc.pages[i].textFrames[j]);
        // 보존할 페이지 번호 수집
        var keepPages={{}};
        for(var u=0;u<used.length;u++){{
            if(used[u]<tblFrames.length){{
                var tf=tblFrames[used[u]];
                // 이 프레임의 페이지 유지
                try{{
                    var pgIdx=-1;
                    for(var pi=0;pi<doc.pages.length;pi++)
                        if(doc.pages[pi]===tf.parentPage){{pgIdx=pi;break;}}
                    if(pgIdx>=0) keepPages[pgIdx]=true;
                }}catch(e){{}}
                // 스레드 체인의 모든 페이지 유지 (다중 페이지 테이블)
                var cur=tf;
                while(cur.nextTextFrame){{
                    cur=cur.nextTextFrame;
                    try{{
                        for(var pi=0;pi<doc.pages.length;pi++)
                            if(doc.pages[pi]===cur.parentPage){{keepPages[pi]=true;break;}}
                    }}catch(e){{}}
                }}
            }}
        }}
        // 사용되지 않은 페이지 삭제 (뒤→앞)
        for(var i=doc.pages.length-1;i>=1;i--){{
            if(!keepPages[i])
                try{{doc.pages[i].remove();}}catch(e){{}}
        }}
    ''', timeout=60)
    _log(log, log_lines, "빈 페이지 정리 완료")

    # Step 5b: 잔여 템플릿 테이블 제거
    # 스레드 연속 페이지에 남아있는 원본 템플릿의 미사용 테이블 프레임 삭제
    _jsx(app, f'''
        var doc=app.activeDocument;
        var used={used_json};
        // 사용된 테이블 프레임 목록 수집
        var allTblFrames=[];
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++)
                if(doc.pages[i].textFrames[j].tables.length>0)
                    allTblFrames.push(doc.pages[i].textFrames[j]);
        // 사용된 인덱스의 프레임 + 스레드 체인 프레임 수집
        var keepFrames={{}};
        for(var u=0;u<used.length;u++){{
            if(used[u]<allTblFrames.length){{
                keepFrames[allTblFrames[used[u]].id]=true;
                var cur=allTblFrames[used[u]];
                while(cur.nextTextFrame){{
                    cur=cur.nextTextFrame;
                    keepFrames[cur.id]=true;
                }}
            }}
        }}
        // 미사용 테이블 프레임 삭제 (뒤→앞)
        for(var i=allTblFrames.length-1;i>=0;i--){{
            if(!keepFrames[allTblFrames[i].id])
                try{{allTblFrames[i].remove();}}catch(e){{}}
        }}
    ''', timeout=60)
    _log(log, log_lines, "잔여 테이블 제거 완료")

    # Step 6: 프레임 오버플로우 해결 (autoGrow로 커진 테이블 대응)
    # 1) 마지막 프레임 확장
    # 2) 여전히 넘치면 연속 페이지 추가 + 스레드 연결 (최대 50회)
    _jsx(app, '''
        var doc=app.activeDocument;
        for(var i=0;i<doc.pages.length;i++){
            for(var j=0;j<doc.pages[i].textFrames.length;j++){
                var tf=doc.pages[i].textFrames[j];
                if(!tf.nextTextFrame && tf.parentStory.overflows){
                    var gb=tf.geometricBounds;
                    var pgB=doc.pages[i].bounds;
                    var margin=doc.pages[i].marginPreferences;
                    var maxBot=pgB[2]-margin.bottom;
                    if(maxBot<=gb[2]) maxBot=pgB[2]-3;
                    if(gb[2]<maxBot){
                        gb[2]=maxBot;
                        tf.geometricBounds=gb;
                    }
                }
            }
        }
        for(var pass2=0;pass2<50;pass2++){
            var anyOv=false;
            for(var i=doc.pages.length-1;i>=0;i--){
                for(var j=0;j<doc.pages[i].textFrames.length;j++){
                    var tf=doc.pages[i].textFrames[j];
                    if(!tf.nextTextFrame && tf.parentStory.overflows){
                        anyOv=true;
                        var newPg=doc.pages.add(LocationOptions.AFTER,doc.pages[i]);
                        try{newPg.appliedMaster=doc.pages[i].appliedMaster;}catch(e2){}
                        var gb=tf.geometricBounds;
                        var pgB=newPg.bounds;
                        var margin=newPg.marginPreferences;
                        var newTf=newPg.textFrames.add();
                        newTf.geometricBounds=[margin.top,gb[1],pgB[2]-margin.bottom,gb[3]];
                        tf.nextTextFrame=newTf;
                        break;
                    }
                }
                if(anyOv) break;
            }
            if(!anyOv) break;
        }
    ''', timeout=300)

    # Step 7: 잔여 셀 오버플로우 — 폰트 축소로 강제 해소 (헤더 행 제외)
    _jsx(app, '''
        var doc=app.activeDocument;
        for(var i=0;i<doc.pages.length;i++){
            for(var j=0;j<doc.pages[i].textFrames.length;j++){
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0){
                    var tbl=tf.tables[0];
                    var cc=tbl.columns.length;
                    for(var r=1;r<tbl.rows.length;r++){
                        for(var c=0;c<cc;c++){
                            try{
                                var cell=tbl.cells.item(r*cc+c);
                                if(cell.overflows && cell.texts[0].characters.length>0){
                                    var origSize=cell.texts[0].characters[0].pointSize;
                                    for(var sz=origSize-0.5;sz>=4&&cell.overflows;sz-=0.5)
                                        cell.texts[0].characters.everyItem().pointSize=sz;
                                }
                            }catch(e){}
                        }
                    }
                }
            }
        }
    ''', timeout=300)
    _log(log, log_lines, "셀 폰트 축소 완료")

    ov = _jsx(app, '''
        var doc=app.activeDocument;var ov=0;
        for(var i=0;i<doc.stories.length;i++) if(doc.stories[i].overflows) ov++;
        ov;
    ''')
    # 셀 레벨 오버플로우 체크
    cell_ov = _jsx(app, '''
        var doc=app.activeDocument;var cnt=0;
        for(var i=0;i<doc.pages.length;i++)
            for(var j=0;j<doc.pages[i].textFrames.length;j++){
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0){
                    var tbl=tf.tables[0];
                    for(var r=0;r<tbl.rows.length;r++)
                        for(var c=0;c<tbl.columns.length;c++)
                            try{if(tbl.cells.item(r*tbl.columns.length+c).overflows) cnt++;}catch(e){}
                }
            }
        cnt;
    ''', timeout=120)
    _log(log, log_lines, f"오버플로우: 프레임={ov} 셀={cell_ov}")

    # Step 7b: 최종 빈 페이지 정리 — 데이터 없는 테이블이 있는 페이지 삭제
    _jsx(app, '''
        var doc=app.activeDocument;
        // 뒤에서 앞으로 순회하며 데이터 없는 페이지 삭제
        for(var i=doc.pages.length-1;i>=0;i--){
            var pg=doc.pages[i];
            var hasData=false;
            for(var j=0;j<pg.textFrames.length;j++){
                var tf=pg.textFrames[j];
                if(tf.tables.length>0){
                    var tbl=tf.tables[0];
                    var cc=tbl.columns.length;
                    // 데이터 행(row 1+)에 내용이 있는지 확인
                    for(var r=1;r<tbl.rows.length&&!hasData;r++){
                        for(var c=0;c<cc-1;c++){
                            try{
                                if(tbl.cells.item(r*cc+c).contents!==""){hasData=true;break;}
                            }catch(e){}
                        }
                    }
                } else if(tf.contents.length>0){
                    hasData=true;
                }
            }
            // 데이터 없는 페이지 삭제 (마지막 1페이지는 보존)
            if(!hasData && doc.pages.length>1)
                try{pg.remove();}catch(e){}
        }
    ''', timeout=60)
    _log(log, log_lines, "최종 빈 페이지 정리 완료")

    # Step 7c: 프레임 오버플로우 최종 해소 — 프레임 확장 → 연속 페이지 (필요 시)
    # 1단계: 모든 테이블 프레임을 페이지 마진까지 확장
    try:
        _jsx(app, '''
        var doc=app.activeDocument;
        for(var i=0;i<doc.pages.length;i++){
            for(var j=0;j<doc.pages[i].textFrames.length;j++){
                var tf=doc.pages[i].textFrames[j];
                if(tf.tables.length>0){
                    var gb=tf.geometricBounds;
                    var pgB=doc.pages[i].bounds;
                    var margin=doc.pages[i].marginPreferences;
                    var maxBot=pgB[2]-margin.bottom;
                    if(gb[2]<maxBot) tf.geometricBounds=[gb[0],gb[1],maxBot,gb[3]];
                }
            }
        }
    ''', timeout=60)
    except Exception:
        _log(log, log_lines, "프레임 확장 실패 — 건너뜀")
    # 2단계: 여전히 오버플로우면 연속 페이지 생성 (세로형 대형 표 전용)
    try:
        ov_check = _jsx(app, '''
            var doc=app.activeDocument;var ov=0;
            for(var i=0;i<doc.stories.length;i++) if(doc.stories[i].overflows) ov++;
            ov;
        ''')
        if int(ov_check or 0) > 0:
            _jsx(app, '''
            var doc=app.activeDocument;
            var masterA=null;
            for(var mi=0;mi<doc.masterSpreads.length;mi++)
                if(doc.masterSpreads[mi].name.charAt(0)==="A"){masterA=doc.masterSpreads[mi];break;}
            for(var i=0;i<doc.pages.length;i++){
                for(var j=0;j<doc.pages[i].textFrames.length;j++){
                    var tf=doc.pages[i].textFrames[j];
                    if(tf.tables.length>0&&tf.parentStory.overflows){
                        var gb=tf.geometricBounds;
                        var pgB=doc.pages[i].bounds;
                        var margin=doc.pages[i].marginPreferences;
                        var maxBot=pgB[2]-margin.bottom;
                        var curTf=tf;
                        for(var pass2=0;pass2<50&&curTf.parentStory.overflows;pass2++){
                            var np=doc.pages.add(LocationOptions.AFTER,curTf.parentPage);
                            if(masterA) try{np.appliedMaster=masterA;}catch(e2){}
                            var npM=np.marginPreferences;var npB=np.bounds;
                            var newTf=np.textFrames.add();
                            newTf.geometricBounds=[npM.top,gb[1],npB[2]-npM.bottom,gb[3]];
                            curTf.nextTextFrame=newTf;
                            curTf=newTf;
                        }
                    }
                }
            }
            ''', timeout=300)
    except Exception:
        _log(log, log_lines, "연속 페이지 생성 실패 — 건너뜀")
    _log(log, log_lines, "프레임 오버플로우 최종 해소")

    # Step 8: PDF
    pdf_name = os.path.basename(job["indd_path"]).replace(".indd", ".pdf")

    _jsx(app, f'''
        var doc=app.activeDocument;
        doc.exportFile(ExportFormat.PDF_TYPE,
            new File(Folder.temp.fsName+"/hanyoung_{eng}.pdf"));
    ''', timeout=120)
    _log(log, log_lines, f"PDF: 성공 ({pdf_name})")

    # Step 9: 저장 + 닫기
    _jsx(app, f'''
        var doc=app.activeDocument;
        doc.save(new File(Folder.temp.fsName+"/hanyoung_{eng}.indd"));
        doc.close(SaveOptions.NO);
        app.scriptPreferences.userInteractionLevel=UserInteractionLevels.INTERACT_WITH_ALL;
    ''', timeout=60)

    # 결과 파일 복사
    import shutil as _sh
    import tempfile as _tmp
    search = [_tmp.gettempdir(), os.environ.get("TMPDIR", "").rstrip("/"), "/tmp", "/private/tmp"]
    final_pdf = settings_path.replace(".settings.json", pdf_name)
    for d in search:
        if not d:
            continue
        src = os.path.join(d, f"hanyoung_{eng}.pdf")
        if os.path.exists(src):
            _sh.copy2(src, final_pdf)
            _log(log, log_lines, f"PDF 복사: {pdf_name}")
            break
    for d in search:
        if not d:
            continue
        src = os.path.join(d, f"hanyoung_{eng}.indd")
        if os.path.exists(src):
            _sh.copy2(src, job["indd_path"])
            break


def _log(cb, lines, msg):
    cb(msg)
    lines.append(msg)
