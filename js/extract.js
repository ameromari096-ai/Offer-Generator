// Best-effort client-side "Extract Candidate Details" for an uploaded CV.
// There is no server-side CV-parsing service behind this static site, so
// extraction runs entirely in the browser (pdf.js for PDFs, mammoth.js for
// .docx, plain text otherwise) and is always reported with a confidence
// level. Low-confidence results must be confirmed by the user before use.
(function (global) {
  const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;

  // Labeled phone numbers ("Phone: +971 50 123 4567") are trusted outright.
  // An unlabeled fallback requires a '+' country code or a "(area code)"
  // group -- a bare run of separated digits is too easily a date, a year
  // range, or a postal/reference code elsewhere on the CV.
  const PHONE_LABEL_RE = /(?:phone|mobile|tel(?:ephone)?|cell|contact)\s*(?:no\.?|number)?\s*[:\-]\s*([+(]?[\d][\d\s().-]{6,}\d)/i;
  const PHONE_FALLBACK_RE = /(\+\d[\d\s().-]{6,}\d)|(\(\d{2,4}\)[\d\s().-]{4,}\d)/;

  function plausiblePhoneDigits(candidate) {
    const digits = candidate.replace(/\D/g, '');
    return digits.length >= 7 && digits.length <= 15;
  }

  function findPhone(text) {
    const labelMatch = PHONE_LABEL_RE.exec(text || '');
    if (labelMatch && plausiblePhoneDigits(labelMatch[1])) {
      return { phone: labelMatch[1].trim(), confidence: 'high' };
    }
    const fallbackMatch = PHONE_FALLBACK_RE.exec(text || '');
    if (fallbackMatch) {
      const candidate = (fallbackMatch[1] || fallbackMatch[2]).trim();
      if (plausiblePhoneDigits(candidate)) {
        return { phone: candidate, confidence: 'low' };
      }
    }
    return { phone: null, confidence: 'low' };
  }

  const NON_NAME_WORDS =
    /curriculum vitae|resume|cv\b|address|phone|mobile|email|profile|summary|objective|experience|education|skills|qualifications|certifications|projects|languages|references|contact|linkedin|github|portfolio|declaration|nationality|marital|gender|birth|street|city|country/i;

  function looksLikeName(line) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.length > 60) return false;
    if (/[0-9@]/.test(trimmed)) return false;
    if (NON_NAME_WORDS.test(trimmed)) return false;
    const words = trimmed.split(/\s+/);
    if (words.length < 1 || words.length > 5) return false;
    return words.every((w) => /^[A-Z][a-zA-Z'.-]*$/.test(w));
  }

  // Explicit "Name: John Smith" / "Full Name: John Smith" style labels, when present.
  function findLabeledName(lines) {
    for (const line of lines) {
      const m = /^(?:full\s*name|candidate\s*name|name)\s*[:\-]\s*(.+)$/i.exec(line.trim());
      if (m && looksLikeName(m[1])) return m[1].trim();
    }
    return null;
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
    const phoneResult = findPhone(text);

    const lines = (text || '')
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(0, 15);

    let name = findLabeledName(lines);
    let nameConfidence = name ? 'high' : 'low';
    if (!name) {
      for (const line of lines) {
        if (looksLikeName(line)) {
          name = line;
          nameConfidence = 'high';
          break;
        }
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
      emailConfidence: email ? 'high' : 'low',
      phone: phoneResult.phone,
      phoneConfidence: phoneResult.confidence
    };
  }

  async function readAsText(file) {
    return await file.text();
  }

  // pdf.js reports one item per glyph run, not per visual line — a name is
  // frequently split into separate items (different weight/kerning from the
  // surrounding text), so naively joining items with '\n' shreds it across
  // multiple "lines" and breaks name detection. Reassemble visual lines by
  // grouping items that share a baseline (their transform's y coordinate).
  function reconstructLines(items) {
    const lines = [];
    let currentLine = '';
    let currentY = null;
    const Y_TOLERANCE = 2;
    for (const item of items) {
      const str = item.str || '';
      const y = Array.isArray(item.transform) ? item.transform[5] : null;
      const sameLine = currentY !== null && y !== null && Math.abs(y - currentY) <= Y_TOLERANCE;
      if (!sameLine) {
        if (currentLine.trim()) lines.push(currentLine.trim());
        currentLine = str;
        currentY = y;
      } else {
        const needsSpace = currentLine && !/\s$/.test(currentLine) && !/^\s/.test(str);
        currentLine += (needsSpace ? ' ' : '') + str;
      }
      if (item.hasEOL) {
        if (currentLine.trim()) lines.push(currentLine.trim());
        currentLine = '';
        currentY = null;
      }
    }
    if (currentLine.trim()) lines.push(currentLine.trim());
    return lines.join('\n');
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
      text += reconstructLines(content.items) + '\n';
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
   * Returns { name, nameConfidence, email, emailConfidence, phone,
   *           phoneConfidence, filename, reference,
   *           status: 'ok'|'uncertain'|'unsupported', warning? }
   */
  async function extractCandidateDetails(file) {
    const reference = `CV-${Date.now().toString(36).toUpperCase()}`;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    let text = '';
    let failureReason = null; // 'unsupported_type' | 'reader_unavailable' | 'parse_error' | 'no_text' | null
    try {
      if (ext === 'pdf') {
        if (!global.pdfjsLib) {
          failureReason = 'reader_unavailable';
        } else {
          text = await readAsPdfText(file);
        }
      } else if (ext === 'docx') {
        if (!global.mammoth) {
          failureReason = 'reader_unavailable';
        } else {
          text = await readAsDocxText(file);
        }
      } else if (ext === 'txt') {
        text = await readAsText(file);
      } else {
        failureReason = 'unsupported_type';
      }
    } catch (err) {
      failureReason = 'parse_error';
    }
    if (!failureReason && !text.trim()) {
      failureReason = 'no_text';
    }

    const result = extractFromText(text, file.name);
    const unsupported = Boolean(failureReason);
    const uncertain =
      unsupported || result.nameConfidence === 'low' || result.emailConfidence === 'low';

    const failureMessages = {
      unsupported_type: `"${file.name}" is not a supported CV file type (use PDF, DOCX, or TXT).`,
      reader_unavailable: `The reader library for "${file.name}" failed to load — try reloading the page.`,
      parse_error: `"${file.name}" could not be parsed — it may be corrupted or password-protected.`,
      no_text: `No selectable text was found in "${file.name}" — it may be a scanned or image-based PDF (common with visually-designed CV templates) with no real text layer.`
    };

    return {
      name: result.name,
      nameConfidence: result.nameConfidence,
      email: result.email,
      emailConfidence: result.emailConfidence,
      phone: result.phone,
      phoneConfidence: result.phoneConfidence,
      filename: file.name,
      reference,
      status: unsupported ? 'unsupported' : uncertain ? 'uncertain' : 'ok',
      warning: unsupported
        ? `${failureMessages[failureReason]} Please enter the candidate name and email manually.`
        : uncertain
        ? 'Some extracted details are unconfirmed. Please review and correct the candidate name/email below.'
        : null
    };
  }

  /**
   * Best-effort raw text extraction from a PDF/DOCX/TXT file, for callers
   * that just want the document's text (e.g. a pasted job description)
   * rather than name/email/phone fields. Reads the whole document, not
   * just the first pages used for CV header detection.
   * Returns { text, warning? }.
   */
  async function extractRawText(file) {
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    try {
      if (ext === 'pdf') {
        if (!global.pdfjsLib) {
          return { text: '', warning: 'The PDF reader library failed to load — try reloading the page, or paste the text instead.' };
        }
        const buf = await file.arrayBuffer();
        const pdf = await global.pdfjsLib.getDocument({ data: buf }).promise;
        let text = '';
        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const content = await page.getTextContent();
          text += reconstructLines(content.items) + '\n';
        }
        if (!text.trim()) {
          return { text: '', warning: `No selectable text was found in "${file.name}" — it may be a scanned/image-based PDF. Please paste the text instead.` };
        }
        return { text };
      }
      if (ext === 'docx') {
        if (!global.mammoth) {
          return { text: '', warning: 'The DOCX reader library failed to load — try reloading the page, or paste the text instead.' };
        }
        const buf = await file.arrayBuffer();
        const result = await global.mammoth.extractRawText({ arrayBuffer: buf });
        return { text: result.value || '' };
      }
      if (ext === 'txt') {
        return { text: await readAsText(file) };
      }
      return { text: '', warning: `"${file.name}" is not a supported file type (use PDF, DOCX, or TXT).` };
    } catch (err) {
      return { text: '', warning: `"${file.name}" could not be parsed — it may be corrupted or password-protected. Please paste the text instead.` };
    }
  }

  // ---------- Employment contract / offer letter extraction ----------
  // PureHealth's contract template repeats the same company letterhead
  // ("Pure Health Medical Supplies L.L.C.", the office address, "Public
  // Document", the document titles) on every page above the candidate's
  // own name, which the generic CV line-heuristic below would otherwise
  // happily match as a name. Screen those lines out, and prefer patterns
  // specific to this contract's wording over the generic fallback.
  const LETTERHEAD_RE =
    /l\.?l\.?c\.?|pure\s*health|public document|offer letter|contract of employment|p\.o\.?\s*box|vision tower|business bay/i;

  function findQuotedEmployeeName(flatText) {
    const m = /\band\s+[“"]([A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,3})[”"]\s+of\s+[A-Za-z]+\s+nationality/i.exec(
      flatText
    );
    return m ? m[1].trim() : null;
  }

  function findGreetingFirstName(text) {
    const m = /\bDear\s+([A-Z][a-zA-Z'.-]+)\s*,/.exec(text || '');
    return m ? m[1].trim() : null;
  }

  function findJobTitleLabel(lines) {
    for (const line of lines) {
      const m = /^JOB\s*TITLE\s+(.+)$/i.exec(line.trim());
      if (m) return m[1].trim();
    }
    return null;
  }

  function findJobTitleFromOfferPhrase(flatText) {
    const m = /position of\s*[“"]([^”"]+)[”"]/i.exec(flatText);
    return m ? m[1].trim() : null;
  }

  function extractFromContractText(text, filename) {
    const emailMatch = EMAIL_RE.exec(text || '');
    const email = emailMatch ? emailMatch[0] : null;

    const allLines = (text || '')
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const headerLines = allLines.slice(0, 25);
    // Patterns can be split across the reconstructed lines' newlines (e.g. a
    // quoted name wrapping mid-sentence), so also search a whitespace-flattened
    // copy of the text for those.
    const flatText = (text || '').replace(/\s+/g, ' ');

    let name = findLabeledName(headerLines) || findQuotedEmployeeName(flatText);
    let nameConfidence = name ? 'high' : 'low';
    if (!name) {
      const greetingFirst = findGreetingFirstName(text);
      if (greetingFirst) {
        name = greetingFirst;
        nameConfidence = 'low';
      }
    }
    if (!name) {
      for (const line of headerLines) {
        if (LETTERHEAD_RE.test(line)) continue;
        if (looksLikeName(line)) {
          name = line;
          nameConfidence = 'high';
          break;
        }
      }
    }
    if (!name) {
      const guess = guessNameFromFilename(filename);
      if (guess) {
        name = guess;
        nameConfidence = 'low';
      }
    }

    const jobTitle = findJobTitleLabel(allLines) || findJobTitleFromOfferPhrase(flatText);

    return {
      name,
      nameConfidence,
      email,
      emailConfidence: email ? 'high' : 'low',
      jobTitle,
      jobTitleConfidence: jobTitle ? 'high' : 'low'
    };
  }

  /**
   * Extracts candidate name, email, and job title from an uploaded
   * employment contract / offer letter File object. Reads the whole
   * document (a contract's JOB TITLE row is typically on page 2, past the
   * 3-page cap extractCandidateDetails uses for CV headers).
   * Returns { name, nameConfidence, email, emailConfidence, jobTitle,
   *           jobTitleConfidence, filename, reference,
   *           status: 'ok'|'uncertain'|'unsupported', warning? }
   */
  async function extractContractDetails(file) {
    const reference = `CONTRACT-${Date.now().toString(36).toUpperCase()}`;
    const raw = await extractRawText(file);
    const result = extractFromContractText(raw.text, file.name);
    const unsupported = !raw.text.trim() && Boolean(raw.warning);
    const uncertain =
      unsupported ||
      result.nameConfidence === 'low' ||
      result.emailConfidence === 'low' ||
      result.jobTitleConfidence === 'low';

    return {
      name: result.name,
      nameConfidence: result.nameConfidence,
      email: result.email,
      emailConfidence: result.emailConfidence,
      jobTitle: result.jobTitle,
      jobTitleConfidence: result.jobTitleConfidence,
      filename: file.name,
      reference,
      status: unsupported ? 'unsupported' : uncertain ? 'uncertain' : 'ok',
      warning: unsupported
        ? `${raw.warning} Please enter the candidate name, email, and job title manually.`
        : uncertain
        ? 'Some extracted details are unconfirmed. Please review and correct the candidate name/email/job title below.'
        : null
    };
  }

  const api = {
    extractCandidateDetails,
    extractFromText,
    reconstructLines,
    extractRawText,
    extractContractDetails
  };
  const root = global.PH || (global.PH = {});
  root.extract = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
