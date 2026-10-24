# Module I demo design

The existing FastAPI app serves one dependency-free HTML/CSS/JS page that calls `/predict` and `/model-info`. The navy/blue neutral palette targets WCAG AA contrast, system typography avoids font downloads, controls have visible amber focus rings, and the two-column layout collapses below 700 px. Loading, success, backend error and status-unavailable states are explicit. Provenance is adjacent to the estimate, and the synthetic/non-medical disclaimer is always visible.

The form uses native required/min/max validation, a disabled `Estimating…` loading state, focus transfer to success/error results, live status regions, and safe DOM text insertion. At 700 px the two-column page and field grid collapse to one column.

UI/UX Pro Max was unavailable, so these decisions were made directly. No browser engine or browser-test package was installed; desktop/mobile rendering, tab order and assistive-technology behavior remain manual QA items. API tests cover the served page and backend validation/failure contracts.
