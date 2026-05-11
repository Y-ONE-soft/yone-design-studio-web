# Y.ONE DESIGN 통합웹사이트

InDesign 조판/표지 자동화 웹 서비스. Flask 기반.

---

## 환경 구성

```
[운영 — 아이맥]                       [개발 — 맥북]
~/dev/yone-design-web/                 ~/dev/yone-design-web/
  ↑                                      ↑
launchd 자동 시작 (24/7)               python3 app.py (수동)
  ↓                                      ↓
localhost:5010                         localhost:5010
  ↓
yonestudio.com (Cloudflare Tunnel)
```

- 운영: **아이맥**의 `~/dev/yone-design-web/` 위치에서 launchd가 24/7 가동
- 개발: **맥북**의 `~/dev/yone-design-web/` 위치에서 사용자가 수동 실행
- 코드 동기화: GitHub Private repo (`YONE-DESIGN/YONE-DESIGN-WEB`)
- 데이터 폴더(조판/, 디자인/): 각 컴퓨터의 로컬 위치 — `YONE_STUDIO_ROOT` 환경변수로 지정

---

## 새 컴퓨터 설치

```bash
# 1. iCloud 밖 위치에 clone
mkdir -p ~/dev
cd ~/dev
git clone https://github.com/YONE-DESIGN/YONE-DESIGN-WEB.git yone-design-web
cd yone-design-web

# 2. git 설정 (이미 있으면 생략)
git config --global user.name "Y.ONE DESIGN"
git config --global user.email "yungienglish.lab@gmail.com"
git config --global credential.helper osxkeychain

# 3. 의존성
pip3 install -r requirements.txt

# 4. 환경변수 설정 (둘 중 하나)
#    A) ~/.zshrc에 추가 (수동 실행용)
#       export YONE_STUDIO_ROOT="/Users/.../Y.ONE STUDIO"
#    B) launchd plist에 등록 (자동 시작용)

# 5. 실행
python3 app.py
```

브라우저: `http://localhost:5010/login`

---

## 환경변수

| 변수 | 용도 | 미지정 시 |
|---|---|---|
| `YONE_STUDIO_ROOT` | 조판/, 디자인/ 데이터 폴더의 상위 경로 | 통합웹 폴더의 상위 폴더 사용 |
| `YONE_ADMIN_PASSWORD` | admin 로그인 비밀번호 | fallback 값 |
| `YONE_ASSISTANT_PASSWORD` | assistant 로그인 비밀번호 | fallback 값 |

자세한 예시는 `.env.example` 참조.

---

## 사용자 계정

| 아이디 | 권한 | 접근 가능 |
|---|---|---|
| admin | 관리자 | 조판, 표지, 목업, 채팅 (전체) |
| assistant | 조교 | 조판, 표지만 |

비밀번호 변경:
- 빠른 방법: `app.py`의 `USERS` 딕셔너리의 fallback 값 직접 수정
- 안전한 방법: `YONE_ADMIN_PASSWORD` / `YONE_ASSISTANT_PASSWORD` 환경변수 등록

---

## 일상 워크플로우

```bash
# 작업 시작 전 (양쪽 컴퓨터 어디서든)
cd ~/dev/yone-design-web
git pull

# 작업 후 반영
git add .
git commit -m "메시지"
git push

# 반대편 컴퓨터에서
git pull
```

---

## 운영 관리 (아이맥)

```bash
# 서비스 상태
launchctl list | grep yone
lsof -i :5010 -nP -t

# 재시작
launchctl unload ~/Library/LaunchAgents/com.yonestudio.flask.plist
launchctl load ~/Library/LaunchAgents/com.yonestudio.flask.plist

# 로그
tail -f ~/Library/Logs/yonestudio-flask.log
tail -f ~/Library/Logs/yonestudio-flask-error.log
```

---

## 디렉터리 구조

```
yone-design-web/
├── app.py                    # Flask 엔트리포인트
├── config.py                 # 경로/포트 설정
├── requirements.txt          # Python 의존성
├── core/                     # 공통 모듈 (job_manager, indesign runner, paths)
├── engines/                  # 교재별 조판/표지 엔진
├── templates/                # Jinja2 HTML 템플릿
├── static/                   # CSS, JS
├── data/                     # 학교/교재 메타데이터 (JSON)
├── jobs/                     # 작업 결과 (gitignore)
├── uploads/                  # 업로드 파일 (gitignore)
└── .env.example              # 환경변수 템플릿
```

---

## .gitignore 제외

- `jobs/`, `uploads/` — 작업 데이터 (대용량, 매번 다름)
- `__pycache__/`, `*.pyc` — Python 캐시
- `.env`, `.env.local` — 비밀번호 등 환경변수
- `.claude/`, `.DS_Store`, `.vscode/`, `.idea/`

---

## 자주 묻는 질문

**Q. 맥북에서 코드 수정해도 아이맥(yonestudio.com)에는 안 반영되네?**
A. 정상. `git push` 후 아이맥에서 `git pull`해야 반영. iCloud처럼 자동 동기화 X.

**Q. 아이맥 Flask가 죽으면?**
A. launchd의 `KeepAlive=true` 설정으로 자동 재시작됨.

**Q. 비밀번호를 코드 안에 평문으로 두는 게 보안상 괜찮나?**
A. Private repo라 외부 노출은 없지만, 운영용에는 `.env` 또는 launchd 환경변수로 분리 권장.
