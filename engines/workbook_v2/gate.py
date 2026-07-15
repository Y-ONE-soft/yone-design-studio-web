"""워크북 v2 완제품 검수 게이트 (W11 — job 06f4b2c2 결함 6건의 자동 검출).

기준은 '조판사가 납품하는 완제품'이다 — 파싱 결과가 아니라 출력물 자체를
검사한다 (파서가 틀리면 게이트도 같이 틀리는 순환 금지):
  G1 [헤더잔존]   지문번호 헤더 원문이 출력 본문에 인쇄됨 (critical)
  G2 [정답잔존]   '정답' 블록/정답표 행이 출력에 인쇄됨 (critical)
  G3 [지문번호]   독립 지문번호 프레임이 원고 지문번호와 불일치
                  (passage_numbers op 사용 시 critical, 아니면 warning)
  G4 [잔여페이지] 원고에 없는 스텝/남는 사이클 페이지 잔존
                  (page_cleanup op 사용 시 critical, 아니면 warning)
  G5 [상하반전]   step2_a1(상단)과 step2_a1_btm(하단)의 기하 배치 반전
                  (step_map pos 힌트 사용 시 critical, 아니면 warning)
  G6 [헤더미인식] 원고(콘텐츠 단락)에 구조적 헤더 후보가 있는데 인식기가
                  하나도 못 잡음 — 파싱 계층 경고 (순환 측정 방지)
  G7 [빈플랜]     렌더 유닛이 0 — 업로드 원고가 어느 스텝에도 매핑되지
                  않았는데 조판이 '성공'으로 끝나는 침묵 유실 (critical, W12)
  G8 [구분선잔존] 원전 교재의 챕터/유닛 구분선("Chapter 03. ..." /
                  "Unit 10 긴 어구 빈칸")이 출력 본문에 인쇄됨 (critical, W12)
  G9 [미사용원고] 업로드/원고 폴더의 원고 파일이 어느 스텝에도 소비되지
                  않고 조용히 무시됨 (W13 c15 실증: "…STEP 2_박소원
                  완료.hwpx" 통합 원고 3종 침묵 무시). 정답/답지/해설
                  파일과 '정답지 짝' 파일은 의도된 미사용이라 stats로만
                  보고, 그 외는 warning (G7 전량 유실의 부분 유실 보완).
  G10 [특수문자]  hwp 사용자 영역(PUA) 문자가 출력에 인쇄됨 — InDesign
                  폰트에 글리프가 없어 tofu(빈 네모)로 찍힌다 (W14 c05/c06
                  실증: 요약 화살표 ⇩가 /\U000f0036으로 인코딩).
                  PUA 단독 단락은 critical, 본문 내 혼입은 warning.
  G10 확장 (W20): 인쇄 매핑 테이블(plan.PUA_PRINT_TABLE — 겹따옴표
                  U+F0852/F0853, 요약 화살표 U+F0036/F003B/F0EA) 등재
                  코드가 본문 혼입으로 잔존하면 critical — 현행 플랜은
                  이 코드들을 정자로 치환하므로 잔존 = 매핑 미적용
                  출력(구출력 소급 검출: c06 W14 최종 출력의 U+F0852/
                  F0853 혼입 2건). 미등재 코드 혼입은 warning 유지
                  (근거 없는 치환 금지 — U+F09F/F000/F081~F085 잠복).
  G11 [마커오염/마커스타일] 변형문제 출처 마커("[NHN_..._변형]")에 원문자
                  접두가 붙어 인쇄(파서 선지 오염) 또는 같은 마커가 복수
                  스타일로 인쇄(kind 오분류 — 발문/선지 스타일로 찍힘).
                  둘 다 critical (W15 c04 실증: 183개 중 9개 비일관 + 오염 1).
  G12 [문장삽입배경] 출처 마커가 있는 스토리에서 문장삽입 발문 뒤 배경
                  (주어진 문장 박스) 미부여 — warning (W15 c04 실증 12건).
  G13 [발문스타일] 발문 시그니처 단락([서술형 N] 접두 태그, 또는 발문
                  시작 신호 + 시오/세요-체 종결)이 발문 계열 스타일이
                  아닌 스타일로 인쇄됨 — critical (W16 c07 실증:
                  "[서술형 2] … 쓰세요." 해요체 발문이 지문 스타일).
  G14 [영단어오분류] 영단어 스타일 단락이 실제 어휘 항목("word: 한글 뜻")
                  이 아님 — 한글 뜻이 없거나 콜론 앞 머리가 1글자(대화문
                  화자 라벨 "A:"/"Minji:") — critical (W16 c10 실증 6건 +
                  c04/80dd3fa2 잠복. v1 실물: 이런 행은 전부 지문 스타일).
  G15 [조건항목]  <조건> 블록 안의 강신호 조건 항목(불릿 시작 또는
                  한글 + '것' 종결, 답란 이전)이 조건 스타일이 아닌
                  스타일로 인쇄됨 — critical (W16 c10 실증 3블록 +
                  c04/c05/0a5da924 잠복).
  G16 [스텝원고미사용] 미사용 원고(G9 suspicious) 중 파일명 콘텐츠 토큰이
                  현행 스텝이 소화 가능한 종류(문장배열/영작배열/실전문제
                  등)인 파일 — 부분 침묵 유실의 강신호라 critical 승격
                  (W17 c11 실증: 구6스텝 폴더의 Step4 빈칸내용/Step5
                  영작배열/Step6 실전문제 3종 침묵 미사용). 대응 스텝이
                  없는 종류(교과서 계열의 어법수정 등)는 G9 warning 유지.
  G17 [워터마크잔존] 원고 선두의 학원 워터마크(URL 단독 라인, 무단도용/
                  무단전재/불법복제 경고 라인)가 출력에 인쇄됨 — critical
                  (W17 c16 실증: cafe.naver URL + "※ 본 자료는 무단도용
                  … 금합니다"가 지문 스타일로 인쇄).
  G18 [유형마커스타일] 문제 유형 구분 마커("[ Type A ]"류 단독 대괄호
                  라인)가 복수 스타일로 인쇄됨 — kind 오분류 (W17 c16
                  실증: [ Type C (2) ]만 Box 전파로 보기 스타일). critical.
  G19 [어법수정혼입] step3(실전문제) 스토리에 어법수정 원고 시그니처
                  (N[영단어] 괄호 표기)가 다량 인쇄됨 — 구6스텝
                  'Step3 어법수정' 파일명이 실전문제로 오라우팅된 상태
                  (W17 c11 실증: 6지문 45개 표기). critical.
  G20 [선두잔재]  스토리 선두 콘텐츠 단락이 날짜-only 라인("17. 11. 23") —
                  원고 표제 블록의 작업 날짜 메모가 표제 제거를 비껴가
                  본문 첫 단락으로 인쇄됨 (W18 c18 실증: 문항 번호 보호
                  규칙(숫자+점 시작)이 날짜를 문항 번호로 오인 보호). critical.
  G13 확장 (W18): 발문 시작 신호가 없어도 꼬리 [출처/태그] + 시오/세요-체
                  종결이면 발문 시그니처 ("영어로 번역하세요 [9강 1번]"이
                  지문 스타일로 인쇄된 c18 실증 + 세로 e79f8af9 기출력의
                  "11. (주관식) … 고르세요. [정답 2개]" 잠복 검출).
  G21 [원문자중복] ①로 시작하면서 본문에 ①이 다시 등장하는 장문(200자+)
                  단락 — 선지 자동번호가 inline 번호 지문(도표/불일치류:
                  선지가 지문 문장에 ①~⑤로 박힘)에 원고에 없는 ①을
                  prepend해 기형 번호('①The graph … ① In Germany …')가
                  인쇄된 오염 (W19 c20 실증: ※ 다중 문항 아이템의 재인쇄
                  지문 + passage_above 우회 경로. 원고에 타이핑된 inline
                  번호 지문은 ①이 1회뿐이라 통과 — c19/0a5da924 실측).
                  critical.
  G22 [간지라벨] 간지의 '고N 모의고사 / YY년 M월' 라벨이 원고(content의
                  grade/year/month)와 불일치 — v1 run.jsx 16.7이 간지를
                  갱신하는데 v2 본가는 divider op 미적용이라 [원본] 템플릿
                  잔재('고2 모의고사 / 26년 3월')가 그대로 납품됐다
                  (W19 c20 실증 + c04/c05/c12/c14/06f4b2c2/세로 계열 등
                  소급 검출 — c05는 고1 25년 10월 책에 고2 26년 3월 간지).
                  '…월 짤지문' 단독 라벨은 v1도 미갱신(실물 잔존)이라 제외.
                  content에 grade/year/month가 없으면 검사 생략.
                  divider op 사용 플랜은 critical, 미사용은 warning
                  (G3/G4 패턴). 세로 실행기도 W20에서 divider op 지원
                  (라벨 내용 정확 매칭 방식 — c17 소급 해소).

  G23 [라벨스타일] 지문번호 라벨 단락([N]/{N})의 인쇄 스타일이 계약
                  (step_map.json label_contract — 플랜 flow.target에 실림)과
                  불일치 — critical (W21 r11 실증: v2가 [N]에 'A_어휘 선택
                  번호'를 입혔으나 v1 실물(워크북03(외부지문))은 [기본 단락]).
  G24 [프레임브레이크] ① 지문 다수 원고가 유닛 1개로 배치(per_passage_units
                  계약 스텝 — 헤더 미인식으로 프레임 분리가 통째로 실패한
                  상태. W21 r11 실증: '1. no.1' 무-p형 헤더 4스텝) ② 유닛
                  시작 단락이 실제 프레임 경계에 있지 않음 (덤프 fc 필드
                  실측 — 신형 덤프 한정). 둘 다 critical.
  G25 [발문빈단락] 발문(하단 문제 스타일) 바로 다음이 빈 단락 — 발문과
                  주어진 문장 사이 불필요한 빈 줄 (W21 r11 실증: C1 발문
                  삽입이 원고 잔여 빈 단락 위에 얹힘. v1 실물은 발문 바로
                  다음이 주어진 문장). critical.
  G26 [섹션마스터] 섹션 시작 페이지의 마스터가 좌/우 변형 계약(step_map
                  master_pair)과 불일치 — 페이지 정리로 시작이 밀렸는데
                  마스터가 그대로 (W21 r11 실증: [원본]워크북_C p13 어휘
                  선택 2 = 우측 시작 B-마스터). section_masters op 사용
                  플랜은 critical, 아니면 warning. 덤프 pages 필드 필요.
  G27 [간지적합] W22 r12 스펙 확정 (사용자 확정 — supp 계열): 간지는
                  업로드 시 입력한 간지 문구, 미입력이면 교재유형만 표기
                  (예: '외부지문'). plan.divider.source(user|type) 계약이
                  있으면 모의고사 라벨 잔재/기대 문구 불일치 = critical.
                  계약 없는 플랜(본가/구출력)은 기존 W21 warning 유지:
                  외부지문(무-p형 'N. no.M') 원고 + '모의고사' 라벨 →
                  사람 확인 지목 (v1 실물도 같은 라벨 유지 관행).
  G4 확장 (W22 r12): 반복 장식(페이지마다 얹히는 발문/섹션 탭)만 남은
                  장식-빈 페이지를 delete 모드 잔여로 합산 — 장식 텍스트가
                  '텍스트 있음'으로 빈 페이지 판정을 비껴가 잔존 (r11
                  재조판 p34 어법선택 발문 / p47 영작배열 탭, 사용자 지목).
  G28 [파트경계] 간지 라벨 페이지가 물리 왼쪽(L) — 페이지 삭제로 파트
                  경계 정렬이 깨졌는데 오른쪽 채움(M 마스터) 페이지 누락.
                  delete 모드의 M 페이지는 간지 직전 오른쪽 채움만 허용
                  (그 외 M 페이지 = 빈 페이지 잔재). delete 모드 critical,
                  아니면 warning (W22 r12 — 사용자 확정 스펙: 파트 경계
                  오른쪽 채움 페이지는 삭제가 아니라 M 마스터 삽입).

G4/G5는 dump_stories.jsx의 W11 확장 필드(stale_pages / pg / b)가 필요하다.
G24②/G26은 W21 확장 필드(fc / pages)가 필요하다. 구버전 덤프에는 경고로만
보고한다 (재덤프 안내). G9는 uploads_dir를 넘긴 경우에만 검사한다 (오프라인
플랜 테스트 호환).
"""
import os
import re
import unicodedata

