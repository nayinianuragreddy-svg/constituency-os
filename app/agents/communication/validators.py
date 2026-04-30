import re
from datetime import date, datetime, timedelta
from typing import Any

from .types import ValidationResult

NAME_RE = re.compile(r"^[A-Za-z .,'\-]{2,80}$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
VOTER_RE = re.compile(r"^[A-Z]{3}\d{7}$")
PHOTO_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,200}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _valid(value: Any, code: str = "valid") -> ValidationResult:
    return ValidationResult(is_valid=True, normalized_value=value, error_hint="", code=code)


def _invalid(hint: str) -> ValidationResult:
    return ValidationResult(is_valid=False, normalized_value=None, error_hint=hint, code="invalid")


def validate_name(value: str) -> ValidationResult:
    text = (value or "").strip()
    if not NAME_RE.fullmatch(text):
        return _invalid("Name must be 2-80 letters/spaces and standard punctuation.")
    text = re.sub(r"\s+", " ", text)
    return _valid(text.title())


def validate_dob(value: str) -> ValidationResult:
    text = (value or "").strip()
    try:
        dob = datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return _invalid("DOB must be in DD/MM/YYYY format.")
    today = date.today()
    age = (today - dob).days // 365
    if age < 18 or age > 110:
        return _invalid("Age must be between 18 and 110 years.")
    return _valid(dob.isoformat())


def validate_mobile(value: str) -> ValidationResult:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not MOBILE_RE.fullmatch(digits):
        return _invalid("Mobile number must be 10 digits and start with 6/7/8/9.")
    return _valid(digits)


def validate_voter_id(value: str) -> ValidationResult:
    text = (value or "").strip().upper()
    if text in {"SKIP", "LATER"}:
        return _valid(None, code="skip")
    if not VOTER_RE.fullmatch(text):
        return _invalid("Voter ID must be EPIC format: 3 letters + 7 digits.")
    return _valid(text)


def validate_mandal(value: str, allowed_mandals: set[str] | None = None) -> ValidationResult:
    text = (value or "").strip()
    if len(text) < 2 or len(text) > 120:
        return _invalid("Mandal must be 2-120 characters.")
    if allowed_mandals and text.lower() not in {m.lower() for m in allowed_mandals}:
        return _invalid("Please choose a mandal from the provided list.")
    return _valid(text)


def validate_village_ward(value: str) -> ValidationResult:
    text = (value or "").strip()
    if len(text) < 2 or len(text) > 80:
        return _invalid("Village / Ward name must be 2-80 characters.")
    return _valid(text)


def validate_ward_number(value: str, valid_wards: set[int] | None = None, attempts: int = 1) -> ValidationResult:
    text = (value or "").strip()
    if not text.isdigit():
        if attempts >= 2:
            return _valid({"ward_number": None, "wards_fallback_text": text, "ward_review_required": True})
        return _invalid("Ward number must be an integer.")
    ward_num = int(text)
    if ward_num <= 0:
        return _invalid("Ward number must be positive.")
    if valid_wards and ward_num not in valid_wards:
        if attempts >= 2:
            return _valid({"ward_number": None, "wards_fallback_text": text, "ward_review_required": True})
        return _invalid("Ward number not found for selected mandal.")
    return _valid({"ward_number": ward_num, "ward_review_required": False})


def validate_geo(value: str) -> ValidationResult:
    text = (value or "").strip()
    if text.lower() in {"skip", "use ward centroid", "centroid"}:
        return _valid({"use_centroid": True, "geo_is_approximate": True})
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        return _invalid("Share location as 'lat,lng' or choose 'Use ward centroid'.")
    try:
        lat = float(parts[0]); lng = float(parts[1])
    except ValueError:
        return _invalid("Latitude/Longitude must be numeric.")
    if lat < -90 or lat > 90 or lng < -180 or lng > 180:
        return _invalid("Latitude/Longitude are out of valid range.")
    return _valid({"geo_lat": round(lat, 6), "geo_lng": round(lng, 6), "geo_is_approximate": False})


def validate_issue_type(value: str, allowed_values: list[str]) -> ValidationResult:
    text = (value or "").strip()
    allowed_map = {a.lower(): a for a in allowed_values}
    key = text.lower()
    if key not in allowed_map:
        return _invalid("Please choose one of the listed issue types.")
    return _valid(allowed_map[key])


def validate_duration_days(value: str) -> ValidationResult:
    text = (value or "").strip()
    if not text.isdigit():
        return _invalid("Duration must be an integer number of days.")
    days = int(text)
    if days < 0 or days > 3650:
        return _invalid("Duration must be between 0 and 3650 days.")
    return _valid(days)


def validate_households_affected(value: str) -> ValidationResult:
    text = (value or "").strip()
    if not text.isdigit():
        return _invalid("Households affected must be an integer.")
    households = int(text)
    if households < 1 or households > 10000:
        return _invalid("Households affected must be between 1 and 10000.")
    return _valid(households)


def validate_free_text(value: str, min_len: int = 0, max_len: int = 1000) -> ValidationResult:
    text = (value or "").strip()
    if len(text) < min_len or len(text) > max_len:
        return _invalid(f"Text length must be between {min_len} and {max_len} characters.")
    return _valid(text)


def validate_photo_file_id(value: str) -> ValidationResult:
    text = (value or "").strip()
    if not PHOTO_FILE_ID_RE.fullmatch(text):
        return _invalid("Invalid Telegram file_id for media upload.")
    return _valid(text)


def validate_severity(value: str) -> ValidationResult:
    return validate_issue_type(value, ["Minor", "Moderate", "Dangerous"])


def validate_urgency(value: str) -> ValidationResult:
    return validate_issue_type(value, ["Low", "Medium", "High", "Emergency", "Normal", "Urgent", "Very Urgent", "Life-threatening"])


def validate_scale(value: str) -> ValidationResult:
    return validate_issue_type(value, ["Street-level", "Ward-level", "Area-wide"])


def validate_incident_date(value: str) -> ValidationResult:
    text = (value or "").strip()
    try:
        parsed = datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return _invalid("Incident date must be DD/MM/YYYY.")
    if parsed > date.today():
        return _invalid("Incident date cannot be in the future.")
    return _valid(parsed.isoformat())


def validate_preferred_date(value: str) -> ValidationResult:
    text = (value or "").strip()
    try:
        parsed = datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return _invalid("Preferred date must be DD/MM/YYYY.")
    today = date.today()
    max_allowed = today + timedelta(days=183)
    if parsed < today or parsed > max_allowed:
        return _invalid("Preferred date must be between today and 6 months from today.")
    return _valid(parsed.isoformat())


def validate_preferred_time(value: str) -> ValidationResult:
    text = (value or "").strip()
    if text.lower() in {"na", "none", "skip"}:
        return _valid(None, code="skip")
    if not TIME_RE.fullmatch(text):
        return _invalid("Preferred time must be HH:MM (24-hour format).")
    return _valid(text)
