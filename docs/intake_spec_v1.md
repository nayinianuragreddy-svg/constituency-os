# Constituency OS — Intake Spec V1

**Purpose:** This document defines what the Communication agent collects from a citizen, in what order, in what shape. It is the source of truth that the deterministic state machine, the database schema, and the LLM extraction prompts all reference.

**Scope:** Communication agent only. Department, Dashboard, Master are downstream consumers of the tickets this spec produces.

**Mode independence:** This spec describes WHAT is collected. The state machine describes the deterministic HOW (LLM off). With LLM on, the same fields are extracted from natural language, and the state machine asks only for what's still missing. Same target, smarter path.

---

## Stage 0 — Identity continuity (deterministic, never LLM)

Before anything else, the bot looks up the incoming `telegram_chat_id`:

- **Known chat_id, registration complete** → returning user, jump to Stage 3
- **Known chat_id, registration incomplete** → resume registration from where they left off
- **Unknown chat_id** → first-time user, start at Stage 1

This lookup is in code, not LLM. Identity is never an LLM decision.

---

## Stage 1 — Greeting + Language Lock

**Trigger:** First message from an unknown chat_id, OR `/start` command.

**Bot says:**
> Namaskaram! This is [MLA Name]'s office. Before we continue, which language are you comfortable with?

**Options shown as inline buttons:**
- Telugu
- Hindi
- English

**Citizen taps one** → language saved to `citizens.preferred_language` → advance to Stage 2.

**Edge cases:**
- If citizen types instead of tapping (e.g. "telugu" or "తెలుగు"), accept and proceed
- If citizen types something unrelated, re-prompt once; if unrelated again, default to English and proceed
- Language can be changed later via "/language" command (not built in V1, flag for V2)

---

## Stage 2 — First-Time Registration

**Skipped entirely if Stage 0 found a returning user with `registration_complete=true`.**

Registration collects 8 fields. 7 mandatory, 1 optional (Voter ID).

### 2A — Personal Details

Collected one at a time, validated, saved progressively (so a drop-off mid-registration leaves partial data we can resume from).

| Order | Field | Type | Mandatory | Validation |
|---|---|---|---|---|
| 1 | Full Name | Text | Yes | 2-80 chars, letters + spaces + standard punctuation |
| 2 | Date of Birth | DD/MM/YYYY | Yes | Valid date, age between 18-110 |
| 3 | Mobile Number | 10-digit | Yes | Indian mobile format, leading 6/7/8/9 |
| 4 | Voter ID | Alphanumeric | **Optional** | If provided: standard EPIC format (3 letters + 7 digits). Skip allowed via "skip" button or typing "skip"/"later" |

**Voter ID skip flow:**
- Bot asks: "Voter ID (optional — type 'skip' to share later)"
- If skipped, set `voter_id = null` and `voter_id_skipped_at = now()`
- Future trigger: when citizen first books a welfare/pension complaint, prompt once more; never beyond that

### 2B — Location Details

| Order | Field | Type | Mandatory | Validation |
|---|---|---|---|---|
| 5 | Mandal / Municipality | Text or dropdown | Yes | Must match seeded mandal list for this constituency |
| 6 | Village / Ward Name | Text | Yes | 2-80 chars |
| 7 | Ward Number | Number | Yes | Integer, must exist in seeded ward list for the mandal |
| 8 | Geo Location | Telegram location share OR pin drop OR "skip and use ward centroid" | Yes (with fallback) | If shared: lat/lng saved. If skipped: ward centroid lat/lng saved as approximation, `geo_is_approximate=true` |

**Ward number validation note:** the constituency's mandal list and ward list must be seeded into the database before the bot is live. If a citizen enters an unrecognised ward, bot asks once more, then accepts free-text and flags ticket for staff review.

### 2C — Confirmation

Bot reads back all 8 fields:

> Please confirm your details:
> Name: Ravi Kumar
> DOB: 15/06/1987
> Mobile: 9876543210
> Voter ID: ABC1234567 (or "Not provided")
> Mandal: Kollur
> Village/Ward: Madhapur
> Ward Number: 12
> Location: Captured (or "Approximate — ward centroid")
>
> Is this correct?

