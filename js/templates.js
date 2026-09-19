// Builds the candidate-facing email HTML and the subject line, per the
// agent's SUBJECT / IN-PERSON / ONLINE / EMAIL BODY rules.
(function (global) {
  const OFFICE_ADDRESS =
    'PureHealth, Aldar Headquarters Building, 6th Floor, Ar Rahah St, Al Rahah, RBW11, Abu Dhabi';
  const OFFICE_MAP_URL = 'https://maps.app.goo.gl/VeACRgR2JG29eShy7';
  const PUREHEALTH_URL = 'https://purehealth.ae/';
  const INTRO_FILENAME = 'PureHealth Introduction 2026.pdf';
  const RECRUITER_REMINDER =
    'Recruiter action required: Add the interviewer email addresses and review all details before sending this email.';

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function firstName(fullName) {
    return (fullName || '').trim().split(/\s+/)[0] || '';
  }

  function buildSubject(jobTitle, interviewType) {
    return `${jobTitle} - PureHealth interview - ${interviewType}`;
  }

  function interviewerLabel(count) {
    return count === 1 ? 'Interviewer' : 'Interviewers';
  }

  function interviewersHtmlList(interviewers) {
    return interviewers
      .map(
        (iv, idx) =>
          `${idx + 1}. ${escapeHtml(iv.name)}${iv.title ? `, ${escapeHtml(iv.title)}` : ''}`
      )
      .join('<br>');
  }

  function locationHtml(state) {
    if (state.interviewType === 'In Person') {
      return (
        `<strong>Office Address:</strong> ${escapeHtml(OFFICE_ADDRESS)}<br>` +
        `<a href="${OFFICE_MAP_URL}" target="_blank" rel="noopener">${OFFICE_MAP_URL}</a>`
      );
    }
    return `<a href="${escapeHtml(state.teamsUrl)}" target="_blank" rel="noopener">Join the Microsoft Teams interview</a>`;
  }

  /**
   * Builds the full Outlook-compatible HTML email body.
   * state: { candidateName, jobTitle, interviewType, teamsUrl, interviewers,
   *          dateLabel, timeLabel }
   */
  function buildEmailHtml(state) {
    const label = interviewerLabel(state.interviewers.length);
    return `<div style="font-family: Segoe UI, Arial, sans-serif; font-size: 14px; color: #222222; line-height: 1.5;">
  <p>Dear ${escapeHtml(firstName(state.candidateName))},</p>
  <p>Greetings,</p>
  <p>As discussed, kindly find the interview details below:</p>
  <table style="border-collapse: collapse; width: 100%; max-width: 560px; border: 1px solid #cccccc;">
    <tr>
      <td colspan="2" style="border: 1px solid #cccccc; padding: 10px 14px; background-color: #175a70; color: #ffffff; font-weight: bold; font-size: 15px;">
        Interview Details
      </td>
    </tr>
    <tr>
      <td style="border: 1px solid #cccccc; padding: 10px 14px; width: 38%;"><strong>Date</strong></td>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;">${escapeHtml(state.dateLabel)}</td>
    </tr>
    <tr>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;"><strong>Time</strong></td>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;">${escapeHtml(state.timeLabel)}</td>
    </tr>
    <tr>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;"><strong>Interview Location</strong></td>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;">${locationHtml(state)}</td>
    </tr>
    <tr>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;"><strong>${label}</strong></td>
      <td style="border: 1px solid #cccccc; padding: 10px 14px;">${interviewersHtmlList(state.interviewers)}</td>
    </tr>
  </table>
  <p>Please reply to this email to confirm your attendance. If you require any further assistance, please feel free to contact us.</p>
  <p>For more information about PureHealth, please visit our website at:<br>
  <a href="${PUREHEALTH_URL}" target="_blank" rel="noopener">${PUREHEALTH_URL}</a></p>
</div>`;
  }

  const api = {
    OFFICE_ADDRESS,
    OFFICE_MAP_URL,
    PUREHEALTH_URL,
    INTRO_FILENAME,
    RECRUITER_REMINDER,
    escapeHtml,
    firstName,
    buildSubject,
    interviewerLabel,
    interviewersHtmlList,
    locationHtml,
    buildEmailHtml
  };

  const root = global.PH || (global.PH = {});
  root.templates = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
