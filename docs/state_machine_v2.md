# Constituency OS — State Machine V2

**Purpose:** This document names every state the Communication agent can be in, and every transition between states. It is the implementation blueprint for `intake_spec_v1.md`.

**Reading order:** read `intake_spec_v1.md` first. This doc assumes you know what's collected; this doc defines how the conversation flows to collect it.

**Conventions:**
- States named in `snake_case`, prefixed by stage (`s0_`, `s1_`, etc.)
- Transitions written as: `from_state --[trigger]--> to_state`
- "Trigger" is what causes the transition: a citizen message, a button tap, a validation result, a timeout
- Every state has the same dual mode: deterministic (LLM off) and LLM-augmented (LLM on). The state names and transitions don't change between modes — what changes is how much can be filled in one turn.

---

## The dual-mode rule (read this first)

For every "ask" state, two things happen on each citizen message:

1. **LLM intent_router runs first** (if `LLM_ENABLED=true`).
   - Returns `{intent, extracted, confidence}`.
   - Can extract MULTIPLE fields from one message.
   - All extracted values pass through deterministic validators before being accepted.

2. **State machine evaluates "what's the next missing required field?"**
   - If LLM extracted everything for the current state → validate, save, advance.
   - If LLM extracted some fields but not the one this state asks for → validate and save what was extracted, then ask for the still-missing field.
   - If LLM is off or extracted nothing useful → ask the current state's field.

**Implication:** state machine never "skips ahead" past a state on its own. It always asks for the next missing required field. LLM just lets that field-asking happen fewer times because more fields fill in per message.

---

## Global states (can be entered from anywhere)

These exist outside the linear flow. Any incoming message is checked against these first.

| State | When | What happens |
|---|---|---|
| `g_unknown_chat` | first message from unknown `telegram_chat_id` | route to `s0_identity_check` |
| `g_off_path_fix` | LLM detects `intent=fix_earlier` mid-flow, AND fix is allowed in current state | route to `s_fix_field` (sub-flow) |
| `g_off_path_status` | LLM detects `intent=ask_status` | route to `s6_status_check` |
| `g_off_path_unclear` | LLM detects `intent=unclear` OR confidence < 0.70 OR LLM off and message doesn't match expected input | re-ask current state's question; after 2 consecutive unclear, offer "Talk to Office" button |
| `g_abandon` | LLM detects `intent=abandon` OR citizen sends "/cancel" | route to `s_abandon_handler` |
| `g_session_resume` | citizen sends any message after >24h gap | check `registration_complete`; if mid-flow when they left, ask "want to continue where we left off?" |

---

## Stage 0 — Identity Continuity

Single state, runs before everything else.

```
s0_identity_check
```

**Transitions:**
- `s0_identity_check --[chat_id known, registration_complete=true, no active draft ticket]--> s6_returning_user_menu`
- `s0_identity_check --[chat_id known, registration_complete=true, active draft ticket exists]--> resume draft ticket flow`
- `s0_identity_check --[chat_id known, registration_complete=false]--> resume registration from saved field`
- `s0_identity_check --[chat_id unknown]--> s1_greet`

---

## Stage 1 — Greeting + Language Lock

```
s1_greet
s1_language_select
```

### `s1_greet`
- Bot sends greeting message + 3 language buttons (Telugu / Hindi / English)
- Transition: `s1_greet --[message sent]--> s1_language_select`

### `s1_language_select`
- Waiting for citizen to pick language (button tap or typed answer)
- Transitions:
  - `s1_language_select --[valid lang chosen]--> save citizens.preferred_language --> s2_register_name`
  - `s1_language_select --[unrecognised input, attempt 1]--> re-ask`
  - `s1_language_select --[unrecognised input, attempt 2]--> default to English --> s2_register_name`

---

## Stage 2 — First-Time Registration

8 sequential ask states, then confirmation, then complete.

