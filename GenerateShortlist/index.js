// HTTP endpoint for the Candidate Sourcing Agent's Copilot Studio integration.
// Reuses js/sourcingExcel.js unchanged (it already supports being `require`d
// as a CommonJS module, see the bottom of that file) so the validation rules
// and the .xlsx layout are identical to the ones in sourcing.html, rather
// than a second copy that could drift out of sync.
const path = require('path');

global.XLSX = require('xlsx');
const sourcingExcel = require(path.join(__dirname, '..', 'js', 'sourcingExcel.js'));

function slugify(text) {
  return (text || 'candidate')
    .toString()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || 'candidate';
}

module.exports = async function (context, req) {
  const body = req.body;
  if (body === undefined || body === null) {
    context.res = {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
      body: { ok: false, errors: ['Request body must be JSON: either a candidate array, or an object with a "candidates" array.'] }
    };
    return;
  }

  const meta = Array.isArray(body) ? {} : body;
  const payload = Array.isArray(body) ? body : (body.candidates !== undefined ? body.candidates : body);
  const rawText = typeof payload === 'string' ? payload : JSON.stringify(payload);

  const result = sourcingExcel.validateAndNormalize(rawText);
  if (!result.ok) {
    context.res = {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
      body: { ok: false, errors: result.errors, warnings: result.warnings }
    };
    return;
  }

  const wb = sourcingExcel.buildWorkbook(result.candidates);
  const contentBase64 = global.XLSX.write(wb, { bookType: 'xlsx', type: 'base64' });

  context.res = {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    body: {
      ok: true,
      filename: `${slugify(meta.jobTitle)}-shortlist.xlsx`,
      contentBase64,
      candidateCount: result.candidates.length,
      warnings: result.warnings
    }
  };
};
