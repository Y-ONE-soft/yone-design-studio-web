/* typeset.js — 파일 업로드 + SSE 실시간 로그 + 결과 카드 */

const materialId = (document.currentScript && document.currentScript.dataset.material)
  || document.querySelector('script[data-material]')?.dataset.material
  || '';

// ── 파일 선택/드롭 (multiple input 누적 지원) ─────────────────────────────

// 슬롯별 누적 파일 저장소 (브라우저가 input.files를 매번 교체하므로 별도 보관)
const _fileStore = {};

function _getStore(key) {
  if (!_fileStore[key]) _fileStore[key] = new DataTransfer();
  return _fileStore[key];
}

function _addFiles(key, fileList) {
  const store = _getStore(key);
  const existing = new Set();
  for (let i = 0; i < store.files.length; i++) {
    existing.add(store.files[i].name + '|' + store.files[i].size);
  }
  for (let i = 0; i < fileList.length; i++) {
    const id = fileList[i].name + '|' + fileList[i].size;
    if (!existing.has(id)) {
      store.items.add(fileList[i]);
      existing.add(id);
    }
  }
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
      listEl.innerHTML = Array.from(store.files).map((f, i) =>
        `<div class="file-list-item">
          <span class="file-list-name">${f.name}</span>
          <button type="button" class="file-list-del" onclick="removeFile('${key}', ${i})" title="삭제">✕</button>
        </div>`
      ).join('');
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
  const newDt = new DataTransfer();
  files.forEach((f, i) => { if (i !== idx) newDt.items.add(f); });
  _fileStore[key] = newDt;
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
  if (!dropped.length) return;
  const input = document.getElementById(`input-${key}`);
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

async function fetchResult(jobId, retries) {
  if (retries === undefined) retries = 20;
  resetBtn();
  try {
    const res = await fetch(`/api/result/${jobId}`);
    const { status, result } = await res.json();

    // 아직 실행 중이면 재시도 (3초 간격)
    if ((status === 'pending' || status === 'running' || !result) && retries > 0) {
      appendLog('[대기] 작업 진행 중... 결과 확인 재시도');
      _resultRetryTimer = setTimeout(() => fetchResult(jobId, retries - 1), 3000);
      return;
    }

    if (status === 'error' || !result) {
      showErrorCard(result?.error || '알 수 없는 오류');
      return;
    }
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

      ${result.mockup_file
        ? `<div class="action-row">
             <a href="http://localhost:8501?file=${encodeURIComponent(result.mockup_file)}"
                target="_blank" class="mockup-btn">🎨 목업에서 열기</a>
           </div>`
        : ''}
    </div>`;

  setStep('verify');
}

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