```
s2_register_name
s2_register_dob
s2_register_mobile
s2_register_voter_id
s2_register_mandal
s2_register_village_ward
s2_register_ward_number
s2_register_geo
s2_register_confirm
s2_register_done
```

### Standard pattern for every register state

For state `s2_register_X`:

```
s2_register_X --[valid input received]--> save to citizens.X --> s2_register_NEXT
s2_register_X --[invalid input, attempt 1]--> ask again with hint
s2_register_X --[invalid input, attempt 2]--> ask again with example
s2_register_X --[invalid input, attempt 3]--> offer "Talk to Office" button + skip if non-mandatory
```

### Field-specific transitions

**`s2_register_name`**
- Validation: 2-80 chars, letters + spaces + standard punctuation
- Next: `s2_register_dob`

**`s2_register_dob`**
- Validation: valid date DD/MM/YYYY, age 18-110
- Special: if LLM extracted age but not DOB, bot asks "What year were you born?" instead of full DOB
- Next: `s2_register_mobile`

**`s2_register_mobile`**
- Validation: 10 digits, leading 6/7/8/9
- Auto-fill: if telegram contact-share button used, prefill from Telegram phone
- Next: `s2_register_voter_id`

**`s2_register_voter_id` (OPTIONAL)**
- Validation: 3 letters + 7 digits, OR "skip" / "later" / button tap
- Special transition: `--[skip]--> save voter_id_skipped_at=now() --> s2_register_mandal`
- Next: `s2_register_mandal`

**`s2_register_mandal`**
- Validation: must match seeded mandal list for this office
- Display as dropdown of seeded mandals (8-15 buttons typically)
- Next: `s2_register_village_ward`

**`s2_register_village_ward`**
- Validation: 2-80 chars
- Next: `s2_register_ward_number`

**`s2_register_ward_number`**
- Validation: integer, must exist in seeded ward list for the chosen mandal
- Special transition: `--[unrecognised ward, attempt 2]--> accept as free text + flag ticket_review_required=true --> s2_register_geo`
- Next: `s2_register_geo`

**`s2_register_geo`**
- Asks: "Please share your location, or tap 'Use ward centroid'"
- Transitions:
  - `--[telegram location shared]--> save lat/lng, geo_is_approximate=false --> s2_register_confirm`
  - `--[ward centroid button]--> save ward centroid lat/lng, geo_is_approximate=true --> s2_register_confirm`
  - `--[skip / no response after 2 prompts]--> use ward centroid as fallback --> s2_register_confirm`

### `s2_register_confirm`
- Bot reads back all 8 fields with edit buttons
- Transitions:
  - `--[Yes / Confirm]--> set registration_complete=true --> s2_register_done`
  - `--[Edit X]--> s_fix_field(X) (returns to s2_register_confirm after edit)`
  - `--[Cancel]--> warning prompt, then if confirmed: clear all fields --> s1_greet`

### `s2_register_done`
- Bot says "Thank you, [Name]. How can I help you today?"
- Transition: `s2_register_done --[immediate, no input needed]--> s3_category_select`

---

## Stage 3 — Issue Category Selection

```
s3_category_select
```

- Bot shows 3 buttons: Public / Private / Appointment
- Transitions:
  - `s3_category_select --[Public tapped]--> s4a_public_subcategory`
  - `s3_category_select --[Private tapped]--> s4b_private_subcategory`
  - `s3_category_select --[Appointment tapped]--> s4c_appointment_subcategory`
  - `s3_category_select --[LLM detects category from text]--> jump to subcategory state directly`
  - `s3_category_select --[unclear input, attempt 2]--> re-ask with examples`

---

## Stage 4A — Public Issue States

```
s4a_public_subcategory
s4a_water_*
s4a_electricity_*
s4a_sanitation_*
s4a_rnb_*
s4a_others_*
```

### `s4a_public_subcategory`
- 5 buttons: Water / Electricity / Sanitation / R&B / Others
- Transitions: each button taps to its first field state below

### Public — Water (`PUB-WTR`) — 6 fields, 6 states

