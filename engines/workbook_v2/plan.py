"""워크북 v2 렌더 플랜 빌더 — v1 파서 산출(steps)을 플랜으로 변환.

스텝별 빌더 레지스트리 방식(단계 전환): 빌더가 있는 스텝만 v2가 렌더하고,
없는 스텝은 플랜에서 제외되며 커버리지 리포트에 '미지원'으로 남는다.
스타일 결정 = core/structure/style_map.json "workbook" 섹션 (실물 인벤토리 가드).

Step3는 Phase 2에서 심은 단락 kind 주석을 그대로 사용 — 스타일 결정이
데이터 룩업 한 줄이다 (v1 processStep3 480줄의 휴리스틱을 대체).

W2 (순수 텍스트 6스텝): v1 JSX의 GREP 치환/단락 삭제/패턴 스타일을
스토리 배치 전 파이썬 전처리로 이식 (engines/workbook/jsx/run.jsx의
processStep1A1/1B2/1C2/2A1/2A1Btm/2C1 대응). v1의 "프레임브레이크 삽입" =
빌더의 유닛 분할 (실행기 break_per_unit이 유닛 경계에 NEXT_FRAME 적용).

W3 (아이콘 4스텝): 단락 dict에 선택 필드 "icon"을 지원 —
  {"t": ..., "s": ..., "runs": [...],
   "icon": {"label": "TF 버튼", "pos": "end"|"start", "pad": " ",
            "mode": "dup"(기본)|"place"}}
실행기(core/jsx/workbook_flow.body.jsx)가 스타일/밑줄/브레이크 이후 마지막
패스에서 역순으로 findLabeledItem(label) 원본을 duplicate(또는 itemLink
place — v1 processStep2B1의 링크 place + 너비 스케일) 인라인 앵커 삽입.
pad는 아이콘과 본문 사이 간격 문자(end면 아이콘 앞, start면 아이콘 뒤).
스타일 "$BASIC"은 문서 내장 [기본 단락] 센티널 — 인벤토리 실물 스타일이
아니라 InDesign 문서 기본 스타일이므로 자동 생성 금지 규칙과 무관.

W4 (step1_c1 — 최난): v1 processStep1C1(run.jsx 1136~1648)의 이식.
  - 헤더 정규화 GREP 15+ → _sub_runs(밑줄 runs 오프셋 보존 치환)로 전처리
  - 프레임 분리 = v1 "FRAME BREAK 재적용" 섹션(실효 동작)의 유닛화:
      헤더(2번째+) → 유닛 {"page_break": true} = 실행기 NEXT_PAGE
      (EBS는 NEXT_FRAME = page_break 없음), 블록 내 첫 하단 스타일 단락
      → 일반 유닛 경계(NEXT_FRAME)
  - 화살표 답지 아이콘: C1 연속 블록 끝 뒤 빈 단락에 icon op
  - 발문("아래 주어진 문장이…") = 빌더가 텍스트 단락으로 생성 + 문제아이콘

유닛 확장 형식: 기존 유닛(단락 list) 외에 {"paras": [...], "page_break": true}
dict 형식 지원 — 실행기가 page_break 유닛 시작 단락에 NEXT_PAGE 적용.
"""
import json
import os
import re

from core.structure.header_detect import (HeaderSilenceError,
                                          detect_headers)
from core.structure.rules import Q_START_HINT as _RE_Q_START_HINT
from core.structure.style_resolver import resolve_style

_DIR = os.path.dirname(os.path.abspath(__file__))
STEP_MAP = json.load(open(os.path.join(_DIR, "step_map.json"),
                          encoding="utf-8"))


def _style(step_unit, kind, default_kind="P"):
    try:
        v = resolve_style("workbook", step_unit, kind)
    except KeyError:
        try:
            v = resolve_style("workbook", step_unit, default_kind)
        except KeyError:
            return None
    if isinstance(v, list):
        return v[0]
    return v


# ── Step3: kind 주석 기반 (질문/지문/선지/보기/조건/답란 전부 데이터 룩업) ──

# v1 processStep3 pass 2 — <보기>/<조건> 표기 정규화 (run.jsx 2197~2200)
_S3_GREPS = [
    (re.compile(r"<\s*보\s*기\s*>"), "<보기>"),
    (re.compile(r"<\s*조\s*건\s*>"), "<조건>"),
    (re.compile(r"\[\s*보기\s*\]"), "<보기>"),
    (re.compile(r"\[\s*조건\s*\]"), "<조건>"),
    # W50: CJK 꺾쇠/전각 이형 — 인쇄 표기도 책 관행("<보기>")으로 통일
    (re.compile(r"[〈《＜]\s*보\s*기\s*[〉》＞]"), "<보기>"),
    (re.compile(r"[〈《＜]\s*조\s*건\s*[〉》＞]"), "<조건>"),
    (re.compile(r"[〈《＜]\s*요\s*약\s*문\s*[〉》＞]"), "<요약문>"),
]
# v1 pass 10 — 번호(S3_NUM) 단락의 "숫자. " 접두 제거 (run.jsx 2423~2431)
_RE_S3_QNUM = re.compile(r"^\d+\.\s")
# W30-r15 (결함 5 — 실서비스 376b34d0 실증): 교과서 꼼꼼변형 실전문제의
# 출처 라인("공통영어2_YBM(김) 1과_03" / "… 1과_01~02" — 문항 끝 단독
# 단락, kind UNKNOWN → 지문 스타일로 인쇄됨). 완제품에 불필요 — 제거.
# 형태: <과목_출판사 토큰(밑줄 포함)> + 공백 + <N과_NN[~NN]> 전체 라인.
# 본문 영어 문장은 '_'가 붙은 선두 토큰 + 'N과_N' 꼬리를 동시에 갖지
# 않아 오매치 없음 (골든 코퍼스 전수 재빌드 diff 0으로 증명).
# W54: 출처 꼬리는 숫자형(03/01~02) 외에 한글 코너명형(딥러닝 등)도 있다
# (1bda7f01 실증: "공통영어2_미래김 1과_딥러닝"이 미매치 → 조건 박스에
# 흡수돼 인쇄). 12자 이하 무공백 꼬리로 한정 — 본문 문장은 공백/길이로 배제.
_RE_S3_TEXTBOOK_SRC = re.compile(
    r"^\S+_\S+\s+\d+과_(?:\d+(?:\s*~\s*\d+)?|[\w가-힣]{1,12})$")
# W61 (비상(황) 실증): step3 원고 선두 표제 — "영어 독해와 작문 비상(황)
# 1과 Step3 (74문항)". 교재/과 + Step 표기 + (N문항)이 한 줄에 오는
# 파일 표제라 완제품에 불필요(첫 문항 위에 지문 스타일로 인쇄됨).
_RE_S3_DOC_TITLE = re.compile(
    r"^.{0,40}?\d+\s*[과강]\s*(?:step\s*\d+|스텝\s*\d+).{0,20}$", re.I)

# ── W66 (사용자 지적 2026-08-14): 대괄호 라벨 = 구조 판정 ────────────────
# "[08강 - Exercise 05~06]"이 또 인쇄됐다. 구 규칙(_RE_S3_TYPE_MARKER /
# _RE_S3_EXERCISE_MARKER)은 "[N강 - Exercise N]" 같은 **형태를 열거하는
# 화이트리스트**라, 번호가 범위(05~06)로 바뀌는 것 하나에 무너진다 —
# W51에서 이미 같은 땜질을 했고 또 뚫렸다. 규칙을 뒤집는다.
#
#   기본값 = 제거. step3의 '단독 대괄호 라벨 라인'은 원고 편집용 인덱스
#   (강/과/Unit/Chapter/Exercise/Type/문항번호…)가 압도적 다수이고,
#   완제품에 인쇄될 이유가 없다. 인쇄돼야 하는 것만 보존한다:
#     K1 내용 블록 마커 — <보기>/[조건]/[요약문]/[정답]/[Answer] …
#     K2 지문 내부 라인 — 앞뒤가 영어 산문인 라벨 (실용문 "[Book Now]")
#     K3 기출 출처 표기 — 변형/시험코드/연월/시험명 (G11 인쇄 관행 계약)
#     K4 문장인 라인    — 종결부호·물음표가 있으면 라벨이 아니다
#     K5 서수가 없는 라벨 — 인덱스는 '번호를 매긴다'. 숫자도 없고 같은
#        꼴의 계열 변주(Type A/Type B)도 아니면 인덱스로 보지 않는다
#        (실용문 버튼 "[Book Now]" / EBS "[Gateway]" 보존).
#   새 표기(범위·오타·다른 교재의 새 라벨)가 와도 K1~K5에 안 걸리면
#   자동 제거된다 — 정규식을 더 추가할 필요가 없다.
_RE_S3_BRACKET_LABEL = re.compile(r"^\[([^\[\]]{1,60})\]$")
# K1 — 내용 블록 마커 (본문/답 영역의 의미 라벨). BOX_MARKERS(보기/조건)는
# rules에서 별도 검사하고, 여기서는 답/요약/해석 계열을 본다.
_RE_S3_LBL_CONTENT = re.compile(
    r"^(?:보기|조건|요약문?|요지|주제|정답|해답|답|해설|해석|풀이|"
    r"answer|key|note|hint|summary|words?|vocabulary)"
    r"\s*[A-Za-z0-9]{0,2}$|"
    # 문항에 인쇄되는 표시 — 배점/유형 태그 ("[3점]" "[서술형 2]")
    r"^\d+\s*점$|^(?:서술형|논술형|단답형|주관식|객관식)\s*\d*$", re.I)
# K3 — 기출 출처 표기 (완제품에 인쇄되는 관행 — gate G11과 같은 계약).
# 변형 접미("…_변형"), 시험 코드(202506H2), 연월(25년 6월), 시험명.
_RE_S3_LBL_ORIGIN = re.compile(
    r"변형|수능특강|수능완성|수능|모의고사|학력평가|학평|모평|교육청|평가원|"
    r"기출|\d{2}\s*년\s*\d{1,2}\s*월|\d{6}\s*[A-Za-z]\s*\d")
# K4 — 문장(발문/조건/본문 한 줄)이면 라벨이 아니다.
_RE_S3_LBL_SENTENCE = re.compile(
    r"[.?!。？]\s*$|시오|세요|십시오|합니다|입니다|하시오")
_RE_S3_LBL_ENGWORD = re.compile(r"[A-Za-z]{2,}")


_RE_S3_LBL_SENT_END = re.compile(r"[.!?][\"'”’\)\]]?\s*$")
_RE_S3_LBL_DIGIT = re.compile(r"\d")
# K5 — 계열 골격: 숫자→'#', 홀로 선 대문자→'@' (Type A / Type B 계열)
_RE_S3_LBL_SKEL_NUM = re.compile(r"\d+")
_RE_S3_LBL_SKEL_ALPHA = re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z])")
# W77 (사용자 지적 2026-08-27 — 올림포스 영어독해 6강): "[ Type A ]" 가
# 인쇄됐다. K5는 '서수가 없으면 인덱스가 아니다'인데 서수를 **숫자로만**
# 봤다. 인덱스는 숫자로도, 홀로 선 알파벳(A/B/C…)으로도 번호를 매긴다 —
# 같은 원고 안에 계열 변주(Type A/Type B)가 없어도 서수는 서수다.
# 홀로 선 대문자가 없는 라벨("[Book Now]" "[Gateway]")은 그대로 보존된다.
_RE_S3_LBL_ORDINAL = re.compile(r"\d|(?<![A-Za-z])[A-Z](?![A-Za-z])")


def _s3_label_skeleton(inner):
    s = _RE_S3_LBL_SKEL_NUM.sub("#", inner)
    return _RE_S3_LBL_SKEL_ALPHA.sub("@", s)


def _s3_label_series(step_data):
    """원고 전체에서 '계열로 변주되는' 대괄호 라벨 골격 집합 (K5).

    인덱스는 번호를 매긴다 — 같은 골격이 서로 다른 값으로 2개 이상 나오면
    (Type A / Type B, 01강 / 02강) 그 골격은 인덱스 계열이다. 같은 문구가
    그대로 반복되는 라벨(실용문 "[Book Now]")은 계열이 아니다."""
    seen = {}
    for group in ("normal", "short"):
        for item in step_data.get(group, []) or []:
            for p in item.get("paragraphs", []) or []:
                t = (p.get("text") or "").strip()
                m = _RE_S3_BRACKET_LABEL.match(t)
                if not m:
                    continue
                inner = m.group(1).strip()
                seen.setdefault(_s3_label_skeleton(inner), set()).add(inner)
    return set(k for k, v in seen.items() if len(v) > 1)


def _s3_is_prose(text):
    """영어 산문 줄인가 — 지문 내부 판정용 (K2)."""
    return len(_RE_S3_LBL_ENGWORD.findall(text or "")) >= 6


from core.structure.block_grammar import SUM_MARKER as _BG_SUM_MARKER

# 유형 표기가 '원고 관행'이라고 볼 최소 비율 (유형 표기 수 / 발문 수)
_S3_TYPE_LABEL_MIN_RATIO = 0.3


def _s3_type_label_idx(seq, R):
    """원고 문항 유형 표기 줄의 인덱스 집합 (출력 제거 대상).

    2026-08-28 사용자 지적(수특라이트영독 10강): "스텝3에 내용 파악, 서술형
    영작, 빈칸 이런 문제 유형들이 본문에 들어가 있다. 문제유형, 출처 같은 건
    전부 빠져야 돼." 원고는 문항마다 앞에 편집용 유형 표기를 다는데
    (`내용 파악` → `12. 다음 글의 내용과 …`) kind UNKNOWN 으로 떨어져 지문
    스타일로 인쇄됐고, <조건> 블록 뒤에 오면 조건으로까지 흡수됐다(`어법`).
    W76 의 `_s3_strip_qtype_tags` 는 **발문 줄 안에 붙은** 태그
    ("11번 어법  다음 글의 …") 전용이라 이 '독립 줄' 형태는 못 잡는다.

    세 층으로 판정한다 — 유형명 목록(화이트리스트)은 쓰지 않는다. '서술형
    어휘 완성'·'서술형 어법 수정'처럼 조합이 열려 있어 표기가 바뀔 때마다
    다시 새기 때문:
      ① 형태 — 문장부호·영문·숫자 없는 짧은 한글 명사구 (R.is_type_label_form)
      ② 위치 — 바로 다음 유의 단락이 발문
      ③ 원고 관행 — 그런 줄이 반복되고 발문 수 대비 충분히 많다
    ③ 덕분에 관행이 없는 원고에 우연히 낀 짧은 한글 한 줄은 지워지지 않는다.
    """
    meaning = [i for i, p in enumerate(seq)
               if (p.get("text") or "").strip()
               and (p.get("kind") or "") != "BLANK"]
    cand = set()
    qn = 0
    for x, i in enumerate(meaning):
        if (seq[i].get("kind") or "") in ("Q", "Q-INTRO"):
            qn += 1
        # 구조 역할이 **형태로 확정된** 줄만 제외한다. Box/Cond/Sum 은 마커
        # 전파로 붙는 kind 라 여기서 쓰면 안 된다 — <조건> 블록 뒤에 온
        # 유형 표기가 Cond 로 물들어 있어(실측 6개 중 2개) 그대로 인쇄됐다.
        if (seq[i].get("kind") or "") in ("A", "GH", "C", "AnsL", "SRC"):
            continue
        _bt = R.norm_brackets((seq[i].get("text") or "").strip())
        if (R.BOX_MARKERS["Box"].match(_bt)
                or R.BOX_MARKERS["Cond"].match(_bt)
                or _BG_SUM_MARKER.match(_bt)):
            continue        # 블록 마커(보기/조건/요약문)는 표기가 아니다
        if not R.is_type_label_form(seq[i].get("text") or ""):
            continue
        if x + 1 >= len(meaning):
            continue
        if (seq[meaning[x + 1]].get("kind") or "") not in ("Q", "Q-INTRO"):
            continue
        # 답표 열 머리 쌍("틀린 부분"/"수정")의 둘째 줄 방어 — 유형 표기는
        # 형제 없이 홀로 온다 (코퍼스 실측: '수정' 16건이 이 형태).
        if x > 0 and R.is_type_label_form(
                seq[meaning[x - 1]].get("text") or ""):
            continue
        cand.add(i)
    if len(cand) < 2 or len(cand) < _S3_TYPE_LABEL_MIN_RATIO * qn:
        return set()        # 원고 관행이 아님 — 건드리지 않는다
    return cand


def _s3_is_index_label(tclean, prev_text, next_text, R, series=()):
    """단독 대괄호 라벨이 '원고 편집용 인덱스'인가 (제거 대상).

    W66 — 형태 열거가 아니라 보존 조건(K1~K5)의 여집합으로 판정한다.
    prev/next는 지문 내부 라벨(K2) 판정용 이웃 단락 텍스트,
    series는 _s3_label_series가 뽑은 계열 골격 집합(K5)."""
    m = _RE_S3_BRACKET_LABEL.match(R.norm_brackets(tclean))
    if not m:
        return False
    inner = m.group(1).strip()
    if not inner:
        return False
    if not (_RE_S3_LBL_ORDINAL.search(inner)        # K5 서수 없는 라벨
            or _s3_label_skeleton(inner) in series):
        return False
    if _RE_S3_LBL_SENTENCE.search(inner):          # K4 문장
        return False
    if _RE_S3_LBL_CONTENT.match(inner):            # K1 내용 블록 마커
        return False
    if (R.BOX_MARKERS["Cond"].match(inner)         # K1 (보기/조건 이형)
            or R.BOX_MARKERS["Box"].match(inner)):
        return False
    if _RE_S3_LBL_ORIGIN.search(inner):            # K3 기출 출처
        return False
    if (_s3_is_prose(prev_text) and _s3_is_prose(next_text)
            and not _RE_S3_LBL_SENT_END.search((prev_text or "").strip())):
        # K2 지문 내부 라벨 — 앞뒤가 본문이고, 앞 문장이 '끝나지 않은'
        # 자리(실용문 버튼/제목 "…, or click / [Book Now] / This package…").
        # 문장이 끝난 자리의 라벨은 지문 사이 경계 = 인덱스다 (0645d4a7
        # 실증: 같은 지문 반복 사이의 "[01강 - Exercise 03]").
        return False
    if _s3_is_prose(inner):                        # 라벨이 아니라 문장
        return False
    return True
# v1 pass 5 번호/INTRO 휴리스틱 (run.jsx 2253~2272) — 분류기(kind)가 약한
# 판정(UNKNOWN/K/Cond)을 내린 단락에만 오버레이. v1 실물 dump 대조에서
# "(주관식) …쓰시오." / "…것은? [2-N]" 발문이 분류기 미인식으로 번호 스타일
# +번호 제거를 못 받는 16건이 실증됨 (교과서 80dd3fa2). v1의 조건 propagation
# 은 번호 스타일 단락을 덮지 않으므로(run.jsx 2417 break) Cond 포함이 파리티.
_RE_S3_KORQ = re.compile(r"[가-힣]\?")
_S3_WEAK_KINDS = {"UNKNOWN", "K", "Cond"}
# W16 c07 (D1) — [서술형 N]/[논술형 N] 접두 태그 발문 + 해요체("쓰세요")
# 발문 (리딩파워 유형편(완성) Unit17 실증: "[서술형 2] … 쓰세요. [출처]"가
# taxonomy·구조 폴백 모두 미인식 → 지문 스타일로 인쇄). 해요체는 해석(K)
# 문장과 충돌 가능 → 발문 시작 신호(Q_START_HINT)와 AND 결합.
_RE_S3_QTAG = re.compile(r"^\[(?:서술|논술)형\s*\d*\]")
_RE_S3_SEYO = re.compile(r"(?:쓰|하|고르|답하|완성하|바꾸|채우)세요")
# W18 c18 (D2) — 시작 신호 없는 해요체 발문 변형: "영어로 번역하세요
# [9강 1번]" (리딩파워 유형편 완성 기출 pool 실증 — 지문 스타일 인쇄) +
# 세로 e79f8af9 기출력 "11. (주관식) … 고르세요. [정답 2개]" 잠복(G13
# 확장 검출). 꼬리 [출처/태그]를 제거한 몸통이 세요-체 종결이면 발문.
_RE_S3_TAIL_TAG = re.compile(r"\s*\[[^\[\]]{1,40}\]\s*$")
_RE_S3_SEYO_END = re.compile(r"세요\s*[.?!]?\s*$")
# W16 c10 (D2) — 영단어(Word) kind 강등: 어휘 항목은 "word: 한글 뜻"이
# 원칙 (v1 실물 고2_25-6 덤프: 화자 라벨 "Minji:"/"A: …"·영문 제목·
# 안내문 필드 "Dates: …"는 전부 지문 스타일). 한글 뜻이 없거나 콜론 앞
# 머리가 1글자면 지문(P)으로 강등.
_RE_S3_HANGUL = re.compile(r"[가-힣]")
_RE_S3_WORD_BAD_HEAD = re.compile(r"^[A-Za-z]\s*[:：]")
# 대화문 화자 라벨 행("A: 노란색 코트를 … 누구야?") — 물음표가 있어도
# 발문이 아니라 대화 지문. 발문은 화자 라벨로 시작하지 않는다 (c10 실증:
# Word 오분류 수리 후 KORQ 오버레이가 대화행을 발문으로 승격하던 것 차단).
_RE_S3_SPEAKER = re.compile(r"^[A-Za-z][A-Za-z .]{0,12}[:：]")
# v1 pass 11 — 화살표 단독 단락 삭제 + 다음 단락 배경(S3_BG) (run.jsx
# 2433~2450). EBS Unit15 v1 실물 dump 대조에서 "↓" 4건 실증 (모의고사
# 코퍼스에도 19건 존재 — v1 파리티 회복).
_RE_S3_ARROW = re.compile(
    "^[⬇⇩↓↘⇓⬆↑⇧⇑️]+$")
# W39 결함 5: T/F 문항의 번호 괄호 영어 행 (선택 표기 꼬리 없는 근접
# 후보 지목용 — 침묵 강등 금지)
_RE_S3_TF_NEAR = re.compile(r"^\d{1,2}\s*\)\s+\S")
# W40 결함 3: 순서배열 선지 순열 행("(A) － (C) － (B)") — 세 라벨이
# 서로 다른 A/B/C 순열일 때만 (지문의 "(A) 문장" 항목과 형태로 구분).
# 구분자: ASCII/유니코드 대시류 + 전각 하이픈(－ U+FF0D — 0a5da924 실증).
_RE_S3_PERM_ROW = re.compile(
    r"^\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)$")
_S3_CIRCLED = ["①", "②", "③", "④", "⑤"]
# W39 결함 6: 발문의 "밑줄 친 <영어구>" 인용 — 조사(가/이/은/는/을/를/의)
# 앞까지의 비한글 연속. 원문자 나열("밑줄 친 ①~⑤ 중")과 구분하기 위해
# 영문자 필수. 인용구는 발문에서 밑줄로 인쇄된다 (실물 관행 — 6b66b750
# 실증: 함축의미 발문 인용구가 평문으로 인쇄).
_RE_S3_UL_QUOTE = re.compile(r"밑줄\s*친\s+([^가-힣]+)")


def _apply_ul_span(text, runs, start, end):
    """runs의 [start,end) 구간에 ul=True 부여 (기존 서식 run 분할 보존)."""
    base = runs or [{"t": text, "ul": False}]
    out = []
    pos = 0
    for r in base:
        t = r.get("t") or ""
        a, b = pos, pos + len(t)
        pos = b
        if not t:
            continue
        cuts = sorted({a, b, min(max(start, a), b), min(max(end, a), b)})
        for x, y in zip(cuts, cuts[1:]):
            if x >= y:
                continue
            seg = dict(r)
            seg["t"] = t[x - a:y - a]
            if x >= start and y <= end:
                seg["ul"] = True
            out.append(seg)
    return out


def _s3_underline_quotes(unit, st_q, st_p, st_bg, warnings):
    """W39 결함 6 — 발문이 '밑줄 친 <영어구>'를 인용하면 렌더에서 밑줄.

    (a) 발문 라인의 인용구 자체 (원고 runs 유무 무관 — 실물 관행),
    (b) 문항에 밑줄 run이 전혀 없으면 지문/배경에서 인용구 유일 일치
        위치에 부여. 대상 특정이 모호(0 또는 2+ 일치)하면 [경고]
        (임의 밑줄 금지)."""
    qi = [i for i, p in enumerate(unit) if p["s"] == st_q]
    for n, i in enumerate(qi):
        p = unit[i]
        m = _RE_S3_UL_QUOTE.search(p["t"])
        if not m:
            continue
        quote = m.group(1).rstrip("  '\"’”")
        # 영단어(2자+) 인용만 — "(A)"/"ⓐ~ⓖ" 류 표식 참조는 인용이
        # 아니라 본문 표식 지시라 제외 (r2c14/r4c03 전수 diff 실측)
        if len(quote) < 2 or not re.search(r"[A-Za-z]{2}", quote):
            continue
        s, e = m.start(1), m.start(1) + len(quote)
        if not any(r.get("ul") for r in _slice_runs(
                p.get("runs") or [{"t": p["t"], "ul": False}], s, e)):
            p["runs"] = _apply_ul_span(p["t"], p.get("runs"), s, e)
        # (b) 문항 범위 = 다음 발문 전까지의 지문/배경 본문
        hi = qi[n + 1] if n + 1 < len(qi) else len(unit)
        body = [q for q in unit[i + 1:hi] if q["s"] in (st_p, st_bg)
                or "지문" in q["s"] or "배경" in q["s"]]
        if any(r.get("ul") for q in body for r in q.get("runs") or []):
            continue          # 원고 밑줄 존재 — 그대로 신뢰
        # 문장/구 인용(3단어+ 또는 15자+)이고 본문이 이 문항 안에 있을
        # 때만 대상 탐지 — '윗글' 공유 지문 참조(본문이 앞 문항에 있음)는
        # 원고 밑줄에 위임 (임의 밑줄 금지 — r4c03 실측)
        if not body or (len(quote) < 15 and len(quote.split()) < 3):
            continue
        if re.match(r"\s*(?:윗\s*글|위\s*글)", p["t"]):
            continue    # '윗글' 참조 — 대상은 앞 공유 지문 (원고 위임)
        hits = [(q, q["t"].find(quote)) for q in body if quote in q["t"]]
        if len(hits) == 1 and hits[0][0]["t"].count(quote) == 1:
            q, at = hits[0]
            q["runs"] = _apply_ul_span(q["t"], q.get("runs"), at,
                                       at + len(quote))
        else:
            warnings.append(
                f"[밑줄] 발문 인용구의 본문 대상 특정 불가"
                f"({len(hits)}건 일치) — 임의 밑줄 미부여: "
                f"'{quote[:40]}'")


def _is_pua(ch):
    """hwp 사용자 영역(PUA) 문자 — BMP U+E000~F8FF + plane 15/16."""
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD
            or 0x100000 <= cp <= 0x10FFFD)


def _s3_arrow_para(text):
    """화살표 단독 단락 판정 — 리터럴 화살표 + PUA 인코딩 변형 (W14).

    hwp 심볼표의 요약 화살표(⇩)가 원고에 따라 리터럴이 아닌 사용자
    영역 문자(, \U000f0036 등)로 저장된다 (c05 모의고사 18건 /
    c06 리딩파워 기출 2건 실증). PUA 단독 단락은 InDesign에서 글리프
    없는 tofu로 인쇄되므로 화살표와 동일하게 삭제+다음 단락 배경 처리
    (게이트 G10이 출력 검사로 이중 방어)."""
    t = text.strip()
    if not t:
        return False
    if _RE_S3_ARROW.match(t):
        return True
    return all(_is_pua(ch) for ch in t)


# ── hwp 심볼 PUA 인쇄 매핑 (W20 D1 — c06 인라인 PUA 잠복 W14 (1) 해소) ──────
# hwp 문자표 심볼이 사용자 영역(PUA) 코드로 저장된 채 본문에 혼입되면
# InDesign에서 tofu로 인쇄된다 (인라인이라 화살표 단독 단락 삭제 경로도
# 못 잡음). 문맥 증거가 실증된 코드만 유니코드 정자로 치환한다 — 근거
# 없는 코드는 등재 금지 (G10이 warning으로 지목, 미등재 잠복: U+F09F
# 조건 불릿 / U+F000 인용부호 앞 공백류 / U+F081~F085 문장 마커).
#   U+F0852/U+F0853  겹따옴표 “ ” — c06 16강 "puts it, ␦Seventy-five
#                    … whole family.␦In other words" + c21 11강 "the
#                    ␦land of opportunity␦ nevertheless" (여닫이 짝 실증)
#   U+F0036/U+F003B/U+F0EA  요약 화살표 ⇩ 변형 — W14 D2 실증(c05 18건/
#                    c06 2건) + W20 모의고사 스텝3 전수 스캔 12폴더·
#                    리딩파워 pool 전부 요약 위치 단독 단락
# 전부 1:1(한 글자) 치환 — _map_chars가 runs 오프셋을 보존한다.
PUA_PRINT_TABLE = str.maketrans({
    "\U000f0852": "“", "\U000f0853": "”",
    "\U000f0036": "⇩", "\U000f003b": "⇩", "": "⇩",
})


def apply_pua_print_map(obj):
    """content 단락 트리에 PUA 인쇄 매핑을 적용한 사본 반환 (원본 무변형).

    "text" 키를 가진 dict는 _map_chars로 텍스트+runs를 함께 치환한다
    (1:1 길이 보존 — 밑줄 runs 오프셋 유지). 매핑에 없는 PUA는 그대로
    통과 (플랜 화살표 판정/G10 게이트가 각자 처리)."""
    if isinstance(obj, list):
        return [apply_pua_print_map(x) for x in obj]
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            out = dict(obj)
            mapped = _map_chars(obj, PUA_PRINT_TABLE)
            out["text"] = mapped["text"]
            if obj.get("runs"):
                out["runs"] = mapped["runs"]
            return out
        return {k: apply_pua_print_map(v) for k, v in obj.items()}
    return obj


# ── 아래첨자 인쇄 매핑 (W23 r13 F3 — 사용자 실측: "₂ 같은 글리프가 폰트
# 때문에 안 보임") ──────────────────────────────────────────────────────────
# 아래첨자 숫자(U+2080~2089, 예: CO₂)는 이 계열 내지의 본문 폰트에 글리프가
# 없어 tofu/공백으로 인쇄된다 (job 6c1430c3 실사용 3차 피드백 — 코퍼스에도
# 06f4b2c2 306건 / 0a5da924 32건 잠복, W11부터 존재). 등가 표기로 치환:
# ASCII 숫자 + 아래첨자 서식 run(sub) — 실행기가 Position.SUBSCRIPT를 직접
# 적용한다 (문자스타일 아님 — seseospecial W7의 underline 속성 직접 적용
# 전례, 자동 생성 금지 규칙과 무관. 어떤 폰트에서든 렌더 가능).
# 게이트 G29가 이 매핑 등재 문자의 출력 잔존을 critical로 소급 검출한다
# (G10 확장의 PUA 테이블과 동일 패턴 — 잔존 = 매핑 미적용 출력).
SUBSCRIPT_PRINT_TABLE = {chr(0x2080 + i): str(i) for i in range(10)}


def _apply_sub_para(para):
    """단락 1개에 아래첨자 매핑 적용 — 텍스트는 ASCII 숫자로, 해당 위치는
    runs에 {"sub": True} 서식 run으로 분리 (1:1 길이 보존 — 밑줄 runs
    오프셋 유지. runs가 없던 단락은 전체를 비밑줄 run으로 실체화)."""
    text = para.get("text") or ""
    idxs = [i for i, ch in enumerate(text) if ch in SUBSCRIPT_PRINT_TABLE]
    if not idxs:
        return para
    runs = para.get("runs") or [{"t": text, "ul": False}]
    pieces = []
    prev = 0
    for i in idxs:
        if i > prev:
            pieces.extend(_slice_runs(runs, prev, i))
        base = _slice_runs(runs, i, i + 1)
        seg = dict(base[0] if base else {"ul": False})
        seg["t"] = SUBSCRIPT_PRINT_TABLE[text[i]]
        seg["sub"] = True
        pieces.append(seg)
        prev = i + 1
    if prev < len(text):
        pieces.extend(_slice_runs(runs, prev, len(text)))
    out = dict(para)
    out["text"] = "".join(SUBSCRIPT_PRINT_TABLE.get(ch, ch) for ch in text)
    out["runs"] = pieces
    return out


