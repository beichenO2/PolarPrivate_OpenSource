# Changelog

## 0.2.0

### Removed (breaking)

- `PrivPortalMiddleware` and the `./middleware.js` module are removed along with
  the retirement of the document-identity product line, together with the
  `PrivPortalOptions`, `IdentityMapping`, `MappingsResponse`, `SecretMapping` and
  `LeakInfo` types. The middleware sourced its data from `/api/sanitize/mappings`,
  which now returns secret keys only, so `sanitize()` / `resolve()` /
  `detectLeaks()` had degraded to identity functions. Callers should drop the
  middleware rather than migrate.

  Server-side PII regex scanning (`/api/sanitize/scan` and `/api/sanitize/redact`)
  is unaffected and remains the supported way to detect or redact PII.

### Unaffected

- `resolveUser` / `listUserBindings` / `createBinding` — cross-service account
  federation, unrelated to document PII.
- `chatCompletion` / `isHealthy` / `listModels`.
