"""Idempotently initialize private buckets before dependent services start."""
from spiderfoot.storage.minio_manager import get_storage_manager
manager = get_storage_manager()
for name in ('sf-reports', 'sf-logs', 'sf-data', 'sf-pg-backups', 'sf-qdrant-snapshots'):
    if not manager.client.bucket_exists(name):
        manager.client.make_bucket(name)
print('Storage buckets ready')