def apply_subscript_print_map(obj):
    """content 단락 트리에 아래첨자 인쇄 매핑을 적용한 사본 반환 (원본
    무변형 — apply_pua_print_map과 동일 계층·동일 순회)."""
    if isinstance(obj, list):
        return [apply_subscript_print_map(x) for x in obj]
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            return _apply_sub_para(obj)
        return {k: apply_subscript_print_map(v) for k, v in obj.items()}
    return obj


# ── 글리프 인쇄 매핑 (W30 후속 — r15 c25 실측: ❮❯ 12건 글리프커버리지
# warning) ──────────────────────────────────────────────────────────────────
# 헤비 꺾쇠 ❮(U+276E)/❯(U+276F)는 이 계열 내지 본문 폰트(Noto Sans CJK KR)
# cmap에 글리프가 없어 tofu/미표시로 인쇄된다 (core.fontcov 실측 — Black/
# Bold/DemiLight/Light/Medium/Regular/Thin 전 7웨이트 미지원. r15 c25
# step3 실전문제 지문의 삽입 문장 표기 12건). W23 SUBSCRIPT_PRINT_TABLE
# 전례대로 지원 실측된 등가 문자로 플랜 계층 치환: 홑꺾쇠 〈(U+3008)/
# 〉(U+3009) — 전 7웨이트 커버 실측 (‹›(U+2039/A)·《》(U+300A/B)·＜＞
# (U+FF1C/E)도 커버되나 원표기와 시각적으로 가장 가까운 홑꺾쇠 채택,
# ‹›는 반각이라 삽입 문장 강조 표기에 과소).
#
# 단, 아래첨자/PUA 매핑과 달리 **빌더 이후**에 적용한다 — 1A1 빌더가
# ❮❯→[]를(_A1_TABLE), 1A2 빌더가 ❮T/F❯ 토큰 제거를 소비하므로 빌더 전에
# 치환하면 해당 로직이 무력화된다. 빌더 산출 유닛에 남은 잔존(=그대로
# 인쇄될 문자)에만 적용. 1:1(한 글자) 치환 — 텍스트/runs 오프셋 보존.
# content 원본은 무변형 (골든/파서 산출 보존 — W20 PUA 전례).
# 게이트 G29가 등재 문자의 출력 잔존을 소급 검출한다.
# W? (2026-08-06 실측 — 선택 워크북 조판 게이트 warning 55건):
# ⦁(U+2981 Z NOTATION SPOT)도 Noto Sans CJK KR cmap 미지원(core.fontcov
# 실측 False). 조건/보기 블록의 항목 표시로 쓰여 tofu 로 인쇄된다.
# 커버 실측 결과 •(U+2022) True / ●(U+25CF) True / ∙(U+2219) False —
# 원표기(중간 크기 점)와 가장 가까운 •(U+2022) 채택.
GLYPH_PRINT_TABLE = {"❮": "〈", "❯": "〉", "⦁": "•"}
_GLYPH_PRINT_TRANS = str.maketrans(GLYPH_PRINT_TABLE)


def apply_glyph_print_map_units(units):
    """빌더 산출 유닛 리스트에 글리프 인쇄 매핑을 in-place 적용.

    유닛은 빌더가 갓 생성한 객체(content와 비공유)라 in-place가 안전하다.
    runs는 해당 단락에 등재 문자가 있을 때만 재작성 (1:1 길이 보존)."""
    for u in units:
        for p in unit_paras(u):
            t = p.get("t") or ""
            if not any(ch in t for ch in GLYPH_PRINT_TABLE):
                continue
            p["t"] = t.translate(_GLYPH_PRINT_TRANS)
            if p.get("runs"):
                p["runs"] = [
                    dict(r, t=r["t"].translate(_GLYPH_PRINT_TRANS))
                    if isinstance(r.get("t"), str) else r
                    for r in p["runs"]]
    return units


def _s3_effective_kind(kind, text):
    # W16 D2 — 영단어 강등 (분류기 수리와 이중 방어: content-only 코퍼스
    # 재실행은 구버전 kind 주석을 그대로 쓰므로 플랜 계층에서도 강등).
    if kind == "Word":
        t = text.strip()
        if not _RE_S3_HANGUL.search(t) or _RE_S3_WORD_BAD_HEAD.match(t):
            return "P"
        return kind
    if kind not in _S3_WEAK_KINDS:
        return kind
    if _RE_S3_SPEAKER.match(text.strip()):
        return kind                     # W16 — 대화 화자 라벨 행은 발문 아님
    if _RE_S3_QTAG.match(text.strip()):
        return "Q"                      # W16 D1 — [서술형 N] 접두 발문
    if _RE_S3_KORQ.search(text):
        return "Q"
    if "다음 글을 읽고 물음에" in text:
        return "Q-INTRO"
    if "시오" in text:
        return "Q"
    if _RE_S3_SEYO.search(text) and _RE_Q_START_HINT.match(text.strip()):
        return "Q"                      # W16 D1 — 해요체 발문 (시작 신호 AND)
    from core.structure import block_grammar as _BG
    if _BG.is_english_question(text):
        return "Q"                      # W38 결함 5 — 영어 지시문 발문
                                        # (번호 + 명령형/WH — 파서 수리와
                                        # 이중 방어, 구 kind 주석 재실행용)
    core = text.strip()
    while True:                         # W18 D2 — 꼬리 [출처/태그] 제거
        nx = _RE_S3_TAIL_TAG.sub("", core)
        if nx == core:
            break
        core = nx
    if (core != text.strip() and _RE_S3_SEYO.search(core)
            and _RE_S3_SEYO_END.search(core)):
        return "Q"                      # W18 D2 — 해요체 + 꼬리 태그 발문
    return kind


def _ansline_fields(eff, arrow_bg=False):
    """답란(AnsL) 단락의 폴백/브릿지 필드 (W45).

    사용자 확정 스펙: 답란은 **답란 전용 스타일 `S_답란`**(지문 스타일 복제 +
    들여쓰기 0)로 인쇄한다. 완성본 다수가 답란을 '지문 스타일'로 갖고 있던 건
    의도가 아니라 회피였다 — 선지 스타일의 들여쓰기 때문에 답란 정렬이
    깨져서 손으로 바꾼 것 (역학습 W44, 61건/13문서).

    조판 템플릿에 `S_답란`이 아직 없을 수 있으므로 fail-open:
      s     = "STEP 03 > S_답란"          (1선)
      s_fb  = "STEP 03 > S_선지 올림포스"  (템플릿에 s가 없을 때 렌더 폴백)
      ind0  = True                        (폴백을 쓴 경우에만 들여쓰기 0
                                           로컬 오버라이드 — 브릿지)
    JSX(workbook_flow / workbook_sero_flow)가 s→s_fb 순으로 해석하고,
    s_fb를 쓴 단락에만 ind0를 적용한다 (S_답란이 있으면 오버라이드 없음)."""
    if eff != "AnsL" or arrow_bg:
        return {}
    fb = _style("STEP3", "AnsL@fallback", default_kind="C")
    if not fb:
        return {}
    return {"s_fb": fb, "ind0": True}


_STEP3_SET_INTRO = "다음 글을 읽고 물음에 답하시오."
_STEP3_SET_INTRO_KEY = "물음에 답하시오"
# W54: 문장삽입/무관문장 지문의 ①~⑤ 위치 마커 (밑줄제거 스타일 판정용)
_RE_S3_NUM_CIRCLED = re.compile(r"[①②③④⑤]")


def _s3_p_no_underline_style():
    """스타일맵 STEP3.P 리스트의 '밑줄제거' 변형 (없으면 None)."""
    try:
        v = resolve_style("workbook", "STEP3", "P")
    except KeyError:
        return None
    if isinstance(v, list):
        for s in v:
            if "밑줄제거" in s:
                return s
    return None

# W53 (배재1 워크북01 p69 실측 2026-08-12): 지문 단락 끝에 **다음 문항의
# 발문**이 줄바꿈 없이 이어붙어 한 단락이 된다 ("…a lot of fun.1. 다음 글의
# 주제로 가장 적절한 것은?"). 그 문항은 번호 스타일을 못 받아 지문 꼬리에
# 묻히고 이후 문항 번호가 하나씩 밀린다. 원고 자체가 붙어 오는 경우
# (꼼꼼변형 파일 경계·조판자 편집 등 상류가 무엇이든) 플랜에서 되돌린다.
#   조건: 문장부호로 끝난 뒤 → 번호 + 한글 발문 도입어. 앞부분이 40자
#   이상(라벨·선지 오분리 방지)일 때만 자른다.
_RE_S3_MERGED_Q = re.compile(
    r"(?<=[.!?\"'”’\)])\s*"
    r"(?=\d{1,3}\.\s*(?:다음|밑줄|윗\s*글|위\s*글|주어진|아래|글의|"
    r"<\s*보기\s*>))")


def _s3_split_merged_questions(paragraphs, warnings):
    """지문에 이어붙은 발문을 별도 단락으로 분리 (W53 — 가산 전용)."""
    out = []
    for p in paragraphs:
        text = p.get("text") or ""
        ms = [m for m in _RE_S3_MERGED_Q.finditer(text) if m.start() >= 40]
        if not ms:
            out.append(p)
            continue
        runs = p.get("runs") or []
        spans, prev = [], 0
        for m in ms:
            spans.append((prev, m.start()))
            prev = m.end()
        spans.append((prev, len(text)))
        for idx, (a, b) in enumerate(spans):
            if not text[a:b].strip():
                continue
            seg = dict(p)
            seg["text"] = text[a:b]
            seg["runs"] = _slice_runs(runs, a, b) if runs else []
            if idx > 0:                     # 뒤쪽 조각 = 새 문항 발문
                seg["kind"] = "Q"
                seg.pop("q_code", None)
            out.append(seg)
        warnings.append("step3: 지문 끝에 이어붙은 발문 %d개 분리 "
                        "(문항 병합 방어 — W53)" % len(ms))
    return out


# ── W75: 원고 답표(hwp 표)가 평탄화된 '라벨 셀 + 기입 셀' 쌍 ────────────────
# 사용자 지적 2026-08-26: "서술형 문제에 abcd 이런 건 답란으로 들어가야 되는데
# 지문으로 들어가있고 답 쓸 수 있는 밑줄도 없다. 단, abcd가 들어갈 경우 밑줄
# 이런 식으로 하면 선지 헤더나 다른 데에 잘못 들어가니까 그런 방식은 안 된다."
#
# 그래서 표기(ⓐ/ⓑ)가 아니라 **원고 표의 구조**로 잡는다. hwp 답표가 평탄화되면
# 라벨 셀과 기입 셀이 각각 한 단락이 되는데, 기입 셀은 '공백만 있고 비어 있지는
# 않은' 단락(' ')이라 단락 경계의 빈 줄('')과 구분된다:
#     ⓐ        ← 라벨 셀
#     ' '       ← 기입 셀 (답 쓰는 칸)
#     ⓑ
#     ' '
# 선지 헤더("ⓐ  ⓑ  ⓒ" 한 줄 + 다음 줄이 선지)는 뒤에 기입 셀이 없으므로
# 이 판정에 걸리지 않는다 — W72 결함의 재발 경로를 원천 차단한다.
_RE_S3_CELL_FILL = re.compile(r"^[\s\u00a0\u3000]+$")
# 기입 셀이 **빈 칸으로 접혀** 라벨 줄에 붙어 나온 형태 (2026-08-28 실증,
# 수특라이트영독 10강): 원고 hwp 2열 표 `번호 | 수정안` 의 답 행이
#   번호                     수정안     ← 열 머리
#   (    ) :                            ← 기입 줄 (뒤 칸이 비어 통째로 접힘)
# 로 추출된다. W75 는 '라벨 셀 + 공백만 있는 다음 단락' 쌍을 보는데 여기는
# 그 다음 단락이 아예 없어(빈 칸이 사라져) 답란 실물화가 안 걸렸다.
# 라벨이 콜론으로 끝나고 뒤에 쓸 내용이 없으면 그 줄 자체가 기입 줄이다.
_RE_S3_CELL_COLON = re.compile(
    r"^\s*(?:[(（]\s*[)）]|[①-⑮ⓐ-ⓩⒶ-Ⓩ㉠-㉭]|\d{1,2}\s*[.)]?)?"
    r"\s*[:：]\s*$")


def _s3_is_kor_hdr_cell(t):
    """답표 **열 머리** 셀인가 (한글 짧은 라벨 — '틀린 부분'/'수정'/'번호')."""
    t = (t or "").strip()
    if not (1 <= len(t) <= 12):
        return False
    if not re.search(r"[가-힣]", t):
        return False
    if re.search(r"[A-Za-z0-9]", t):
        return False
    return not re.search(r"[.?!,:;]|시오|세요", t)


def _s3_answer_cell_idx(seq):
    """라벨 셀(= 답란으로 실물화할 단락) 인덱스 집합."""
    out = set()
    n = len(seq)
    # ① 기입 칸이 접힌 콜론형 ("(    ) :") — 답표 열 머리 뒤에 오거나
    #    형제 행이 2줄 이상 이어질 때만 (문장 중간의 콜론 줄 오탐 차단).
    meaning = [i for i in range(n) if (seq[i].get("text") or "").strip()]
    x = 0
    while x < len(meaning):
        if not _RE_S3_CELL_COLON.match(
                (seq[meaning[x]].get("text") or "").strip()):
            x += 1
            continue
        y = x
        while y < len(meaning) and _RE_S3_CELL_COLON.match(
                (seq[meaning[y]].get("text") or "").strip()):
            y += 1
        head = (x > 0 and _is_anslabel_head(
            (seq[meaning[x - 1]].get("text") or "").strip()))
        if head or (y - x) >= 2:
            # 원고가 이미 밑줄 친 기입 칸을 갖고 있으면 그대로 둔다 —
            # 원고 길이가 관행이고, 우리 칸 수로 덮으면 기존 산출물이
            # 짧아진다 (b56bbc2f 등 4잡 A/B 실측: 46칸 → 35칸).
            out.update(i for i in meaning[x:y]
                       if not any(r.get("ul")
                                  for r in (seq[i].get("runs") or [])))
        x = y
    for i in range(n - 1):
        t = (seq[i].get("text") or "")
        tc = t.strip()
        # 라벨 셀은 표의 '머리 칸'이라 아주 짧다 (ⓐ / 답 / (1) / ①).
        # 길이를 넉넉히 주면 보기 단어('turning')·조건 항목('- 총 12단어')·
        # 표제('Unit 18')처럼 뒤에 우연히 공백 셀이 오는 줄까지 걸린다
        # (코퍼스 실측 5잡).
        if not tc or len(tc) > 3:
            continue
        if seq[i].get("kind") in ("Box", "Cond", "Sum", "GH", "A", "C"):
            continue        # 보기/조건/요약 블록 내용물은 답표 셀이 아니다
        if re.search(r"[.?!]\s*$|시오|세요", tc):
            continue
        if not re.sub(r"[()\[\]{}\s_]", "", tc):
            continue        # '(   )' 처럼 내용 없는 셀은 라벨이 아니다
        nt = seq[i + 1].get("text") or ""
        if nt == "" or not _RE_S3_CELL_FILL.match(nt):
            continue        # 바로 다음이 기입 셀(' ')이 아니면 표가 아니다
        prev = None
        for k in range(i - 1, -1, -1):
            if (seq[k].get("text") or "").strip():
                prev = (seq[k].get("text") or "").strip()
                break
        if prev is not None and _s3_is_kor_hdr_cell(prev) \
                and _s3_is_kor_hdr_cell(tc):
            continue        # 열 머리 2줄('틀린 부분'/'수정') — 답표 op 담당
        out.add(i)
    return out


# ── W76: STEP3 발문 앞 유형 태그 / 꼬리 지시문 / 주어진 문장 라벨 ───────────
# 사용자 지적 2026-08-26:
#   ① "앞에 왜 번호랑 어법, 문맥상 어휘 이런 게 들어갔어 … 발문만 들어가면 돼"
#   ② "[주어진 문장] 이건 필요없고 주어진 문장에 단락스타일 배경만 잘 입혀지면 돼"
#   ③ "갑자기 뭔 고르시오. 발문이 들어가?" (지문 뒤 ※ 꼬리 지시문)
# 원고(통합변형문제)는 발문을 "<N번> <유형명>␣␣<발문>" 으로 적고, 문항 끝에
# "※ ①~⑤ 중 … 고르시오." 를 한 줄 더 붙인다. 셋 다 조판에는 없어야 한다.
_RE_S3_QTYPE_TAG = re.compile(
    r"^\s*(?:\d{1,3}(?:\s*[~-]\s*\d{1,3})?\s*번\s*)?"
    r"(?:[가-힣][가-힣\s]{0,11})\s{2,}(?=\S)")
# 유형 태그를 벗긴 나머지가 '진짜 발문 시작'이어야 한다 (rules.Q_START_HINT
# 와 같은 눈) — 그래야 "다음 글을 읽고␣␣물음에 답하시오." 같은 안내문의
# 가운데 두 칸을 태그 경계로 오인하지 않는다.


def _s3_strip_qtype_tags(pre, q_effs=("Q",)):
    """발문 앞 유형 태그 제거 — 문서 안에서 3회 이상 반복될 때만."""
    from core.structure import rules as R
    hits = []
    for row in pre:
        if row["eff"] not in q_effs:
            continue
        t = row["tclean"]
        m = _RE_S3_QTYPE_TAG.match(t)
        if not m:
            continue
        rest = t[m.end():].strip()
        if not rest or not R.Q_START_HINT.match(rest):
            continue
        hits.append((row, m.end()))
    if len(hits) < 3:
        return 0
    for row, cut in hits:
        raw = row["text"]
        off = len(raw) - len(raw.lstrip())        # 원문 선두 공백 보정
        row["text"], row["runs"] = _cut_span(raw, row["runs"], 0, off + cut)
        row["tclean"] = row["text"].strip()
    return len(hits)


def _s3_drop_tail_directives(pre, q_effs=("Q",)):
    """지문 뒤 꼬리 지시문(※ …) 제거 — 자기 본문이 없는 발문만."""
    drop = []
    n = len(pre)
    for i, row in enumerate(pre):
        if row["eff"] not in q_effs:
            continue
        if not _RE_S3_TAIL_DIRECTIVE.match(row["tclean"]):
            continue
        if _STEP3_SET_INTRO_KEY in row["tclean"]:
            continue        # 세트 머리 안내문("※ 다음 …물음에 답하시오.")
        # 꼬리 지시문은 **자기 문항의 지문 뒤**에 온다. 직전 유의 단락이
        # 그 문항의 내용(지문/어휘/보기/조건/답란)일 때만 꼬리로 본다 —
        # 선지 뒤/문서 머리에 오는 ※ 는 다음 세트의 머리 안내문이다
        # (코퍼스 65cf0265 '※ 다음 도표를 보고 물음에 답하시오.' 실증).
        _prev = None
        for k in range(i - 1, -1, -1):
            if pre[k]["tclean"]:
                _prev = pre[k]
                break
        if _prev is None or _prev["eff"] not in (
                "P", "P-CONTEXT", "Word", "Box", "Cond", "Sum",
                "Ans", "AnsL", "SRC", "UNKNOWN"):
            continue
        body = False
        for j in range(i + 1, n):
            if pre[j]["eff"] in ("Q", "Q-INTRO"):
                break
            if pre[j]["tclean"]:
                body = True
                break
        if not body:
            drop.append(i)
    for i in reversed(drop):
        del pre[i]
    return len(drop)


def build_step3(step_data):
    """step3 데이터 {normal:[{question_num, paragraphs}], short:[...]} → 유닛.

    W38 — 블록 문맥 오버레이 (core.structure.block_grammar): 파서 kind
    주석이 구버전(콘텐츠-only 코퍼스 재실행)이어도 <조건>/[요약문] 블록
    문맥이 라인 판정을 제약하도록 플랜 계층에서 같은 규칙을 적용한다
    (파서 수리와 이중 방어 — W16 D2 전례). 유닛별 최종 판정 시퀀스는
    block_grammar.validate_sequence 하드 불변식으로 검증해 [경고] 지목.

    W39 — 유형 주도 슬롯 배정 (파서와 이중 방어): 1패스(기존 오버레이)로
    eff를 확정한 뒤, 2패스에서 발문 유형의 기대 슬롯(주어진 블록)을 형태
    신호로 배정한다. 배정 불가 단락은 침묵 강등하지 않고 [경고]로 지목."""
    from core.structure import block_grammar as BG
    from core.structure import rules as R
    st_q = _style("STEP3", "Q")
    units = []
    warnings = []
    lbl_series = _s3_label_series(step_data)     # W66 K5 — 계열 골격
    for group in ("normal", "short"):
        for item in step_data.get(group, []) or []:
            arrow_pending = False
            in_cond = False          # W38: <조건> 블록 열림 상태
            cond_no = 1              # 다음 조건 항목 번호 기대값
            sum_bg = False           # W38: [요약문] 배경 전파 상태
            pre = []                 # 1패스 산출 (슬롯 배정 전)
            seq = _s3_split_merged_questions(
                item.get("paragraphs", []), warnings)
            ans_cells = _s3_answer_cell_idx(seq)      # W75
            # 원고 문항 유형 표기("내용 파악"/"서술형 영작"/"빈칸") 제거 —
            # 블록 오버레이 전에 빼야 <조건> 뒤 표기가 조건으로 흡수되지 않는다
            _type_idx = _s3_type_label_idx(seq, R)
            if _type_idx:
                warnings.append("step3: 원고 문항 유형 표기 %d줄 제거"
                                % len(_type_idx))
            for _pi, p in enumerate(seq):
                if _pi in _type_idx:
                    continue
                text = p.get("text", "")
                kind = p.get("kind") or "UNKNOWN"
                tclean = text.strip()
                if _pi in ans_cells:
                    # W75: 원고 답표의 라벨 셀 → 답란 행(라벨 + 밑줄 칸).
                    _blank = " " * _S3_ANSROW_SPACES
                    pre.append({
                        "text": tclean + " " + _blank, "tclean": tclean,
                        "kind": kind, "eff": "AnsL", "arrow_bg": False,
                        "q_code": None,
                        "runs": [{"t": tclean + " ", "ul": False},
                                 {"t": _blank, "ul": True}]})
                    continue
                if p.get("image"):
                    # W77: 원고 그림(도표/그래프) — 본문 흐름의 제자리에
                    # 표시만 남긴다. 슬롯 배정 패스는 그림을 모르므로
                    # 아래에서 이웃 행으로 옮겨 붙인다(_s3_attach_images).
                    pre.append({"text": "", "tclean": "", "kind": "IMG",
                                "eff": "_IMG", "arrow_bg": False,
                                "q_code": None, "runs": [],
                                "image": p["image"]})
                    continue
                if kind in ("GH", "A", "BLANK"):
                    continue          # 제거 대상 (style_map에서 null)
                if _s3_arrow_para(text):
                    arrow_pending = True     # v1 pass 11: 화살표 단락 삭제
                    continue
                if _RE_S3_TEXTBOOK_SRC.match(tclean):
                    continue    # W30-r15: 교과서 실전문제 출처 라인 제거
                                # (결함 5 — 배경 대기(arrow_pending)는
                                # SRC 마커와 동일하게 소비하지 않고 통과)
                if _s3_is_index_label(
                        tclean,
                        (seq[_pi - 1].get("text") or "") if _pi else "",
                        (seq[_pi + 1].get("text") or "")
                        if _pi + 1 < len(seq) else "", R, lbl_series):
                    continue    # W66: 원고 편집용 대괄호 인덱스 제거
                                # (구 W51 Type/Exercise 화이트리스트 대체)
                if _RE_S3_DOC_TITLE.match(tclean):
                    continue    # W61: 원고 선두 표제(교재/과/StepN) 제거
                # W76 ②: "[주어진 문장] …" 라벨은 마커지 내용이 아니다 —
                # 벗겨야 배경(주어진 문장 박스) 형태 판정이 걸린다.
                _mgl = BG.GIVEN_LABEL_PREFIX.match(text)
                if _mgl and not text[_mgl.end():].strip():
                    continue    # 2026-08-28 사용자 지적: 라벨이 **단독 줄**로
                                # 오는 원고 — 벗길 내용이 없으니 줄째 뺀다
                                # (W76 ②는 '라벨+내용' 한 줄만 처리해
                                #  단독 줄은 지문 스타일로 인쇄됐다)
                if _mgl and text[_mgl.end():].strip():
                    text, p_runs = _cut_span(text, p.get("runs") or [],
                                             0, _mgl.end())
                    tclean = text.strip()
                    p = dict(p, text=text, runs=p_runs)
                eff = _s3_effective_kind(kind, text)
                # W50: 마커 판정용 괄호 이형 정규화 (표기는 tclean 보존)
                tmark = R.norm_brackets(tclean)
                # ── W38 블록 문맥 오버레이 ──────────────────────────────
                if BG.SUM_MARKER.match(tmark):
                    eff = "Sum"
                    sum_bg = True
                    in_cond = False
                elif sum_bg:
                    # 구 kind 주석 방어 (W39): 꺾쇠형 <요약문> 시절 Box로
                    # 주석된 요약 문장도 배경으로 — 단 마커 라인(<보기> 등
                    # 새 블록 진입)은 전파 종료 (stale Box 콘텐츠 한정).
                    stale_box = (eff == "Box"
                                 and not R.BOX_MARKERS["Box"].match(tmark)
                                 and not R.BOX_MARKERS["Cond"].match(tmark)
                                 and not R.C_START.match(tclean)
                                 and not R.C_AB_HEADER.match(tclean))
                    if eff in ("P", "K", "UNKNOWN") and tclean or stale_box:
                        eff = "P-CONTEXT"
                    else:
                        sum_bg = False
                if R.BOX_MARKERS["Cond"].match(tmark):
                    in_cond = True
                    cond_no = 1
                    sum_bg = False
                elif in_cond:
                    # W39 결함 3: 블록 안 단어 나열은 조건 내용물 (구
                    # kind 주석 P/UNKNOWN/C 방어 — 파서 수리와 이중)
                    if eff in ("P", "UNKNOWN", "Word", "C", "K") \
                            and BG.is_cond_wordlist(tclean):
                        eff = "Cond"
                    elif (R.COND_BLOCK_END.search(tclean)
                            or eff in ("Q-INTRO", "GH", "A", "Ans",
                                       "Box", "Sum", "C")):
                        in_cond = False
                    elif eff == "Q":
                        take, cond_no = BG.cond_item_take(tclean, cond_no)
                        if take:
                            eff = "Cond"   # 블록 문맥 우선 — 조건 항목
                        else:
                            in_cond = False   # 진짜 발문 = 블록 종료
                    elif eff == "Cond":
                        cond_no = BG.cond_item_seen(tclean, cond_no)
                # v1 pass 11: 화살표 다음 단락 → 배경(S3_BG). 출처
                # 마커(SRC)는 배경을 소비하지 않고 통과 — 배경은 마커
                # 다음 실제 요약문/주어진 문장에 부여 (W15 c04).
                arrow_bg = False
                if arrow_pending and kind != "SRC":
                    arrow_bg = True
                    arrow_pending = False
                pre.append({"text": text, "tclean": tclean, "kind": kind,
                            "eff": eff, "arrow_bg": arrow_bg,
                            "q_code": p.get("q_code"),
                            "runs": p.get("runs") or []})

            # ── 2패스: 유형 주도 슬롯 배정 (W39) ────────────────────────
            # W76: 발문 앞 유형 태그 제거 + 꼬리 지시문(※) 제거 — 슬롯
            # 배정 앞에서 (발문 본문이 정리돼야 유형 판정이 정확하다)
            _s3_attach_images(pre, warnings)
            _n_tag = _s3_strip_qtype_tags(pre)
            if _n_tag:
                warnings.append("step3: 발문 유형 태그 %d개 제거 "
                                "(원고 표기 — 조판은 발문만)" % _n_tag)
            _n_tail = _s3_drop_tail_directives(pre)
            if _n_tail:
                warnings.append("step3: 지문 뒤 꼬리 지시문 %d개 제거 "
                                "(발문 중복 — ※ …)" % _n_tail)
            _s3_number_order_rows(pre)
            # 2026-08-25 사용자 지적 — 선지 헤더/후치 보기 캡션 구조 인식.
            # 슬롯 배정(_s3_assign_slots) 앞: 여기서 확정된 C/Box 는
            # _promote_ansline 의 '구조 역할 확정' 제외 목록에 걸려 답란으로
            # 강등되지 않는다.
            _s3_choice_headers(pre, R)
            _s3_box_captions(pre, BG, R)
            warnings.extend(_s3_assign_slots(pre, BG))

            # ── 3패스: 스타일 확정 + 유닛 생성 ──────────────────────────
            unit = []
            eff_seq = []
            for row in pre:
                # 그림은 행이 스타일 없음으로 탈락해도 살린다 (침묵 유실 금지)
                for _im in row.get("img_before") or ():
                    unit.append(_s3_image_para(_im))
                style = _style("STEP3", row["eff"])
                if style is None:
                    for _im in row.get("img_after") or ():
                        unit.append(_s3_image_para(_im))
                    continue
                if row["arrow_bg"]:
                    style = _style("STEP3", "P-CONTEXT")
                # W54 (1bda7f01 실증 — 사용자 지적 5): 지문 스타일의 GREP
                # (원문자 뒤 영단어 → 지문 밑줄)은 어법 지문(원고가 ⓐ~ⓔ 뒤
                # 단어에 밑줄 의도)용이다. 문장삽입/무관문장 지문의 ①~⑤
                # 위치 마커에도 발동해 원고에 없는 밑줄이 생긴다 — 원고
                # runs에 밑줄이 전혀 없는 ①~⑤ 마커 지문은 '밑줄제거' 변형
                # 스타일(스타일맵 P 리스트 2번째)로 보낸다.
                if row["eff"] == "P" and _RE_S3_NUM_CIRCLED.search(row["tclean"]) \
                        and not any(r.get("ul") for r in (row["runs"] or [])):
                    style = _s3_p_no_underline_style() or style
                eff_seq.append((row["eff"], row["tclean"]))
                text, runs = row["text"], row["runs"]
                for rx, repl in _S3_GREPS:
                    text, runs = _sub_runs(rx, repl, text, runs)
                if style == st_q:
                    text, runs = _sub_runs(_RE_S3_QNUM, "", text, runs)
                para = {"t": text, "s": style, "runs": runs}
                para.update(_ansline_fields(row["eff"], row["arrow_bg"]))
                unit.append(para)
                for _im in row.get("img_after") or ():
                    unit.append(_s3_image_para(_im))
            if unit:
                _s3_underline_quotes(unit, st_q, _style("STEP3", "P"),
                                     _style("STEP3", "P-CONTEXT"),
                                     warnings)
                # 지문번호 라벨 — v1 processStep3 파리티.
                # v1(run.jsx)은 문항마다 "{code}" 단락을 맨 앞에 넣는데
                # v2 빌더에는 이 처리가 없어 실전 섹션에만 지문번호가
                # 통째로 빠져 있었다 (2026-08-07 실측: 실전 55p 코드 0개.
                # 문서 전체 코드 검사는 통과해 기계검증이 못 잡음).
                # 다문항 세트 안내문 (사용자 확정 스펙 2026-08-07: "한 지문에
                # 여러 문제 달려있는 문제들은 원고에 없더라도 '다음 글을 읽고
                # 물음에 답하시오.' 넣어야 돼"). 실측: 17개 세트 전부 발문이
                # 2개 이상인데 안내문은 2개 세트에만 있었다.
                # W53 (배재2 워크북01 검수 실증 2026-08-12): 교과서/부교재
                # 계열은 STEP3 전체가 question_num="textbook" 단일 통짜
                # 아이템이라(코퍼스 35건 중 30건) nq>1이 항상 참 — 세트
                # 안내문이 '실전 문제 섹션 맨 앞'에 1개 얹혀 인쇄된다
                # (검수자 삭제 지시 3건 = 과당 1건. 원고에 안내문이 있는
                # 통짜 아이템은 dedup에 걸려 조용히 지나갔을 뿐).
                # 위 스펙은 문항번호가 있는 '세트' 단위 아이템 대상이므로
                # 통짜 아이템에는 삽입하지 않는다 (원고 안내문은 보존).
                nq = sum(1 for p in unit if p.get("s") == st_q)
                aggregate = (str(item.get("question_num") or "").strip()
                             .lower() == "textbook")
                if nq > 1 and not aggregate and not any(
                        _STEP3_SET_INTRO_KEY in (p.get("t") or "")
                        for p in unit):
                    unit.insert(0, {"t": _STEP3_SET_INTRO,
                                    "s": _style("STEP3", "Q-INTRO")
                                    or "$BASIC", "runs": []})
                # W54 (1bda7f01 미래엔김 실증 — 사용자 지적 2): 통짜
                # (textbook) 아이템은 위 유닛 단위 삽입 대신 **세트 단위**로
                # 판정한다 — 원고가 세트마다 안내문을 갖고 있어도 첫 세트
                # 등 일부에 없으면 그 세트만 누락된 채 인쇄됐다. 지문 블록
                # 시작(직전이 선지/답란/조건 등 이전 세트 꼬리)마다 다음
                # 지문 시작 전까지 발문 수를 세고, 2개 이상인데 직전에
                # 안내문이 없으면 그 지문 앞에 삽입한다 (원고 안내문 보존).
                if aggregate:
                    _s3_insert_set_intros(unit, st_q)
                # W54 (사용자 지적 4): 서술형 문항(선지·답란이 전혀 없는
                # 발문 블록)은 답을 쓸 여백이 없다 — 발문 블록 끝에 답란
                # 스타일 빈 단락 2개를 삽입해 필기 공간을 준다.
                _s3_insert_answer_space(unit, st_q)
                # W66 ②③ (사용자 지적 2026-08-14): 답 영역 실물화 —
                # 원문자 기입 줄 칸 길이 통일 + 답표 헤더 2줄 → 표 op
                _s3_widen_answer_rows(unit, _style("STEP3", "C"))
                _s3_answer_tables(unit, st_q, warnings)
                # W67: 지문 속 빈칸(밑줄 공백)이 줄 끝에서 증발하는 것 방지
                _s3_fix_blank_runs(unit)
                code = (item.get("code") or "").strip()
                if code:
                    unit.insert(0, {"t": "{" + code + "}", "s": "$BASIC",
                                    "runs": []})
                units.append(unit)
                warnings.extend(BG.validate_sequence(eff_seq))
    return {"units": units, "warnings": warnings}


