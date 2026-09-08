/* typeset.js — 파일 업로드 + SSE 실시간 로그 + 결과 카드 */

const materialId = (document.currentScript && document.currentScript.dataset.material)
  || document.querySelector('script[data-material]')?.dataset.material
  || '';

// ── 파일 선택/드롭 (multiple input 누적 지원) ─────────────────────────────

// 슬롯별 누적 파일 저장소 (브라우저가 input.files를 매번 교체하므로 별도 보관)
const _fileStore = {};
// 슬롯별 상대경로 저장소 — store.files와 같은 순서. 폴더를 통째로 끌어놓으면
// 'EBS 20지문/6~10/워크북/Step1 A1 어휘선택.docx' 처럼 폴더 경로가 남는다.
// 원고가 여러 폴더로 나뉜 교재(부교재 워크북)에서 폴더 = 원고 한 세트다.
const _relStore = {};

function _getStore(key) {
  if (!_fileStore[key]) _fileStore[key] = new DataTransfer();
  if (!_relStore[key]) _relStore[key] = [];
  return _fileStore[key];
}

function _addFiles(key, fileList, relPaths) {
  const store = _getStore(key);
  const rels = _relStore[key];
  const existing = new Set();
  for (let i = 0; i < store.files.length; i++) {
    existing.add((rels[i] || '') + '|' + store.files[i].name + '|' + store.files[i].size);
  }
  for (let i = 0; i < fileList.length; i++) {
    const rel = (relPaths && relPaths[i]) || fileList[i].webkitRelativePath || '';
    const id = rel + '|' + fileList[i].name + '|' + fileList[i].size;
    if (!existing.has(id)) {
      store.items.add(fileList[i]);
      rels.push(rel);
      existing.add(id);
    }
  }
}

// 드롭된 항목(파일/폴더)을 재귀 순회해 {file, rel} 목록으로 편다.
function _readEntry(entry, prefix) {
  return new Promise((resolve) => {
    if (!entry) { resolve([]); return; }
    if (entry.isFile) {
      entry.file(
        (f) => resolve([{ file: f, rel: prefix + entry.name }]),
        () => resolve([])
      );
      return;
    }
    if (!entry.isDirectory) { resolve([]); return; }
    const reader = entry.createReader();
    const all = [];
    const readBatch = () => {
      reader.readEntries((entries) => {
        if (!entries.length) {
          Promise.all(all.map((e) => _readEntry(e, prefix + entry.name + '/')))
            .then((lists) => resolve([].concat.apply([], lists)));
          return;
        }
        for (let i = 0; i < entries.length; i++) all.push(entries[i]);
        readBatch();          // readEntries는 한 번에 일부만 준다 — 소진까지 반복
      }, () => resolve([]));
    };
    readBatch();
  });
}

function _syncInput(key) {
  const input = document.getElementById(`input-${key}`);
  const store = _getStore(key);
  input.files = store.files;

  // 파일 리스트 렌더링
  const listEl = document.getElementById(`file-list-${key}`);
  if (listEl) {
    if (store.files.length === 0) {
      listEl.innerHTML = '';
    } else {
      const rels = _relStore[key] || [];
      listEl.innerHTML = Array.from(store.files).map((f, i) => {
        const rel = rels[i] || '';
        const dir = rel.indexOf('/') >= 0
          ? rel.slice(0, rel.lastIndexOf('/')) + '/' : '';
        return `<div class="file-list-item">
          <span class="file-list-name">${dir ? `<span style="opacity:.55">${dir}</span>` : ''}${f.name}</span>
          <button type="button" class="file-list-del" onclick="removeFile('${key}', ${i})" title="삭제">✕</button>
        </div>`;
      }).join('');
    }
  }

  // 드롭존 상태
  const zone = document.querySelector(`#slot-${key} .drop-zone`);
  if (zone) zone.classList.toggle('has-file', store.files.length > 0);

  // 기존 이름 표시 (드롭존 내 span)
  const nameEl = document.getElementById(`name-${key}`);
  if (nameEl) {
    nameEl.textContent = store.files.length > 0 ? `${store.files.length}개 선택됨` : '';
  }
}

