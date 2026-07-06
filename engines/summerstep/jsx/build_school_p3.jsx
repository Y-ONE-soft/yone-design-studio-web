#target "indesign"
// PART3 기출 2-frame: 1 problem/frame (top/bottom), auto-number, 유형 page-break.
// 유형 banner = E/M masters (mint) + 챕터-styled title (running header). Overflow = leading->12, font->8, else fullpage.
#include "p3data_active.jsx"
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
function main(){
  var doc=app.activeDocument; if(!doc) return "NO DOC";
  var out="";
  function getPS(n){var a=doc.allParagraphStyles;for(var i=0;i<a.length;i++)if(a[i].name==n)return a[i];return null;}
  function getCS(n){var a=doc.allCharacterStyles;for(var i=0;i<a.length;i++)if(a[i].name==n)return a[i];return null;}
  function getMaster(p){for(var m=0;m<doc.masterSpreads.length;m++)if(doc.masterSpreads[m].namePrefix==p)return doc.masterSpreads[m];return null;}
  var NONE=getCS("[없음]"), CS_CH=getCS("챕터");
  // ensure red char style
  var CS_RED=getCS("기출_빨강"); if(!CS_RED){ CS_RED=doc.characterStyles.add({name:"기출_빨강"});
    var red=doc.swatches.itemByName("C=15 M=100 Y=100 K=0"); if(!red.isValid) red=doc.colors.add({name:"기출빨강색",model:ColorModel.PROCESS,colorValue:[0,100,100,0]});
    try{ CS_RED.fillColor=red; }catch(e){} }
  var PS={ passage:getPS("박스 지문"), choice:getPS("선지"), bogi:getPS("보기"), jogeon:getPS("조건") };
  // 주어진 글/문장(순서·삽입) 구분용: "박스 지문 사본" (박스 지문 복제 + 옅은 회색 배경)
  var PS_GIVEN=getPS("박스 지문 사본");
  if(!PS_GIVEN && PS.passage){ try{ PS_GIVEN=PS.passage.duplicate(); PS_GIVEN.name="박스 지문 사본";
      var gsw=doc.swatches.itemByName("C=0 M=1 Y=6 K=7"); if(!gsw.isValid) gsw=doc.swatches.itemByName("c9m4y16k0");
      if(gsw.isValid){ PS_GIVEN.paragraphShadingOn=true; PS_GIVEN.paragraphShadingColor=gsw; }
    }catch(e){ out+="givenStyle:"+e+"; "; PS_GIVEN=PS.passage; } }
  if(!PS_GIVEN) PS_GIVEN=PS.passage;
  var mE=getMaster("E"), mR=getMaster("R"), mM=getMaster("M"), mD=getMaster("D");
  // remove jumbled "PART." banner frame from E master (banner top-left, not footer)
  for(var mp=0;mp<mE.pages.length;mp++){ var mpg=mE.pages[mp]; var mfs=mpg.textFrames;
    for(var f=mfs.length-1;f>=0;f--){ try{ var gb=mfs[f].geometricBounds; var c=String(mfs[f].contents);
      if(gb[0]<25 && c.indexOf("PART.")>=0){ mfs[f].remove(); } }catch(e){} } }

  // reference 유형-title frame: a 챕터-styled frame on an A-master page (어법 chapter title)
  var refTitle=null, refSide=null;
  for(var pi=0; pi<doc.pages.length && !refTitle; pi++){ var pg=doc.pages[pi]; if(!pg.appliedMaster||pg.appliedMaster.namePrefix!="A") continue;
    for(var f=0;f<pg.textFrames.length;f++){ var tf=pg.textFrames[f]; try{ var c=String(tf.contents); if(c.length>0&&c.length<20){ var cs0=tf.parentStory.characters[0].appliedCharacterStyle; if(cs0&&cs0.name=="챕터"){ refTitle=tf; refSide=pg.side; break; } } }catch(e){} }
  }
  if(!refTitle) out+="WARN no refTitle; ";

  // cleanup old off-trim 유형-title duplicates from previous builds (pasteboard frames whose text is a 유형 name)
  var TYPESET={};
  for(var ti=0;ti<P3DATA.length;ti++){ if(P3DATA[ti].t) TYPESET[P3DATA[ti].t]=1; }
  var cleaned=0;
  for(var sp=0;sp<doc.spreads.length;sp++){ var tfs=doc.spreads[sp].textFrames;
    for(var f=tfs.length-1;f>=0;f--){ try{ if(tfs[f].parentPage==null){ var cc=String(tfs[f].contents).replace(/[\r\n]/g,""); if(TYPESET[cc]){ tfs[f].remove(); cleaned++; } } }catch(e){} } }
  out+="cleanedOldTitles="+cleaned+"; ";

  // numbered list + 발문 style
  var lst; try{ lst=doc.numberingLists.itemByName("기출번호"); if(!lst.isValid) throw 0; }catch(e){ lst=doc.numberingLists.add({name:"기출번호"}); }
  try{ lst.continueNumbersAcrossStories=true; }catch(e){}
  var PS_STEM=getPS("기출_발문");
  if(!PS_STEM){ PS_STEM=doc.paragraphStyles.add({name:"기출_발문"}); try{PS_STEM.basedOn=getPS("실전 문제");}catch(e){} }
  try{ PS_STEM.bulletsAndNumberingListType=ListType.NUMBERED_LIST; PS_STEM.appliedNumberingList=lst; PS_STEM.numberingLevel=1; PS_STEM.numberingContinue=true; PS_STEM.numberingApplyRestartPolicy=false; PS_STEM.numberingStartAt=1; }catch(e){ out+="numErr:"+e+"; "; }
  try{ PS_STEM.pointSize=9; PS_STEM.fontStyle="Medium"; PS_STEM.spaceAfter=3; }catch(e){}

  var nStart=-1,nEnd=-1,kStart=-1;
  for(var pi=0;pi<doc.pages.length;pi++){ var mn=doc.pages[pi].appliedMaster?doc.pages[pi].appliedMaster.namePrefix:"";
    if(mn=="N"){ if(nStart<0)nStart=pi; nEnd=pi; }
    if(mn=="K"&&pi>60&&kStart<0&&nStart>=0) kStart=pi; }
  if(nStart<0||kStart<0) return "BOUNDS FAIL n="+nStart+" k="+kStart;
  function isL(pg){ return pg.side==1818653800; }
  function topGB(pg){ return isL(pg)?[33,26,153,181]:[33,29,153,184]; }
  function botGB(pg){ return isL(pg)?[157,26,277,181]:[157,29,277,184]; }
  function fullGB(pg){ return isL(pg)?[33,26,277,181]:[33,29,277,184]; }
  var W=doc.documentPreferences.pageWidth;

  // delete old 기출 content pages
  for(var pi=kStart-1; pi>nEnd; pi--) doc.pages[pi].remove();
  out+="deleted old, pages="+doc.pages.length+"; ";
  var afterPg=doc.pages[nEnd];
  function addPage(masterObj){ var np=doc.pages.add(LocationOptions.AFTER, afterPg); try{np.appliedMaster=masterObj;}catch(e){} afterPg=np; return np; }

  // place 챕터-styled 유형 title (off-trim running-header source; E/R master shows the banner+number)
  function addTitle(pg, name){ if(!name || name==="") name="기출";
    var isL=(pg.side==1818653800);
    var gb = isL ? [-26,57,0,122] : [-26,29,0,94];
    var fr=pg.textFrames.add(); fr.geometricBounds=gb; fr.contents=name;
    try{ if(CS_CH) fr.parentStory.texts[0].appliedCharacterStyle=CS_CH; }catch(e){ out+="titleTxt:"+e+"; "; }
  }

  function pour(fr, P){
    var st=fr.parentStory;
    function ins(t,cs){ if(t==="")return; var a=st.length; st.insertionPoints[-1].contents=t; var b=st.length; if(b<=a)return;
      var rng=st.characters.itemByRange(a,b-1); try{rng.appliedCharacterStyle=NONE;rng.clearOverrides(OverrideType.CHARACTER_ONLY);}catch(e){}
      if(cs){var c=getCS(cs); if(c){try{rng.appliedCharacterStyle=c;}catch(e){}}} }
    function fmt(f){ if(f.indexOf('u')>=0)return "문제_밑줄"; if(f.indexOf('r')>=0)return "기출_빨강"; if(f.indexOf('b')>=0)return "기출_볼드"; return null; }
    function para(ps,runs){ if(st.length>0) st.insertionPoints[-1].contents="\r"; for(var r=0;r<runs.length;r++) ins(runs[r][0], fmt(runs[r][1]));
      try{ var pp=st.paragraphs[-1]; pp.appliedParagraphStyle=ps; pp.clearOverrides(); }catch(e){} }
    // strip embedded answer marker at end of stem (세종1 format)
    if(P.stem&&P.stem.length){ var _lr=P.stem[P.stem.length-1]; _lr[0]=_lr[0].replace(/\s*[①②③④⑤]\s*$/,""); if(_lr[0]==""&&P.stem.length>1) P.stem.pop(); }
    para(PS_STEM, P.stem);
    var isOI=(P.t=="글의 순서"||P.t=="문장 삽입"); var firstPassageDone=false;
    // collect abc answer blanks; 4 -> 2-column, else 1-column
    var abcList=[]; for(var q=0;q<P.b.length;q++) if(P.b[q].r=="abc") abcList.push(P.b[q]);
    var twoCol=(abcList.length==4); var abcPoured=false;
    // pour answer-blank runs VERBATIM from manuscript (no regeneration). 4 blanks -> 2-column arrangement only.
    function pourAbcRuns(B){ for(var r=0;r<B.x.length;r++) ins(B.x[r][0], fmt(B.x[r][1])); }
    function pourAbc(){
      if(twoCol){
        for(var row=0;row<2;row++){
          if(st.length>0) st.insertionPoints[-1].contents="\r";
          pourAbcRuns(abcList[row*2]);
          st.insertionPoints[-1].contents="\t";
          pourAbcRuns(abcList[row*2+1]);
          try{ var pp=st.paragraphs[-1]; pp.appliedParagraphStyle=PS.choice; pp.texts[0].clearOverrides(OverrideType.CHARACTER_ONLY); pp.tabStops.add({alignment:TabStopAlignment.LEFT_ALIGN, position:78}); }catch(e){}
        }
      } else {
        for(var i=0;i<abcList.length;i++){
          if(st.length>0) st.insertionPoints[-1].contents="\r";
          pourAbcRuns(abcList[i]);
          try{ var pp1=st.paragraphs[-1]; pp1.appliedParagraphStyle=PS.choice; pp1.texts[0].clearOverrides(OverrideType.CHARACTER_ONLY); }catch(e){}
        }
      }
    }
    for(var bi=0;bi<P.b.length;bi++){ var B=P.b[bi];
      if(B.r=="abc"){ if(!abcPoured){ pourAbc(); abcPoured=true; } continue; }
      var pst=PS.passage;
      if(B.r=="choice")pst=PS.choice;
      else if(B.r=="bogi"||B.r=="bogi_h"||B.r=="word_h")pst=PS.bogi;
      else if(B.r=="jogeon"||B.r=="jogeon_h")pst=PS.jogeon;
      else if(B.r=="optline")pst=PS.choice;
      else if(B.r=="mbchoice"||B.r=="mbhead")pst=PS.choice;
      else if(B.r=="passage"){ if(isOI && !firstPassageDone){ pst=PS_GIVEN; firstPassageDone=true; } }
      para(pst, B.x);
      // (A)(B) 빈칸 선지: 마커/A열/…/B열 탭정렬 (para의 clearOverrides 뒤에 탭스톱 추가)
      if(B.r=="mbchoice"||B.r=="mbhead"){ try{ var mp=st.paragraphs[-1]; mp.tabStops.everyItem().remove();
        mp.tabStops.add({alignment:TabStopAlignment.LEFT_ALIGN, position:7});
        mp.tabStops.add({alignment:TabStopAlignment.LEFT_ALIGN, position:28});
        mp.tabStops.add({alignment:TabStopAlignment.LEFT_ALIGN, position:34}); }catch(e){} }
    }
  }
  // 넘침 처리: 자간/간격/폰트 축소(크램) 금지 — 오버라이드("+")·"붙어있음" 방지.
  // 반프레임에 안 맞으면 전체페이지로 승격, 그래도 넘치면 다음 페이지로 스레드. 단락 속성 변경 0.
  var curType=null, page=null, mode="newband"; var totalProblems=0;
  for(var idx=0; idx<P3DATA.length; idx++){ var P=P3DATA[idx]; totalProblems++;
    if(P.t!==curType){ curType=P.t; page=addPage(mM); try{page.appliedMaster=(page.side==1818653800)?mE:mR;}catch(e){} addTitle(page, curType); mode="top"; }
    else if(mode=="newcont"){ page=addPage(mM); mode="top"; }
    var slot=mode;
    var fr=page.textFrames.add(); fr.geometricBounds=(slot=="top")?topGB(page):botGB(page);
    pour(fr,P);
    var fullUsed=false;
    if(fr.overflows){
      // 반프레임에 안 맞음 -> 전체페이지 자연크기로 승격
      if(slot=="bottom"){ page=addPage(mM); try{fr.move(page);}catch(e){} }
      fr.geometricBounds=fullGB(page); fullUsed=true;
      // 전체페이지도 넘치면 다음 전체페이지로 스레드(스레드 프레임, 축소 없음)
      var g=0; while(fr.overflows && g<12){ var np=addPage(mM); var nf=np.textFrames.add(); nf.geometricBounds=fullGB(np); fr.nextTextFrame=nf; fr=nf; g++; }
    }
    if(fullUsed){ mode="newcont"; } else { mode=(slot=="top")?"bottom":"newcont"; }
  }
  // re-add 기출 footer marker on first 기출 content page
  try{ var mkCS=getCS("파트마커C"); var firstFr=doc.pages[nEnd+1].textFrames[0]; var fst=firstFr.parentStory;
    fst.insertionPoints[0].contents="기출\r"; fst.characters.itemByRange(0,1).appliedCharacterStyle=mkCS;
    var mkPS=getPS("파트마커P"); if(mkPS) fst.paragraphs[0].appliedParagraphStyle=mkPS;
  }catch(e){ out+="mkErr:"+e+"; "; }
  out+="poured "+totalProblems+" problems, total pages="+doc.pages.length;
  doc.recompose(); doc.save();
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
  return out;
}
try{ main(); }catch(e){ "ERR "+e.toString()+" @"+e.line; }