# ── W77: 원고 그림(도표/그래프) 단락 ───────────────────────────────────────
# 사용자 지시 2026-08-27 — "원고에 있는 도표 이미지도 조판이 됐으면 좋겠어."
# 그림은 발문/지문/선지 어느 슬롯도 아니라 슬롯 배정 패스(_s3_assign_slots
# 등)를 통과시키지 않는다. 1패스 직후 이웃 행으로 옮겨 붙이고(아래),
# 3패스에서 제자리에 그림 단락으로 되돌린다.
def _s3_attach_images(pre, warnings):
    """pre의 _IMG 행을 뒤 행의 img_before(마지막이면 앞 행의 img_after)로 이동."""
    imgs = [i for i, r in enumerate(pre) if r.get("eff") == "_IMG"]
    if not imgs:
        return
    for i in reversed(imgs):
        img = pre[i].get("image")
        nxt = next((j for j in range(i + 1, len(pre))
                    if pre[j].get("eff") != "_IMG"), None)
        if nxt is not None:
            pre[nxt].setdefault("img_before", []).insert(0, img)
        else:
            prv = next((j for j in range(i - 1, -1, -1)
                        if pre[j].get("eff") != "_IMG"), None)
            if prv is None:
                warnings.append("step3: 원고 그림 1개를 붙일 단락이 없어 누락")
                continue
            pre[prv].setdefault("img_after", []).append(img)
    for i in reversed(imgs):
        pre.pop(i)


def _s3_image_para(img):
    """그림 1개 → 플랜 단락. 실행기(JSX)가 image 키를 보고 인라인 앵커로 배치."""
    return {"t": "", "s": _style("STEP3", "P"), "runs": [],
            "align": "center", "image": dict(img)}


# ── W66 (사용자 지적 2026-08-14 ②③): 답 영역 실물화 ─────────────────────
# 원고의 답 영역은 hwp 표/공백으로만 표시돼 조판에서 '평문 두 줄'이나
# '짧은 밑줄'로 인쇄된다. 수작업 완성본(사용자 페이스트보드 실측)에 맞춘다.
#   ② "틀린 부분 / 수정" 두 줄 → 2열 표 (헤더 1행 + 답 N행).
#      N은 발문의 "(틀린 부분 4개)"에서 읽는다 — 없으면 기본 8행.
#   ③ "ⓐ    ⓑ    ⓒ" 기입 줄 → 칸 길이를 완성본과 같은 35칸으로.
# 실측(워크북수특라이트영어독해_내지_v2.indd 페이스트보드):
#   표 = 2열 각 40.875mm(단 폭 82mm), 헤더 행 4.822mm/답 행 6.233mm,
#        헤더 채움 "C=44 M=0 Y=0 K=14" 50%, 4변 0.5pt, 셀 여백 1mm
#   답란 = 원문자 + 밑줄 공백 35칸 (3칸이 82mm 단에 정확히 한 줄)
_S3_ANSROW_SPACES = 35
# 열 머리 판정은 구조 룰(core.structure.rules)과 같은 눈을 쓴다 — 표기가
# 하나 바뀌어도(ⓐ/㉠/(a)) 두 모듈이 갈라지지 않도록 별칭으로만 둔다.
from core.structure.rules import (COL_MARK_TOKEN as _RE_COL_MARKS,
                                  choice_columns as _RE_COL_COLUMNS)
_RE_S3_CIRCLED_LTR = re.compile(r"[ⓐ-ⓩⒶ-Ⓩ㉠-㉭]")
_RE_S3_ANSROW_GAP = re.compile(r"[ \t　\xa0]{3,}")
_RE_S3_WRONG_COUNT = re.compile(r"(\d+)\s*개")
_S3_ANSTABLE_ROWS_DEFAULT = 8


def _s3_widen_answer_rows(unit, choice_style=None):
    """원문자 기입 줄("ⓐ   ⓑ   ⓒ")의 밑줄 칸을 완성본 길이로 (W66 ③).

    구조 판정: 단락이 원문자와 공백'만'으로 이뤄지고(=쓸 내용이 없는 기입
    줄), 3칸 이상 공백 구간이 있으면 답 쓰는 칸이다. 원고가 몇 칸을 줬든
    (14칸/15칸/전각공백) 완성본과 같은 35칸으로 통일하고 밑줄 run을 준다.

    2026-08-25 사용자 지적("선지 헤더 abc 뒤에 자꾸 밑줄이 들어간다"):
    **다열 선지의 열 머리**("ⓐ  ⓑ  ⓒ" 위에 선지 ①~⑤가 오는 줄)는 형태가
    기입 줄과 똑같아 여기 걸렸다 — 원고 runs 에는 밑줄이 전혀 없는데
    35칸 밑줄이 새로 붙었다. 답란인지 열 머리인지는 **다음 줄**이 가른다:
    다음 유의 단락이 같은 열 수의 선지면 열 머리다. 판정을 _s3_choice_headers
    와 같은 눈(R.choice_columns)으로 두 겹 건다 — ① 확정된 선지 스타일
    제외 ② 스타일이 어긋나도 구조로 재확인."""
    n = 0
    for pi, p in enumerate(unit):
        t = p.get("t") or ""
        if not t.strip():
            continue
        marks = _RE_S3_CIRCLED_LTR.findall(t)
        if not marks or not _RE_S3_ANSROW_GAP.search(t):
            continue
        if _RE_S3_CIRCLED_LTR.sub("", t).strip():
            continue          # 원문자 외 내용이 있으면 기입 줄이 아니다
        if choice_style and p.get("s") == choice_style:
            continue          # 선지 헤더로 확정된 줄 — 답란이 아니다
        _nx = next((q for q in unit[pi + 1:] if (q.get("t") or "").strip()),
                   None)
        if _nx is not None and _RE_COL_MARKS.findall(t) \
                and _RE_COL_COLUMNS(_nx.get("t") or "") == len(marks):
            continue          # 다음 줄이 같은 열 수의 선지 = 열 머리
        runs, text = [], []
        for mk in marks:
            runs.append({"t": mk, "ul": False})
            runs.append({"t": " " * _S3_ANSROW_SPACES, "ul": True})
            text.append(mk + " " * _S3_ANSROW_SPACES)
        p["t"] = "".join(text)
        p["runs"] = runs
        n += 1
    return n


_S3_NBSP = " "
# 빈칸 최대 칸 수 — 8pt 기준 15칸 ≈ 10mm (82mm 단에서 항상 한 줄에 수용)
_S3_BLANK_MAX = 15


def _s3_fix_blank_runs(unit):
    """지문 속 빈칸(밑줄 친 공백 런)이 줄 끝에서 사라지는 것 방지 (W67).

    사용자 지적 2026-08-14 "스텝3 빈칸 튀어나오는 거": 빈칸 문항의 빈칸은
    원고에서 '밑줄 친 공백'이라, 그 자리가 줄 끝이면 InDesign이 공백을
    흘려버려 빈칸이 통째로 사라지고 뒤따르는 마침표만 다음 줄에 남는다
    (8강 실측: "These trends are" + 공백 44칸 + "."). 마지막 한 칸만
    보통 공백으로 남기고 나머지를 줄바꿈 없는 공백(U+00A0)으로 바꾸면
    빈칸은 소멸하지 않고, 빈칸 뒤에서만 줄이 바뀐다.

    원문자 기입 줄(답란)은 제외 — 그쪽은 칸 사이에서 줄이 바뀌어야 한다."""
    n = 0
    for p in unit:
        runs = p.get("runs") or []
        t = p.get("t") or ""
        if not runs or not t.strip():
            continue
        if not _s3_is_prose(t):
            continue          # 지문(산문)만 — 답란/기입 줄은 줄바꿈 기회가
                              # 필요하고, 줄 끝 공백 소멸도 무해하다
        if sum(len(r.get("t") or "") for r in runs) != len(t):
            continue          # run 오프셋 불일치 — 손대지 않는다
        changed = False
        for r in runs:
            rt = r.get("t") or ""
            if not r.get("ul") or len(rt) < 3 or rt.strip():
                continue      # 밑줄 친 '공백만' 있는 런
            # 길이는 상한(_S3_BLANK_MAX)까지만 — 원고가 준 칸 수(8강 실측
            # 43칸)는 임의값이라 그대로 두면 줄 끝에서 갈 곳이 없어
            # 프레임 밖으로 나가거나(튀어나옴) 앞 단어가 "ar|e"처럼
            # 쪼개진 채 줄이 바뀐다. 앞뒤 한 칸은 보통 공백으로 남겨
            # 줄바꿈 기회를 준다.
            k = min(len(rt), _S3_BLANK_MAX)
            r["t"] = " " + _S3_NBSP * (k - 2) + rt[-1]
            changed = True
        if changed:
            p["t"] = "".join(r.get("t") or "" for r in runs)
            n += 1
    return n


def _s3_answer_tables(unit, st_q, warnings):
    """답표 헤더 두 줄("틀린 부분"/"수정") → 표 op 한 단락으로 (W66 ②).

    구조 판정: 서술형 발문("…쓰시오/고치시오") 블록의 **끝**에, 지문 뒤로
    남은 짧은 한글 열머리 2줄(문장부호·영문·숫자·원문자 없음)이 연달아
    오면 그것이 원고 답표(hwp 2열 표)의 헤더가 평탄화된 것이다. 두 줄을
    지우고 표 op 단락 하나로 바꾼다 — 행 수는 발문의 "(… N개)"."""
    def _is_passage(p):
        s = p.get("s") or ""
        return ("실전 문제 지문" in s or s == _style("STEP3", "P-CONTEXT")
                or s == _style("STEP3", "Word"))

    def _is_hdr_cell(p):
        t = (p.get("t") or "").strip()
        if not (1 <= len(t) <= 12):
            return False
        if not re.search(r"[가-힣]", t):
            return False
        if re.search(r"[A-Za-z0-9]", t):
            return False
        if re.search(r"[.?!,:;]|시오|세요", t):
            return False
        if _RE_S3_CIRCLED_LTR.search(t) or re.search(r"[①-⑮]", t):
            return False
        # 블록 마커(<조건>/[보기])·조건 항목(불릿/"…할 것")은 답표 헤더가
        # 아니다 — 같은 '짧은 한글 두 줄' 모양이라 반드시 배제한다.
        if re.search(r"[<>\[\]〈〉《》]|^[\s•·⦁◦∙ㆍ\-–—*]", t):
            return False
        if re.search(r"것\s*$", t):
            return False
        if p.get("s") in (_style("STEP3", "Cond"), _style("STEP3", "Box")):
            return False
        return True

    i = 0
    made = 0
    while i < len(unit) - 1:
        if not (_is_hdr_cell(unit[i]) and _is_hdr_cell(unit[i + 1])):
            i += 1
            continue
        # 답표는 '지문 뒤'에 온다 — 직전 비빈 단락이 지문/어휘가 아니면
        # (원고 표제·메타 표의 짧은 두 줄 등) 답표가 아니다.
        prev = None
        for k in range(i - 1, -1, -1):
            if (unit[k].get("t") or "").strip():
                prev = unit[k]
                break
        if prev is None or not _is_passage(prev):
            i += 1
            continue
        j = i + 2
        while j < len(unit) and not (unit[j].get("t") or "").strip():
            j += 1          # 뒤따르는 빈 줄은 답 여백 — 블록 끝으로 본다
        # 블록 끝 조건: 다음 내용이 없거나 새 발문/새 지문 (= 답 영역 종료).
        # 2026-08-28 실증(수특라이트영독 10강, 4문항 전부): 원고가 어휘 각주
        # ("* shareholder value 주주 가치")를 답표 헤더 **뒤**에 놓아 다음
        # 내용이 '영단어' 스타일이었고, 지문 계열인데도 이 조건에서 걸려
        # 표가 하나도 생성되지 않았다. 지문 계열 판정을 _is_passage 로 통일
        # (지문/배경/영단어 — 위 '답표는 지문 뒤' 판정과 같은 눈).
        nxt = unit[j] if j < len(unit) else None
        if nxt is not None and nxt.get("s") != st_q and not _is_passage(nxt):
            i += 1
            continue
        # 직전 발문 찾기 (서술형 + 행 수)
        qi = None
        for k in range(i - 1, -1, -1):
            if unit[k].get("s") == st_q:
                qi = k
                break
        # 답표는 '발문 → 지문 → 답표' 자리다. 발문과 두 줄 사이에 지문/
        # 어휘 외의 것(선지·조건·보기·다른 발문)이 끼면 답표가 아니다.
        # (실용문 지문은 불릿 줄이 많아 '거리'로는 못 자른다 — 585a48a5)
        if qi is None or not all(
                _is_passage(unit[k]) or not (unit[k].get("t") or "").strip()
                for k in range(qi + 1, i)):
            i += 1
            continue
        qt = (unit[qi].get("t") or "").strip()
        if not re.search(r"시오\s*[.?]?\s*$|시오\s*\(", qt) \
                and "쓰시오" not in qt and "고치시오" not in qt:
            i += 1
            continue
        m = _RE_S3_WRONG_COUNT.search(qt)
        rows = int(m.group(1)) if m else _S3_ANSTABLE_ROWS_DEFAULT
        rows = max(1, min(rows, 20))
        if not m:
            warnings.append(
                "step3: 답표 행 수를 발문에서 못 읽어 기본 %d행 — %s"
                % (_S3_ANSTABLE_ROWS_DEFAULT, qt[:40]))
        headers = [(unit[i].get("t") or "").strip(),
                   (unit[i + 1].get("t") or "").strip()]
        # 헤더 셀("틀린 부분"/"수정")은 **지문 스타일을 쓰지 않는다**
        # (사용자 지시 2026-08-27). 지문 스타일에는 한글 런을 통째로
        # 밑줄 치는 GREP([가-힣]… → 문자스타일 '지문 밑줄')이 걸려 있어
        # 한글 헤더에 원고에 없는 밑줄이 생긴다. 크기/정렬이 같은
        # '밑줄제거' 변형으로 — 표 모양(8pt·가운데)은 그대로다.
        hdr_style = (_s3_p_no_underline_style() or unit[i].get("s")
                     or "$BASIC")
        host_style = unit[i].get("s") or "$BASIC"
        # 지문 바로 밑에 표가 붙어 답답하다(사용자 지시 2026-08-27) —
        # 표 앞에 빈 단락 한 개(엔터 한 칸)를 둔다. 앞이 이미 빈 줄이면
        # 넣지 않는다(두 줄이 되지 않게).
        # 각주가 헤더 뒤에 밀려 있으면 지문 바로 뒤로 되돌린다 — 그대로 두면
        # 표 아래에 각주가 떠서 다른 문항(지문 → 각주 → 선지)과 어긋난다.
        _wsty = _style("STEP3", "Word")
        while (i + 2 < len(unit) and _wsty
               and unit[i + 2].get("s") == _wsty):
            unit.insert(i, unit.pop(i + 2))
            i += 1
        _prev_blank = (i > 0 and not (unit[i - 1].get("t") or "").strip())
        _rows = [] if _prev_blank else [
            {"t": "", "s": host_style, "runs": []}]
        _rows.append({
            "t": "", "s": host_style, "runs": [],
            "table": {"cols": headers, "rows": rows,
                      "header_style": hdr_style,
                      "header_style_fb": host_style},
        })
        unit[i:i + 2] = _rows
        made += 1
        i += 1
    return made


def _s3_insert_set_intros(unit, st_q):
    """통짜(textbook) step3 유닛의 세트 단위 안내문 삽입 (W54).

    세트 = 지문 블록(지문/배경 스타일 연속, 사이의 (A)류 라벨 허용) +
    그 뒤 발문들. 지문 블록 시작 인덱스마다 다음 지문 블록 전까지의
    발문(st_q) 수를 세고, 2개 이상인데 지문 직전 단락이 안내문
    (물음에 답하시오)이 아니면 안내문을 삽입한다."""
    intro_style = _style("STEP3", "Q-INTRO") or "$BASIC"

    def _is_passage(p):
        s = p.get("s") or ""
        return "실전 문제 지문" in s or s == _style("STEP3", "P-CONTEXT")

    # 지문 블록 시작 수집 (직전 비빈 단락이 지문/라벨이 아닌 P 단락)
    starts = []
    prev_passage = False
    for i, p in enumerate(unit):
        t = (p.get("t") or "").strip()
        if _is_passage(p):
            if not prev_passage:
                starts.append(i)
            prev_passage = True
        elif not t or re.match(r"^\(\s*[A-E]\s*\)$", t):
            pass    # 빈 줄/(A)류 위치 라벨은 지문 블록 연속으로 취급
        else:
            prev_passage = False
    starts_set = sorted(starts) + [len(unit)]
    # 역순 삽입 (인덱스 안정)
    for k in range(len(starts_set) - 2, -1, -1):
        a, b = starts_set[k], starts_set[k + 1]
        nq = sum(1 for p in unit[a:b] if p.get("s") == st_q)
        if nq < 2:
            continue
        prev = None
        for j in range(a - 1, -1, -1):
            if (unit[j].get("t") or "").strip():
                prev = unit[j]
                break
        if prev is not None and _STEP3_SET_INTRO_KEY in (prev.get("t") or ""):
            continue
        # W61 (사용자 지적 "발문 다음에 왜 다음 글을 읽고가 나와?"):
        # 직전이 발문이면 이 지문은 그 발문에 딸린 자료다 — 안내문을
        # 끼우면 '발문 → 안내문 → 지문' 순서가 된다. 삽입 금지.
        if prev is not None and prev.get("s") == st_q:
            continue
        unit.insert(a, {"t": _STEP3_SET_INTRO, "s": intro_style,
                        "runs": []})


def _s3_insert_answer_space(unit, st_q):
    """선지·답란 없는 서술형 발문 블록 끝에 답란 빈 단락 2개 삽입 (W54).

    발문(st_q)부터 다음 발문/안내문/지문 블록 시작 전까지를 문항 블록으로
    보고, 블록 안에 선지(C)·답란(AnsL) 스타일이 하나도 없으면 블록 끝에
    빈 답란 단락을 넣는다 (사용자 스펙: "서술형은 답 쓸 칸 없으면 여백
    일부 — 엔터쳐서 답란/선지 스타일")."""
    st_c = _style("STEP3", "C")
    st_ansl = _style("STEP3", "AnsL")
    intro_style = _style("STEP3", "Q-INTRO")

    def _is_passage(p):
        s = p.get("s") or ""
        return "실전 문제 지문" in s or s == _style("STEP3", "P-CONTEXT")

    def _prev_meaningful(j):
        for k in range(j - 1, -1, -1):
            if (unit[k].get("t") or "").strip():
                return unit[k]
        return None

    q_idx = [i for i, p in enumerate(unit) if p.get("s") == st_q]
    for qi in reversed(q_idx):
        # 서술형 발문만 (시오-체, '고르시오' 제외) — 지문 내 ①~⑤ 선택형
        # ('…곳을 고르시오' / '…것은?')은 답 쓸 여백이 필요 없다.
        qt = (unit[qi].get("t") or "").strip()
        if not re.search(r"시오\s*[.?]?\s*$", qt) or "고르시오" in qt:
            continue
        # 문항 블록 끝 = 다음 발문/안내문, 또는 **새 세트의 지문**(직전이
        # 발문이 아닌 지문 블록 시작 — 발문 바로 뒤 지문은 문항 내부 지문).
        end = len(unit)
        for j in range(qi + 1, len(unit)):
            p = unit[j]
            if p.get("s") in (st_q, intro_style):
                end = j
                break
            if _is_passage(p) and not _is_passage(unit[j - 1] if j else {}):
                prev = _prev_meaningful(j)
                if prev is not None and prev.get("s") != st_q:
                    end = j
                    break
        span = unit[qi + 1:end]
        if any(p.get("s") in (st_c, st_ansl) for p in span):
            continue
        for _ in range(2):
            unit.insert(end, {"t": "", "s": st_ansl, "runs": []})


def _s3_number_order_rows(pre):
    """순서배열 선지 순열 행 5연속에 원문자 부여 + 선지(eff C) 확정.

    W40 결함 3: 원고의 hwpx 2열 표(번호 셀|순열 셀) 병합은 파서
    (_merge_step3_split_choice_numbers 선호출)가 1선. 이 함수는 (a) 병합
    이전에 수집된 구 content.json 재플랜과 (b) 원고 자체에 번호가 없는
    원고의 폴백 — **순열 형태 행 5연속 + 전부 번호 없음**일 때만 ①~⑤를
    부여한다 (기존 자동번호와 같은 글리프. 파서가 병합한 행은 ①로 시작해
    C_START(kind C)로 이미 선지 — 여기 오지 않는다)."""
    i, n = 0, len(pre)
    while i < n:
        m = _RE_S3_PERM_ROW.match(pre[i]["tclean"])
        if not m or len(set(m.groups())) != 3:
            i += 1
            continue
        j = i
        run = []
        while j < n:
            mj = _RE_S3_PERM_ROW.match(pre[j]["tclean"])
            if not mj or len(set(mj.groups())) != 3:
                break
            run.append(pre[j])
            j += 1
        if len(run) == 5:
            for d, row in zip(_S3_CIRCLED, run):
                prefix = d + " "
                row["text"] = prefix + row["text"]
                row["tclean"] = prefix + row["tclean"]
                row["eff"] = "C"
                if row["runs"]:
                    row["runs"] = ([{"t": prefix, "ul": False}]
                                   + list(row["runs"]))
        i = j


def _s3_choice_headers(pre, R):
    """다열 선지 열 머리 → 선지(C) — 표기 불문 구조 인식 (파서와 이중 방어).

    2026-08-25 사용자 지적: "선지 헤더로 들어가는 abc 뒤에 자꾸 밑줄이
    들어간다. 선지 헤더면 선지 단락스타일이어야 하는데 지문으로 처리된다."
      윗글의 괄호 ⓐ, ⓑ, ⓒ에서 흐름상 알맞은 말로 …             ← 발문
      ⓐ      ⓑ      ⓒ                                        ← 열 머리
      ① excited  confident  convenience                      ← 선지
    기존 인식(R.C_AB_HEADER)은 `(A)` **리터럴**만 봐서 ⓐ/㉠/(a) 표기의 열
    머리를 전부 놓쳤고(kind UNKNOWN → 지문 스타일), 아래 _s3_widen_answer_rows
    는 같은 줄을 '답란 기입 줄'로 보고 원고에 없던 밑줄 35칸을 붙였다
    (같은 줄을 두 모듈이 다른 눈으로 본 결과 — 지문 스타일 + 가짜 밑줄).
    열 머리는 표기가 아니라 위치+형태로 잡는다: 열 라벨만으로 이뤄진 줄이고
    바로 다음 유의 단락이 같은 열 수의 원문자 선지일 때만."""
    n = 0
    rows = [r for r in pre if r["tclean"]]
    for x, row in enumerate(rows):
        if row["eff"] in ("Q", "Q-INTRO", "GH", "A", "C", "Cond", "Box",
                          "Sum", "SRC"):
            continue
        marks = R.choice_header_marks(row["tclean"])
        if not marks:
            continue
        nxt = rows[x + 1] if x + 1 < len(rows) else None
        if not nxt or nxt["eff"] != "C":
            continue
        if R.choice_columns(nxt["tclean"]) != len(marks):
            continue
        row["eff"] = "C"
        row["choice_header"] = True
        n += 1
    return n


def _s3_box_captions(pre, BG, R):
    """후치 <보기> 캡션 — 라벨이 자기 내용 **뒤**에 오는 원고 (2026-08-25).

    원고(hwp)의 보기 상자는 캡션이 표 뒤에 추출돼 스트림이
      confident / appreciate / stylish /   ← 보기 내용
      the way / feel / help                ← 보기 내용
      보기                                 ← 마커 (내용 뒤!)
    순서로 온다. 마커 뒤만 보는 전방 전파는 이 형태에서 ① 앞의 어구 나열을
    직전 <조건> 블록이 흡수해 조건 상자에 인쇄하고 ② 보기 상자는 빈 채로
    인쇄하고 ③ 마커 뒤 답란을 보기 스타일로 삼킨다 (사용자 실증 스크린샷).
    마커 뒤에 보기 내용이 없고 앞에 붙어 있으면 그 앞이 이 마커의 내용이다 —
    구간을 Box 로 되돌리고 라벨을 구간 맨 앞으로 옮긴다(라벨이 상자 머리)."""
    idxs = [i for i, r in enumerate(pre) if r["tclean"]]
    moves = []
    for mi, si in BG.trailing_box_captions([pre[i]["tclean"] for i in idxs]):
        if pre[idxs[mi]]["eff"] not in ("Box", "UNKNOWN"):
            continue          # <조건>/<요약문> 등 다른 블록 마커 (이중 방어)
        for y in range(si, mi):
            pre[idxs[y]]["eff"] = "Box"
        pre[idxs[mi]]["eff"] = "Box"
        moves.append((idxs[mi], idxs[si]))
        # 마커 뒤에 붙어 있던 Box 는 구 전방 전파가 삼킨 **답란**이다
        # (보기 내용은 앞에 있었다) — 기입란이면 답란으로 되돌린다.
        for y in range(mi + 1, len(idxs)):
            row = pre[idxs[y]]
            if row["eff"] != "Box":
                break
            t = row["tclean"]
            if BG.is_box_content(t):
                break
            row["eff"] = "AnsL" if R.ANS_UL_RUN.search(t) else "P"
    for marker_i, start_i in reversed(moves):
        pre.insert(start_i, pre.pop(marker_i))
    return len(moves)


def _s3_assign_slots(pre, BG):
    """유형 주도 슬롯 배정 2패스 (파서 컨텍스트 패스와 이중 방어).

    주어진 블록: 발문 유형의 실측 시퀀스(block_sequences.json)가 발문
    직후 배경 단락을 기대하면, 그 자리의 단락을 형태 신호로 배정한다.
    배정 불가(형태 불일치) 단락은 침묵 강등 금지 — [경고] + 후보 슬롯."""
    warn = []
    last_q = None            # (q_code, 발문 텍스트)
    given_pending = False    # 발문 직후 첫 유의 단락 대기 상태
    demote_pending = False   # W40 결함 4: 유형이 슬롯 비기대 — 구 주석 강등
    for row in pre:
        eff = row["eff"]
        if eff in ("Q", "Q-INTRO"):
            last_q = (row.get("q_code"), row["tclean"])
            given_pending = BG.expects_given_block(last_q[0], last_q[1])
            # 유형이 분류됐는데 주어진 블록을 기대하지 않으면(선지 직행
            # 실측 — OBJ-GRM-PAREN 등), 발문 직후 P-CONTEXT 구 주석은
            # 판정 2 오배정 잔재다 (0a5da924 215번 실증) — 지문으로 강등.
            # Q 한정 (Q-INTRO 묶음 인트로 뒤 장문 배열형의 주어진 글 보존).
            demote_pending = (eff == "Q" and bool(last_q[0])
                              and not given_pending)
            continue
        if not row["tclean"] or row["kind"] == "SRC" \
                or (row["eff"] == "UNKNOWN"
                    and BG.BRACKET_LABEL.match(row["tclean"])):
            continue         # 빈 단락/출처 마커/구조 라벨은 슬롯 비소비
        if demote_pending:
            # 발문 직후 첫 유의 단락에만 적용 (W40 결함 4). 요약 빈칸
            # 선택형의 요약문 형태(인라인 (A)/(B) 빈칸)는 배경 유지.
            demote_pending = False
            if eff == "P-CONTEXT" and not row["arrow_bg"] \
                    and not BG.is_summary_blank_form(row["tclean"]):
                row["eff"] = "P"
                eff = "P"
        # T/F 선택 행 (W39 결함 5 — 구 kind 주석 이중 방어)
        if last_q and BG.is_tf_question(last_q[1]) \
                and eff in ("P", "UNKNOWN", "K", "Word"):
            if BG.is_tf_choice_row(row["tclean"]):
                row["eff"] = "C"
                continue
            if _RE_S3_TF_NEAR.match(row["tclean"]) \
                    and not _RE_S3_HANGUL.search(row["tclean"]):
                warn.append(
                    "[슬롯] 선지행(T/F) 후보가 선택 표기 꼬리 없음 — "
                    f"배정 불가 지목: '{row['tclean'][:40]}'")
        if given_pending:
            given_pending = False
            verdict = BG.given_slot_scan(
                eff, row["tclean"], prior_only=not (last_q and last_q[0]))
            if verdict == "assign":
                if not row["arrow_bg"]:
                    row["eff"] = "P-CONTEXT"
                continue
            if verdict == "warn":
                warn.append(
                    "[슬롯] 주어진 블록 배정 불가 — 발문 유형은 배경 "
                    f"단락을 기대하나 형태 불일치(현재 {eff}): "
                    f"'{row['tclean'][:40]}' (발문: "
                    f"'{(last_q[1] if last_q else '')[:30]}')")

    # 답란 쌍 (W39 결함 4 — 구 kind 주석 이중 방어): "라벨:" + 밑줄 빈칸
    from core.structure import rules as R
    meaningful = [r for r in pre if r["tclean"]]
    for x, row in enumerate(meaningful):
        if row["eff"] not in ("UNKNOWN", "K") \
                or not BG.ANS_LABEL.match(row["tclean"]):
            continue
        nxt = meaningful[x + 1] if x + 1 < len(meaningful) else None
        if nxt and (nxt["eff"] in ("Ans", "AnsL")
                    or any(p.match(nxt["tclean"])
                           for p in R.ANS_PATTERNS[:2])):
            row["eff"] = "AnsL"
            nxt["eff"] = "AnsL"

    # 괄호 라벨 답란 (W40 결함 5 — 구 kind 주석 이중 방어): 보기/조건
    # 블록 내용 직후의 "(A) ______" 라인은 답란(AnsL)이다 — 파서 수리
    # 이전 content의 Box 흡수 주석(보기 스타일)·Ans 주석(지문 관행)을
    # 위치(블록 뒤) + 형태(괄호 라벨 + 밑줄 런) 신호로 승격.
    prev_eff = None
    for row in meaningful:
        if row["eff"] in ("Box", "Ans", "Cond") \
                and BG.ANS_PAREN_BLANK.match(row["tclean"]) \
                and prev_eff in ("Box", "Cond", "AnsL"):
            row["eff"] = "AnsL"
        prev_eff = row["eff"]

    # 서답형 답란 표 (2026-08-06 사용자 지적: "(기호)(어색한 표현)
    # (고친 표현) 이런 게 지문이 아니잖아"). 어법 수정 문항의 답란은
    #   "(기호)  (어색한 표현)  (고친 표현)"      ← 열 머리
    #   "(     ) ____________ → ____________"    ← 기입 줄 ×N
    # 형태인데 지문 스타일로 인쇄되고 있었다. 열 머리는 괄호 라벨만
    # 2개 이상, 기입 줄은 괄호 + 밑줄 + 화살표로 판별한다.
    for x, row in enumerate(meaningful):
        # 이미 AnsL 이면 통과. "Ans" 는 **지문 스타일**로 인쇄되므로
        # 답란 표의 기입 줄이면 AnsL 로 승격해야 한다 (2026-08-06 실측:
        # 열 머리만 S_답란 이 되고 기입 줄 2개가 지문 스타일로 남음).
        if row["eff"] == "AnsL":
            continue
        # W54 (1bda7f01 미래엔김 실증 — 사용자 지적 1): 이미 구조 역할이
        # 확정된 단락(발문/인트로/선지/조건/보기/요약문/출처)은 답란으로
        # 강등하지 않는다 — 발문 "윗글의 밑줄 친 ⓐ~ⓔ중 어법상 어색한
        # 것은?"(원문자 2개+40자 이하)이 원문자 열 머리로 오인돼 S_답란이
        # 되면서 문항 번호·발문 스타일이 통째로 빠졌다.
        if row["eff"] in ("Q", "Q-INTRO", "C", "Cond", "Box", "Sum", "SRC"):
            continue
        t = row["tclean"]
        # W52 (0645d4a7 v2_6 사용자 지적 1): 원문자 시작 + 실내용이 있는
        # 행은 **선지**다 — 순서배열 선지 "① (A)-(C)-(B)\t② (B)-(A)-(C)"가
        # 괄호 라벨 2개+ 규칙에 걸려 답란으로 오분류됐다(선지 스타일·탭
        # 정렬 모두 이탈). 원문자 답란 열("ⓐ   ⓑ   "/"㉠ ___")은 마커·공백·
        # 밑줄뿐이라 잔여물이 없다 — 잔여물 유무로 가른다.
        if re.match(r"^\s*[①-⑳ⓐ-ⓩ㉠-㉭❶-❿]", t):
            residue = re.sub(r"[①-⑳ⓐ-ⓩ㉠-㉭❶-❿\s_,~:.·]+", "", t)
            if residue:
                continue    # 선지 행 — 답란 승격 금지
        is_head = (len(_RE_PAREN_LABEL.findall(t)) >= 2
                   and len(t) <= 40 and "_" not in t)
        is_row = bool(_RE_ANS_ARROW_ROW.match(t))
        # 괄호 없는 변형 (원문자 열 머리 / "㉠ ____" 기입 줄)
        if not is_head:
            is_head = _is_anslabel_head(t)
        if not is_row:
            is_row = bool(_RE_ANS_BLANK_ROW.match(t)
                          or _RE_ANS_PAREN_COLON.match(t)
                          or R.ANS_MARK_BLANK_ROW.match(t)  # ⓐ __ ⓑ __
                          or R.ANS_UL_ROW.match(t))    # W57: 밑줄런 답란
        if not (is_head or is_row):
            continue
        # 열 머리는 바로 뒤에 기입 줄이 와야 한다 (오검출 차단)
        if is_head:
            nxt = meaningful[x + 1] if x + 1 < len(meaningful) else None
            if not (nxt and (_RE_ANS_ARROW_ROW.match(nxt["tclean"])
                             or _RE_ANS_BLANK_ROW.match(nxt["tclean"])
                             or _RE_ANS_PAREN_COLON.match(nxt["tclean"])
                             or _is_anslabel_head(nxt["tclean"]))):
                continue
        row["eff"] = "AnsL"
    return warn


