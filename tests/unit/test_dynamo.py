
from fintrust import dynamo


def _create_upload(upload_id: str) -> None:
    """Create a test upload-tracking record."""
    dynamo.create_upload_tracking(
        upload_id=upload_id,
        bucket="test-raw-bucket",
        object_key=f"uploads/{upload_id}.csv",
    )


# ---------------------------------------------------------------------
# Existing risk-event tests
# ---------------------------------------------------------------------

def test_put_and_get_risk_event(aws_resources):
    account_id = "ACC-001"
    transaction_id = "TX-001"
    timestamp = "2026-09-29T10:00:00Z"

    dynamo.put_risk_event(
        account_id,
        transaction_id,
        timestamp,
        {
            "risk_level": "HIGH",
            "reason": "HIGH_AMOUNT",
        },
    )

    result = dynamo.get_risk_event(account_id, transaction_id)

    assert result is not None
    assert result["account_id"] == account_id
    assert result["transaction_id"] == transaction_id
    assert result["risk_level"] == "HIGH"
    assert result["reason"] == "HIGH_AMOUNT"


def test_get_account_risk_events(aws_resources):
    dynamo.put_risk_event(
        "ACC-001",
        "TX-001",
        "2026-09-29T10:00:00Z",
        {
            "risk_level": "HIGH",
            "reason": "HIGH_AMOUNT",
        },
    )

    dynamo.put_risk_event(
        "ACC-001",
        "TX-002",
        "2026-09-29T11:00:00Z",
        {
            "risk_level": "MEDIUM",
            "reason": "CROSS_BORDER",
        },
    )

    results = dynamo.get_account_risk_events("ACC-001")

    assert len(results) == 2
    assert {item["risk_level"] for item in results} == {
        "HIGH",
        "MEDIUM",
    }
    assert {item["transaction_id"] for item in results} == {
        "TX-001",
        "TX-002",
    }


def test_same_timestamp_transactions_are_stored_separately(aws_resources):
    timestamp = "2026-09-29T10:00:00Z"

    dynamo.put_risk_event(
        "ACC-001",
        "TX-001",
        timestamp,
        {
            "risk_level": "HIGH",
            "reason": "HIGH_AMOUNT",
        },
    )

    dynamo.put_risk_event(
        "ACC-001",
        "TX-002",
        timestamp,
        {
            "risk_level": "MEDIUM",
            "reason": "CROSS_BORDER",
        },
    )

    first = dynamo.get_risk_event("ACC-001", "TX-001")
    second = dynamo.get_risk_event("ACC-001", "TX-002")
    results = dynamo.get_account_risk_events("ACC-001")

    assert first is not None
    assert second is not None
    assert first["transaction_id"] == "TX-001"
    assert second["transaction_id"] == "TX-002"
    assert len(results) == 2


# ---------------------------------------------------------------------
# Upload-tracking tests
# ---------------------------------------------------------------------

def test_create_upload_tracking_initial_stages(aws_resources):
    upload_id = "UPLOAD-001"

    _create_upload(upload_id)

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["upload_id"] == upload_id
    assert result["record_type"] == "SUMMARY"
    assert result["bucket"] == "test-raw-bucket"
    assert result["object_key"] == f"uploads/{upload_id}.csv"
    assert result["status"] == "PROCESSING"

    assert result["stages"] == {
        "csv_uploaded": "COMPLETED",
        "ingestion_started": "WAITING",
        "validation": "WAITING",
        "transactions_queued": "WAITING",
        "risk_scoring": "WAITING",
        "results_persisted": "WAITING",
    }

    assert result["total_records"] == 0
    assert result["valid_records"] == 0
    assert result["quarantined_records"] == 0
    assert result["queued_records"] == 0
    assert result["scored_records"] == 0
    assert result["completed_records"] == 0
    assert result["duplicate_records"] == 0


def test_set_upload_validation_results(aws_resources):
    upload_id = "UPLOAD-002"

    _create_upload(upload_id)

    dynamo.mark_workflow_started(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=3,
        valid_records=2,
        quarantined_records=1,
    )

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["total_records"] == 3
    assert result["valid_records"] == 2
    assert result["quarantined_records"] == 1

    assert result["stages"]["ingestion_started"] == "COMPLETED"
    assert result["stages"]["validation"] == "COMPLETED"
    assert result["stages"]["transactions_queued"] == "IN_PROGRESS"
    assert result["stages"]["risk_scoring"] == "WAITING"
    assert result["stages"]["results_persisted"] == "WAITING"


def test_mark_upload_queued_updates_progress(aws_resources):
    upload_id = "UPLOAD-003"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=3,
        valid_records=2,
        quarantined_records=1,
    )

    dynamo.mark_upload_queued(
        upload_id=upload_id,
        queued_records=2,
    )

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["queued_records"] == 2
    assert result["stages"]["transactions_queued"] == "COMPLETED"
    assert result["stages"]["risk_scoring"] == "IN_PROGRESS"
    assert result["stages"]["results_persisted"] == "WAITING"
    assert result["status"] == "PROCESSING"


def test_mark_transaction_persisted_increments_once(aws_resources):
    upload_id = "UPLOAD-004"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=1,
        valid_records=1,
        quarantined_records=0,
    )

    dynamo.mark_upload_queued(upload_id, 1)

    first_result = dynamo.mark_transaction_persisted(
        upload_id,
        "TX-001",
    )

    duplicate_result = dynamo.mark_transaction_persisted(
        upload_id,
        "TX-001",
    )

    result = dynamo.get_upload_tracking(upload_id)

    assert first_result is True
    assert duplicate_result is False
    assert result is not None
    assert result["completed_records"] == 1


