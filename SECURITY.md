# Security — PolarPrivate (Open Source)

PolarPrivate is a **localhost-only** secret vault and LLM proxy. This document is for open-source consumers. Full design notes live in [`docs/security-model.md`](docs/security-model.md).

## Assets

| Asset | Location | Notes |
|-------|----------|-------|
| Master Password | User memory / session | Derives Fernet keys; never stored plaintext |
| Secret values | SQLite (Fernet ciphertext) | API keys, tokens, signing material |
| Vault DB file | `./data` (Docker) or local SQLite path | Contains ciphertext + salt + wrapped keys |
| Audit / config | Same SQLite DB | No secret plaintext |

## Trust boundaries

- **In scope:** Your machine, PolarPrivate process memory while unlocked, localhost HTTP to `127.0.0.1:12790`.
- **Out of scope:** Remote attackers on the public Internet (service is not meant to be exposed).
- **Agent / LLM context:** Callers must use QCSA capability codes and proxy routes — they must **not** receive secret plaintext.

**Important:** Binding to `127.0.0.1` is necessary but **not sufficient**. Treat **localhost as a convenience transport, not a universal trust boundary.**

### Localhost and DNS rebinding

Malicious web pages or compromised local browsers can sometimes reach `127.0.0.1` services via **DNS rebinding** or browser same-site quirks. PolarPrivate does not implement a full anti-rebinding token layer. Mitigations:

- Do not browse untrusted sites in the same profile while the vault is unlocked.
- Do not reverse-proxy PolarPrivate to `0.0.0.0` or a public hostname.
- Prefer Docker / `privportal serve` defaults (`127.0.0.1` only).

## R9 — no reveal

There is **no** `/api/secrets/{id}/reveal` and no service-token path that returns secret plaintext to clients. The GUI is **write-only** for secrets.

Secrets flow only through closed channels:

| Class | Route | Behavior |
|-------|-------|----------|
| **A** | `/proxy/{service}/{path}` | Inject auth headers upstream; plaintext never in HTTP bodies |
| **B** | `/sign/{provider}/{action}` | HMAC/sign with secret; returns headers only |
| **D** | `/api/d-class/grant` | SHA256 whitelist–gated grant for specific SDK integrations |

## Non-goals

- Not a hosted multi-tenant secret manager.
- Not safe to expose on LAN/WAN without additional hardening.
- PII `/api/sanitize/*` is stateless regex scan/redact — not a guarantee that all LLM traffic is filtered.

## Reporting vulnerabilities

Please **do not** open public GitHub issues for exploitable findings.

Email maintainers privately (see repository contact / Polarisor security channel) with:

1. Description and impact  
2. Reproduction steps on a current `PolarPrivate_OpenSource` commit  
3. Your environment (OS, Docker vs `privportal serve`)

We aim to acknowledge within 7 days.
