// Builds a standalone RFC 5545 .ics calendar file, attached to the
// candidate email draft as a REGULAR FILE ATTACHMENT (same mechanism as the
// PDF/CV attachments) — not embedded as a live text/calendar;method=REQUEST
// MIME part. That approach was tried and reverted: it made Outlook send the
// email immediately on open instead of drafting it. A plain .ics attachment
// requires the recruiter (or candidate) to deliberately double-click it to
// add the event to their own calendar — nothing happens automatically.
(function (global) {
  const UAE_OFFSET_MS = 4 * 60 * 60 * 1000; // UAE is a fixed UTC+4, no DST.

  function escapeIcsText(s) {
    return String(s || '')
      .replace(/\\/g, '\\\\')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,')
      .replace(/\r?\n/g, '\\n');
  }

  // RFC 5545: content lines SHOULD be folded at 75 octets; continuation
  // lines start with a single space.
  function foldLine(line) {
    if (line.length <= 75) return line;
    const parts = [];
    let rest = line;
    while (rest.length > 75) {
      parts.push(rest.slice(0, 75));
      rest = ' ' + rest.slice(75);
    }
    parts.push(rest);
    return parts.join('\r\n');
  }

  function pad2(n) {
    return String(n).padStart(2, '0');
  }

  function formatUtcStamp(d) {
    return (
      `${d.getUTCFullYear()}${pad2(d.getUTCMonth() + 1)}${pad2(d.getUTCDate())}T` +
      `${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}${pad2(d.getUTCSeconds())}Z`
    );
  }

  // dayKeyMs is the UTC-midnight representation of the UAE calendar day (see
  // dateUtils.js); minutesFromMidnight is UAE LOCAL time-of-day (can exceed
  // 1440 for an interview that crosses midnight — Date arithmetic below
  // rolls that over to the next calendar day correctly).
  function toIcsUtc(dayKeyMs, minutesFromMidnight) {
    const localAsUtcMs = dayKeyMs + minutesFromMidnight * 60000;
    return formatUtcStamp(new Date(localAsUtcMs - UAE_OFFSET_MS));
  }

  /**
   * options: { uid, dayKey, startMinutes, endMinutes, summary, location, description }
   * METHOD:PUBLISH with no ORGANIZER/ATTENDEE — a plain "add this event to
   * your calendar" file, not a live invitation transaction.
   */
  function buildEvent(options) {
    const lines = [
      'BEGIN:VCALENDAR',
      'PRODID:-//PureHealth//Interview Scheduling Assistant//EN',
      'VERSION:2.0',
      'METHOD:PUBLISH',
      'CALSCALE:GREGORIAN',
      'BEGIN:VEVENT',
      `UID:${options.uid}`,
      `DTSTAMP:${formatUtcStamp(new Date())}`,
      `DTSTART:${toIcsUtc(options.dayKey, options.startMinutes)}`,
      `DTEND:${toIcsUtc(options.dayKey, options.endMinutes)}`,
      `SUMMARY:${escapeIcsText(options.summary)}`,
      `LOCATION:${escapeIcsText(options.location)}`,
      `DESCRIPTION:${escapeIcsText(options.description)}`,
      'STATUS:CONFIRMED',
      'SEQUENCE:0',
      'END:VEVENT',
      'END:VCALENDAR'
    ];
    return lines.map(foldLine).join('\r\n') + '\r\n';
  }

  const api = { buildEvent };
  const root = global.PH || (global.PH = {});
  root.ics = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
