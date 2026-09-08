---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "local-verification",
  "kind": "information",
  "version": 1,
  "title": "Fixop local verification",
  "status": "proposed",
  "owner": "semcod/fixop",
  "created": "2026-09-08",
  "updated": "2026-09-08",
  "review_after": "2026-09-15",
  "source_revision": "9b24f634e9c50b35e9e768562bc7e915d69b5b36",
  "affected_repositories": [
    "semcod/fixop"
  ],
  "evidence": [
    "https://github.com/semcod/fixop/issues/4",
    "https://github.com/subactor/onedev-agent/issues/207"
  ]
}
---

# Fixop local verification

<!-- docs:section purpose -->
## Purpose

Verify the existing supported Python matrix and canonical documentation through protected local CI and independent publication.

<!-- docs:section scope -->
## Scope

The executor uses Python 3.10.19 and 3.13.15, the approved uv.lock and dev extras, matching the existing hosted test matrix. It verifies exact dependency input hashes before importing candidate source and running every pytest test without network access.

<!-- docs:section evidence -->
## Evidence

The hosted workflow requires Python 3.10 and 3.13. Tests mock SSH and network interactions. The approved input revision is `9b24f634e9c50b35e9e768562bc7e915d69b5b36`; the executor implementation is tracked in subactor/onedev-agent issue #207.

<!-- docs:section content -->
## Documentation and publication

The second protected gate runs Wellmanifest Docs revision `ebe7501063ef4f3e63ded610c2d3183010ca636e` against the exact trusted base. The adoption pin is .governance/docs.json. A child-only Git URL mapping supplies repository identity for local mirrors. The independent Validator must bind the exact PR head and merge result before publication. Existing hosted checks remain required.

<!-- docs:section limitations -->
## Limits

Passing mocked Linux tests does not prove real infrastructure remediation, Windows/macOS behavior, wheel packaging or all IDE/LLM sessions. A changed dependency input needs an independently reviewed executor pin/image update. Source configuration, runtime deployment and observed verification are separate evidence.

<!-- docs:section next_actions -->
## Acceptance

Observe the deployed executor on this unchanged canary head, retain both Python results and the documentation result, then independently require the local gate alongside both hosted checks. Publish through the trusted Validator adapter.
