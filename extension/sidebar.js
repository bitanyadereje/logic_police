// sidebar.js

async function getCurrentTabId() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0].id;
}

function renderResult(data) {
  const container = document.getElementById('content');

  // Verdict badge
  const verdictClass = data.valid ? 'valid' : 'invalid';
  const verdictIcon = data.valid ? '✓' : '✗';
  const verdictText = data.valid ? 'Valid' : 'Invalid';

  let html = `
    <div class="verdict-badge ${verdictClass}">
      <span class="icon">${verdictIcon}</span>
      ${verdictText}
    </div>
  `;

  // Premises
  html += `<div class="card"><div class="card-title"><span class="emoji">📋</span> Premises</div>`;
  if (data.premises && data.premises.length) {
    data.premises.forEach((p, idx) => {
      html += `<div class="premise-item"><span class="num">${idx+1}.</span> ${p}</div>`;
    });
  } else {
    html += `<div class="text-muted" style="padding:4px 0;">No premises extracted.</div>`;
  }
  html += `</div>`;

  // Conclusion
  html += `<div class="card"><div class="card-title"><span class="emoji">🎯</span> Conclusion</div>`;
  html += `<div class="conclusion-text">${data.conclusion || 'No conclusion identified.'}</div>`;
  html += `</div>`;

  // Formal Logic
  if (data.formal_premises && data.formal_premises.length) {
    const logicStr = data.formal_premises.join(', ') + ' ' + '⊢' + ' ' + data.formal_conclusion;
    html += `<div class="card"><div class="card-title"><span class="emoji">🔢</span> Formal Logic</div>`;
    html += `<div class="logic-box">${logicStr}</div>`;
    html += `</div>`;
  }

  // Hint
  html += `<div class="hint">💡 Re‑highlight and press <kbd>Ctrl+Shift+Y</kbd></div>`;

  container.innerHTML = html;
}

function renderError(msg) {
  const container = document.getElementById('content');
  container.innerHTML = `<div class="error">⚠️ ${msg}</div>`;
}

function renderLoading() {
  const container = document.getElementById('content');
  container.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      <span>Analyzing argument…</span>
    </div>
  `;
}

async function analyze() {
  renderLoading();
  try {
    const tabId = await getCurrentTabId();
    chrome.runtime.sendMessage({ action: 'analyzeHighlight', tabId: tabId }, (response) => {
      if (chrome.runtime.lastError) {
        renderError('Extension error. Reload the page and try again.');
        return;
      }
      if (response.error) {
        renderError(response.error);
        return;
      }
      if (response.success) {
        renderResult(response.data);
      } else {
        renderError('Unknown response from background.');
      }
    });
  } catch (e) {
    renderError('Error: ' + e.message);
  }
}

setTimeout(analyze, 200);