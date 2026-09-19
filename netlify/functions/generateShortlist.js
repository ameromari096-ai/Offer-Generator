// HTTP endpoint for the Candidate Sourcing Agent's Copilot Studio integration,
// deployed as a Netlify Function (see docs/copilot-studio-integration.md).
// Reuses js/sourcingExcel.js unchanged (it already supports being `require`d
// as a CommonJS module) so the validation rules and the .xlsx layout are
// identical to the ones sourcing.html uses in the browser.
// A literal relative path (not path.join(__dirname, ...)) so Netlify's
// function bundler can statically detect and package this dependency.
global.XLSX = require('xlsx');
const sourcingExcel = require('../../js/sourcingExcel.js');

// Set SHORTLIST_API_KEY in the Netlify dashboard (Site configuration ->
// Environment variables) once deployed, and send it back as the x-api-key
// header on every call. Left unset, the function stays open — fine for a
// first local test, not for a real deployment.
const REQUIRED_KEY = process.env.SHORTLIST_API_KEY;

function slugify(text) {
  return (
    (text || 'candidate')
      .toString()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '') || 'candidate'
  );
}

function json(statusCode, payload) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  };
}

exports.handler = async function (event) {
  if (event.httpMethod !== 'POST') {
    return json(405, { ok: false, errors: ['Use POST.'] });
  }

  if (REQUIRED_KEY && event.headers['x-api-key'] !== REQUIRED_KEY) {
    return json(401, { ok: false, errors: ['Unauthorized: missing or incorrect x-api-key header.'] });
  }

  let body;
  try {
    body = JSON.parse(event.body || 'null');
  } catch (e) {
    return json(400, { ok: false, errors: [`Could not parse request body as JSON: ${e.message}`] });
  }
  if (body === null || body === undefined) {
    return json(400, { ok: false, errors: ['Request body must be JSON: either a candidate array, or an object with a "candidates" array.'] });
  }

  const meta = Array.isArray(body) ? {} : body;
  const payload = Array.isArray(body) ? body : body.candidates !== undefined ? body.candidates : body;
  const rawText = typeof payload === 'string' ? payload : JSON.stringify(payload);

  const result = sourcingExcel.validateAndNormalize(rawText);
  if (!result.ok) {
    return json(400, { ok: false, errors: result.errors, warnings: result.warnings });
  }

  const wb = sourcingExcel.buildWorkbook(result.candidates);
  const contentBase64 = global.XLSX.write(wb, { bookType: 'xlsx', type: 'base64' });

  return json(200, {
    ok: true,
    filename: `${slugify(meta.jobTitle)}-shortlist.xlsx`,
    contentBase64,
    candidateCount: result.candidates.length,
    warnings: result.warnings
  });
};
