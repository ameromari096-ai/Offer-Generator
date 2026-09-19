# Auto-continue chat (no more clicking "continue" by hand)

`sourcing.html`'s agent chat card used to embed the Copilot Studio webchat
iframe directly. The agent's own search tool has a per-turn round limit, so
mid-search it pauses and asks the recruiter to reply "continue" to keep
going — and the iframe gave no way to do that automatically.

This replaces the iframe with a small custom chat client
(`js/agentChat.js`) that talks to the *same* Copilot Studio agent over
[Direct Line](https://learn.microsoft.com/azure/bot-service/rest-api/bot-framework-rest-direct-line-3-0-concepts)
instead of the embedded widget. It watches every bot reply for the
"reply/type/say continue" phrasing and automatically sends `continue` back
— up to 20 rounds — so a recruiter can paste a brief once and get the full
shortlist without babysitting the chat. A "Stop auto-continue" button lets
you take back manual control at any point, and a "Continue" button appears
whenever auto-continue is off or the 20-round safety cap is hit.

This needs one thing the manual iframe didn't: a Direct Line secret, which
must stay server-side (never in the browser), so it's exchanged for a
short-lived token by a small Netlify Function
(`netlify/functions/directlineToken.js`) — the same Netlify site already
hosting `generateShortlist`.

## 1. Get the agent's Direct Line secret

1. Open the agent in [Copilot Studio](https://copilotstudio.microsoft.com/).
2. Go to **Settings → Security → Web channel security** (the same page
   where "Require secured access" lives, from the earlier access-sharing
   work).
3. Under **Direct Line secrets**, copy one of the two secrets shown (click
   the eye icon to reveal it, then copy).
   - It's fine to leave **Require secured access** either on or off — this
     integration already goes through the secret → token exchange, which is
     the secure path either way.

## 2. Add it to Netlify

1. Go to the same Netlify site used for `generateShortlist`
   (`harmonious-kataifi-f271a2.netlify.app`) → **Site configuration →
   Environment variables**.
2. Add `DIRECTLINE_SECRET` with the value copied above.
3. **Deploys → Trigger deploy → Deploy site** once so the function picks up
   the new variable.

That's it — no change needed on the Copilot Studio side beyond copying the
secret; the agent's instructions, tools, and "No authentication" setting
all stay exactly as they are.

## How it decides when to auto-continue

`js/agentChat.js` checks every bot message against a pattern that matches
things like *"Reply 'continue' to keep searching"*, *"Type continue to
proceed"*, or *"Would you like me to continue?"* — not just the bare word
"continue" anywhere in the text, so it won't misfire on a sentence that
merely mentions it in passing. When it matches:

- If auto-continue is still on and under the 20-round cap, it waits ~0.7s
  (so replies don't look instantaneous/bot-like) and sends `continue`
  automatically, updating the status line with the round count.
- If you've clicked **Stop auto-continue**, or the 20-round cap is hit, it
  instead shows a **Continue** button so you can keep going manually.

20 rounds and a ~1.2s poll interval are hardcoded in `js/agentChat.js`
(`MAX_AUTO_CONTINUES`, `POLL_INTERVAL_MS`) if you ever want to tune them.

## Troubleshooting

- **"Could not get a chat token (HTTP 500)"** — `DIRECTLINE_SECRET` isn't
  set on Netlify yet, or the deploy that picks it up hasn't run.
- **"Direct Line rejected the secret" / HTTP 401-403** — the secret was
  copied wrong, or was rotated in Copilot Studio after you copied it (the
  "Direct Line secrets" page lets you regenerate either one — copy the
  current value again).
- **Chat connects but the agent never replies** — check the agent is still
  **Published** in Copilot Studio; an unpublished draft doesn't answer
  Direct Line conversations even if the webchat used to work.

## Rollback

If this ever needs to go back to the plain embedded iframe, it's the
`copilot-embed` markup/CSS this replaced — see git history for
`sourcing.html` and `styles.css` around the commit that introduced this
file.