function removeFile(key, idx) {
  const store = _getStore(key);
  const files = Array.from(store.files);
  const rels = _relStore[key] || [];
  const newDt = new DataTransfer();
  const newRels = [];
  files.forEach((f, i) => {
    if (i !== idx) { newDt.items.add(f); newRels.push(rels[i] || ''); }
  });
  _fileStore[key] = newDt;
  _relStore[key] = newRels;
  _syncInput(key);
}

function handleFileSelect(input, key) {
  if (!input.files.length) return;
  if (input.multiple) {
    _addFiles(key, input.files);
    _syncInput(key);
  } else {
    updateSlot(key, input.files[0].name);
  }
}

function handleDrop(event, key) {
  event.preventDefault();
  const dropped = event.dataTransfer.files;
  const input = document.getElementById(`input-${key}`);

  // 폴더 드롭 — DataTransferItem.webkitGetAsEntry()로 재귀 수집.
  // (dataTransfer.files 는 폴더를 0바이트 항목으로만 준다)
  const items = event.dataTransfer.items;
  if (input.multiple && items && items.length) {
    const entries = [];
    for (let i = 0; i < items.length; i++) {
      const en = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
      if (en) entries.push(en);
    }
    if (entries.some((en) => en.isDirectory)) {
      Promise.all(entries.map((en) => _readEntry(en, ''))).then((lists) => {
        const flat = [].concat.apply([], lists);
        if (!flat.length) return;
        _addFiles(key, flat.map((x) => x.file), flat.map((x) => x.rel));
        _syncInput(key);
      });
      return;
    }
  }

  if (!dropped.length) return;
  if (input.multiple) {
    _addFiles(key, dropped);
    _syncInput(key);
  } else {
    const dt = new DataTransfer();
    dt.items.add(dropped[0]);
    input.files = dt.files;
    updateSlot(key, dropped[0].name);
  }
}

function updateSlot(key, filename) {
  const zone = document.querySelector(`#slot-${key} .drop-zone`);
  const label = document.getElementById(`name-${key}`);
  label.textContent = filename;
  if (filename) zone.classList.add('has-file');
  else zone.classList.remove('has-file');
}

// ── 취소 ──────────────────────────────────────────────────────────────────

let _currentJobId = null;
let _currentEvtSource = null;
let _resultRetryTimer = null;

function _showCancelBtn(show) {
  const btn = document.getElementById('cancel-btn');
  if (btn) btn.style.display = show ? '' : 'none';
}

// 외부(멀티-레슨 처리 등)에서 현재 작업 상태를 공유하기 위한 setter.
window._tsSetCurrent = function (jobId, evtSource) {
  _currentJobId = jobId || null;
  _currentEvtSource = evtSource || null;
  _showCancelBtn(!!jobId);
};

// 멀티-레슨 루프가 사용자 취소를 감지할 수 있도록 노출하는 플래그.
window._tsCancelled = false;

async function cancelJob() {
  if (!_currentJobId) return;
  window._tsCancelled = true;
  const btn = document.getElementById('cancel-btn');
  if (btn) { btn.disabled = true; btn.textContent = '취소 중...'; }
  if (_currentEvtSource) { _currentEvtSource.close(); _currentEvtSource = null; }
  try {
    await fetch(`/api/cancel/${_currentJobId}`, { method: 'POST' });
  } catch (_) {}
  appendLog('[취소] 조판이 취소되었습니다.');
  _showCancelBtn(false);
  resetBtn();
  _currentJobId = null;
}

// ── 폼 제출 ──────────────────────────────────────────────────────────────

