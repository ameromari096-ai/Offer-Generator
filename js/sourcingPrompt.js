// Builds the "Sourcing Brief" document handed to an AI agent that can
// actually browse the live web (this static site has no server, no LinkedIn
// API access, and no hidden API keys to call an LLM itself — see the
// Candidate Sourcing section of the main README for why). The brief embeds
// the full sourcing ruleset plus every parameter chosen in the filter panel,
// and asks for the result back as JSON matching CANDIDATE_SCHEMA_EXAMPLE so
// it can be pasted into this tool's "Import results" step and turned into a
// real, rule-checked .xlsx file.
(function (global) {
  const EXCLUDED_ORGS = [
    'PureHealth', 'The Medical Office', 'OneHealth', 'The Life Corner', 'TalentOne',
    'Daman', 'SEHA', 'SEHA Clinics', 'SSMC', 'Rafed', 'PureCS', 'Circle Health Group',
    'Hellenic Health Group', 'Tamouh', 'PureLab', 'Sakina', 'Pura'
  ];

  const GEOGRAPHY_OPTIONS = [
    'United Arab Emirates', 'Saudi Arabia', 'Qatar', 'Kuwait', 'Bahrain', 'Oman', 'Egypt'
  ];
  const DEFAULT_GEOGRAPHY = ['United Arab Emirates'];

  const SENIORITY_OPTIONS = [
    'Not specified', 'Entry-level', 'Associate', 'Mid-Senior', 'Director', 'VP', 'Executive/C-level'
  ];

  const CANDIDATE_SCHEMA_EXAMPLE = {
    candidateName: 'Full name as shown on LinkedIn',
    currentTitle: 'Current job title',
    currentCompany: 'Current employer',
    currentLocation: 'City, Country',
    linkedinUrl: 'https://www.linkedin.com/in/their-real-handle',
    organizationBrief: [
      'Bullet 1: headcount/size, 8-20 words',
      'Bullet 2: bed count if a hospital, or other size signal, 8-20 words',
      'Bullet 3: another relevant fact about the organization, 8-20 words'
    ],
    shortlistRationale: [
      'Bullet 1: compares the candidate against the brief/JD, 8-20 words',
      'Bullet 2: compares the candidate against the brief/JD, 8-20 words',
      'Bullet 3: compares the candidate against the brief/JD, 8-20 words'
    ],
    candidateBrief: [
      'Bullet 1: total years of relevant experience, with a number, 8-20 words',
      'Bullet 2: industries/sectors worked in, named specifically, 8-20 words',
      'Bullet 3: the strongest specific link to the brief/JD, 8-20 words'
    ],
    matchScore: 82,
    confidence: 'High'
  };

  function bulletsOrNote(list) {
    const items = (list || []).filter(Boolean);
    return items.length ? items.map((s) => `  - ${s}`).join('\n') : '  (none specified)';
  }

  /**
   * state: {
   *   jobTitle, seniority, industry, mustHaves: string[], briefingText, jdText,
   *   geography: { countries: string[], global: boolean, custom: string, exclusions: string, usedDefault: boolean },
   *   profileCount, sourcingDirection: 'external'|'internal', excludedOrgs: string[],
   *   hospitalBedPriority: boolean
   * }
   */
  function buildSourcingBrief(state) {
    const geoParts = [];
    if (state.geography.global) geoParts.push('Global (no geographic restriction)');
    geoParts.push(...state.geography.countries);
    if (state.geography.custom) geoParts.push(state.geography.custom);
    const geoLine = geoParts.length ? geoParts.join(', ') : 'United Arab Emirates';
    const geoNote = state.geography.usedDefault
      ? ' (not specified by the requester — defaulted to PureHealth\'s primary market; adjust if a different market applies)'
      : '';

    const orgList = state.sourcingDirection === 'internal'
      ? `INTERNAL SOURCING REQUESTED — search ONLY within these entities (do not exclude them):\n${bulletsOrNote(state.excludedOrgs)}`
      : `EXCLUDE candidates currently employed at any of the following (and any other confirmed PureHealth-affiliated entity), unless it is one of the target companies for internal mobility:\n${bulletsOrNote(state.excludedOrgs)}`;

    const targetCount = Number(state.profileCount) || 15;
    const hardBudget = targetCount * 8;

    return `You are a Candidate Sourcing Agent. Find REAL LinkedIn-based candidates matching the role below and deliver them as a structured shortlist. Do not fabricate a candidate or a LinkedIn URL under any circumstance — only include profiles you actually found via live search.

=== ROLE BRIEF ===
Job title: ${state.jobTitle || '(not specified — infer from the briefing text below)'}
Seniority: ${state.seniority}
Industry: ${state.industry || '(infer from the briefing/JD)'}
Must-haves / required skills:
${bulletsOrNote(state.mustHaves)}

Free-text briefing:
${state.briefingText ? state.briefingText.trim() : '(none provided)'}

${state.jdText ? `Attached/pasted job description:\n${state.jdText.trim()}\n` : ''}
=== SEARCH PARAMETERS ===
Target geography: ${geoLine}${geoNote}
${state.geography.exclusions ? `Geographic exclusions: ${state.geography.exclusions}\n` : ''}Number of profiles required: ${targetCount} — this is a REQUIREMENT, not a target to approximate. Do not stop short of it unless you have exhausted the escalation ladder below.
Sourcing direction: ${state.sourcingDirection === 'internal' ? 'INTERNAL (search only within the listed entities)' : 'EXTERNAL (exclude the listed entities)'}
${orgList}
${state.hospitalBedPriority ? 'For hospitals/healthcare organizations: prioritize by bed capacity, and prefer private hospitals over public/government ones when comparable in size.\n' : ''}
=== SOURCING RULES ===
- Only LinkedIn public profiles, English-language only. Never fabricate a candidate or a LinkedIn URL — only include profiles you actually found.
- Prefer large, well-known organizations, judged as prominent within the relevant industry AND geography — not necessarily globally famous.

=== SEARCH LOOP CONTROL — REACH THE TARGET COUNT ===
Work through this escalation ladder, only moving to the next tier when the current one is exhausted (not after a single query):
Tier 1: Exact title + exact geography + preferred company tier.
Tier 2: Add title synonyms and adjacent seniority (±1 level).
Tier 3: Expand to adjacent/related job titles doing similar work.
Tier 4: Expand geography slightly (nearby cities/regions), if not hard-restricted above.
Tier 5: Include mid-size or lesser-known organizations, not just top-tier ones.
Run multiple distinct queries per tier. Hard budget = ${hardBudget} queries (8x the requested count) — track and report your query count.
Never repeat an identical query. Keep accumulating candidates across tiers.
Only stop before reaching the target if you hit the full budget after genuinely working through all 5 tiers — then explain specifically which tiers you exhausted and why the pool is thin.

=== OUTPUT FORMAT — REQUIRED ===
Return the shortlist as a JSON array, one object per candidate, matching EXACTLY this shape (organizationBrief, shortlistRationale, and candidateBrief must each contain EXACTLY 3 strings, each a full 8-20 word clause — never a fragment, never fewer than 3, never compressed into one string):

${JSON.stringify([CANDIDATE_SCHEMA_EXAMPLE], null, 2)}

matchScore is numeric 0-100. confidence is exactly "High", "Medium", or "Low".
Paste that JSON array into the "Import results & generate Excel" step of this tool to produce the final .xlsx shortlist — do not hand-build the spreadsheet yourself.`;
  }

  const api = {
    EXCLUDED_ORGS,
    GEOGRAPHY_OPTIONS,
    DEFAULT_GEOGRAPHY,
    SENIORITY_OPTIONS,
    CANDIDATE_SCHEMA_EXAMPLE,
    buildSourcingBrief
  };

  const root = global.PH || (global.PH = {});
  root.sourcingPrompt = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