```
s4a_water_issue_type        --> s4a_water_location
s4a_water_location          --> s4a_water_duration
s4a_water_duration          --> s4a_water_households
s4a_water_households        --> s4a_water_prev_complaint
s4a_water_prev_complaint    --> s4a_water_description
s4a_water_description       --> s5_complaint_confirm
```

| State | Asks | Validation | Required |
|---|---|---|---|
| `s4a_water_issue_type` | 5 buttons (No supply / Contamination / Pipeline break / Borewell / New connection) | Enum match | Yes |
| `s4a_water_location` | "Where exactly?" | 2-200 chars | Yes |
| `s4a_water_duration` | "How many days?" | Integer 0-3650 | Yes |
| `s4a_water_households` | "How many households?" | Integer 1-10000 | Yes |
| `s4a_water_prev_complaint` | "Have you filed a previous complaint?" | Yes (with ref) / No | No — skip allowed |
| `s4a_water_description` | "Anything else to add?" | 0-1000 chars | No — skip allowed |

### Public — Electricity (`PUB-ELC`) — same pattern, 6 states

```
s4a_electricity_issue_type --> s4a_electricity_location --> s4a_electricity_duration
--> s4a_electricity_households --> s4a_electricity_discom_ref --> s4a_electricity_description
--> s5_complaint_confirm
```

### Public — Sanitation (`PUB-SAN`) — 6 states

```
s4a_sanitation_issue_type --> s4a_sanitation_location --> s4a_sanitation_duration
--> s4a_sanitation_scale --> s4a_sanitation_photo --> s4a_sanitation_description
--> s5_complaint_confirm
```

### Public — Roads & Buildings (`PUB-RNB`) — 6 states

```
s4a_rnb_issue_type --> s4a_rnb_location --> s4a_rnb_severity --> s4a_rnb_duration
--> s4a_rnb_photo --> s4a_rnb_description --> s5_complaint_confirm
```

### Public — Others (`PUB-OTH`) — 6 states

```
s4a_others_title --> s4a_others_dept --> s4a_others_location
--> s4a_others_urgency --> s4a_others_description --> s4a_others_photo
--> s5_complaint_confirm
```

---

## Stage 4B — Private Issue States

```
s4b_private_subcategory
s4b_police_*
s4b_revenue_*
s4b_welfare_*
s4b_medical_*
s4b_education_*
s4b_others_*
```

### `s4b_private_subcategory`
- 6 buttons: Police / Revenue / Welfare / Medical / Education / Others
- Each button taps to its first field state

### Private — Police (`PRV-POL`) — 7 states

```
s4b_police_nature --> s4b_police_incident_date --> s4b_police_station
--> s4b_police_fir_number --> s4b_police_parties --> s4b_police_urgency
--> s4b_police_description --> s5_complaint_confirm
```

### Private — Revenue (`PRV-REV`) — 6 states

```
s4b_revenue_issue_type --> s4b_revenue_plot --> s4b_revenue_village_mandal
--> s4b_revenue_status --> s4b_revenue_documents --> s4b_revenue_description
--> s5_complaint_confirm
```

### Private — Welfare (`PRV-WEL`) — 6 states + voter ID re-prompt

```
s4b_welfare_voter_id_check (only if voter_id was previously skipped)
s4b_welfare_category --> s4b_welfare_scheme --> s4b_welfare_issue_type
--> s4b_welfare_app_number --> s4b_welfare_pending_duration --> s4b_welfare_description
--> s5_complaint_confirm
```

**`s4b_welfare_voter_id_check`** (special):
- Triggered only if `citizens.voter_id IS NULL AND citizens.voter_id_skipped_at IS NOT NULL`
- Bot says: "Welfare schemes typically need voter ID. Want to share it now? (skip still allowed)"
- `--[ID provided]--> save voter_id --> s4b_welfare_category`
- `--[skip]--> mark voter_id_skip_acknowledged=true (don't ask again) --> s4b_welfare_category`

