"""W14 — 품질 루프 4라운드 결함 가드 (미학습 원고 2종 실증 결함의 재발 방지).

투입 원고 (docs/원고_구조_인벤토리.md 다양성 후보):
  후보③ 공통영어1 비상(홍) 3과 타학교 기출 서술형 hwpx (조건 지시문
         발문 헤더형, Step3 단독) → textbook_workbook_v2
  후보⑥ 리딩파워 유형완성 기출문제-16강 CR-4(177문제).hwp ([CRN-N]형
         기출 문제모음) → ebs_workbook_v2

결함→가드 매핑:
  D1 문제모음 파일명 라우팅 공백 — '변형문제' 토큰 없는 기출 문제모음
     ("…기출문제-16강 CR-4(177문제).hwp")이 어느 스텝에도 매핑되지 않아
     prepare_jsx 빈플랜 차단에 걸림 (c06 실증 — W12 안전망이 침묵 유실은
     막았으나 조판 자체가 불가). 붙은 문항수 표기 "\\d문제"를 문제모음
     신호로 라우팅 (전수 인벤토리 20982건 중 36종 전부 문제모음 실증).
  D2 요약 화살표(⇩)의 hwp 사용자 영역(PUA) 인코딩 변형 — v1 pass 11
     포트(_RE_S3_ARROW)가 리터럴 화살표만 매칭해 (c05 모의고사
     18건)/\U000f0036(c06 2건) 단독 단락이 tofu로 인쇄되고 요약문 배경도
     미부여. 플랜 삭제+배경 일반화 + 게이트 G10 [특수문자] 이중 방어
     (검출 실증: 수리 전 c05 W13 최종 출력 덤프 → G10 critical 18건).
"""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")


# ── D1: 문제모음 파일명 라우팅 (\d문제) ─────────────────────────────────────

def test_variant_pool_count_marker_routes():
    from engines.workbook_v2.engine import (_is_variant_pool_filename,
                                            _routes_to_step3)
    # W14 c06 실물 + 인벤토리 대표 문제모음
    for f in ("리딩파워 유형완성 기출문제-16강 CR-4(177문제).hwp",
              "리딩파워유형편완성_CH1_01강_변형문제(46문제).hwp",
              "고2_2023년-12월-모의고사_변형문제_18_42_231문제_아잉카아카데미.hwp",
              "3과 50문제.hwp"):
        assert _is_variant_pool_filename(f), f
        assert _routes_to_step3(f), f


def test_variant_pool_count_marker_rejects():
    from engines.workbook_v2.engine import _is_variant_pool_filename
    # 정답/해설 본, 스텝 원고, 문항수가 아닌 띄어쓴 "N 문제"(day 범위)
    for f in ("변형문제 정답지.hwp",
              "리딩파워유형편완성_CH1_01강_변형문제(46문제) 해설.hwp",
              "Step1 A1 어휘선택.docx",
              "배재고 어휘 DAY23~25 문제.hwpx",
              "24년 3월 고2 문제.hwpx"):
        assert not _is_variant_pool_filename(f), f
