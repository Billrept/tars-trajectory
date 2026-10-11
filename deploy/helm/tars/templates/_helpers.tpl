{{- define "tars.labels" -}}
app.kubernetes.io/part-of: tars
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "tars.selector" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/name: {{ .name }}
{{- end }}

{{/* registry/name@digest when CI supplied a digest, otherwise registry/name:tag */}}
{{- define "tars.image" -}}
{{- $ref := index .root.Values.images .image -}}
{{- if and $ref $ref.digest -}}
{{ .root.Values.image.registry }}/{{ .image }}@{{ $ref.digest }}
{{- else -}}
{{ .root.Values.image.registry }}/{{ .image }}:{{ .root.Values.image.tag }}
{{- end -}}
{{- end }}

{{- define "tars.podSecurity" -}}
runAsNonRoot: true
{{- if ne .Values.platform "openshift" }}
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
{{- end }}
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{- define "tars.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end }}

{{/* Non-secret configuration shared by every Python container. Secrets come from envFrom. */}}
{{- define "tars.env" -}}
{{- $c := .Values.config }}
- {name: APP_ENV, value: {{ $c.appEnv | quote }}}
- {name: CORS_ORIGINS, value: {{ $c.publicOrigin | quote }}}
- {name: EPHEMERIS_URL, value: "http://{{ .Release.Name }}-ephemeris:8000"}
- {name: S3_ENDPOINT_URL, value: {{ $c.s3EndpointUrl | quote }}}
- {name: AWS_REGION, value: {{ $c.region | quote }}}
- {name: DATASET_BUCKET, value: {{ $c.datasetBucket | quote }}}
- {name: RESULT_BUCKET, value: {{ $c.resultBucket | quote }}}
- {name: DATABASE_SCHEMA, value: {{ $c.databaseSchema | quote }}}
- {name: CACHE_PREFIX, value: "tars:{{ $c.appEnv }}"}
- {name: COOKIE_SECURE, value: {{ $c.cookieSecure | quote }}}
- {name: TRUSTED_PROXY_HOPS, value: {{ $c.trustedProxyHops | quote }}}
- {name: GLOBAL_QUEUE_CAP, value: {{ $c.globalQueueCap | quote }}}
- {name: RATE_LIMIT_PER_MIN, value: {{ $c.rateLimitPerMin | quote }}}
- {name: RATE_LIMIT_PER_DAY, value: {{ $c.rateLimitPerDay | quote }}}
- {name: ACTIVE_MANIFEST_TTL_SECONDS, value: {{ $c.activeManifestTtlSeconds | quote }}}
- {name: CREATE_BUCKETS, value: "0"}
- {name: QUEUE_REDIS_CA_CERT, value: /etc/tars/certs/queue-redis-ca.crt}
- {name: CACHE_REDIS_CA_CERT, value: /etc/tars/certs/cache-redis-ca.crt}
- {name: NUMBA_CACHE_DIR, value: /tmp/numba}
- {name: HOME, value: /tmp}
{{- end }}

{{- define "tars.envFrom" -}}
- secretRef:
    name: {{ .Values.secrets.runtime }}
{{- end }}

{{- define "tars.volumes" -}}
- name: tmp
  emptyDir: {sizeLimit: 256Mi}
- name: ca-certs
  secret:
    secretName: {{ .Values.secrets.caCerts }}
    defaultMode: 0444
{{- end }}

{{- define "tars.volumeMounts" -}}
- {name: tmp, mountPath: /tmp}
- {name: ca-certs, mountPath: /etc/tars/certs, readOnly: true}
{{- end }}
