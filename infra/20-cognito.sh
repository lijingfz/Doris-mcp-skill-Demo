#!/usr/bin/env bash
# P0 / T0.5 — Cognito for Quick → AgentCore Gateway (inbound CUSTOM_JWT).
#   * user pool doris-mcp-quick (admin-created users only) + hosted UI domain
#   * resource server doris-mcp with scope "invoke"
#   * client A quick-user    : authorization code + PKCE (Quick "User authentication")
#   * client B quick-service : client_credentials       (Quick "Service authentication", smoke tests)
#   * user demo; its password is generated into Secrets Manager doris-mcp/cognito-demo-user
# Secrets are never printed or passed as command-line arguments.
# QUICK_CALLBACK overrides the OAuth redirect URL (use the one Quick shows in T0.7).
# Dry-run by default. APPLY=1 to execute. Safe to re-run (also re-syncs client A settings).
source "$(dirname "$0")/lib.sh"

POOL_NAME=doris-mcp-quick
DOMAIN_PREFIX="doris-mcp-$ACCOUNT_ID"
RS_ID=doris-mcp
SCOPE="$RS_ID/invoke"
QUICK_CALLBACK="${QUICK_CALLBACK:-https://$AWS_REGION.quicksight.aws.amazon.com/sn/oauthcallback}"
DEMO_USER=demo
DEMO_SECRET=doris-mcp/cognito-demo-user

# --- user pool --------------------------------------------------------------
POOL_ID="$(none_to_empty "$(aws cognito-idp list-user-pools --max-results 60 \
  --query "UserPools[?Name=='$POOL_NAME'].Id | [0]" --output text)")"
if [[ -z "$POOL_ID" ]]; then
  POOL_ID="$(run aws cognito-idp create-user-pool --pool-name "$POOL_NAME" \
    --admin-create-user-config AllowAdminCreateUserOnly=true \
    --policies 'PasswordPolicy={MinimumLength=16,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true,RequireSymbols=false}' \
    --username-configuration CaseSensitive=false \
    --user-pool-tags "Project=$PROJECT_TAG" \
    --query UserPool.Id --output text)"
  POOL_ID="${POOL_ID:-$(placeholder user-pool)}"
else
  log "user pool exists: $POOL_ID"
fi

# --- hosted UI domain (classic hosted UI, works on every feature plan) -------
DOMAIN_OWNER="$(none_to_empty "$(aws cognito-idp describe-user-pool-domain --domain "$DOMAIN_PREFIX" \
  --query DomainDescription.UserPoolId --output text)")"
if [[ -z "$DOMAIN_OWNER" ]]; then
  run aws cognito-idp create-user-pool-domain --domain "$DOMAIN_PREFIX" --user-pool-id "$POOL_ID" \
    --managed-login-version 1 >/dev/null
elif [[ "$DOMAIN_OWNER" != "$POOL_ID" ]]; then
  log "FATAL: domain $DOMAIN_PREFIX belongs to another pool ($DOMAIN_OWNER)"; exit 1
else
  log "domain exists: $DOMAIN_PREFIX"
fi

# --- resource server + scope ------------------------------------------------
if ! is_placeholder "$POOL_ID" && aws cognito-idp describe-resource-server --user-pool-id "$POOL_ID" \
     --identifier "$RS_ID" >/dev/null 2>&1; then
  log "resource server exists: $RS_ID"
else
  run aws cognito-idp create-resource-server --user-pool-id "$POOL_ID" --identifier "$RS_ID" \
    --name "$RS_ID" --scopes ScopeName=invoke,ScopeDescription=invoke-doris-mcp-tools >/dev/null
fi

# --- app clients ------------------------------------------------------------
client_lookup() {
  is_placeholder "$POOL_ID" && return 0
  none_to_empty "$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --max-results 60 \
    --query "UserPoolClients[?ClientName=='$1'].ClientId | [0]" --output text)"
}

# update-user-pool-client resets omitted fields, so create and update share one full argument list.
CLIENT_A_ARGS=(--allowed-o-auth-flows code --allowed-o-auth-scopes openid "$SCOPE"
  --allowed-o-auth-flows-user-pool-client --supported-identity-providers COGNITO
  --callback-urls "$QUICK_CALLBACK" --explicit-auth-flows ALLOW_REFRESH_TOKEN_AUTH
  --prevent-user-existence-errors ENABLED --enable-token-revocation
  --access-token-validity 60 --id-token-validity 60 --refresh-token-validity 30
  --token-validity-units AccessToken=minutes,IdToken=minutes,RefreshToken=days)