def test_mark_duplicate_transaction_scored_increments_once(aws_resources):
    upload_id = "UPLOAD-009"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=1,
        valid_records=1,
        quarantined_records=0,
    )

    dynamo.mark_upload_queued(upload_id, 1)

    first_result = dynamo.mark_transaction_scored(
        upload_id,
        "TX-001",
        duplicate_transaction=True,
    )

    second_result = dynamo.mark_transaction_scored(
        upload_id,
        "TX-001",
        duplicate_transaction=True,
    )

    result = dynamo.get_upload_tracking(upload_id)

    assert first_result is True
    assert second_result is False
    assert result is not None
    assert result["scored_records"] == 1
    assert result["duplicate_records"] == 1


def test_upload_completes_when_all_transactions_are_persisted(aws_resources):
    upload_id = "UPLOAD-005"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=3,
        valid_records=3,
        quarantined_records=0,
    )

    dynamo.mark_upload_queued(upload_id, 3)

    for transaction_id in ("TX-001", "TX-002"):
        assert dynamo.mark_transaction_scored(
            upload_id,
            transaction_id,
        ) is True

        assert dynamo.mark_transaction_persisted(
            upload_id,
            transaction_id,
        ) is True

    intermediate_result = dynamo.get_upload_tracking(upload_id)

    assert intermediate_result is not None
    assert intermediate_result["completed_records"] == 2
    assert intermediate_result["status"] == "PROCESSING"
    assert intermediate_result["stages"]["results_persisted"] == "WAITING"

    assert dynamo.mark_transaction_scored(
        upload_id,
        "TX-003",
    ) is True

    assert dynamo.mark_transaction_persisted(
        upload_id,
        "TX-003",
    ) is True

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["completed_records"] == 3
    assert result["status"] == "COMPLETED"
    assert result["current_stage"] == "results_persisted"
    assert result["stages"]["risk_scoring"] == "COMPLETED"
    assert result["stages"]["results_persisted"] == "COMPLETED"


def test_zero_valid_records_complete_without_scoring(aws_resources):
    upload_id = "UPLOAD-006"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=2,
        valid_records=0,
        quarantined_records=2,
    )

    # Queueing must still be explicitly confirmed, even when there
    # are no valid transactions to send to SQS.
    before_queue_confirmation = dynamo.get_upload_tracking(upload_id)

    assert before_queue_confirmation is not None
    assert (
        before_queue_confirmation["stages"]["transactions_queued"]
        == "IN_PROGRESS"
    )

    dynamo.mark_upload_queued(upload_id, 0)

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["queued_records"] == 0
    assert result["completed_records"] == 0
    assert result["status"] == "COMPLETED"
    assert result["stages"]["transactions_queued"] == "COMPLETED"
    assert result["stages"]["risk_scoring"] == "COMPLETED"
    assert result["stages"]["results_persisted"] == "COMPLETED"


def test_fast_worker_completion_is_not_regressed(aws_resources, monkeypatch):
    upload_id = "UPLOAD-007"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=1,
        valid_records=1,
        quarantined_records=0,
    )

    # Simulate the scoring worker finishing the transaction before
    # ingestion has finished its queue-completion update.
    assert dynamo.mark_transaction_scored(
        upload_id,
        "TX-001",
    ) is True

    assert dynamo.mark_transaction_persisted(
        upload_id,
        "TX-001",
    ) is True

    original_update_item = dynamo.upload_tracking_table.update_item

    def update_item_with_worker_race(*args, **kwargs):
        response = original_update_item(*args, **kwargs)

        update_expression = kwargs.get("UpdateExpression", "")

        if (
            "queued_records = :queued" in update_expression
            and "#stages.#transactions_queued = :completed"
            in update_expression
        ):
            # The queue stage has just been marked complete.
            # Let the worker's completion check run before
            # mark_upload_queued performs its next update.
            dynamo._complete_upload_if_ready(upload_id)

        return response

    monkeypatch.setattr(
        dynamo.upload_tracking_table,
        "update_item",
        update_item_with_worker_race,
    )

    dynamo.mark_upload_queued(upload_id, 1)

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["completed_records"] == 1
    assert result["status"] == "COMPLETED"
    assert result["stages"]["transactions_queued"] == "COMPLETED"
    assert result["stages"]["risk_scoring"] == "COMPLETED"
    assert result["stages"]["results_persisted"] == "COMPLETED"


def test_failed_upload_is_not_marked_completed(aws_resources):
    upload_id = "UPLOAD-008"

    _create_upload(upload_id)
    dynamo.mark_ingestion_started(upload_id)

    dynamo.set_upload_validation_results(
        upload_id=upload_id,
        total_records=1,
        valid_records=1,
        quarantined_records=0,
    )

    dynamo.mark_upload_queued(upload_id, 1)

    dynamo.mark_upload_failed(
        upload_id,
        "Test processing failure",
    )

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["status"] == "FAILED"
    assert result["failure_reason"] == "Test processing failure"

    # Even if the transaction is subsequently recorded, a failed
    # upload must not be changed to COMPLETED.
    dynamo.mark_transaction_persisted(upload_id, "TX-001")

    result = dynamo.get_upload_tracking(upload_id)

    assert result is not None
    assert result["status"] == "FAILED"
    assert result["stages"]["results_persisted"] != "COMPLETED"