from core.inspect import find_leaked_answers
from engines.workbook_v2.plan import (PUA_PRINT_TABLE, is_header_line,
                                      is_a1_header, passage_labels,
                                      _norm_header)

_RE_BARE_NUM = re.compile(r"^\d{1,3}(?:\s*~\s*\d{1,3})?$")
# G21 — 원문자 선지 번호 (①~⑮: 지문 inline 번호도 같은 집합)
_CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
# G22 — 모의고사 간지 라벨 ('고N 모의고사' + 'YY년 M월' 연속 2단락)
_RE_DIVIDER_L1 = re.compile(r"^고(\d)\s*모의고사$")
_RE_DIVIDER_L2 = re.compile(r"^(\d{2})년\s*0?(\d{1,2})월$")
_RE_DIGIT = re.compile(r"\d")
_RE_ENG_WORD = re.compile(r"[A-Za-z]+")

# G11 — 변형문제 출처 마커 (출력 검사용 독립 정의 — 파서/플랜과 순환 방지)
_RE_SRC_MARKER = re.compile(r"^\[[^\[\]]{2,}변형\]$")
_RE_SRC_POLLUTED = re.compile(r"^[①-⑤]\[[^\[\]]{2,}변형\]$")
# G12 — 문장삽입 발문 (주어진 문장 배경 박스 기대)
_RE_INSERT_PROMPT = re.compile(r"주어진 문장이 들어가|들어갈 위치|"
                               r"들어가기에 가장 적절한 곳")

# G13 — 발문 시그니처 (출력 검사용 독립 정의 — 플랜 오버레이와 순환 방지)
_RE_HANGUL = re.compile(r"[가-힣]")
_RE_Q_LEAD_TAG = re.compile(r"^\[(?:서술|논술)형\s*\d*\]")
_RE_Q_TRAIL_SRC = re.compile(r"\s*\[[^\[\]]{1,40}\]\s*$")
_RE_Q_START = re.compile(r"^(?:다음|윗\s*글|위\s*글|글의\s*흐름|주어진)")
_RE_Q_END = re.compile(r"(?:시오|세요)\s*[.?!]?\s*$")
# 발문 계열 스타일 시그니처 — "실전 문제 지문"(지문 스타일)과 충돌하지
# 않도록 "하단 문제"/"OX문제"처럼 구체 명칭으로 한정
_Q_STYLE_KEYS = ("번호", "발문", "다음 글을 읽고", "하단 문제", "OX문제")

# G14 — 영단어 스타일 오용 (실제 어휘 항목은 "word: 한글 뜻" — 한글 필수,
# 콜론 앞 머리 2+글자. 1글자 머리는 대화문 화자 라벨 "A:")
_RE_WORD_BAD_HEAD = re.compile(r"^[A-Za-z]\s*[:：]")

# G15 — <조건> 블록 항목 (강신호 한정 — v1 실물 관행: 영어 어구 나열은
# 지문 유지, 시오-체 번호 항목은 발문 유지. 4ed24266/c15 v1 덤프 실증)
_RE_COND_BULLET = re.compile(r"^\s*[•⦁◦∙ㆍ·]")
_RE_COND_GEOT = re.compile(r"것\s*\.?\s*$")
_RE_COND_NUMSTART = re.compile(r"^\s*\d+\s*[.)]")
# 답란 = 밑줄런으로 '끝나는' 줄 한정 — 본문 중간 빈칸 표기("보기의
# [_______]에서 … 할 것"은 조건 항목)와 구분 (c06 실증)
_RE_COND_BLOCK_END = re.compile(r"_{6,}\s*[.,)]?\s*$|^\s*(?:정답|→|우리말)")
_RE_COND_QHINT = re.compile(r"^(?:다음|윗\s*글|위\s*글|글의|밑줄|주어진|"
                            r"\(주관식\)|서술형)")

# G8 — 원전 교재 구분선 (파서 _RE_CHAPTER_DIVIDER/_RE_UNIT_DIVIDER 준용.
# 출력 검사용 독립 정의 — 파서가 틀리면 게이트도 같이 틀리는 순환 방지)
_DIVIDER_PATTERNS = [
    re.compile(r"^Chapter\s+\d+\.\s", re.I),
    re.compile(r"^Unit\s+\d+\s+[가-힣][가-힣0-9\s]{0,30}$"),
]

# G17 — 학원 워터마크 (W17 c16): URL '단독' 라인(본문 속 인용 URL과 구분)
# 또는 무단도용/무단전재 경고 문구 포함 라인. '불법복제'는 어휘 정의
# ("pirate : … 불법 복제하다" — 화이트북 실덤프 실증)와 충돌해 제외.
_RE_WATERMARK_URL = re.compile(r"^(?:https?://\S+|www\.\S+)$")
_RE_WATERMARK_WARN = re.compile(r"무단\s*도용|무단\s*전재")

# G18 — 문제 유형 구분 마커 (W17 c16): "[ Type A ]" / "[ Type C (1) ]" /
# "[ Type D (1) 어법 ]" 류 단독 대괄호 라인. 같은 가족 마커는 한 스타일로
# 일관 인쇄돼야 한다 (G11 SRC 마커의 유형 마커 확장).
_RE_TYPE_MARKER = re.compile(r"^\[\s*Type\b[^\[\]]{0,30}\]$", re.I)

