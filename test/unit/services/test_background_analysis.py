import uuid
from unittest.mock import Mock, patch, MagicMock
import pytest
from spiderfoot.services import background_analysis as bg


def test_stable_point_ids_are_valid_and_separate_scans():
    a = bg.point_id('scan-a', 'event')
    assert str(uuid.UUID(a)) == a
    assert a == bg.point_id('scan-a', 'event')
    assert a != bg.point_id('scan-b', 'event')


@pytest.mark.parametrize('vectors,count,dims', [([],1,3), ([[1,2]],1,3), ([[1,2,3]],2,3)])
def test_incomplete_embeddings_fail_before_job_can_advance(vectors,count,dims):
    with pytest.raises(RuntimeError):
        bg.require_vectors(vectors,count,dims)


def test_complete_embeddings_are_accepted():
    bg.require_vectors([[0,1,2],[2,1,0]],2,3)


def test_recovery_uses_saved_report_without_another_paid_call():
    processor = bg.Processor.__new__(bg.Processor)
    processor.storage = Mock()
    processor.storage.get_report.return_value = b'existing report'
    processor.session = Mock()
    processor.model = 'configured-model'
    processor.emit = Mock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'status':'FINISHED','name':'test','seed_target':'example.test'}
    with patch.object(bg, 'update') as update:
        processor.process(conn, {'scan_id':'scan-a','stage':2})
    processor.session.post.assert_not_called()
    update.assert_called_once_with(conn,'scan-a',state='complete',stage=3,model='configured-model',error='')


def test_aborted_scan_is_not_sent_for_analysis():
    processor = bg.Processor.__new__(bg.Processor)
    processor.session = Mock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'status':'ABORTED'}
    with patch.object(bg, 'update') as update:
        processor.process(conn, {'scan_id':'scan-a','stage':0})
    processor.session.post.assert_not_called()
    update.assert_called_once_with(conn,'scan-a',state='cancelled')


def test_historical_scan_is_not_shown_as_queued_forever():
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.side_effect = [None, {'status':'FINISHED','ended':1}]
    with patch.object(bg,'connect',return_value=conn), patch.dict(bg.os.environ,{'SF_BACKGROUND_SINCE_MS':'2'}):
        assert bg.job_status('old-scan')['state'] == 'not_scheduled'
    conn.close.assert_called_once()
