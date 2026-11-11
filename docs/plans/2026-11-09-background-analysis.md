# Automatic background analysis

Objective: users launch scans and receive indexed, correlated, stored results without managing Vector, MinIO, or Qdrant.

Constraints: preserve OVH network isolation, existing credentials and scans; no fake/mock AI results; use an explicitly selected real analysis provider. Keep infrastructure private and data on persistent volumes. Earlier interface patches are separate.

Plan:
1. Deploy private MinIO, Qdrant and Vector with persistent storage, health checks, bounded resources and restart policies; initialize buckets automatically.
2. Wire scan completion to durable background processing with idempotent writes and retries; index real embeddings, archive results, and expose processing state.
3. Connect the selected LLM service for automatic agent analysis and reports. User selected OpenRouter; credential loaded securely from OVH `/home/ubuntu/.env`; do not silently substitute a model.
4. Verify end-to-end with existing scan data, retry/restart behavior, and API retrieval; retain deployment receipts and rollback image/config identities.

Acceptance: no per-scan infrastructure setup; completed scans become searchable and archived automatically; transient service failures retry; processing failures remain visible; no secrets in logs. No internet reconnaissance scans are needed for validation.

## Deployment status (2026-11-09)

Workspace: `/home/pop/dev/spiderfoot-background`, branch `feat/automatic-background-analysis`, based on `f3b4ec3c8ec83554d3c2710a84a41e624146486c`, uncommitted candidate.

Deployed private MinIO, Qdrant, Vector, bucket initialization, and durable background worker on OVH. Worker uses OpenRouter; API and frontend automatic report integration are deployed. Existing startup credential fix remains deployed; separate interface-review changes remain excluded.

Checks: eight worker unit tests, three automatic report frontend tests, frontend typecheck and production build passed. MinIO and Qdrant write/read checks passed. Vector → MinIO telemetry roundtrip passed. Existing scan BF4808E5 completed with 13 points, 13 archived evidence rows, a 3,744-byte report, zero retries, and OpenRouter request gen-1794261717-Q74uOTIkzMdsIPAsTSCt. API returned complete after worker recreation and browser rendered report automatically (3,475 visible characters); manual generation controls are hidden when background analysis is enabled. All six app/background containers healthy.

Remote operation receipt: `/opt/harvest/spiderfoot-ng/deployment/background/deployment.json`; backups `.env.before-background-20261109` and `compose.core.yml.before-background-20261109`. Images pinned by digest. Vector upgraded to 0.60.0 and uses AWS credential environment directly rather than config interpolation.

New scans finishing after the deployment cutoff are discovered every 15 seconds. Historical scans show not_scheduled; no bulk paid backfill. Correlation searched the shared index with zero cross-scan candidates on the first indexed scan. Existing local report edits are preserved. Model call reported $0.07908, excluding embedding charges. Verification fixtures cleaned. Failed jobs stop after five attempts and remain visible; storage uses persistent volumes, not off-host backup. Build passed with existing CSS/chunk warnings. No unrelated interface patches deployed.
