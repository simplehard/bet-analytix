// Clique no ícone da extensão: abre/fecha o painel na aba do Instagram.
const IG = /^https:\/\/www\.instagram\.com\//;

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.url || !IG.test(tab.url)) {
    const t = await chrome.tabs.create({ url: 'https://www.instagram.com/' });
    await chrome.storage.session.set({ openPanelOnTab: t.id });
    return;
  }
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'toggle' });
  } catch {
    // Aba aberta antes da instalação: injeta o script e tenta de novo.
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
    await chrome.tabs.sendMessage(tab.id, { type: 'toggle' });
  }
});

// Quando a aba do Instagram que abrimos termina de carregar, abre o painel.
chrome.tabs.onUpdated.addListener(async (tabId, info) => {
  if (info.status !== 'complete') return;
  const { openPanelOnTab } = await chrome.storage.session.get('openPanelOnTab');
  if (openPanelOnTab !== tabId) return;
  await chrome.storage.session.remove('openPanelOnTab');
  chrome.tabs.sendMessage(tabId, { type: 'open' }).catch(() => {});
});
