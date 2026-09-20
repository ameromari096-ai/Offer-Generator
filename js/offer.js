(function () {
  const { extract, offerTemplates, eml } = window.PH;

  if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'vendor/pdf.worker.min.js';
  }

  // Stop the browser from navigating to a file dropped outside the drop zone.
  ['dragover', 'drop'].forEach((evt) =>
    window.addEventListener(evt, (e) => e.preventDefault())
  );

  const state = {
    contractFile: null,
    contractArrayBuffer: null,
    contractExtraction: null
  };

  const el = (id) => document.getElementById(id);

  const MIME_TYPES = {
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    txt: 'text/plain'
  };

  function mimeTypeFor(filename) {
    const ext = (filename.split('.').pop() || '').toLowerCase();
    return MIME_TYPES[ext] || 'application/octet-stream';
  }

  // ---------- Fixed onboarding documents list ----------
  el('fixedAttachmentsList').innerHTML = offerTemplates.FIXED_ATTACHMENTS.map(
    (name) => `<li>${offerTemplates.escapeHtml(name)}</li>`
  ).join('');

  el('formsLink').value = offerTemplates.DEFAULT_FORMS_LINK;

  // ---------- Contract extraction (file picker + drag-and-drop share this) ----------
  const dropZone = el('contractDropZone');
  const contractInput = el('contractInput');

  async function handleContractFile(file) {
    const statusEl = el('contractStatus');
    if (!file) {
      state.contractFile = null;
      state.contractArrayBuffer = null;
      state.contractExtraction = null;
      statusEl.textContent = '';
      dropZone.classList.remove('has-file');
      return;
    }

    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!['pdf', 'docx', 'txt'].includes(ext)) {
      statusEl.innerHTML = `<span class="warn-text">"${offerTemplates.escapeHtml(file.name)}" is not a supported file type. Please use a PDF, DOCX, or TXT file.</span>`;
      return;
    }

    statusEl.textContent = 'Extracting candidate details from the contract/offer letter...';
    state.contractFile = file;
    state.contractArrayBuffer = await file.arrayBuffer();
    dropZone.classList.add('has-file');

    const result = await extract.extractContractDetails(file);
    state.contractExtraction = result;

    // Uploading a contract is a deliberate "use this candidate" action, so
    // it overwrites whatever is currently in the name/email/job title fields.
    if (result.name) {
      el('candidateName').value = result.name;
    }
    if (result.email) {
      el('candidateEmail').value = result.email;
    }
    if (result.jobTitle) {
      el('jobTitle').value = result.jobTitle;
    }

    const parts = [`Contract on file: ${offerTemplates.escapeHtml(result.filename)} (ref ${result.reference}).`];
    if (result.warning) {
      parts.push(`<span class="warn-text">${offerTemplates.escapeHtml(result.warning)}</span>`);
    } else {
      parts.push('Extraction looks confident, but please double-check the fields above.');
    }
    statusEl.innerHTML = parts.join(' ');
  }

  contractInput.addEventListener('change', (e) => handleContractFile(e.target.files[0]));

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
      contractInput.files = dt.files;
    } catch (err) {
      /* DataTransfer construction can fail in older browsers; extraction still runs */
    }
    handleContractFile(file);
  });

  // ---------- Validation & preview ----------
  function collectFormState() {
    return {
      candidateName: el('candidateName').value.trim(),
      candidateEmail: el('candidateEmail').value.trim(),
      jobTitle: el('jobTitle').value.trim(),
      formsLink: el('formsLink').value.trim()
    };
  }

  function validateForPreview(form) {
    const missing = [];
    if (!state.contractFile) missing.push('the candidate\'s employment contract or offer letter (upload it above)');
    if (!form.candidateName) missing.push('candidate full name');
    if (!form.candidateEmail) missing.push('candidate email');
    if (!form.jobTitle) missing.push('job title');
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
    renderPreview(form);
    goToStep('preview');
  });

  function renderPreview(form) {
    state.form = form;

    const warningsBox = el('previewWarnings');
    warningsBox.innerHTML = '';
    const warnings = [];
    if (!form.formsLink) {
      warnings.push('Note: No onboarding documents form link was provided — that line will show an empty link.');
    }
    warnings.forEach((w) => {
      const p = document.createElement('p');
      p.className = 'warn-text';
      p.textContent = w;
      warningsBox.appendChild(p);
    });

    const contractAttachmentName = offerTemplates.contractAttachmentFilename(
      form.candidateName,
      state.contractFile.name
    );

    const fields = [
      ['Candidate', form.candidateName],
      ['Candidate email', form.candidateEmail],
      ['Job title', form.jobTitle],
      ['Onboarding documents form link', form.formsLink || '(not provided)'],
      [
        'Attachments',
        [contractAttachmentName, ...offerTemplates.FIXED_ATTACHMENTS].join('\n')
      ],
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

    const subject = offerTemplates.buildSubject();
    el('previewSubject').textContent = subject;

    const emailHtml = offerTemplates.buildEmailHtml(form);
    el('previewEmailBody').innerHTML = emailHtml;

    state.subject = subject;
    state.emailHtml = emailHtml;
    state.contractAttachmentName = contractAttachmentName;
  }

  el('backToEditBtn').addEventListener('click', () => goToStep('details'));

  // ---------- Approval & draft creation ----------
  async function fetchFixedAttachments() {
    const results = [];
    for (const filename of offerTemplates.FIXED_ATTACHMENTS) {
      try {
        const res = await fetch(offerTemplates.FIXED_ATTACHMENTS_DIR + encodeURIComponent(filename));
        if (!res.ok) throw new Error('not found');
        const buf = await res.arrayBuffer();
        results.push({ filename, mimeType: mimeTypeFor(filename), arrayBuffer: buf, ok: true });
      } catch (e) {
        results.push({ filename, ok: false });
      }
    }
    return results;
  }

  el('approveBtn').addEventListener('click', async () => {
    const form = state.form;
    el('approveBtn').disabled = true;
    el('approveBtn').textContent = 'Creating email draft...';

    const fixedResults = await fetchFixedAttachments();
    const fixedOk = fixedResults.filter((r) => r.ok);
    const fixedFailed = fixedResults.filter((r) => !r.ok);

    const attachments = [
      {
        filename: state.contractAttachmentName,
        mimeType: mimeTypeFor(state.contractFile.name),
        arrayBuffer: state.contractArrayBuffer
      },
      ...fixedOk.map((r) => ({ filename: r.filename, mimeType: r.mimeType, arrayBuffer: r.arrayBuffer }))
    ];

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
    emlLink.download = `${form.candidateName} - Offer Email Draft.eml`;
    emlLink.classList.remove('hidden');

    const messages = [
      `Unsent Outlook email draft created with ${attachments.length} attachment(s): the employment contract plus the ${fixedOk.length} standard onboarding document(s).`
    ];
    if (fixedFailed.length) {
      messages.push(
        `Warning: ${fixedFailed.length} standard document(s) could not be attached (${fixedFailed
          .map((r) => r.filename)
          .join(', ')}). The draft was still created without them — add them manually before sending.`
      );
    }

    el('recruiterReminder').textContent =
      'Recruiter action required: Review the attached documents and the candidate details before sending this email.';

    renderDoneMessages(messages);
    renderVerificationChecklist(form, { fixedFailed });

    el('approveBtn').disabled = false;
    el('approveBtn').textContent = 'Yes, create the email draft';
    goToStep('done');
  });

  function renderDoneMessages(messages) {
    const box = el('doneMessages');
    box.innerHTML = messages.map((m) => `<p>${offerTemplates.escapeHtml(m)}</p>`).join('');
  }

  function renderVerificationChecklist(form, flags) {
    const checks = [
      [Boolean(form.candidateName), 'Candidate name provided'],
      [Boolean(form.candidateEmail), 'Candidate email provided'],
      [Boolean(form.jobTitle), 'Job title present'],
      [Boolean(state.contractFile), 'Employment contract / offer letter attached'],
      [flags.fixedFailed.length === 0, 'All standard onboarding documents attached'],
      [true, 'Email draft remains unsent']
    ];
    const ul = el('verificationChecklist');
    ul.innerHTML = checks
      .map(([ok, label]) => `<li class="${ok ? 'ok' : 'fail'}">${ok ? '✅' : '⚠️'} ${offerTemplates.escapeHtml(label)}</li>`)
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
