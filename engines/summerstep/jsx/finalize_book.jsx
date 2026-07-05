#target "indesign"
// finalize_book.jsx — 조판 후 구조 마감 자동화 (문서 실제 레이아웃에서 값 도출).
// 대상: 목차 페이지동기화 + 기출 간지 챕터목록 + 정답 헤더 relabel + 목차 GREP.
// 성덕/특정 학교 값 하드코딩 없음 — 전부 문서에서 읽음. 이미 맞으면 무변경(idempotent).
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

function main(){
  var doc=app.activeDocument; var log="[finalize] "+doc.name+"\n";

  function getCS(n){var a=doc.allCharacterStyles;for(var i=0;i<a.length;i++)if(a[i].name==n)return a[i];return null;}
  function pageNum(pg){ return pg?parseInt(pg.name,10):-1; }

  // ---- 1) 문서 스캔: 챕터CS 타이틀 -> 페이지들, 특수 타이틀 페이지 ----
  var chapMap={};          // 정규화 타이틀텍스트 -> 최소 페이지번호 (내용 챕터)
  var titlePages={};       // 특정 타이틀(정답지/Pre-study 등) -> 최소 페이지번호
  function norm(s){ return String(s).replace(/[\r\n\t]/g,' ').replace(/\s+/g,' ').replace(/^\s+|\s+$/g,''); }
  function noteTitle(map,key,pn){ if(!(key in map)||pn<map[key]) map[key]=pn; }
  for(var pi=0;pi<doc.pages.length;pi++){ var pg=doc.pages[pi]; var pn=pageNum(pg);
    for(var f=0;f<pg.textFrames.length;f++){ var tf=pg.textFrames[f];
      var raw=""; try{raw=String(tf.contents);}catch(e){continue;}
      var c=norm(raw); if(c.length<1) continue;
      var cs0=null; try{cs0=tf.parentStory.characters[0].appliedCharacterStyle;}catch(e){}
      var psn0=""; try{psn0=tf.parentStory.paragraphs[0].appliedParagraphStyle.name;}catch(e){}
      if(cs0&&cs0.name=="챕터"&&c.length<=28) noteTitle(chapMap,c,pn);
      if(psn0.indexOf("Pre_타이틀")>=0) noteTitle(titlePages,"PRESTUDY",pn); // 단락스타일로만(목차 텍스트 오인방지)
      if(c=="정답지") noteTitle(titlePages,"JEONGDAP",pn);
    }
  }

  // 내용 챕터명 -> 페이지 (공백정규화 + prefix/포함 매칭, 최소페이지)
  function findChapterPage(name){
    name=norm(name); if(!name) return -1; var best=-1;
    for(var k in chapMap){ // k는 이미 정규화됨
      if(k==name || k.indexOf(name+" ")==0){ if(best<0||chapMap[k]<best) best=chapMap[k]; }
    }
    return best;
  }

  // ---- 2) 목차 프레임 찾기 + 파싱 ----
  function getPS(n){var a=doc.allParagraphStyles;for(var i=0;i<a.length;i++)if(a[i].name==n)return a[i];return null;}
  // 목차는 보통 앞쪽 몇 페이지. 목차_파트/목차_항목 단락이 있는 프레임 대상.
  var tocParas=[];  // {para, kind:'item'|'part', label, curPageNum}
  for(var pi=0;pi<Math.min(6,doc.pages.length);pi++){ var pg=doc.pages[pi];
    for(var f=0;f<pg.textFrames.length;f++){ var st=pg.textFrames[f].parentStory; var pars=st.paragraphs;
      for(var q=0;q<pars.length;q++){ var psn=pars[q].appliedParagraphStyle.name;
        if(psn=="목차_항목"||psn=="목차_파트"){ tocParas.push({para:pars[q],psn:psn}); }
      }
    }
  }
  log+="목차 단락 "+tocParas.length+"개, 내용챕터 "+(function(){var n=0;for(var k in chapMap)n++;return n;})()+"개\n";

  // 파트 라벨 -> divider 페이지 도출
  // 규칙: 자식챕터 있는 파트=첫자식-2, Pre-study="Pre-study"타이틀-2, 정답="정답지"-2
  function setTrailingNum(para,newnum){ var t=String(para.contents); var m=t.match(/(\d+)\s*[\r\n]?$/); if(!m) return false;
    var num=m[1]; if(num==String(newnum)) return "same"; var idx=t.lastIndexOf(num);
    try{ para.characters.itemByRange(idx, idx+num.length-1).contents=String(newnum); return true; }catch(e){ return false; } }
  function itemName(t){ var m=t.match(/Chapter\s*\d+\s+([\s\S]+?)\s*\t\s*\d+\s*[\r\n]?$/); return m?m[1].replace(/^\s+|\s+$/g,''):null; }

  var changed=0, same=0, skip=0;
  function applyNum(e,page,tag){ var r=setTrailingNum(e.para,page);
    if(r===true){changed++; log+="  "+tag+" -> "+page+"\n";} else if(r=="same")same++; else skip++; }
  // PASS 1: 목차_항목 (자식 페이지 먼저 확정)
  for(var i=0;i<tocParas.length;i++){ var e=tocParas[i]; if(e.psn!="목차_항목") continue;
    var nm=itemName(String(e.para.contents)); if(!nm){ skip++; continue; }
    var pg=findChapterPage(nm);
    if(pg<0){ log+="  ⚠항목 미매칭: \""+nm+"\"\n"; skip++; continue; }
    e._page=pg; applyNum(e,pg,"항목 '"+nm+"'");
  }
  // PASS 2: 목차_파트 (Pre-study/정답=타이틀-2, PART=첫자식-2)
  for(var i=0;i<tocParas.length;i++){ var e=tocParas[i]; if(e.psn!="목차_파트") continue;
    var lbl=norm(e.para.contents); if(!/[가-힣A-Za-z]/.test(lbl)){ continue; } // 빈 단락 스킵
    var page=-1;
    if(/Pre-study/.test(lbl)){ if(titlePages["PRESTUDY"]) page=titlePages["PRESTUDY"]-2; }
    else if(/정답/.test(lbl)){ if(titlePages["JEONGDAP"]) page=titlePages["JEONGDAP"]-2; }
    else { for(var j=i+1;j<tocParas.length;j++){ if(tocParas[j].psn=="목차_파트")break;
             if(tocParas[j].psn=="목차_항목" && tocParas[j]._page>0){ page=tocParas[j]._page-2; break; } } }
    if(page>0) applyNum(e,page,"파트 '"+lbl.substring(0,18)+"'");
    else { log+="  ⚠파트 페이지 미도출: \""+lbl.substring(0,24)+"\"\n"; skip++; }
  }
  log+="목차 동기화: 변경 "+changed+", 이미맞음 "+same+", 스킵 "+skip+"\n";

  // ---- 2.5) 기출 파트: 배너로 실제 기출 챕터 도출 -> 기출 간지 + 기출 TOC 재생성 ----
  // 기출 유형 어휘집(파서 KNOWN과 동일, 공백 포함형). 독해 챕터(대의파악 등, 무공백)와 구분됨.
  var GT={"대의 파악":1,"세부 내용 파악":1,"함축 의미 추론":1,"어법":1,"어휘":1,"빈칸 추론":1,"무관한 문장":1,"글의 순서":1,"순서 배열":1,"순서":1,"문장 삽입":1,"요약문":1,"지칭 추론":1,"장문":1,"복합":1,"서술형 영작":1,"서술형 요약문, 빈칸":1,"서술형 우리말":1,"서술형 어법":1};
  // 독해 챕터 최대 페이지(기출 시작 경계) + 정답 divider 페이지(기출 끝 경계)
  var dokMax=0; for(var i=0;i<tocParas.length;i++){ if(tocParas[i].psn=="목차_항목" && tocParas[i]._page>dokMax && tocParas[i]._isGichul!==true){ /*설정 후*/ } }
  var jeongPage=(titlePages["JEONGDAP"]||99999);
  // 기출 배너 목록: chapMap 중 GT에 속하고 페이지 정답 전
  var gichul=[]; for(var k in chapMap){ if(GT[k] && chapMap[k]<jeongPage) gichul.push({name:k,page:chapMap[k]}); }
  gichul.sort(function(a,b){return a.page-b.page;});
  // 독해 챕터 페이지들(무공백형)을 제외하기 위해: GT형(공백)만 담겼으므로 독해와 자동분리됨.
  // 단, "어법"/"어휘"가 어법파트 divider와 겹칠 수 있어 페이지가 독해max보다 큰 것만.
  var dokPages=[]; for(var i=0;i<tocParas.length;i++){ var e=tocParas[i]; if(e.psn=="목차_항목"&&e._page>0){ var nm=itemName(String(e.para.contents)); if(nm&&/파악$|추론$|배열$|삽입$/.test(nm)&&nm.indexOf(" ")<0) dokPages.push(e._page); } }
  var dokEnd=0; for(var i=0;i<dokPages.length;i++) if(dokPages[i]>dokEnd) dokEnd=dokPages[i];
  var g2=[]; for(var i=0;i<gichul.length;i++){ if(gichul[i].page>dokEnd) g2.push(gichul[i]); } gichul=g2;
  log+="기출 챕터 감지 "+gichul.length+"개";
  if(gichul.length){ log+=" (첫 "+gichul[0].name+" p"+gichul[0].page+")\n";
    var gichulDivider=gichul[0].page-2; // 기출 간지 = 첫 기출챕터 -2

    // (A) 기출 간지 챕터목록 재구성(라인 추가/삭제 포함): 6+챕터 목록프레임(독해간지 4개와 구분)
    var listFrame=null;
    for(var m=0;m<doc.masterSpreads.length && !listFrame;m++){ var ms=doc.masterSpreads[m];
      for(var mp=0;mp<ms.pages.length && !listFrame;mp++){ var mpg=ms.pages[mp];
        for(var mf=0;mf<mpg.textFrames.length;mf++){ var mc=String(mpg.textFrames[mf].contents);
          var cn=(mc.match(/Chapter\s*\d+/g)||[]).length; if(cn>=6){ listFrame=mpg.textFrames[mf]; break; } } } }
    if(listFrame){ var lst=listFrame.parentStory; var csB=getCS("개념_bold(or)")||getCS("개념_bold"), csT=getCS("개념_제목");
      function chapParas(){ var a=[],p=lst.paragraphs; for(var i=0;i<p.length;i++) if(/Chapter\s*\d+/.test(String(p[i].contents))) a.push(i); return a; }
      var idx=chapParas();
      // 초과 라인 제거
      for(var i=idx.length-1;i>=gichul.length;i--){ try{ lst.paragraphs[idx[i]].remove(); }catch(e){} }
      idx=chapParas();
      // 부족 라인 추가(마지막 챕터라인 복제 형식)
      while(idx.length<gichul.length){ var last=lst.paragraphs[idx[idx.length-1]];
        var lt=String(last.contents).replace(/[\r\n]+$/,'');
        last.insertionPoints[-1].contents="\r"+lt; // 형식복제(줄바꿈+동일 텍스트)
        idx=chapParas(); }
      // 각 라인 번호(개념_bold)+이름(개념_제목) 세팅
      idx=chapParas();
      for(var ci=0;ci<gichul.length;ci++){ var para=lst.paragraphs[idx[ci]]; var t=String(para.contents);
        var nn=(ci+1<10?"0":"")+(ci+1);
        // 번호: "Chapter \d+" -> "Chapter NN" + 개념_bold 적용
        var mC=t.indexOf("Chapter");
        if(mC>=0){ var after=t.substring(mC+8); var dm=after.match(/^\s*(\d+)/);
          if(dm){ var ds=mC+8+after.indexOf(dm[1]); try{ para.characters.itemByRange(ds, ds+dm[1].length-1).contents=nn; }catch(e){}
            if(csB){ try{ para.characters.itemByRange(mC, mC+7+1+nn.length-1).appliedCharacterStyle=csB; }catch(e){} } } }
        // 이름: 마지막 탭 뒤 + 개념_제목 적용
        t=String(para.contents); var lastTab=t.lastIndexOf("\t"); if(lastTab<0)continue;
        var chs=para.characters; var end=chs.length; var lastCh=String(chs[end-1].contents); var stop=(lastCh=="\r"||lastCh=="\n")?end-2:end-1;
        try{ para.characters.itemByRange(lastTab+1,stop).contents=gichul[ci].name; }catch(e){}
        if(csT){ try{ para.characters.itemByRange(lastTab, stop).appliedCharacterStyle=csT; }catch(e){} }
      }
      log+="기출 간지 챕터목록 재구성 "+gichul.length+"개\n";
      // 기본값(12pt/24leading) 리셋 후, 넘치면 프레임높이÷챕터수로 fit(폰트도 축소=긴이름 wrap방지). 결정론적·idempotent.
      var lp=lst.paragraphs; for(var i=0;i<lp.length;i++){ try{ lp[i].pointSize=12; lp[i].leading=24; }catch(e){} }
      if(listFrame.overflows){ var gb=listFrame.geometricBounds; var hPt=(gb[2]-gb[0])*2.834646;
        var fit=Math.floor((hPt-6)/gichul.length); if(fit<11)fit=11; if(fit>24)fit=24;
        var fpt=Math.floor(fit*0.58); if(fpt<9)fpt=9; if(fpt>12)fpt=12;
        for(var i=0;i<lp.length;i++){ try{ lp[i].pointSize=fpt; lp[i].leading=fit; }catch(e){} }
        log+="  간지 오버플로우 -> pt="+fpt+"/leading="+fit+"(프레임맞춤)\n";
      }
    }

    // (B) 기출 TOC 항목 재생성: 기출 파트 뒤 목차_항목 삭제 -> 정답 파트 앞에 실제 기출챕터 일괄삽입
    var ps_item2=getPS("목차_항목");
    var gPart=null, jPart=null;
    for(var i=0;i<tocParas.length;i++){ if(tocParas[i].psn=="목차_파트"){ var lab=norm(tocParas[i].para.contents);
      if(/기출/.test(lab)) gPart=tocParas[i].para; else if(/정답/.test(lab)) jPart=tocParas[i].para; } }
    if(gPart){ var story=gPart.parentStory;
      setTrailingNum(gPart, gichulDivider); // 기출 파트 페이지 = 기출 divider
      // 기출 파트와 정답 파트 사이 목차_항목 삭제
      var pars=story.paragraphs; var gi=-1,ji=-1;
      for(var i=0;i<pars.length;i++){ var nm3=pars[i].appliedParagraphStyle.name; var lb=norm(pars[i].contents);
        if(nm3=="목차_파트"&&/기출/.test(lb)) gi=i; if(nm3=="목차_파트"&&/정답/.test(lb)&&ji<0&&i>gi&&gi>=0) ji=i; }
      var end=(ji>=0?ji:pars.length);
      for(var i=end-1;i>gi;i--){ if(pars[i].appliedParagraphStyle.name=="목차_항목"){ try{pars[i].remove();}catch(e){} } }
      // 삽입 지점: 정답 파트가 있으면 그 앞, 없으면 스토리 끝
      var block=""; for(var ci=0;ci<gichul.length;ci++){ var nn=(ci+1<10?"0":"")+(ci+1);
        block+="\tChapter "+nn+"  "+gichul[ci].name+"\t"+gichul[ci].page+"\r"; }
      // 재조회 후 삽입
      pars=story.paragraphs; var jp=null;
      for(var i=0;i<pars.length;i++){ if(pars[i].appliedParagraphStyle.name=="목차_파트"&&/정답/.test(norm(pars[i].contents))){ jp=pars[i]; break; } }
      var startCount=story.paragraphs.length;
      if(jp){ jp.insertionPoints[0].contents=block; }
      else { story.insertionPoints[-1].contents="\r"+block.replace(/\r$/,""); }
      // 새로 생긴 목차_항목 단락에 스타일 적용
      pars=story.paragraphs; var gi2=-1;
      for(var i=0;i<pars.length;i++){ if(pars[i].appliedParagraphStyle.name=="목차_파트"&&/기출/.test(norm(pars[i].contents))){ gi2=i; break; } }
      var applied=0;
      for(var i=gi2+1;i<pars.length && applied<gichul.length;i++){ var lb2=norm(pars[i].contents);
        if(/^Chapter\s*\d+/.test(lb2)){ try{ pars[i].appliedParagraphStyle=ps_item2; applied++; }catch(e){} } }
      log+="기출 TOC 항목 재생성 "+gichul.length+"개 (PART03 p"+gichulDivider+")\n";
    }
  } else log+=" (기출 없음)\n";

  // ---- 2.7) 정답 '유닛' 챕터 헤더 relabel: TOC 챕터 항목(정답순)을 소스로 (있을때만, 카운트일치시만) ----
  var csU=getCS("유닛");
  if(csU){
    app.findGrepPreferences=NothingEnum.NOTHING; app.findGrepPreferences.appliedCharacterStyle=csU; app.findGrepPreferences.findWhat="Chapter[^\\r]{0,3}";
    var uf=doc.findGrep(); app.findGrepPreferences=NothingEnum.NOTHING;
    // TOC 챕터 시퀀스(문서순) = 목차_항목들의 (번호,이름). 정답 유닛 헤더도 같은 순서.
    var seq=[];
    for(var i=0;i<tocParas.length;i++){ if(tocParas[i].psn!="목차_항목")continue; var tt=String(tocParas[i].para.contents);
      var mm=tt.match(/Chapter\s*(\d+)\s+([\s\S]+?)\s*\t\s*\d+\s*[\r\n]?$/); if(mm) seq.push({num:mm[1],name:norm(mm[2])}); }
    if(uf.length>0 && uf.length==seq.length){
      for(var i=uf.length-1;i>=0;i--){ var para=uf[i].paragraphs[0]; var rr=para.textStyleRanges; var numRun=null,nameRun=null;
        for(var r=0;r<rr.length;r++){ var t=String(rr[r].contents);
          if(rr[r].appliedCharacterStyle.name=="유닛" && t.indexOf("Chapter")>=0) numRun=rr[r];
          else if(numRun && !nameRun && /[가-힣(]/.test(t)) nameRun=rr[r]; }
        if(nameRun) nameRun.contents=seq[i].name;
        if(numRun) numRun.contents=String(numRun.contents).replace(/\d+/, seq[i].num);
      }
      log+="정답 유닛 헤더 relabel "+uf.length+"개 (TOC순)\n";
    } else if(uf.length>0) log+="정답 유닛 헤더 "+uf.length+"개 vs TOC챕터 "+seq.length+"개 불일치 — 스킵\n";
  }

  // ---- 3) 목차_항목 GREP: Chapter \d+ 보장 ----
  var ps_item=getPS("목차_항목");
  if(ps_item){ var ng=ps_item.nestedGrepStyles; for(var g=0;g<ng.length;g++){
    if(ng[g].grepExpression.indexOf("Chapter 01")>=0 && ng[g].grepExpression.indexOf("|")>=0){ ng[g].grepExpression="Chapter \\d+"; log+="목차_항목 GREP -> 'Chapter \\d+'\n"; } } }

  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
  return log;
}
try{ main(); }catch(e){ "ERR "+e.toString()+" @"+e.line; }
