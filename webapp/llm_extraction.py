"""Automated field extraction from an uploaded hiring approval / CV /
passport, using Claude to do the language-understanding work the offer-agent
chat skill does manually — same priority rules, same notice-period-section
rule, same "never infer nationality" rule.

Requires ANTHROPIC_API_KEY in the environment. If it's unset, callers should
catch the resulting error and fall back to the manual entry form — this
feature is additive, never a hard requirement for using the app.
"""

from __future__ import annotations

from typing import List, Optional

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-opus-5"


class ExtractedField(BaseModel):
    value: Optional[str] = None
    source: str  # "hiring_approval" | "cv" | "passport" | "user"
    confirmed_unavailable: bool = False


class ConflictOption(BaseModel):
    value: str
    source: str


class FieldConflict(BaseModel):
    field: str
    options: List[ConflictOption]


class ExtractionResult(BaseModel):
    business_unit_raw: Optional[str] = None
    candidate_full_name: ExtractedField
    candidate_first_name: Optional[ExtractedField] = None
    candidate_phone_number: ExtractedField
    candidate_email_address: ExtractedField
    nationality: ExtractedField
    job_title: ExtractedField
    line_manager: ExtractedField
    department: ExtractedField
    notice_period: ExtractedField
    total_salary: ExtractedField
    conflicts: List[FieldConflict] = []
    notes: List[str] = []


SYSTEM_PROMPT = """You extract employment-offer fields from a hiring \
approval, a candidate CV, and (optionally) a passport. You do NOT decide \
anything or fill placeholders yourself — you only report what each source \
says, following these rules exactly.

SOURCES AND PRIORITY (for each field, prefer the highest-priority source \
that states it): 1) passport (name & nationality ONLY), 2) hiring \
approval, 3) CV. Never blend or average values across sources.

HIRING APPROVAL FIELD MAPPING (match labels case-insensitively; ignore \
HTML, markup, signatures, disclaimers, extra whitespace, and unrelated \
forwarded-email-thread text — read only the newest/topmost message unless \
it is missing a field the older ones have):
- "Candidate Recommended" -> candidate_full_name
- "Job Title" -> job_title
- "Reporting Line" -> line_manager
- "Division" or "Department" -> department (if the document has BOTH \
  "Division" and "Department" labeled separately with DIFFERENT values, \
  that is a genuine conflict — report both as a FieldConflict for \
  "department", do not guess which one wins)
- "Business Unit" -> business_unit_raw (copy the exact string, e.g. \
  "PureHealth" or "TalentOne"/"Talent One" — never infer it from job \
  title, department, or anything else)
- "Proposed Salary" -> total_salary (the MONTHLY total; strip "AED", \
  commas, and "/-" — return just the number as a string, e.g. "90000". \
  Do NOT use "Previous Salary", the separated employee's "Salary", or the \
  Grade Level Min/Mid/Max band figures — only "Proposed Salary".)

NOTICE PERIOD IS SPECIAL: search specifically inside the "Contract \
Term(s)"/"Contract Term Details" section (near "Contract Type" and \
"Contract Tenure") and take the value beside/below "Notice Period" THERE \
ONLY. A hiring approval can contain a second, unrelated "Notice Period" \
label elsewhere (e.g. under general Remarks/Notes, near "Tentative DOJ") \
— ignore that one even if it looks more prominent; only the Contract \
Terms section's value counts. If you cannot find a Notice Period under \
that section at all, leave notice_period.value null (do not use the \
other one, do not guess). Both employment-contract templates this feeds \
read "{{notice period}} calendar days in writing" — so notice_period.value \
must be a bare number of DAYS. If the source states it in months (e.g. \
"3 months"), convert to days as months x 30 and add a one-line note to \
`notes` explaining the conversion (e.g. "Notice period: 90 (converted \
from hiring approval's \\"3 months\\", months x 30)").

CV: use for candidate_phone_number and candidate_email_address (the \
candidate's own contact details, never a recruiter's signature block), \
and for nationality/full name ONLY if the hiring approval/passport don't \
state them. NEVER infer nationality from a name, a language listed on the \
CV, or a phone country code — only from an explicit nationality statement. \
If no source explicitly states nationality, leave nationality.value null.

PASSPORT: if provided (text or image), use it ONLY to read the legal full \
name and nationality — never report or reference any other passport \
field (passport number, birth details, dates, sex, photograph, signature) \
even internally; just ignore that content.

NAMES: preserve the highest-priority full name EXACTLY as written — never \
translate, abbreviate, anglicize, or "correct" capitalization. For \
candidate_first_name: strip a courtesy title (Mr./Mrs./Ms./Dr./Prof. etc.) \
from the resolved full name and take the first remaining name component; \
you may leave candidate_first_name null and the caller will derive it.

CONFLICTS: if two passages at the SAME priority level disagree on a field \
(e.g. two different values both labeled as the hiring approval's \
Department), report it as a FieldConflict with both options — do not \
pick one yourself. A field is not "missing" just because it has a \
conflict; only report it as null when NO source states it at all.

confirmed_unavailable must stay false in every field you return — you are \
never the one who confirms a value is permanently unavailable; that is a \
human decision. Use value=null (with confirmed_unavailable=false) for \
anything not found in any source; the human reviewing your output decides \
whether to accept that as truly unavailable.

For every field, set `source` to whichever of "hiring_approval", "cv", or \
"passport" the winning value actually came from (or "user" — never use \
that value yourself, it's reserved for values a person typed directly).
"""


def _build_user_content(
    hiring_approval_text: Optional[str],
    cv_text: Optional[str],
    passport_text: Optional[str],
    passport_image_base64: Optional[str],
    passport_image_media_type: Optional[str],
) -> list:
    parts = [
        "=== HIRING APPROVAL ===\n" + (hiring_approval_text or "(not provided)"),
        "=== CV ===\n" + (cv_text or "(not provided)"),
    ]
    if passport_text:
        parts.append("=== PASSPORT TEXT (name & nationality ONLY) ===\n" + passport_text)

    content: list = []
    if passport_image_base64 and passport_image_media_type:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": passport_image_media_type,
                    "data": passport_image_base64,
                },
            }
        )
        parts.append(
            "=== PASSPORT IMAGE ATTACHED ===\nRead ONLY the legal full name "
            "and nationality from it; ignore every other detail."
        )
    content.append({"type": "text", "text": "\n\n".join(parts)})
    return content


def extract_offer_fields(
    hiring_approval_text: Optional[str] = None,
    cv_text: Optional[str] = None,
    passport_text: Optional[str] = None,
    passport_image_base64: Optional[str] = None,
    passport_image_media_type: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> ExtractionResult:
    client = anthropic.Anthropic()

    content = _build_user_content(
        hiring_approval_text,
        cv_text,
        passport_text,
        passport_image_base64,
        passport_image_media_type,
    )

    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_format=ExtractionResult,
    )
    return response.parsed_output
