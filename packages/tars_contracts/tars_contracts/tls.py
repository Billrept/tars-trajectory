"""TLS options for managed Redis (e.g. IBM Cloud Databases for Redis, rediss:// with a private CA).

Each managed instance has its own CA certificate, so the path comes from a per-client
environment variable. It is applied only to rediss:// URLs: a plain redis:// connection
rejects TLS options, and the same deployment config may point at either.
"""
import os

def redis_tls_kwargs(url,ca_env):
    path=os.environ.get(ca_env)
    return {'ssl_ca_certs':path} if path and url.startswith('rediss://') else {}