document.getElementById('typeset-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const form = e.target;
  const formData = new FormData(form);
  // 폴더째 업로드한 슬롯은 상대경로를 함께 보낸다 (input.files 순서와 1:1).
  // 서버가 이걸로 '폴더 = 원고 한 세트'를 복원한다 — 파일명만 보내면
  // 여러 폴더의 같은 이름 원고가 서로 덮어써져 침묵 유실된다.
  Object.keys(_relStore).forEach((k) => {
    const rels = _relStore[k] || [];
    if (rels.some((r) => r && r.indexOf('/') >= 0)) {
      formData.append(k + '_relpaths', JSON.stringify(rels));
    }
  });
  const runBtn = document.getElementById('run-btn');

  runBtn.disabled = true;
  runBtn.textContent = '실행 중...';

  // 이전 작업 정리
  if (_currentEvtSource) { _currentEvtSource.close(); _currentEvtSource = null; }
  if (_resultRetryTimer) { clearTimeout(_resultRetryTimer); _resultRetryTimer = null; }
  _currentJobId = null;
  window._tsCancelled = false;

  // 진행 영역 표시
  document.getElementById('progress-area').classList.remove('hidden');
  document.getElementById('result-area').classList.add('hidden');
  document.getElementById('result-area').innerHTML = '';
  document.getElementById('log-area').textContent = '';
  setStep(null);

  if (!materialId) {
    appendLog('[오류] 교재 ID를 찾을 수 없습니다. 페이지를 새로고침해주세요.');
    resetBtn();
    return;
  }

  // 폼에 _target_material 필드가 있으면 그걸 우선 사용 (워크북 세로버전 등 분기용)
  const overrideMaterial = (formData.get('_target_material') || '').toString().trim();
  const effectiveMaterial = overrideMaterial || materialId;

  try {
    const res = await fetch(`/api/run/${effectiveMaterial}`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      const errMsg = data.error || '서버 오류';
      appendLog(`[오류] ${errMsg}`);
      if (res.status === 401 || errMsg === 'unauthorized') {
        appendLog('세션이 만료되었습니다. 페이지를 새로고침합니다...');
        setTimeout(() => location.reload(), 1500);
      }
      resetBtn();
      return;
    }

    _currentJobId = data.job_id;
    _showCancelBtn(true);
    startStream(data.job_id);
  } catch (err) {
    appendLog(`[오류] ${err.message}`);
    resetBtn();
  }
});

// ── SSE 스트리밍 ──────────────────────────────────────────────────────────

function startStream(jobId) {
  const evtSource = new EventSource(`/api/stream/${jobId}`);
  _currentEvtSource = evtSource;

  evtSource.onmessage = (e) => {
    const msg = e.data;
    if (msg === '[DONE]') {
      evtSource.close();
      _currentEvtSource = null;
      _showCancelBtn(false);
      fetchResult(jobId);
      return;
    }
    if (msg === '[PING]') return;
    appendLog(msg);
    updateStepFromLog(msg);
  };

  evtSource.onerror = () => {
    evtSource.close();
    _currentEvtSource = null;
    _showCancelBtn(false);
    appendLog('[연결 끊김] 결과를 확인합니다...');
    fetchResult(jobId);
  };
}

// ── 단계 표시 업데이트 ────────────────────────────────────────────────────

function updateStepFromLog(msg) {
  if (msg.includes('[1/3]')) setStep('parse');
  else if (msg.includes('[2/3]')) setStep('typeset');
  else if (msg.includes('[3/3]')) setStep('verify');
}

function setStep(active) {
  ['parse', 'typeset', 'verify'].forEach(s => {
    const el = document.getElementById(`step-${s}`);
    el.classList.toggle('active', s === active);
    el.classList.toggle('done',
      (active === 'typeset' && s === 'parse') ||
      (active === 'verify' && (s === 'parse' || s === 'typeset'))
    );
  });
}

// ── 결과 카드 ─────────────────────────────────────────────────────────────