### Private — Medical Emergency (`PRV-MED`) — 8 states

```
s4b_medical_patient_name --> s4b_medical_patient_age --> s4b_medical_relation
--> s4b_medical_nature --> s4b_medical_location --> s4b_medical_urgency
--> s4b_medical_financial --> s4b_medical_description --> s5_complaint_confirm
```

**Note:** No special "we'll call in 2 minutes" path in V1.8. Treat as regular subcategory.

### Private — Education (`PRV-EDU`) — 7 states

```
s4b_education_institution --> s4b_education_issue_type --> s4b_education_student_name
--> s4b_education_class --> s4b_education_status --> s4b_education_ref_number
--> s4b_education_description --> s5_complaint_confirm
```

### Private — Others (`PRV-OTH`) — 5 states

```
s4b_others_title --> s4b_others_nature --> s4b_others_urgency
--> s4b_others_documents --> s4b_others_description --> s5_complaint_confirm
```

---

## Stage 4C — Appointment / Invitation

```
s4c_appointment_subcategory
s4c_appointment_*
```

### `s4c_appointment_subcategory`
- 3 buttons: Meeting / Event Invitation / Felicitation
- Each taps into the same shared field flow with category code differing

### Appointment — shared flow — 10 states

```
s4c_appointment_type        (auto-set from button tap, but state exists for confirmation/edit)
--> s4c_appointment_org_name
--> s4c_appointment_purpose
--> s4c_appointment_preferred_date
--> s4c_appointment_preferred_time
--> s4c_appointment_venue
--> s4c_appointment_attendees
--> s4c_appointment_contact_name
--> s4c_appointment_contact_number
--> s4c_appointment_notes
--> s5_complaint_confirm
```

---

## Stage 5 — Confirmation, Ticket Generation, Acknowledgement

```
s5_complaint_confirm
s5_ticket_generated
s5_acknowledgement
```

### `s5_complaint_confirm`
- Bot reads back ALL collected fields for this complaint
- Inline buttons: Yes / Edit [each field] / Cancel

Transitions:
- `s5_complaint_confirm --[Yes tapped]--> generate ticket_id --> save ticket --> s5_ticket_generated`
- `s5_complaint_confirm --[Edit field X]--> s_fix_field(X) (returns to s5_complaint_confirm)`
- `s5_complaint_confirm --[Cancel]--> warning + confirm --> discard draft --> s6_returning_user_menu`

### `s5_ticket_generated` (system state, no input)
- Generates ticket_id format `[CATEGORY-CODE]-[DDMMYY]-[SEQUENCE]`
- Inserts into `tickets` and `ticket_custom_fields` tables
- Resolves default routing queue from `complaint_categories.default_routing_queue`
- Logs `agent_actions` row
- Auto-transition: `--> s5_acknowledgement`

### `s5_acknowledgement`
- Bot sends acknowledgement message with ticket_id and category
- Auto-transition: `--> s6_returning_user_menu`

---

## Stage 6 — Returning User Main Menu

```
s6_returning_user_menu
s6_status_check
```

### `s6_returning_user_menu`
- Bot sends "Welcome back, [Name]. What would you like to do?"
- 5 buttons: New Complaint / Check Status / Talk to Office / Change Language / Help

Transitions:
- `--[New Complaint]--> s3_category_select`
- `--[Check Status]--> s6_status_check`
- `--[Talk to Office]--> create handoff ticket to PA queue --> bot says "Forwarded to office"`
- `--[Change Language]--> s1_language_select (then back to s6)`
- `--[Help]--> bot sends help text --> stays in s6`
- `--[direct text input from citizen]--> LLM intent router decides which path` (if LLM on)

### `s6_status_check`
- Bot looks up tickets for this citizen
- 0 tickets: "You haven't filed any complaints yet. Want to file one?" --> s3_category_select
- 1 ticket: shows status of that ticket --> s6_returning_user_menu
- 2+ tickets: shows list, asks which --> s6_returning_user_menu

---

## Off-path sub-flows

