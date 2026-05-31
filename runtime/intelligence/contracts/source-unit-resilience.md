# Source-Unit Resilience Policy

PAOS collectors use source-unit resilience by default.

Source-unit examples:
- Threads account collector: one account
- Threads keyword collector: one keyword/query
- RSS collector: one feed
- Future collectors: one repository/provider/query target

Policy:
- Do not remove or disable configured source units only because they are empty or temporarily problematic.
- One source-unit error or empty result must not fail the whole collector when other units succeed.
- Record unit-level empty/error as warnings in diagnostics and continue to next unit.
- Write usable collected items even when some units fail/empty.
- Collector/job should fail only when:
  - auth/session fails globally, or
  - config is invalid, or
  - output cannot be written, or
  - no source units are processable, or
  - all processable units fail with errors and no usable items are produced.

Status convention:
- `success`: all processable source units produced usable results.
- `success_with_warnings`: at least one source unit is empty/failed but at least one unit succeeded.
- `failed`: global failure conditions above.
