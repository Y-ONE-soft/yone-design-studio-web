# 화이트북 외부 파서 리포 스냅샷 (W35 배치 C — docs/인식지점_전수감사.md 리스크 4위).
#
# parse_whitebook.py 는 아래 원본의 byte-identical 스냅샷이다 (md5 09c723f4…):
#   조판/교재/프리미엄북/화이트북/auto/parse_whitebook.py
#   (= engines/whitebook/config.json 의 "parse_script" — iCloud, 리포 밖)
#
# 참조 관계 (감사 권고 확인 결과):
#   - v1(engines/whitebook)은 종전대로 config parse_script(원본 경로)를 subprocess
#     호출 — 실서비스 운영 무변경, 원본 파일 무수정.
#   - v2(engines/whitebook_v2)는 이 스냅샷을 import 해 사용 — 섹션 분할만
#     engines/whitebook_v2/wb_parser.py 의 구조 신호 인식으로 대체.
#   - 원본과의 divergence는 tests/test_whitebook_section_batch_c.py 의
#     byte-parity 테스트가 감시한다 (감사 사각 해소 지점).
