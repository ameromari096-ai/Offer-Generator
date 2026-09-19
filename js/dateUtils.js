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
  const MONTH_LOOKUP = (() => {
    const map = {};
    MONTH_NAMES.forEach((name, i) => {
      map[name.toLowerCase()] = i;
      map[name.slice(0, 3).toLowerCase()] = i;
    });
    return map;
  })();

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

  function mondayOfWeekContaining(dk) {
    const wd = isoWeekday(dk); // 1..7
    return dk - (wd - 1) * 86400000;
  }

  function addDays(dk, days) {
    return dk + days * 86400000;
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

  const WEEKDAY_LOOKUP = (() => {
    const map = {};
    WEEKDAY_NAMES.forEach((name, i) => {
      map[name.toLowerCase()] = i + 1;
      map[name.slice(0, 3).toLowerCase()] = i + 1;
    });
    return map;
  })();

  function findWeekdayToken(text) {
    const words = text.toLowerCase().match(/[a-z]+/g) || [];
    for (const w of words) {
      if (WEEKDAY_LOOKUP[w]) return WEEKDAY_LOOKUP[w];
    }
    return null;
  }

  /**
   * Resolves a free-text date phrase against the current UAE date.
   * Returns one of:
   *   { status: 'ok', dayKey, label }
   *   { status: 'ambiguous', message, options: [{dayKey, label}, ...] }
   *   { status: 'error', message }
   */
  function resolvePhrase(rawPhrase) {
    const phrase = (rawPhrase || '').trim();
    if (!phrase) return { status: 'error', message: 'Please provide an interview date.' };
    const lower = phrase.toLowerCase();
    const today = uaeTodayDayKey();

    if (/^today$/.test(lower)) {
      return { status: 'ok', dayKey: today, label: formatDayKey(today) };
    }
    if (/^tomorrow$/.test(lower)) {
      const dk = addDays(today, 1);
      return { status: 'ok', dayKey: dk, label: formatDayKey(dk) };
    }

    const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(phrase);
    if (isoMatch) {
      const dk = dayKey(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
      return finishExplicitDate(dk, today);
    }

    // "22 September 2026", "September 22 2026", "22 Sep 2026", with optional comma.
    const monthWordMatch =
      /^(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)\.?,?\s+(\d{4})$/.exec(phrase) ||
      /^([a-zA-Z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$/.exec(phrase);
    if (monthWordMatch) {
      let day, monthName, year;
      if (/^\d/.test(monthWordMatch[1])) {
        [, day, monthName, year] = monthWordMatch;
      } else {
        [, monthName, day, year] = monthWordMatch;
      }
      const monthIdx = MONTH_LOOKUP[monthName.toLowerCase()];
      if (monthIdx === undefined) {
        return { status: 'error', message: `"${monthName}" is not a recognized month name. Please provide the month in words, e.g. "22 September 2026".` };
      }
      const dk = dayKey(Number(year), monthIdx, Number(day));
      if (new Date(dk).getUTCMonth() !== monthIdx || new Date(dk).getUTCDate() !== Number(day)) {
        return { status: 'error', message: `"${phrase}" is not a valid calendar date.` };
      }
      return finishExplicitDate(dk, today);
    }

    // All-numeric date, e.g. 09/10/2026 or 09-10-2026 — day/month order is ambiguous.
    const numericMatch = /^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/.exec(phrase);
    if (numericMatch) {
      return {
        status: 'ambiguous',
        message: `"${phrase}" is ambiguous. Please provide the month in words, e.g. "22 September 2026".`,
        options: []
      };
    }

    // this <weekday> / next <weekday> / <weekday> next week / next week on <weekday> / bare <weekday>
    const weekdayNum = findWeekdayToken(lower);
    if (weekdayNum) {
      const thisWeekMonday = mondayOfWeekContaining(today);
      const thisWeekDate = addDays(thisWeekMonday, weekdayNum - 1);
      const nextWeekDate = addDays(thisWeekMonday, 7 + weekdayNum - 1);
      const wantsNextWeek = /\bnext\b/.test(lower);

      if (wantsNextWeek) {
        return { status: 'ok', dayKey: nextWeekDate, label: formatDayKey(nextWeekDate) };
      }

      const isBareOrThis = /\bthis\b/.test(lower) || !/next|last/.test(lower);
      if (isBareOrThis) {
        if (thisWeekDate < today) {
          return {
            status: 'error',
            message: `${WEEKDAY_NAMES[weekdayNum - 1]} of this week has already passed. Please provide another date.`
          };
        }
        return { status: 'ok', dayKey: thisWeekDate, label: formatDayKey(thisWeekDate) };
      }
    }

    return {
      status: 'error',
      message: `Could not understand the date "${phrase}". Please use a phrase like "tomorrow", "next Monday", or an explicit date such as "22 September 2026".`
    };
  }

  function finishExplicitDate(dk, today) {
    if (dk < today) {
      return { status: 'error', message: `${formatDayKey(dk)} is in the past. Please provide another date.` };
    }
    return { status: 'ok', dayKey: dk, label: formatDayKey(dk) };
  }

  const api = {
    nowInUae,
    dayKey,
    uaeTodayDayKey,
    isoWeekday,
    formatDayKey,
    toDateInputValue,
    fromDateInputValue,
    resolvePhrase,
    WEEKDAY_NAMES,
    MONTH_NAMES
  };

  const root = global.PH || (global.PH = {});
  root.dateUtils = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
