# 썸머스텝(SUMMER STEP) 고1 특강 조판 파이프라인

여름방학 고1 특강 교재 자동조판. 학교별(상일1·명일1·세종1·성덕1…) 공용 파이프라인, **원고만 바꾸면** 아래 수정이 전부 자동 반영된다(성덕/특정학교 하드코딩 없음).

## 책 구조
PRE study(품사/문장성분) → PART1 어법 → PART2 독해 → PART3 기출(학교별) → 정답 및 해설. 각 파트는 간지(divider)로 구분.

## 파이프라인 (실행 순서)
1. **파서**: `parse_p3_json.py <base> <school>` — 원고 hwpx(Part3_원고_*.hwpx) → 문제/유형 구조 추출 → `p3_<school>.json`
   - 의존: `hwpx_paras.py`(중복없는 단락), `hwpx_paras2.py`(표 flatten, 선지표 재구성)
2. **데이터 생성**: `emit_jsx_data.py <base> <school>` → `p3data_<school>.jsx.txt` (var P3DATA)
   - 정답 데이터: `ansdata_<school>.json` = ans_<school>.json + p3_<school>.json 1:1(정렬), 유형은 문제유형에서 매핑 → var ANSWERS
3. **PART3 빌더**: `jsx/build_school_p3.jsx` (app.activeDocument 대상, p3data_active.jsx include) — 기출 문제 조판(E/R/M 마스터, 유형배너, 2프레임)
4. **정답 빌더**: `jsx/build_school_answer.jsx` (answerdata_active.jsx include) — 정답 및 해설 조판
5. **마감 자동화**: `jsx/finalize_book.jsx` (app.activeDocument) — 목차/간지/헤더를 **문서 실제 레이아웃에서 읽어** 동기화. idempotent(재실행 안전).

문서 활성화는 `jsx/activate.jsx` (activate_target.txt에 NFD 파일명조각). ⚠**한글 파일명은 NFD** — `printf '%s' "학교_썸머스텝" | iconv -f UTF-8 -t UTF-8-MAC`.

## 자동 반영되는 수정 (2026 세션에서 확립)

### A. 파서 (parse_p3_json.py) — 원고 구조 인식
- `expand_glued`: 발문+지문이 한 단락에 접착된 경우(len>240으로 발문 미인식) 런 서식 보존하며 분리
- `norm_glyphs`: 사제폰트 PUA 정규화 — 발문앞 딩벳(F0E8)제거·요약화살표(F0EA)→↓·제시문마커(F02B1/2)→①②
- `is_type_header` KNOWN: 세부 내용 파악/지칭 추론/순서 등 유형헤더 인식(평문·빨강 무관)
- `merge_multiblank_choices`: (A)(B) 빈칸 선지(표 flatten으로 쪼개진 "①while/…/whereas")를 마커\tA\t…\tB 한 줄로 병합

### B. PART3 빌더 (build_school_p3.jsx)
- fitFrame 크램 제거: 넘치면 축소말고 전체페이지 승격+스레드(→ "+"오버라이드·박스 붙음 방지). para()에 clearOverrides()
- mbchoice/mbhead 탭정렬(7·28·34mm), abc답란 clearOverrides(CHARACTER_ONLY)
- addTitle: 유형시작 배너=유형명(첫 배너 "기출 문제" 아님)

### C. 정답 빌더 (build_school_answer.jsx)
- brk()+setPS(): 내용 삽입 후 단락스타일 적용(유형헤더/정답줄/해설 밀림 방지)
- 실전문제 해설 스타일: 자동번호 NO_LIST + 번호 1%-squish nested GREP(`^\d+?\)`) 제거 → "N) 정답" 정상표시

### D. 마감 (finalize_book.jsx) — 문서 레이아웃에서 도출, 하드코딩 없음
- **목차 페이지 동기화**: 각 목차_항목=챕터명으로 실제 챕터CS 타이틀 페이지 매칭(공백정규화·prefix). 각 목차_파트=Pre-study/정답=타이틀-2, PART=첫자식-2
- **기출 TOC 재생성**: 문서의 기출 배너(유형 어휘집 GT와 매칭, 독해챕터 뒤·정답 앞)를 페이지순 열거 → PART03 아래 "Chapter NN 유형" 실제 페이지로 재작성(개수 무관). PART03 페이지=기출 divider
- **기출 간지 챕터목록**: 6+챕터 목록 마스터프레임 있으면(상일1식) 기출 유형으로 갱신
- **정답 유닛 헤더 relabel**: 유닛스타일 "Chapter" 헤더 있고 TOC챕터수와 일치시, TOC순서로 relabel
- **목차_항목 GREP**: `Chapter 01|02|03|04` → `Chapter \d+` (챕터 5+ 파랑볼드)

## 함정
- 활성문서 확인 필수(같은 "학교_썸머스텝"이 여러 파일; list docs로). 파일명 NFD.
- InDesign `para.contents=문자열`(뒤 \r없이) 설정→다음 단락 병합. 단락 재구성은 정답파트앞 일괄삽입 or 삭제후 append.
- CS.horizontalScale 읽으면 미설정시 garbage반환 — char레벨 실측.
- 학교별 차이: 상일1(수정)=E/R/M 기출간지+챕터목록+정답 유닛헤더(유저 커스텀). 성덕1=기출 없음(106p). 세종1=기출 14유형.