**Inline buttons:**
- ✅ Yes, all correct
- ✏️ Edit Name
- ✏️ Edit DOB
- ✏️ Edit Mobile
- ✏️ Edit Voter ID
- ✏️ Edit Mandal
- ✏️ Edit Ward
- ✏️ Edit Location
- ❌ Cancel and start over

Each "Edit X" jumps to that single field, keeps everything else, then returns to confirmation.

On "Yes" → set `registration_complete=true` → advance to Stage 3.

---

## Stage 3 — Issue Category Selection

**Bot says (returning user):**
> Welcome back, [Name]! How can I help you today?

**Bot says (just-registered user):**
> Thank you, [Name]. How can I help you today?

**Inline buttons:**
- 🔵 Public Issue (community / infrastructure)
- 🟠 Private Issue (personal matter)
- 📅 Appointment / Invitation

Selection determines which Stage 4 path runs.

---

## Stage 4A — Public Issues

**Sub-categories:**
1. Water
2. Electricity
3. Sanitation
4. Roads & Buildings (R&B)
5. Others

Bot presents 5 buttons. Citizen taps one → corresponding field template.

### 4A.1 — Public — Water (`PUB-WTR`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Issue Type | Enum | Yes | No supply / Contamination / Pipeline break / Borewell / New connection |
| Exact Location | Text | Yes | Free text — village/ward/street name |
| Duration of Issue | Number (days) | Yes | 0-3650 |
| Approx. Households Affected | Number | Yes | 1-10000 |
| Previous Complaint Filed? | Enum + optional ref | No | Yes (with ref no) / No |
| Additional Description | Free text | No | 0-1000 chars |

### 4A.2 — Public — Electricity (`PUB-ELC`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Issue Type | Enum | Yes | Power cut / Transformer fault / Streetlight / Billing dispute / New connection |
| Exact Location | Text | Yes | Free text |
| Duration of Issue | Number (days) | Yes | 0-3650 |
| Approx. Households Affected | Number | Yes | 1-10000 |
| DISCOM Complaint Ref | Text | No | Number / NA |
| Additional Description | Free text | No | 0-1000 chars |

### 4A.3 — Public — Sanitation (`PUB-SAN`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Issue Type | Enum | Yes | Drainage overflow / Garbage not collected / Open sewage / Public toilet condition |
| Exact Location | Text | Yes | Free text |
| Duration of Issue | Number (days) | Yes | 0-3650 |
| Scale of Impact | Enum | Yes | Street-level / Ward-level / Area-wide |
| Photo Evidence | Image upload | No | Optional, stored as media reference |
| Additional Description | Free text | No | 0-1000 chars |

### 4A.4 — Public — Roads & Buildings (`PUB-RNB`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Issue Type | Enum | Yes | Road damage / Pothole / Bridge condition / Govt building repair / Drainage on road |
| Exact Location | Text | Yes | Village/ward/road name |
| Severity | Enum | Yes | Minor / Moderate / Dangerous |
| Duration of Issue | Number (days) | Yes | 0-3650 |
| Photo Evidence | Image upload | No | Optional |
| Additional Description | Free text | No | 0-1000 chars |

### 4A.5 — Public — Others (`PUB-OTH`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Brief Title | Text | Yes | 5-120 chars |
| Department Concerned | Text | No | Free text or NA |
| Exact Location | Text | Yes | Village/ward |
| Urgency Level | Enum | Yes | Low / Medium / High / Emergency |
| Detailed Description | Free text | Yes | 10-1000 chars |
| Photo / Document Evidence | Image upload | No | Optional |

**Routing for "Others":** If `department_concerned` is provided, route there. Else route to PA queue for triage.

---

## Stage 4B — Private Issues

**Sub-categories:**
1. Police Issue
2. Revenue Issue
3. Welfare Issue
4. Medical Emergency
5. Education
6. Others

### 4B.1 — Private — Police (`PRV-POL`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Nature of Issue | Enum | Yes | FIR not registered / Harassment / False case / Property dispute / Threat / Other |
| Incident Date | DD/MM/YYYY | Yes | Past or today; not future |
| Police Station Name | Text | Yes | 2-120 chars |
| FIR / Complaint Number | Text | No | Number or NA |
| Parties Involved | Text | Yes | Brief description, 5-300 chars |
| Urgency Level | Enum | Yes | Normal / Urgent / Emergency |
| Detailed Description | Free text | Yes | 10-1000 chars |

