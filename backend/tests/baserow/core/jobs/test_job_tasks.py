import pytest
from unittest.mock import Mock, patch
from celery.exceptions import SoftTimeLimitExceeded
from requests.exceptions import ConnectionError

from django.core.cache import cache

from baserow.core.jobs.models import Job
from baserow.core.jobs.registries import JobType
from baserow.core.jobs.cache import job_progress_key
from baserow.core.jobs.tasks import run_async_job
from baserow.core.jobs.constants import (
    JOB_FAILED,
    JOB_FINISHED,
    JOB_PENDING,
)


class TmpCustomJobType(JobType):
    type = "custom_job_type"

    max_count = 1

    model_class = Job

    job_exceptions_map = {
        ConnectionError: "Error message",
    }

    def run(self, job, progress):
        pass


@pytest.mark.django_db(transaction=True, databases=["default", "default-copy"])
@patch("baserow.core.jobs.registries.JobTypeRegistry.get_by_model")
@pytest.mark.timeout(10)
def test_run_task(mock_get_by_model, data_fixture):
    data_fixture.register_temp_job_types()

    def run(job, progress):

        progress.increment(50, "test")

        # Check if the job has updated in the transaction
        job.refresh_from_db()
        assert job.progress_percentage == 50
        assert job.state == "test"

        # We're using the second connection to check if we can get the most recent
        # progress value while the transaction is still active.
        job_copy = Job.objects.using("default-copy").get(pk=job.id)
        # Normal progress is expected to be 0
        assert job_copy.progress_percentage == 0
        assert job_copy.state == JOB_PENDING
        # Progress stored in Redis is expected to be accurate.
        assert job_copy.get_cached_progress_percentage() == 50
        assert job_copy.get_cached_state() == "test"

        progress.increment(50)

    job = data_fixture.create_fake_job()

    # Fake the run method of job
    fake_job_type = TmpCustomJobType()
    fake_job_type.run = Mock(side_effect=run)
    mock_get_by_model.return_value = fake_job_type

    with pytest.raises(Job.DoesNotExist):
        run_async_job(0)

    run_async_job(job.id)

    fake_job_type.run.assert_called_once()

    job = Job.objects.get(pk=job.id)
    assert job.progress_percentage == 100
    assert job.state == JOB_FINISHED

    # The cache entry will be removed when when job completes.
    assert cache.get(job_progress_key(job.id)) is None

    job_copy = Job.objects.using("default-copy").get(pk=job.id)
    assert job_copy.progress_percentage == 100
    assert job_copy.state == JOB_FINISHED
    assert job_copy.get_cached_progress_percentage() == 100
    assert job_copy.get_cached_state() == JOB_FINISHED


@pytest.mark.django_db(transaction=True)
@patch("baserow.core.jobs.registries.JobTypeRegistry.get_by_model")
def test_run_task_with_exception(mock_get_by_model, data_fixture):

    job_type = TmpCustomJobType()
    job_type.run = Mock(side_effect=Exception("test-1"))
    mock_get_by_model.return_value = job_type

    job = data_fixture.create_fake_job()

    with pytest.raises(Exception):
        run_async_job(job.id)

    job.refresh_from_db()
    assert job.state == JOB_FAILED
    assert job.error == "test-1"
    assert (
        job.human_readable_error
        == "Something went wrong during the custom_job_type job execution."
    )


@pytest.mark.django_db(transaction=True)
@patch("baserow.core.jobs.registries.JobTypeRegistry.get_by_model")
def test_run_task_failing_time_limit(mock_get_by_model, data_fixture):
    job_type = TmpCustomJobType()
    job_type.run = Mock(side_effect=SoftTimeLimitExceeded("test"))
    mock_get_by_model.return_value = job_type

    job = data_fixture.create_fake_job()

    with pytest.raises(SoftTimeLimitExceeded):
        run_async_job(job.id)

    job.refresh_from_db()
    assert job.state == JOB_FAILED
    assert job.error == "SoftTimeLimitExceeded('test',)"
    assert (
        job.human_readable_error
        == "The custom_job_type job took too long and was timed out."
    )


@pytest.mark.django_db(transaction=True)
@patch("baserow.core.jobs.registries.JobTypeRegistry.get_by_model")
def test_run_task_with_exception_mapping(mock_get_by_model, data_fixture):
    job_type = TmpCustomJobType()
    job_type.run = Mock(side_effect=ConnectionError("connection error"))
    mock_get_by_model.return_value = job_type

    job = data_fixture.create_fake_job()

    with pytest.raises(ConnectionError):
        run_async_job(job.id)

    job.refresh_from_db()
    assert job.state == JOB_FAILED
    assert job.error == "connection error"
    assert job.human_readable_error == "Error message"
