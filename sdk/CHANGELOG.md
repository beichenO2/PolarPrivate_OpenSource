# Changelog

## 0.7.0

### Removed (breaking)

- `PrivPortalMiddleware` and the `privportal_sdk.middleware` module are removed
  along with the retirement of the document-identity product line. The client
  middleware sourced its data from `/api/sanitize/mappings`, which now returns
  secret keys only, so `sanitize()` / `resolve()` / `detect_leaks()` had degraded
  to identity functions. Callers should drop the middleware rather than migrate.

  Server-side PII regex scanning (`/api/sanitize/scan` and `/api/sanitize/redact`)
  is unaffected and remains the supported way to detect or redact PII.

### Changed

- The package version of record moves to `0.7.0`; `pyproject.toml` (previously
  stale at `0.1.0`) and `__version__` (previously `0.6.0`) are back in sync.
- Package description now reflects the actual surface: LLM proxy calls and
  cross-service identity bindings.

### Unaffected

- `resolve_user` / `list_user_bindings` / `create_binding` — cross-service
  account federation, unrelated to document PII.
- `chat_completion` / `achat_completion` / `is_healthy` / `list_models`.