### 4B.2 — Private — Revenue (`PRV-REV`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Issue Type | Enum | Yes | Patta / Land mutation / Encroachment / Survey / Property tax / Pahani |
| Survey / Plot Number | Text | No | Number or NA |
| Village / Mandal | Text | Yes | 2-120 chars |
| Status of Issue | Enum | Yes | Fresh request / Pending / Rejected |
| Relevant Documents | File upload | No | Optional, stored as media reference |
| Detailed Description | Free text | Yes | 10-1000 chars |

### 4B.3 — Private — Welfare (`PRV-WEL`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Welfare Category | Enum | Yes | Pension / Housing / Ration card / Caste certificate / Women scheme / SC/ST scheme / Other |
| Scheme Name (if known) | Text | No | Or NA |
| Issue Type | Enum | Yes | New application / Application pending / Application rejected / Amount not received |
| Application / Reference Number | Text | No | Or NA |
| Duration of Pending | Text | Yes | "Since X days" or "Since X months" |
| Detailed Description | Free text | Yes | 10-1000 chars |

**If Voter ID was previously skipped:** trigger one prompt to share it now (welfare schemes typically need voter ID linkage). Skip still allowed.

### 4B.4 — Private — Medical Emergency (`PRV-MED`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Patient Name | Text | Yes | 2-80 chars |
| Patient Age | Number | Yes | 0-120 |
| Relation to Caller | Enum | Yes | Self / Family member / Neighbour |
| Nature of Emergency | Enum | Yes | Accident / Critical illness / Hospitalization support / Financial aid for treatment |
| Current Location / Hospital | Text | Yes | 2-200 chars |
| Urgency Level | Enum | Yes | Urgent / Very Urgent / Life-threatening |
| Financial Assistance Needed? | Boolean | Yes | Yes / No |
| Detailed Description | Free text | Yes | 10-1000 chars |

**Note:** Medical emergency is treated as a regular private subcategory in V1 prototype. Special "we'll call you in 2 minutes" path NOT built — flagged for V2.5 once office staffing model supports it.

### 4B.5 — Private — Education (`PRV-EDU`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Institution Name | Text | Yes | 2-200 chars |
| Issue Type | Enum | Yes | Admission / Scholarship / Fee reimbursement / Infrastructure / Teacher shortage / TC / Other |
| Student Name | Text | Yes | 2-80 chars |
| Class / Course | Text | Yes | 1-80 chars |
| Status | Enum | Yes | Fresh request / Pending / Rejected |
| Reference / Application Number | Text | No | Or NA |
| Detailed Description | Free text | Yes | 10-1000 chars |

### 4B.6 — Private — Others (`PRV-OTH`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Brief Title | Text | Yes | 5-120 chars |
| Nature of Issue | Free text | Yes | 10-500 chars |
| Urgency Level | Enum | Yes | Low / Medium / High / Emergency |
| Relevant Documents | File upload | No | Optional |
| Detailed Description | Free text | Yes | 10-1000 chars |

**Routing:** All private-others tickets route to PA queue for triage.

---

## Stage 4C — Appointment / Invitation

**Sub-categories (one shared field template):**
1. Meeting Request with MLA (`APT-MTG`)
2. Event Invitation (`APT-EVT`)
3. Felicitation / Programme (`APT-FEL`)

| Field | Type | Mandatory | Allowed values |
|---|---|---|---|
| Type | Enum | Yes | Meeting / Event invitation / Felicitation / Programme |
| Organisation / Individual Name | Text | Yes | 2-200 chars |
| Purpose / Occasion | Free text | Yes | 10-500 chars |
| Preferred Date | DD/MM/YYYY | Yes | Today or future, max +6 months |
| Preferred Time | HH:MM | No | 24-hr format if provided |
| Venue / Location | Text | Yes | 2-200 chars |
| Expected Attendees | Number | No | 1-100000 |
| Contact Person Name | Text | Yes | 2-80 chars |
| Contact Person Number | 10-digit mobile | Yes | Same validation as registration mobile |
| Additional Notes | Free text | No | 0-1000 chars |

**Routing:** All appointment tickets route to PA queue (single pseudo-officer) for MLA scheduling. Department agent does not handle appointments.

---

## Stage 5 — Confirmation, Ticket Generation, Acknowledgement

