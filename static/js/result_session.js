// W30 후속 — /api/result 세션 만료(401)·job 소멸(404) 공용 처리.
// static/js/typeset.js(1c55e6e)와 같은 수리를, 자체 fetchResult 사본을 가진
// 인라인 폴링 템플릿들에 공용화한 것. 로그인 세션(12시간 절대 만료)이 조판
// 중 끝나면 /api/result가 401 {"error":"unauthorized"}를 반환하는데, 종전
// 인라인 사본들은 이를 '결과 없음'으로 오분류해 게이트 경고·결과를 사용자에게
// 전달하지 못했다 (실증: job 376b34d0). localStorage 키·스키마는 typeset.js와
// 동일('ts_pending_result', {jobId, path, ts}) — 복원은 path 매칭이라 페이지 간
// 간섭 없음. 라우트/세션 정책 무변경(보안 약화 없음).
(function () {
  'use strict';
  var KEY = 'ts_pending_result';

  function save(jobId) {
    try {
      localStorage.setItem(KEY, JSON.stringify(
        { jobId: jobId, path: location.pathname, ts: Date.now() }));
    } catch (_) {}
  }

  function clear() {
    try { localStorage.removeItem(KEY); } catch (_) {}
  }

  function showExpiredCard(jobId) {
    save(jobId);
    var area = document.getElementById('result-area');
    if (!area) return;
    area.classList.remove('hidden');
    area.innerHTML =
      '<div class="result-card warn">' +
        '<div class="result-header">' +
          '<span class="result-badge">🔒 세션 만료</span>' +
        '</div>' +
        '<p>로그인 세션이 만료되어 조판 결과를 표시하지 못했습니다.<br>' +
           '결과와 검수 경고는 서버에 보관되어 있습니다 — 다시 로그인한 뒤 ' +
           '이 페이지로 돌아오면 자동으로 표시됩니다.</p>' +
        '<div class="action-row">' +
          '<a href="/login" class="mockup-btn">🔑 다시 로그인</a>' +
        '</div>' +
      '</div>';
  }

  // fetch Response의 401/404를 처리했으면 true 반환 — 호출측은 즉시 return.
  // 401: 재시도해도 영원히 401 — 재로그인 안내 카드 + job_id 보관.
  // 404: job 소멸(서버 재시작 등) — 보관 정리 후 안내.
  function handle(res, jobId, showError) {
    if (res.status === 401) {
      if (typeof window.appendLog === 'function') {
        window.appendLog('[오류] 세션이 만료되어 결과를 가져오지 못했습니다. 다시 로그인하면 결과가 표시됩니다.');
      }
      showExpiredCard(jobId);
      return true;
    }
    if (res.status === 404) {
      clear();
      if (showError) {
        showError('작업 결과를 찾을 수 없습니다 (서버가 재시작되었을 수 있습니다). 조판을 다시 실행해 주세요.');
      }
      return true;
    }
    return false;
  }

  // 재로그인 후 같은 페이지 복귀 시 보류된 결과 자동 복원 (24시간 한도).
  // 페이지의 전역 fetchResult를 호출 — typeset.js가 로드된 페이지에서는
  // typeset.js 자체 복원 IIFE가 담당하므로 이중 발화하지 않는다.
  function resume() {
    if (typeof window._savePendingResult === 'function') return;  // typeset.js 복원 담당
    var entry = null;
    try { entry = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (_) {}
    if (!entry || !entry.jobId || entry.path !== location.pathname) return;
    if (Date.now() - (entry.ts || 0) > 24 * 3600 * 1000) { clear(); return; }
    if (typeof window.fetchResult !== 'function') return;
    var progress = document.getElementById('progress-area');
    if (progress) progress.classList.remove('hidden');
    if (typeof window.appendLog === 'function') {
      window.appendLog('[복원] 이전 조판 결과를 확인합니다... (job ' + entry.jobId + ')');
    }
    window.fetchResult(entry.jobId);
  }

  window.ResultSession = { save: save, clear: clear, handle: handle, resume: resume };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', resume);
  } else {
    resume();
  }
})();