### `s_fix_field(X)` — fix earlier field

Triggered from `g_off_path_fix` global state, OR from "Edit X" button in confirmation.

**Allowed when:** any registration ask state, any complaint-collection ask state, OR `s2_register_confirm` / `s5_complaint_confirm`.

**Disallowed when:** `tickets.status != 'draft'` (i.e. ticket already created).

**Flow:**
- Save current state as `return_to_state`
- Jump to ask state for field X
- On valid input, save field, return to `return_to_state`

Transitions:
- `s_fix_field(X) --[invalid input, 3 attempts]--> abort fix, return to return_to_state with error message`
- `s_fix_field(X) --[citizen tries to fix locked field, e.g. ticket_id]--> bot says "That can't be changed here. Talk to office?"`

### `s_abandon_handler` — explicit cancel

Triggered from `g_abandon` global, or when citizen explicitly says cancel/never mind/leave it.

**Flow:**
- If mid-registration: save partial, mark `registration_complete=false`, bot says "No problem. We'll continue when you're back."
- If mid-complaint: discard draft (don't save partial complaint), bot says "Cancelled. What else can I help with?" --> `s6_returning_user_menu`
- If during status check or main menu: bot says "Okay, ping me anytime" --> exit conversation (no state change)

### `s_session_resume` — return after gap

Triggered from `g_session_resume` global (>24h since last message).

**Flow:**
- If `registration_complete=false` and partial registration exists:
  - Bot: "Welcome back. Want to continue your registration where we left off?"
  - Yes --> resume from last completed register state
  - No --> ask if they want to start over (clears partial) or talk to office
- If `registration_complete=true` and active draft complaint exists:
  - Bot: "You were filing a complaint about [category] last time. Continue?"
  - Yes --> resume from last completed complaint field state
  - No --> discard draft --> `s6_returning_user_menu`
- Otherwise: `s6_returning_user_menu`

---

## State persistence model

Every transition writes to the database:

- `citizen_conversations.current_state` — current state name
- `citizen_conversations.last_state_change_at` — timestamp
- `citizen_conversations.return_to_state` — for fix_field flows
- `citizen_conversations.draft_ticket_id` — UUID of in-progress ticket draft, if any
- `citizen_conversations.draft_payload` — JSONB of fields collected so far for current draft

This is deliberate: the bot is stateless. Every message read this row, computes next state, writes back. Crash safety is automatic.

---

## State count summary (for codex)

| Stage | States | Notes |
|---|---|---|
| Stage 0 | 1 | identity check |
| Stage 1 | 2 | greet + language |
| Stage 2 | 10 | 8 register + confirm + done |
| Stage 3 | 1 | category select |
| Stage 4A — Public | 1 + (6 × 5) = 31 | subcategory + 5 paths × 6 fields each |
| Stage 4B — Private | 1 + (avg 6 × 6) = 37 | subcategory + 6 paths, varying length, includes welfare voter_id_check |
| Stage 4C — Appointment | 1 + 10 = 11 | subcategory + 10-step shared flow |
| Stage 5 | 3 | confirm + generate + ack |
| Stage 6 | 2 | menu + status check |
| Off-path | 3 sub-flows | fix_field, abandon, session_resume |
| Global | 6 guards | unknown_chat, fix, status, unclear, abandon, resume |

**Total named states: ~99** (~30 ask states + ~5 confirm/system states + ~64 unique field-collection states across categories)

This is a large state machine. It's tedious but mechanical. Codex's job is faithful translation, not invention.

---

## What is NOT in this state machine (deferred)

- Photo/voice upload UX inside collection states (placeholder field captured as Telegram `file_id`, no preview rendering)
- /language command for re-selection mid-conversation
- Interrupt handling for officer-side replies arriving while citizen is in a flow (Department agent handles those, not Communication)
- Multi-turn clarification within a single state (e.g. "What did you mean by 'soon'?" — state machine just re-asks the question)
- Group chat behaviour (assume DM only)
