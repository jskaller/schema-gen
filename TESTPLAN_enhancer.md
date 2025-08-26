
# Schema Enhancer – Test Plan (v39)

## Scope
Validate the new enrichment layer (`app/services/enhance.py`) that upgrades specialties to Schema.org enums, extracts breadcrumbs/socials/phones from page HTML, and merges into the JSON-LD without breaking routes or history.

## Environments
- macOS (Apple Silicon), Python 3.11+ or 3.13 in your current venv
- App started via `make dev` or `uvicorn app.main:app --reload`

## Pre-check
1. Visit `http://127.0.0.1:8000/__routes` – confirm `/`, `/submit`, `/history`, `/admin`, `/batch` exist.
2. Optional: clear `app.db` if you want a fresh history (or keep as-is).

## Functional Tests

### T1 – Montefiore Cancer (Department/Specialty)
- **Input**: URL = `https://montefioreeinstein.org/cancer`
- Page Type = `Department/Specialty` (mapped to `MedicalOrganization + [MedicalWebPage, Hospital, MedicalSpecialty, BreadcrumbList]`)
- Topic = `Cancer`, Subject = `Montefiore Einstein`, Audience = `Patient`
- **Expect**:
  - `medicalSpecialty` on the root set to `Oncologic` (enum upgrade)
  - `MedicalWebPage` node exists and has `breadcrumb` property
  - `BreadcrumbList` contains multiple levels (Home → … → Cancer)
  - `sameAs` includes at least one social profile found on the page
  - A phone present on root (`telephone`) and/or a `contactPoint[0].telephone`

### T2 – Cardiology page (choose a real department URL)
- Topic = `Cardiology`
- **Expect**: `medicalSpecialty` becomes `Cardiovascular`

### T3 – Page without breadcrumbs markup
- Use a deep URL on a site lacking `<nav aria-label="breadcrumb">`
- **Expect**: Fallback breadcrumbs generated from path segments

### T4 – Page without visible phones
- Use a page where no phone numbers exist
- **Expect**: No `contactPoint` added; no crash

### T5 – Social extraction
- Use a page with multiple footer links to social platforms
- **Expect**: `sameAs` includes those links (no duplicates)

### T6 – History & Export unaffected
- Submit any page; navigate to `/history` and open the run
- **Expect**: record saved; JSON-LD export still downloads successfully

## Non-functional
- No 404s on `/`, `/admin`, `/admin/types`, `/history`, `/batch`
- Time to generate similar to before (a few seconds variance acceptable)
- No new Python dependencies required

## Regression Risks
- If `enhance_jsonld` returns malformed `@graph`, validation/score may drop.
- Ensure the enhancer does not overwrite explicit user-provided fields.

## Rollback
- Comment out the `enhance_jsonld(...)` call in `app/main.py`
- Restart `uvicorn`; enhancer disabled.
