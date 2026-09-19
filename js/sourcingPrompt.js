// Builds the "Sourcing Brief" document handed to the PureHealth Sourcing
// Agent (Microsoft 365 Copilot). This site has no server, no LinkedIn API
// access, and no hidden API keys to call an LLM itself — see the Candidate
// Sourcing section of the main README for why. The brief embeds the full
// sourcing ruleset plus every parameter chosen in the filter panel, and
// asks the agent to search, verify, and hand back a finished Excel
// shortlist itself (it has its own Excel/column rules already configured).
(function (global) {
  const EXCLUDED_ORGS = [
    'PureHealth', 'The Medical Office', 'OneHealth', 'The Life Corner', 'TalentOne',
    'Daman', 'SEHA', 'SEHA Clinics', 'SSMC', 'Rafed', 'PureCS', 'Circle Health Group',
    'Hellenic Health Group', 'Tamouh', 'PureLab', 'Sakina', 'Pura'
  ];

  const GEOGRAPHY_OPTIONS = [
    'United Arab Emirates', 'United Kingdom', 'United States', 'Canada', 'Europe'
  ];
  // None checked by default — the requester picks explicitly, or adds a
  // custom location, or leaves it unspecified.
  const DEFAULT_GEOGRAPHY = [];

  function bulletsOrNote(list) {
    const items = (list || []).filter(Boolean);
    return items.length ? items.map((s) => `  - ${s}`).join('\n') : '  (none specified)';
  }

  // Like bulletsOrNote, but for a single-value-style field (job title,
  // industry, company size) that now accepts multiple chips: prints a plain
  // line for exactly one value, an "ANY of" bullet list for several, or the
  // given fallback note when empty.
  function valueOrList(list, label, fallback) {
    const items = (list || []).filter(Boolean);
    if (!items.length) return `${label}: ${fallback}`;
    if (items.length === 1) return `${label}: ${items[0]}`;
    return `${label} (match ANY of the following):\n${items.map((s) => `  - ${s}`).join('\n')}`;
  }

  /**
   * state: {
   *   jobTitle: string[], yearsExperience, industry: string[], companySize: string[],
   *   targetCompanies: string[], keywords: string[], briefingText, jdText,
   *   geography: { countries: string[], global: boolean, customLocations: string[], exclusions: string },
   *   profileCount, sourcingDirection: 'external'|'internal', excludedOrgs: string[],
   *   hospitalBedPriority: boolean
   * }
   */
  function buildSourcingBrief(state) {
    const geoParts = [];
    if (state.geography.global) geoParts.push('Global (no geographic restriction)');
    geoParts.push(...state.geography.countries);
    geoParts.push(...(state.geography.customLocations || []));
    const geoLine = geoParts.length
      ? geoParts.join(', ')
      : '(not specified by the requester — infer from the briefing/JD, or ask if genuinely unclear)';

    const orgList = state.sourcingDirection === 'internal'
      ? `INTERNAL SOURCING REQUESTED — search ONLY within these entities (do not exclude them):\n${bulletsOrNote(state.excludedOrgs)}`
      : `EXCLUDE candidates currently employed at any of the following (and any other confirmed PureHealth-affiliated entity), unless it is one of the target companies for internal mobility:\n${bulletsOrNote(state.excludedOrgs)}`;

    const targetCount = Number(state.profileCount) || 15;
    const hardBudget = targetCount * 8;

    return `You are a Candidate Sourcing Agent. Find REAL LinkedIn-based candidates matching the role below and deliver them as a structured shortlist. Do not fabricate a candidate or a LinkedIn URL under any circumstance — only include profiles you actually found via live search.

=== ROLE BRIEF ===
${valueOrList(state.jobTitle, 'Job title', '(not specified — infer from the briefing text below)')}
Years of experience: ${state.yearsExperience || '(not specified — infer from the briefing/JD)'}
${valueOrList(state.industry, 'Industry', '(infer from the briefing/JD)')}
${valueOrList(state.companySize, 'Company size', '(no preference specified)')}
Target companies (prioritize candidates currently or previously at these, if any are listed):
${bulletsOrNote(state.targetCompanies)}
Keywords / required skills:
${bulletsOrNote(state.keywords)}

Free-text briefing:
${state.briefingText ? state.briefingText.trim() : '(none provided)'}

${state.jdText ? `Attached/pasted job description:\n${state.jdText.trim()}\n` : ''}
=== SEARCH PARAMETERS ===
Target geography: ${geoLine}
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
Tier 2: Add title synonyms and adjacent experience levels.
Tier 3: Expand to adjacent/related job titles doing similar work.
Tier 4: Expand geography slightly (nearby cities/regions), if not hard-restricted above.
Tier 5: Include mid-size or lesser-known organizations, not just top-tier ones.
Run multiple distinct queries per tier. Hard budget = ${hardBudget} queries (8x the requested count) — track and report your query count.
Never repeat an identical query. Keep accumulating candidates across tiers.
Only stop before reaching the target if you hit the full budget after genuinely working through all 5 tiers — then explain specifically which tiers you exhausted and why the pool is thin.

=== OUTPUT FORMAT — REQUIRED ===
Generate the finished shortlist directly as a downloadable Excel (.xlsx) workbook, following your own configured column format and rules exactly. Do not reply with the results as chat text, a table, or JSON — hand back the actual spreadsheet file.`;
  }

  const api = {
    EXCLUDED_ORGS,
    GEOGRAPHY_OPTIONS,
    DEFAULT_GEOGRAPHY,
    buildSourcingBrief
  };

  const root = global.PH || (global.PH = {});
  root.sourcingPrompt = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
