chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getSelectedText') {
    const selection = window.getSelection();
    const text = selection.toString().trim();
    sendResponse({ text: text });
  }
  return true;
});