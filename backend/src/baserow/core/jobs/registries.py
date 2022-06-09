from typing import Any, Dict

from django.contrib.auth.models import AbstractBaseUser

from baserow.core.utils import Progress
from baserow.core.registry import (
    ModelInstanceMixin,
    Registry,
    Instance,
    CustomFieldsInstanceMixin,
    MapAPIExceptionsInstanceMixin,
    ModelRegistryMixin,
    CustomFieldsRegistryMixin,
)

from .types import AnyJob
from .models import Job
from .exceptions import JobTypeDoesNotExist, JobTypeAlreadyRegistered


class JobType(
    CustomFieldsInstanceMixin,
    ModelInstanceMixin,
    MapAPIExceptionsInstanceMixin,
    Instance,
):
    """
    This abstract class represents a custom job type that can be added to the
    job type registry. It must be extended so customisation can be done. Each job
    type will have its own `run` method that will be run asynchronously.
    """

    job_exceptions_map = {}
    """
    A map of exception that can be used to map exceptions to certain task error
    messages.
    """

    def prepare_values(
        self, values: Dict[str, Any], user: AbstractBaseUser
    ) -> Dict[str, Any]:
        """
        The prepare_values hook gives the possibility to change the provided values
        that just before they are going to be used to create or update the instance. For
        example if an ID is provided, it can be converted to a model instance. Or to
        convert a certain date string to a date object. It's also an opportunity to add
        specific validations.

        :param values: The provided values.
        :param user: The user on whose behalf the change is made.
        :return: The updated values.
        """

        return values

    def after_job_creation(self, job: AnyJob, values: Dict[str, Any]):
        """
        This method gives the possibility to change the job just after the
        instance creation. For example, files can be saved, or relationship can be
        added.

        :param Job: The created job.
        :param values: The provided values.
        """

    def run(self, job: AnyJob, progress: Progress) -> Any:
        """
        This method is the task of this job type that will be executed asynchronously.

        :param job: the related job instance
        :param progress: A progress object that can be used to track the progress of
          the task.
        """

        raise NotImplementedError("The run method must be implemented.")

    def clean_up_jobs(self):
        """
        This method is periodically executed and should cleanup jobs that need to be.
        This can be clean generated files or remove expired jobs. Do nothing by default,
        if a job type need to clean jobs, can be done here.
        """


class JobTypeRegistry(
    CustomFieldsRegistryMixin,
    ModelRegistryMixin[Job, JobType],
    Registry[JobType],
):
    """
    The registry that holds all the available job types.
    """

    name = "job_type"

    does_not_exist_exception_class = JobTypeDoesNotExist
    already_registered_exception_class = JobTypeAlreadyRegistered


job_type_registry: JobTypeRegistry = JobTypeRegistry()
