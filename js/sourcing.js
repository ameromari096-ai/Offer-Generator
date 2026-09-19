(function () {
  const { sourcingPrompt, extract, templates } = window.PH;
  const el = (id) => document.getElementById(id);

  const state = {
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

  // ---------- Reusable chip field: type a value, press Enter (or click Add) to add it as a chip ----------
  function createChipField(chipsId, inputId, addBtnId, initial) {
    const values = [...(initial || [])];
    const box = el(chipsId);
    const input = el(inputId);
    const addBtn = el(addBtnId);

    function render() {
      box.innerHTML = '';
      values.forEach((val, idx) => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.innerHTML = `${templates.escapeHtml(val)} <button type="button" aria-label="Remove ${templates.escapeHtml(val)}">&times;</button>`;
        chip.querySelector('button').addEventListener('click', () => {
          values.splice(idx, 1);
          render();
        });
        box.appendChild(chip);
      });
    }

    function addFromInput() {
      const val = input.value.trim();
      if (!val) return;
      if (!values.some((v) => v.toLowerCase() === val.toLowerCase())) {
        values.push(val);
        render();
      }
      input.value = '';
    }

    addBtn.addEventListener('click', addFromInput);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addFromInput();
      }
    });

    render();
    return { getValues: () => values.slice() };
  }

  const orgField = createChipField('orgChips', 'orgAddInput', 'orgAddBtn', sourcingPrompt.EXCLUDED_ORGS);
  const jobTitleField = createChipField('jobTitleChips', 'jobTitleInput', 'jobTitleAddBtn');
  const industryField = createChipField('industryChips', 'industryInput', 'industryAddBtn');
  const companySizeField = createChipField('companySizeChips', 'companySizeInput', 'companySizeAddBtn');
  const targetCompanyField = createChipField('targetCompanyChips', 'targetCompanyInput', 'targetCompanyAddBtn');
  const keywordField = createChipField('keywordChips', 'keywordInput', 'keywordAddBtn');
  const geoCustomField = createChipField('geoCustomChips', 'geoCustomInput', 'geoCustomAddBtn');

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
    const customLocations = geoCustomField.getValues();

    return {
      jobTitle: jobTitleField.getValues(),
      yearsExperience: el('yearsExperience').value.trim(),
      industry: industryField.getValues(),
      companySize: companySizeField.getValues(),
      targetCompanies: targetCompanyField.getValues(),
      keywords: keywordField.getValues(),
      briefingText: el('briefingText').value,
      jdText: state.jdText,
      geography: {
        countries: checkedCountries,
        global,
        customLocations,
        exclusions: el('geoExclusions').value.trim()
      },
      profileCount: Number(el('profileCount').value) || 15,
      sourcingDirection: document.querySelector('input[name="sourcingDirection"]:checked').value,
      excludedOrgs: orgField.getValues()
    };
  }

  el('generateBriefBtn').addEventListener('click', () => {
    const form = collectFilterState();
    if (!form.jobTitle.length && !form.briefingText && !form.jdText) {
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
    const slug = (jobTitleField.getValues()[0] || 'candidate-sourcing').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    a.href = url;
    a.download = `${slug || 'candidate-sourcing'}-brief.txt`;
    a.click();
    URL.revokeObjectURL(url);
  });
})();
