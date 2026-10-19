# Y.ONE 디자인 스튜디오 — 조판 서비스 컨테이너 (Fly.io `yos-studio`, yos-typeset 과 같은 방식)
#   python 3.13 + node 22 + chromium(Vivliostyle 가 쓰는 브라우저) + ghostscript(CMYK 인쇄본)
#   실행: gunicorn 워커 1개(잡 등록부가 인메모리) + 스레드. 상태는 전부 /data (Fly 볼륨).
#   yos-typeset 처럼 root 로 돈다(Fly 머신은 단일 테넌트 VM · chromium 은 --no-sandbox). 자세한 건 deploy/README.md
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=Asia/Seoul \
    NODE_MAJOR=22

# ── OS: chromium(+의존 라이브러리) · ghostscript · 기본 CJK 서체(폴백) · node ──
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg tzdata \
        chromium ghostscript fonts-noto-cjk fonts-noto-color-emoji fontconfig \
        libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
        libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 파이썬 의존성 (소스보다 먼저 — 캐시) ──
COPY requirements.txt requirements-vivlio.txt requirements-web.txt ./
RUN pip install -r requirements-web.txt

# ── Vivliostyle CLI (vivliostyle/ — 나중에 뽑을 때 쓴다) — 크롬은 내려받지 않고 시스템 chromium 을 쓴다 ──
COPY vivliostyle/package.json vivliostyle/package-lock.json ./vivliostyle/
RUN cd vivliostyle && PUPPETEER_SKIP_DOWNLOAD=1 npm ci --no-audit --no-fund

# ── 소스 ──
COPY . .
# 리포의 카탈로그는 첫 기동 때 볼륨으로 복사된다(entrypoint) — 이후엔 볼륨이 정본
# 리포의 카탈로그는 첫 기동 때 /data/catalog 로 복사된다(entrypoint) — 이후엔 볼륨이 정본
RUN mv catalog /app/catalog.seed && mkdir -p /data/studio /data/catalog /data/fonts /data/icc \
    && chmod +x deploy/entrypoint.sh

# ── 런타임 경로 — 전부 /data (fly.toml [mounts] 가 볼륨을 여기에 건다) ──
ENV YONE_STUDIO_ROOT=/data/studio \
    YONE_CATALOG_DIR=/data/catalog \
    YONE_FONT_DIRS=/data/fonts \
    YONE_ICC_DIRS=/data/icc \
    YONE_VIV_BROWSER=/usr/bin/chromium \
    YONE_STUDIO_HOST=0.0.0.0 YONE_STUDIO_PORT=5099 \
    YONE_COOKIE_SECURE=1

EXPOSE 5099
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://127.0.0.1:5099/api/v1/health || exit 1
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
