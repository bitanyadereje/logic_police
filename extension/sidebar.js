// sidebar.js

async function getCurrentTabId() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0].id;
}

function renderResult(container, data) {
  let html = '<div class="result">';

  // Premises
  html += '<div style="font-weight:600;font-size:14px;margin-bottom:6px;">📋 Premises</div>';
  if (data.premises && data.premises.length) {
    data.premises.forEach(p => {
      html += `<div class="premise">• ${p}</div>`;
    });
  } else {
    html += `<div style="color:#6b7280;font-size:13px;">No premises found</div>`;
  }

  // Conclusion
  html += '<div class="conclusion">🎯 Conclusion</div>';
  html += `<div style="padding:6px 0;border-bottom:none;">• ${data.conclusion}</div>`;

  // Formal logic
  if (data.formal_premises && data.formal_premises.length) {
    html += '<div class="formal">';
    html += `<div>Formal: ${data.formal_premises.join(', ')} ⊢ ${data.formal_conclusion}</div>`;
    html += '</div>';
  }

  // Validity badge
  const badgeClass = data.valid ? 'badge-valid' : 'badge-invalid';
  const badgeText = data.valid ? '✅ VALID' : '❌ INVALID';
  html += `<div class="badge ${badgeClass}">${badgeText}</div>`;

  html += '</div>';
  html += `<div class="status" style="margin-top:12px;">💡 Re-highlight and press <kbd>Ctrl+Shift+Y</kbd></div>`;
  container.innerHTML = html;
}

function renderError(container, message) {
  container.innerHTML = `<div class="error">❌ ${message}</div>`;
}

function renderLoading(container) {
  container.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      <span>Analyzing...</span>
    </div>
  `;
}

async function analyzeHighlight() {
  const content = document.getElementById('content');
  renderLoading(content);

  try {
    const tabId = await getCurrentTabId();
    chrome.runtime.sendMessage({ action: 'analyzeHighlight', tabId: tabId }, (response) => {
      if (chrome.runtime.lastError) {
        renderError(content, 'Extension error');
        return;
      }
      if (response.error) renderError(content, response.error);
      else if (response.success) renderResult(content, response.data);
      else renderError(content, 'Unknown error.');
    });
  } catch (error) {
    renderError(content, 'Error: ' + error.message);
  }
}

setTimeout(analyzeHighlight, 100);