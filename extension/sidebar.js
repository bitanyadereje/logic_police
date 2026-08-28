/**
 * Logic Pollice — sidebar.js
 * Handles state rendering, analysis, animations, dark mode, and clipboard.
 */

(function () {
  'use strict';

  const PREMISE_COLLAPSE_THRESHOLD = 5;

  const els = {
    main: document.getElementById('main'),
    loading: document.getElementById('loadingState'),
    error: document.getElementById('errorState'),
    empty: document.getElementById('emptyState'),
    result: document.getElementById('resultState'),

    errorMessage: document.getElementById('errorMessage'),
    retryBtn: document.getElementById('retryBtn'),

    seal: document.getElementById('seal'),
    sealMark: document.getElementById('sealMark'),
    verdictLabel: document.getElementById('verdictLabel'),
    verdictSub: document.getElementById('verdictSub'),
    whyTrigger: document.getElementById('whyTrigger'),
    tooltip: document.getElementById('tooltip'),

    premiseCount: document.getElementById('premiseCount'),
    premiseList: document.getElementById('premiseList'),
    collapseToggle: document.getElementById('collapseToggle'),

    conclusionText: document.getElementById('conclusionText'),

    formalLine: document.getElementById('formalLine'),
    copyBtn: document.getElementById('copyBtn'),
    copyIcon: document.getElementById('copyIcon'),
    copyLabel: document.getElementById('copyLabel'),

    themeToggle: document.getElementById('themeToggle'),
  };

  const ALL_STATES = [els.loading, els.error, els.empty, els.result];

  function showState(el) {
    ALL_STATES.forEach((s) => s.classList.toggle('hidden', s !== el));
  }

  // ----------------------------------------------------------------
  // Dark mode
  // ----------------------------------------------------------------
  let darkMode = false;

  function applyTheme() {
    document.body.classList.toggle('dark', darkMode);
    els.themeToggle.setAttribute('aria-pressed', String(darkMode));
  }

  function initTheme() {
    try {
      if (window.chrome && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(['logicPolliceDark'], (res) => {
          darkMode = !!res.logicPolliceDark;
          applyTheme();
        });
        return;
      }
    } catch (e) { /* no-op */ }
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    darkMode = !!prefersDark;
    applyTheme();
  }

  els.themeToggle.addEventListener('click', () => {
    darkMode = !darkMode;
    applyTheme();
    try {
      if (window.chrome && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ logicPolliceDark: darkMode });
      }
    } catch (e) { /* no-op */ }
  });

  // ----------------------------------------------------------------
  // Rendering functions
  // ----------------------------------------------------------------
  function renderLoading() {
    showState(els.loading);
  }

  function renderEmpty() {
    showState(els.empty);
  }

  function renderError(message) {
    els.errorMessage.textContent = message || 'The extraction step didn\u2019t return a usable set of premises.';
    showState(els.error);
  }

  function whyText(valid, premiseCount) {
    if (valid) {
      return premiseCount <= 2
        ? 'The conclusion follows necessarily from the premises \u2014 a classic two-premise syllogism.'
        : 'Each premise chains into the next, and the conclusion follows necessarily from the full set.';
    }
    return 'The conclusion doesn\u2019t follow necessarily from the premises as stated \u2014 check for an unstated assumption or a shift in terms.';
  }

  function renderResult(data) {
    const {
      premises = [],
      conclusion = '',
      formal_premises = [],
      formal_conclusion = '',
      valid = false,
    } = data;

    // Verdict seal
    els.seal.classList.remove('stamp-in', 'valid', 'invalid');
    void els.seal.offsetWidth;
    els.seal.classList.add(valid ? 'valid' : 'invalid');
    els.sealMark.textContent = valid ? '\u2713' : '\u2717';

    els.verdictLabel.textContent = valid ? 'Valid' : 'Invalid';
    els.verdictLabel.className = 'label ' + (valid ? 'valid' : 'invalid');
    els.verdictSub.textContent = valid
      ? 'The argument holds together.'
      : 'The argument doesn\u2019t hold together.';

    requestAnimationFrame(() => els.seal.classList.add('stamp-in'));

    els.tooltip.textContent = whyText(valid, premises.length);
    els.tooltip.classList.remove('open');

    // Premises
    els.premiseCount.textContent = String(premises.length);
    els.premiseList.innerHTML = '';
    els.premiseList.classList.toggle('collapsed', premises.length > PREMISE_COLLAPSE_THRESHOLD);
    els.collapseToggle.classList.toggle('hidden', premises.length <= PREMISE_COLLAPSE_THRESHOLD);
    els.collapseToggle.textContent = 'expand';
    els.collapseToggle.dataset.expanded = 'false';

    premises.forEach((p, i) => {
      const li = document.createElement('li');
      const num = document.createElement('span');
      num.className = 'num';
      num.textContent = String(i + 1).padStart(2, '0');
      const txt = document.createElement('span');
      txt.textContent = p;
      li.appendChild(num);
      li.appendChild(txt);
      li.style.animationDelay = (i * 70) + 'ms';
      els.premiseList.appendChild(li);
      requestAnimationFrame(() => li.classList.add('fade-in'));
    });

    // Conclusion
    els.conclusionText.textContent = conclusion;

    // Formal logic line
    els.formalLine.innerHTML = '';
    formal_premises.forEach((fp) => {
      const span = document.createElement('span');
      span.className = 'premise-token';
      span.textContent = fp;
      els.formalLine.appendChild(span);
    });
    const turnstile = document.createElement('span');
    turnstile.className = 'turnstile';
    turnstile.textContent = '\u22A2';
    els.formalLine.appendChild(turnstile);
    const concl = document.createElement('span');
    concl.textContent = formal_conclusion;
    els.formalLine.appendChild(concl);

    els.copyBtn.classList.remove('copied');
    els.copyIcon.textContent = '\u29C9';
    els.copyLabel.textContent = 'Copy';
    els.copyBtn.dataset.payload = formal_premises.join(', ') + ' \u22A2 ' + formal_conclusion;

    showState(els.result);
  }

  // ----------------------------------------------------------------
  // Interactions
  // ----------------------------------------------------------------
  els.whyTrigger.addEventListener('click', () => {
    els.tooltip.classList.toggle('open');
  });

  els.collapseToggle.addEventListener('click', () => {
    const expanded = els.collapseToggle.dataset.expanded === 'true';
    els.premiseList.classList.toggle('collapsed', expanded);
    els.collapseToggle.textContent = expanded ? 'expand' : 'collapse';
    els.collapseToggle.dataset.expanded = String(!expanded);
  });

  els.copyBtn.addEventListener('click', async () => {
    const payload = els.copyBtn.dataset.payload || '';
    try {
      await navigator.clipboard.writeText(payload);
      els.copyBtn.classList.add('copied');
      els.copyIcon.textContent = '\u2713';
      els.copyLabel.textContent = 'Copied';
      setTimeout(() => {
        els.copyBtn.classList.remove('copied');
        els.copyIcon.textContent = '\u29C9';
        els.copyLabel.textContent = 'Copy';
      }, 1600);
    } catch (e) {
      els.copyLabel.textContent = 'Copy failed';
    }
  });

  els.retryBtn.addEventListener('click', () => {
    if (window.LogicPollice && typeof window.LogicPollice.analyze === 'function') {
      window.LogicPollice.analyze();
    } else {
      renderEmpty();
    }
  });

  // ----------------------------------------------------------------
  // ANALYSIS ENGINE (the missing part)
  // ----------------------------------------------------------------
  async function getCurrentTabId() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0].id;
  }

  async function analyze() {
    renderLoading();
    try {
      const tabId = await getCurrentTabId();
      chrome.runtime.sendMessage({ action: 'analyzeHighlight', tabId: tabId }, (response) => {
        if (chrome.runtime.lastError) {
          renderError('Extension error: ' + chrome.runtime.lastError.message);
          return;
        }
        if (response.error) {
          renderError(response.error);
        } else if (response.success) {
          renderResult(response.data);
        } else {
          renderError('Unknown response from background.');
        }
      });
    } catch (e) {
      renderError('Error: ' + e.message);
    }
  }

  // ----------------------------------------------------------------
  // Public API
  // ----------------------------------------------------------------
  window.LogicPollice = window.LogicPollice || {};
  window.LogicPollice.showLoading = renderLoading;
  window.LogicPollice.showEmpty = renderEmpty;
  window.LogicPollice.showError = renderError;
  window.LogicPollice.showResult = renderResult;
  window.LogicPollice.analyze = analyze;
  window.LogicPollice.onRetry = analyze;

  // ----------------------------------------------------------------
  // Init
  // ----------------------------------------------------------------
  initTheme();
  renderEmpty();

  // Auto‑analyze on sidebar load
  setTimeout(analyze, 200);

  // ----------------------------------------------------------------
  // Optional: listen for messages from background (if you ever send them)
  // ----------------------------------------------------------------
  try {
    if (window.chrome && chrome.runtime && chrome.runtime.onMessage) {
      chrome.runtime.onMessage.addListener((message) => {
        if (!message || !message.type) return;
        if (message.type === 'LOGIC_POLLICE_LOADING') renderLoading();
        if (message.type === 'LOGIC_POLLICE_ERROR') renderError(message.error);
        if (message.type === 'LOGIC_POLLICE_RESULT') renderResult(message.data);
      });
    }
  } catch (e) { /* not in extension context */ }

})();