// W30 후속 — 세션 만료(401) 시 결과·게이트 경고 미전달 수리.
// 장시간 조판 중 로그인 세션(12시간 절대 만료)이 끝나면 /api/result 폴링이
// 401 {"error":"unauthorized"}를 받는데, 종전 코드는 이를 '결과 아직 없음'
// 으로 오분류해 20회 재시도 후 "알 수 없는 오류"만 표시했다 (실증: job
// 376b34d0 — 게이트 critical이 사용자에게 도달하지 못함). 수리: 401을
// 명시 감지해 재로그인 안내 카드를 띄우고, job_id를 localStorage에 보관 —
// 재로그인 후 같은 페이지로 돌아오면 자동으로 결과를 이어서 표시한다.
// (서버 결과는 인메모리 보관이므로 Flask 재시작 전까지 조회 가능. 라우트/
// 세션 정책은 무변경 — 보안 약화 없음.)
const PENDING_RESULT_KEY = 'ts_pending_result';

function _savePendingResult(jobId) {
  try {
    localStorage.setItem(PENDING_RESULT_KEY, JSON.stringify(
      { jobId: jobId, path: location.pathname, ts: Date.now() }));
  } catch (_) {}
}

function _clearPendingResult() {
  try { localStorage.removeItem(PENDING_RESULT_KEY); } catch (_) {}
}

function showSessionExpiredCard(jobId) {
  _savePendingResult(jobId);
  const area = document.getElementById('result-area');
  if (!area) return;
  area.classList.remove('hidden');
  area.innerHTML = `
    <div class="result-card warn">
      <div class="result-header">
        <span class="result-badge">🔒 세션 만료</span>
      </div>
      <p>로그인 세션이 만료되어 조판 결과를 표시하지 못했습니다.<br>
         결과와 검수 경고는 서버에 보관되어 있습니다 — 다시 로그인한 뒤
         이 페이지로 돌아오면 자동으로 표시됩니다.</p>
      <div class="action-row">
        <a href="/login" class="mockup-btn">🔑 다시 로그인</a>
      </div>
    </div>`;
}

async function fetchResult(jobId, retries) {
  if (retries === undefined) retries = 20;
  resetBtn();
  try {
    const res = await fetch(`/api/result/${jobId}`);
    if (res.status === 401) {
      // 세션 만료 — 재시도해도 영원히 401. 재로그인 안내 + 결과 보류.
      appendLog('[오류] 세션이 만료되어 결과를 가져오지 못했습니다. 다시 로그인하면 결과가 표시됩니다.');
      _showCancelBtn(false);
      showSessionExpiredCard(jobId);
      return;
    }
    const { status, result } = await res.json();
    if (res.status === 404) {
      // job 소멸 (서버 재시작 등) — 재시도 무의미.
      _clearPendingResult();
      showErrorCard('작업 결과를 찾을 수 없습니다 (서버가 재시작되었을 수 있습니다). 조판을 다시 실행해 주세요.');
      return;
    }

    // 아직 실행 중이면 재시도 (3초 간격)
    if ((status === 'pending' || status === 'running' || !result) && retries > 0) {
      appendLog('[대기] 작업 진행 중... 결과 확인 재시도');
      _resultRetryTimer = setTimeout(() => fetchResult(jobId, retries - 1), 3000);
      return;
    }

    if (status === 'error' || !result) {
      _clearPendingResult();
      showErrorCard(result?.error || '알 수 없는 오류');
      return;
    }
    _clearPendingResult();
    showResultCard(jobId, result);
  } catch (err) {
    if (retries > 0) {
      _resultRetryTimer = setTimeout(() => fetchResult(jobId, retries - 1), 3000);
      return;
    }
    showErrorCard(err.message);
  }
}

