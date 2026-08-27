function sanitizeText(text) {
    return text
        .replace(/\s+/g, ' ')
        .replace(/[^\w\s.,!?'-]/g, '')
        .trim();
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getSelectedText') {
    const selection = window.getSelection();
    const rawText = selection.toString();
    
    if (!rawText) {
      sendResponse({ text: '' });
      return;
    }

    const cleanText = sanitizeText(rawText);
    sendResponse({ text: cleanText });
  }
  return true;
});