# G19 — 어법수정 원고 시그니처 (W17 c11): "1[asked]" 정답 괄호 표기.
_RE_GRAMMAR_FIX_SIG = re.compile(r"\d\s*\[\s*[A-Za-z]")

# G20 — 스토리 선두 날짜-only 라인 (W18 c18): 원고 표제 블록의 작업 날짜
# 메모 ("17. 11. 23"). 본문 어디서나가 아니라 '스토리 첫 콘텐츠 단락'만
# 검사한다 (본문 속 날짜 표기 오탐 방지 — 양품 16종 sweep 0 확인).
_RE_LEAD_DATE = re.compile(r"^\d{2,4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?$")

# G2 — step3 말미 압축 정답표 행 (완제품 보존 관행 — W21 r11 v1 실물 실증)
_RE_ANSWER_KEY_ROW = re.compile(
    r"^\d{1,2}\s*\.\s*[①-⑤](?:\s+\d{1,2}\s*\.\s*[①-⑤])+")

# G23 — "$BASIC" 계약의 [기본 단락] 별칭 (실행기 basicParaOf 대응 +
# 플랜 문자열 그대로의 합성 덤프 호환)
_BASIC_ALIASES = {"[기본 단락]", "[Basic Paragraph]", "NormalParagraphStyle",
                  "$ID/NormalParagraphStyle", "$BASIC"}
# G25 — C1 자동 삽입 발문 텍스트 (B1의 '하단 문제_지문' 등 부분 일치 오탐
# 방지: 스타일 leaf 정확 일치 + 이 접두 텍스트만 검사)
_RE_C1_PROMPT_TEXT = re.compile(r"^아래 주어진 문장")
# G27 — 외부지문 무-p형 헤더 ("1. no.1")
_RE_NOP_HEADER = re.compile(r"^\s*\d+\s*[.)]\s*no\.?\s*\d+(?:~\d+)?\s*$",
                            re.I)

# G16 — 현행 스텝이 소화 가능한 콘텐츠 토큰 (파일명 정규화 기준 —
# _norm_fname: 공백 제거 + 소문자). EBS 계열은 어법수정도 스텝 원고
# (file_map step2_a1)라 토큰에 추가된다.
_STEP_CONTENT_TOKENS = ("어휘선택", "본문ox", "본문정리", "내용종합",
                        "문장배열", "빈칸어휘", "어휘완성", "빈칸내용",
                        "어법선택", "어법ox", "빈칸어법", "영작배열",
                        "낱말배열", "실전문제")
_STEP_CONTENT_TOKENS_EBS = _STEP_CONTENT_TOKENS + ("어법수정",)


# G10 — hwp 사용자 영역(PUA) 문자 (BMP U+E000~F8FF + plane 15/16).
# InDesign 본문 폰트에 글리프가 없어 tofu로 인쇄된다. ￼(U+FFFC 앵커)는
# PUA가 아니므로 무관.
def _is_pua(ch):
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD
            or 0x100000 <= cp <= 0x10FFFD)


def _clean(t):
    """덤프 단락 텍스트 정규화 — 앵커(￼)/개행 제거 + 공백 정리."""
    t = unicodedata.normalize("NFC", t or "")
    t = t.replace("￼", "")
    return _norm_header(t)


def _dump_paras(dump):
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            yield p.get("t", ""), p.get("s", "")


def _flow_probe_text(flow):
    """플로우에서 가장 긴 단락 텍스트 — 덤프 스토리 식별용 (충분히 고유)."""
    best = ""
    for u in flow.get("units", []):
        paras = u["paras"] if isinstance(u, dict) else u
        for p in paras:
            if len(p.get("t") or "") > len(best):
                best = p["t"]
    return best


def _find_story_with_text(dump, text):
    key = _clean(text)
    if not key:
        return None
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            if _clean(p.get("t", "")) == key:
                return story
    return None


def _find_flow_story(dump, flow, max_probe=40):
    """플로우 → 덤프 스토리 매칭 (W21 r11 — 다수 단락 스코어링).

    단일 최장 단락 매칭(_flow_probe_text)은 같은 지문을 재인쇄하는 step3
    스토리로 오매핑될 수 있다 (0e3108fd 실증: step1_a2 최장 단락이 step3
    실전문제 지문과 동일). 플로우 단락 여러 개의 포함 수로 스코어링하고,
    동률이면 단락 수가 적은(초집합이 아닌) 스토리를 고른다."""
    probes = []
    seen = set()
    for u in flow.get("units", []):
        for p in (u["paras"] if isinstance(u, dict) else u):
            tt = _clean(p.get("t") or "")
            if len(tt) >= 8 and tt not in seen:
                seen.add(tt)
                probes.append(tt)
        if len(probes) >= max_probe:
            break
    if not probes:
        return _find_story_with_text(dump, _flow_probe_text(flow))
    probe_set = set(probes[:max_probe])
    best = None
    best_key = (-1, 0)
    for story in dump.get("stories", []):
        texts = {_clean(p.get("t", "")) for p in story.get("paragraphs", [])}
        score = len(probe_set & texts)
        if score == 0:
            continue
        key = (score, -len(story.get("paragraphs", [])))
        if key > best_key:
            best_key = key
            best = story
    return best


def _is_struct_header_candidate(paras, i):
    """구조적 헤더 후보 — 형식 무관 판정 (parser._is_passage_marker_struct
    준용). 짧고 숫자 포함, 영단어 적고, 뒤에 긴 영어 본문이 따라옴."""
    text = (paras[i].get("text") or "").strip()
    if not text or len(text) > 40:
        return False
    if not _RE_DIGIT.search(text):
        return False
    if len(_RE_ENG_WORD.findall(text)) >= 4:
        return False
    j = i + 1
    while j < len(paras) and not (paras[j].get("text") or "").strip():
        j += 1
    if j >= len(paras):
        return False
    return len(_RE_ENG_WORD.findall(paras[j].get("text") or "")) >= 5


# 헤더 기반 스텝 (헤더 제거/정규화가 빌더 책임인 스텝)
_HEADER_STEPS = ("step1_c2", "step2_c1", "step2_b1", "step2_a1", "step1_c1")

# ── G9: 미사용 업로드 원고 (W13) ─────────────────────────────────────────────
_MS_EXTS = (".docx", ".hwp", ".hwpx")
_RE_ANSWERISH = re.compile(r"정답|답지|답안|해설|answer", re.I)
_RE_S3_NUMFILE = re.compile(r"\d+(?:\s*~\s*\d+)?\s*번\s*\.(?:hwpx?|docx)",
                            re.I)
_RE_VARIANT = re.compile(r"변형\s*문제")


def _norm_fname(name):
    return unicodedata.normalize(
        "NFC", os.path.splitext(name)[0]).replace(" ", "").lower()


