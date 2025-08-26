
# Test Plan – (40b) Enhancer Guardrails for Condition Pages

## Goals
- Detect condition pages (`/cancer/types/…`) and enrich `MedicalCondition` safely.
- Collapse duplicate breadcrumbs; exclude "Back to ..." crumbs.
- Keep contact info off `MedicalCondition`; attach phones/socials to org only.
- Extract PDQ-like items into `MedicalCondition` when available.

## Quick Steps

1) Neuroblastoma page
- URL: https://montefioreeinstein.org/cancer/types/endocrine-system/neuroblastoma
- Expect:
  - One `BreadcrumbList` referenced from `MedicalWebPage.breadcrumb`
  - `MedicalCondition` has: `typicalAgeRange`, small sets of `signOrSymptom`, `riskFactor`, `typicalTest`, `possibleTreatment`
  - No `telephone`, `address`, or `contactPoint` on the condition node
  - If phones/socials exist, they live on a `MedicalOrganization`/`Hospital` node

2) Non-condition page (e.g., /cancer)
- Breadcrumbs + socials enrich as before; no condition extraction triggered.

3) Phones
- Numbers with area codes starting 0/1 are dropped.

4) History/Export
- Submissions still save and export as usual.
