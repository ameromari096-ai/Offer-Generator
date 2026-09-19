// Mints a short-lived Direct Line token for the Candidate Sourcing Agent's
// auto-continue chat client (js/agentChat.js), so the long-lived Direct Line
// secret never reaches the browser.
//
// Set DIRECTLINE_SECRET in the Netlify dashboard (Site configuration ->
// Environment variables) to the secret from the agent's Copilot Studio
// Channels -> Direct Line page (see docs/directline-auto-continue.md), then
// Deploys -> Trigger deploy -> Deploy site once to pick it up.
const DIRECTLINE_SECRET = process.env.DIRECTLINE_SECRET;

function json(statusCode, payload) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  };
}

exports.handler = async function (event) {
  if (event.httpMethod !== 'POST' && event.httpMethod !== 'GET') {
    return json(405, { error: 'Use POST.' });
  }

  if (!DIRECTLINE_SECRET) {
    return json(500, { error: 'DIRECTLINE_SECRET is not configured on this Netlify site yet.' });
  }

  let res;
  try {
    res = await fetch('https://directline.botframework.com/v3/directline/tokens/generate', {
      method: 'POST',
      headers: { Authorization: `Bearer ${DIRECTLINE_SECRET}` }
    });
  } catch (e) {
    return json(502, { error: `Could not reach Direct Line: ${e.message}` });
  }

  let data;
  try {
    data = await res.json();
  } catch (e) {
    return json(502, { error: 'Direct Line returned a non-JSON response.' });
  }

  if (!res.ok) {
    return json(res.status, { error: 'Direct Line rejected the secret.', details: data });
  }

  return json(200, { token: data.token, expires_in: data.expires_in });
};
