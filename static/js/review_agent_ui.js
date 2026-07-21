// W41 후속 — AI 검수 에이전트 결과 카드(판정 그룹 + 재조판 버튼) 공용 렌더.
// static/js/typeset.js에 있던 _reviewAgentHtml/rerunJob을 공용화한 것 —
// result_session.js(W30-후속)와 같은 패턴으로, 자체 showResultCard 사본을
// 가진 인라인 폴링 템플릿 19곳에서도 같은 카드를 렌더한다.
//
// 사용 계약:
//   - typeset.js 경로: showResultCard가 ReviewAgentUI.html(jobId, ra)로 삽입.
//   - 인라인 템플릿: showResultCard 말미에
//       if (window.ReviewAgentUI) ReviewAgentUI.append(area, jobId, result.review_agent);
//   - 재조판 버튼 onclick은 전역 rerunJob(jobId) — 이 파일이 정의.
//     페이지 전역 startStream/appendLog/setStep이 있으면 재사용(전 템플릿 보유),
//     없어도 fetch 자체는 수행하고 로그만 생략한다 (fail-open).
// 라우트/세션 정책 무변경 — 표시 계층만.
(function () {
  'use strict';

  function esc(s) {
    return String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // judgement 분류: auto_fixable(재조판 제안 — 사용자 클릭 시에만 실행),
  // manuscript_error(원고 오류 — 원고 수정 필요), operator_judgment(운영 확인).
  function raHtml(jobId, ra) {
    if (!ra) return '';
    var verdictBadge = {
      pass: '✅ 통과', suspect: '👁 확인 필요', fail: '❌ 결함 발견'
    }[ra.verdict] || esc(ra.verdict || '?');
    var judgeLabel = {
      auto_fixable: '🔁 자동 수정 가능(재조판 제안)',
      manuscript_error: '📝 원고 오류 (원고 수정 필요)',
      operator_judgment: '👁 운영 판단 필요'
    };
    var groups = { auto_fixable: [], manuscript_error: [], operator_judgment: [] };
    (ra.findings || []).forEach(function (f) {
      (groups[f.judgement] || groups.operator_judgment).push(f);
    });
    var items = '';
    Object.keys(groups).forEach(function (j) {
      var list = groups[j];
      if (!list.length) return;
      items += '<div class="ra-group"><div class="ra-group-label">' + judgeLabel[j] +
        ' — ' + list.length + '건</div><ul class="warn-list">' +
        list.map(function (f) {
          return '<li>p' + esc(f.page) + ' [' + esc(f.check || f.type) + '] ' + esc(f.detail) +
            (f.suggestion ? ' <em>(' + esc(f.suggestion) + ')</em>' : '') + '</li>';
        }).join('') + '</ul></div>';
    });
    var nAuto = (ra.counts && ra.counts.auto_fixable) || 0;
    var rerunBtn = nAuto > 0
      ? '<div class="action-row">' +
          '<button type="button" class="mockup-btn" id="rerun-btn" ' +
                  'onclick="rerunJob(\'' + esc(jobId) + '\')">🔁 재조판 실행 (자동 수정 제안 ' + nAuto + '건)</button>' +
        '</div>'
      : '';
    var meta = [
      ra.pages_reviewed && ra.pages_reviewed.length
        ? '표본 ' + ra.pages_reviewed.length + '페이지 검수' : '',
      ra.wall_s ? ra.wall_s + '초' : ''
    ].filter(Boolean).join(' · ');
    return (
      '<div class="ra-card" style="margin-top:12px;padding:12px;border:1px solid #d0d4dc;border-radius:8px;">' +
        '<div class="result-header">' +
          '<span class="result-badge">🔍 AI 검수: ' + verdictBadge + '</span>' +
          '<span style="font-size:12px;color:#667;">' + esc(meta) + '</span>' +
        '</div>' +
        (items || '<p style="font-size:13px;">발견된 결함이 없습니다.</p>') +
        (ra.notes ? '<p style="font-size:12px;color:#667;">' + esc(ra.notes) + '</p>' : '') +
        rerunBtn +
      '</div>');
  }

  // 인라인 템플릿용 — 이미 렌더된 결과 카드(.result-card) 안에 RA 카드를 덧붙인다.
  // ra가 없으면 no-op. 결과 카드가 없으면(area 직접) area에 붙인다.
  function appendCard(area, jobId, ra) {
    if (!ra || !area) return;
    var html = raHtml(jobId, ra);
    if (!html) return;
    var host = area.querySelector('.result-card') || area;
    var wrap = document.createElement('div');
    wrap.innerHTML = html;
    while (wrap.firstChild) host.appendChild(wrap.firstChild);
    area.classList.remove('hidden');
  }

  function _log(msg) {
    if (typeof window.appendLog === 'function') window.appendLog(msg);
  }

  // 재조판 — POST /api/rerun/<job_id> 후 페이지 공용 진행 영역/스트림으로 전환.
  // 실제 재실행은 이 사용자 클릭에서만 발생한다 (무단 재조판 금지 — W41 계약).
  async function rerunJob(jobId) {
    var btn = document.getElementById('rerun-btn');
    if (btn) { btn.disabled = true; btn.textContent = '재조판 시작 중...'; }
    try {
      var res = await fetch('/api/rerun/' + jobId, { method: 'POST' });
      var data = await res.json();
      if (!res.ok || data.error) {
        _log('[재조판 오류] ' + (data.error || '서버 오류'));
        if (btn) { btn.disabled = false; btn.textContent = '🔁 재조판 실행'; }
        return;
      }
      // 새 job으로 진행 영역 전환 (기존 결과 카드는 대체)
      var progress = document.getElementById('progress-area');
      var result = document.getElementById('result-area');
      var log = document.getElementById('log-area');
      if (progress) progress.classList.remove('hidden');
      if (result) { result.classList.add('hidden'); result.innerHTML = ''; }
      if (log) log.textContent = '';
      if (typeof window.setStep === 'function') { try { window.setStep(null); } catch (_) {} }
      _log('[재조판] 새 작업 시작 (job ' + data.job_id + ' — 원본 ' + jobId + ')');
      if (typeof window._tsSetCurrent === 'function') window._tsSetCurrent(data.job_id, null);
      if (typeof window.startStream === 'function') {
        window.startStream(data.job_id);
      } else {
        _log('[재조판] 진행 스트림 함수를 찾지 못했습니다 — 완료 후 페이지를 새로고침해 주세요.');
      }
    } catch (err) {
      _log('[재조판 오류] ' + err.message);
      if (btn) { btn.disabled = false; btn.textContent = '🔁 재조판 실행'; }
    }
  }

  window.ReviewAgentUI = { html: raHtml, append: appendCard, rerun: rerunJob };
  window.rerunJob = rerunJob;
})();
