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

// Mensagens do monitor (vindas do content script).
chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === 'badge') {
    chrome.action.setBadgeBackgroundColor({ color: '#e1306c' });
    chrome.action.setBadgeText({ text: msg.count ? String(msg.count) : '' });
  }
  if (msg?.type === 'notify') {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: msg.title,
      message: msg.message,
      priority: 1,
    });
  }
});

// Clique na notificação: abre a aba "Monitorar" no Instagram.
chrome.notifications.onClicked.addListener(async (id) => {
  chrome.notifications.clear(id);
  const [tab] = await chrome.tabs.query({ url: 'https://www.instagram.com/*' });
  if (!tab) return chrome.tabs.create({ url: 'https://www.instagram.com/' });
  await chrome.tabs.update(tab.id, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
  chrome.tabs.sendMessage(tab.id, { type: 'openMonitor' }).catch(() => {});
});
