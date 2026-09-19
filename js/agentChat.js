// Drives the PureHealth Copilot Studio Candidate Sourcing Agent over Direct
// Line (rather than the embedded webchat iframe), so this client can detect
// the agent's "reply continue to keep searching" prompt and resend
// "continue" automatically instead of the recruiter clicking through it by
// hand round after round. See docs/directline-auto-continue.md for the
// one-time Copilot Studio + Netlify setup this needs.
(function () {
  const el = (id) => document.getElementById(id);
  const escapeHtml = (window.PH && window.PH.templates && window.PH.templates.escapeHtml) || ((s) => String(s || ''));

  const TOKEN_ENDPOINT = 'https://harmonious-kataifi-f271a2.netlify.app/.netlify/functions/directlineToken';
  const DL_BASE = 'https://directline.botframework.com/v3/directline';
  const MAX_AUTO_CONTINUES = 20;
  const POLL_INTERVAL_MS = 1200;
  // Matches the phrasing the agent's own instructions use when it pauses
  // mid-search ("Reply 'continue' to keep searching", "Would you like me to
  // continue?", "Type continue to proceed", etc.) without over-matching a
  // sentence that merely mentions the word "continue" in passing.
  const CONTINUE_PATTERN = /\b(reply|type|say|send)\b[^.?!\n]{0,25}\bcontinue\b|\bcontinue\?\s*$|\bwould you like\b[^.?!\n]{0,50}\bcontinue\b/i;

  const state = {
    conversationId: null,
    token: null,
    watermark: null,
    userId: 'sourcing-web-' + Math.random().toString(36).slice(2, 10),
    autoContinueCount: 0,
    autoContinueEnabled: true,
    connected: false,
    connecting: false,
    polling: false,
    seenActivityIds: new Set()
  };

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function linkify(escapedText) {
    return escapedText.replace(
      /(https?:\/\/[^\s<]+)/g,
      (url) => `<a href="${url}" target="_blank" rel="noopener">${url}</a>`
    );
  }

  function addMessage(text, who) {
    const log = el('agentChatLog');
    const row = document.createElement('div');
    row.className = `chat-msg chat-msg--${who}`;
    row.innerHTML = linkify(escapeHtml(text)).replace(/\n/g, '<br>');
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function setStatus(text) {
    el('agentChatStatus').textContent = text || '';
  }

  function showManualContinue(show) {
    el('agentChatContinueBtn').classList.toggle('hidden', !show);
  }

  function showStopAuto(show) {
    el('agentChatStopAutoBtn').classList.toggle('hidden', !show);
  }

  async function fetchToken() {
    const res = await fetch(TOKEN_ENDPOINT, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `Could not get a chat token (HTTP ${res.status}).`);
    }
    return data.token;
  }

  async function connect() {
    if (state.connected || state.connecting) return;
    state.connecting = true;
    setStatus('Connecting to the sourcing agent...');
    try {
      state.token = await fetchToken();
      const res = await fetch(`${DL_BASE}/conversations`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${state.token}` }
      });
      if (!res.ok) throw new Error(`Direct Line rejected the conversation request (HTTP ${res.status}).`);
      const data = await res.json();
      state.conversationId = data.conversationId;
      state.connected = true;
      setStatus('');
      pollActivities();
    } catch (e) {
      setStatus(`Could not connect: ${e.message}`);
    } finally {
      state.connecting = false;
    }
  }

  async function sendActivity(text) {
    if (!state.connected) await connect();
    if (!state.connected) return;
    addMessage(text, 'user');
    try {
      await fetch(`${DL_BASE}/conversations/${state.conversationId}/activities`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${state.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'message', from: { id: state.userId }, text })
      });
    } catch (e) {
      setStatus(`Message failed to send: ${e.message}`);
    }
  }

  async function pollActivities() {
    if (state.polling) return;
    state.polling = true;
    while (state.connected) {
      try {
        const url =
          `${DL_BASE}/conversations/${state.conversationId}/activities` +
          (state.watermark ? `?watermark=${encodeURIComponent(state.watermark)}` : '');
        const res = await fetch(url, { headers: { Authorization: `Bearer ${state.token}` } });
        if (res.ok) {
          const data = await res.json();
          if (data.watermark) state.watermark = data.watermark;
          (data.activities || []).forEach((activity) => {
            if (activity.from && activity.from.id === state.userId) return;
            if (state.seenActivityIds.has(activity.id)) return;
            state.seenActivityIds.add(activity.id);
            if (activity.type === 'message' && activity.text) {
              handleBotMessage(activity.text);
            }
          });
        }
      } catch (e) {
        // Transient network hiccups are expected on a long-polling loop; keep retrying silently.
      }
      await sleep(POLL_INTERVAL_MS);
    }
    state.polling = false;
  }

  function handleBotMessage(text) {
    addMessage(text, 'bot');
    showManualContinue(false);

    if (!CONTINUE_PATTERN.test(text)) {
      setStatus('');
      showStopAuto(false);
      return;
    }

    if (!state.autoContinueEnabled) {
      setStatus('Auto-continue is stopped. Click "Continue" to keep going manually.');
      showManualContinue(true);
      return;
    }

    if (state.autoContinueCount >= MAX_AUTO_CONTINUES) {
      setStatus(`Stopped after ${MAX_AUTO_CONTINUES} automatic continues (safety limit) — click "Continue" to keep going.`);
      showManualContinue(true);
      showStopAuto(false);
      return;
    }

    state.autoContinueCount += 1;
    setStatus(`Auto-continuing search... (round ${state.autoContinueCount} of ${MAX_AUTO_CONTINUES})`);
    showStopAuto(true);
    setTimeout(() => sendActivity('continue'), 700);
  }

  el('agentChatSendBtn').addEventListener('click', () => {
    const input = el('agentChatInput');
    const text = input.value.trim();
    if (!text) return;
    state.autoContinueCount = 0;
    state.autoContinueEnabled = true;
    sendActivity(text);
    input.value = '';
  });

  el('agentChatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      el('agentChatSendBtn').click();
    }
  });

  el('agentChatContinueBtn').addEventListener('click', () => {
    showManualContinue(false);
    sendActivity('continue');
  });

  el('agentChatStopAutoBtn').addEventListener('click', () => {
    state.autoContinueEnabled = false;
    showStopAuto(false);
    setStatus('Auto-continue stopped. The agent will wait for you to click "Continue".');
  });
})();
