chrome.action.onClicked.addListener(async (tab) => {
  await chrome.sidePanel.open({ tabId: tab.id });
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'analyzeHighlight') {
    const tabId = request.tabId;

    chrome.tabs.sendMessage(tabId, { action: 'getSelectedText' }, async (response) => {
      if (chrome.runtime.lastError) {
        sendResponse({ error: 'Could not get text. Refresh the page and try again.' });
        return;
      }

      const text = response.text;

      if (!text) {
        sendResponse({ error: 'No text selected. Highlight text on the page.' });
        return;
      }

      if (text.length > 1000) {
        sendResponse({ error: `Text too long (${text.length} chars). Highlight under 1000 characters.` });
        return;
      }

      try {
        const res = await fetch('http://localhost:8000/deconstruct', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text })
        });

        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const data = await res.json();
        sendResponse({ success: true, data: data });
      } catch (error) {
        sendResponse({ error: `Cannot connect to backend. Is it running?` });
      }
    });
    return true;
  }
});