CLIENT_B_ARGS=(--allowed-o-auth-flows client_credentials --allowed-o-auth-scopes "$SCOPE"
  --allowed-o-auth-flows-user-pool-client --prevent-user-existence-errors ENABLED
  --access-token-validity 60 --token-validity-units AccessToken=minutes)

CLIENT_A_ID="$(client_lookup quick-user)"
if [[ -z "$CLIENT_A_ID" ]]; then
  CLIENT_A_ID="$(run aws cognito-idp create-user-pool-client --user-pool-id "$POOL_ID" \
    --client-name quick-user --generate-secret "${CLIENT_A_ARGS[@]}" \
    --query UserPoolClient.ClientId --output text)"
  CLIENT_A_ID="${CLIENT_A_ID:-$(placeholder client-a)}"
else
  log "client quick-user exists: $CLIENT_A_ID (re-applying settings, callback=$QUICK_CALLBACK)"
  run aws cognito-idp update-user-pool-client --user-pool-id "$POOL_ID" --client-id "$CLIENT_A_ID" \
    --client-name quick-user "${CLIENT_A_ARGS[@]}" --query UserPoolClient.ClientId --output text >/dev/null
fi

CLIENT_B_ID="$(client_lookup quick-service)"
if [[ -z "$CLIENT_B_ID" ]]; then
  CLIENT_B_ID="$(run aws cognito-idp create-user-pool-client --user-pool-id "$POOL_ID" \
    --client-name quick-service --generate-secret "${CLIENT_B_ARGS[@]}" \
    --query UserPoolClient.ClientId --output text)"
  CLIENT_B_ID="${CLIENT_B_ID:-$(placeholder client-b)}"
else
  log "client quick-service exists: $CLIENT_B_ID"
fi

# --- demo user (password generated into Secrets Manager, never printed or put in argv) ---
if ! is_placeholder "$POOL_ID" && aws cognito-idp admin-get-user --user-pool-id "$POOL_ID" \
     --username "$DEMO_USER" >/dev/null 2>&1; then
  log "user $DEMO_USER exists"
elif [[ "$APPLY" != "1" ]]; then
  log "DRY-RUN: create secret $DEMO_SECRET with a generated password (if missing)"
  run aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username "$DEMO_USER" --message-action SUPPRESS
  log "DRY-RUN: admin-set-user-password --permanent for $DEMO_USER from secret $DEMO_SECRET (via 0600 temp file)"
else
  private_tmp
  if ! aws secretsmanager describe-secret --secret-id "$DEMO_SECRET" >/dev/null 2>&1; then
    pw="$(aws secretsmanager get-random-password --password-length 20 --exclude-punctuation \
      --require-each-included-type --query RandomPassword --output text)"
    printf '{"username":"%s","password":"%s"}' "$DEMO_USER" "$pw" > "$PRIVATE_TMP"
    unset pw
    aws secretsmanager create-secret --name "$DEMO_SECRET" --tags "Key=Project,Value=$PROJECT_TAG" \
      --description "Cognito demo user for Quick -> doris-mcp-gw" \
      --secret-string "file://$PRIVATE_TMP" --query ARN --output text >/dev/null
    log "secret $DEMO_SECRET created"
  fi
  aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username "$DEMO_USER" \
    --message-action SUPPRESS --query User.Username --output text >/dev/null
  aws secretsmanager get-secret-value --secret-id "$DEMO_SECRET" --query SecretString --output text |
    python3 -c 'import json,sys; s=json.load(sys.stdin); json.dump({"UserPoolId": sys.argv[1], "Username": s["username"], "Password": s["password"], "Permanent": True}, open(sys.argv[2], "w"))' \
      "$POOL_ID" "$PRIVATE_TMP"
  aws cognito-idp admin-set-user-password --cli-input-json "file://$PRIVATE_TMP"
  rm -f "$PRIVATE_TMP"
  log "user $DEMO_USER created with a permanent password (stored only in $DEMO_SECRET)"
fi

# --- state ------------------------------------------------------------------
if ! is_placeholder "$POOL_ID"; then
  state_set COGNITO_POOL_ID "$POOL_ID"
  state_set COGNITO_DOMAIN "$DOMAIN_PREFIX.auth.$AWS_REGION.amazoncognito.com"
  state_set DISCOVERY_URL "https://cognito-idp.$AWS_REGION.amazonaws.com/$POOL_ID/.well-known/openid-configuration"
  state_set QUICK_CALLBACK "$QUICK_CALLBACK"
fi
is_placeholder "$CLIENT_A_ID" || state_set CLIENT_A_ID "$CLIENT_A_ID"
is_placeholder "$CLIENT_B_ID" || state_set CLIENT_B_ID "$CLIENT_B_ID"
log "done (APPLY=$APPLY)"
