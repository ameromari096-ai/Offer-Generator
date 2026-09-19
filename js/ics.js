// Builds an unsent Outlook calendar draft (.ics). No ATTENDEE/ORGANIZER/
// METHOD:REQUEST properties are emitted, because any of those turn a plain
// .ics import into a meeting Outlook is prepared to auto-send — instead this
// produces an ordinary appointment on the recruiter's own calendar that they
// review, add interviewer/candidate invitees to, and send manually.
(function (global) {
  function pad(n) {
    return String(n).padStart(2, '0');
  }

  // dayKey: UTC-midnight ms representing the UAE calendar date.
  // minutesOfDay: minutes since UAE local midnight.
  // Returns "YYYYMMDDTHHMMSSZ" (true UTC instant, UAE is UTC+4 with no DST).
  function toIcsUtc(dayKey, minutesOfDay) {
    const uaeLocalMs = dayKey + minutesOfDay * 60000;
    const utcMs = uaeLocalMs - 4 * 60 * 60 * 1000;
    const d = new Date(utcMs);
    return (
      `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T` +
      `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
    );
  }

  function nowStampUtc() {
    const d = new Date();
    return (
      `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T` +
      `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
    );
  }

  function escapeIcsText(s) {
    return String(s || '')
      .replace(/\\/g, '\\\\')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,')
      .replace(/\r?\n/g, '\\n');
  }

  // Folds lines longer than 75 octets per RFC 5545.
  function foldLine(line) {
    if (line.length <= 75) return line;
    let result = '';
    let rest = line;
    while (rest.length > 75) {
      result += rest.slice(0, 75) + '\r\n ';
      rest = rest.slice(75);
    }
    return result + rest;
  }

  /**
   * state: { requestId, subject, dayKey, startMinutes, endMinutes,
   *          location, description }
   */
  function buildIcs(state) {
    const lines = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//PureHealth//Interview Scheduling Assistant//EN',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      'BEGIN:VEVENT',
      `UID:${state.requestId}@purehealth.ae`,
      `DTSTAMP:${nowStampUtc()}`,
      `DTSTART:${toIcsUtc(state.dayKey, state.startMinutes)}`,
      `DTEND:${toIcsUtc(state.dayKey, state.endMinutes)}`,
      `SUMMARY:${escapeIcsText(state.subject)}`,
      `LOCATION:${escapeIcsText(state.location)}`,
      `DESCRIPTION:${escapeIcsText(state.description)}`,
      'STATUS:TENTATIVE',
      'TRANSP:OPAQUE',
      'END:VEVENT',
      'END:VCALENDAR'
    ];
    return lines.map(foldLine).join('\r\n') + '\r\n';
  }

  const api = { buildIcs, toIcsUtc };
  const root = global.PH || (global.PH = {});
  root.ics = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
