from tars_contracts.tls import redis_tls_kwargs

def test_redis_ca_only_passed_when_configured(monkeypatch):
    monkeypatch.delenv('CACHE_REDIS_CA_CERT',raising=False)
    assert redis_tls_kwargs('rediss://h:6380/0','CACHE_REDIS_CA_CERT')=={}
    monkeypatch.setenv('CACHE_REDIS_CA_CERT','/etc/tars/certs/cache-ca.crt')
    assert redis_tls_kwargs('rediss://h:6380/0','CACHE_REDIS_CA_CERT')=={'ssl_ca_certs':'/etc/tars/certs/cache-ca.crt'}
    assert redis_tls_kwargs('redis://h:6379/0','CACHE_REDIS_CA_CERT')=={} # plain redis:// rejects TLS options

def test_queue_settings_use_managed_redis_ca(monkeypatch):
    from jobs_service.config import redis_settings
    monkeypatch.setenv('QUEUE_REDIS_URL','rediss://user:secret@queue.example:6380/0')
    monkeypatch.delenv('QUEUE_REDIS_CA_CERT',raising=False)
    plain=redis_settings();assert plain.ssl and plain.ssl_ca_certs is None
    monkeypatch.setenv('QUEUE_REDIS_CA_CERT','/etc/tars/certs/queue-ca.crt')
    assert redis_settings().ssl_ca_certs=='/etc/tars/certs/queue-ca.crt'

def test_plain_queue_url_ignores_ca(monkeypatch):
    from jobs_service.config import redis_settings
    monkeypatch.setenv('QUEUE_REDIS_URL','redis://queue:6379/0');monkeypatch.setenv('QUEUE_REDIS_CA_CERT','/etc/tars/certs/queue-ca.crt')
    assert redis_settings().ssl_ca_certs is None
