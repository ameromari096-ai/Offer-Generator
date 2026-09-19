// Validates the JSON a sourcing agent pastes back (see js/sourcingPrompt.js
// for the schema it was asked to follow) against the shortlist's formatting
// rules, then builds a real .xlsx file with SheetJS (vendored as
// vendor/xlsx.min.js — see vendor/README.md). This never invents candidate
// data; it only formats and checks what was pasted in.
(function (global) {
  const COLUMNS = [
    { key: 'candidateName', header: 'Candidate Name', width: 22 },
    { key: 'currentTitle', header: 'Current Job Title', width: 26 },
    { key: 'currentCompany', header: 'Current Company', width: 24 },
    { key: 'currentLocation', header: 'Current Location', width: 20 },
    { key: 'linkedinUrl', header: 'LinkedIn Profile URL', width: 38 },
    { key: 'organizationBrief', header: 'Organization Brief', width: 50, bullets: true },
    { key: 'shortlistRationale', header: 'Shortlist Rationale', width: 50, bullets: true },
    { key: 'candidateBrief', header: 'Candidate Brief', width: 50, bullets: true },
    { key: 'matchScore', header: 'Match Score', width: 14 }
  ];

  const LINKEDIN_RE = /^https?:\/\/([a-z]{2,3}\.)?linkedin\.com\/in\//i;
  const CONFIDENCE_LEVELS = ['High', 'Medium', 'Low'];

  function normalizeBullets(value) {
    let items;
    if (Array.isArray(value)) {
      items = value.map((v) => String(v == null ? '' : v));
    } else if (typeof value === 'string') {
      items = value
        .split(/\r?\n|(?:^|\s)•\s*/)
        .map((s) => s.replace(/^[-*•]\s*/, '').trim());
    } else {
      items = [];
    }
    return items.map((s) => s.trim()).filter(Boolean);
  }

  function wordCount(s) {
    return s.trim().split(/\s+/).filter(Boolean).length;
  }

  /**
   * rawText: the pasted JSON (array, or { candidates: [...] }).
   * Returns { ok, candidates, rows, errors, warnings } where `candidates`
   * are normalized objects ready for buildWorkbook, `rows` mirrors them for
   * an on-screen preview, and `errors` block export until resolved.
   */
  function validateAndNormalize(rawText) {
    let parsed;
    try {
      parsed = JSON.parse(rawText);
    } catch (e) {
      return { ok: false, candidates: [], rows: [], errors: [`Could not parse JSON: ${e.message}`], warnings: [] };
    }
    const list = Array.isArray(parsed) ? parsed : Array.isArray(parsed.candidates) ? parsed.candidates : null;
    if (!list) {
      return { ok: false, candidates: [], rows: [], errors: ['Expected a JSON array of candidates (or an object with a "candidates" array).'], warnings: [] };
    }
    if (list.length === 0) {
      return { ok: false, candidates: [], rows: [], errors: ['The candidate list is empty.'], warnings: [] };
    }

    const errors = [];
    const warnings = [];
    const candidates = list.map((item, idx) => {
      const rowLabel = `Row ${idx + 1}${item && item.candidateName ? ` (${item.candidateName})` : ''}`;
      const out = { ...item };

      ['candidateName', 'currentTitle', 'currentCompany', 'currentLocation'].forEach((field) => {
        if (!out[field] || !String(out[field]).trim()) {
          errors.push(`${rowLabel}: missing "${field}".`);
        } else {
          out[field] = String(out[field]).trim();
        }
      });

      const url = String(out.linkedinUrl || '').trim();
      if (!url) {
        errors.push(`${rowLabel}: missing "linkedinUrl".`);
      } else if (!LINKEDIN_RE.test(url)) {
        warnings.push(`${rowLabel}: "linkedinUrl" doesn't look like a LinkedIn profile URL (${url}). Only include real profiles you actually found.`);
      }
      out.linkedinUrl = url;

      ['organizationBrief', 'shortlistRationale', 'candidateBrief'].forEach((field) => {
        const bullets = normalizeBullets(out[field]);
        if (bullets.length !== 3) {
          errors.push(`${rowLabel}: "${field}" has ${bullets.length} bullet(s), needs exactly 3.`);
        }
        bullets.forEach((b, i) => {
          const wc = wordCount(b);
          if (wc < 5) {
            warnings.push(`${rowLabel}: "${field}" bullet ${i + 1} looks too short (${wc} words) to be a full clause.`);
          }
        });
        out[field] = bullets;
      });

      const score = Number(out.matchScore);
      if (!Number.isFinite(score) || score < 0 || score > 100) {
        errors.push(`${rowLabel}: "matchScore" must be a number from 0-100.`);
      } else {
        out.matchScore = Math.round(score);
      }

      const confRaw = String(out.confidence || '').trim();
      const conf = CONFIDENCE_LEVELS.find((c) => c.toLowerCase() === confRaw.toLowerCase());
      if (!conf) {
        errors.push(`${rowLabel}: "confidence" must be High, Medium, or Low (got "${confRaw || '(empty)'}").`);
      } else {
        out.confidence = conf;
      }

      return out;
    });

    return { ok: errors.length === 0, candidates, rows: candidates, errors, warnings };
  }

  function buildWorkbook(candidates) {
    const header = COLUMNS.map((c) => c.header);
    const aoa = [header];
    candidates.forEach((cand) => {
      aoa.push(COLUMNS.map((c) => {
        const v = cand[c.key];
        if (c.bullets) return (v || []).map((b) => `• ${b}`).join('\n');
        if (c.key === 'matchScore') return `${v} (${cand.confidence})`;
        return v;
      }));
    });

    // The vendored (community) build of xlsx doesn't write cell styles, so
    // wide columns + tall rows are what keep the bullet columns readable —
    // Excel still renders the embedded "\n" bullet line breaks even without
    // a "Wrap Text" style on the cell.
    const ws = global.XLSX.utils.aoa_to_sheet(aoa);
    ws['!cols'] = COLUMNS.map((c) => ({ wch: c.width }));
    ws['!rows'] = [{ hpt: 20 }].concat(candidates.map(() => ({ hpt: 90 })));

    const wb = global.XLSX.utils.book_new();
    global.XLSX.utils.book_append_sheet(wb, ws, 'Shortlist');
    return wb;
  }

  function downloadWorkbook(candidates, filename) {
    const wb = buildWorkbook(candidates);
    global.XLSX.writeFile(wb, filename || 'candidate-shortlist.xlsx');
  }

  const api = { COLUMNS, validateAndNormalize, buildWorkbook, downloadWorkbook };
  const root = global.PH || (global.PH = {});
  root.sourcingExcel = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
