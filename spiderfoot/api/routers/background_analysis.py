"""Read automatic analysis from the scan's normal report view."""
import os
from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import SafeId, optional_auth

router = APIRouter()


@router.get('/scans/{scan_id}/analysis')
def analysis_status(scan_id: SafeId, api_key=Depends(optional_auth)):
    if os.environ.get('SF_BACKGROUND_ENABLED', 'false').lower() != 'true':
        return {'state': 'disabled'}
    from spiderfoot.services.background_analysis import job_status
    from spiderfoot.storage.minio_manager import get_storage_manager
    try:
        status = job_status(scan_id)
        if status['state'] == 'complete':
            status['report'] = get_storage_manager().get_report(scan_id, 'automatic', 'md').decode()
        return status
    except Exception:
        raise HTTPException(503, 'Automatic analysis is temporarily unavailable') from None
