# PureHealth Interview Scheduling Assistant

A self-contained website with two tools:

- **Interview Scheduling Assistant** (`index.html`) — collect and validate
  interview details, extract candidate details from an uploaded CV, resolve
  UAE (Gulf Standard Time) dates, calculate interview times, preview the
  candidate email, and generate **unsent** Outlook email drafts for a
  recruiter to review and send manually.
- **Candidate Sourcing Agent** (`sourcing.html`) — a LinkedIn-search-style
  filter panel that builds a ready-to-run sourcing brief and turns a
  sourcing agent's results into a real `.xlsx` shortlist. See
  [Candidate Sourcing Agent](#candidate-sourcing-agent) below.

**Nothing is ever sent automatically.** The site has no server and no
connection to Outlook, Microsoft Graph, or SharePoint — it produces two files
you download and finish in Outlook yourself:

- **`<request-id>-email-draft.eml`** — the candidate-facing interview email.
  Opening this file (e.g. double-clicking it, or "Open" from your downloads)
  creates a fully editable, **unsent** email draft in Outlook, complete with
  the candidate email as recipient, the formatted HTML body, and attachments.
  Add interviewer addresses to Cc/To if needed and send it yourself.
- **`<request-id>-candidate-access-draft.eml`** — a short internal email
  ("Subject: Candidate Access") asking your access/facilities team to grant
  the candidate access, listing their name, email, mobile number, and the
  interview date/time. No recipient is filled in — add your team's address
  before sending. A missing email or phone number shows as an explicit
  `[... not provided]` placeholder rather than being silently left blank.

## Why not "real" Outlook/Teams/SharePoint drafts?

The original agent specification assumes a Copilot Studio / Power Automate
environment with live connectors (Outlook, Microsoft Graph, Teams, SharePoint).
A static website has no such backend or credentials, so this implementation:

- **Never invents a Teams link.** For an Online interview you must paste the
  genuine Teams join URL from a meeting you've already created. If you don't
  have one yet, the app will not let you proceed to the email draft.
- **Bundles a placeholder** `assets/purehealth-introduction-2026.pdf`
  standing in for the "Get PureHealth Introduction" SharePoint retrieval.
  Replace that file with the approved PDF before using this in production —
  the app attaches whatever file exists at that path.
- **Extracts CV details entirely in your browser** (via pdf.js / mammoth.js,
  vendored in `vendor/` — see `vendor/README.md`) — no CV content is uploaded
  anywhere. Name, email, and phone number are pulled with best-effort
  heuristics (an unlabeled phone number is only trusted if it has a country
  code or area-code parentheses, to avoid mistaking a date or reference
  number for one). A scanned/image-based PDF (no real text layer, common
  with visually-designed templates) can't be read this way; the app tells
  you clearly when that happens and asks you to enter the details manually.

## Using it

1. Serve the folder over HTTP (opening `index.html` directly via `file://`
   also works for the core flow, but some browsers block Web Workers — used
   by the PDF parser — under `file://`). For local testing:
   ```
   python3 -m http.server 8000
   ```
   then open `http://localhost:8000/`.
2. Fill in the candidate, job, interviewer, date, time, and interview-type
   details (optionally upload a CV first to auto-fill the candidate's name,
   email, and mobile number).
3. Click **Continue to preview** — the assistant resolves the date, computes
   the end time, and shows the full preview plus the candidate-facing email
   exactly as it will be sent.
4. Click **Yes, create the email drafts** to generate both `.eml` files.
   Download them, open them in Outlook, add the interviewer/team email
   addresses, double-check everything, and send when ready.

## Project structure

```
index.html                              Interview Scheduling Assistant markup / wizard steps
sourcing.html                           Candidate Sourcing Agent markup
styles.css                              Styling for both tools
js/dateUtils.js                         UAE date resolution ("next Monday", etc.)
js/timeUtils.js                         Start/end time calculation, 12h formatting
js/extract.js                           Client-side CV name/email extraction + raw text extraction (JD upload)
js/templates.js                         Email HTML template + shared escapeHtml helper
js/eml.js                               .eml (email draft) file builder
js/main.js                              Interview Scheduling wizard state machine / UI wiring
js/sourcingPrompt.js                    Builds the sourcing brief text from the filter panel's state
js/sourcingExcel.js                     Validates pasted candidate JSON and builds the .xlsx shortlist
js/sourcing.js                          Candidate Sourcing page state machine / UI wiring
assets/purehealth-logo.png              Brand logo used in the header
assets/purehealth-introduction-2026.pdf Placeholder attachment — replace with the real file
vendor/                                 Vendored pdf.js + mammoth.js + xlsx (see vendor/README.md)
```

No build step or dependencies are required beyond a modern browser; pdf.js,
mammoth.js, and xlsx ship as local files under `vendor/` rather than a CDN,
so CV parsing and Excel generation work even on networks that block
third-party CDNs.

## Candidate Sourcing Agent

`sourcing.html` implements a "Candidate Sourcing Agent" workflow: given a
role brief, find real LinkedIn candidates matching it and deliver them as a
structured shortlist Excel file, using a LinkedIn-search-style filter panel
(job title, seniority, industry, must-haves, geography, profile count,
internal/external sourcing direction, and the PureHealth network exclusion
list) for the search parameters.

### Why not a one-click live search?

The original agent specification assumes it can browse LinkedIn and call an
AI model directly. A static site has no server, no LinkedIn API access, and
nowhere safe to store an API key (any key embedded in client-side JavaScript
would be public), so this implementation splits the workflow into two honest
steps instead of pretending to search LinkedIn itself:

1. **Generate a sourcing brief.** The filter panel's parameters, the
   free-text briefing, and an optional uploaded/pasted job description are
   assembled into a complete, ready-to-run brief — including the full
   sourcing ruleset (search-tier escalation ladder, exclusion list, output
   format) — for you to run in an AI assistant that can actually browse the
   live web (e.g. Claude or ChatGPT with web search/browsing enabled).
2. **Import results and generate the Excel file.** Paste the JSON array the
   agent returns back into the page. Every candidate is validated against
   the shortlist's formatting rules — exactly 3 bullets per bullet column,
   a real-looking `linkedin.com/in/...` URL, a 0-100 match score, a valid
   confidence label — before a real `.xlsx` file (built with the vendored
   `xlsx` library, no server round-trip) is generated. **No candidate or
   LinkedIn URL is ever fabricated by this tool** — it only formats and
   checks data you bring back from a real search.
