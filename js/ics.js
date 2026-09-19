// Builds an RFC 5545 iCalendar METHOD:REQUEST block for the interview email,
// so double-clicking the generated .eml opens an editable, unsent Outlook
// MEETING request (with a real calendar entry, Accept/Decline) instead of a
// plain email that never touches the calendar. Still never sends anything
// itself — the recruiter reviews and sends the meeting invite from Outlook,
// same as the plain-email path this replaces for the candidate invite.
(function (global) {
  const UAE_OFFSET_MS = 4 * 60 * 60 * 1000; // UAE is a fixed UTC+4, no DST.

  function escapeIcsText(s) {
    return String(s || '')
      .replace(/\\/g, '\\\\')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,')
      .replace(/\r?\n/g, '\\n');
  }

  function quoteParam(s) {
    return String(s || '').replace(/"/g, '');
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
   * options: {
   *   uid, dayKey, startMinutes, endMinutes, summary, location,
   *   description, htmlDescription, attendeeName, attendeeEmail
   * }
   */
  function buildMeetingRequest(options) {
    const lines = [
      'BEGIN:VCALENDAR',
      'PRODID:-//PureHealth//Interview Scheduling Assistant//EN',
      'VERSION:2.0',
      'METHOD:REQUEST',
      'CALSCALE:GREGORIAN',
      'BEGIN:VEVENT',
      `UID:${options.uid}`,
      `DTSTAMP:${formatUtcStamp(new Date())}`,
      `DTSTART:${toIcsUtc(options.dayKey, options.startMinutes)}`,
      `DTEND:${toIcsUtc(options.dayKey, options.endMinutes)}`,
      `SUMMARY:${escapeIcsText(options.summary)}`,
      `LOCATION:${escapeIcsText(options.location)}`,
      `DESCRIPTION:${escapeIcsText(options.description)}`
    ];
    if (options.htmlDescription) {
      lines.push(`X-ALT-DESC;FMTTYPE=text/html:${escapeIcsText(options.htmlDescription)}`);
    }
    lines.push(
      'ORGANIZER;CN="PureHealth Talent Acquisition":mailto:no-reply@purehealth.ae',
      `ATTENDEE;CN="${quoteParam(options.attendeeName)}";ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:${options.attendeeEmail}`,
      'STATUS:CONFIRMED',
      'SEQUENCE:0',
      'END:VEVENT',
      'END:VCALENDAR'
    );
    return lines.map(foldLine).join('\r\n') + '\r\n';
  }

  const api = { buildMeetingRequest };
  const root = global.PH || (global.PH = {});
  root.ics = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