# ── W2 공용: v1 JSX 판정 로직의 파이썬 포트 ─────────────────────────────────
# (원본: engines/workbook/jsx/run.jsx — isBracketPara/isBlankPara/hasKorean2/
#  isHeaderLine/isA1Header/extractTail. 의미론 보존을 위해 패턴을 그대로 이식)

# v1 isBlankPara의 공백 문자 집합
_RE_BLANK = re.compile(
    "^[\\s\u00a0\u1680\u180e\u2000-\u200b\u202f\u205f\u3000]*$")
_RE_BRACKET = re.compile(r"^\s*\[[^\]]+\]\s*$")
_RE_HARD = re.compile(r"^\s*2\.\s*어휘\s*2단계_Hard\s*$")   # 1A1 삭제 대상
_RE_KOR2 = re.compile(r"[가-힣][\s\S]*[가-힣]")             # v1 hasKorean2
_RE_B2_QNUM = re.compile(r"^\s*\(\d+\)")                    # v1 reNumStart
_RE_B2_CHOICE = re.compile(r"^\s*[①-⑳]")          # v1 reCircled

# v1 insertHeaderBreaks의 헤더 패턴 (run.jsx headerPatterns — compact form 매칭)
#
# W49 (실서비스 0e3e6469 영어Ⅱ_YBM(박) 1과 실증): 지문번호는 단일 순번(본문2)
# 뿐 아니라 하위분할(major-minor) 순번(본문2-1, 본문2-2)을 가진다 — 한 지문이
# 분량상 둘로 쪼개진 경우. 하위분할 '-M'도 순번의 일부이므로 `본문\d+` 뒤에
# `-M`이 오면 기존 패턴이 매칭에 실패해(본문2 뒤 '('/'$'만 허용) legacy 인식이
# 0 → 구조 인식기의 seq(단조성)로만 잡혀, seq 제외 규칙이 있는 step2_c2가 헤더를
# 못 지우고 원문 그대로 인쇄(G1 [헤더잔존]). 어휘 특례가 아니라 '순번은 계층적
# (major.minor)일 수 있다'는 구조 일반화로 `_ORD`를 도입해 전 패턴 공유한다.
_ORD = r"\d+(?:[-–—.]\d+)*"     # 계층적 순번: 3, 2-1, 4.2 …
_HEADER_PATTERNS = [
    re.compile(r"^L\d+[-–—]본문" + _ORD + r"(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^[A-Za-z]{1,15}\d*[-–—]본문" + _ORD + r"(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^L\d+[-–—][A-Za-z]{1,30}(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^L\d+[-–—]p\.?\d+(?:~\d+)?(?:[A-Za-z]{1,20})?$", re.I),
    re.compile(r"^p\d+[-–—\.]?(?:no\.)?\d+(?:~\d+)?(?:\([^\)]{0,40}\))?$",
               re.I),
    # 교과서 추가지문형 — 지문번호 뒤 한글 라벨 꼬리 ("p1-no.3과 추가지문",
    # W11): compact 매칭이라 공백 제거 후 한글 연속. 기존 패턴 무변경 append.
    re.compile(r"^p\d+[-–—\.]?(?:no\.)?\d+(?:~\d+)?[가-힣][가-힣0-9]{0,30}"
               r"(?:\([^\)]{0,40}\))?$", re.I),
    re.compile(r"^p\d+[-–—]?Example\d*$", re.I),
    re.compile(r"^p\d+[-–—][A-Za-z]{1,15}\.?\d+(?:~\d+)?$", re.I),
    re.compile(r"^p\d+[-–—](?:서술형|논술형)Practice$", re.I),
    re.compile(r"^p\d+[-–—]+수능대비ANALYSIS$", re.I),
    # 부교재 코너명형 (W12): "1. p80-수능 Analysis" — compact "p80-수능Analysis".
    # 기존 패턴 무변경 append.
    re.compile(r"^p\d+[-–—]?수능Analysis$", re.I),
    # 부교재 코너명 일반형 (W25): 위 두 패턴이 "수능대비ANALYSIS"/"수능
    # Analysis" 라는 **특정 코너 문구**를 하드코딩한 탓에, 같은 꼴의 다른
    # 코너명(원전 교재마다 다르다 — "수능 대비 ANALYSIS", "수능 유형
    # ANALYSIS" …)이 오면 또 미인식 → 헤더 인쇄 + 유닛 미분할이 재발한다.
    # 문구가 아니라 **꼴**로 매치한다: pN- + 한글 코너명 + 영문 코너명.
    # (compact 매칭이라 공백은 이미 제거된 상태. 순수 한글 꼬리형은 위의
    #  '한글 꼬리' 패턴이, 순수 영문형은 Example/Practice 패턴이 담당.)
    re.compile(r"^p\d+[-–—]+[가-힣][가-힣0-9]{0,15}[A-Za-z][A-Za-z0-9]{0,20}$",
               re.I),
    # 외부지문 무-p형 (W21 r11 — 성덕 외부지문 실사용 실증): "1. no.1" 처럼
    # 페이지 없이 지문 순번만 있는 헤더. v1 isHeaderLine도 미인식이라 v1
    # 렌더 출력엔 헤더가 그대로 인쇄됐고(3664cc0e 조판_로그 '헤더 0개'),
    # 실물 .indd(워크북03(외부지문))는 조판사가 손으로 헤더 제거+프레임
    # 분리를 복원한 상태 — 완제품 기준으로 v2가 인식한다. 기존 패턴 무변경
    # append ("N. " 접두 제거 후 compact "no.1" 형태만 매치).
    re.compile(r"^no\.?\d+(?:~\d+)?$", re.I),
    # 교과서 L-p-코너명형 (W30-r15 — 실서비스 376b34d0 실증): "1. L1-p. 13
    # 본문 1" → compact "L1-p.13본문1". 기존 L-p 패턴(위 4번째)은 한글
    # 꼬리를 허용하지 않아 미인식 → step1_c2/step2_b1/step2_c1이 지문
    # 6개를 유닛 1개 통짜로 배치 + 헤더 원문 인쇄 (사용자 지목 결함 2~4).
    # 기존 패턴 무변경 append.
    re.compile(r"^L\d+[-–—]p\.?\d+(?:~\d+)?[가-힣][가-힣0-9]{0,30}"
               r"(?:\([^\)]{0,40}\))?$", re.I),
    # 교과서 강이름-p-코너명형 (W73 — 능률(민) SL1 실증): "1. Special
    # Lesson 1-p. 52 본문 1" → compact "SpecialLesson1-p.52본문1". 위의
    # L-p 패턴은 강 코드가 `L\d+` 축약일 때만 매칭해, 강 이름을 풀네임으로
    # 쓰는 원전이 오면 헤더 미인식 → 유닛 미분할 + 헤더 원문 인쇄 +
    # 지문번호 라벨이 헤더 전문이 되어 JSX 줄임말이 전 지문을 "Special"
    # 하나로 뭉갠다. 기존 패턴 무변경 append.
    re.compile(r"^[A-Za-z]{2,30}\d{0,3}[-–—]p\.?\d+(?:~\d+)?"
               r"[가-힣][가-힣0-9]{0,30}(?:\([^\)]{0,40}\))?$", re.I),
    # 교과서 L-한글라벨형 (W30-r15 — 같은 원고): "6. L1-추가본문" →
    # compact "L1-추가본문". 페이지/숫자 없이 한글 라벨만 직결된 형태.
    # 숫자 없는 한글 꼬리라 기존 어느 패턴에도 안 걸렸다.
    re.compile(r"^L\d+[-–—][가-힣][가-힣0-9]{0,30}(?:\([^\)]{0,40}\))?$"),
]
_RE_SUPP = re.compile(r"^Supplementary Reading$", re.I)


def _is_blank(text):
    return bool(_RE_BLANK.match(text or ""))


# ── W59: bracket 없는 지문 라벨 원고의 구조 폴백 ────────────────────────────
# 비상(황) 실증(2026-08-13): 이 원고는 스텝마다 지문 라벨 형식이 다르다 —
# step1_a1/a1_2/a2/b2는 "1과 MR1"(대괄호 없음), step1_c2/step2_*는
# "1. p1-Main Reading 1". bracket([N]) 기준으로만 유닛을 나누는 빌더들이
# 경계를 하나도 못 찾아 **전 지문이 1유닛 통짜**로 배치됐고(a1/a1_2/a2/b2),
# b2는 미분류 [경고]까지 냈다. 구조 인식기(header_detect)는 "1과 MR1"을
# 정확히 잡으므로, **bracket 헤더가 문서에 하나도 없을 때만** 구조 헤더를
# bracket 대용 경계로 승격한다 (기존 bracket 원고는 무영향 — 회귀 0).
_RE_LEAD_LESSON = re.compile(r"^\s*\d+\s*[과강]\s*")


_RE_LEAD_ORD = re.compile(r"^\s*\d{1,3}\s*[.)]\s*")
_RE_LEAD_PAGE = re.compile(r"^p\.?\s*\d+\s*[-–—.]?\s*", re.I)
_RE_LEAD_NO = re.compile(r"^no\.?\s*", re.I)
# W73 (능률(민) SL1 실증): 페이지 마커 앞의 강 이름 접두 ("Special Lesson 1-").
# **뒤에 페이지 마커가 실제로 올 때만**(lookahead) 벗긴다 — "L1-본문1(p.17)"
# 처럼 접두 뒤가 곧바로 라벨인 기존 표기는 건드리지 않는다.
_RE_LEAD_LESSON_NAME = re.compile(
    r"^[A-Za-z][A-Za-z]{0,14}(?:\s+[A-Za-z][A-Za-z]{0,14}){0,2}"
    r"\s*\d{0,3}\s*[-–—]\s*(?=p\.?\s*\d)", re.I)
# W73: "본문 1" / "본문1" 표기 혼재 → 공백 없는 쪽으로 통일. 같은 지문을
# 스텝마다 다른 문자열로 가리키면 지문번호 프레임 갱신이 짝을 못 찾는다.
_RE_BONMUN_SP = re.compile(r"본문\s+(\d)")


def _abbrev_label(t):
    """W63: 긴 라벨 줄임말 (JSX abbreviateLabel과 같은 규칙 — 표기 일치).

    영문 다단어 → 각 단어 이니셜 + 숫자("Main Reading 1"→"MR1"),
    한글 다단어 → 첫 단어("추가 본문"→"추가"). 8자 이하는 그대로."""
    t = (t or "").strip()
    if " " not in t or len(t) <= 8:
        return t
    toks = t.split()
    if re.search(r"[가-힣]", t):
        return toks[0]
    ini, num = "", ""
    for tok in toks:
        if tok.isdigit():
            num = tok
            continue
        if tok[:1].isalpha():
            ini += tok[0].upper()
    return (ini + num) if ini else t


# W63: 라벨 통일 모드 — 같은 원고 안에 축약형 지문번호("1과 MR1")와
# 완전형("1. p1-Main Reading 1")이 **공존**할 때만 축약형으로 통일한다.
# 완전형만 쓰는 기존 교재("[Further Reading]", "[3과 추가지문]")는 무변경.
_LABEL_ABBREV = False


def _detect_label_abbrev(steps):
    """원고 전 스텝 헤더에 '공백 없는 축약 라벨'이 있으면 통일 모드 ON."""
    for sd in (steps or {}).values():
        if not isinstance(sd, dict):
            continue
        for p in (sd.get("paragraphs") or [])[:400]:
            t = re.sub(r"\s+", " ", (p.get("text") or "")).strip()
            t = re.sub(r"^\[|\]$", "", t).strip()
            m = _RE_LEAD_LESSON.match(t)
            if not m:
                continue
            rest = t[m.end():].strip()
            if rest and " " not in rest and len(rest) <= 6 \
                    and re.match(r"^[A-Za-z]{1,3}\d*$", rest):
                return True
    return False


def _header_label(text):
    """W63 (사용자 지시): 지문 헤더 → **전 스텝 공통** 지문번호 라벨.

    "1. p1-Main Reading 1" / "1과 MR1" → "MR1". 선행 순번("1.")·페이지
    마커("p1-")·"no."·과 접두("1과 ")를 벗기고 줄임말 규칙을 적용한다.
    문장배열(C1)이 이 함수를 안 쓰고 선행 순번을 그대로 라벨로 삼아
    "{1}{2}{3}…"이 되면서 다른 스텝({MR1}/[MR1])과 어긋났다."""
    base = re.sub(r"\s+", " ", (text or "")).strip()
    base = _RE_LEAD_ORD.sub("", base)
    # W73: 강 이름 접두를 벗긴 쪽을 먼저 쓰되, 그 결과가 **비면** 벗기지 않은
    # 원래 경로로 되돌린다 — "1. L1-p.17"은 접두("L1-")와 페이지("p.17")를
    # 둘 다 벗기면 라벨이 통째로 사라진다(코퍼스 실측 회귀). 라벨이 남는
    # 헤더("… 본문 1", "… Further Reading")에서만 접두 제거가 발효된다.
    result = ""
    for cand in (_RE_LEAD_LESSON_NAME.sub("", base), base):
        t = _RE_LEAD_PAGE.sub("", cand)
        t = _RE_LEAD_NO.sub("", t)
        t = _RE_BONMUN_SP.sub(r"본문\1", t)   # W73: "본문 1" → "본문1"
        if not _LABEL_ABBREV:
            result = t.strip(" -–—")        # 통일 모드 아님 — 정규화만
        else:
            result = _abbrev_label(_RE_LEAD_LESSON.sub("", t).strip(" -–—"))
        # 꼬리 주석("(정답 1개)")만 남은 것도 라벨이 사라진 것과 같다 —
        # "1. L1-p.17  (정답 1개)" 는 접두·페이지를 벗기면 본체가 없다.
        if re.sub(r"\s*\([^)]*\)\s*$", "", result).strip():
            return result
    return result


