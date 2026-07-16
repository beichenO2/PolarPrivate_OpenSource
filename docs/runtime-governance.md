# PolarPrivate Runtime Governance

## Authority boundary

- PolarPort (`127.0.0.1:11050`) is the sole port allocation authority.
- PolarProcess (`127.0.0.1:11055`) is the sole lifecycle authority.
- Project launchers claim their preferred port, then replace the shell with the foreground service process.
- Persistent services must not use background shells, PID files, direct signals, or a second process manager.

## Services owned by this repository

| Service ID | Launcher | Preferred port | Health | Auto-start |
|---|---|---:|---|---|
| `privportal-backend` | `Start/backend.sh` | 12790 | `/health` | true |
| `privportal-frontend` | `Start/frontend.sh` | 12795 | `/` | true |

The frontend launcher injects the backend target through
`POLARPRIVATE_BACKEND_URL`. The Vite configuration also accepts
`POLARPRIVATE_FRONTEND_PORT` and refuses port fallback with `strictPort`.

## Compatibility entrypoints

`backend/Start/start.sh`, `stop.sh`, and `restart.sh` remain as lifecycle
clients for existing callers. They call only the exact
`privportal-backend` PolarProcess endpoint and never manage a PID directly.

## External and scheduled services

- `polarprivate4taoci` is owned by the separate `~/Desktop/Server`
  repository. This repository must not edit, register, stop, or restart it.
- `privportal-vault-sync` is a no-port hourly task already scheduled by
  PolarProcess. Runtime migration must not execute the backup task.

## Safe registration

Run `scripts/register-runtime.sh` to update the two PolarProcess records
without starting or restarting either service. Registration is intentionally
separate from lifecycle actions so live PIDs can be compared before and after.
