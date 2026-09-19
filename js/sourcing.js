(function () {
  const { sourcingPrompt, extract, templates } = window.PH;
  const el = (id) => document.getElementById(id);

  const state = {
    excludedOrgs: [...sourcingPrompt.EXCLUDED_ORGS],
    jdText: ''
  };

  // ---------- Static filter options ----------
  const geoBox = el('geoCheckboxes');
  sourcingPrompt.GEOGRAPHY_OPTIONS.forEach((country) => {
    const id = `geo-${country.replace(/\s+/g, '-')}`;
    const wrap = document.createElement('label');
    wrap.className = 'checkbox-inline';
    const checked = sourcingPrompt.DEFAULT_GEOGRAPHY.includes(country) ? 'checked' : '';
    wrap.innerHTML = `<input type="checkbox" id="${id}" value="${templates.escapeHtml(country)}" ${checked}> ${templates.escapeHtml(country)}`;
    geoBox.appendChild(wrap);
  });

  // ---------- Org exclusion chips ----------
  function renderOrgChips() {
    const box = el('orgChips');
    box.innerHTML = '';
    state.excludedOrgs.forEach((org, idx) => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML = `${templates.escapeHtml(org)} <button type="button" aria-label="Remove ${templates.escapeHtml(org)}">&times;</button>`;
      chip.querySelector('button').addEventListener('click', () => {
        state.excludedOrgs.splice(idx, 1);
        renderOrgChips();
      });
      box.appendChild(chip);
    });
  }
  renderOrgChips();

  el('orgAddBtn').addEventListener('click', () => {
    const input = el('orgAddInput');
    const val = input.value.trim();
    if (!val) return;
    if (!state.excludedOrgs.some((o) => o.toLowerCase() === val.toLowerCase())) {
      state.excludedOrgs.push(val);
      renderOrgChips();
    }
    input.value = '';
  });
  el('orgAddInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      el('orgAddBtn').click();
    }
  });

  // ---------- JD upload ----------
  const jdDropZone = el('jdDropZone');
  const jdInput = el('jdInput');

  async function handleJdFile(file) {
    const statusEl = el('jdStatus');
    if (!file) return;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!['pdf', 'docx', 'txt'].includes(ext)) {
      statusEl.innerHTML = `<span class="warn-text">"${templates.escapeHtml(file.name)}" is not a supported file type. Please use a PDF, DOCX, or TXT file.</span>`;
      return;
    }
    statusEl.textContent = 'Reading job description...';
    jdDropZone.classList.add('has-file');
    const result = await extract.extractRawText(file);
    if (result.warning) {
      statusEl.innerHTML = `<span class="warn-text">${templates.escapeHtml(result.warning)}</span>`;
    } else {
      state.jdText = result.text;
      statusEl.textContent = `Loaded "${file.name}" (${result.text.length.toLocaleString()} characters) — it will be included in the sourcing brief.`;
    }
  }

  jdInput.addEventListener('change', (e) => handleJdFile(e.target.files[0]));
  ['dragenter', 'dragover'].forEach((evt) =>
    jdDropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      jdDropZone.classList.add('dragover');
    })
  );
  ['dragleave', 'dragend'].forEach((evt) =>
    jdDropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      jdDropZone.classList.remove('dragover');
    })
  );
  jdDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    jdDropZone.classList.remove('dragover');
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) handleJdFile(file);
  });

  // ---------- Step 1: build brief ----------
  function collectFilterState() {
    const checkedCountries = Array.from(geoBox.querySelectorAll('input:checked')).map((cb) => cb.value);
    const global = el('geoGlobal').checked;
    const custom = el('geoCustom').value.trim();
    const usedDefault =
      !global &&
      !custom &&
      checkedCountries.length === sourcingPrompt.DEFAULT_GEOGRAPHY.length &&
      checkedCountries.every((c) => sourcingPrompt.DEFAULT_GEOGRAPHY.includes(c));

    return {
      jobTitle: el('jobTitle').value.trim(),
      yearsExperience: el('yearsExperience').value.trim(),
      industry: el('industry').value.trim(),
      companySize: el('companySize').value.trim(),
      targetCompanies: el('targetCompanies').value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
      keywords: el('keywords').value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
      briefingText: el('briefingText').value,
      jdText: state.jdText,
      geography: {
        countries: checkedCountries,
        global,
        custom,
        exclusions: el('geoExclusions').value.trim(),
        usedDefault
      },
      profileCount: Number(el('profileCount').value) || 15,
      sourcingDirection: document.querySelector('input[name="sourcingDirection"]:checked').value,
      excludedOrgs: state.excludedOrgs,
      hospitalBedPriority: el('hospitalBedPriority').checked
    };
  }

  el('generateBriefBtn').addEventListener('click', () => {
    const form = collectFilterState();
    if (!form.jobTitle && !form.briefingText && !form.jdText) {
      alert('Please provide a job title, a free-text briefing, or a job description file before generating a brief.');
      return;
    }
    const brief = sourcingPrompt.buildSourcingBrief(form);
    el('briefText').value = brief;
    el('briefOutput').classList.remove('hidden');
    el('briefCopyStatus').textContent = '';
  });

  el('copyBriefBtn').addEventListener('click', async () => {
    const text = el('briefText').value;
    try {
      await navigator.clipboard.writeText(text);
      el('briefCopyStatus').textContent = 'Copied to clipboard.';
    } catch (e) {
      const ta = el('briefText');
      ta.focus();
      ta.select();
      document.execCommand('copy');
      el('briefCopyStatus').textContent = 'Copied to clipboard.';
    }
  });

  el('downloadBriefBtn').addEventListener('click', () => {
    const blob = new Blob([el('briefText').value], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const slug = (el('jobTitle').value.trim() || 'candidate-sourcing').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    a.href = url;
    a.download = `${slug || 'candidate-sourcing'}-brief.txt`;
    a.click();
    URL.revokeObjectURL(url);
  });
})();