### 5A — Confirmation

After all required fields collected, bot reads back the complaint:

> Please confirm your complaint:
> Category: Public → Water
> Issue Type: Pipeline break
> Location: Madhapur, Ward 12, Main Road
> Duration: 3 days
> Households Affected: 50
> [...other fields...]
>
> Is this correct?

**Inline buttons:**
- ✅ Yes, register this complaint
- ✏️ Edit [each field name]
- ❌ Cancel this complaint

### 5B — Ticket Generation

On "Yes":
- Generate `ticket_id` in format `[CATEGORY-CODE]-[DDMMYY]-[SEQUENCE]`
  - `PUB-WTR-280426-0042`
  - Sequence is per-day, per-office, zero-padded to 4 digits
- Save full ticket with all fields to `tickets` table
- Save subcategory-specific custom fields to `ticket_custom_fields` (JSONB column)
- Default routing queue resolved from `complaint_categories.default_routing_queue`
- Create `agent_actions` row: `agent_name="communication", action_type="ticket.created", payload={ticket_id, category_code, ...}`

### 5C — Acknowledgement to Citizen

> Thank you, [Name]. Your complaint has been registered.
>
> Ticket ID: PUB-WTR-280426-0042
> Category: Public → Water
> Status: Open — assigned to Water Department
>
> You can quote this ID for any follow-up. We'll update you when there is progress.

---

## Stage 6 — Returning user main menu (post-registration)

When a returning user (registration_complete=true) sends a message at any time outside an active flow:

**Bot responds:**
> Welcome back, [Name]. What would you like to do?

**Inline buttons:**
- 🆕 New Complaint
- 📊 Check Status of Existing Complaint
- 📞 Talk to Office (forwards to PA inbox)
- 🌐 Change Language
- ❓ Help

---

## Off-path handling (LLM-augmented, but bounded)

These are flows the citizen can trigger from anywhere mid-conversation. Code handles state transitions; LLM only helps detect intent and extract fields.

### "Fix earlier field"

- Trigger: citizen says something like "wait i gave wrong ward, change to 14" mid-flow
- Allowed when state ∈ {any registration state, any complaint-collection state, confirmation states}
- Disallowed once `tickets.status != 'draft'` — at that point bot says: "This complaint is already registered. To update, please contact our office (button to PA queue)."
- When allowed: jump state machine to the named field, keep all other field values, return to confirmation

### "Status check"

- Trigger: citizen says "any update on my ticket" / "what about my last complaint" / quotes a ticket ID
- Code looks up `tickets` for this `citizen_id` (or matching ticket_id if quoted)
- LLM drafts the status reply; LLM does not query DB
- If multiple recent tickets, list them and ask which

### "Unclear / out of scope"

- Trigger: citizen says something the LLM cannot map to any known intent
- State stays put
- Bot asks one clarifying question via reply drafter
- After 2 unclear messages in a row, offer "Talk to Office" button

### "Abandon"

- Trigger: explicit ("never mind", "cancel", "leave it") or 24h of silence
- If mid-registration: save partial, mark `registration_complete=false`, citizen can resume next time
- If mid-complaint: discard draft, return to main menu next message

---

## What the LLM extracts toward (the dual-mode rule)

When `LLM_ENABLED=true`, the intent_router (already built in V2 Phase 2) extracts toward this same spec. Specifically:

- registration fields (name, dob, mobile, voter_id, mandal, village, ward_number)
- top-level category (public / private / appointment)
- subcategory (water / electricity / police / etc.)
- as many subcategory-specific fields as possible from the citizen's natural language

State machine then asks ONLY for missing required fields. Same target spec, fewer turns.

When `LLM_ENABLED=false`, state machine asks every required field one at a time. Same spec, more turns.

**Result:** the deterministic build IS the foundation. LLM is a faster path to the same ticket.

---

## What is NOT in this spec (deferred)

These are real but not V1.8 scope:

- Photo/voice/document upload UX (placeholder field exists; storage backend later)
- WhatsApp channel (Telegram only for V1.8)
- /language command to change language post-registration
- Medical emergency special path with SLA
- Multi-MLA / multi-office support (office_id column exists; not exercised)
- Geo agent integration (geo location captured; not yet used for radius queries)
- Officer-side reply parsing (Department agent's job; phase 3)