function showResultCard(jobId, result) {
  const area = document.getElementById('result-area');
  area.classList.remove('hidden');

  const ok = result.ok;
  const overflow = result.overflow ?? '?';
  const warnings = result.warnings || [];

  // 스토리 테이블
  let storyRows = '';
  for (const [key, v] of Object.entries(result.stories || {})) {
    const match = v.actual === v.expected;
    storyRows += `<tr class="${match ? '' : 'mismatch'}">
      <td>${key}</td>
      <td>${v.actual ?? '?'}</td>
      <td>${v.expected}</td>
      <td>${match ? '✓' : '✗'}</td>
    </tr>`;
  }

  // 경고 목록
  const warnHtml = warnings.length
    ? `<ul class="warn-list">${warnings.map(w => `<li>${w}</li>`).join('')}</ul>`
    : '';

  // AI 검수 에이전트 리포트 (W41 — opt-in 실행 시에만 존재)
  // 렌더는 공용 static/js/review_agent_ui.js (인라인 폴링 템플릿과 공유).
  const raHtml = window.ReviewAgentUI
    ? ReviewAgentUI.html(jobId, result.review_agent) : '';

  area.innerHTML = `
    <div class="result-card ${ok ? 'ok' : 'warn'}">
      <div class="result-header">
        <span class="result-badge">${ok ? '✅ 조판 완료' : '⚠️ 확인 필요'}</span>
        <span class="overflow-badge ${overflow > 0 ? 'bad' : ''}">오버플로우 ${overflow}개</span>
      </div>

      <table class="story-table">
        <thead><tr><th>섹션</th><th>수집</th><th>예상</th><th></th></tr></thead>
        <tbody>${storyRows}</tbody>
      </table>

      ${warnHtml}
      ${raHtml}

      ${result.mockup_file
        ? `<div class="action-row">
             <a href="http://localhost:8501?file=${encodeURIComponent(result.mockup_file)}"
                target="_blank" class="mockup-btn">🎨 목업에서 열기</a>
           </div>`
        : ''}
    </div>`;

  setStep('verify');
}

// ── AI 검수 에이전트 리포트 렌더 (W41) ────────────────────────────────────
// W41 후속: 렌더(_reviewAgentHtml)와 재조판(rerunJob)은 공용
// static/js/review_agent_ui.js로 이동 — 인라인 폴링 템플릿 19곳과 공유.
// 이 파일을 로드하는 템플릿은 review_agent_ui.js를 먼저 include한다.
// (rerunJob의 취소 버튼/현재 job 연동은 window._tsSetCurrent 경유.)

function showErrorCard(msg) {
  const area = document.getElementById('result-area');
  area.classList.remove('hidden');
  area.innerHTML = `<div class="result-card error"><p>❌ 오류: ${msg}</p></div>`;
}

// ── 유틸 ──────────────────────────────────────────────────────────────────

function appendLog(msg) {
  const pre = document.getElementById('log-area');
  pre.textContent += msg + '\n';
  pre.scrollTop = pre.scrollHeight;
}

function resetBtn() {
  const btn = document.getElementById('run-btn');
  btn.disabled = false;
  btn.innerHTML = '<span class="btn-icon">▶</span> 조판 실행';
}

// ── 세션 만료로 보류된 결과 자동 복원 (W30 후속) ──────────────────────────
// 폴링 401로 보류된 job_id가 이 페이지 것이면, 재로그인 후 돌아왔을 때
// 결과를 이어서 조회해 표시한다. 24시간 지난 항목은 폐기 (서버 인메모리
// 결과는 재시작 시 소멸 — 그 경우 fetchResult가 404 안내 후 정리한다).
(function resumePendingResult() {
  let entry = null;
  try {
    entry = JSON.parse(localStorage.getItem(PENDING_RESULT_KEY) || 'null');
  } catch (_) {}
  if (!entry || !entry.jobId || entry.path !== location.pathname) return;
  if (Date.now() - (entry.ts || 0) > 24 * 3600 * 1000) {
    _clearPendingResult();
    return;
  }
  const progress = document.getElementById('progress-area');
  if (progress) progress.classList.remove('hidden');
  appendLog(`[복원] 이전 조판 결과를 확인합니다... (job ${entry.jobId})`);
  fetchResult(entry.jobId);
})();
