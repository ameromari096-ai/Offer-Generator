// Time calculation logic: start time + duration -> end time, 12-hour formatting.
(function (global) {
  // "HH:MM" (24h, from <input type="time">) -> minutes since midnight.
  function parseHm(value) {
    const m = /^(\d{1,2}):(\d{2})$/.exec((value || '').trim());
    if (!m) return null;
    const h = Number(m[1]);
    const min = Number(m[2]);
    if (h > 23 || min > 59) return null;
    return h * 60 + min;
  }

  function minutesToLabel(totalMinutes) {
    const wrapped = ((totalMinutes % 1440) + 1440) % 1440;
    let h = Math.floor(wrapped / 60);
    const m = wrapped % 60;
    const suffix = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) h = 12;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')} ${suffix}`;
  }

  function minutesToHm(totalMinutes) {
    const wrapped = ((totalMinutes % 1440) + 1440) % 1440;
    const h = Math.floor(wrapped / 60);
    const m = wrapped % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  }

  /**
   * Calculates the interview end time from a validated start time and duration.
   * startValue: "HH:MM" 24h. durationMinutes: integer > 0.
   * Returns { status: 'ok', startMinutes, endMinutes, formatted, crossesMidnight }
   *      or { status: 'error', message }
   */
  function calculate(startValue, durationMinutes) {
    const startMinutes = parseHm(startValue);
    if (startMinutes === null) {
      return { status: 'error', message: 'Please provide a valid start time.' };
    }
    const duration = Number(durationMinutes);
    if (!Number.isFinite(duration) || duration <= 0) {
      return { status: 'error', message: 'What is the interview duration in minutes?' };
    }
    const endMinutes = startMinutes + Math.round(duration);
    if (endMinutes <= startMinutes) {
      return { status: 'error', message: 'The calculated end time must be later than the start time.' };
    }
    const crossesMidnight = endMinutes >= 1440;
    return {
      status: 'ok',
      startMinutes,
      endMinutes,
      crossesMidnight,
      formatted: `${minutesToLabel(startMinutes)} – ${minutesToLabel(endMinutes)} (UAE Time)`
    };
  }

  function normalizeDurationInput(rawValue, rawUnit) {
    const value = Number(rawValue);
    if (!Number.isFinite(value) || value <= 0) return null;
    if (rawUnit === 'hours') return Math.round(value * 60);
    return Math.round(value);
  }

  const api = { parseHm, minutesToLabel, minutesToHm, calculate, normalizeDurationInput };

  const root = global.PH || (global.PH = {});
  root.timeUtils = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
