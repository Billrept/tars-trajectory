#!/usr/bin/env bash
# Platform bootstrap for TARS on OpenShift — run once by a cluster admin. Safe to re-run.
#
#   KUBECONFIG=~/.kube/<admin>.conf deploy/openshift/bootstrap.sh
#
# 1. Installs the CloudNativePG operator (certified, OperatorHub).
# 2. Creates the namespace and the data layer (deploy/helm/tars-data): HA Postgres,
#    Redis queue + cache, a NooBaa object bucket.
# 3. Builds the two secrets the app chart expects (tars-runtime, tars-ca-certs).
# 4. Creates the CI deployer: a ServiceAccount with `admin` on this namespace only.
# CI never receives the admin credentials used here. Secrets are never printed.
set -euo pipefail

: "${KUBECONFIG:?Set KUBECONFIG to a cluster-admin kubeconfig}"
NS="${NS:-tars}"
DATA="${DATA_RELEASE:-tars-data}"
HELM="${HELM:-helm}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
k() { kubectl --request-timeout=30s "$@"; }
log() { printf '\n==> %s\n' "$*"; }
wait_for() { # wait_for <description> <timeout-seconds> <command...>
  local what=$1 timeout=$2; shift 2; local start=$SECONDS
  until "$@" >/dev/null 2>&1; do
    (( SECONDS - start > timeout )) && { echo "timed out waiting for $what" >&2; exit 1; }
    sleep 5
  done
  echo "ready: $what"
}

log "CloudNativePG operator"
k apply -f - <<'EOF'
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: cloudnative-pg
  namespace: openshift-operators
spec:
  channel: stable-v1
  name: cloudnative-pg
  source: certified-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
EOF
wait_for "CloudNativePG CRDs" 600 k get crd clusters.postgresql.cnpg.io
csv_ok() { k -n openshift-operators get csv -o jsonpath='{range .items[*]}{.metadata.name}={.status.phase}{"\n"}{end}' | grep -q '^cloudnative-pg.*=Succeeded$'; }
wait_for "CloudNativePG operator" 600 csv_ok

log "Namespace $NS"
k create namespace "$NS" --dry-run=client -o yaml | k apply -f -
k label namespace "$NS" app.kubernetes.io/part-of=tars --overwrite >/dev/null

log "Data layer ($DATA)"
"$HELM" upgrade --install "$DATA" "$ROOT/deploy/helm/tars-data" -n "$NS" --wait --timeout 15m
k -n "$NS" wait "cluster.postgresql.cnpg.io/$DATA-pg" --for=condition=Ready --timeout=15m
obc_bound() { [ "$(k -n "$NS" get obc "$DATA-objects" -o jsonpath='{.status.phase}')" = Bound ]; }
wait_for "object bucket" 300 obc_bound

log "Runtime secrets (tars-runtime, tars-ca-certs)"
secret() { k -n "$NS" get secret "$1" -o jsonpath="{.data.$2}" | base64 -d; }
cm() { k -n "$NS" get configmap "$1" -o jsonpath="{.data.$2}"; }
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT; chmod 700 "$work"
run="$work/runtime"; ca="$work/ca"; mkdir "$run" "$ca"   # one file per secret key

pg_uri=$(secret "$DATA-pg-app" uri)
redis_pw=$(secret "$DATA-redis" password)
service_token=$(secret tars-runtime SERVICE_TOKEN 2>/dev/null || true)
[ -n "$service_token" ] || service_token=$(openssl rand -hex 24) # 48 chars (tr </dev/urandom | head SIGPIPEs under pipefail)

printf '%s' "${pg_uri}?sslmode=verify-full&sslrootcert=/etc/tars/certs/postgres-ca.crt" > "$run/DATABASE_URL"
printf '%s' "redis://:${redis_pw}@${DATA}-redis-queue.${NS}.svc:6379/0" > "$run/QUEUE_REDIS_URL"
printf '%s' "redis://:${redis_pw}@${DATA}-redis-cache.${NS}.svc:6379/0" > "$run/CACHE_REDIS_URL"
secret "$DATA-objects" AWS_ACCESS_KEY_ID > "$run/AWS_ACCESS_KEY_ID"
secret "$DATA-objects" AWS_SECRET_ACCESS_KEY > "$run/AWS_SECRET_ACCESS_KEY"
printf '%s' "$service_token" > "$run/SERVICE_TOKEN"
k -n "$NS" create secret generic tars-runtime --dry-run=client -o yaml --from-file="$run" | k apply -f - >/dev/null

secret "$DATA-pg-ca" 'ca\.crt' > "$ca/postgres-ca.crt"
echo "in-cluster Redis uses plain redis:// inside the namespace; no CA" > "$ca/queue-redis-ca.crt"
cp "$ca/queue-redis-ca.crt" "$ca/cache-redis-ca.crt"
k -n "$NS" create secret generic tars-ca-certs --dry-run=client -o yaml --from-file="$ca" | k apply -f - >/dev/null
echo "secrets written (values not shown)"

log "CI deployer (admin on $NS only)"
k apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata: {name: tars-deployer, namespace: $NS}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: tars-deployer-admin, namespace: $NS}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: admin}
subjects: [{kind: ServiceAccount, name: tars-deployer, namespace: $NS}]
---
apiVersion: v1
kind: Secret
metadata:
  name: tars-deployer-token
  namespace: $NS
  annotations: {kubernetes.io/service-account.name: tars-deployer}
type: kubernetes.io/service-account-token
EOF
wait_for "deployer token" 120 sh -c "kubectl -n '$NS' get secret tars-deployer-token -o jsonpath='{.data.token}' | grep -q ."

bucket=$(cm "$DATA-objects" BUCKET_NAME); host=$(cm "$DATA-objects" BUCKET_HOST); port=$(cm "$DATA-objects" BUCKET_PORT)
apps=$(k get ingresses.config cluster -o jsonpath='{.spec.domain}')
api=$(k config view --minify -o jsonpath='{.clusters[0].cluster.server}')
log "Done. GitHub environment settings for this cluster:"
cat <<EOF
  secret   OPENSHIFT_SERVER        = $api
  secret   OPENSHIFT_TOKEN         = (kubectl -n $NS get secret tars-deployer-token -o jsonpath='{.data.token}' | base64 -d | gh secret set OPENSHIFT_TOKEN --env <env>)
  variable DEPLOY_AUTH             = token
  variable TARS_PLATFORM           = openshift
  variable K8S_NAMESPACE           = $NS
  variable TARS_HOST               = tars.$apps
  variable TARS_INGRESS_CLASS      = (empty)
  variable TARS_INGRESS_TLS_SECRET = (empty; router wildcard certificate)
  variable TARS_S3_ENDPOINT        = https://$host:$port
  variable TARS_S3_CA_CONFIGMAP    = openshift-service-ca.crt
  variable TARS_DATASET_BUCKET     = $bucket
  variable TARS_RESULT_BUCKET      = $bucket
  variable TARS_TRUSTED_PROXY_HOPS = 1
EOF
