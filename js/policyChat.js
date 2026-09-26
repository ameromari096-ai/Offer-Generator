// TA Policy Assistant: renders the Copilot Studio agent with Bot Framework Web
// Chat (instead of the stock iframe) so the page can see when a question is
// waiting on an answer and show a "thinking" indicator the stock canvas lacks.
// If Web Chat or the agent's token endpoint can't be reached, it falls back to
// the stock iframe.
(function () {
  'use strict';

  var TOKEN_URL = 'https://default6609531482d748e8be7c967c923aa1.dd.environment.api.powerplatform.com' +
    '/powervirtualagents/botsbyschema/cr30a_ph-talentacquisitionpolicy_I0Z6tQ/directline/token' +
    '?api-version=2022-03-01-preview';
  var FALLBACK_IFRAME_URL = 'https://copilotstudio.microsoft.com/environments/Default-66095314-82d7-48e8-be7c-967c923aa1dd' +
    '/bots/cr30a_ph-talentacquisitionpolicy_I0Z6tQ/webchat?__version__=2&enableFileAttachment=false&cliAgent=true';

  var SLOW_MS = 15000;      // after this, reassure the user it's still working
  var VERY_SLOW_MS = 90000; // after this, suggest retrying

  var container = document.getElementById('policyChat');
  var webchatEl = document.getElementById('webchat');
  var statusEl = document.getElementById('chatStatus');
  var thinkingEl = document.getElementById('thinkingIndicator');
  var thinkingText = document.getElementById('thinkingText');

  var slowTimer = null;
  var verySlowTimer = null;

  function clearTimers() {
    clearTimeout(slowTimer);
    clearTimeout(verySlowTimer);
  }

  function showThinking() {
    clearTimers();
    thinkingText.textContent = 'The agent is thinking';
    thinkingEl.classList.remove('hidden');
    slowTimer = setTimeout(function () {
      thinkingText.textContent = 'Still working on it — policy lookups can take a little while';
    }, SLOW_MS);
    verySlowTimer = setTimeout(function () {
      thinkingText.textContent = 'This is taking longer than usual — you can wait, or ask again';
    }, VERY_SLOW_MS);
  }

  function hideThinking() {
    clearTimers();
    thinkingEl.classList.add('hidden');
  }

  function fallBackToIframe(reason) {
    if (window.console) console.warn('TA Policy chat: falling back to the stock iframe —', reason);
    hideThinking();
    statusEl.classList.add('hidden');
    webchatEl.classList.add('hidden');
    var iframe = document.createElement('iframe');
    iframe.className = 'policy-chat__frame';
    iframe.title = 'Talent Acquisition Policy Agent chat';
    iframe.src = FALLBACK_IFRAME_URL;
    container.appendChild(iframe);
  }

  function fetchJson(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error(url + ' returned HTTP ' + res.status);
      return res.json();
    });
  }

  function start() {
    if (!window.WebChat) {
      fallBackToIframe('Web Chat script did not load');
      return;
    }

    var environmentEndpoint = TOKEN_URL.slice(0, TOKEN_URL.indexOf('/powervirtualagents'));
    var apiVersion = TOKEN_URL.slice(TOKEN_URL.indexOf('api-version')).split('=')[1];
    var regionalSettingsUrl = environmentEndpoint +
      '/powervirtualagents/regionalchannelsettings?api-version=' + apiVersion;

    Promise.all([fetchJson(regionalSettingsUrl), fetchJson(TOKEN_URL)])
      .then(function (results) {
        var directLineUrl = results[0].channelUrlsById.directline;
        var token = results[1].token;
        if (!directLineUrl || !token) throw new Error('missing Direct Line URL or token');

        var directLine = window.WebChat.createDirectLine({
          domain: directLineUrl + 'v3/directline',
          token: token
        });

        var store = window.WebChat.createStore({}, function (api) {
          return function (next) {
            return function (action) {
              var activity = action.payload && action.payload.activity;

              if (action.type === 'DIRECT_LINE/CONNECT_FULFILLED') {
                statusEl.classList.add('hidden');
                // Ask the agent for its greeting, as Copilot Studio's own canvas does.
                api.dispatch({
                  type: 'DIRECT_LINE/POST_ACTIVITY',
                  meta: { method: 'keyboard' },
                  payload: {
                    activity: { type: 'event', name: 'startConversation', channelData: { postBack: true } }
                  }
                });
              } else if (action.type === 'DIRECT_LINE/POST_ACTIVITY' && activity && activity.type === 'message') {
                showThinking();
              } else if (action.type === 'DIRECT_LINE/POST_ACTIVITY_REJECTED') {
                hideThinking();
              } else if (action.type === 'DIRECT_LINE/INCOMING_ACTIVITY' && activity &&
                         activity.type === 'message' && activity.from && activity.from.role === 'bot') {
                hideThinking();
              }

              return next(action);
            };
          };
        });

        window.WebChat.renderWebChat({
          directLine: directLine,
          store: store,
          locale: 'en-US',
          styleOptions: {
            accent: '#175a70',
            primaryFont: '"Segoe UI", Arial, sans-serif',
            bubbleBorderRadius: 10,
            bubbleFromUserBackground: '#175a70',
            bubbleFromUserTextColor: '#ffffff',
            bubbleFromUserBorderRadius: 10,
            hideUploadButton: true,
            sendBoxButtonColor: '#175a70',
            typingAnimationDuration: 60000
          }
        }, webchatEl);
      })
      .catch(function (err) {
        fallBackToIframe(err && err.message ? err.message : err);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
