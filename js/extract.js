// Best-effort client-side "Extract Candidate Details" for an uploaded CV.
// There is no server-side CV-parsing service behind this static site, so
// extraction runs entirely in the browser (pdf.js for PDFs, mammoth.js for
// .docx, plain text otherwise) and is always reported with a confidence
// level. Low-confidence results must be confirmed by the user before use.
(function (global) {
  const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;

  function looksLikeName(line) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.length > 60) return false;
    if (/[0-9@]/.test(trimmed)) return false;
    if (/curriculum vitae|resume|cv\b|address|phone|email|profile|summary/i.test(trimmed)) return false;
    const words = trimmed.split(/\s+/);
    if (words.length < 2 || words.length > 4) return false;
    return words.every((w) => /^[A-Z][a-zA-Z'.-]*$/.test(w));
  }

  function guessNameFromFilename(filename) {
    const base = filename.replace(/\.[^.]+$/, '');
    const cleaned = base
      .replace(/[_\-]+/g, ' ')
      .replace(/\b(cv|resume|curriculum vitae)\b/gi, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!cleaned) return null;
    const words = cleaned.split(' ').filter(Boolean);
    if (words.length < 2 || words.length > 4) return null;
    return words
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  }

  function extractFromText(text, filename) {
    const emailMatch = EMAIL_RE.exec(text || '');
    const email = emailMatch ? emailMatch[0] : null;

    const lines = (text || '')
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(0, 15);

    let name = null;
    let nameConfidence = 'low';
    for (const line of lines) {
      if (looksLikeName(line)) {
        name = line;
        nameConfidence = 'high';
        break;
      }
    }
    if (!name) {
      const guess = guessNameFromFilename(filename);
      if (guess) {
        name = guess;
        nameConfidence = 'low';
      }
    }

    return {
      name,
      nameConfidence,
      email,
      emailConfidence: email ? 'high' : 'low'
    };
  }

  async function readAsText(file) {
    return await file.text();
  }

  async function readAsPdfText(file) {
    if (!global.pdfjsLib) return '';
    const buf = await file.arrayBuffer();
    const pdf = await global.pdfjsLib.getDocument({ data: buf }).promise;
    let text = '';
    const pageCount = Math.min(pdf.numPages, 3); // CV header info is always on page 1
    for (let i = 1; i <= pageCount; i++) {
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      text += content.items.map((it) => it.str).join('\n') + '\n';
    }
    return text;
  }

  async function readAsDocxText(file) {
    if (!global.mammoth) return '';
    const buf = await file.arrayBuffer();
    const result = await global.mammoth.extractRawText({ arrayBuffer: buf });
    return result.value || '';
  }

  /**
   * Extracts candidate details from an uploaded CV File object.
   * Returns { name, nameConfidence, email, emailConfidence, filename,
   *           reference, status: 'ok'|'uncertain'|'unsupported', warning? }
   */
  async function extractCandidateDetails(file) {
    const reference = `CV-${Date.now().toString(36).toUpperCase()}`;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    let text = '';
    let unsupported = false;
    try {
      if (ext === 'pdf') {
        if (!global.pdfjsLib) {
          unsupported = true;
        } else {
          text = await readAsPdfText(file);
        }
      } else if (ext === 'docx') {
        if (!global.mammoth) {
          unsupported = true;
        } else {
          text = await readAsDocxText(file);
        }
      } else if (ext === 'txt') {
        text = await readAsText(file);
      } else {
        unsupported = true;
      }
    } catch (err) {
      unsupported = true;
    }
    if (!unsupported && !text.trim()) {
      unsupported = true;
    }

    const result = extractFromText(text, file.name);
    const uncertain =
      unsupported || result.nameConfidence === 'low' || result.emailConfidence === 'low';

    return {
      name: result.name,
      nameConfidence: result.nameConfidence,
      email: result.email,
      emailConfidence: result.emailConfidence,
      filename: file.name,
      reference,
      status: unsupported ? 'unsupported' : uncertain ? 'uncertain' : 'ok',
      warning: unsupported
        ? `Could not automatically read text from "${file.name}" (the file type is unsupported, or the reader library failed to load — check your internet connection). Please enter the candidate name and email manually.`
        : uncertain
        ? 'Some extracted details are unconfirmed. Please review and correct the candidate name/email below.'
        : null
    };
  }

  const api = { extractCandidateDetails, extractFromText };
  const root = global.PH || (global.PH = {});
  root.extract = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
