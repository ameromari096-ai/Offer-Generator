// Builds a standard .eml (RFC 5322 / MIME) file. Double-clicking it in
// Outlook opens a normal, fully editable, UNSENT draft message — this is
// the closest a static web page can get to "Create Outlook Interview Email
// Draft" without a live Graph/Outlook connection. The recruiter adds
// interviewer addresses and sends it themselves.
(function (global) {
  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  }

  function chunkBase64(b64) {
    const lines = [];
    for (let i = 0; i < b64.length; i += 76) {
      lines.push(b64.slice(i, i + 76));
    }
    return lines.join('\r\n');
  }

  function encodeHeaderWord(text) {
    // Simple RFC 2047 encoded-word for non-ASCII subjects/names; plain ASCII
    // is left untouched for readability.
    if (/^[\x20-\x7e]*$/.test(text)) return text;
    const b64 = btoa(unescape(encodeURIComponent(text)));
    return `=?UTF-8?B?${b64}?=`;
  }

  /**
   * options: {
   *   to: string (candidate email, may be empty),
   *   subject: string,
   *   html: string,
   *   attachments: [{ filename, mimeType, arrayBuffer }],
   *   calendarIcs: string (optional) — when given, wraps html in a
   *     multipart/alternative and adds a text/calendar;method=REQUEST
   *     sibling part, so Outlook opens this as an editable meeting request
   *     (with a real calendar entry) instead of a plain email.
   * }
   */
  function buildEml(options) {
    const boundary = `----PureHealth_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
    const attachments = options.attachments || [];

    const headers = [
      `To: ${options.to || ''}`,
      `Subject: ${encodeHeaderWord(options.subject)}`,
      'MIME-Version: 1.0',
      `Content-Type: multipart/mixed; boundary="${boundary}"`,
      'X-Unsent: 1'
    ];
    if (options.calendarIcs) {
      // Legacy Outlook marker that makes a double-clicked .eml open as an
      // editable Meeting Request compose window instead of a plain email.
      headers.push('Content-Class: urn:content-classes:calendarmessage');
    }

    const parts = [];
    if (options.calendarIcs) {
      const altBoundary = `${boundary}_ALT`;
      const plainText = htmlToPlainText(options.html);
      parts.push(
        `--${boundary}\r\n` +
          `Content-Type: multipart/alternative; boundary="${altBoundary}"\r\n\r\n` +
          `--${altBoundary}\r\n` +
          'Content-Type: text/plain; charset="utf-8"\r\n' +
          'Content-Transfer-Encoding: quoted-printable\r\n\r\n' +
          quotedPrintable(plainText) +
          '\r\n' +
          `--${altBoundary}\r\n` +
          'Content-Type: text/html; charset="utf-8"\r\n' +
          'Content-Transfer-Encoding: quoted-printable\r\n\r\n' +
          quotedPrintable(options.html) +
          '\r\n' +
          `--${altBoundary}--\r\n`
      );
      parts.push(
        `--${boundary}\r\n` +
          'Content-Type: text/calendar; method=REQUEST; charset="utf-8"\r\n' +
          'Content-Transfer-Encoding: quoted-printable\r\n\r\n' +
          quotedPrintable(options.calendarIcs) +
          '\r\n'
      );
    } else {
      parts.push(
        `--${boundary}\r\n` +
          'Content-Type: text/html; charset="utf-8"\r\n' +
          'Content-Transfer-Encoding: quoted-printable\r\n\r\n' +
          quotedPrintable(options.html) +
          '\r\n'
      );
    }

    for (const att of attachments) {
      const b64 = chunkBase64(arrayBufferToBase64(att.arrayBuffer));
      parts.push(
        `--${boundary}\r\n` +
          `Content-Type: ${att.mimeType}; name="${att.filename}"\r\n` +
          'Content-Transfer-Encoding: base64\r\n' +
          `Content-Disposition: attachment; filename="${att.filename}"\r\n\r\n` +
          b64 +
          '\r\n'
      );
    }

    parts.push(`--${boundary}--\r\n`);

    return headers.join('\r\n') + '\r\n\r\n' + parts.join('');
  }

  // Minimal HTML-to-text conversion for the plain-text alternative part —
  // good enough for a fallback view, not meant to preserve exact layout.
  function htmlToPlainText(html) {
    return String(html || '')
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|tr|table|li)>/gi, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function quotedPrintable(str) {
    // Minimal encoder sufficient for our generated HTML (ASCII + a few UTF-8
    // punctuation marks like the en dash).
    const bytes = new TextEncoder().encode(str);
    let out = '';
    let lineLen = 0;
    for (const byte of bytes) {
      let piece;
      if ((byte >= 33 && byte <= 126 && byte !== 61) || byte === 32 || byte === 9) {
        piece = String.fromCharCode(byte);
      } else if (byte === 10) {
        out += '\r\n';
        lineLen = 0;
        continue;
      } else if (byte === 13) {
        continue;
      } else {
        piece = '=' + byte.toString(16).toUpperCase().padStart(2, '0');
      }
      if (lineLen + piece.length > 75) {
        out += '=\r\n';
        lineLen = 0;
      }
      out += piece;
      lineLen += piece.length;
    }
    return out;
  }

  const api = { buildEml, arrayBufferToBase64 };
  const root = global.PH || (global.PH = {});
  root.eml = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
