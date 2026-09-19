# PureHealth Interview Scheduling Assistant

A self-contained website that implements the PureHealth Interview Scheduling
Agent workflow: collect and validate interview details, extract candidate
details from an uploaded CV, resolve UAE (Gulf Standard Time) dates, calculate
interview times, preview the candidate email, and generate **unsent** calendar
and email drafts for a recruiter to review and send manually.

**Nothing is ever sent automatically.** The site has no server and no
connection to Outlook, Microsoft Graph, or SharePoint — it produces two files
you download and finish in Outlook yourself:

- **`<request-id>-calendar-draft.ics`** — import/open this to create the
  appointment on your own calendar as a normal (unsent) item. Add interviewer
  and candidate invitees and send the invitation from Outlook when you're
  ready.
- **`<request-id>-email-draft.eml`** — opening this file (e.g. double-clicking
  it, or "Open" from your downloads) creates a fully editable, **unsent**
  email draft in Outlook, complete with the candidate email as recipient, the
  formatted HTML body, and attachments. Add interviewer addresses to Cc/To if
  needed and send it yourself.

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
  loaded from a CDN) — no CV content is uploaded anywhere. If those libraries
  can't load (e.g. no internet access) or the file type is unsupported, the
  app tells you and asks you to enter the candidate's name/email manually.

## Using it

1. Serve the folder over HTTP (opening `index.html` directly via `file://`
   also works for the core flow, but the CDN-loaded CV parsers may be blocked
   by some browsers under `file://`). For local testing:
   ```
   python3 -m http.server 8000
   ```
   then open `http://localhost:8000/`.
2. Fill in the candidate, job, interviewer, date, time, and interview-type
   details (optionally upload a CV first to auto-fill the candidate's name
   and email).
3. Click **Continue to preview** — the assistant resolves the date, computes
   the end time, and shows the full preview plus the candidate-facing email
   exactly as it will be sent.
4. Click **Yes, create the drafts** to generate the `.ics` and `.eml` files.
   Download both, open them in Outlook, add interviewer email addresses,
   double-check everything, and send when ready.

## Project structure

```
index.html                              Page markup / wizard steps
styles.css                              Styling
js/dateUtils.js                         UAE date resolution ("next Monday", etc.)
js/timeUtils.js                         Start/end time calculation, 12h formatting
js/extract.js                           Client-side CV name/email extraction
js/templates.js                         Email HTML + calendar description templates
js/ics.js                               .ics (calendar draft) file builder
js/eml.js                               .eml (email draft) file builder
js/main.js                              Wizard state machine / UI wiring
assets/purehealth-introduction-2026.pdf Placeholder attachment — replace with the real file
```

No build step or dependencies are required beyond a modern browser; pdf.js
and mammoth.js are loaded from a CDN only when a CV is uploaded.
