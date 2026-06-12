#!/usr/bin/env python3
"""Helper for vault-sync.sh restore — safely passes large payload + password to API."""
import json
import sys
import urllib.request

def main():
    if len(sys.argv) < 4:
        print("Usage: vault-restore-helper.py <backup_file> <master_password> <api_base>", file=sys.stderr)
        sys.exit(1)

    backup_path, master_pw, api_base = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(backup_path) as f:
        backup = json.load(f)

    body = json.dumps({
        "payload": backup["payload"],
        "salt": backup["salt"],
        "master_password": master_pw,
        "strategy": "merge",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{api_base}/api/vault/restore",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"API error {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)

    parts = []
    for k in ("projects", "identities", "secrets", "bindings"):
        if result.get(k, 0) > 0:
            parts.append(f"{result[k]} {k}")
    skipped = result.get("skipped", 0)
    if parts:
        print(f"Imported: {', '.join(parts)} (skipped {skipped})")
    else:
        print(f"All {skipped} records already exist — nothing to import")

if __name__ == "__main__":
    main()
