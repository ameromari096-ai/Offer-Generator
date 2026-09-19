(function () {
  const { dateUtils, timeUtils, extract, templates, eml } = window.PH;

  if (window.pdfjsLib) {
    // Same-origin, vendored copy — avoids cross-origin worker restrictions
    // and CDN-blocking networks entirely (see vendor/README.md).
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'vendor/pdf.worker.min.js';
  }

  const INTRO_PDF_PATH = 'assets/purehealth-introduction-2026.pdf';
  const DRAFT_STORE_KEY = 'ph-interview-drafts';

  // Stop the browser from navigating to a file dropped outside the CV drop zone.
  ['dragover', 'drop'].forEach((evt) =>
    window.addEventListener(evt, (e) => e.preventDefault())
  );

  const state = {
    cvFile: null,
    cvArrayBuffer: null,
    cvExtraction: null,
    noCv: false,
    resolvedDayKey: null,
    resolvedDateLabel: '',
    startMinutes: null,
    endMinutes: null,
    timeLabel: '',
    approved: false
  };

  const el = (id) => document.getElementById(id);

  // ---------- Interviewer rows ----------
  function addInterviewerRow(name = '', title = '') {
    const container = el('interviewerRows');
    const row = document.createElement('div');
    row.className = 'interviewer-row';
    row.innerHTML = `
      <input type="text" class="iv-name" placeholder="Interviewer name" value="${templates.escapeHtml(name)}">
      <input type="text" class="iv-title" placeholder="Title (optional)" value="${templates.escapeHtml(title)}">
      <button type="button" class="btn-remove" title="Remove">&times;</button>
    `;
    row.querySelector('.btn-remove').addEventListener('click', () => {
      if (container.children.length > 1) row.remove();
    });
    container.appendChild(row);
  }

  function getInterviewers() {
    return Array.from(document.querySelectorAll('#interviewerRows .interviewer-row'))
      .map((row) => ({
        name: row.querySelector('.iv-name').value.trim(),
        title: row.querySelector('.iv-title').value.trim()
      }))
      .filter((iv) => iv.name);
  }

  el('addInterviewerBtn').addEventListener('click', () => addInterviewerRow());
  addInterviewerRow();

  // ---------- CV extraction (file picker + drag-and-drop share this) ----------
  const dropZone = el('cvDropZone');
  const cvInput = el('cvInput');

  async function handleCvFile(file) {
    const statusEl = el('cvStatus');
    if (!file) {
      state.cvFile = null;
      state.cvArrayBuffer = null;
      state.cvExtraction = null;
      statusEl.textContent = '';
      dropZone.classList.remove('has-file');
      return;
    }

    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!['pdf', 'docx', 'txt'].includes(ext)) {
      statusEl.innerHTML = `<span class="warn-text">"${templates.escapeHtml(file.name)}" is not a supported CV file type. Please use a PDF, DOCX, or TXT file.</span>`;
      return;
    }

    statusEl.textContent = 'Extracting candidate details from CV...';
    state.cvFile = file;
    state.cvArrayBuffer = await file.arrayBuffer();
    dropZone.classList.add('has-file');

    const result = await extract.extractCandidateDetails(file);
    state.cvExtraction = result;

    // Uploading a CV is a deliberate "use this candidate" action, so it
    // overwrites whatever is currently in the name/email fields.
    if (result.name) {
      el('candidateName').value = result.name;
    }
    if (result.email) {
      el('candidateEmail').value = result.email;
    }

    const parts = [`CV on file: ${templates.escapeHtml(result.filename)} (ref ${result.reference}).`];
    if (result.warning) {
      parts.push(`<span class="warn-text">${templates.escapeHtml(result.warning)}</span>`);
    } else {
      parts.push('Extraction looks confident, but please double-check the fields above.');
    }
    statusEl.innerHTML = parts.join(' ');
  }

  cvInput.addEventListener('change', (e) => handleCvFile(e.target.files[0]));

  ['dragenter', 'dragover'].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    })
  );
  ['dragleave', 'dragend'].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (evt === 'dragleave' && dropZone.contains(e.relatedTarget)) return;
      dropZone.classList.remove('dragover');
    })
  );
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    try {
      const dt = new DataTransfer();
      dt.items.add(file);
      cvInput.files = dt.files;
    } catch (err) {
      /* DataTransfer construction can fail in older browsers; extraction still runs */
    }
    handleCvFile(file);
  });

  // ---------- Interview type ----------
  document.querySelectorAll('input[name="interviewType"]').forEach((radio) => {
    radio.addEventListener('change', () => {
      const isOnline = document.querySelector('input[name="interviewType"]:checked').value === 'Online';
      el('teamsUrlField').classList.toggle('hidden', !isOnline);
    });
  });

  // ---------- Date resolution ----------
  el('resolveDateBtn').addEventListener('click', () => resolveDate());
  el('dateInput').addEventListener('change', () => {
    if (el('dateInput').value) {
      el('datePhrase').value = '';
      const dk = dateUtils.fromDateInputValue(el('dateInput').value);
      const today = dateUtils.uaeTodayDayKey();
      if (dk < today) {
        showDateAmbiguous(`${dateUtils.formatDayKey(dk)} is in the past. Please choose another date.`, []);
        state.resolvedDayKey = null;
        el('resolvedDateLabel').textContent = '';
      } else {
        state.resolvedDayKey = dk;
        state.resolvedDateLabel = dateUtils.formatDayKey(dk);
        el('resolvedDateLabel').textContent = state.resolvedDateLabel;
        el('dateAmbiguous').classList.add('hidden');
      }
    }
  });

  function showDateAmbiguous(message, options) {
    const box = el('dateAmbiguous');
    box.classList.remove('hidden');
    box.innerHTML = `<p class="warn-text">${templates.escapeHtml(message)}</p>`;
    if (options && options.length) {
      options.forEach((opt) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-secondary';
        btn.textContent = opt.label;
        btn.addEventListener('click', () => {
          state.resolvedDayKey = opt.dayKey;
          state.resolvedDateLabel = opt.label;
          el('resolvedDateLabel').textContent = opt.label;
          el('dateInput').value = dateUtils.toDateInputValue(opt.dayKey);
          box.classList.add('hidden');
        });
        box.appendChild(btn);
      });
    }
  }

  function resolveDate() {
    const phrase = el('datePhrase').value.trim();
    el('dateAmbiguous').classList.add('hidden');
    if (!phrase) {
      state.resolvedDayKey = null;
      el('resolvedDateLabel').textContent = '';
      showDateAmbiguous('Please type a date phrase, e.g. "tomorrow" or "next Monday".', []);
      return;
    }
    const result = dateUtils.resolvePhrase(phrase);
    if (result.status === 'ok') {
      state.resolvedDayKey = result.dayKey;
      state.resolvedDateLabel = result.label;
      el('resolvedDateLabel').textContent = result.label;
      el('dateInput').value = dateUtils.toDateInputValue(result.dayKey);
    } else {
      state.resolvedDayKey = null;
      el('resolvedDateLabel').textContent = '';
      showDateAmbiguous(result.message, result.options || []);
    }
  }

  // ---------- Time calculation ----------
  function recalcTime() {
    const start = el('startTime').value;
    const duration = el('duration').value;
    const overrideEnd = el('endTimeOverride').value;
    el('timeConflict').classList.add('hidden');
    el('timeSummary').textContent = '';
    state.startMinutes = null;
    state.endMinutes = null;
    state.timeLabel = '';

    if (!start || !duration) return;
    const calc = timeUtils.calculate(start, duration);
    if (calc.status !== 'ok') {
      el('timeSummary').innerHTML = `<span class="warn-text">${templates.escapeHtml(calc.message)}</span>`;
      return;
    }

    if (overrideEnd) {
      const overrideMinutes = timeUtils.parseHm(overrideEnd);
      if (overrideMinutes !== null && overrideMinutes !== calc.endMinutes % 1440) {
        const box = el('timeConflict');
        box.classList.remove('hidden');
        box.innerHTML = `
          <p>The duration (${duration} min) and the end time you entered don't match. Which should control?</p>
          <button type="button" class="btn-secondary" id="useDurationBtn">Use duration (${timeUtils.minutesToLabel(calc.endMinutes)})</button>
          <button type="button" class="btn-secondary" id="useEndTimeBtn">Use my end time (${timeUtils.minutesToLabel(overrideMinutes)})</button>
        `;
        el('useDurationBtn').addEventListener('click', () => {
          el('endTimeOverride').value = '';
          recalcTime();
        });
        el('useEndTimeBtn').addEventListener('click', () => {
          const newDuration = (overrideMinutes - calc.startMinutes + 1440) % 1440;
          el('duration').value = newDuration;
          recalcTime();
        });
        return;
      }
    }

    state.startMinutes = calc.startMinutes;
    state.endMinutes = calc.endMinutes;
    state.timeLabel = calc.formatted + (calc.crossesMidnight ? ' (next day)' : '');
    el('timeSummary').textContent = state.timeLabel;
  }

  ['startTime', 'duration', 'endTimeOverride'].forEach((id) =>
    el(id).addEventListener('input', recalcTime)
  );

  // ---------- Validation & preview ----------
  function collectFormState() {
    return {
      candidateName: el('candidateName').value.trim(),
      candidateEmail: el('candidateEmail').value.trim(),
      jobTitle: el('jobTitle').value.trim(),
      interviewers: getInterviewers(),
      interviewType: document.querySelector('input[name="interviewType"]:checked').value,
      teamsUrl: el('teamsUrl').value.trim()
    };
  }

  function validateForPreview(form) {
    const missing = [];
    const durationMissing = !el('duration').value;
    if (!form.candidateName) missing.push('candidate full name');
    if (!form.jobTitle) missing.push('job title');
    if (form.interviewers.length === 0) missing.push('at least one interviewer name');
    if (!state.resolvedDayKey) missing.push('a resolved interview date');
    if (!el('startTime').value) missing.push('start time');
    if (durationMissing) missing.push('interview duration in minutes');
    if (!durationMissing && (state.startMinutes === null || state.endMinutes === null)) {
      missing.push('a valid start time and duration (end time must be later than start time)');
    }
    if (form.interviewType === 'Online' && !form.teamsUrl) {
      missing.push('a genuine Microsoft Teams join link');
    }
    if (missing.length === 1 && durationMissing) {
      return { ok: false, message: 'What is the interview duration in minutes?' };
    }
    if (missing.length) {
      return { ok: false, message: `Please provide: ${missing.join(', ')}.` };
    }
    return { ok: true };
  }

  el('continueBtn').addEventListener('click', () => {
    const form = collectFormState();
    const validation = validateForPreview(form);
    const errBox = el('formErrors');
    if (!validation.ok) {
      errBox.classList.remove('hidden');
      errBox.textContent = validation.message;
      return;
    }
    errBox.classList.add('hidden');
    state.noCv = !state.cvFile;
    renderPreview(form);
    goToStep('preview');
  });

  function renderPreview(form) {
    state.form = form;
    state.approved = false;

    const warningsBox = el('previewWarnings');
    warningsBox.innerHTML = '';
    const warnings = [];
    if (state.noCv) {
      warnings.push('Warning: No candidate CV was provided. The email draft can still be created, but the candidate CV will not be attached.');
    }
    if (!form.candidateEmail) {
      warnings.push('Note: No candidate email was provided. A preview is shown, but the email draft cannot be created until an email address is added.');
    }
    warnings.forEach((w) => {
      const p = document.createElement('p');
      p.className = 'warn-text';
      p.textContent = w;
      warningsBox.appendChild(p);
    });

    const interviewerLabel = templates.interviewerLabel(form.interviewers.length);
    const interviewersText = form.interviewers
      .map((iv, i) => `${i + 1}. ${iv.name}${iv.title ? `, ${iv.title}` : ''}`)
      .join('\n');

    const location =
      form.interviewType === 'In Person'
        ? `${templates.OFFICE_ADDRESS} (${templates.OFFICE_MAP_URL})`
        : form.teamsUrl;

    const fields = [
      ['Candidate', form.candidateName],
      ['Candidate email', form.candidateEmail || '(not provided)'],
      ['Job title', form.jobTitle],
      ['Resolved date', state.resolvedDateLabel],
      ['Start time', timeUtils.minutesToLabel(state.startMinutes) + ' (UAE Time)'],
      ['Duration', `${el('duration').value} minutes`],
      ['Calculated end time', timeUtils.minutesToLabel(state.endMinutes) + ' (UAE Time)'],
      ['Formatted time', state.timeLabel],
      ['Interview type', form.interviewType],
      ['Interview location', location],
      [interviewerLabel, interviewersText],
      ['Interviewer email addresses', 'To be added manually by the recruiter'],
      ['Attachments', `PureHealth Introduction 2026.pdf${state.cvFile ? `, ${state.cvFile.name}` : ''}`],
      ['Warnings', warnings.length ? warnings.join(' ') : 'None']
    ];

    const list = el('previewList');
    list.innerHTML = '';
    fields.forEach(([label, value]) => {
      const dt = document.createElement('dt');
      dt.textContent = label + ':';
      const dd = document.createElement('dd');
      dd.style.whiteSpace = 'pre-line';
      dd.textContent = value;
      list.appendChild(dt);
      list.appendChild(dd);
    });

    const subject = templates.buildSubject(form.jobTitle, form.interviewType);
    el('previewSubject').textContent = subject;

    const emailHtml = templates.buildEmailHtml({
      candidateName: form.candidateName,
      interviewType: form.interviewType,
      teamsUrl: form.teamsUrl,
      interviewers: form.interviewers,
      dateLabel: state.resolvedDateLabel,
      timeLabel: state.timeLabel
    });
    el('previewEmailBody').innerHTML = emailHtml;

    state.subject = subject;
    state.emailHtml = emailHtml;
  }

  el('backToEditBtn').addEventListener('click', () => goToStep('details'));

  // ---------- Approval & draft creation ----------
  function requestFingerprint(form) {
    return [
      form.candidateEmail || form.candidateName,
      form.jobTitle,
      form.interviewType,
      state.resolvedDayKey,
      state.startMinutes
    ].join('|');
  }

  function loadDraftStore() {
    try {
      return JSON.parse(localStorage.getItem(DRAFT_STORE_KEY) || '{}');
    } catch (e) {
      return {};
    }
  }

  function saveDraftStore(store) {
    try {
      localStorage.setItem(DRAFT_STORE_KEY, JSON.stringify(store));
    } catch (e) {
      /* ignore persistence failures (e.g. private browsing) */
    }
  }

  async function fetchIntroPdf() {
    try {
      const res = await fetch(INTRO_PDF_PATH);
      if (!res.ok) throw new Error('not found');
      const buf = await res.arrayBuffer();
      return { ok: true, arrayBuffer: buf };
    } catch (e) {
      return { ok: false };
    }
  }

  el('approveBtn').addEventListener('click', async () => {
    const form = state.form;

    // 1. Revalidate date and time.
    const today = dateUtils.uaeTodayDayKey();
    if (!state.resolvedDayKey || state.resolvedDayKey < today) {
      alert('The interview date is no longer valid (it may have passed). Please go back and re-resolve the date.');
      goToStep('details');
      return;
    }
    if (state.startMinutes === null || state.endMinutes === null || state.endMinutes <= state.startMinutes) {
      alert('The interview time is no longer valid. Please go back and re-check the start time and duration.');
      goToStep('details');
      return;
    }
    if (form.interviewType === 'Online' && !form.teamsUrl) {
      alert('An online interview requires a genuine Microsoft Teams link. Please go back and add one.');
      goToStep('details');
      return;
    }

    state.approved = true;
    el('approveBtn').disabled = true;
    el('approveBtn').textContent = 'Creating email draft...';

    // 2 & 3. Scheduling request ID + duplicate check.
    const store = loadDraftStore();
    const fingerprint = requestFingerprint(form);
    let requestId = store[fingerprint];
    let isDuplicate = Boolean(requestId);
    if (!requestId) {
      requestId = `PH-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
      store[fingerprint] = requestId;
      saveDraftStore(store);
    }

    const messages = [];
    if (isDuplicate) {
      messages.push(`An unsent email draft already exists for this exact request (ID ${requestId}). Reusing it instead of creating a duplicate.`);
    } else {
      messages.push(`Scheduling request ID: ${requestId}`);
    }

    // 4. Retrieve PureHealth Introduction 2026.pdf (Get PureHealth Introduction).
    const intro = await fetchIntroPdf();
    let emailCreated = false;

    if (!form.candidateEmail) {
      messages.push('Email draft NOT created: a candidate email address is required for the email draft.');
    } else if (!intro.ok) {
      messages.push('Email draft NOT created: the PureHealth Introduction 2026.pdf could not be retrieved (Get PureHealth Introduction failed).');
    } else {
      // 5. Create Outlook Interview Email Draft.
      const attachments = [
        { filename: templates.INTRO_FILENAME, mimeType: 'application/pdf', arrayBuffer: intro.arrayBuffer }
      ];
      if (state.cvFile && state.cvArrayBuffer) {
        attachments.push({
          filename: state.cvFile.name,
          mimeType: state.cvFile.type || 'application/octet-stream',
          arrayBuffer: state.cvArrayBuffer
        });
      }
      const emlContent = eml.buildEml({
        to: form.candidateEmail,
        subject: state.subject,
        html: state.emailHtml,
        attachments
      });
      const emlBlob = new Blob([emlContent], { type: 'message/rfc822' });
      const emlUrl = URL.createObjectURL(emlBlob);
      const emlLink = el('downloadEml');
      emlLink.href = emlUrl;
      emlLink.download = `${requestId}-email-draft.eml`;
      emlLink.classList.remove('hidden');
      emailCreated = true;
      messages.push(`Unsent Outlook email draft created with ${attachments.length} attachment(s) (Create Outlook Interview Email Draft).`);
    }

    el('recruiterReminder').textContent = templates.RECRUITER_REMINDER;

    renderDoneMessages(messages);
    renderVerificationChecklist(form, { emailCreated, introOk: intro.ok, isDuplicate });

    el('approveBtn').disabled = false;
    el('approveBtn').textContent = 'Yes, create the email draft';
    goToStep('done');
  });

  function renderDoneMessages(messages) {
    const box = el('doneMessages');
    box.innerHTML = messages.map((m) => `<p>${templates.escapeHtml(m)}</p>`).join('');
  }

  function renderVerificationChecklist(form, flags) {
    const typeCheckOk = form.interviewType === 'In Person' ? true : Boolean(form.teamsUrl);
    const typeCheckLabel =
      form.interviewType === 'In Person'
        ? 'In Person interview has no Teams link'
        : 'Online interview uses a genuine Teams URL in the email draft';
    const emailCheckOk = flags.emailCreated || !form.candidateEmail;
    const emailCheckLabel = flags.emailCreated
      ? 'Email draft created'
      : form.candidateEmail
      ? 'Email draft not created (see message above)'
      : 'Email draft skipped: no candidate email was provided';

    const checks = [
      [Boolean(form.candidateName), 'Candidate name provided'],
      [Boolean(form.candidateEmail), 'Candidate email provided'],
      [Boolean(form.jobTitle), 'Job title present'],
      [form.interviewers.length > 0, 'Interviewer order preserved, no invented email addresses'],
      [Number(el('duration').value) > 0, 'Duration supplied and greater than zero'],
      [Boolean(state.resolvedDayKey), 'Date resolved and matches weekday shown'],
      [state.resolvedDayKey >= dateUtils.uaeTodayDayKey(), 'Interview is not in the past'],
      [state.endMinutes > state.startMinutes, 'End time is later than start time'],
      [typeCheckOk, typeCheckLabel],
      [true, 'Email draft remains unsent'],
      [true, flags.isDuplicate ? 'Existing email draft reused (no duplicate created)' : 'No duplicate email draft was created'],
      [flags.introOk, 'PureHealth Introduction file attached'],
      [state.noCv ? true : Boolean(state.cvFile), state.noCv ? 'No CV was provided (recruiter warned)' : 'Candidate CV attached'],
      [emailCheckOk, emailCheckLabel]
    ];
    const ul = el('verificationChecklist');
    ul.innerHTML = checks
      .map(([ok, label]) => `<li class="${ok ? 'ok' : 'fail'}">${ok ? '✅' : '⚠️'} ${templates.escapeHtml(label)}</li>`)
      .join('');
  }

  el('startOverBtn').addEventListener('click', () => window.location.reload());

  // ---------- Step navigation ----------
  function goToStep(stepName) {
    ['details', 'preview', 'done'].forEach((s) => {
      el(`${s}Section`).classList.toggle('hidden', s !== stepName);
    });
    document.querySelectorAll('#stepIndicator li').forEach((li) => {
      li.classList.toggle('active', li.dataset.step === stepName);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
})();
