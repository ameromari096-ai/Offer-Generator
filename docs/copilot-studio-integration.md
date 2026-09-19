# Copilot Studio integration (one-click shortlist Excel)

This wires the Candidate Sourcing Agent's Step 2 (validate + build `.xlsx`)
into a Copilot Studio agent, so a recruiter running the sourcing brief in
Copilot Studio gets a finished Excel shortlist back automatically instead of
pasting JSON into `sourcing.html` by hand. The manual copy/paste workflow
(see the main README) keeps working regardless — this is an optional
upgrade for a Copilot Studio-based agent specifically.

**What this needs that the manual workflow doesn't:**
- A place to host the backend endpoint (see the two options below — one of
  them, Netlify, needs no payment method and no local software install).
- Access to Copilot Studio's own **Workflow** builder for your agent (see
  the important note below — this is *not* a classic Power Automate flow).

**Important — Power Automate cloud flows cannot be used here at all.**
It's tempting to build this as a classic Power Automate flow (at
make.powerautomate.com) and add it as a Copilot Studio tool. Don't — as of
this writing, Copilot Studio's "Add a tool → Workflows" picker explicitly
states *"Only workflows that use the 'When an agent calls the workflow'
trigger are shown. Power Automate cloud flows are not supported"* — this
holds **regardless of which trigger the cloud flow uses**, including a
cloud flow you've swapped onto the "Microsoft Copilot Studio" trigger. The
only thing that works is a **Workflow built directly inside Copilot
Studio's own builder** (Section 2 below walks through this). We initially
went the classic-flow route, hit this wall, and had to rebuild — save
yourself the detour.

Both hosting options below run the exact same validation/Excel logic (both
`require('../js/sourcingExcel.js')` unchanged — no second copy to keep in
sync) and return the exact same response shape, so Section 2 (the
Copilot Studio Workflow) is identical either way — only the endpoint URL
and auth header differ.

## 1. Deploy the backend

### Option A — Netlify Functions (recommended: free, no card, no local install)

Netlify's free plan needs no credit card and explicitly allows commercial
use, and deployment is entirely web-based (connect a GitHub repo and click
— no CLI, nothing to install on your machine).

1. Go to [app.netlify.com](https://app.netlify.com/) and sign up (free —
   "Sign up with GitHub" is easiest).
2. Click **Add new site → Import an existing project → Deploy with
   GitHub**, authorize Netlify to see your repos, and pick
   `ameromari096-ai/Offer-Generator`.
3. Leave the build settings as detected (this repo's `netlify.toml` already
   points Netlify at `netlify/functions/`) and click **Deploy**. It finishes
   in under a minute.
4. Once deployed, go to **Site configuration → Environment variables** and
   add `SHORTLIST_API_KEY` with a secret value you make up (e.g. a random
   password) — this is the shared secret the Copilot Studio Workflow will
   send back on every call, so the endpoint isn't wide open to the public
   internet. Then
   **Deploys → Trigger deploy → Deploy site** once to pick up the new
   variable.
5. Your endpoint is:
   ```
   https://<your-site-name>.netlify.app/.netlify/functions/generateShortlist
   ```
   (find `<your-site-name>` on the site's overview page, or rename it under
   **Site configuration → General → Site details → Change site name**).

