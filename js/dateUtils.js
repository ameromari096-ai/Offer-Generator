// Date resolution logic for the PureHealth Interview Scheduling Assistant.
// All "today" calculations use Gulf Standard Time (UTC+04:00, no DST) regardless
// of the visitor's own timezone, per the agent's DATE RULES.
(function (global) {
  const WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
  ];
  const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  // Returns a Date whose UTC fields (getUTCFullYear/Month/Date/Day) represent
  // the current calendar day/time in Gulf Standard Time (UTC+4, fixed offset).
  function nowInUae() {
    return new Date(Date.now() + 4 * 60 * 60 * 1000);
  }

  // A "day-only" value (UAE calendar date) represented as a UTC-midnight Date,
  // safe to compare with === on getTime() or with plain <, >.
  function dayKey(y, m, d) {
    return Date.UTC(y, m, d);
  }

  function uaeTodayDayKey() {
    const n = nowInUae();
    return dayKey(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate());
  }

  // Monday=1 ... Sunday=7
  function isoWeekday(dk) {
    const jsDay = new Date(dk).getUTCDay(); // 0=Sun..6=Sat
    return jsDay === 0 ? 7 : jsDay;
  }

  function formatDayKey(dk) {
    const d = new Date(dk);
    const weekday = WEEKDAY_NAMES[isoWeekday(dk) - 1];
    const day = String(d.getUTCDate());
    const month = MONTH_NAMES[d.getUTCMonth()];
    const year = d.getUTCFullYear();
    return `${weekday} - ${day} - ${month} - ${year}`;
  }

  function toDateInputValue(dk) {
    const d = new Date(dk);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function fromDateInputValue(value) {
    // value is "YYYY-MM-DD" from <input type="date">, always unambiguous.
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!m) return null;
    return dayKey(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }

  const api = {
    nowInUae,
    dayKey,
    uaeTodayDayKey,
    isoWeekday,
    formatDayKey,
    toDateInputValue,
    fromDateInputValue,
    WEEKDAY_NAMES,
    MONTH_NAMES
  };

  const root = global.PH || (global.PH = {});
  root.dateUtils = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