def find_unused_uploads(content, uploads_dir):
    """(expected_unused, suspicious) — 스텝에 소비되지 않은 원고 파일 분류.

    used 판정은 파서 소비 규칙의 근사 재현:
      - 루트: content steps의 filename (파서가 매칭·rename한 실명)
      - Step3 하위폴더: "N번" 파일(모의고사 번호 매칭), 변형문제 문제모음,
        교과서 경로(step3가 textbook 항목이면 비정답 후보 전부 소비)
    expected_unused = 정답/답지/해설 토큰 파일 + '정답지 짝' 파일(빈칸어휘
    스텝처럼 정답지 본이 소비되는 경우의 문제지 본) — 관행상 폴더에 늘
    존재하므로 stats로만 보고한다.
    """
    steps = (content.get("steps") or {}) if content else {}
    used = set()
    for sd in steps.values():
        if isinstance(sd, dict) and sd.get("filename"):
            used.add(_norm_fname(sd["filename"]))
    st3 = steps.get("step3") or {}
    st3_items = ((st3.get("normal") or []) + (st3.get("short") or [])
                 if isinstance(st3, dict) else [])
    st3_textbook = any(it.get("question_num") == "textbook"
                       for it in st3_items)
    st3_numbered = any(it.get("question_num") != "textbook"
                       for it in st3_items)

    # 전체 파일명 집합 (W21 r11): 업로드 슬롯 접두 사본("manuscripts_X")의
    # 원본 X가 라우팅으로 다른 하위 폴더(Step3/)에 스테이징된 경우도 중복
    # 사본으로 판정하기 위함 (0e3108fd 실측: "manuscripts_Step 3.hwpx"의
    # 원본 "Step 3.hwpx"가 Step3/로 라우팅돼 같은 폴더 존재 검사를 비껴감).
    all_names = set()
    for root, dirs, files in os.walk(uploads_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            all_names.add(unicodedata.normalize("NFC", f))

    expected, suspicious = [], []
    for root, dirs, files in os.walk(uploads_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        in_step3 = "step3" in unicodedata.normalize(
            "NFC", os.path.relpath(root, uploads_dir)).lower()
        for f in sorted(files):
            if f.startswith(".") or os.path.splitext(f)[1].lower() \
                    not in _MS_EXTS:
                continue
            nf = unicodedata.normalize("NFC", f)
            key = _norm_fname(nf)
            if key in used:
                continue
            # 업로드 슬롯 접두 사본("manuscripts_X")과 스테이징 사본(X)이
            # 같은 uploads 디렉터리에 공존 (W18 sero 실증: 26개 오탐) —
            # 접두 제거명이 소비됐거나 같은 폴더에 존재하면 중복 사본
            if nf.startswith("manuscripts_"):
                stripped = nf[len("manuscripts_"):]
                if (_norm_fname(stripped) in used
                        or stripped in all_names):
                    continue
            if in_step3:
                if st3_numbered and _RE_S3_NUMFILE.search(nf):
                    continue      # 모의고사 번호 매칭으로 소비
                if _RE_VARIANT.search(nf) and st3_items:
                    continue      # 변형문제 문제모음 (W12 라우팅)
                if (st3_textbook and not _RE_ANSWERISH.search(nf)):
                    continue      # 교과서 경로: 비정답 후보 전부 소비
            if _RE_ANSWERISH.search(nf) or any(u.startswith(key)
                                               for u in used):
                # 정답/답지류, 또는 소비된 변형본의 짝 파일 (예: 사용
                # "…빈칸어휘 정답지.docx"/"…영작배열(서술형).hwpx"의 짝
                # "…빈칸어휘.docx"/"…영작배열.docx") — 관행상 의도된 미사용
                expected.append(nf)
            else:
                suspicious.append(nf)
    return expected, suspicious


def inspect_workbook_finish(content, plan, dump, uploads_dir=None):
    """content(원고 파싱본) + plan + 출력 덤프 → 완제품 게이트 리포트."""
    critical = []
    warnings = []
    stats = {}
    plan = plan or {}
    steps = (content.get("steps") or {}) if content else {}

    strict_numbers = bool(plan.get("passage_numbers"))
    strict_pages = bool(plan.get("page_cleanup"))
    pos_used = any((fl.get("target") or {}).get("pos")
                   for fl in plan.get("flows", []))

    # ── G7 빈 플랜 — 업로드 원고가 렌더 유닛으로 전혀 이어지지 않음 ─────
    # (W12 실증: 변형문제 문제모음 hwp가 스텝 분류에 안 잡혀 조용히
    # 유실됐는데 verify ok=True로 끝나던 침묵 유실 차단)
    total_units = sum(len(fl.get("units") or [])
                     for fl in plan.get("flows", []))
    stats["plan_units"] = total_units
    if total_units == 0:
        critical.append("[빈플랜] 렌더 유닛 0 — 업로드 원고가 어느 스텝에도 "
                        "매핑되지 않음 (파일명/폴더 규칙 확인)")

    # ── G1 헤더 원문 잔존 + G8 구분선 잔존 ──────────────────────────────
    leaks = []
    divider_leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if any(p.match(tt) for p in _DIVIDER_PATTERNS):
            divider_leaks.append(tt[:60])
            continue
        if not _RE_DIGIT.search(tt):
            continue
        if tt.startswith("{") or tt.startswith("["):
            continue    # {20}/{3과 추가지문}/[20] — 의도된 라벨 산출물
        if is_header_line(tt) or is_a1_header(tt):
            leaks.append(tt[:60])
    stats["header_leaks"] = len(leaks)
    if leaks:
        critical.append(f"[헤더잔존] {len(leaks)}개 단락이 지문번호 헤더 "
                        f"원문 그대로 인쇄됨: "
                        + " | ".join(sorted(set(leaks))[:5]))
    stats["divider_leaks"] = len(divider_leaks)
    if divider_leaks:
        critical.append(f"[구분선잔존] {len(divider_leaks)}개 단락이 원전 "
                        f"챕터/유닛 구분선 그대로 인쇄됨: "
                        + " | ".join(sorted(set(divider_leaks))[:5]))

    # ── G2 정답 블록 잔존 ────────────────────────────────────────────────
    ans = find_leaked_answers(dump)
    # W21 r11: step3(문제 pool) 스토리의 압축 정답표 행("1. ①  2. ② …")은
    # 완제품 관행상 보존 — v1 실물(워크북03(외부지문) 스토리 53)도 실전문제
    # 지문 스타일로 유지한다 (문제책 말미 정답 모음). step3 플로우 스토리
    # 안의 해당 셰이프만 critical에서 제외하고 stats로 보고.
    st3_flow = next((fl for fl in plan.get("flows", [])
                     if fl.get("step") == "step3"), None)
    if ans and st3_flow:
        # 플랜에도 있는 행만 면제 (파서가 의도 보존한 정답 모음) — 파서가
        # 잘라야 했던 '정답' 마커 블록의 행(06f4b2c2)은 플랜에 없어 잔존
        # critical 유지. find_leaked_answers는 raw strip()[:60] — 동일 정규화.
        st3_plan_texts = {(p.get("t") or "").strip()[:60]
                          for u in st3_flow.get("units", [])
                          for p in (u["paras"] if isinstance(u, dict) else u)}
        st3_dump = _find_flow_story(dump, st3_flow)
        if st3_dump is not None:
            st3_texts = {(p.get("t") or "").strip()[:60]
                         for p in st3_dump.get("paragraphs", [])}
            kept = [a for a in ans
                    if _RE_ANSWER_KEY_ROW.match(a) and a in st3_texts
                    and a in st3_plan_texts]
            if kept:
                stats["answer_rows_step3_kept"] = len(kept)
                ans = [a for a in ans if a not in set(kept)]
    stats["answer_leaks"] = len(ans)
    if ans:
        critical.append(f"[정답잔존] {len(ans)}개 단락: "
                        + " | ".join(ans[:5]))

    # ── G10 hwp 사용자 영역(PUA) 문자 잔존 (W14, W20 확장) ───────────────
    pua_solo = []
    pua_inline = []
    pua_mapped = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not any(_is_pua(ch) for ch in tt):
            continue
        codes = sorted({f"U+{ord(ch):04X}" for ch in tt if _is_pua(ch)})
        if all(_is_pua(ch) or ch.isspace() for ch in tt):
            pua_solo.append(codes[0])
        elif any(_is_pua(ch) and ord(ch) in PUA_PRINT_TABLE for ch in tt):
            # W20 — 인쇄 매핑 등재 코드의 혼입 잔존은 critical (현행
            # 플랜은 치환하므로 잔존 = 매핑 미적용/구출력)
            pua_mapped.append(f"{codes[0]} ({tt[:30]})")
        else:
            pua_inline.append(f"{codes[0]} ({tt[:30]})")
    stats["pua_solo"] = len(pua_solo)
    stats["pua_inline"] = len(pua_inline)
    stats["pua_mapped_inline"] = len(pua_mapped)
    if pua_solo:
        critical.append(
            f"[특수문자] hwp 사용자 영역(PUA) 단독 단락 {len(pua_solo)}개 — "
            f"폰트 글리프 없음(tofu 인쇄): "
            + ", ".join(sorted(set(pua_solo))[:5]))
    if pua_mapped:
        critical.append(
            f"[특수문자] 인쇄 매핑 등재 PUA 코드가 본문에 잔존 "
            f"{len(pua_mapped)}개 단락 (플랜 매핑 미적용 출력): "
            + " | ".join(pua_mapped[:3]))
    if pua_inline:
        warnings.append(
            f"[특수문자] 본문 내 PUA 문자 혼입 {len(pua_inline)}개 단락: "
            + " | ".join(pua_inline[:3]))

    # ── G11 변형문제 출처 마커 인쇄 상태 (W15 c04) ───────────────────────
    # "[202506H2_18목적추론_변형]" 단독 단락은 관행상 지문 스타일로 일관
    # 인쇄된다 (v1 실물 고2 25-6 워크북 대조). ① 마커에 원문자 접두가 붙어
    # 인쇄 = 파서 선지 오염(원고에 없는 선지 번호), ② 같은 마커 셰이프가
    # 복수 스타일로 인쇄 = kind 오분류(발문/선지 스타일로 크게 찍힘) —
    # 둘 다 critical.
    src_styles = {}
    src_polluted = []
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if _RE_SRC_POLLUTED.match(tt):
            src_polluted.append(tt[:40])
            continue
        if _RE_SRC_MARKER.match(tt):
            src_styles.setdefault(s, []).append(tt)
    stats["src_markers"] = sum(len(v) for v in src_styles.values())
    stats["src_marker_styles"] = len(src_styles)
    stats["src_polluted"] = len(src_polluted)
    if src_polluted:
        critical.append(
            f"[마커오염] 출처 마커에 원고에 없는 원문자 접두 "
            f"{len(src_polluted)}개: " + " | ".join(src_polluted[:3]))
    if len(src_styles) > 1:
        major = max(src_styles, key=lambda k: len(src_styles[k]))
        minority = {k: v for k, v in src_styles.items() if k != major}
        critical.append(
            "[마커스타일] 출처 마커가 복수 스타일로 인쇄됨 (기준 "
            f"「{major}」 {len(src_styles[major])}개 외): "
            + " | ".join(f"「{k}」 {len(v)}개 (예: {v[0][:30]})"
                         for k, v in sorted(minority.items())[:3]))

    # ── G17 학원 워터마크 잔존 (W17 c16) ─────────────────────────────────
    watermark = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if _RE_WATERMARK_URL.match(tt) or _RE_WATERMARK_WARN.search(tt):
            watermark.append(tt[:50])
    stats["watermark_leaks"] = len(watermark)
    if watermark:
        critical.append(
            f"[워터마크잔존] 학원 워터마크/경고 라인 {len(watermark)}개가 "
            f"출력에 인쇄됨: " + " | ".join(watermark[:3]))

    # ── G18 유형 마커 스타일 일관성 (W17 c16) ────────────────────────────
    type_styles = {}
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if _RE_TYPE_MARKER.match(tt):
            type_styles.setdefault(s, []).append(tt)
    stats["type_markers"] = sum(len(v) for v in type_styles.values())
    stats["type_marker_styles"] = len(type_styles)
    if len(type_styles) > 1:
        major = max(type_styles, key=lambda k: len(type_styles[k]))
        minority = {k: v for k, v in type_styles.items() if k != major}
        critical.append(
            "[유형마커스타일] 유형 구분 마커가 복수 스타일로 인쇄됨 (기준 "
            f"「{major}」 {len(type_styles[major])}개 외): "
            + " | ".join(f"「{k}」 {len(v)}개 (예: {v[0][:30]})"
                         for k, v in sorted(minority.items())[:3]))

    # ── G12 문장삽입 '주어진 문장' 배경 (W15 c04 — warning) ──────────────
    # 변형 문제모음(출처 마커가 있는 스토리)에서 문장삽입 발문 뒤 3단락 내에
    # 배경 스타일 단락이 없으면 지목 — 주어진 문장 박스 누락 (v2는 분류
    # 계층 P-CONTEXT로 부여, v1 실물은 마커에 배경을 줬음 — 어느 쪽이든
    # '배경 없음'은 결함).
    insert_missing = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        if not any(_RE_SRC_MARKER.match(_clean(p.get("t", ""))) for p in ps):
            continue
        for i, p in enumerate(ps):
            if not _RE_INSERT_PROMPT.search(_clean(p.get("t", ""))):
                continue
            window = [q for q in ps[i + 1:i + 5]
                      if _clean(q.get("t", ""))][:3]
            if not any("배경" in (q.get("s") or "") for q in window):
                insert_missing.append(_clean(p.get("t", ""))[:40])
    stats["insert_bg_missing"] = len(insert_missing)
    if insert_missing:
        warnings.append(
            f"[문장삽입배경] 문장삽입 발문 뒤 배경(주어진 문장 박스) 미부여 "
            f"{len(insert_missing)}건: " + " | ".join(insert_missing[:3]))

    # ── G13 발문 스타일 누락 (W16 c07) ───────────────────────────────────
    # [서술형 N] 접두 태그, 또는 발문 시작 신호("다음/윗글/주어진…") +
    # 시오/세요-체 종결(꼬리 [출처] 태그 제거 후)이 발문 계열 스타일이
    # 아니면 검출 — 해요체("쓰세요") 발문이 지문 스타일로 인쇄되는 결함.
    q_style_miss = []
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not _RE_HANGUL.search(tt):
            continue
        core = tt
        while True:
            nx = _RE_Q_TRAIL_SRC.sub("", core)
            if nx == core:
                break
            core = nx
        body = _RE_Q_LEAD_TAG.sub("", core).strip()
        had_tail_tag = core != tt   # 꼬리 [출처/태그]가 있었음
        is_q_sig = bool(_RE_Q_LEAD_TAG.match(core)) or (
            _RE_Q_START.match(body) and _RE_Q_END.search(body)) or (
            had_tail_tag and bool(_RE_Q_END.search(body)))   # W18 확장
        if is_q_sig and body and not any(k in (s or "")
                                         for k in _Q_STYLE_KEYS):
            q_style_miss.append(tt[:45])
    stats["q_style_miss"] = len(q_style_miss)
    if q_style_miss:
        critical.append(
            f"[발문스타일] 발문 시그니처 단락 {len(q_style_miss)}개가 발문 "
            f"계열 스타일이 아님: " + " | ".join(q_style_miss[:3]))

    # ── G20 스토리 선두 날짜-only 잔재 (W18 c18) ─────────────────────────
    lead_junk = []
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            tt = _clean(p.get("t", ""))
            if not tt:
                continue
            if _RE_LEAD_DATE.match(tt):
                lead_junk.append(tt[:30])
            break               # 스토리 첫 콘텐츠 단락만 검사
    stats["leading_date_junk"] = len(lead_junk)
    if lead_junk:
        critical.append(
            f"[선두잔재] 스토리 선두에 날짜-only 라인 {len(lead_junk)}개 "
            f"인쇄됨 (표제 블록 잔재): " + " | ".join(lead_junk[:3]))

    # ── G14 영단어 스타일 오분류 (W16 c10) ───────────────────────────────
    word_bad = []
    for t, s in _dump_paras(dump):
        if "영단어" not in (s or ""):
            continue
        tt = _clean(t)
        if not tt:
            continue
        if not _RE_HANGUL.search(tt) or _RE_WORD_BAD_HEAD.match(tt):
            word_bad.append(tt[:45])
    stats["word_style_bad"] = len(word_bad)
    if word_bad:
        critical.append(
            f"[영단어오분류] 어휘 항목이 아닌 단락 {len(word_bad)}개가 "
            f"영단어 스타일로 인쇄됨: " + " | ".join(word_bad[:3]))

    # ── G21 원문자 ① 중복 오염 (W19 c20) ────────────────────────────────
    # ※ 다중 문항 아이템은 발문마다 지문을 재인쇄한다. 마지막 5지선다
    # 발문(도표/불일치류 — 선지가 지문 문장 inline ①~⑤) 뒤 재인쇄 지문에
    # 선지 자동번호가 원고에 없는 ①을 prepend → '①The graph … ① In
    # Germany …'처럼 한 단락에 ①이 2회 등장하는 기형 번호가 인쇄된다.
    # 원고에 타이핑된 inline 번호 지문('①Families … ②Gary …' c19 /
    # '① Remember …' 0a5da924)은 ①이 1회뿐이라 통과 (v1 관행 보존).
    choice_polluted = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if len(tt) < 200 or not tt or tt[0] != "①":
            continue
        if "①" in tt[1:]:
            choice_polluted.append(tt[:60])
    stats["choice_polluted_passages"] = len(choice_polluted)
    if choice_polluted:
        critical.append(
            f"[원문자중복] ①로 시작하면서 본문에 ①이 다시 등장하는 장문 "
            f"단락 {len(choice_polluted)}개 — 선지 자동번호가 inline 번호 "
            f"지문에 ①을 중복 부여한 오염: " + " | ".join(choice_polluted[:2]))

    # ── G22 간지 라벨 원고 불일치 (W19 c20 + 본가 소급) ──────────────────
    # v1 16.7은 간지의 '고N 모의고사 / YY년 M월'을 원고 값으로 갱신한다.
    # content에 grade/year/month가 전부 있을 때만 검사 (교과서 간지는
    # subject/publisher 형식이라 L1 패턴 자체가 안 잡힘).
    exp_g, exp_y, exp_m = (content or {}).get("grade"), \
        (content or {}).get("year"), (content or {}).get("month")
    divider_stale = []
    if exp_g and exp_y and exp_m:
        for story in dump.get("stories", []):
            ps = story.get("paragraphs", [])
            for i in range(len(ps) - 1):
                m1 = _RE_DIVIDER_L1.match(_clean(ps[i].get("t", "")))
                m2 = _RE_DIVIDER_L2.match(_clean(ps[i + 1].get("t", "")))
                if not (m1 and m2):
                    continue
                if (int(m1.group(1)) != int(exp_g)
                        or int(m2.group(1)) != int(exp_y) % 100
                        or int(m2.group(2)) != int(exp_m)):
                    divider_stale.append(
                        f"{m1.group(0)}/{m2.group(0)}")
    stats["divider_stale"] = len(divider_stale)
    if divider_stale:
        msg = (f"[간지라벨] 간지 라벨 {len(divider_stale)}개가 원고"
               f"(고{exp_g} {exp_y}년 {exp_m}월)와 불일치 — 템플릿 잔재: "
               + " | ".join(sorted(set(divider_stale))[:3]))
        # divider op 사용 플랜은 갱신이 계약 — critical. 미사용(과거 출력
        # /세로 실행기)은 warning 지목 (G3/G4 패턴).
        if plan.get("divider"):
            critical.append(msg)
        else:
            warnings.append(msg)

    # ── G15 <조건> 블록 항목 스타일 (W16 c10) ────────────────────────────
    # <조건> 마커부터 답란(밑줄런/정답/→/우리말) 이전까지 스캔. 강신호
    # 조건 항목(불릿 시작 / 한글 + '것' 종결 / 번호 + 한글 + '것' 종결)이
    # 조건 스타일이 아니면 검출. 발문 스타일 + 발문 신호(시작 힌트/시오)는
    # 블록 종료로 간주 (v1 실물: 시오-체 번호 항목은 발문 유지 관행).
    cond_miss = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        for i, p in enumerate(ps):
            if _clean(p.get("t", "")) != "<조건>":
                continue
            for j in range(i + 1, len(ps)):
                qt = _clean(ps[j].get("t", ""))
                qs = ps[j].get("s") or ""
                if not qt:
                    continue
                if _RE_COND_BLOCK_END.search(qt):
                    break
                if qt.startswith("<보기>") or qt == "보기":
                    break
                if any(k in qs for k in ("다음 글을 읽고", "보기", "배경")):
                    break
                if "번호" in qs and (_RE_COND_QHINT.match(qt)
                                     or "시오" in qt):
                    break
                strong = (_RE_COND_BULLET.match(qt)
                          or (_RE_COND_GEOT.search(qt)
                              and _RE_HANGUL.search(qt)))
                if strong and "조건" not in qs:
                    cond_miss.append(qt[:45])
                elif not (_RE_HANGUL.search(qt)
                          or _RE_COND_BULLET.match(qt)):
                    continue    # 영어 어구 나열 — 지문 유지 관행 (skip)
                elif "조건" not in qs and not strong:
                    break       # 한글 비조건 문장 — 블록 종료로 간주
    stats["cond_item_miss"] = len(cond_miss)
    if cond_miss:
        critical.append(
            f"[조건항목] <조건> 블록 항목 {len(cond_miss)}개가 조건 스타일이 "
            f"아님: " + " | ".join(cond_miss[:3]))

    # ── G3 독립 지문번호 프레임 ↔ 원고 지문번호 ─────────────────────────
    labels = list((plan.get("passage_numbers") or {}).get("labels") or [])
    if not labels:
        labels = passage_labels(steps)
    expected = set(labels)
    for sd in steps.values():
        if isinstance(sd, dict):
            for n in sd.get("question_numbers") or []:
                expected.add(str(n))
    bare_frames = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        if len(ps) != 1:
            continue
        tt = _clean(ps[0].get("t", ""))
        if _RE_BARE_NUM.match(tt):
            bare_frames.append(tt)
    unknown = sorted(set(t for t in bare_frames if t not in expected))
    stats["number_frames"] = len(bare_frames)
    stats["number_frame_unknown"] = len(unknown)
    if unknown:
        msg = (f"[지문번호] 원고에 없는 번호 프레임 {len(unknown)}종 잔존"
               f" (템플릿 잔재): " + ", ".join(unknown[:10]))
        (critical if strict_numbers else warnings).append(msg)

    # ── G4b 고아 번호 페이지 (W14 c03/c15 실증) ─────────────────────────
    # 지문번호/문항번호 프레임은 있는데 콘텐츠 스토리가 전혀 없는 페이지 —
    # 원고 없는 스텝의 섹션 머리/예시 페이지(c03 '20' 3p), 또는 W13 스레드
    # 절단 이후 빈 프레임 페이지가 삭제 판정(다중 프레임 전부 빈)을
    # 벗어나며 남은 잔재(c15 '5' 3p). page_cleanup 사용 시 critical.
    # 콘텐츠 판정은 '플랜(원고) 단락과 겹치는 스토리'만 — 섹션 마커
    # (" 빈칸 어휘")/발문/예시 등 내지 장식 텍스트는 콘텐츠가 아니다
    # (c03 p6/p10/p11: 마커·예시 텍스트 때문에 '내용 있음'으로 오인 방지).
    plan_texts = set()
    for fl in plan.get("flows", []):
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                tt = _clean(p.get("t", ""))
                if len(tt) >= 4:
                    plan_texts.add(tt)
    num_pages = set()
    content_pages = set()
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        pgs = story.get("pg") or []
        if len(ps) == 1 and _RE_BARE_NUM.match(_clean(ps[0].get("t", ""))):
            num_pages.update(pgs)
        elif any(_clean(p.get("t", "")) in plan_texts
                 for p in ps if len(_clean(p.get("t", ""))) >= 4):
            content_pages.update(pgs)
    orphan_pages = sorted(num_pages - content_pages, key=lambda x: (
        int(x) if str(x).isdigit() else 10**9, str(x)))
    stats["orphan_number_pages"] = len(orphan_pages)
    if orphan_pages:
        msg = (f"[잔여페이지] 번호 프레임만 있고 콘텐츠 없는 페이지 "
               f"{len(orphan_pages)}개: p" + ", p".join(
                   str(p) for p in orphan_pages[:10]))
        (critical if strict_pages else warnings).append(msg)

    # ── G4 잔여 페이지 (원고 없는 스텝/남는 사이클) ──────────────────────
    cleanup_op = (plan.get("page_cleanup")
                  if isinstance(plan.get("page_cleanup"), dict) else {})
    cleanup_delete = cleanup_op.get("empty") == "delete"
    stale = dump.get("stale_pages")
    if stale is None:
        warnings.append("[잔여페이지] 덤프에 페이지 정보 없음(구버전 덤프)"
                        " — 재덤프 필요")
    else:
        if cleanup_delete:
            # W21 delete 모드: 빈 페이지는 삭제가 계약 — M 마스터 면제 없음.
            # 페이지 인벤토리(pages)의 빈 페이지(프레임 있고 전부 공백 —
            # 스레드 절단 후 단일 프레임 꼬리 포함)도 잔여로 합산 (r11
            # 재조판 1차 실측: stale 판정 밖 p12/p21 잔존).
            residual = list(stale)
            seen_p = {str(e.get("p")) for e in residual}
            for pe in dump.get("pages") or []:
                if pe.get("empty") and str(pe.get("p")) not in seen_p:
                    residual.append({"p": pe.get("p"), "m": pe.get("m")})
                    seen_p.add(str(pe.get("p")))
            # W22 r12: 장식-빈 페이지 합산 — 반복 장식(페이지마다 얹히는
            # 발문/섹션 탭) 단일 프레임 텍스트만 남은 페이지는 pages의
            # empty 판정('텍스트 있음')을 비껴간다 (r11 재조판 실측:
            # p34 어법선택 발문 / p47 영작배열 탭 — 사용자 지목 결함).
            # 콘텐츠(플랜 단락) 페이지에서 수집한 단일 페이지 스토리
            # 텍스트와 같은 텍스트 + 공백/번호 프레임만 있는 페이지를
            # 잔여로 본다. 간지/표지(마스터 없음)와 M 채움 페이지(파트
            # 경계 — G28이 위치 검증)는 제외.
            page_texts = {}
            furn = set()
            for story in dump.get("stories", []):
                pgs = story.get("pg") or []
                txt = _clean("".join(p.get("t", "")
                                     for p in story.get("paragraphs", [])))
                for pg in pgs:
                    page_texts.setdefault(str(pg), []).append(txt)
                if len(pgs) == 1 and txt and str(pgs[0]) in content_pages:
                    furn.add(txt)
            for pe in dump.get("pages") or []:
                p = str(pe.get("p"))
                m = str(pe.get("m") or "")
                if (p in seen_p or p in content_pages
                        or m in ("", "[None]") or m.startswith("M")):
                    continue
                texts = page_texts.get(p)
                if texts and all((not t) or _RE_BARE_NUM.match(t)
                                 or t in furn for t in texts):
                    residual.append({"p": pe.get("p"), "m": pe.get("m")})
                    seen_p.add(p)
        else:
            empty_prefix = cleanup_op.get("empty_master", "M")
            residual = [e for e in stale
                        if not str(e.get("m", "")).startswith(empty_prefix)]
        stats["stale_pages"] = len(residual)
        if residual:
            names = [str(e.get("p")) for e in residual]
            msg = (f"[잔여페이지] 내용 없는 스텝/사이클 페이지 "
                   f"{len(residual)}개 잔존: p" + ", p".join(names[:12])
                   + ("…" if len(names) > 12 else ""))
            (critical if strict_pages else warnings).append(msg)

    # ── G23 지문번호 라벨 스타일 계약 (W21 r11) ──────────────────────────
    # step_map.json의 label_contract가 flow.target으로 플랜에 실린다.
    # 라벨 셰이프 단락(단독 [N]/{N})의 실측 스타일이 계약과 다르면 critical.
    label_style_bad = []
    for fl in plan.get("flows", []):
        contract = (fl.get("target") or {}).get("label_contract")
        if not contract or not contract.get("re"):
            continue
        story = _find_flow_story(dump, fl)
        if story is None:
            continue
        try:
            rx = re.compile(contract["re"])
        except re.error:
            continue
        want = contract.get("style") or "$BASIC"
        for p in story.get("paragraphs", []):
            tt = _clean(p.get("t", ""))
            if not tt or not rx.match(tt):
                continue
            s = p.get("s") or ""
            ok_style = (s in _BASIC_ALIASES if want == "$BASIC"
                        else s == want)
            if not ok_style:
                label_style_bad.append(
                    f"{fl['step']} {tt[:15]} 「{s}」≠「{want}」")
    stats["label_style_bad"] = len(label_style_bad)
    if label_style_bad:
        critical.append(
            f"[라벨스타일] 지문번호 라벨 {len(label_style_bad)}개가 계약 "
            f"스타일과 불일치: " + " | ".join(label_style_bad[:4]))

    # ── G24 프레임 브레이크 (W21 r11) ────────────────────────────────────
    # ① per_passage_units 계약 스텝이 지문 다수 원고에서 유닛 1개로 배치 —
    #    헤더 미인식으로 프레임 분리가 통째로 실패한 상태 (플랜 실측).
    labels_for_units = list((plan.get("passage_numbers") or {})
                            .get("labels") or []) or passage_labels(steps)
    break_fail = []
    for fl in plan.get("flows", []):
        if not (fl.get("target") or {}).get("per_passage_units"):
            continue
        if len(fl.get("units") or []) == 1 and len(labels_for_units) >= 2:
            break_fail.append(f"{fl['step']} (지문 {len(labels_for_units)}개 "
                              f"→ 유닛 1개)")
    stats["frame_break_plan_fail"] = len(break_fail)
    if break_fail:
        critical.append(
            f"[프레임브레이크] 지문 분리 미발생 {len(break_fail)}개 스텝: "
            + " | ".join(break_fail[:5]))

    # ② 유닛 시작 단락이 실제 프레임 경계에 있는지 (덤프 fc 실측 — 신형
    #    덤프 한정. 단락↔플랜 1:1 정렬은 배치 방식(story.contents 치환)이
    #    보장, trimWsOverset로 꼬리 단락이 줄 수 있어 범위 밖은 생략).
    fc_missing_warned = False
    break_pos_bad = []
    for fl in plan.get("flows", []):
        units = fl.get("units") or []
        if not fl.get("break_per_unit") or len(units) < 2:
            continue
        story = _find_flow_story(dump, fl)
        if story is None:
            continue
        if "fc" not in story:
            if not fc_missing_warned:
                warnings.append("[프레임브레이크] 덤프에 프레임 문자 인덱스"
                                "(fc) 없음(구버전 덤프) — 실측 생략")
                fc_missing_warned = True
            continue
        fc_set = {c for c in story.get("fc") or [] if c >= 0}
        ps = story.get("paragraphs", [])
        offsets = []
        off = 0
        for p in ps:
            offsets.append(off)
            off += len(p.get("t") or "")
        upto = 0
        for k, u in enumerate(fl["units"]):
            n_paras = len(u["paras"] if isinstance(u, dict) else u)
            start = upto
            upto += n_paras
            if k == 0 or start >= len(offsets):
                continue
            if offsets[start] not in fc_set:
                break_pos_bad.append(f"{fl['step']} 유닛{k + 1}")
    stats["frame_break_pos_bad"] = len(break_pos_bad)
    if break_pos_bad:
        critical.append(
            f"[프레임브레이크] 유닛 시작이 프레임 경계에 있지 않음 "
            f"{len(break_pos_bad)}건: " + " | ".join(break_pos_bad[:5]))

    # ── G25 발문 다음 빈 단락 (W21 r11) ──────────────────────────────────
    # 발문(하단 문제 스타일) 바로 다음의 '진짜 빈'(앵커 없는) 단락 —
    # 발문과 주어진 문장 사이 불필요한 빈 줄. v1 실물은 발문 직후가 BTM.
    prompt_gap = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        for i, p in enumerate(ps[:-1]):
            leaf = (p.get("s") or "").split(" > ")[-1].strip()
            if leaf != "하단 문제":
                continue
            if not _RE_C1_PROMPT_TEXT.match(_clean(p.get("t", ""))):
                continue    # C1 자동 삽입 발문만 — B1 발문 등 오탐 방지
            nt = (ps[i + 1].get("t") or "")
            if "￼" in nt:
                continue          # 아이콘 앵커 단락은 빈 줄이 아님
            if not nt.replace("\r", "").strip():
                prompt_gap.append(_clean(p.get("t", ""))[:35])
    stats["prompt_gap_blanks"] = len(prompt_gap)
    if prompt_gap:
        critical.append(
            f"[발문빈단락] 발문 바로 다음 빈 단락 {len(prompt_gap)}건 "
            f"(발문-주어진 문장 사이 빈 줄): " + " | ".join(prompt_gap[:3]))

    # ── G26 섹션 시작 좌/우 마스터 (W21 r11) ─────────────────────────────
    pages_inv = {str(e.get("p")): e for e in dump.get("pages") or []}
    strict_masters = bool(plan.get("section_masters"))
    master_bad = []
    pages_missing_warned = False
    for fl in plan.get("flows", []):
        pair = (fl.get("target") or {}).get("master_pair")
        if not pair:
            continue
        if not pages_inv:
            if not pages_missing_warned and dump.get("stories"):
                warnings.append("[섹션마스터] 덤프에 페이지 인벤토리(pages) "
                                "없음(구버전 덤프) — 실측 생략")
                pages_missing_warned = True
            break
        story = _find_flow_story(dump, fl)
        if story is None or not story.get("pg"):
            continue
        entry = pages_inv.get(str(story["pg"][0]))
        if not entry:
            continue
        want = pair.get("right") if entry.get("side") == "R" \
            else pair.get("left")
        if want and entry.get("m") != want:
            master_bad.append(f"{fl['step']} p{entry.get('p')}"
                              f"({entry.get('side')}) 「{entry.get('m')}」"
                              f"≠「{want}」")
    stats["section_master_bad"] = len(master_bad)
    if master_bad:
        msg = (f"[섹션마스터] 섹션 시작 페이지 마스터가 좌/우 변형과 "
               f"불일치 {len(master_bad)}건: " + " | ".join(master_bad[:5]))
        (critical if strict_masters else warnings).append(msg)

    # ── G27 간지 적합성 (W21 r11 → W22 r12 스펙 확정) ────────────────────
    # 사용자 확정 스펙 (r12 피드백 3, supp 계열): 간지는 업로드 시 입력한
    # 간지 문구, 미입력이면 교재유형만 표기 (예: '외부지문'). 엔진이
    # plan.divider.source(user|type)로 계약을 실으면:
    #   ① '고N 모의고사 / YY년 M월' 잔재 = critical (기대 문구로 갱신됐어야 함)
    #   ② 간지 라벨 실측(마스터 없는 페이지의 단일 페이지 스토리)이 기대
    #      문구(line1)와 불일치 = critical (라벨 실측이 없으면 생략 —
    #      간지 없는 합성 덤프/내지 호환)
    # source 없는 플랜(본가 모의고사/구출력)은 기존 W21 warning 유지:
    # 외부지문 무-p형('N. no.M') 원고 + '모의고사' 라벨 → 사람 확인 지목
    # (v1 실물도 같은 라벨을 유지한 관행 — 자동 치환 근거가 없었다).
    is_nop_manuscript = any(
        _RE_NOP_HEADER.match(_norm_header(p.get("text") or ""))
        for sd in steps.values() if isinstance(sd, dict)
        for p in (sd.get("paragraphs") or []))
    divider_plan = plan.get("divider") or {}
    supp_divider = divider_plan.get("source") in ("user", "type")
    if supp_divider or is_nop_manuscript:
        mock_dividers = []
        for story in dump.get("stories", []):
            ps = story.get("paragraphs", [])
            for i in range(len(ps) - 1):
                if (_RE_DIVIDER_L1.match(_clean(ps[i].get("t", "")))
                        and _RE_DIVIDER_L2.match(
                            _clean(ps[i + 1].get("t", "")))):
                    mock_dividers.append(_clean(ps[i].get("t", "")))
        stats["divider_type_mismatch"] = len(mock_dividers)
        if supp_divider:
            want_l1 = _clean(divider_plan.get("line1") or "")
            if mock_dividers:
                critical.append(
                    f"[간지적합] 간지 {len(mock_dividers)}개가 모의고사 "
                    f"라벨 잔재 — 기대 문구 「{want_l1}」 미적용: "
                    + mock_dividers[0])
            elif pages_inv and want_l1:
                # 간지 라벨 실측 대조 — 마스터 없는 페이지의 단일 페이지
                # 스토리(2단락+, 첫 단락 한글) = 간지 라벨 (실행기
                # updateDividerPages와 동일 판정 부류)
                divider_wrong = []
                for story in dump.get("stories", []):
                    pgs = story.get("pg") or []
                    if len(pgs) != 1:
                        continue
                    entry = pages_inv.get(str(pgs[0]))
                    if (not entry
                            or str(entry.get("m") or "") not in ("",
                                                                 "[None]")):
                        continue
                    ps = story.get("paragraphs", [])
                    if len(ps) < 2:
                        continue
                    t0 = _clean(ps[0].get("t", ""))
                    if not _RE_HANGUL.search(t0) and t0 != want_l1:
                        continue
                    if t0 != want_l1:
                        divider_wrong.append(f"p{entry.get('p')} 「{t0[:20]}」")
                stats["divider_label_wrong"] = len(divider_wrong)
                if divider_wrong:
                    critical.append(
                        f"[간지적합] 간지 라벨 {len(divider_wrong)}개가 기대 "
                        f"문구 「{want_l1}」와 불일치: "
                        + " | ".join(divider_wrong[:3]))
        elif is_nop_manuscript and mock_dividers:
            warnings.append(
                f"[간지적합] 외부지문 원고인데 간지 {len(mock_dividers)}개가 "
                f"'모의고사' 라벨 — 원고 유형과 불일치 의심 (사람 확인): "
                + mock_dividers[0])

    # ── G28 파트 경계 정렬 (W22 r12) ─────────────────────────────────────
    # [원본]워크북_C 실측: 간지 스프레드 = 왼쪽(빈 페이지) + 오른쪽(라벨).
    # ① 간지 라벨 페이지가 물리 왼쪽(L)이면 파트 경계 채움 페이지 누락 —
    #    delete 모드(정렬이 실행기 계약)는 critical, 아니면 warning
    #    (v1 실물도 밀린 간지를 방치한 관행 — W19 D5 주석. 완제품 기준
    #    으로 폐기, 사용자 확정 스펙: 오른쪽 채움 페이지 = M 마스터 삽입).
    # ② delete 모드의 M 마스터 페이지는 간지 직전 오른쪽 채움만 허용 —
    #    그 외 위치의 M 페이지는 빈 페이지 잔재 (W21 '완전 정리' 정책).
    if pages_inv:
        div_l1 = _clean((plan.get("divider") or {}).get("line1") or "")
        boundary_bad = []
        for story in dump.get("stories", []):
            pgs = story.get("pg") or []
            if len(pgs) != 1:
                continue
            entry = pages_inv.get(str(pgs[0]))
            if not entry or str(entry.get("m") or "") not in ("", "[None]"):
                continue
            ps = story.get("paragraphs", [])
            if not ps:
                continue
            t0 = _clean(ps[0].get("t", ""))
            is_label = (div_l1 and t0 == div_l1) or (
                len(ps) >= 2 and _RE_DIVIDER_L1.match(t0)
                and _RE_DIVIDER_L2.match(_clean(ps[1].get("t", ""))))
            if is_label and entry.get("side") == "L":
                boundary_bad.append(
                    f"간지 p{entry.get('p')}가 왼쪽 페이지 (오른쪽 채움 누락)")
        if cleanup_delete:
            plist = dump.get("pages") or []
            for i, pe in enumerate(plist):
                if not str(pe.get("m") or "").startswith("M"):
                    continue
                nxt = plist[i + 1] if i + 1 < len(plist) else None
                ok_pos = (pe.get("side") == "R" and nxt
                          and str(nxt.get("m") or "") in ("", "[None]"))
                if not ok_pos:
                    boundary_bad.append(
                        f"M 페이지 p{pe.get('p')} 위치 이상 "
                        f"(간지 직전 오른쪽 채움만 허용)")
        stats["part_boundary_bad"] = len(boundary_bad)
        if boundary_bad:
            msg = (f"[파트경계] 파트 경계 정렬 이상 {len(boundary_bad)}건: "
                   + " | ".join(boundary_bad[:5]))
            (critical if cleanup_delete else warnings).append(msg)

    # ── G5 step2_a1 상단 / step2_a1_btm 하단 기하 검사 ───────────────────
    flows = {fl["step"]: fl for fl in plan.get("flows", [])}
    if "step2_a1" in flows and "step2_a1_btm" in flows:
        st_top = _find_story_with_text(dump, _flow_probe_text(flows["step2_a1"]))
        st_btm = _find_story_with_text(dump,
                                       _flow_probe_text(flows["step2_a1_btm"]))
        if st_top and st_btm and st_top.get("b") and st_btm.get("b"):
            shared = set(st_top.get("pg") or []) & set(st_btm.get("pg") or [])
            if shared and st_top["b"][0] >= st_btm["b"][0]:
                msg = ("[상하반전] step2_a1(상단)이 step2_a1_btm(하단)보다 "
                       f"아래에 배치됨 (top {st_top['b'][0]} ≥ "
                       f"{st_btm['b'][0]})")
                (critical if pos_used else warnings).append(msg)
                stats["a1_swapped"] = True
            else:
                stats["a1_swapped"] = False
        elif st_top and st_btm:
            warnings.append("[상하배치] 덤프에 프레임 좌표 없음(구버전 덤프)"
                            " — 상/하단 검사 생략")

    # ── G19 어법수정 원고 step3 혼입 (W17 c11) ───────────────────────────
    # step3(실전문제) 스토리에 "1[asked]" 정답 괄호 표기가 다량이면
    # 구6스텝 'Step3 어법수정' 오라우팅 — 실전문제/변형 pool에는 이 표기가
    # 없다. step1_c2(빈칸어휘 정답지)는 같은 표기를 정당하게 쓰므로
    # 반드시 step3 플로우 스토리로 한정한다.
    if "step3" in flows:
        st3_story = _find_story_with_text(
            dump, _flow_probe_text(flows["step3"]))
        if st3_story is not None:
            sig_hits = sum(
                len(_RE_GRAMMAR_FIX_SIG.findall(_clean(p.get("t", ""))))
                for p in st3_story.get("paragraphs", []))
            stats["grammar_fix_sig_hits"] = sig_hits
            if sig_hits >= 5:
                critical.append(
                    f"[어법수정혼입] step3 스토리에 어법수정 정답 괄호 "
                    f"표기 {sig_hits}개 — 어법수정 원고가 실전문제로 "
                    f"오라우팅된 상태 (파일명 라우팅 확인)")

    # ── G9 미사용 업로드 원고 (W13 — 부분 침묵 유실 보고)
    #    + G16 스텝원고 미사용 critical 승격 (W17 c11) ─────────────────────
    if uploads_dir and os.path.isdir(uploads_dir):
        expected_unused, suspicious = find_unused_uploads(content,
                                                          uploads_dir)
        stats["unused_uploads_expected"] = expected_unused
        stats["unused_uploads"] = suspicious
        wt = ((content or {}).get("workbook_type") or "")
        tokens = (_STEP_CONTENT_TOKENS_EBS if wt == "EBS"
                  else _STEP_CONTENT_TOKENS)
        # W18 c17 — 같은 콘텐츠 가족의 파일이 이미 소비된 경우(예: 'Step1 C2
        # 빈칸어휘 정답지' 소비 + 'Step1 C2 빈칸어휘(개정)' 병존)는 부분
        # 침묵 유실이 아니라 변형본 짝 — critical 승격에서 제외(G9 warning
        # 유지). G16의 본래 표적은 '그 가족이 아예 미소비'(W17 c11).
        used_names = {_norm_fname(sd["filename"])
                      for sd in steps.values()
                      if isinstance(sd, dict) and sd.get("filename")}

        def _family_consumed(f):
            toks = [tok for tok in tokens if tok in _norm_fname(f)]
            return toks and all(any(tok in u for u in used_names)
                                for tok in toks)

        step_unused = [f for f in suspicious
                       if any(tok in _norm_fname(f) for tok in tokens)
                       and not _family_consumed(f)]
        other_unused = [f for f in suspicious if f not in step_unused]
        stats["unused_step_manuscripts"] = step_unused
        if step_unused:
            critical.append(
                f"[스텝원고미사용] 현행 스텝이 소화 가능한 원고 "
                f"{len(step_unused)}개가 사용되지 않음 (부분 침묵 유실): "
                + " | ".join(step_unused[:5]))
        if other_unused:
            warnings.append(
                f"[미사용원고] {len(other_unused)}개 파일이 어느 스텝에도 "
                f"사용되지 않음 (파일명 규칙 확인): "
                + " | ".join(other_unused[:5]))

    # ── G6 파싱 계층: 구조적 헤더 후보 미인식 (경고) ─────────────────────
    for key in _HEADER_STEPS:
        sd = steps.get(key)
        if not isinstance(sd, dict):
            continue
        paras = sd.get("paragraphs") or []
        cands = [i for i in range(len(paras))
                 if _is_struct_header_candidate(paras, i)]
        if not cands:
            continue
        recognized = 0
        for i in cands:
            t = _norm_header(paras[i].get("text") or "")
            if is_header_line(t) or is_a1_header(t) or t.startswith("["):
                recognized += 1
        if recognized == 0:
            warnings.append(
                f"[헤더미인식] {key}: 구조적 헤더 후보 {len(cands)}개 중 "
                f"인식 0개 — 새 헤더 형식 의심: "
                + (paras[cands[0]].get("text") or "")[:40])

    return {"ok": not critical, "critical": critical, "warnings": warnings,
            "stats": stats}
