from __future__ import annotations

import unittest.mock as mock
import pytest
from agenttrace.app.worker import worker_runner, main

def test_worker_runner_wraps_async_pipeline():
    job = {
        "job_id": "job-1",
        "analysis_id": "analysis-1",
        "repository_id": "repo-1",
        "snapshot_id": "snap-1",
        "analysis_version": "analysis-v2",
    }
    
    with mock.patch("agenttrace.app.worker.run_analysis_pipeline") as mock_pipeline:
        mock_pipeline.return_value = {"analysis_id": "analysis-1", "status": "COMPLETED"}
        
        res = worker_runner(job)
        
        assert res == {"analysis_id": "analysis-1", "status": "COMPLETED"}
        mock_pipeline.assert_called_once_with(job)

@mock.patch("agenttrace.app.worker.time.sleep", side_effect=KeyboardInterrupt)
@mock.patch("agenttrace.app.worker.DurableAnalysisWorker")
@mock.patch("agenttrace.app.worker.init_database")
@mock.patch("agenttrace.app.worker.PsycopgSqlConnection")
def test_worker_main_loop_stops_on_interrupt(mock_conn, mock_init, mock_worker_cls, mock_sleep):
    mock_worker = mock.MagicMock()
    mock_worker.run_once.return_value = {"status": "idle"}
    mock_worker_cls.return_value = mock_worker
    
    with pytest.raises(KeyboardInterrupt):
        main()
        
    mock_init.assert_called_once()
    mock_worker.run_once.assert_called_once()
