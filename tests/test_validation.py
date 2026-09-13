from offer_agent.models import ConflictOption, FieldConflict, FieldValue, ResolvedOffer
from offer_agent.preview import build_preview
from offer_agent.validation import validate_offer


def _base_fields():
    return {
        "candidate full name": FieldValue("Jane Doe", "cv"),
        "candidate phone number": FieldValue("+971500000000", "cv"),
        "candidate email address": FieldValue("jane@example.com", "cv"),
        "candidate first name": FieldValue("Jane", "calculation"),
        "job title": FieldValue("Engineer", "hiring_approval"),
        "nationality": FieldValue("Canadian", "cv"),
        "line manager": FieldValue("John Smith", "hiring_approval"),
        "notice period": FieldValue("30", "hiring_approval"),
        "Total Salary": FieldValue("20000", "hiring_approval"),
    }


def test_conflicted_field_is_not_also_reported_missing():
    resolved = ResolvedOffer(
        offer_id="offer-conflict-not-missing",
        business_unit_raw="PureHealth",
        fields=_base_fields(),  # deliberately has no "department" entry
        conflicts=[
            FieldConflict(
                field="department",
                options=[
                    ConflictOption("Commercial Office", "hiring_approval (Division)"),
                    ConflictOption("Commercial", "hiring_approval (Department)"),
                ],
            )
        ],
    )
    validation = validate_offer(resolved)

    assert "department" not in validation.missing_fields
    assert len(validation.conflicts) == 1
    assert not validation.can_finalize  # still blocked, just by the conflict, not "missing"


def test_preview_shows_conflict_note_not_not_yet_provided():
    resolved = ResolvedOffer(
        offer_id="offer-conflict-preview",
        business_unit_raw="PureHealth",
        fields=_base_fields(),
        conflicts=[
            FieldConflict(
                field="department",
                options=[
                    ConflictOption("Commercial Office", "hiring_approval (Division)"),
                    ConflictOption("Commercial", "hiring_approval (Department)"),
                ],
            )
        ],
    )
    validation = validate_offer(resolved)
    preview = build_preview(resolved, validation)

    assert "Department: See conflicts below" in preview
    missing_section = preview.split("Missing fields:")[1].split("Unresolved placeholders:")[0]
    assert "Department" not in missing_section


def test_notes_are_disclosed_as_warnings_not_user_overrides():
    resolved = ResolvedOffer(
        offer_id="offer-notice-period-conversion",
        business_unit_raw="PureHealth",
        fields=_base_fields(),
        notes=['Notice period: 90 (converted from hiring approval\'s "3 months", months x 30)'],
    )
    validation = validate_offer(resolved)
    preview = build_preview(resolved, validation)

    assert "converted from hiring approval" in validation.warnings[0]
    assert "converted from hiring approval" in preview
    # It's a computed note, not something the user typed -> must not appear
    # under "User overrides".
    overrides_section = preview.split("User overrides:")[1].split("Missing fields:")[0]
    assert "converted from hiring approval" not in overrides_section
