#!/usr/bin/env bash
# Fail when a known secret value or a common secret pattern appears in any
# file git would commit (tracked + untracked-not-ignored).
# Never prints secret values — only the variable name and the file path.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
CRED_FILE="${CRED_FILE:-/home/ubuntu/AI-code/Doris-test/credentials.env}"
SELF="scripts/check-secrets.sh"
fail=0

files=()
while IFS= read -r -d '' f; do
  [[ -f "$f" && "$f" != "$SELF" ]] && files+=("$f")
done < <(git ls-files -z --cached --others --exclude-standard)

# 1) Exact values of *PASSWORD* / *SECRET* variables from the credentials file.
#    The value is fed to grep via a pipe (-f -), never as a command-line argument.
if [[ -r "$CRED_FILE" ]]; then
  while IFS='=' read -r name _; do
    [[ "$name" =~ (PASSWORD|SECRET) ]] || continue
    # An empty pattern would match every file; skip short/empty values.
    len="$(set -a; source "$CRED_FILE"; v="${!name}"; echo "${#v}")"
    [[ "$len" -ge 4 ]] || continue
    for f in "${files[@]}"; do
      if (set -a; source "$CRED_FILE"; printf '%s\n' "${!name}") | grep -qIF -f - -- "$f"; then
        echo "LEAK: value of $name found in $f"
        fail=1
      fi
    done
  done < <(grep -E '^[A-Za-z_]+=' "$CRED_FILE")
else
  echo "WARN: $CRED_FILE not readable — skipped exact-value check"
fi

# 1b) Passwords held only in Secrets Manager (created by infra/*.sh, always in us-east-1). The value
#     stays in a shell variable and reaches grep through a process substitution — never argv, never printed.
for sid in ${SM_SECRETS:-doris-mcp/mcp_svc doris-mcp/cognito-demo-user}; do
  if ! pw="$(aws secretsmanager get-secret-value --region "${SM_REGION:-us-east-1}" --secret-id "$sid" \
               --query SecretString --output text 2>/dev/null |
             python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])' 2>/dev/null)" || [[ ${#pw} -lt 4 ]]; then
    # A check that could not run is not a pass: fix the AWS credentials, then re-run.
    echo "FAIL: cannot read secret $sid — its exact-value check did not run"
    fail=1
    continue
  fi
  while IFS= read -r f; do
    echo "LEAK: password of secret $sid found in $f"
    fail=1
  done < <(grep -lIF -f <(printf '%s\n' "$pw") -- "${files[@]}" 2>/dev/null)
done
unset pw

# 2) Generic patterns: AWS access keys, private keys, inline passwords.
#    Placeholders such as IDENTIFIED BY '<password>' or '${DORIS_RO_PASSWORD}' are not secrets.
patterns='AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|aws_secret_access_key[[:space:]]*=|IDENTIFIED BY '"'"'[^<$'"'"'][^<'"'"']{3,}'"'"
for f in "${files[@]}"; do
  if grep -qIE -- "$patterns" "$f"; then
    echo "LEAK: secret-like pattern in $f"
    fail=1
  fi
done

if [[ $fail -ne 0 ]]; then
  echo "check-secrets: FAILED — do not commit"
  exit 1
fi
echo "check-secrets: OK (${#files[@]} files scanned)"
