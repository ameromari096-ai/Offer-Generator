# Copilot Studio integration (one-click shortlist Excel)

This wires the Candidate Sourcing Agent's Step 2 (validate + build `.xlsx`)
into a Copilot Studio agent, so a recruiter running the sourcing brief in
Copilot Studio gets a finished Excel shortlist back automatically instead of
pasting JSON into `sourcing.html` by hand. The manual copy/paste workflow
(see the main README) keeps working regardless — this is an optional
upgrade for a Copilot Studio-based agent specifically.

**What this needs that the manual workflow doesn't:**
- An Azure subscription (to host the Function — cost is near-zero for this
  volume; see "Cost" below).
- A Power Platform license that includes the **HTTP / custom connector**
  entitlement (Power Automate Premium, or an equivalent Process license).
  Copilot Studio licensing alone does not include this — it's a separate
  Power Platform connector entitlement.
- Access to create a Power Automate flow and add an action to a Copilot
  Studio topic in your tenant.

## 1. Deploy the Azure Function

The function code lives at the repo root (`host.json`, `package.json`,
`GenerateShortlist/`) so it can `require('../js/sourcingExcel.js')` and
reuse the exact same validation/Excel logic the web page uses — no second
copy to keep in sync.

Prerequisites: [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli),
[Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local),
Node.js 18+.

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

### Test it directly

```bash
curl -X POST "https://offer-generator-sourcing.azurewebsites.net/api/GenerateShortlist?code=<key>" \
  -H "Content-Type: application/json" \
  -d '{"jobTitle":"ICU Nurse Manager","candidates":[{"candidateName":"Test Candidate","currentTitle":"ICU Nurse Manager","currentCompany":"Example Hospital","currentLocation":"Dubai, UAE","linkedinUrl":"https://www.linkedin.com/in/testcandidate","organizationBrief":["Bullet one is a full clause about size.","Bullet two is a full clause about beds.","Bullet three is a full clause about other fact."],"shortlistRationale":["Rationale bullet one comparing to the brief.","Rationale bullet two comparing to the brief.","Rationale bullet three comparing to the brief."],"candidateBrief":["Has 10 years of relevant experience in ICU nursing.","Worked across private hospitals and government health systems.","Strongest link is DHA license matching the JD requirement."],"matchScore":88,"confidence":"High"}]}'
```

A valid request returns `200` with `{ ok: true, filename, contentBase64,
candidateCount, warnings }`. An invalid one (wrong bullet count, missing
field, bad score/confidence) returns `400` with `{ ok: false, errors,
warnings }` — the same messages `sourcing.html`'s Step 2 shows.

## 2. Build the Power Automate flow

1. In [Power Automate](https://make.powerautomate.com/), create a new
   **Instant cloud flow** with trigger **"Manually trigger a flow"**
   (Copilot Studio calls this as an action). Add input parameters:
   `jobTitle` (text), `candidatesJson` (text — Copilot Studio passes the
   JSON array it produced as a string here).
2. Add an **HTTP** action (this is the step that needs the premium
   connector entitlement):
   - Method: `POST`
   - URI: `https://offer-generator-sourcing.azurewebsites.net/api/GenerateShortlist?code=<key>`
   - Headers: `Content-Type: application/json`
   - Body: `{ "jobTitle": @{triggerBody()['text_1']}, "candidates": @{triggerBody()['text_2']} }`
     (use the actual dynamic content names Power Automate generated for
     your two inputs).
3. Add a **Condition**: `outputs('HTTP')['statusCode']` is equal to `200`.
   - **If yes**: Parse the HTTP action's body as JSON (use "Parse JSON"
     with a sample of the success response above), then add
     **OneDrive for Business → Create file**:
     - Folder: wherever you want shortlists saved (e.g. `/Candidate Shortlists`)
     - File name: the flow's `filename` output
     - File content: `base64ToBinary(body('Parse_JSON')?['contentBase64'])`
   - Then add **OneDrive for Business → Create share link for a file or
     folder** on the file just created, and return that link as the flow's
     output (respond to Copilot Studio).
   - **If no**: Parse the error body and return `errors` as the flow's
     output, so Copilot Studio can tell the recruiter what to fix (e.g.
     "candidate 3 is missing a LinkedIn URL") instead of failing silently.

## 3. Wire it into the Copilot Studio topic

1. In the Copilot Studio agent handling candidate sourcing, after the step
   where the agent has produced its candidate JSON array, **add an
   action → the Power Automate flow you just built**, passing the job
   title and the JSON array (as a string) as inputs.
2. Add a branch on the flow's response:
   - **Success** → message the user with the OneDrive link (e.g. "Here's
     your shortlist: {ShareLink}").
   - **Failure** → message the user with the `errors` list and ask the
     agent to correct and resend the candidate list (it can retry the
     same action with corrected JSON).

## Cost recap

- **Azure Function**: Consumption plan gives 1M free executions/month —
  this tool will not come close to that, so expect close to $0, though an
  Azure subscription (billing account) must exist.
- **Power Automate**: the HTTP action used in step 2 requires a Premium
  (or Process) license — this is the one piece not covered by having
  Copilot Studio alone.
- **Copilot Studio**: whatever you already have provisioned; this
  integration adds one action call per sourcing run, not a new licensing
  tier by itself.

## Rollback / fallback

If the flow or Function is ever down, nothing breaks for the manual path —
`sourcing.html`'s Step 2 (paste JSON, validate, download) works completely
independently of this integration.
