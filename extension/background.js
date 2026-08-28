chrome.action.onClicked.addListener(async (tab) => {
  await chrome.sidePanel.open({ tabId: tab.id });
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'analyzeHighlight') {
    chrome.tabs.sendMessage(request.tabId, { action: 'getSelectedText' }, (response) => {
      if (chrome.runtime.lastError || !response.text) {
        sendResponse({ error: 'No text selected. Refresh the page.' });
        return;
      }
      const text = response.text;
      // --- INCREASED LIMIT to 15000 chars ---
      if (text.length > 15000) {
        sendResponse({ error: `Text too long (${text.length} chars). Max is 15000.` });
        return;
      }
      fetch('http://localhost:8000/deconstruct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data: data }))
      .catch(err => sendResponse({ error: 'Backend not running.' }));
    });
    return true;
  }
});