def _bracket_label_text(text):
    """W62: bracket 대용 헤더를 정상 교재와 같은 `[라벨]` 형태로 정규화.

    비상(황) 실증 — 이 원고의 지문번호는 "1과 MR1" 평문이라 템플릿의
    지문번호 GREP(대괄호/중괄호 표기 → 지문번호 문자스타일)이 하나도
    걸리지 않아 본문과 똑같이 인쇄됐다(사용자 지적 "지문번호도 안
    입혀져있다"). `[MR1]`로 감싸면 기존 스타일 체계가 그대로 적용된다.
    선행 과/강 접두("1과 ")는 라벨의 일부가 아니라 문서 전체 공통값이라
    제거한다."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    t = _RE_LEAD_LESSON.sub("", t)
    t = t.lstrip(" .,·-–—")          # W68: "11강., Gateway" → "Gateway"
    if not t:
        return text
    if t.startswith("[") and t.endswith("]"):
        return t
    # W68: "1번"/"1"/"exercise 01" 꼴은 다른 스텝의 지문번호(01,02…)와 같은
    # 표기로 — 한 강 안에서 섹션마다 번호 표기가 달라 보이지 않게 한다.
    # ("MR1"처럼 공백 없이 붙은 코너명은 라벨 자체라 건드리지 않는다.)
    m = re.match(r"^(?:\d{1,2}강\s*[.,]?\s*)?"
                 r"(?:exercise|ex|no\.?|번호)?\s*(\d{1,3})\s*번?$", t, re.I)
    if m and m.group(1):
        t = "%02d" % int(m.group(1))
    return "[" + t + "]"


def _absorbed_idx(paragraphs):
    """W61: 헤더 블록으로 흡수된 라인(출처/과 제목 반복) 인덱스 —
    bracket 유무와 무관하게 제거 대상."""
    texts = [(p.get("text") or "") for p in paragraphs or []]
    if not texts:
        return set()
    try:
        det = detect_headers(texts, legacy=is_header_line)
    except Exception:                                          # noqa: BLE001
        return set()
    return set(det.absorbed_idx)


def _bracket_fallback_idx(paragraphs):
    """지문 시작 구조 헤더 인덱스 집합 (bracket 라벨을 보완).

    W68 (수특라이트 11강 실증 — 사용자 지적 "지문번호 인식 못했어"):
    이 원고의 지문 라벨은 `[gateway]` **하나만** 대괄호고 나머지 넷은
    평문("11강 1번")이다. 구 규칙은 '대괄호가 하나라도 있으면 구조
    폴백을 끈다'였기 때문에 라벨 5개 중 1개만 앵커가 되어 지문 5개가
    한 유닛으로 뭉쳤다(=지문번호 실종). 대괄호 수보다 구조 헤더가
    많으면 둘의 합집합을 앵커로 쓴다 — 대괄호가 제대로 라벨 노릇을
    하는 기존 원고(대괄호 ≥ 구조 헤더)는 판정이 그대로다."""
    texts = [(p.get("text") or "") for p in paragraphs or []]
    if not texts:
        return set()
    try:
        det = detect_headers(texts, legacy=is_header_line)
    except Exception:                                          # noqa: BLE001
        return set()
    # 강한 근거(직후 영어 본문)를 가진 헤더만 — 라벨 오검출로 유닛이
    # 잘게 쪼개지는 것 방지
    strong = {c["i"] for c in det.candidates
              if c["signals"].get("body_next")}
    heads = {i for i in det.header_idx if i in strong}
    n_bracket = sum(1 for t in texts if _is_bracket_para(t))
    if n_bracket and len(heads) <= n_bracket:
        return set()        # 대괄호가 라벨 노릇을 하고 있다 — 기존 동작
    return heads


def _is_bracket_para(text):
    """v1 isBracketPara: [XX] 단독 단락 (내용 없는 [  ]는 제외)."""
    if not _RE_BRACKET.match(text or ""):
        return False
    inner = re.sub(r"\]\s*$", "", re.sub(r"^\s*\[", "", text))
    return len(re.sub(r"\s", "", inner)) > 0


def _has_circled(text):
    """v1 processStep2A1Btm isPassage: ①~⑳ (U+2460~2473) 포함 여부."""
    return any(0x2460 <= ord(ch) <= 0x2473 for ch in text or "")


def _norm_header(s):
    s = (s or "").replace("\ufeff", "")
    s = re.sub("[\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()


# W25: 헤더 꼬리 주석 "(정답 1개)" — 본체 패턴 매칭 **전에** 벗긴다.
# 꼬리 그룹 `(?:\([^\)]{0,40}\))?` 을 각 패턴이 개별로 달고 있던 탓에, 꼬리를
# 안 단 패턴(코너명형 수능Analysis/수능대비ANALYSIS, Practice형, 서술형
# Practice, no.N형, L-p형)은 "(정답 N개)"가 붙은 헤더를 통째로 놓쳤다.
# 하단 문제(step2_a1_btm) 헤더는 관행적으로 항상 이 꼬리가 붙기 때문에
# 그 스텝의 헤더가 legacy 프라이어에서 전멸한다 —
# 코퍼스 r2c12ext2/r2c14ext3 실측: step2_a1_btm 헤더 4/4개 False.
# (v2는 구조 인식기가 구제하지만 legacy는 '항상 유지'하는 하위호환 하한선
#  이라 여기가 뚫리면 구조 신호가 약한 원고에서 그대로 미인식이 된다.
#  v1 run.jsx isHeaderLine도 같은 구조라 헤더가 지면에 인쇄됐다.)
# 패턴마다 꼬리 그룹을 덧붙이는 대신 한 곳에서 벗겨, 새 패턴이 추가돼도
# 같은 함정에 다시 빠지지 않게 한다.
_RE_HDR_TAIL_PARENS = re.compile(r"(?:\s*\([^()]{0,40}\))+\s*$")


def is_header_line(text):
    """v1 isHeaderLine: 'N. p2-no.20' 류 지문 헤더 (제거+프레임 분리 대상)."""
    hn = _norm_header(text)
    if len(hn) > 60:
        return False
    if _RE_SUPP.match(hn):
        return True
    body = re.sub(r"^\d+\s*[.)]?\s*", "", hn)
    if not body or len(body) > 50:
        return False
    compact = re.sub(r"\s+", "", body)
    if any(p.match(compact) for p in _HEADER_PATTERNS):
        return True
    # 기존 판정이 False일 때만 꼬리 주석을 벗겨 재시도 (additive — 기존
    # True 판정은 위에서 그대로 반환되므로 회귀 없음).
    stripped = _RE_HDR_TAIL_PARENS.sub("", body).strip()
    if not stripped or stripped == body:
        return False
    compact = re.sub(r"\s+", "", stripped)
    return any(p.match(compact) for p in _HEADER_PATTERNS)


# ── W31: 구조 우선 헤더 인식 (문서 단위 — 정규식 열거는 프라이어로 강등) ─────
# 새 인식기(core/structure/header_detect)가 1선, 기존 is_header_line/
# is_a1_header는 legacy 프라이어(가산점 + 하위호환 보장 — legacy 인식분은
# 항상 유지). False로 내리면 기존 정규식 열거 단독 동작 (안전 밸브).
USE_STRUCT_HEADER_DETECT = True


def _step_header_detection(step_data, step_name, legacy, strict=True):
    """스텝 원고 전체를 문서 단위로 훑어 헤더 인덱스 집합을 얻는다.

    strict=True: 침묵 금지 — 강한 구조 후보(직후 영어 본문)가 2+개인데
    인식이 0~1개면 HeaderSilenceError로 조판 중단 (경고 아님)."""
    texts = [(p.get("text") or "")
             for p in step_data.get("paragraphs", []) or []]
    det = (detect_headers(texts, legacy=legacy)
           if USE_STRUCT_HEADER_DETECT else _legacy_only(texts, legacy))
    if strict and USE_STRUCT_HEADER_DETECT and det.silent():
        raise HeaderSilenceError(step_name, det)
    _drop_shape_outliers(det, texts, step_name, legacy)
    return det


# 한 스텝 안의 지문 헤더는 **형태가 같다**("1. p3-no.250921" 처럼 no. 표기).
# 구조 인식기의 anchor 규칙은 "짧은 번호 줄 + 뒤에 영어 본문"을 헤더 후보로
# 보는데, 본문 안의 짧은 번호 문장이 그 모양과 같으면 헤더로 오인한다.
#   실측 2026-08-17 (고2 25년 9월 어법OX): "29.  The examples are endlessly."
#   가 헤더로 잡혀 유닛이 16→17로 갈리고 그 문장이 지면에서 사라졌다.
#   (조판 전 구조 검사가 막아 조판은 시작도 못 했다)
# 다수파가 no. 표기를 갖는데 소수가 안 갖는다면 그 소수는 본문이다.
#
# W25 — 단, 이 '소수파 정정'은 **구조 인식기가 승격한 라인**에만 적용해야
# 한다. legacy 프라이어(정규식 열거)가 헤더라고 확언한 라인까지 떨어뜨리면
# header_detect의 호환성 계약("legacy 인식분은 항상 유지")을 깨고, 한 스텝
# 안에 표기가 섞인 정상 원고에서 그 소수 표기의 지문이 통째로 사라진다.
#   실측 2026-08-24 (올림포스 독해기본2 1강 어법선택 하단 문제 — 사용자
#   지목): 헤더 4개 중 3개가 "N. pN-no.0N", 1개가 코너명형
#   "1. p8-수능 대비 ANALYSIS". 다수파 규칙이 그 1개를 본문으로 정정해
#   유닛이 4→3으로 줄고 1번 지문(Bloom Cookie)이 지면에서 사라졌다.
#   같은 헤더가 다른 스텝에서는 본문 단락으로 남아 그대로 인쇄됐다.
# 원래 막으려던 오탐("29.  The examples are endlessly.")은 legacy가 False라
# 여전히 정정 대상 — 가드의 효력은 그대로다.
_RE_HDR_NO = re.compile(r"no\.?\s*\d", re.I)
# W75 (수특라이트 13강 실증 — 사용자 지적 "어법선택 객관식 게이트웨이 문제가
# 누락됐어"): 이 정정이 노린 오탐("29.  The examples are endlessly.")은 지문
# 마커가 **없는** 본문 문장이다. 반면 소수 표기 헤더("1. p86-Gateway")는
# 다수와 같은 페이지 마커(pN)를 갖는 같은 계열 헤더다 — 표기(no.) 하나로
# 지우면 그 지문이 통째로 사라지거나(하단 문제) 헤더 원문이 인쇄된다
# (빈칸어법). 마커를 가진 줄은 정정 대상에서 뺀다.
_RE_HDR_MARKER = re.compile(
    r"\bp\.?\s*\d|\bno\.?\s*\d|\bL\s*\d|\bU\s*\d|본문\s*\d|"
    r"\d\s*[과강]", re.I)


def _drop_shape_outliers(det, texts, step_name, legacy=None):
    idx = sorted(det.header_idx)
    if len(idx) < 3:
        return                      # 표본이 적으면 다수파를 못 정한다
    with_no = [i for i in idx if _RE_HDR_NO.search(texts[i] or "")]
    if len(with_no) < 2 or len(with_no) == len(idx):
        return                      # no. 형식 원고가 아니거나 이미 균일
    if len(with_no) < len(idx) * 0.7:
        return                      # 다수파라 할 수 없으면 건드리지 않는다
    for i in idx:
        if i in with_no:
            continue
        if callable(legacy) and legacy(texts[i] or ""):
            continue                # legacy 확언 헤더 — 정정 대상 아님
        if _RE_HDR_MARKER.search(texts[i] or ""):
            continue                # W75: 같은 계열 마커 보유 — 헤더 유지
        det.header_idx.discard(i)
        print("[헤더인식] %s: 본문으로 정정 (다수 헤더는 no. 표기) — %r"
              % (step_name, (texts[i] or "")[:40]), flush=True)


def _legacy_only(texts, legacy):
    """안전 밸브 경로 — 기존 정규식 열거만으로 Detection 구성."""
    from core.structure.header_detect import Detection
    det = Detection()
    for i, t in enumerate(texts):
        if legacy(t):
            det.header_idx.add(i)
    return det


# v1 processStep2A1의 헤더 판정 (isA1Header — 헤더를 지우지 않고 {tail}로 변환)
_RE_A1_L = re.compile(r"^\s*\d+\s*[.)]?\s*L\d+\s*[-–—﹣－]\s*.+",
                      re.I)
_RE_A1_PNO = re.compile(
    r"^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-–—﹣－]|\s)*"
    r"no\.?\s*\d+(?:~\d+)?\b.*$", re.I)
_RE_A1_PDESC = re.compile(
    r"^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-–—﹣－]|\s)+\s*.+$",
    re.I)
_RE_A1_ANALYSIS = re.compile(r"^\s*\d+.*수능\s*대비\s*analysis.*$", re.I)
_RE_A1_BONMUN = re.compile(r"^\s*\d+\s*[.)]?\s*.*?본문\s*\d+\s*$", re.I)
# 외부지문 무-p형 (W21 r11): "1. no.1" — v1 실물(워크북03(외부지문))은
# 조판사가 손으로 {1}~{4} 정규화 + 프레임 분리를 복원했다 (스토리 61 실측).
_RE_A1_NO = re.compile(r"^\s*\d+\s*[.)]?\s*no\.?\s*\d+(?:~\d+)?\s*$", re.I)


def is_a1_header(text):
    t = re.sub(r"[\r\n]", "", text or "")
    return bool(_RE_A1_L.match(t) or _RE_A1_PNO.match(t)
                or _RE_A1_PDESC.match(t) or _RE_A1_ANALYSIS.match(t)
                or _RE_A1_BONMUN.match(t) or _RE_A1_NO.match(t))


def extract_tail(text):
    """v1 processStep2A1 extractTail: 헤더 → {tail} 정규화용 꼬리 추출."""
    s = (text or "").strip()
    m = re.search(r"(본문\s*\d+)\s*$", s, re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)?"
                 r"\s*[-–—]?\s*(본문\s*\d+)\b", s, re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\s*(\d+)[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)\s*$",
                 s, re.I)
    if m:
        return "본문" + m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)?"
                 r"\s*[-–—]?\s*(.+)$", s, re.I)
    if m:
        return re.sub(r"^\s*p\.?\s*\d+\s*[-–—]?\s*", "", m.group(1),
                      flags=re.I)
    # 한글 꼬리가 지문번호에 직결된 추가지문형 ("no.3과 추가지문" → "3과
    # 추가지문", W11) — 번호+꼬리 전체가 라벨. 아래 기존 분기보다 먼저 검사
    # (기존 분기는 번호와 꼬리를 분리해 "과 추가지문"만 남긴다).
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*"
                 r"(\d+(?:~\d+)?[가-힣][가-힣0-9\s]*[가-힣0-9])\s*"
                 r"(?:\([^)]*\))?\s*$", s, re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*(\d+(?:~\d+)?)"
                 r"(?:[\s-]*(.+))?$", s, re.I)
    if m:
        return m.group(2) if m.group(2) else m.group(1)
    # 외부지문 무-p형 (W21 r11): "1. no.1" → "1" — p-형("1. p2-no.20"→"20")과
    # 동일하게 no-번호를 라벨로 (v1 실물 {1}~{4} 대조). 기존 분기 무변경 삽입.
    m = re.match(r"^\s*\d+[\s.)-]*no\.?\s*(\d+(?:~\d+)?)\s*$", s, re.I)
    if m:
        return m.group(1)
    if re.search(r"수능\s*대비\s*analysis", s, re.I):
        return "분석"
    # 부교재 코너명형 (W12): "N. pN-수능 Analysis" → "분석N" (선행 순번 —
    # C1 GREP {분석N}/원고 [분석N] 마커 관행과 일치). 기존 분기 무변경 삽입.
    m = re.match(r"^\s*(\d+)[\s.)-]*p\.?\s*\d+[\s-]*수능\s*Analysis\s*$",
                 s, re.I)
    if m:
        return "분석" + m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+\s*(?:[-–—]|\s)+\s*(.+)$",
                 s, re.I)
    if m:
        return m.group(1)
    # W74 (올포기출 13강 실증 — 사용자 지적 "어법선택 상단프레임 지문번호에
    # 문자스타일 안 입혀짐"): 위 형식 열거가 전부 빗나가면 꼬리가 빈
    # 문자열이라 헤더가 **원문 그대로** 인쇄된다 ({tail} 로 안 감싸이니
    # 템플릿의 지문번호 GREP도 안 걸린다). 페이지 마커(p12) 없이 강 번호만
    # 쓰는 원고("1. 13강 지문1 (2025년 3월 고1 31번)")가 그 경우다.
    # 구조로 꼬리를 남긴다 — 선행 순번 + 꼬리 괄호(출처) + 강/과 접두를
    # 벗긴 나머지. 벗길 게 하나도 없으면 종전대로 빈 문자열(원문 유지).
    # 꼬리가 지문 마커("… no.1")로 끝나면 그 번호가 라벨 (v1 실물 {1}~{4})
    m = re.search(r"\bno\.?\s*(\d+(?:\s*~\s*\d+)?)\s*$", s, re.I)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    t = re.sub(r"^\s*\d{1,3}\s*[.)]\s*", "", s)
    t = re.sub(r"(?:\s*\([^()]*\))+\s*$", "", t)
    t = _RE_LEAD_LESSON.sub("", t).strip(" .,·-–—")
    t = re.sub(r"\s+", " ", t)
    if t and len(t) <= 30 and t != s.strip():
        return t
    return ""


def _mk(text, style, runs):
    return {"t": text, "s": style, "runs": runs or []}


def unit_paras(unit):
    """유닛의 단락 리스트 — list(기존) / {"paras": ...} dict(W4) 겸용."""
    return unit["paras"] if isinstance(unit, dict) else unit


def _map_chars(para, table):
    """텍스트+runs에 1:1 문자 치환 적용 (길이 보존 → runs 오프셋 유지)."""
    text = (para.get("text") or "").translate(table)
    runs = [dict(r, t=(r.get("t") or "").translate(table))
            for r in para.get("runs") or []]
    return {"text": text, "runs": runs}


def _split_tabs(text, runs):
    """v1 grepChange('\\t','\\r') 대응 — 탭 경계에서 단락 분할 (runs도 분할)."""
    if "\t" not in (text or ""):
        return [(text, runs or [])]
    pieces = []
    cur_runs = []
    for r in runs or [{"t": text, "ul": False}]:
        parts = (r.get("t") or "").split("\t")
        for i, part in enumerate(parts):
            if i > 0:
                pieces.append(cur_runs)
                cur_runs = []
            if part:
                cur_runs.append(dict(r, t=part))
    pieces.append(cur_runs)
    return [("".join(r["t"] for r in rs), rs) for rs in pieces]


# ── STEP1 A1 (+A1_2): 어휘 선택 — v1 processStep1A1 ─────────────────────────
# ❮❯→[] 치환, 빈 단락(\r{2,}) 제거, "2. 어휘2단계_Hard" 단락 삭제,
# 지문번호 [N] 기준 유닛 분할(=프레임브레이크), [N] 다음 본문 구간 → A1_어휘 선택.

_A1_TABLE = str.maketrans({"❮": "[", "❯": "]"})


def build_step1_a1(step_data):
    # 지문번호 [N]은 [기본 단락] — v1 processStep1A1은 전체 BASIC_PARA 후
    # 본문 구간에만 A1_어휘 선택을 입히고 bracket은 손대지 않는다 (S1_A_NUM
    # 은 선언만 되고 미사용). v1 실물 대조: 워크북03(외부지문) 스토리 21
    # '[1]' = [기본 단락] (W21 r11 D1 — v2가 NUM을 입히던 것은 이식 오류).
    st_body = _style("STEP1A1", "C")
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    _fb = _bracket_fallback_idx(step_data.get("paragraphs"))   # W59
    _ab = _absorbed_idx(step_data.get("paragraphs"))           # W61 출처
    for _i, raw in enumerate(step_data.get("paragraphs", []) or []):
        p = _map_chars(raw, _A1_TABLE)
        text = p["text"]
        if _i in _ab:
            continue    # W61: 헤더 앞 반복 출처 라인 제거
        if _is_blank(text) or _RE_HARD.match(text):
            continue    # v1: \r{2,}→\r + Hard 단락 remove()
        if _is_bracket_para(text) or _i in _fb:
            if seen_bracket and cur:
                units.append(cur)
                cur = []
            seen_bracket = True
            if _i in _fb:          # W62: 평문 헤더 → [라벨] 정규화
                text = _bracket_label_text(text)
                p = {"text": text, "runs": [{"t": text, "ul": False}]}
            cur.append(_mk(text, "$BASIC", p["runs"]))
        else:
            cur.append(_mk(text, st_body, p["runs"]))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP1 B2: 내용 종합 — v1 processStep1B2 ─────────────────────────────────
# 지문번호 [N] 기준 유닛 분할, [N] 다음 본문 → A2_본문 박스, (N) → 번호,
# 원문자 → 선지. 빈 단락은 유지(v1 동일) — 스타일은 직전 단락을 따라간다.

def build_step1_b2(step_data):
    # 지문번호 [N]은 [기본 단락] — v1 processStep1B2도 전체 BASIC_PARA 후
    # ']' 닫힘 뒤 본문/번호/선지만 스타일링, bracket은 기본 유지 (W21 r11
    # D3 — v1 실물 워크북03(외부지문) 스토리 137 '[1]' = [기본 단락]).
    st_num = "$BASIC"
    st_body = _style("STEP1B2", "P")
    st_q = _style("STEP1B2", "Q")
    st_c = _style("STEP1B2", "C")
    paras = list(step_data.get("paragraphs", []) or [])
    while paras and _is_blank(paras[-1].get("text") or ""):
        paras.pop()     # v1: \r{2,}\s*$ → \r (꼬리 빈 단락 정리)
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    in_body = False     # [N] 직후 본문 구간 (v1: ']' 닫힘 뒤 ~ (N)/원문자 전)
    prev_style = st_body
    _fb = _bracket_fallback_idx(paras)                          # W59
    _ab = _absorbed_idx(paras)                                  # W61 출처
    for _i, p in enumerate(paras):
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if _i in _ab:
            continue    # W61: 헤더 앞 반복 출처 라인 제거
        if _is_bracket_para(text) or _i in _fb:
            if seen_bracket and cur:
                units.append(cur)
                cur = []
            seen_bracket = True
            in_body = True
            if _i in _fb:          # W62: 평문 헤더 → [라벨] 정규화
                text = _bracket_label_text(text)
                runs = [{"t": text, "ul": False}]
            cur.append(_mk(text, st_num, runs))
            prev_style = st_num
            continue
        if _is_blank(text):
            cur.append(_mk(text, prev_style, runs))
            continue
        if _RE_B2_QNUM.match(text):
            style = st_q
            in_body = False
        elif _RE_B2_CHOICE.match(text):
            style = st_c
            in_body = False
        elif in_body:
            style = st_body
        else:
            style = st_body
            warnings.append("step1_b2: 본문 구간 밖 미분류 단락 → P: "
                            + text[:40])
        cur.append(_mk(text, style, runs))
        prev_style = style
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# 서답형 답란 표 판별 (아래 _promote_ansline 에서 사용)
_RE_PAREN_LABEL = re.compile(r"\([^()]{1,12}\)")
_RE_ANS_ARROW_ROW = re.compile(r"^\s*\([^()]{0,8}\)\s*_{3,}.*(?:→|->).*_{3,}")

# 괄호 없는 답란 표 (2026-08-07 사용자 지적: "㉠ ㉡ ㉢, 기호 알맞게 고친
# 표현 — 선지 위에 있는 건데 왜 지문으로 들어가 있어? 이건 선지 헤더잖아").
# 이 원고의 열 머리는 괄호가 아니라 원문자/맨텍스트라 _RE_PAREN_LABEL 기반
# 규칙에 하나도 걸리지 않아 29건이 지문 스타일로 인쇄됐다.
#   "㉠\t\t㉡\t㉢"                 ← 원문자 열 머리
#   "기호        알맞게 고친 표현"   ← 라벨 열 머리
#   "㉠ _____________________"      ← 기입 줄
_RE_CIRCLED = re.compile(r"[㉠-㉭①-⑮ⓐ-ⓞ]")
# W52: '번호     수정안' 열 머리 + '(    ) :      ' 기입 줄 (아잉카류
# 어법 고르기 답란 표 — 0645d4a7 v2_6 사용자 지적 4: 지문 스타일로 인쇄)
_RE_ANS_HEAD_WORDS = re.compile(
    r"(기호|어색한\s*표현|고친\s*표현|알맞게\s*고친|번호|수정안)")
_RE_ANS_PAREN_COLON = re.compile(r"^\s*\(\s*\)\s*:\s*_*\s*$")
_RE_ANS_BLANK_ROW = re.compile(
    r"^\s*[㉠-㉭①-⑮ⓐ-ⓞ]\s*_{3,}\s*$")


def _is_anslabel_head(t):
    """괄호 없는 답란 표의 열 머리인가 (원문자 2개 이상 / 라벨 어휘)."""
    if len(t) > 40 or "_" in t:
        return False
    if len(_RE_CIRCLED.findall(t)) >= 2:
        return True
    return len(_RE_ANS_HEAD_WORDS.findall(t)) >= 2


# ── STEP1 C2 / STEP2 C1: 빈칸 어휘/어법 — v1 processStep1C2/2C1 ─────────────
# 헤더 제거+유닛 분할(insertHeaderBreaks), 빈 단락 제거, 탭→단락 분할,
# 한글 2자+ 단락 → 한글해석 스타일, 나머지 → 기본 스텝 스타일.

def _build_wordfill(step_data, step_unit):
    st_p = _style(step_unit, "P")
    st_k = _style(step_unit, "K")
    units = []
    warnings = []
    cur = []
    # W31: 구조 우선 인식 (legacy is_header_line은 프라이어) + 침묵 금지
    det = _step_header_detection(step_data, step_unit.lower(),
                                 legacy=is_header_line)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        if det.is_header(i):
            if cur:
                units.append(cur)
                cur = []
            continue    # v1: 헤더 단락은 비우고 프레임브레이크만 남김
        if det.is_absorbed(i):
            continue    # W50: 헤더 직전 섹션 타이틀 줄 (헤더 블록 일부)
        if _is_blank(text):
            continue    # v1: insertHeaderBreaks 말미의 빈 줄 일괄 제거
        for piece_text, piece_runs in _split_tabs(text, p.get("runs") or []):
            style = st_k if _RE_KOR2.search(piece_text) else st_p
            cur.append(_mk(piece_text, style, piece_runs))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


def build_step1_c2(step_data):
    return _build_wordfill(step_data, "STEP1C2")


def build_step2_c1(step_data):
    return _build_wordfill(step_data, "STEP2C1")


# ── STEP2 A1: 어법 선택 — v1 processStep2A1 ─────────────────────────────────
# 헤더 → {tail} 정규화(제거 아님), 헤더 기준 유닛 분할(첫 헤더 제외),
# 전 단락 → A1_어법 선택. 빈 단락 유지 (v1 동일 — 유닛 끝이라 지면 영향 없음).

def build_step2_a1(step_data):
    st = _style("STEP2A1", "P")
    units = []
    warnings = []
    cur = []
    seen_header = False
    # W31: 구조 우선 인식 (legacy is_a1_header는 프라이어) + 침묵 금지.
    # 구조 신호로만 잡힌 헤더도 유닛 분할 경계가 된다 ({tail} 정규화는
    # extract_tail이 꼬리를 찾을 때만 — v1 동일: 못 찾으면 원문 유지).
    det = _step_header_detection(step_data, "step2_a1",
                                 legacy=is_a1_header)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if det.is_absorbed(i):
            continue    # W50: 헤더 직전 섹션 타이틀 줄 (헤더 블록 일부)
        if is_a1_header(text) or det.is_header(i):
            if seen_header and cur:
                units.append(cur)
                cur = []
            seen_header = True
            tail = extract_tail(text)
            if tail:
                # W63: 축약 라벨 원고만 다른 스텝과 통일 (그 외 기존 유지)
                lab_t = _header_label(tail) if _LABEL_ABBREV else tail.strip()
                text = "{" + (lab_t or tail.strip()) + "}"
                runs = [{"t": text, "ul": False}]
        cur.append(_mk(text, st, runs))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP2 A1 하단: 어법 선택 객관식 — v1 processStep2A1Btm ──────────────────
# 원문자(①~⑳) 없는 단락 전부 삭제, 지문 1개 = 유닛 1개(프레임 1개),
# 전 단락 → A1_어법 선택 하단. 밑줄은 지문 밑줄 문자스타일 (v1 CS_PASSAGE_UL).

_RE_EN_WORD = re.compile(r"[A-Za-z']+")


def build_step2_a1_btm(step_data):
    st = _style("STEP2A1Practice", "P")
    units = []
    # 유닛 경계는 **헤더**다 (문항 1개 = 프레임 1개).
    # 예전에는 "원문자(①~⑤) 있는 단락 1개 = 유닛 1개" 였는데, 네모형 문항은
    # 지문 외에 선지 ①~⑤ 줄이 따로 있어 한 문항이 여러 유닛으로 쪼개졌다.
    # 그러면 상단(어법선택)과 유닛 수가 어긋나 다른 지문끼리 짝지어진다.
    det = _step_header_detection(step_data, "step2_a1_btm",
                                 legacy=is_header_line)
    cur = None
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        if det.is_absorbed(i):
            continue    # W50: 헤더 직전 섹션 타이틀 줄 (헤더 블록 일부)
        if det.is_header(i):
            cur = []
            units.append(cur)
            continue
        if cur is None:
            continue    # 헤더 이전(책 제목/공통 발문) = 삭제 대상 (v1 동일)
        if p.get("placeholder"):
            continue    # 자리보존 — 유닛은 유지하고 내용만 비운다
        # 원문자(①~⑤)가 있으면 지문 또는 선지. 원문자가 없어도 영문 본문이면
        # 지문이다 — 네모형 문항의 지문은 (A)(B)(C) 표기라 원문자가 없어서,
        # 원문자만 보던 예전 필터가 지문을 통째로 버리고 선지만 남겼다
        # (2026-08-08 실측: 마더텅 26 = 230631).
        if not _has_circled(text) and len(_RE_EN_WORD.findall(text)) < 8:
            continue    # 발문/책 제목/빈 단락 = 삭제 대상 (v1 동일)
        cur.append(_mk(text, st, p.get("runs") or []))
    # 내용이 없는 유닛도 버리지 않는다 — 자리를 지켜야 상·하단이 안 어긋난다
    units = [u if u else [_mk(" ", st, [])] for u in units]
    return {"units": units, "warnings": [],
            "ul_style": "공통 > 지문 밑줄"}


# ── W3 공용: 아이콘 스텝용 헬퍼 ─────────────────────────────────────────────

# v1 hasCircled (1B1에서 사용하는 넓은 원문자 집합: ①~⑳ + ⓵~⓿ + ❶~❿)
_RE_CIRCLED_WIDE = re.compile("[①-⑳⓵-⓿❶-❿]")
# v1 startsWithDaeum: /^(\s*[“”‘’"']*)다음/
_RE_DAEUM = re.compile("^\\s*[\"'“”‘’]*다음")
# v1 STEP1A2 TF 토큰: ❮ T / F ❯
_RE_TF_TOKEN = re.compile("❮\\s*T\\s*/\\s*F\\s*❯")
# v1 STEP1B1 주제/제목 검출: /^\s*\{?\s*(주제|제목)\s*\}?(\s|$)/
_RE_SUBJ_HEAD = re.compile(r"^\s*\{?\s*(주제|제목)\s*\}?(?:\s|$)")
# v1 STEP1B1 교체 정규식(뒤 공백까지 소비): ^(\s*)\{?\s*주제\s*\}?\s*
_RE_SUBJ_STRIP = {
    "주제": re.compile(r"^\s*\{?\s*주제\s*\}?\s*"),
    "제목": re.compile(r"^\s*\{?\s*제목\s*\}?\s*"),
}
# v1 STEP2C2 소괄호 번호 단독줄: ^\s*\(\d{1,2}\)\s*$
_RE_C2_SOLO_NUM = re.compile(r"^\s*\(\d{1,2}\)\s*$")

_ICON_TF_DUP = {"label": "TF 버튼", "pos": "end", "pad": " "}
_ICON_TF_PLACE = {"label": "TF 버튼", "pos": "end", "pad": " ",
                  "mode": "place"}
_ICON_STEP1_Q = {"label": "STEP1 문제아이콘", "pos": "start", "pad": "\t"}
_ICON_STEP2_ANS = {"label": "STEP2 영작 답지", "pos": "start"}


def _cut_span(text, runs, start, end):
    """text[start:end] 구간을 텍스트+runs에서 동시에 제거 (오프셋 정합 유지)."""
    new_text = text[:start] + text[end:]
    new_runs = []
    off = 0
    for r in runs or []:
        t = r.get("t") or ""
        a, b = off, off + len(t)
        head = t[:max(0, min(len(t), start - a))]
        tail = t[max(0, min(len(t), end - a)):]
        kept = head + tail
        if kept:
            new_runs.append(dict(r, t=kept))
        off = b
    return new_text, new_runs


# ── STEP1 A2: 본문 O/X — v1 processStep1A2 ──────────────────────────────────
_RE_A2_CHOICE = re.compile(r"[①-⑩]")
_RE_A2_QUESTION = re.compile(r"\d+\s*[.)]\s*(?:윗글|다음)")


# 전체 기본 단락 → bracket 뒤 영어 본문 = A2_본문 박스, ❮T/F❯ 토큰 단락 =
# A2_OX문제 + 토큰 제거 + TF 버튼 duplicate 삽입. bracket 위 빈 단락 제거(≤5),
# bracket 기준 유닛 분할(=프레임브레이크). bracket/빈 단락은 [기본 단락] 유지.

def build_step1_a2(step_data):
    st_box = _style("STEP1A2", "P")
    st_ox = _style("STEP1A2", "OX")
    # 5지선다 선지 전용 (템플릿 실측: STEP 01 > 하단 문제_선지)
    st_choice = "STEP 01 > 하단 문제_선지"
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    in_choice = False
    _fb = _bracket_fallback_idx(step_data.get("paragraphs"))    # W59
    _ab = _absorbed_idx(step_data.get("paragraphs"))            # W61 출처
    for _i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if _i in _ab:
            continue    # W61: 헤더 앞 반복 출처 라인 제거
        if _is_bracket_para(text) or _i in _fb:
            if seen_bracket and cur:
                # v1 insertFrameBreaksAtBrackets: bracket 위 빈 단락 제거(최대 5)
                guard = 5
                while cur and guard > 0 and _is_blank(cur[-1]["t"]):
                    cur.pop()
                    guard -= 1
                units.append(cur)
                cur = []
            seen_bracket = True
            if _i in _fb:          # W62: 평문 헤더 → [라벨] 정규화
                text = _bracket_label_text(text)
                runs = [{"t": text, "ul": False}]
            cur.append(_mk(text, "$BASIC", runs))
            continue
        n_tok = 0
        while True:
            m = _RE_TF_TOKEN.search(text)
            if not m:
                break
            text, runs = _cut_span(text, runs, m.start(), m.end())
            n_tok += 1
        if n_tok > 0:
            item = _mk(text, st_ox, runs)
            item["icon"] = dict(_ICON_TF_DUP)
            if n_tok > 1:
                warnings.append("step1_a2: 한 단락에 TF 토큰 " + str(n_tok)
                                + "개 → 아이콘 1개만 삽입: " + text[:40])
            cur.append(item)
            continue
        if _is_blank(text):
            cur.append(_mk(text, "$BASIC", runs))   # v1: 기본 단락 유지
            continue
        # 5지선다(①~⑤) 구간 — 일부 회차는 O/X 문항 앞에 5지선다 문제가
        # 하나 더 붙는다. 발문("1. 윗글의 …")과 그 선지를 종전 규칙은
        # "bracket 뒤 영어" 하나로 묶어 **지문 박스**로 인쇄했다
        # (2026-08-06 사용자 지적 + 실측 p21: ①~⑤ 전부 A2_본문 박스).
        # 선지는 전용 스타일(하단 문제_선지), 발문은 기본 단락으로 분리.
        if _RE_A2_CHOICE.match(text.lstrip()):
            in_choice = True
            cur.append(_mk(text, st_choice, runs))
            continue
        if _RE_A2_QUESTION.match(text.lstrip()):
            in_choice = False
            cur.append(_mk(text, "$BASIC", runs))   # 발문은 지문 아님
            continue
        if seen_bracket and re.search(r"[A-Za-z]", text):
            # 선지 구간 안의 이어짐(줄바꿈된 긴 선지)도 선지 스타일 유지
            style = st_choice if in_choice else st_box
            cur.append(_mk(text, style, runs))
        else:
            in_choice = False
            cur.append(_mk(text, "$BASIC", runs))   # 섹션 제목 등 비영어
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP1 B1: 본문 정리 — v1 processStep1B1 ─────────────────────────────────
# {주제}/{제목} 정규화(단독줄은 다음 단락과 병합), bracket(2번째+)·"다음" 발문
# 기준 유닛 분할, 선지 위/제목 앞 빈 줄 보장, "다음" 발문에 STEP1 문제아이콘+탭.

# W74: 각주(어휘 풀이) 줄 — 별표 머리 + "단어: 뜻" (※/＊ 이형 포함)
_RE_GLOSS_NOTE = re.compile(r"^\s*[*※＊✻∗]{1,3}\s*\S[^\r\n]{0,120}?[:：]")


def build_step1_b1(step_data):
    st_all = _style("STEP1B1", "*")
    st_subj = _style("STEP1B1", "SUBJ")
    st_title = _style("STEP1B1", "TITLE")
    st_q = _style("STEP1B1", "Q")
    st_jim = _style("STEP1B1", "P@bottom")
    st_c = _style("STEP1B1", "C")
    st_box = _style("STEP1B1", "Box")
    src = list(step_data.get("paragraphs", []) or [])
    warnings = []
    # W74: 헤더 블록으로 흡수된 줄(라벨 다음 줄의 출처 — "2025년 3월 고1
    # 학력평가 31번") 제거. a1/b2는 이미 _absorbed_idx로 걷어내는데 b1만
    # 빠져 있어, 출처가 라벨로 오인되면 그 줄이 본문 박스를 차지하고
    # 지문이 밀렸다 (올포기출 13강 실증).
    _ab_b1 = _absorbed_idx(src)
    if _ab_b1:
        src = [q for _k, q in enumerate(src) if _k not in _ab_b1]

    # 1) {주제}/{제목} 정규화 — v1 grepChange 3종 + 스타일 패스의 합성.
    #    단독줄("주제")은 다음 비공백 단락과 병합("{주제} <내용>"), 인라인은
    #    접두만 "{주제} "로 재작성. tag로 SUBJ/TITLE 스타일 지정을 예약.
    items = []
    i = 0
    while i < len(src):
        text = src[i].get("text") or ""
        runs = src[i].get("runs") or []
        m = _RE_SUBJ_HEAD.match(text)
        if m:
            kind = m.group(1)
            strip_end = _RE_SUBJ_STRIP[kind].match(text).end()
            prefix = "{" + kind + "} "
            if not text[strip_end:].strip():
                j = i + 1
                while j < len(src) and _is_blank(src[j].get("text") or ""):
                    j += 1
                if j < len(src):
                    nxt_t = src[j].get("text") or ""
                    nxt_r = src[j].get("runs") or []
                    items.append({"t": prefix + nxt_t,
                                  "runs": [{"t": prefix, "ul": False}]
                                  + list(nxt_r),
                                  "tag": kind})
                    i = j + 1
                    continue
                items.append({"t": text, "runs": runs, "tag": None})
                i += 1
                continue
            body_t, body_r = _cut_span(text, runs, 0, strip_end)
            items.append({"t": prefix + body_t,
                          "runs": [{"t": prefix, "ul": False}] + body_r,
                          "tag": kind})
            i += 1
            continue
        items.append({"t": text, "runs": runs, "tag": None})
        i += 1

    # W72 (job c1new 12강 실증 — 사용자 지적 "지문에 단락스타일이 본문
    # 정리로 들어갔다"): 지문 라벨 집합을 **스타일 결정 전에** 만든다.
    # 아래 '라벨 다음 단락 = 본문 박스' 판정이 대괄호 라벨만 보고 있어서,
    # 라벨을 평문으로 적는 원고(12강 '12강 gateway', 11강 '11강 exercise 01')
    # 는 지문이 본문 박스를 못 받고 기본값(B1_내용 정리)으로 인쇄됐다
    # — 완제품(광문2 수특라이트영독3강 p16)은 크림색 본문 박스다.
    # W68이 유닛 경계용으로 만들던 집합을 그대로 앞으로 당겨 공유한다.
    _b1_src = step_data.get("paragraphs") or []
    _b1_fb = _bracket_fallback_idx(_b1_src)
    _b1_labels = set()
    for _i in _b1_fb:
        _lt = re.sub(r"\s+", " ", (_b1_src[_i].get("text") or "")).strip()
        if _lt:
            _b1_labels.add(_lt)
    # 첫 지문의 라벨은 detect_headers가 '앞 문맥 없음'으로 후보에서 빼므로
    # (11강 '11강., Gateway') 선두 짧은 라벨 한 줄을 같은 자격으로 인정한다.
    # 단, 이미 구조 라벨이 잡힌 원고(=대괄호 라벨이 없는 원고)에서만 —
    # 대괄호로 라벨이 오는 기존 교재는 판정이 그대로다.
    for _p in (_b1_src if _b1_fb else []):
        _lt = re.sub(r"\s+", " ", (_p.get("text") or "")).strip()
        if not _lt:
            continue
        if (len(_lt) <= 30 and not re.search(r"[.?!]\s*$", _lt)
                and len(re.findall(r"[A-Za-z]{2,}", _lt)) <= 3):
            _b1_labels.add(_lt)
        break

    # 2) 스타일 결정 (v1 적용 순서: 전체 B1 → 선지 → 하단 → 지문/본문박스
    #    → 주제/제목 → '[' 시작 단락 [기본 단락])
    def _b1_is_label(t):
        if _is_bracket_para(t):
            return True
        n = re.sub(r"\s+", " ", t or "").strip()
        return bool(n) and n in _b1_labels

    out = []
    for it in items:
        text = it["t"]
        style = st_all
        if _RE_CIRCLED_WIDE.search(text) and not _RE_DAEUM.match(text):
            style = st_c
        if _RE_DAEUM.match(text):
            style = st_q
        out.append(_mk(text, style, it["runs"]))
    for k in range(len(items) - 1):
        if (_RE_DAEUM.match(items[k]["t"])
                and re.search(r"[A-Za-z]", items[k + 1]["t"])):
            out[k + 1]["s"] = st_jim
        if _b1_is_label(items[k]["t"]):
            out[k + 1]["s"] = st_box
    for k, it in enumerate(items):
        if it["tag"] == "주제":
            out[k]["s"] = st_subj
        elif it["tag"] == "제목":
            out[k]["s"] = st_title
        zs = re.sub("^[\\s\u00a0\u2000-\u200b]+", "", it["t"])
        if re.match("^[\\[［]", zs):
            out[k]["s"] = "$BASIC"      # v1: bracket 단락 → 기본 단락

    # 2b) W74: 각주(어휘 풀이) — "* dyslexia: 난독증 ** voraciously: 탐욕스럽게".
    # 원고에서 지문 바로 뒤에 오는 이 줄은 지문의 일부다. 예전엔 어떤
    # 스타일 패스에도 안 걸려 기본값(B1_내용 정리)으로 지문 박스 **밖에**
    # 따로 찍혔다 (사용자 지적: "하단 문제_지문 단락스타일로 들어가서
    # 오른쪽 정렬되어야 하는데 별도로 조판됨"). 앞 단락이 지문이면 같은
    # 스타일 + 오른쪽 정렬로 붙인다 — 별표 머리 + 콜론이라는 구조로만
    # 판정하므로 표기가 바뀌어도(※, ＊) 걸린다.
    for k in range(1, len(out)):
        if not _RE_GLOSS_NOTE.match(items[k]["t"]):
            continue
        prev_s = out[k - 1]["s"]
        if prev_s not in (st_jim, st_box):
            continue
        out[k]["s"] = prev_s
        out[k]["align"] = "right"

    # 3) 선지(원문자) 위 빈 줄 보장 (역순 — v1과 동일 조건)
    k = len(out) - 1
    while k > 0:
        t = out[k]["t"]
        if _RE_CIRCLED_WIDE.search(t) and not _RE_DAEUM.match(t):
            prev = re.sub(r"[\r\n]", "", out[k - 1]["t"])
            if prev != "" and not _RE_CIRCLED_WIDE.search(prev):
                out.insert(k, _mk("", st_all, []))
        k -= 1

    # 4) {제목} 앞 빈 줄 보장 (역순)
    k = len(out) - 1
    while k >= 1:
        if out[k]["s"] == st_title:
            prev = re.sub(r"[\r\n]", "", out[k - 1]["t"])
            if prev != "":
                out.insert(k, _mk("", st_title, []))
        k -= 1

    # 5) "다음" 발문에 아이콘+탭 (실행기 최종 패스에서 삽입)
    for item in out:
        if _RE_DAEUM.match(item["t"]):
            item["icon"] = dict(_ICON_STEP1_Q)

    # 6) 유닛 분할: bracket(2번째+) + 모든 "다음" 발문 (v1 프레임브레이크 대상)
    # W68 (11강 실증 — 사용자 지적 "본문정리는 또 왜 이러는 건데"): 이 원고의
    # 지문 라벨은 대괄호가 아니라 평문("11강 exercise 01")이라 경계가 되지
    # 못했고, 다음 지문 블록이 앞 문항(하단)의 꼬리에 그대로 붙었다.
    # a1/a2/b2와 같은 계약으로 구조 헤더도 경계·지문번호로 쓴다.
    # (인덱스는 위 병합/빈줄 삽입으로 밀리므로 **텍스트**로 대조한다.)
    units = []
    cur = []
    seen_bracket = False
    for item in out:
        t = item["t"]
        _norm = re.sub(r"\s+", " ", t).strip()
        if not _is_bracket_para(t) and _norm and _norm in _b1_labels:
            # 평문 라벨 → 다른 스텝과 같은 [라벨] 표기로 (지문번호 스타일)
            t = _bracket_label_text(_norm)
            item["t"] = t
            item["runs"] = [{"t": t, "ul": False}]
            item["s"] = "$BASIC"
        if _is_bracket_para(t):
            # W63: 지문번호 표기를 다른 스텝과 통일 ("[1과 MR1]"→"[MR1]")
            inner = re.sub(r"^\s*\[|\]\s*$", "", t)
            lab = _header_label(inner)
            if lab and lab != inner.strip():
                t = "[" + lab + "]"
                item["t"] = t
            if seen_bracket and cur:
                units.append(cur)
                cur = []
            seen_bracket = True
        elif _RE_DAEUM.match(t) and cur:
            units.append(cur)
            cur = []
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP2 B1: 어법 OX — v1 processStep2B1 ───────────────────────────────────
# insertHeaderBreaks 의미론(헤더 제거+유닛 분할+빈 단락 제거 — W2 재사용),
# 각 내용 단락 끝에 TF 버튼(링크 place + 너비 스케일) 삽입.

def build_step2_b1(step_data):
    st = _style("STEP2B1", "*")
    units = []
    cur = []
    # W31: 구조 우선 인식 (legacy is_header_line은 프라이어) + 침묵 금지
    det = _step_header_detection(step_data, "step2_b1",
                                 legacy=is_header_line)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        if det.is_header(i):
            if cur:
                units.append(cur)
                cur = []
            continue
        if det.is_absorbed(i):
            continue    # W50: 헤더 직전 섹션 타이틀 줄 (헤더 블록 일부)
        if _is_blank(text):
            continue    # v1 insertHeaderBreaks 말미 GREP이 빈 줄 일괄 제거
        item = _mk(text, st, p.get("runs") or [])
        item["icon"] = dict(_ICON_TF_PLACE)
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": []}


# ── STEP2 C2: 영작 배열 — v1 processStep2C2 ─────────────────────────────────
# (N) 단독줄·빈 단락·영어 전용(한글/슬래시/bracket 없음) 단락 삭제,
# 한글 2자+ → 번호, 슬래시 → 보기(우선), [/] 포함 → 기본. 보기 블록 끝마다
# 빈 단락+STEP2 영작 답지 아이콘, bracket 앞 빈 줄 2개(이전 유닛 꼬리),
# bracket 기준 유닛 분할.
# EBS 분기 (v1 run.jsx 2125 — 리딩파워는 문제들이 연속해서 흐름): bracket
# 유닛 분할(프레임브레이크) 생략, 대신 bracket 앞 빈 줄 2개만 같은 유닛에
# 유지 (v1 7단계는 유형 공통, 9단계 브레이크만 EBS 생략).

_RE_C2_PAGEMARK = re.compile(r"\bp\.?\s*\d", re.I)


def _c2_is_bracket(text):
    # v1 step9 판정: '['와 ']' 포함 + '\s*[' 시작
    return ("[" in text and "]" in text
            and bool(re.match(r"^\s*\[", text)))


def build_step2_c2(step_data, workbook_type="모의고사"):
    st_num = _style("STEP2C2", "Q")
    st_view = _style("STEP2C2", "Box")
    is_ebs = (workbook_type == "EBS")
    warnings = []

    # 1) 삭제 룰 (v1 1~2단계: (N) 단독줄, 빈 단락, 영어 전용 답 단락)
    kept = []
    # W31: 구조 우선 인식 — 새 형식 헤더도 제거 (유닛은 bracket 기준이라
    # 침묵 게이트는 비적용 strict=False).
    det = _step_header_detection(
        step_data, "step2_c2",
        legacy=lambda t: is_header_line(_norm_header(t)), strict=False)
    # W67 (사용자 지적 2026-08-14 "영작배열은 왜 지문 번호 없이 다 이어져서
    # 들어갔어"): C2의 유닛 분할·지문번호는 bracket 단락이 담당하는데,
    # 이 원고의 지문 헤더는 "1. p50-no.01" p형이라 bracket이 하나도 없어
    # 전부 '헤더 제거' 대상이 됐다 → 유닛 1개, 라벨 0개. bracket이 없는
    # 원고에선 구조 헤더를 [라벨]로 정규화해 그 자리를 대신하게 한다
    # (A1/B1이 W59/W62에서 쓰는 _bracket_fallback_idx와 같은 계약).
    # bracket이 하나도 없는 원고에서만 발동 — 기존 bracket 원고는 무영향.
    _c2_paras = step_data.get("paragraphs", []) or []
    _no_bracket = not any(_c2_is_bracket(q.get("text") or "")
                          for q in _c2_paras)

    def _c2_strong_header(i, text):
        """이 헤더 검출을 '강한 것'으로 볼지 (W75).

        seq(시퀀스 단조성)만으로 잡힌 약한 검출은 원칙적으로 제외한다 —
        모의고사 C2의 "20번" 문항 라벨은 v1이 인쇄하는 내용이기 때문
        (코퍼스 r9c20mock2503 실증). 다만 **페이지 마커(pN)** 를 가진 줄은
        그 스텝 헤더 계열과 같은 형태다: 수특라이트 13강처럼 첫 지문만
        표기가 다르면(N. pN-Gateway) seq 로만 잡히는데, 여기서 빼면 그
        지문이 라벨 없이 앞 유닛에 붙는다 (사용자 지적 "영작배열
        게이트웨이도 지문번호 없이 그냥 조판됐어")."""
        if det.via(i) != "seq":
            return True
        return bool(_RE_C2_PAGEMARK.search(text or ""))
    for i, p in enumerate(_c2_paras):
        text = p.get("text") or ""
        if _no_bracket and det.is_header(i) and _c2_strong_header(i, text):
            lab = re.sub(r"^\s*\[|\]\s*$", "", _header_label(text) or "")
            lab = lab.strip()
            # W74: 강 접두("13강 지문 1")는 문서 전체 공통값이라 지문번호가
            # 아니다 — a1/b1이 _bracket_label_text에서 벗기는 것과 같은 계약.
            # 교과서의 "3과 추가지문"(과 접두)은 라벨 자체라 건드리지 않는다.
            lab = re.sub(r"^\d{1,2}\s*강\s*", "", lab).strip() or lab
            if lab:
                kept.append({"text": "[" + lab + "]",
                             "runs": [{"t": "[" + lab + "]", "ul": False}]})
                continue
        if _RE_C2_SOLO_NUM.match(text):
            continue
        if _is_blank(text):
            continue    # v1: \r{2,} → \r
        # 지문 헤더 제거 (W17 c11: "1. L1-본문1" 한글 포함 헤더가 v1의
        # eng_only 삭제 룰을 비껴가 문항번호 스타일로 인쇄됨 — G1 검출.
        # 모의고사형 헤더("1. p16-no.01")는 eng_only가 이미 삭제하던 것과
        # 동일 의미론 — 지문 번호는 독립 프레임(passage_numbers) 담당).
        # bracket 단락([Project 1-1] 등)은 C2의 유닛 분할 마커라 제거
        # 금지 (W31 코퍼스 diff 실증: r3c13ybm 유닛 2→1 회귀 방지).
        # seq(시퀀스 단조성)만으로 잡힌 약한 검출도 제거 금지 — 모의고사
        # C2의 "20번" 문항 라벨은 v1이 인쇄하는 내용이다 (코퍼스 diff
        # 실증: r9c20mock2503/r10c22mock2503g1). C2는 유닛을 bracket이
        # 담당하므로 제거는 강한 검출(legacy/anchor/shape)로만.
        if (det.is_header(i) and not _c2_is_bracket(text)
                and _c2_strong_header(i, text)):
            continue
        if det.is_absorbed(i) and not _c2_is_bracket(text):
            continue    # W50: 헤더 직전 섹션 타이틀 줄 (헤더 블록 일부)
        has_br = "[" in text and "]" in text
        eng_only = (re.search(r"[A-Za-z]", text)
                    and not re.search("[가-힣]", text)
                    and "/" not in text)
        if eng_only and not has_br:
            continue    # 영어 정답 문장 삭제
        kept.append(p)

    # 2) 스타일 (v1 3~5단계 + 9단계 bracket→기본 오버라이드)
    styled = []
    for p in kept:
        text = p.get("text") or ""
        style = "$BASIC"
        if _RE_KOR2.search(text):
            style = st_num
        if "/" in text:
            style = st_view
        if "[" in text or "]" in text:
            style = "$BASIC"
        styled.append(_mk(text, style, p.get("runs") or []))

    # 3) 보기 블록 끝마다 빈 단락 + 아이콘 (v1 6단계)
    out = []
    for k, item in enumerate(styled):
        out.append(item)
        if item["s"] == st_view and (k + 1 >= len(styled)
                                     or styled[k + 1]["s"] != st_view):
            icon_para = _mk("", "$BASIC", [])
            icon_para["icon"] = dict(_ICON_STEP2_ANS)
            out.append(icon_para)

    # 4) 유닛 분할 + bracket 앞 빈 줄 2개 보장 (v1 7·9단계 —
    #    빈 줄은 프레임브레이크 앞 = 이전 유닛 꼬리에 붙는다).
    #    EBS: 유닛 분할 없이 빈 줄 2개만 (v1 9단계 브레이크 생략 분기).
    units = []
    cur = []
    seen_bracket = False
    for item in out:
        if _c2_is_bracket(item["t"]):
            if seen_bracket and cur:
                cur.append(_mk("", "$BASIC", []))
                cur.append(_mk("", "$BASIC", []))
                if not is_ebs:
                    units.append(cur)
                    cur = []
            seen_bracket = True
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── W4: STEP1 C1 문장 배열 — v1 processStep1C1 (최난) ───────────────────────
# 원본: engines/workbook/jsx/run.jsx 1136~1648. 패스 순서를 v1 그대로 유지:
# 공백 bracket 제거 → 헤더 정규화 GREP → 레지듀얼 정리 → 프리앰블 제거 →
# 스타일 패스(기본/BTM/C1/BTM갭/BTM_T/원문자/갭 빈줄 제거/교과서 분기) →
# 화살표 아이콘 → 발문 삽입 → { 안전망 → 헤더 잔재 정리 → (하단 제외) →
# 유닛 분할(헤더=NEXT_PAGE|EBS는 NEXT_FRAME, 블록 첫 하단 단락=NEXT_FRAME).

_RE_C1_HEADER = re.compile(r"^\s*\{[^}]+\}")
# W68: 원고에만 있는 발문 표기("Q. …") / 강 표제("11강. 흐름에 무관한 …").
# 엔진이 넣는 발문은 "Q."로 시작하지 않는다 — 그래서 이 둘만 안전하게 걷힌다.
_RE_C1_MANU_PROMPT = re.compile(r"^\s*Q\s*[.:]\s*\S")
_RE_C1_LESSON_TITLE = re.compile(r"^\s*\d{1,2}\s*[강과]\s*[.,]\s*\S")
# W78 (2026-08-27 비상(황) 3과 실증 — 사용자 지적 "하단 문제가 MR1만 들어감"):
# "Q."는 원고 발문만의 표기가 아니다. 교과서 지문 자체가 Q&A 표제를 쓰면
# ("Q. What happens in our brain when we read?") 그 줄이 하단 슬롯의
# 주어진 문장이자 지문 본문인데, 리터럴 `^Q[.:]`가 이를 발문으로 보고
# 6줄을 걷어내 10지문 중 6지문의 하단 문제가 통째로 사라졌다.
# 구조로 가른다 — **지시문은 한국어다**. 발문은 학생에게 주는 한국어 명령이고
# (엔진이 넣는 발문도, 원고가 적어 둔 중복 발문도 전부 한글), "Q." 뒤가
# 영어로만 이어지는 줄은 지문 내용이다.
_RE_C1_HANGUL = re.compile(r"[가-힣]")


def _c1_is_manu_prompt(text):
    """원고 발문 표기("Q. …") 여부 — 한국어 지시문일 때만 참."""
    t = text or ""
    return bool(_RE_C1_MANU_PROMPT.match(t) and _RE_C1_HANGUL.search(t))
_RE_C1_CHOICE = re.compile(r"^\s*\([A-Z]\)")
_RE_C1_ABC = re.compile(r"^\s*\(([ABC])\)")
_RE_C1_EMPTY_BRACKET = re.compile(
    "^\\s*\\[[\\s  -​]*\\]\\s*$")
_RE_C1_NUM_BRACKET = re.compile(r"^\s*\[\d+")
# v1 hits7 (원문자 → 하단 지문): ①-⑳ + ⓵-⓿ + ❶-➓
_RE_C1_CIRCLED_WIDE = re.compile("[①-⑳⓵-⓿❶-➓]")
_RE_C1_CIRCLED_PROMPT = re.compile("[①-⑳]")   # 발문 유형 판별용
# v1 has3PlusGaps: 공백류 3연속 이상
_RE_3GAPS = re.compile("[ \\t  -​  　]{3,}")

# v1 헤더 정규화 GREP 체인 (순서 보존 — InDesign GREP과 동일 의미의 파이썬 re)
_C1_GREPS = [
    # 추가지문형: 번호+한글 꼬리 전체를 라벨로 ("no.3과 추가지문" →
    # "{3과 추가지문}", W11). 한글 꼬리 없으면 다음 룰(기존)이 담당.
    (re.compile(r"\bno\.\s*(\d{1,3}(?:~\d{1,3})?[가-힣][가-힣0-9\s]*[가-힣0-9])"),
     r"{\1}"),
    (re.compile(r"\bno\.\s*(\d{1,3}(?:~\d{1,3})?)"), r"{\1}"),
    # W69 (job a3d13ab3 수특라이트 12강 — 사용자 확정): EBS 강 대표지문
    # 헤더 "N. [문장삽입] p78-Gateway"는 no.N 형식이 아니라 어느 룰에도
    # 안 걸렸다 → 헤더 줄이 본문에 그대로 인쇄(9번)되거나, W44 승격이
    # 문항번호를 라벨로 올려 {14} 같은 가짜 지문번호가 찍혔다(14번).
    # 다른 스텝(step1_a1/b1)이 원고의 [12강 gateway]/[gateway] 라벨을
    # 그대로 인쇄하는 관행에 맞춰 {gateway}로 정규화한다.
    (re.compile(r"\bp\.?\s*\d+\s*[-–—]?\s*Gateway\b", re.I),
     "{gateway}"),
    (re.compile(r"\bExample\s+(\d{1,3})"), r"{\1}"),
    (re.compile(r"\b(\d+)\.\s*p\d+\s*[-–—]?\s*Example\b"),
     r"{\1}"),
    # 부교재 코너명형 (W12): "N. pN-수능 Analysis" → {분석N} (선행 순번 —
    # 같은 원고의 [분석N] 마커 관행과 일치), "N. pN-Practice 0M" → {M}
    # ([M] 마커 관행과 일치, 선행 0 제거). 기존 룰 무변경 삽입 — 아래
    # ANALYSIS(대문자 전용)/서술형 Practice 룰과 매치 집합이 겹치지 않는다.
    (re.compile(r"\b(\d+)\.\s*p\d+\s*[-–—]?\s*수능\s*Analysis\b", re.I),
     r"{분석\1}"),
    (re.compile(r"\b\d+\.\s*p\d+\s*[-–—]?\s*Practice\s*0*(\d{1,3})\b"),
     r"{\1}"),
    (re.compile(r"\bANALYSIS\b"), "{분석}"),
    (re.compile(r"\b\d+\.\s*L\d+\s*[-–—.]?\s*p\.?\s*\d+"
                r"[^\r\n]*?본문\s*(\d+)\b"), r"{본문\1}"),
    (re.compile(r"L\d+\s*[-–—.]?\s*p\.?\s*\d+"
                r"[^\r\n]*?본문\s*(\d+)\b"), r"{본문\1}"),
    # (?<!\{): 이미 {본문N}으로 정규화된 라벨 재래핑 방지 — 위 L-p 룰이
    # 만든 "{본문1}"이 "{{본문1}}"로 이중 래핑돼 인쇄되던 것 교정
    # (W30-r15 — 실서비스 376b34d0 실측. v1 JSX도 같은 순서라 동일 증상
    # 이었을 형태지만 이 헤더형("N. L1-p. 13 본문 1")은 v2 첫 실사용 —
    # 완제품 기준 교정. "N. L1-본문1"류 기존 경로는 '-' 선행이라 무영향).
    # W49: `\d+` → 하위분할 순번(본문2-1)까지 라벨에 포함. `\d+`만 잡으면
    # "본문2-1(p.18)" → "{본문2}-1(p.18)"로 (a) 라벨 충돌(2-1·2-2 둘 다 {본문2}),
    # (b) "-1(p.18)" 잔재 인쇄, (c) 마커가 `^{…}$` 아님 → 프레임브레이크 게이트
    # 오검(0e3e6469 step1_c1). 순번은 계층적 → 하위분할 전체를 라벨로.
    (re.compile(r"(?<!\{)(본문)\s*(\d+(?:\s*[-–—.]\s*\d+)*)"), r"{\1\2}"),
    (re.compile(r"\b(\d+)\.\s*L\d+\s*[-–—.]?\s*p\.?\s*\d+\b"),
     r"{본문\1}"),
    # 교과서 L-한글라벨형 (W30-r15 — "6. L1-추가본문" → "{추가본문}"):
    # 페이지/본문번호 없이 한글 라벨이 직결된 헤더. 기존 어느 룰에도 안
    # 걸려 헤더 미정규화 → 추가본문 지문이 본문5 블록에 흡수 + 발문/프레임
    # 분리 누락 (사용자 지목 결함 1). 기존 룰 무변경 삽입 — L-p형은 위
    # 룰들이 먼저 소비하고, 이 룰은 'N. L<n>-<한글>' 전체 라인만 매치.
    (re.compile(r"\b(\d+)\.\s*L\d+\s*[-–—.]\s*([가-힣][가-힣0-9\s]{0,30}?)"
                r"\s*$"), r"{\2}"),
    (re.compile(r"\bL\d+\s*[-–—.]?\s*p\.?\s*\d+\b"), ""),
    (re.compile(r"\b\d+\.\s*p\d+\s*[-–—]?\s*서술형\s*Practice\b"),
     "{서술형 Practice}"),
    (re.compile(r"\b\d+\.\s*p\d+\s*[-–—]?\s*논술형\s*"
                r"Prac(?:tice|ice)\b"), "{논술형 Practice}"),
]
# v1 "Clean up residual text before {" (3회 반복)
_C1_RESID = [
    (re.compile(r"((?:^|,)\s*)[^{\r\n]*?(\{[^}]+\})"), r"\1\2"),
    (re.compile(r"-\s*(\{)"), r"\1"),
    (re.compile(r"(^|,)\s+(\{)"), r"\1\2"),
]
# v1 "Clean up header remnants" (최종)
# W49: 라벨의 하위분할 순번(본문2-1) 뒤 "(p.18)" 잔재도 제거 (\d+ → 계층 순번).
_C1_REMNANT = [
    # W71: 라벨 뒤 유형 표기 제거 ("{01}  [문장삽입]" → "{01}"). 유형을 헤더
    # 앞에 적는 원고("2. [문단배열] p82-no.03")는 _C1_RESID 가 앞부분을
    # 걷어내지만, 뒤에 적는 원고("3. p80-no.01  [문장배열]", 12강 최종본)는
    # 잔재가 남아 지문번호 자리에 인쇄되고 — 라벨이 블록마다 달라져
    # 지문별 슬롯 묶음(W70)까지 무력화된다.
    (re.compile(r"(\{[^}]+\})\s*\[[^\]]*\]\s*$"), r"\1"),
    (re.compile(r"(\{본문\d+(?:[-–—.]\d+)*\})\([^)]*\)"), r"\1"),
    (re.compile(r"(\{[A-Za-z][A-Za-z\s]+\})\([^)]*\)"), r"\1"),
]

# W71: 원고 헤더의 문항 유형 표기 — "[문단배열]" / "[문장배열]" / "[문장삽입]".
_RE_C1_KIND = re.compile(r"\[\s*(문단\s*배열|순서\s*배열|문장\s*배열|"
                         r"문장\s*삽입)\s*\]")
_RE_TAB = re.compile(r"\t")
_RE_LEAD3WS = re.compile(r"^\s{3,}")
# W69: 주어진 문장(BTM) 단락의 앞뒤 공백·개행 — docx 표 셀 추출 잔재.
_RE_C1_EDGE_BREAK = re.compile(
    "^[\\s\u2028\u2029]+|[\\s\u2028\u2029]+$")

_PROMPT_CIRC = "아래 주어진 문장이 들어갈 위치로 알맞은 곳을 고르시오."
_PROMPT_ORDER = "아래 주어진 문장 다음에 이어질 문장들의 적절한 순서를 쓰시오."
_ICON_ARROW = {"label": "화살표 답지", "pos": "start"}


def _slice_runs(runs, a, b):
    """runs에서 [a,b) 문자 구간만 잘라 반환 (오프셋 정합 유지)."""
    out = []
    off = 0
    for r in runs or []:
        t = r.get("t") or ""
        s, e = off, off + len(t)
        lo, hi = max(a, s), min(b, e)
        if lo < hi:
            out.append(dict(r, t=t[lo - s:hi - s]))
        off = e
    return out


def _sub_runs(rx, repl, text, runs):
    """re.sub 대응 — 텍스트와 runs를 동시에 치환 (밑줄 오프셋 보존).

    치환 삽입분은 비밑줄 run으로 들어간다 (v1 GREP changeTo와 동일:
    새 텍스트는 서식 없는 평문)."""
    matches = list(rx.finditer(text))
    if not matches:
        return text, runs
    out_t = []
    out_r = []
    last = 0
    for m in matches:
        out_t.append(text[last:m.start()])
        out_r.extend(_slice_runs(runs, last, m.start()))
        rep = m.expand(repl)
        if rep:
            out_t.append(rep)
            out_r.append({"t": rep, "ul": False})
        last = m.end()
    out_t.append(text[last:])
    out_r.extend(_slice_runs(runs, last, len(text)))
    return "".join(out_t), out_r


_RE_C1_SENT_NORM = re.compile(r"[\s\u2028\u2029]+")
_C1_SENT_TRANS = {ord("\u2019"): "'", ord("\u2018"): "'",
                  ord("\u201c"): '"', ord("\u201d"): '"',
                  ord("\u2013"): "-", ord("\u2014"): "-",
                  ord("\u2015"): "-", ord("\u2500"): "-"}


def _c1_norm_sent(text):
    """문장 대조용 정규화 — 공백 접기 + 따옴표/대시 이형 통일 + 소문자."""
    t = (text or "").translate(_C1_SENT_TRANS)
    return _RE_C1_SENT_NORM.sub(" ", t).strip().lower()


def _c1_true_empty(text):
    """v1 발문 삽입 walk의 isEmpty: \\r\\n 제거 후 빈 문자열 (공백은 비빈)."""
    return re.sub(r"[\r\n]", "", text or "") == ""


def _c1_remove_gap_blank(items, st_btm, st_btm_t):
    """v1: BTM(주어진 문장) → 빈 단락 → BTM_T 사이 빈 줄 1개 제거 (역순)."""
    i = len(items) - 2
    while i >= 1:
        if (items[i - 1]["s"] == st_btm and _is_blank(items[i]["t"])
                and items[i + 1]["s"] == st_btm_t):
            del items[i]
        i -= 1


# W44: step1_c1 헤더 **부분 인식** 보강 스위치 (False = W43 이전 동작).
PROMOTE_C1_MISSED_HDR = True
_RE_C1_ORDINAL = re.compile(r"^\s*(\d{1,3})\s*[.)]")


# W53 (배재2 워크북01 검수 실증 2026-08-12): 교과서 보충지문 코너명.
# C1 문장배열 헤더 "8. L1-Further Reading(p.26-27)"은 '본문N'이 없어 선두
# 순번 폴백으로 {8}이 라벨이 됐다. 같은 책의 어휘선택/빈칸어휘 섹션은 원고
# 대괄호 라벨이라 이미 [Further Reading 1]/[Further Reading 2] — 같은 책
# 안의 정상 구간이 컨벤션의 정답이다. 코너명 집합은 final 엔진의 교과서
# 보충지문 마커와 동일 계열(Further Reading / Read More / Read Culture).
_RE_C1_CORNER = re.compile(
    r"(further\s*reading|read\s*more|read\s*culture)", re.I)
_C1_CORNER_CANON = {"furtherreading": "Further Reading",
                    "readmore": "Read More",
                    "readculture": "Read Culture"}


def _c1_corner_name(text):
    """헤더 원문에서 교과서 보충지문 코너명 추출 (없으면 None)."""
    m = _RE_C1_CORNER.search(text or "")
    if not m:
        return None
    key = re.sub(r"\s+", "", m.group(1)).lower()
    return _C1_CORNER_CANON.get(key)


def _c1_corner_labels(items, orig_texts):
    """순번만 남은 코너명 지문 라벨을 코너명으로 교정 (W53 — 가산 전용).

    대상은 `{8}`처럼 **숫자 라벨**인 헤더 중 원문에 코너명이 있는 것뿐이다
    (본문N·이미 코너명인 라벨은 무접촉 → 모의고사 계열 숫자 라벨 회귀 없음).
    같은 코너명이 2개 이상이면 등장 순서로 1,2… 접미, 1개면 접미 없음
    (어휘선택 섹션 원고 라벨과 동일 규칙 — 1과 [Further Reading],
    2·3과 [Further Reading 1]/[Further Reading 2] 실측).
    """
    hits = []
    for i, it in enumerate(items):
        m = re.match(r"^\s*\{([^}]+)\}\s*$", it.get("t") or "")
        if not m or not re.match(r"^\d+$", m.group(1).strip()):
            continue
        name = _c1_corner_name(orig_texts[i] if i < len(orig_texts) else "")
        if name:
            hits.append((i, name))
    if not hits:
        return 0
    total = {}
    for _, name in hits:
        total[name] = total.get(name, 0) + 1
    seen = {}
    for i, name in hits:
        seen[name] = seen.get(name, 0) + 1
        label = name if total[name] == 1 else "%s %d" % (name, seen[name])
        new_t = "{" + label + "}"
        items[i]["t"] = new_t
        items[i]["runs"] = [{"t": new_t, "ul": False}]
    return len(hits)


def _c1_promote_missed_headers(items, orig_texts, warnings):
    """GREP 열거가 놓친 지문 헤더를 {라벨}로 승격 (가산 전용).

    items: build_step1_c1의 작업 리스트 (GREP 정규화 후, in-place 수정)
    orig_texts: GREP 이전 원문 (인덱스 일치)
    """
    n = len(items)
    known = [i for i in range(n) if _RE_C1_HEADER.match(items[i]["t"])]
    if not known:
        return
    try:
        det = detect_headers(list(orig_texts))
    except Exception:                                          # noqa: BLE001
        return
    cand = sorted(i for i in det.header_idx
                  if i < n and not _RE_C1_HEADER.match(items[i]["t"]))
    if not cand:
        return
    # 인식 헤더의 원문 순번 (없으면 승격 판단 불가 → 종료)
    ords = {}
    for i in known:
        m = _RE_C1_ORDINAL.match(orig_texts[i] if i < len(orig_texts) else "")
        if m:
            ords[i] = int(m.group(1))
    if not ords:
        return
    promoted = 0
    for i in cand:
        m = _RE_C1_ORDINAL.match(orig_texts[i])
        if not m:
            continue
        prev = max((k for k in ords if k < i), default=None)
        if prev is None or int(m.group(1)) != ords[prev] + 1:
            continue
        nxt = min((k for k in known if k > i), default=n)
        if not any(_RE_C1_CHOICE.match(items[j]["t"])
                   for j in range(i + 1, nxt)):
            continue
        mb = re.search(r"본문\s*(\d+(?:\s*[-–—.]\s*\d+)*)", orig_texts[i])
        if mb:
            label = "본문" + re.sub(r"\s+", "", mb.group(1))
        elif _LABEL_ABBREV:   # W63: 축약 라벨 원고만
            label = _header_label(orig_texts[i]) or m.group(1)
        else:
            label = m.group(1)
        new_t = "{" + label + "}"
        items[i]["t"] = new_t
        items[i]["runs"] = [{"t": new_t, "ul": False}]
        ords[i] = int(m.group(1))
        known = sorted(known + [i])
        promoted += 1
    if promoted:
        warnings.append("step1_c1: 구조 인식기로 미인식 헤더 %d개 승격 "
                        "(부분 인식 보강 — W44)" % promoted)


def _c1_order_labels(labels):
    """지문 라벨 표시 순서.

    원칙은 **원고 순서 보존**이다. 원고가 이미 지문번호 순이면(정상 형식)
    손대지 않는다 — job ea9c65b4(영어독해 8강)처럼 {01}…{05~06} 으로
    정렬돼 온 원고를 건드리면 그 자체가 회귀다. 12강처럼 문항이 유형
    순환이라 지문번호가 03·05·01… 로 흩어진 경우에만 재배치한다.

    재배치 순서는 같은 교재 다른 스텝(step1_a1/a2/b2 의 [12강 gateway] →
    [12강 1번] …)과 같게 비숫자 라벨(gateway)을 앞, 숫자를 오름차순으로.
    비숫자 라벨이 둘 이상이면 정렬 근거가 없으므로 원순서를 유지한다.
    """
    nums = []
    for lb in labels:
        m = re.search(r"\d+", lb)
        nums.append(int(m.group()) if m else None)
    if all(n is not None for n in nums):
        if nums == sorted(nums):
            return list(labels)                 # 이미 지문번호 순 — 보존
    if sum(1 for n in nums if n is None) > 1:
        return list(labels)                     # 코너명 라벨 다수 — 보존
    idx = {lb: i for i, lb in enumerate(labels)}
    return sorted(labels,
                  key=lambda lb: (0, 0, idx[lb])
                  if re.search(r"\d+", lb) is None
                  else (1, int(re.search(r"\d+", lb).group()), idx[lb]))


# W73: 원고가 문항 앞에 다는 유형 표기 발문 — "02  문단배열   주어진 문장
# 다음에 이어질 글의 순서를 쓰시오." / "01  문장배열 …" / "02  문장삽입 …".
_RE_C1_TYPE_PROMPT = re.compile(
    r"^\s*\d{1,2}\s+(?:문단\s*배열|문장\s*배열|문장\s*삽입|순서\s*배열)\s")
_RE_C1_TYPE_INSERT = re.compile(r"^\s*\d{1,2}\s+문장\s*삽입\s")
# W73: 원고 섹션 구분줄 — "WORKSHEET  |  문장배열 + 문장삽입". 하단 스타일을
# 쓰지만 하단 **본문**이 아니라 문항 묶음의 표제다.
_RE_C1_SECTION_DIV = re.compile(r"^\s*(?:WORKSHEET|워크시트)\s*[|｜]")


def _c1_is_bottom_body(it, st_btm, st_btm_t, st_hadan):
    """이 단락이 하단 프레임의 **본문**인가 (W73).

    st_btm("C1_문장 배열 하단")은 하단 본문뿐 아니라 유형 표기 발문·섹션
    구분줄에도 쓰인다. 그것까지 하단으로 세면 카드 블록이 '상·하단 섞임'으로
    판정돼 슬롯 배치가 통째로 꺼진다(능률(민) SL1 실증). 두 표제 형태만
    판정에서 뺀다 — 기존 하단 본문 판정은 그대로다."""
    s = it["s"]
    if s in (st_btm_t, st_hadan):
        return True
    if s != st_btm:
        return False
    t = it["t"]
    return not (_RE_C1_TYPE_PROMPT.match(t) or _RE_C1_SECTION_DIV.match(t))


def _c1_group_slot_units(items, st_c1, st_btm, st_btm_t, st_hadan, warnings):
    """지문 라벨로 블록을 묶어 상단(배열 카드)/하단(순서·삽입) 슬롯에 배치.

    W70 (job a3d13ab3 실증 — 사용자 지적 "문장배열 조판 완전 엉망").
    완제품 계약 (광문2 워크북02 수특라이트영독3강 p28~30, 수특라이트11강
    p25·p27 실측): **한 페이지 = 한 지문**이고
      상단 프레임 = 지문번호 + 문장배열 카드((A)~(Z) + 화살표 답란)
      하단 프레임 = 지문번호 **없이** 발문 + 주어진 문장 + 본문 박스
    이다. 원고가 지문별로 상단·하단을 연속 표기하면 예전의 '원고 순서대로
    프레임에 흘리기'가 우연히 맞았지만, 12강처럼 문항이 [문단배열]→
    [문장삽입]→[문장배열] 유형 순환이고 지문번호가 03·05·01…로 흩어진
    원고에서는 문단배열이 상단을 차지하고 배열 카드가 밀리며, 하단 블록의
    지문번호까지 그대로 인쇄된다(라벨이 달라 W51 흡수 규칙이 안 걸린다).

    반환 None = 이 형식이 아님 → 호출자가 기존 순서대로 경로를 쓴다.
    """
    hdr_idx = [i for i, it in enumerate(items)
               if _RE_C1_HEADER.match(it["t"])]
    if len(hdr_idx) < 2:
        return None
    bottom_styles = {st_btm, st_btm_t, st_hadan}
    pre = items[:hdr_idx[0]]
    bounds = hdr_idx + [len(items)]
    raw = [(items[bounds[b]], items[bounds[b] + 1:bounds[b + 1]])
           for b in range(len(bounds) - 1)]

    # W73 (능률(민) SL1 실증 — C1이 문항당 한 페이지를 먹고 하단이 계속
    # 비었다): 이 원고는 다음 문항의 **유형 표기 발문**("02  문단배열  주어진
    # 문장 다음에…")이 앞 블록 꼬리에 붙어 온다. 헤더로 블록을 자르면 카드
    # 블록이 하단 스타일 줄을 하나 물고 있게 되어 아래 '상·하단 섞임' 판정에
    # 걸리고, 슬롯 배치가 통째로 꺼진 채 원고 순서대로 흘러 지문 5개가
    # 39유닛/20쪽이 됐다. 꼬리의 유형 표기 줄은 **다음 블록의 것**이므로
    # 옮겨 준다 (표기 줄이 꼬리에 없는 기존 원고는 무영향).
    for b in range(len(raw) - 1):
        body = raw[b][1]
        j = len(body) - 1
        while j >= 0 and _is_blank(body[j]["t"]):
            j -= 1
        if j >= 0 and _RE_C1_TYPE_PROMPT.match(body[j]["t"]):
            raw[b] = (raw[b][0], body[:j])
            raw[b + 1] = (raw[b + 1][0], body[j:] + raw[b + 1][1])

    # 유형 표기 줄을 넘기고 나면 카드도 하단도 없는 '구분줄만' 블록이 남는다
    # ("WORKSHEET | 문장배열 + 문장삽입"). 그 자체로는 문항이 아니므로 다음
    # 블록의 머리에 붙인다 — 기존 경로가 쓰던 '라벨만 있는 빈 유닛 병합'과
    # 같은 계약. 마지막 블록이면 옮길 곳이 없으니 그대로 둔다.
    merged = []
    carry = []
    for b, (head, body) in enumerate(raw):
        body = carry + body
        carry = []
        if b < len(raw) - 1:
            has_card = any(it["s"] == st_c1 for it in body)
            has_btm = any(_c1_is_bottom_body(it, st_btm, st_btm_t, st_hadan)
                          for it in body)
            if not has_card and not has_btm:
                carry = body
                continue
        merged.append((head, body))
    if carry and merged:
        merged[-1] = (merged[-1][0], merged[-1][1] + carry)
    raw = merged
    if len(raw) < 2:
        return None

    blocks = []
    for head, body in raw:
        is_card = any(it["s"] == st_c1 for it in body)
        is_btm = any(_c1_is_bottom_body(it, st_btm, st_btm_t, st_hadan)
                     for it in body)
        if is_card and is_btm:
            return None          # 한 블록에 상·하단이 섞인 형식 — 기존 경로
        if not is_card and not is_btm:
            return None          # 유형 판정 불가 — 기존 경로
        # 하단 블록의 세부 유형 — 완제품(수특라이트11강 p25→p27) 순서는
        # 문단배열(순서 쓰시오) 다음 문장삽입(위치 고르시오)이다. 엔진이
        # 넣은 발문으로 판정한다 (본문 형태보다 안정적).
        sub = 0
        for it in body:
            if it["s"] == st_hadan and it["t"].strip() == _PROMPT_CIRC:
                sub = 1       # 문장삽입 — 문단배열 뒤에 온다
                break
        # W73: 원고 유형 표기가 남아 있으면 그것으로도 판정 (엔진 발문이
        # 아직 안 붙은 원고 — 표기 줄을 앞 블록에서 넘겨받은 경우).
        if not sub:
            for it in body:
                if _RE_C1_TYPE_INSERT.match(it["t"]):
                    sub = 1
                    break
        blocks.append({"label": re.sub(r"\s+", "", head["t"]),
                       "head": head, "body": body, "sub": sub,
                       "kind": "card" if is_card else "bottom"})
    labels = []
    groups = {}
    for blk in blocks:
        if blk["label"] not in groups:
            groups[blk["label"]] = {"card": [], "bottom": []}
            labels.append(blk["label"])
        groups[blk["label"]][blk["kind"]].append(blk)
    # 라벨이 지문마다 한 번씩만 나오는 원고(= 상·하단 짝 개념이 없음)나
    # 카드/하단 한쪽만 있는 원고는 이 배치의 대상이 아니다.
    if len(labels) == len(blocks):
        return None
    if not any(g["card"] for g in groups.values()):
        return None
    if not any(g["bottom"] for g in groups.values()):
        return None

    def _paras(its):
        out = []
        for it in its:
            para = _mk(it["t"], it["s"] if it["s"] is not None else "$BASIC",
                       it["runs"])
            if it.get("icon"):
                para["icon"] = it["icon"]
            out.append(para)
        return out

    ordered = _c1_order_labels(labels)
    if ordered != labels:
        warnings.append("step1_c1: 지문 %d개를 지문번호 순으로 재배치 "
                        "(원고는 유형 순환 순서 — %s → %s)"
                        % (len(ordered), labels[0], ordered[0]))
    units = []
    first = True
    for lb in ordered:
        g = groups[lb]
        cards = g["card"]
        # 하단이 둘 이상이면 문단배열 → 문장삽입 순 (완제품 실측 순서).
        btms = sorted(g["bottom"], key=lambda b: b["sub"])
        for i in range(max(len(cards), len(btms), 1)):
            head_it = (cards[i]["head"] if i < len(cards)
                       else (btms[i]["head"] if i < len(btms) else None))
            top = _paras([head_it]) if head_it is not None else []
            if i < len(cards):
                top += _paras(cards[i]["body"])
            if first and pre:
                top = _paras(pre) + top
            unit = {"paras": top}
            if not first:
                unit["page_break"] = True
            units.append(unit)
            first = False
            if i < len(btms):
                # 하단 프레임: 지문번호(헤더 단락)를 넣지 않는다 — 완제품
                # 실측에서 하단에는 지문번호가 없다.
                units.append({"paras": _paras(btms[i]["body"])})
    warnings.append("step1_c1: 지문별 상·하단 슬롯 배치 %d지문 / %d유닛 "
                    "(완제품 계약 — 상단=배열 카드, 하단=순서·삽입 문제)"
                    % (len(ordered), len(units)))
    return units


def build_step1_c1(step_data, workbook_type="모의고사", exclude_btm=False,
                   split_condition=True):
    # split_condition: v1 conditionIdxList 잔존 해석의 NEXT_FRAME 유닛 분리.
    # 세로 워크북(workbook_sero_v2)은 페이지당 프레임 2개(상단 보기+하단)라
    # 이 분리가 실물 v1 출력에 없고(사이클 페이지 오버플로우 유발) False로
    # 끈다. 가로(workbook_v2)는 기존 동작 유지(True) — 코퍼스 4케이스 미발동.
    st_c1 = _style("STEP1C1", "P")
    st_btm = _style("STEP1C1", "BTM")
    st_btm_t = _style("STEP1C1", "BTM_T")
    st_hadan = _style("STEP1C1", "Q@bottom")
    is_ebs = (workbook_type == "EBS")
    warnings = []

    # 0) 원본 → 작업 리스트 (s=None은 '어떤 스타일 패스도 안 건드림' 추적 —
    #    v1에서 startParagraph가 스타일 재적용에 안 지워지는 단락 판별용)
    items = [{"t": p.get("text") or "", "runs": p.get("runs") or [],
              "s": None}
             for p in step_data.get("paragraphs", []) or []]

    # 1) 공백만 있는 bracket 단락 제거: [   ] → 삭제
    items = [it for it in items if not _RE_C1_EMPTY_BRACKET.match(it["t"])]
    # C1의 발문·머리글·기입란은 **엔진/템플릿이 자기 계약으로 만든다**
    # (아래 발문 삽입 패스, 마스터 러닝헤드, 상·하단 슬롯). 원고에 적힌
    # 같은 부속물은 전부 중복이다.
    #
    # W68까지는 `^Q[.:]` 리터럴만 걷어냈는데, 원고마다 발문 표기가 달라
    # 그대로 통과했다 — 2026-08-24 능률(민) SL1 실증(사용자 지적):
    #   "02  문단배열   주어진 문장 다음에 이어질 글의 순서를 쓰시오."  (발문 중복)
    #   "WORKSHEET  |  문장배열 + 문장삽입"                          (원고 머리글)
    #   "정답 순서  ______________"                                  (원고 기입란)
    # 이 11개 페이지에 그대로 인쇄됐다. 그래서 리터럴이 아니라 구조로
    # 판정한다 (core/structure/manuscript_noise — 파이프 필드 막대 /
    # '…시오' 종결 지시문 / 밑줄만 남는 기입란). 문장 속 빈칸이나
    # 선지·지문은 구조가 달라 걸리지 않는다.
    from core.structure import manuscript_noise as _mn
    _c1_kinds = {}
    for it in items:
        k = _mn.classify(it["t"])
        if k or _c1_is_manu_prompt(it["t"]) \
                or _RE_C1_LESSON_TITLE.match(it["t"]):
            _c1_kinds[id(it)] = k or "prompt"
    _c1_drop = [it for it in items if id(it) in _c1_kinds]
    if _c1_drop:
        items = [it for it in items if id(it) not in _c1_kinds]
        _cnt = {}
        for it in _c1_drop:
            _k = _c1_kinds[id(it)]
            _cnt[_k] = _cnt.get(_k, 0) + 1
        warnings.append(
            "step1_c1: 원고 부속물 %d줄 제거 (엔진 발문/템플릿 머리글과 "
            "중복) — %s — 예: %s"
            % (len(_c1_drop),
               ", ".join("%s %d" % (k, v) for k, v in sorted(_cnt.items())),
               _c1_drop[0]["t"][:30]))
    # W50: 헤더 직전 섹션 타이틀 줄(Further Reading 류) 제거 — C1은 유닛
    # 분할을 det가 아니라 {라벨} GREP이 담당하므로, 흡수 줄만 여기서
    # 미리 걷어낸다 (de909e4d 실증: 타이틀 줄이 $BASIC으로 인쇄).
    try:
        _det_c1 = detect_headers([it["t"] for it in items],
                                 legacy=is_header_line)
        if _det_c1.absorbed_idx:
            items = [it for k, it in enumerate(items)
                     if not _det_c1.is_absorbed(k)]
    except Exception:                                          # noqa: BLE001
        pass
    # GREP 정규화 전 원문 (W44 부분 인식 보강의 순번·구조 판정 기준)
    orig_texts = [it["t"] for it in items]

    # W71: 헤더의 유형 표기("3. p80-no.01  [문장배열]")를 GREP 이 라벨을
    # 정규화하며 지우기 전에 기록해 둔다. 유형 표기가 있는 원고에서는
    # 문단배열(하단 슬롯)과 문장배열(상단 배열 카드)을 추측이 아니라
    # 원고가 명시한 대로 가를 수 있다.
    for it in items:
        m = _RE_C1_KIND.search(it["t"])
        if m:
            it["_kind"] = re.sub(r"\s+", "", m.group(1))

    # 2) 헤더 정규화 GREP 체인 + 레지듀얼 정리(3회)
    for it in items:
        t, r = it["t"], it["runs"]
        for rx, repl in _C1_GREPS:
            t, r = _sub_runs(rx, repl, t, r)
        for _ in range(3):
            for rx, repl in _C1_RESID:
                t, r = _sub_runs(rx, repl, t, r)
        it["t"], it["runs"] = t, r

    # 3) 프리앰블 제거 — 첫 {N} 헤더 앞 단락 삭제 ((A) 선지가 있으면 보류)
    first_hdr = next((i for i, it in enumerate(items)
                      if _RE_C1_HEADER.match(it["t"])), -1)
    # W31: GREP 열거가 하나도 못 잡으면 구조 우선 인식기로 폴백 — 검출된
    # 헤더를 {라벨}로 정규화해 이후 패스(_RE_C1_HEADER 기준)가 그대로 동작.
    if first_hdr < 0 and USE_STRUCT_HEADER_DETECT:
        det = detect_headers([it["t"] for it in items])
        if det.silent():
            raise HeaderSilenceError("step1_c1", det)
        if det.header_idx:
            ordinal = 0
            for i in sorted(det.header_idx):
                ordinal += 1
                t = items[i]["t"]
                m = re.search(r"본문\s*(\d+)", t)
                if m:
                    label = "본문" + m.group(1)
                elif _LABEL_ABBREV:
                    # W63: 축약 라벨 원고만 — 다른 스텝과 동일 규칙
                    label = _header_label(t) or str(ordinal)
                else:
                    m = re.match(r"^\s*(\d{1,3})\s*[.)]", t)
                    label = m.group(1) if m else str(ordinal)
                new_t = "{" + label + "}"
                items[i]["t"] = new_t
                items[i]["runs"] = [{"t": new_t, "ul": False}]
            first_hdr = next((i for i, it in enumerate(items)
                              if _RE_C1_HEADER.match(it["t"])), -1)
            warnings.append("step1_c1: 구조 인식기로 헤더 %d개 검출 "
                            "(정규식 열거 미인식 형식)"
                            % len(det.header_idx))
    # W44 (역학습 실증 — 완성본 대조): **부분 인식** 보강. GREP 열거가 일부
    # 헤더만 잡으면(예: "N. L4-본문N(p.94)"는 잡히고 "7. L4-Read More(p.109)"
    # 는 못 잡음) 위 폴백이 발동하지 않아, 못 잡은 블록의 (A)~(J) 배열
    # 항목이 통째로 스타일 없이($BASIC) 인쇄된다 (완성본 ac9fc469
    # 영어Ⅰ_미래엔(김)_4과: 10단락이 실제로는 C1_문장 배열 스타일).
    # 승격 조건(가산만 — 기존 인식분은 절대 건드리지 않음):
    #   (a) 구조 인식기가 헤더로 본 라인이고,
    #   (b) 원문 선두 순번이 직전 인식 헤더의 순번 +1로 이어지고,
    #   (c) 그 블록에 (A)~(Z) 배열 선지가 실제로 뒤따른다.
    # 세 조건이 동시에 성립할 때만 {라벨}로 정규화한다.
    if first_hdr >= 0 and USE_STRUCT_HEADER_DETECT and PROMOTE_C1_MISSED_HDR:
        _c1_promote_missed_headers(items, orig_texts, warnings)
        first_hdr = next((i for i, it in enumerate(items)
                          if _RE_C1_HEADER.match(it["t"])), first_hdr)
    # W53: 코너명 지문 라벨 교정 ({8} → {Further Reading 1}). orig_texts와
    # 인덱스가 어긋나기 전(프리앰블 절단 앞)에 수행한다.
    _n_corner = _c1_corner_labels(items, orig_texts)
    if _n_corner:
        warnings.append("step1_c1: 코너명 지문 라벨 %d개 교정 "
                        "(순번 → Further Reading 류)" % _n_corner)
    if first_hdr > 0:
        if not any(_RE_C1_CHOICE.match(items[i]["t"])
                   for i in range(first_hdr)):
            items = items[first_hdr:]
    elif first_hdr < 0:
        warnings.append("step1_c1: {N} 지문 헤더 미인식 — 프레임 분리 없이 "
                        "단일 유닛 배치")

    n = len(items)
    hdr_idx = [i for i, it in enumerate(items)
               if _RE_C1_HEADER.match(it["t"])]

    # 3b) 조건(주어진 문장) 후보 — v1 conditionIdxList와 동일 시퀀스.
    #     v1에선 이 startParagraph가 이후 스타일 적용으로 지워져(2026 회귀)
    #     '어떤 스타일도 안 받은 단락'만 실효 → _cond 플래그로 추적.
    hdr_ends = hdr_idx + [n]
    for b in range(len(hdr_ends) - 1):
        saw_choice = False
        for i in range(hdr_ends[b] + 1, hdr_ends[b + 1]):
            t = items[i]["t"]
            trim = re.sub("^[\\s　]+|[\\s　]+$", "", t)
            if not trim:
                continue
            if _RE_C1_CHOICE.match(t):
                saw_choice = True
                continue
            if (saw_choice and re.match(r"^[A-Za-z]", trim)
                    and not re.search("[가-힣]", trim)):
                items[i]["_cond"] = True
                break

    # 4a) {…} 헤더 + [N bracket → [기본 단락]
    for it in items:
        if _RE_C1_NUM_BRACKET.match(it["t"]) or _RE_C1_HEADER.match(it["t"]):
            it["s"] = "$BASIC"

    # 4b) 모든 {header} 다음 첫 비빈 단락 → C1_BTM (EBS 등 본문 별도 줄 원고)
    for h in hdr_idx:
        j = h + 1
        while j < n and _is_blank(items[j]["t"]):
            j += 1
        if j < n:
            items[j]["s"] = st_btm

    # 4c) (A)~(Z) 선지 → C1_문장 배열 (3+공백 단락에서 블록 종료)
    in_block = False
    for i, it in enumerate(items):
        if i > 0 and _RE_C1_HEADER.match(items[i - 1]["t"]):
            in_block = True
        if _RE_3GAPS.search(it["t"]):
            in_block = False
        if in_block and _RE_C1_CHOICE.match(it["t"]):
            it["s"] = st_c1

    # 4d) 3+공백 단락 → C1_BTM, BTM 단락의 탭 + 선행 공백(3+) 제거
    # W69 (job a3d13ab3 수특라이트 12강 실증 — 사용자 지적 "문장배열 조판
    # 잘못됨"): 이 패스의 탭 제거가 4e의 판정 근거(_RE_3GAPS)를 파괴한다.
    # docx 표 셀에서 온 주어진 문장은 "\n\t*8 문장 \n\t*7" 형태라 탭을
    # 지우면 개행 하나만 남아 3연속 공백이 사라진다 → 4e 미발동 →
    # [문단배열] 유형의 (A)(B)(C)가 하단 지문 스타일을 못 받고 $BASIC으로
    # 인쇄되고, 6) 발문 삽입(_PROMPT_ORDER)과 답란도 통째로 누락됐다.
    # 제거 **전에** 플래그로 기록해 4e가 그것을 보게 한다 (판정 집합은
    # 기존의 상위집합 — 제거 후에도 3GAPS가 남던 케이스는 그대로 통과).
    for it in items:
        if _RE_3GAPS.search(it["t"]):
            it["s"] = st_btm
            it["_gap3"] = True
    for it in items:
        if it["s"] == st_btm:
            t, r = _sub_runs(_RE_TAB, "", it["t"], it["runs"])
            t, r = _sub_runs(_RE_LEAD3WS, "", t, r)
            # W69: 표 셀 유래 앞뒤 개행 제거. 남겨두면 박스 안에서 강제
            # 개행이 되어 한 줄짜리 문장이 양쪽정렬로 늘어나 글자 사이가
            # 벌어진 채 인쇄된다 (a3d13ab3 p33/p35 실증).
            t, r = _sub_runs(_RE_C1_EDGE_BREAK, "", t, r)
            it["t"], it["runs"] = t, r

    # 4d-2) W74 (올포기출 13강 실증 — 사용자 지적 "문장배열 15번 하단
    # 프레임 주어진 문장이 별도로 조판되고 문제가 다음 페이지로 넘어감"):
    # 이 원고는 지문 15개는 주어진 문장 앞에 3연속 공백이 있는데 **한
    # 지문만 없다**(원고 사고). 그러면 4d가 BTM을 못 잡고, 그 줄은 3b의
    # 조건(_cond) 단락으로 남아 **혼자 한 프레임**을 차지한다 (하단 발문
    # +본문은 다음 페이지로 밀림).
    # 공백 표기에 기대지 않는 구조 근거를 쓴다 — 주어진 문장은 배열
    # 카드((A)~(Z)) 중 하나와 **같은 문장**이다. 카드 뒤에 BTM이 하나도
    # 없는 블록에서만, 카드와 문장이 일치하는 줄을 BTM으로 승격한다
    # (기존 원고는 이미 BTM이 잡혀 있어 무발동 — 회귀 0).
    _hdr2 = [i for i, it in enumerate(items) if _RE_C1_HEADER.match(it["t"])]
    _ends2 = _hdr2 + [len(items)]
    _rescued = 0
    for _b in range(len(_ends2) - 1):
        _b0, _b1 = _ends2[_b], _ends2[_b + 1]
        _cards = [i for i in range(_b0, _b1) if items[i]["s"] == st_c1]
        if not _cards:
            continue
        if any(items[i]["s"] == st_btm for i in range(_cards[-1] + 1, _b1)):
            continue
        _ctxt = set()
        for i in _cards:
            _ctxt.add(_c1_norm_sent(_RE_C1_CHOICE.sub("", items[i]["t"], 1)))
        _ctxt.discard("")
        for i in range(_cards[-1] + 1, _b1):
            it = items[i]
            if _is_blank(it["t"]):
                continue
            if _RE_C1_CIRCLED_WIDE.search(it["t"]):
                break               # 하단 본문이 시작됐다
            if it["s"] is not None:
                continue
            if _c1_norm_sent(it["t"]) in _ctxt:
                it["s"] = st_btm
                _rescued += 1
                break
    if _rescued:
        warnings.append("step1_c1: 주어진 문장 %d개를 카드 대조로 복원 "
                        "(원고에 3연속 공백 표기 없음)" % _rescued)

    # 4e) BTM(3+공백 잔존) 뒤 (A|B|C) 시퀀스 → C1_하단 지문
    # W71: 판정 기준을 "BTM 단락 뒤에 (A)(B)(C) 가 온다"로 넓힌다. 주어진
    # 문장을 표 셀로 넣는 원고는 3연속 공백으로 BTM 이 잡히지만, 평문
    # 한 줄로 적는 원고(12강 최종본)는 4b(헤더 다음 첫 비빈 단락 → BTM)로만
    # 잡혀 여기서 걸러졌다 → 문단배열의 (A)(B)(C)가 상단 배열 카드 스타일로
    # 인쇄되고 발문도 붙지 않았다. 문장배열 블록은 4c 가 (A)를 이미
    # 카드 스타일로 덮어써 이 루프의 시작 조건(s == st_btm)에 걸리지 않는다.
    for i in range(n):
        if items[i]["s"] != st_btm:
            continue
        j = i + 1
        while j < n and _is_blank(items[j]["t"]):
            j += 1
        if j >= n or not _RE_C1_ABC.match(items[j]["t"]):
            continue
        if not (items[i].get("_gap3") or _RE_3GAPS.search(items[i]["t"])):
            # W71: 표 셀 유래(3연속 공백)가 아닌 **평문** 주어진 문장은,
            # 원고가 헤더에 '문단배열'이라 표기한 블록에서만 하단으로 본다.
            # 표기가 없는 원고(수능특강 29강·Test2 워크북: 헤더 → 지문 첫
            # 문장 → (A)~(H))에서는 문단배열과 상단 배열 카드를 가를 근거가
            # 없으므로 종전 동작(카드)을 유지한다 — 추측으로 바꾸면 이미
            # 납품된 교재가 통째로 다른 모양이 된다.
            h = i
            while h >= 0 and not _RE_C1_HEADER.match(items[h]["t"]):
                h -= 1
            kind = items[h].get("_kind") if h >= 0 else None
            if kind not in ("문단배열", "순서배열"):
                continue
        k = j
        while k < n:
            t = items[k]["t"]
            if "{" in t or not _RE_C1_ABC.match(t):
                break
            items[k]["s"] = st_btm_t
            k += 1

    # 4f) 원문자 포함 단락 → C1_하단 지문 (v1 grepFind — 스토리 전역)
    for it in items:
        if _RE_C1_CIRCLED_WIDE.search(it["t"]):
            it["s"] = st_btm_t

    # 4g) BTM → 빈 단락 → BTM_T 사이 빈 줄 1개 제거
    _c1_remove_gap_blank(items, st_btm, st_btm_t)
    n = len(items)

    # 4h) 교과서 분기: 《제목》/평문 한 줄 하단 구조 식별
    if workbook_type == "교과서":
        hdr_idx = [i for i, it in enumerate(items)
                   if _RE_C1_HEADER.match(it["t"])]
        hdr_ends = hdr_idx + [n]
        for b in range(len(hdr_ends) - 1):
            b_start, b_end = hdr_ends[b], hdr_ends[b + 1]
            last_choice = -1
            for i in range(b_start + 1, b_end):
                if _RE_C1_CHOICE.match(items[i]["t"]):
                    last_choice = i
            if last_choice < 0:
                continue
            j = last_choice + 1
            while j < b_end and _is_blank(items[j]["t"]):
                j += 1
            if j >= b_end:
                continue
            btm_i = j
            j = btm_i + 1
            while j < b_end and _is_blank(items[j]["t"]):
                j += 1
            if j >= b_end:
                continue
            nxt = items[j]["t"]
            if (not _RE_C1_CHOICE.match(nxt)
                    and not re.search("[①-⑳]", nxt)):
                continue
            if items[btm_i]["s"] == st_btm:
                continue
            items[btm_i]["s"] = st_btm
            k = j
            while k < b_end:
                t = items[k]["t"]
                if _RE_C1_HEADER.match(t):
                    break
                if not _is_blank(t):
                    items[k]["s"] = st_btm_t
                k += 1
        _c1_remove_gap_blank(items, st_btm, st_btm_t)
        n = len(items)

    # 5) 화살표 답지 아이콘 — C1 연속 블록 끝 뒤 (v1 STEP1C1_New 방식)
    out = []
    i = 0
    while i < n:
        it = items[i]
        out.append(it)
        is_run_end = (it["s"] == st_c1
                      and (i + 1 >= n or items[i + 1]["s"] != st_c1))
        if is_run_end:
            if is_ebs and i + 1 < n and _is_blank(items[i + 1]["t"]):
                # EBS: 기존 빈 단락 재사용 (frame break 밀림 방지)
                nxt = items[i + 1]
                nxt["s"] = "$BASIC"
                nxt["icon"] = dict(_ICON_ARROW)
                out.append(nxt)
                i += 2
                continue
            if not is_ebs:
                # 동아박/교과서/모의고사: \r\r — 빈 단락 2개, 두 번째에 화살표
                out.append({"t": "", "runs": [], "s": "$BASIC"})
            arrow = {"t": "", "runs": [], "s": "$BASIC",
                     "icon": dict(_ICON_ARROW)}
            out.append(arrow)
        i += 1
    items = out
    n = len(items)

    # 6) 발문 삽입 — C1_하단 지문 연속 구간 첫 단락 앞 (하단 제외 시 생략)
    if not exclude_btm:
        starts = [i for i in range(n)
                  if items[i]["s"] == st_btm_t
                  and (i == 0 or items[i - 1]["s"] != st_btm_t)]
        for i in reversed(starts):
            bt = items[i]["t"]
            if _RE_C1_CIRCLED_PROMPT.search(bt):
                prompt = _PROMPT_CIRC
            elif _RE_C1_CHOICE.match(bt):
                prompt = _PROMPT_ORDER
            else:
                continue
            ins = i
            while ins > 0:
                above = items[ins - 1]
                # v1 isEmpty: 앵커(￼) 포함 단락은 비빈 — 아이콘 단락에서 멈춤
                if above["s"] == st_btm or (
                        _c1_true_empty(above["t"])
                        and not above.get("icon")):
                    ins -= 1
                    continue
                break
            p = {"t": prompt, "runs": [], "s": st_hadan,
                 "icon": dict(_ICON_STEP1_Q)}
            items.insert(ins, p)
            # W21 r11 D4: 발문과 주어진 문장(BTM) 사이의 원고 잔여 빈 단락
            # 제거 — 걸어 올라오며 건넌 빈 단락이 발문 아래 남아 '하단 문제
            # 발문 ↔ 주어진 문장' 사이 불필요한 빈 줄로 인쇄됐다 (실사용
            # 0e3108fd 실증). v1 실물(워크북03(외부지문) 스토리 26)은 발문
            # 바로 다음이 BTM — 빈 단락 없음. 아이콘 단락은 보존.
            k = ins + 1
            while (k < len(items) and _c1_true_empty(items[k]["t"])
                   and not items[k].get("icon")):
                del items[k]
        n = len(items)

    # 7) 안전망: '{' 포함 단락 → [기본 단락] (v1 Final safety)
    for it in items:
        if "{" in it["t"]:
            it["s"] = "$BASIC"

    # 8) 헤더 잔재물 정리
    for it in items:
        t, r = it["t"], it["runs"]
        for rx, repl in _C1_REMNANT:
            t, r = _sub_runs(rx, repl, t, r)
        it["t"], it["runs"] = t, r

    # 9) 하단만 제외: BTM/BTM_T/발문 단락 삭제 (상단 유지)
    if exclude_btm:
        items = [it for it in items
                 if it["s"] not in (st_btm, st_btm_t, st_hadan)]
        n = len(items)

    # 10a) W70: 완제품 계약(한 페이지 = 한 지문, 상단 배열 카드 / 하단
    #      지문번호 없는 순서·삽입 문제)에 맞는 지문별 슬롯 배치. 이 형식이
    #      아니면 None 을 돌려주고 아래 기존 경로로 떨어진다.
    _slot = _c1_group_slot_units(items, st_c1, st_btm, st_btm_t, st_hadan,
                                 warnings)
    if _slot is not None:
        return {"units": _slot, "warnings": warnings}

    # 10) 유닛 분할 — v1 "FRAME BREAK 재적용"의 실효 동작:
    #     헤더(2번째+) = NEXT_PAGE (EBS는 NEXT_FRAME),
    #     블록 내 첫 하단 스타일 단락 = NEXT_FRAME,
    #     스타일 패스가 안 건드린 조건 단락 = NEXT_FRAME (v1 startParagraph 잔존)
    bottom_styles = {st_btm, st_btm_t, st_hadan}
    units = []
    cur = []
    cur_page_break = False

    def _flush():
        if cur:
            unit = {"paras": list(cur)}
            if cur_page_break:
                unit["page_break"] = True
            units.append(unit)

    seen_header = False
    block_bottom_done = True
    prev_hdr_label = None
    for it in items:
        is_hdr = bool(_RE_C1_HEADER.match(it["t"]))
        if is_hdr:
            label = re.sub(r"\s+", "", it["t"])
            # W51 (job 0645d4a7 수특라이트 실증): 원고가 같은 지문 헤더를
            # 상단(카드)·하단(주어진 문장+지문) 블록에 각각 반복 표기하는
            # 형식 — 두 번째 동일 라벨 헤더를 새 지문(NEXT_PAGE)으로 처리해
            # 상·하단이 서로 다른 페이지로 찢어졌다. 직전 헤더와 라벨이
            # 같으면 같은 지문의 섹션 재표기 — 유닛 경계는 하단 스타일
            # 단락(NEXT_FRAME)이 만들므로 헤더 라인은 흡수(미출력)한다.
            if seen_header and label == prev_hdr_label:
                _flush()
                cur = []
                cur_page_break = False
                block_bottom_done = False
                continue
            prev_hdr_label = label
            _flush()
            cur = []
            cur_page_break = seen_header and not is_ebs
            seen_header = True
            block_bottom_done = False
        elif (not block_bottom_done and it["s"] in bottom_styles):
            _flush()
            cur = []
            cur_page_break = False
            block_bottom_done = True
        elif split_condition and it.get("_cond") and it["s"] is None:
            _flush()
            cur = []
            cur_page_break = False
        para = _mk(it["t"], it["s"] if it["s"] is not None else "$BASIC",
                   it["runs"])
        if it.get("icon"):
            para["icon"] = it["icon"]
        cur.append(para)
    _flush()

    # W68 (11강 실증 — 사용자 지적 "왜 여기가 말썽이야"): 지문번호만 있고
    # 내용이 없는 유닛이 프레임을 한 칸 차지해, 상단(배열)/하단(문장삽입)
    # 짝이 어긋나고 페이지 절반이 비었다. 원인은 원고가 같은 지문을 여러
    # 문항에 재사용하는 형식(1.p74-no.01 … 4.p74-no.01)이라, 지문번호
    # 헤더 바로 뒤에 하단 스타일 단락이 오면 헤더 직후에 또 프레임을
    # 끊기 때문. 라벨만 남은 유닛은 **다음 유닛의 머리로 병합**한다
    # (프레임 시작 동작은 다음 유닛 것을 따른다 — 새 페이지로 밀지 않음).
    if len(units) > 1:
        merged, i, orphan = [], 0, 0
        while i < len(units):
            u = units[i]
            body = [p for p in u["paras"] if (p.get("t") or "").strip()]
            if (i + 1 < len(units) and len(body) == 1
                    and _RE_C1_HEADER.match(body[0].get("t") or "")):
                nxt = units[i + 1]
                nxt["paras"] = list(u["paras"]) + list(nxt["paras"])
                orphan += 1
                i += 1
                continue
            merged.append(u)
            i += 1
        if orphan:
            units = merged
            warnings.append(
                "step1_c1: 라벨만 있는 빈 유닛 %d개를 다음 블록에 병합 "
                "(상·하단 프레임 짝 맞춤)" % orphan)
    return {"units": units, "warnings": warnings}


# ── 스텝 빌더 레지스트리 (단계 전환: 지원 스텝을 여기서 늘려간다) ────────────

STEP_BUILDERS = {
    "step3": build_step3,
    "step1_a1": build_step1_a1,
    "step1_a1_2": build_step1_a1,   # v1과 동일: 같은 처리, 다른 스토리
    "step1_a2": build_step1_a2,
    "step1_b1": build_step1_b1,
    "step1_b2": build_step1_b2,
    "step1_c2": build_step1_c2,
    "step2_a1": build_step2_a1,
    "step2_a1_btm": build_step2_a1_btm,
    "step2_b1": build_step2_b1,
    "step2_c1": build_step2_c1,
    "step2_c2": build_step2_c2,
    "step1_c1": build_step1_c1,
}

# 원고 유형(EBS/교과서/모의고사) 분기가 필요한 빌더 — v1은 settings의
# workbook_type으로 분기 (workbook 엔진은 미전달 = "" → 非EBS 처리).
_CTX_BUILDERS = {"step1_c1", "step2_c2"}


# ── 지문번호 라벨 추출 (W11 — 독립 번호 프레임 갱신 op + 검수 게이트용) ──────
# 헤더 "1. p1-no.3과 추가지문" → "3과 추가지문", "1. p2-no.20" → "20".
# 페이지 번호 뒤 (?!\d): 코너명형 헤더 "1. p80-수능 Analysis"에서 p80이
# p8+라벨"0"으로 쪼개져 엉뚱한 라벨이 나오던 백트래킹 차단 (W12 실증 —
# 지문번호 프레임이 0/6/8로 갱신됨). 코너명형은 라벨 없음 → 다음 스텝/
# bracket 폴백([분석N]/[N])이 담당.
_RE_LABEL_HEADER = re.compile(
    r"^\s*\d+\s*[.)]\s*p\.?\s*\d+(?!\d)\s*[-–—.]?\s*(?:no\.\s*)?"
    r"(\d+(?:\s*~\s*\d+)?(?:\s*[가-힣][가-힣0-9\s]*[가-힣0-9])?)",
    re.I)
# 외부지문 무-p형 헤더 "1. no.1" → no-번호 (W21 r11 — p-형과 동일 규칙)
_RE_LABEL_HEADER_NOP = re.compile(
    r"^\s*\d+\s*[.)]\s*no\.\s*(\d+(?:\s*~\s*\d+)?)\s*$", re.I)
# W25 — 번호 없는 코너명형 헤더 ("1. p8-수능 대비 ANALYSIS" /
# "1. p80-수능 Analysis"). extract_tail이 "분석"/"분석N"을 내는 두 꼴과
# 같은 범위로 좁혀 둔다 — 라벨 판정을 더 넓히면 채택 스텝이 바뀐다.
# W75: 코너명형 헤더 일반 — "N. pN-<번호 아닌 꼬리>" (Gateway/Further
# Reading/수능 Analysis…). no.형 번호 헤더는 위 _RE_LABEL_HEADER 담당.
_RE_LABEL_CORNER = re.compile(
    r"^\s*\d+\s*[.)]\s*p\.?\s*\d+(?!\d)\s*[-–—.]?\s*"
    r"(?!\s*(?:no\.?\s*)?\d)\S", re.I)
_RE_CORNER_ANALYSIS = re.compile(
    r"^\s*\d+\s*[.)]\s*p\.?\s*\d+\s*[-–—.]?\s*수능\s*(?:대비\s*)?"
    r"analysis\s*(?:\([^)]*\))?\s*$", re.I)
# bracket 지문번호 "[3과 추가지문]" / "[20]" → 내용부
_RE_LABEL_BRACKET = re.compile(r"^\s*\[([^\]]+)\]\s*$")

# 라벨 소스 우선순위: 헤더 기반 스텝(독립 번호 프레임 섹션과 동일 원고 계열)
_LABEL_STEPS = ("step1_c2", "step2_c1", "step2_b1", "step2_a1", "step1_a1")


def passage_labels(steps):
    """원고 지문번호 라벨을 순서대로 추출 (중복 제거, 첫 유효 스텝 채택).

    독립 텍스트 프레임 지문번호 갱신 op(passage_numbers)와 검수 게이트의
    '원고 지문번호' 기준. 헤더 스텝이 없으면 step1_a1의 bracket 단락 폴백.
    """
    for key in _LABEL_STEPS:
        data = steps.get(key) or {}
        labels = []
        corner = []
        for p in data.get("paragraphs", []) or []:
            text = _norm_header(p.get("text") or "")
            m = _RE_LABEL_HEADER.match(text)
            if not m:
                m = _RE_LABEL_HEADER_NOP.match(text)
            if not m and key == "step1_a1":
                m = _RE_LABEL_BRACKET.match(text)
            if m:
                label = re.sub(r"\s+", " ", m.group(1)).strip()
                if label and label not in labels:
                    labels.append(label)
                continue
            # W25 — 번호 없는 코너명형 헤더("1. p8-수능 대비 ANALYSIS")는
            # 위 정규식이 전부 놓쳐 **그 지문 몫의 라벨이 통째로 빠진다**.
            # 한 스텝에 표기가 섞이면(코너명 1 + no.형 3) 라벨이 지문보다
            # 적어져, 남는 번호 프레임에 템플릿 잔재가 그대로 인쇄된다
            # (올림포스 독해기본2 실측: 지문 4개 / 라벨 3개 — 전 강 공통).
            # 라벨 문구는 step2_a1 헤더 변환과 같은 규칙(extract_tail)을 써
            # "분석"으로 맞춘다 — 어법 선택 상단이 이미 그렇게 찍고 있다.
            # 채택 스텝과 기존 라벨 문자열은 건드리지 않는다: 코너명 라벨을
            # **원래 자리에 끼워 넣기만** 한다 (라벨 판정을 넓히면 채택
            # 스텝 자체가 바뀌어 다른 교재의 번호 표기가 통째로 달라진다 —
            # 코퍼스 실측으로 확인된 회귀).
            # W75 (수특라이트 13강 실증 — 사용자 지적 "gateway가 첫번째인데
            # 하나도 안 맞아"): 코너명 헤더를 'ANALYSIS' 한 종류로 열거하던
            # 것을 구조로 넓힌다 — 선행 순번 + 페이지 마커 뒤 꼬리가 번호가
            # **아닌** 헤더는 전부 코너명형이다(Gateway/Further Reading/…).
            # 라벨이 하나라도 빠지면 그 뒤 지문의 번호 프레임이 통째로 한
            # 칸씩 밀린다. 라벨 문구는 다른 스텝과 같은 규칙(extract_tail),
            # 꼬리 주석("(정답 1개)")은 라벨이 아니므로 벗긴다.
            if _RE_CORNER_ANALYSIS.match(text) or _RE_LABEL_CORNER.match(text):
                lab = re.sub(r"\s+", " ", extract_tail(text) or "").strip()
                lab = re.sub(r"(?:\s*\([^()]*\))+\s*$", "", lab).strip()
                if lab:
                    corner.append((len(labels), lab))
        if labels:
            for off, (pos, lab) in enumerate(corner):
                if lab not in labels:
                    labels.insert(pos + off, lab)
            return labels
    # W59 (비상(황) 실증): 형식 열거가 전부 실패하면 구조 인식기 폴백 —
    # 이 원고의 라벨은 숫자가 아니라 텍스트다("1. p1-Main Reading 1").
    # 라벨 = 헤더 라인에서 선행 순번("1.")과 페이지 마커("p1-")를 벗긴
    # 나머지. 라벨이 비면 passage_numbers가 빈 배열이 되어 템플릿 잔재
    # 번호(20,21,…)가 그대로 인쇄된다 ([지문번호] critical의 뿌리).
    for key in _LABEL_STEPS:
        data = steps.get(key) or {}
        texts = [(p.get("text") or "")
                 for p in data.get("paragraphs", []) or []]
        if not texts:
            continue
        try:
            det = detect_headers(texts, legacy=is_header_line)
        except Exception:                                      # noqa: BLE001
            continue
        labels = []
        for i in sorted(det.header_idx):
            t = _norm_header(texts[i])
            t = re.sub(r"^\s*\d{1,3}\s*[.)]\s*", "", t)         # 선행 순번
            t = re.sub(r"^p\.?\s*\d+\s*[-–—.]?\s*", "", t, flags=re.I)
            t = re.sub(r"^no\.?\s*", "", t, flags=re.I)
            t = re.sub(r"\s+", " ", t).strip(" -–—")
            # W74 (올포기출 13강 실증 — 사용자 지적 "지문번호 프레임에
            # 지문번호가 들어가야 되는데 강만 들어가있음"): 이 원고의 헤더는
            # "1. 13강 지문1 (2025년 3월 고1 31번)" 이라 라벨이 통째로 길고,
            # 좁은 번호 프레임에서 JSX 줄임말 규칙(한글 다단어 → 첫 단어)이
            # "13강"만 남겼다. 번호 프레임에 들어갈 건 지문번호다 —
            # 꼬리 괄호(출처)와 강 접두를 벗겨 "지문N"이 남으면 두 자리
            # 번호로 정규화한다 (완제품 관행 01,02,…). 다른 형태의 라벨
            # ("Main Reading 1", "3과 추가지문")은 그대로 둔다.
            _t2 = re.sub(r"(?:\s*\([^()]*\))+\s*$", "", t).strip()
            _t2 = re.sub(r"^\d{1,2}\s*강\s*", "", _t2).strip()
            _m2 = re.match(r"^지문\s*(\d{1,3})\s*번?$", _t2)
            if _m2:
                t = "%02d" % int(_m2.group(1))
            if t and t not in labels:
                labels.append(t)
        if labels:
            return labels
    return []


def _label_key(text):
    """라벨 대조 키 — 번호가 있으면 번호(0패딩 제거), 없으면 글자 그대로.

    같은 지문을 스텝마다 다르게 적는다: 'N045' / '[실전예제 045]' / '045'.
    번호가 그 지문의 정체이므로 번호를 키로 삼아 표기를 하나로 모은다.
    """
    t = re.sub(r"\s+", " ", (text or "")).strip()
    m = re.search(r"(\d{1,4})\s*(?:~\s*\d{1,4})?\s*$", t)
    if m:
        return str(int(m.group(1)))
    return t


def _step_header_labels(data):
    """한 스텝의 지문 헤더 → 라벨 순열 (헤더에서 순번·페이지 마커를 벗김)."""
    texts = [(p.get("text") or "") for p in (data or {}).get("paragraphs")
             or []]
    if not texts:
        return []
    try:
        det = detect_headers(texts, legacy=is_header_line)
    except Exception:                                          # noqa: BLE001
        return []
    out = []
    for i in sorted(det.header_idx):
        t = _norm_header(texts[i])
        t = re.sub(r"^\s*\d{1,3}\s*[.)]\s*", "", t)
        t = re.sub(r"^p\.?\s*\d+\s*[-–—.]?\s*", "", t, flags=re.I)
        t = re.sub(r"^no\.?\s*", "", t, flags=re.I)
        t = re.sub(r"(?:\s*\([^()]*\))+\s*$", "", t)
        t = re.sub(r"\s+", " ", t).strip(" -–—")
        if t:
            out.append(t)
    return out


def passage_labels_by_step(steps, frame_steps):
    """번호 프레임 스텝별 라벨 (W84).

    스텝마다 지문 구성이 다를 수 있다 — 수능만만 실증: 스텝1은 실전예제
    4지문뿐인데 스텝2(어법 O/X·빈칸 어법)는 **본문 2 + 실전예제 4** 라
    한 벌의 공용 라벨을 그대로 쓰면 본문 자리에 '실전예제 045'가 박힌다
    (사용자 지적 2026-08-31). 각 스텝의 **자기 헤더**로 순열을 만들고,
    표기는 공용 라벨(원고 대괄호 라벨 등)의 문구로 통일한다.

    스텝 헤더가 없거나 공용 라벨과 순열이 같으면 그 스텝은 넣지 않는다 —
    기존 교재(모든 스텝의 지문이 같은 원고)는 동작이 그대로다.
    """
    common = passage_labels(steps)
    canon = {}
    for lab in common:
        canon.setdefault(_label_key(lab), lab)
    out = {}
    for key in frame_steps:
        seq = _step_header_labels(steps.get(key))
        off = len(seq) - len(common)
        # 공용 라벨보다 지문이 **많은** 스텝만 다룬다. 개수가 같으면 공용
        # 라벨이 이미 맞는 것이고, 거기서 헤더로 다시 라벨을 만들면 표기만
        # 흔들린다 (코퍼스: 비상 Extended Reading·본문N 계열 30여 잡).
        if not seq or not common or off <= 0:
            continue
        # 앞머리(공용 라벨보다 많은 지문)는 자기 헤더 문구 그대로 —
        # 이 교재에서는 '본문'이다. 뒤쪽은 공용 라벨과 같은 지문이므로
        # 번호로 맞추되, 번호 체계가 다르면('실전01' vs 'N049') 순서로 맞춘다.
        head = [canon.get(_label_key(t), t) for t in seq[:off]]
        # 앞머리가 공용 라벨에 이미 있는 지문이면 헤더 추출이 어긋난 것이다
        # (같은 지문을 두 번 센 것) — 그런 문서는 건드리지 않는다. 코퍼스
        # 실측: 이 가드가 없으면 비상 Main Reading·본문N 계열 30여 잡의
        # 라벨이 통째로 밀린다.
        common_keys = {_label_key(x) for x in common}
        if any(h in common or _label_key(h) in common_keys for h in head):
            continue
        if all(_label_key(t) in canon for t in seq[off:]):
            labels = head + [canon[_label_key(t)] for t in seq[off:]]
        else:
            labels = head + list(common)
        if labels and labels != common:
            out[key] = labels
    return out


def ensure_step3_kinds(step3_data, log=None):
    """구버전 content.json(step3 단락에 kind 미주석) 재사용 대비 —
    kind가 하나도 없으면 v1 파서의 주석기를 그대로 호출해 in-place 보강.

    현행 파서(engines/workbook/parser)는 항상 kind를 심으므로 실서비스
    경로에선 no-op. 과거 job content.json 재실행(코퍼스/E2E)용 fail-open."""
    if not step3_data:
        return
    items = ((step3_data.get("normal") or [])
             + (step3_data.get("short") or []))
    if not items:
        return
    has_kind = any(p.get("kind")
                   for it in items for p in it.get("paragraphs") or [])
    if has_kind:
        return
    try:
        from engines.workbook.parser import _annotate_step3_kinds
        _annotate_step3_kinds(items, log)
        if callable(log):
            log("[v2] step3 kind 주석 보강 (구버전 content.json — "
                "kind 미포함)")
    except Exception as e:                                  # noqa: BLE001
        if callable(log):
            log(f"[v2] ⚠️ step3 kind 주석 보강 실패 — 기본 스타일 배치: {e}")


def steps_to_plan(steps, exclude=None, workbook_type="모의고사",
                  step_map=None):
    """v1 content steps → {"format": "wb-flows-v1", "flows": [...],
    "unsupported": [스텝키]} — 미지원 스텝은 커버리지 리포트용으로 기록.

    exclude: 스텝 키(전체 제외) + "step1_c1_btm"(C1 하단만 제외) 지원.
    workbook_type: "모의고사"|"교과서"|"EBS" — C1/C2 프레임 분리·아이콘 분기.
    step_map: 스텝→스토리 매핑 override (None = 모의고사 기본 STEP_MAP).
        지정 시 매핑에 없는 스텝은 배치 불가 → unsupported로 보고
        (EBS/수능특강 내지는 스텝 페이지 구성이 다르다).
    """
    global _LABEL_ABBREV
    _LABEL_ABBREV = _detect_label_abbrev(steps)
    exclude = set(exclude or [])
    smap = STEP_MAP if step_map is None else step_map
    flows = []
    unsupported = []
    warnings = []
    for step_key, step_data in steps.items():
        if step_key in exclude:
            continue
        builder = STEP_BUILDERS.get(step_key)
        if builder is None or (step_map is not None
                               and step_key not in smap):
            unsupported.append(step_key)
            continue
        # W20 D1 — hwp 심볼 PUA 인쇄 매핑 (사본 — content 원본 무변형)
        step_data = apply_pua_print_map(step_data)
        # W23 F3 — 아래첨자(₂류) 인쇄 매핑: ASCII 숫자 + sub 서식 run
        step_data = apply_subscript_print_map(step_data)
        if step_key == "step1_c1":
            built = builder(step_data, workbook_type=workbook_type,
                            exclude_btm=("step1_c1_btm" in exclude))
        elif step_key in _CTX_BUILDERS:
            built = builder(step_data, workbook_type=workbook_type)
        else:
            built = builder(step_data)
        # W30 후속 — 빌더가 소비하고 남은 ❮❯ 잔존을 등가 글리프로 치환
        # (빌더 이후 적용 — 1A1 []·1A2 TF 토큰 로직 보존)
        apply_glyph_print_map_units(built["units"])
        warnings.extend(built.get("warnings") or [])
        target = dict(smap.get(step_key, {}))
        flow = {"step": step_key, "target": target,
                "break_per_unit": True, "units": built["units"]}
        if built.get("ul_style"):
            flow["ul_style"] = built["ul_style"]
        flows.append(flow)
    # 전 스텝 공통 최종 패스 — 내용 없이 괄호쌍만 남은 단락 제거.
    # 원고가 채울 자리를 표시하다 비워둔 잔재라 어느 스텝에서도 내용이
    # 아니다 (2026-08-25 SL1 step2_c2: "()" 1줄이 완제품에 인쇄).
    _eb = _drop_empty_brackets(flows)
    if _eb:
        warnings.append("빈 괄호 단락 %d줄 제거 (원고 잔재)" % _eb)
    return {"format": "wb-flows-v1", "flows": flows,
            "unsupported": sorted(unsupported),
            # W66 ④ (사용자 지적 2026-08-14): 유닛 꼬리 몇 줄이 다음 칸으로
            # 새면 그 칸을 통째로 버린다 — 자간/행간으로 흡수(한도 안에서만,
            # 못 담으면 원복). "정말 아주 길어서 다음 페이지까지 넘어가야
            # 하는 경우만 제외하고는 웬만해선 한 프레임에" (사용자 스펙).
            "unit_fit": {"max_tracking": -25, "max_leading": 1,
                         "max_spill_lines": 5},
            "warnings": warnings}


def _drop_empty_brackets(flows):
    """유닛에서 빈 괄호쌍 단락 제거 — 제거 수 반환 (구조 판정)."""
    from core.structure import manuscript_noise as _mn
    n = 0
    for fl in flows:
        for i, u in enumerate(fl.get("units") or []):
            paras = u["paras"] if isinstance(u, dict) else u
            keep = [p for p in paras
                    if not _mn.is_empty_bracket(p.get("t") or "")]
            n += len(paras) - len(keep)
            if len(keep) != len(paras):
                if isinstance(u, dict):
                    u["paras"] = keep
                else:
                    fl["units"][i] = keep
    return n


# W75: 지문 뒤에 한 줄 더 붙는 '꼬리 지시문' — ※ 로 시작하는 선택 안내
# ("※ ①~⑤ 중 … 고르시오."). 자기 본문이 없어 문제 시작으로 세면 킵이
# 그 줄만 남긴 페이지를 만든다.
_RE_S3_TAIL_DIRECTIVE = re.compile(r"^[※*]\s*\S")


# 킵 블록 판정 보조 — 발문 블록이 '자기 지문 전문'을 다시 싣는가.
# 세트 멤버(윗글 발문)는 지문이 없거나 영작 대상 **발췌 한 문장**만 갖고,
# 지문을 재인쇄하는 독립 문항은 지문 전문을 갖는다. 절대 글자 수는 원고마다
# 다르므로 **그 문서의 전형 지문량(비-윗글 발문 블록의 중앙값)** 과 견준다.
_S3_OWN_PASSAGE_RATIO = 0.5


def _s3_block_passage_len(flat, i, q_styles):
    """발문 flat[i] 뒤 다음 발문 전까지의 지문 총 길이."""
    tot = 0
    for j in range(i + 1, len(flat)):
        q = flat[j]
        if q.get("s") in q_styles:
            break
        if "지문" in (q.get("s") or ""):
            tot += len((q.get("t") or "").strip())
    return tot


def _s3_own_passage_floor(flat, q_styles):
    """'자기 지문을 싣는다'고 볼 최소 지문량 — 문서 전형값의 절반."""
    import statistics
    base = []
    for i, q in enumerate(flat):
        if q.get("s") not in q_styles:
            continue
        t = (q.get("t") or "").lstrip()
        if re.match(r"^윗\s*글|^위\s*글", t):
            continue
        base.append(_s3_block_passage_len(flat, i, q_styles))
    if not base:
        return None
    return statistics.median(base) * _S3_OWN_PASSAGE_RATIO


def question_keep_op(plan, steps=("step3",)):
    """W23 r13 (F4) — 문제 단위 펼침면 킵 op 계산 (실행기/게이트 공용 계약).

    사용자 확정 스펙: 한 문제(발문+지문+선지 전체)가 왼쪽→오른쪽 페이지로
    이어지는 것은 허용, 오른쪽 페이지에서 잘려 다음 장(스프레드 넘김)으로
    이어지는 것은 금지 — 그 경우 문제 전체를 다음 페이지로 민다.

    starts = 문제 시작 단락의 '평탄화(flat) 인덱스' (실행기 processFlow가
    유닛을 순서대로 평탄화해 스토리에 얹으므로 스토리 단락 인덱스와 1:1).
    문제 시작 = STEP3 발문(Q)/그룹 인트로(Q-INTRO) 스타일 단락. 인덱스 0은
    제외 — 플로우 첫 단락을 밀면 섹션 시작 자체가 마커 페이지를 벗어난다.
    q_styles는 게이트 G30이 출력 재검산에 소비한다. 대상 스텝에 시작점이
    없으면 None (op 미적용)."""
    q_styles = set()
    for kind in ("Q", "Q-INTRO"):
        st = _style("STEP3", kind)
        if st:
            q_styles.add(st)
    flows_cfg = {}
    for fl in plan.get("flows", []):
        if fl.get("step") not in steps:
            continue
        starts = []
        stem_starts = []
        # W75 (수특라이트 13강 실증): 자기 본문이 **없는** 발문은 문제
        # 시작이 아니다 — 이 원고의 문맥어휘/어법 문항은 지문 뒤에
        # "※ ①~⑤ 중 … 고르시오." 지시문이 한 줄 더 붙는데, 그것까지
        # 시작으로 세면 킵이 그 줄만 남기고 다음 문제를 새 페이지로 밀어
        # **한 줄짜리 페이지**가 생긴다(게이트 G41 [발문고아] critical).
        # 다음 발문까지 비발문 내용이 하나도 없으면 앞 블록의 꼬리다.
        _flat = [q for u in fl.get("units", []) for q in unit_paras(u)]
        _intro_style = _style("STEP3", "Q-INTRO")
        _ansl_style = _style("STEP3", "AnsL")
        _tail_only = set()
        for _i, _q in enumerate(_flat):
            if _q.get("s") not in q_styles:
                continue
            if _q.get("s") == _intro_style:
                continue        # 세트 안내문은 원래 자기 본문이 없다 —
                                # 뒤따르는 발문과 한 덩어리로 밀려야 한다
            _qt = (_q.get("t") or "").strip()
            if len(_qt) > 60 or not _RE_S3_TAIL_DIRECTIVE.match(_qt):
                continue        # 지문 뒤 꼬리 지시문(※ …)만 대상
            _body = 0
            for _j in range(_i + 1, len(_flat)):
                if _flat[_j].get("s") in q_styles:
                    break
                # 답 여백(공백만 있는 줄·답란 스타일·표)도 그 문항의 몸통이다
                if (_flat[_j].get("t") or "") or _flat[_j].get("table") \
                        or _flat[_j].get("s") == _ansl_style:
                    _body += 1
                    break
            if not _body:
                _tail_only.add(_i)
        _own_floor = _s3_own_passage_floor(_flat, q_styles)
        idx = 0
        for u in fl.get("units", []):
            for p in unit_paras(u):
                if p.get("s") in q_styles and idx > 0 \
                        and idx not in _tail_only:
                    # W52 (0645d4a7 v2_6 사용자 지적 3): '윗글' 참조 발문은
                    # 위에 이미 인쇄된 지문의 세트 멤버 — 독립 시작으로
                    # 삼으면 지문(※ 인트로+본문)과 문항이 페이지 경계에서
                    # 갈라진다. 세트 시작(Q-INTRO/'다음 글' 발문)만 킵
                    # 경계로 남겨 지문+문항이 한 덩어리로 밀리게 한다.
                    # 발문고아킵(stem_keep)은 모든 발문에 계속 적용 —
                    # stem_starts 별도 전달.
                    stem_starts.append(idx)
                    t = (p.get("t") or "").lstrip()
                    # 2026-08-28 사용자 지적("64번 다음에 공간이 널널한데
                    # 65번이 왜 다음 페이지로"): W52의 '윗글 발문 = 세트
                    # 멤버' 규칙은 **지문을 한 번만 싣는 원고**의 관행이다.
                    # 문항마다 지문을 재인쇄하는 원고에서는 '윗글' 발문도
                    # 자기 지문을 갖는 독립 문항이라, 앞 문항과 한 덩어리로
                    # 묶이면 킵 블록이 두 문항 크기가 되어 들어갈 자리가
                    # 있는데도 통째로 다음 페이지로 밀린다(65+66 실측).
                    # 표기가 아니라 **자기 지문 유무**로 가른다.
                    if not re.match(r"^윗\s*글|^위\s*글", t) or (
                            _own_floor is not None
                            and _s3_block_passage_len(_flat, idx, q_styles)
                            >= _own_floor):
                        starts.append(idx)
                idx += 1
        if starts:
            flows_cfg[fl["step"]] = {"starts": starts,
                                     "stem_starts": stem_starts}
    if not flows_cfg:
        return None
    # W40 결함 2 — 발문 고아 방지 (프레임판 question_keep): 프레임 하단에
    # 발문만 남거나 발문+본문 1줄만 남으면 문제 시작을 다음 프레임으로
    # 민다 (실행기 enforceStemKeep 계약 — min_lines = 발문 뒤 최소 동반
    # 본문 줄수. 게이트 G41이 stem_keep 유무로 critical/warning 분기).
    return {"flows": flows_cfg, "q_styles": sorted(q_styles),
            "stem_keep": {"min_lines": 2}}


# 다열 선지 판정용 (W83) — 원 숫자 마커, 그리고 '줄 머리가 아닌' 마커 앞 공백
_RE_CHOICE_MARK = re.compile(r"[①-⑳]")
_RE_CHOICE_SPLIT = re.compile(r"(?<=\S)[ \u00a0]+(?=[①-⑳])")


def _multi_choice_grid_rows(rows):
    """여러 줄에 걸친 다열 선지 '격자'의 행 인덱스 (W83).

    한 줄에 선지가 둘 이상 있고 그런 줄이 **연달아 둘 이상**일 때만 격자다
    (`① (A)-(C)-(B) ② (B)-(A)-(C)` / `③ … ④ …` / `⑤ …`). 열이 행마다
    맞아야 하므로 탭스톱이 필요하다. 다섯 개가 한 줄에 다 들어간 선지
    (`① (A) ② (B) ③ (C) ④ (D) ⑤ (E)`)는 맞출 상대가 없어 대상이 아니다 —
    기존 완성본의 공백 정렬을 그대로 둔다.
    """
    out = set()
    run = []
    for i, p in enumerate(rows + [None]):
        multi = (p is not None and "선지" in (p.get("s") or "")
                 and "\t" not in (p.get("t") or "")
                 and len(_RE_CHOICE_MARK.findall(p.get("t") or "")) >= 2)
        if multi:
            run.append(i)
            continue
        if len(run) >= 2:
            out |= set(run)
        run = []
    return out


def normalize_choice_tabs(plan, steps=("step3",)):
    """W40 결함 1b — 다열 선지 행의 탭 구분자 정규화 (탭스톱 적용 전 필수).

    원고는 기본 12.7mm 그리드에서 긴 항목이 다음 스톱으로 밀리는 걸 사람이
    탭/공백을 더 넣어 눈대중으로 맞춘 흔적을 갖고 있다 (`① draw\\t\\t was`
    vs `③ drawn\\t was`). 명시 탭스톱을 부여하는 지금은 이 여분이 오히려
    같은 열을 행마다 다른 셀 인덱스에 앉혀 어긋나게 만든다. 게이트 G42는
    행 간 min(셀수)까지만 대조해 이 잔여 어긋남을 통과시킨다 (v14 실증:
    `① boosts`의 where=269.6 vs `⑤ boosts`의 where=282.3).

    연속 탭과 탭 직후 선행 공백을 단일 탭으로 접어 셀 인덱스를 의미 단위로
    맞춘다. runs 는 문자 인덱스가 아니라 텍스트 조각이라 같은 규칙을 적용해
    동기화하고, 합계가 어긋나면 그 단락은 건드리지 않는다 (fail-safe)."""
    n = 0
    for fl in plan.get("flows", []):
        if fl.get("step") not in steps:
            continue
        for u in fl.get("units", []):
            rows = list(unit_paras(u))
            grid = _multi_choice_grid_rows(rows)
            for _i, p in enumerate(rows):
                t = p.get("t") or ""
                if "선지" not in (p.get("s") or ""):
                    continue
                if "\t" not in t:
                    if _i not in grid:
                        continue
                    # W83 — 한 줄에 선지 여러 개인데 구분이 공백뿐인 원고
                    # ('① (A)-(C)-(B) ② (B)-(A)-(C)'). 탭이 없으면 아래
                    # choice_tabs_op 이 열 정렬 계약을 아예 안 만들어 번호가
                    # 행마다 제멋대로 붙는다 — 둘째 선지부터 탭으로 가른다.
                    new_t = _RE_CHOICE_SPLIT.sub("\t", t)
                    if new_t == t:
                        continue
                    runs = p.get("runs") or []
                    new_runs = [dict(r, t=_RE_CHOICE_SPLIT.sub(
                        "\t", r.get("t") or "")) for r in runs]
                    if runs and "".join(r.get("t") or ""
                                        for r in new_runs) != new_t:
                        continue      # 마커가 run 경계에 걸침 — 원본 유지
                    p["t"] = new_t
                    if runs:
                        p["runs"] = new_runs
                    n += 1
                    continue
                new_t = re.sub(r"\t[\t ]+", "\t", t)
                if new_t == t:
                    continue
                runs = p.get("runs") or []
                new_runs = [dict(r, t=re.sub(r"\t[\t ]+", "\t", r.get("t") or ""))
                            for r in runs]
                if runs and "".join(r.get("t") or "" for r in new_runs) != new_t:
                    continue          # 탭이 run 경계에 걸침 — 원본 유지
                p["t"] = new_t
                if runs:
                    p["runs"] = new_runs
                n += 1
    return n


def choice_tabs_op(plan, steps=("step3",)):
    """W40 결함 1 — 다열 선지 열 정렬 op 계산 (실행기 applyChoiceTabs 계약).

    실행기는 있었는데 플랜 쪽 계약 생성부가 없어 계약 미발행 상태였고,
    그래서 명시 탭스톱 없이 InDesign 기본 12.7mm 탭 그리드로 떨어져 열이
    행마다 한 스톱씩 어긋났다 (게이트 G42가 편차 12.7mm로 지목 — v13
    33그룹). 대상 스텝에 탭 선지 단락이 없으면 None (op 미적용).

    grid/min_gap 은 v1 손마무리 실물 관행값 (배재2_워크북01 실측)."""
    hits = 0
    target = []
    for fl in plan.get("flows", []):
        step = fl.get("step")
        if step not in steps:
            continue
        n = 0
        for u in fl.get("units", []):
            for p in unit_paras(u):
                if "선지" in (p.get("s") or "") and "\t" in (p.get("t") or ""):
                    n += 1
        if n:
            target.append(step)
            hits += n
    if not target:
        return None
    return {"steps": target, "grid": 12.7, "min_gap": 2,
            "style_contains": "선지", "_rows": hits}
