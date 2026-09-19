// Mints a short-lived Direct Line token for the Candidate Sourcing Agent's
// auto-continue chat client (js/agentChat.js), so the long-lived Direct Line
// secret never reaches the browser.
//
// Set DIRECTLINE_SECRET in the Netlify dashboard (Site configuration ->
// Environment variables) to the secret from the agent's Copilot Studio
// Settings -> Security -> Web channel security page (see
// docs/directline-auto-continue.md), then Deploys -> Trigger deploy ->
// Deploy site once to pick it up.
//
// Direct Line's global endpoint (directline.botframework.com) is supposed to
// route to the nearest datacenter, but a bot registered in a specific
// geography can come back with a "ResourceNotFound: Site missing" error from
// the global endpoint while working fine on its actual regional one. Rather
// than guess, try every documented regional endpoint and use whichever one
// actually recognizes this bot's secret.
const DIRECTLINE_SECRET = process.env.DIRECTLINE_SECRET;

// '' = global (directline.botframework.com); tried first since most bots use it.
const REGIONS = ['', 'europe', 'asia', 'northamerica', 'india'];

function directLineBase(region) {
  return region
    ? `https://${region}.directline.botframework.com/v3/directline`
    : 'https://directline.botframework.com/v3/directline';
}

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

  const attempts = [];

  for (const region of REGIONS) {
    let res;
    try {
      res = await fetch(`${directLineBase(region)}/tokens/generate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${DIRECTLINE_SECRET}` }
      });
    } catch (e) {
      attempts.push({ region: region || 'global', error: `network error: ${e.message}` });
      continue;
    }

    let data;
    try {
      data = await res.json();
    } catch (e) {
      attempts.push({ region: region || 'global', error: 'non-JSON response' });
      continue;
    }

    if (res.ok) {
      return json(200, { token: data.token, expires_in: data.expires_in, region });
    }

    attempts.push({ region: region || 'global', status: res.status, error: data && data.error && data.error.message });
  }

  return json(502, {
    error:
      'Direct Line rejected the secret on every known regional endpoint (global, europe, asia, northamerica, india). ' +
      'This usually means this Copilot Studio agent has no classic Direct Line channel/site registered at all, ' +
      'rather than a wrong region or a typo\'d secret.',
    attempts
  });
};