Test it (this `curl` can be run from any terminal, or from Cloud Shell —
nothing to install, since you're only calling a URL):
```bash
curl -X POST "https://<your-site-name>.netlify.app/.netlify/functions/generateShortlist" \
  -H "Content-Type: application/json" \
  -H "x-api-key: <the secret you set above>" \
  -d '{"jobTitle":"ICU Nurse Manager","candidates":[{"candidateName":"Test Candidate","currentTitle":"ICU Nurse Manager","currentCompany":"Example Hospital","currentLocation":"Dubai, UAE","linkedinUrl":"https://www.linkedin.com/in/testcandidate","organizationBrief":["Bullet one is a full clause about size.","Bullet two is a full clause about beds.","Bullet three is a full clause about other fact."],"shortlistRationale":["Rationale bullet one comparing to the brief.","Rationale bullet two comparing to the brief.","Rationale bullet three comparing to the brief."],"candidateBrief":["Has 10 years of relevant experience in ICU nursing.","Worked across private hospitals and government health systems.","Strongest link is DHA license matching the JD requirement."],"matchScore":88,"confidence":"High"}]}'
```

A valid request returns `200` with `{ ok: true, filename, contentBase64,
candidateCount, warnings }`. An invalid one (wrong bullet count, missing
field, bad score/confidence) returns `400` with `{ ok: false, errors,
warnings }` — the same messages `sourcing.html`'s Step 2 shows. A missing
or wrong `x-api-key` header returns `401`.

### Option B — Azure Functions (if your org already has an Azure subscription)

The function code lives at the repo root (`host.json`, `package.json`,
`GenerateShortlist/`).

Prerequisites: [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli),
[Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
(or use [Azure Cloud Shell](https://shell.azure.com) in the browser — both
come pre-installed there, nothing to download), Node.js 18+.

```bash
# 1. Log in and pick/create a resource group
az login
az group create --name rg-offer-generator --location uaenorth

# 2. Create a storage account (required by Azure Functions) and the
#    function app itself, on the Consumption (pay-per-execution) plan
az storage account create --name offergenfuncstorage --location uaenorth \
  --resource-group rg-offer-generator --sku Standard_LRS

az functionapp create --name offer-generator-sourcing \
  --resource-group rg-offer-generator --storage-account offergenfuncstorage \
  --consumption-plan-location uaenorth --runtime node --runtime-version 20 \
  --functions-version 4

# 3. Install dependencies and deploy this repo's root as the function app
npm install
func azure functionapp publish offer-generator-sourcing
```

(`az functionapp create --name ...` must be globally unique — pick your own
name. Change `uaenorth` to whichever Azure region you use.)

Get the function's key (required on every call, since `authLevel` is
`"function"`):

```bash
az functionapp function keys list --name offer-generator-sourcing \
  --resource-group rg-offer-generator --function-name GenerateShortlist
```

Your endpoint is:
```
https://offer-generator-sourcing.azurewebsites.net/api/GenerateShortlist?code=<key from above>
```
(Same request/response shape as Option A, just `?code=<key>` in the URL
instead of an `x-api-key` header.)

## 2. Build the Copilot Studio Workflow

This creates the tool directly inside your agent — no separate "connect an
existing flow" step, and no Power Automate involved.

### 2a. Create the workflow
1. Open your agent in Copilot Studio → **Actions/Tools** tab.
2. **"+ Add a tool"** → click the **"Workflows"** tab → **"+ Add"** to
   create a new one from scratch. Name it (e.g. "Generate Candidate
   Shortlist").
3. You land on a canvas with two nodes already present: **"When an agent
   calls the workflow"** (trigger) and **"Respond to the agent"** (final
   output) — leave both in place, you'll fill in what's between them.

### 2b. Trigger inputs
Click the trigger node → **"+ Add an input"** twice: `jobTitle` (Text) and
`candidatesJson` (Text).

### 2c. Initialize a result variable
Click the **"+"** between the trigger and the HTTP step you're about to
add → **Variable** → **Initialize variable** → name `resultMessage`, type
Text, value empty. (Both branches below will fill this in; a single shared
variable is simplest since both branches merge back into one "Respond to
the agent" node.)

### 2d. The HTTP call
Click **"+"** → **Connector** → search **"HTTP"** → the plain HTTP action.
- Method: `POST`
- URI: your endpoint from Section 1 — either
  `https://<your-site-name>.netlify.app/.netlify/functions/generateShortlist`
  (Option A) or `https://offer-generator-sourcing.azurewebsites.net/api/GenerateShortlist?code=<key>`
  (Option B)
- Headers: `Content-Type: application/json`, plus `x-api-key: <your secret>`
  for Option A (Option B carries its key in the URL instead)
- Body: click into the field and build it by hand — type `{ "jobTitle": "`,
  open **Dynamic content** and click `jobTitle` (inserts a chip), type
  `", "candidates": `, open Dynamic content again and click
  `candidatesJson`, then type the closing `}`. Typing the whole thing as
  one guessed string usually fails validation — building it this way (type,
  click a chip, type, click a chip) is what actually works.

### 2e. Branch on the status code
Click **"+"** → **If/Else**. Condition: click the left box → Dynamic
content → the HTTP action's **Status code** → operator **"is equal to"** →
right box `200`.

**Gotcha:** a non-2xx response (like our backend's `400` for bad data)
marks the HTTP action itself as **"Failed"**, and by default every step
after it gets **skipped** rather than letting your If/Else inspect the
status code. Fix it on **every node that follows HTTP** (starting with the
If/Else): open its **Settings → Run after**, and check **both "Succeeded"
and "Failed"** (not just "Succeeded"). Without this, the error branch never
runs — the workflow just silently stops.

### 2f. "If" branch (success)
1. **Connector → OneDrive for Business → Create file**. First time you use
   it, it'll ask you to sign in/connect your OneDrive account.
   - Folder Path: plain text, `/Candidate Shortlists`
   - File Name: click the **`</>`** icon next to the field (not the
     lightning-bolt "Dynamic content" one) to open a real expression/code
     editor, and type:
     ```
     outputs('HTTP')?['body']?['filename']
     ```
   - File Content: same `</>` editor, type:
     ```
     base64ToBinary(outputs('HTTP')?['body']?['contentBase64'])
     ```
   **Gotcha:** the normal text field (lightning-bolt/"Function" tab) does
   **not** evaluate typed function calls like `json(...)` — it just pastes
   them in as literal text, which silently produces garbage (e.g. a
   400-character-limit error from a filename that's actually the entire
   base64 blob). Only the `</>` code editor actually evaluates expressions.
   Also: the HTTP response body here is **already a parsed object**, not a
   JSON string — wrapping it in `json(...)` throws `expects a string or
   XML, got Object`. Reference it directly as shown above, no `json()`.
2. **Connector → OneDrive for Business → Create share link for a file or
   folder**. File: the "Create file" action's `Id`/item output. Link Type:
   `View`. **Link Scope: `Organization`** — most tenants block "Anyone"
   links (`Sharing by link is not enabled on the web, site, or tenant`),
   and Organization-scoped links are almost always still allowed.
3. **Variable → Set variable**: `resultMessage` = `Here's your shortlist: `
   + (Dynamic content) the share-link action's Web URL output.

### 2g. "Else" branch (failure)
**Variable → Set variable**: `resultMessage` set via the `</>` code editor
to:
```
concat('Sourcing agent error: ', join(outputs('HTTP')?['body']?['errors'], '; '))
```

### 2h. Wire the final response
Click **"Respond to the agent"** → **"+ Add an output"** → Text, name
`result`, value = the `resultMessage` variable (Dynamic content).

### 2i. Publish and test
**Save**, then **Publish** (this workflow type must be published — the
canvas's own "Test" button errors with `AgentTriggerTest.notTestable`
otherwise). There is no standalone test for this workflow type either way
— testing only happens through a live chat with the agent, so publish and
try a real (or explicit test) request in the agent's chat.

## Cost recap

- **Netlify (Option A)**: free plan, no credit card, commercial use
  allowed — 125,000 function calls/month included, far more than this tool
  will ever use.
- **Azure Function (Option B)**: Consumption plan gives 1M free
  executions/month, but requires an Azure subscription (billing account) to
  exist in the first place — use this only if your org already has one.
- **Copilot Studio Workflow's HTTP connector**: unlike a classic Power
  Automate flow, this didn't hit any Premium/Process licensing prompt while
  we built and ran it — Copilot Studio's own Workflow connectors appear to
  be licensed differently. Not a guarantee for every tenant, but no extra
  license was needed in practice here.
- **Copilot Studio**: whatever you already have provisioned; this
  integration adds one workflow call per sourcing run, not a new licensing
  tier by itself.

## Rollback / fallback

If the workflow or backend is ever down, nothing breaks for the manual path —
`sourcing.html`'s Step 2 (paste JSON, validate, download) works completely
independently of this integration.
