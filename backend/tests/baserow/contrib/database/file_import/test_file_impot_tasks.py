import pytest
from pyinstrument import Profiler
from freezegun import freeze_time

from django.utils import timezone
from django.conf import settings

from baserow.contrib.database.fields.models import SelectOption
from baserow.contrib.database.fields.field_cache import FieldCache
from baserow.contrib.database.fields.dependencies.handler import FieldDependencyHandler
from baserow.core.jobs.tasks import run_async_job, clean_up_jobs
from baserow.core.jobs.constants import (
    JOB_FAILED,
    JOB_FINISHED,
    JOB_PENDING,
)
from baserow.contrib.database.file_import.exceptions import (
    FileImportMaxErrorCountExceeded,
)


@pytest.mark.django_db(transaction=True)
def test_run_file_import_task(data_fixture):

    job = data_fixture.create_file_import_job()
    table = job.table

    run_async_job(job.id)

    job.refresh_from_db()
    assert job.state == JOB_FINISHED
    assert job.progress_percentage == 100

    model = table.get_model()
    rows = model.objects.all()

    assert len(rows) == 5

    # A table with non string field
    user = data_fixture.create_user()
    table, _, _ = data_fixture.build_table(
        columns=[
            (f"col1", "text"),
            (f"col2", "number"),
            (f"col3", "url"),
        ],
        rows=[],
        user=user,
    )

    data = [["foo", 1, "http://test.en"], ["bar", 2, "http://example.com"]]

    job = data_fixture.create_file_import_job(user=user, table=table, data=data)
    run_async_job(job.id)

    model = table.get_model()
    field1, field2, field3 = table.field_set.all()
    rows = model.objects.all()

    assert len(rows) == 2

    job.refresh_from_db()
    with pytest.raises(ValueError):
        # Check that the data file has been removed
        job.data_file.path

    # Import data to an existing table
    data = [["baz", 3, "http://example.com"], ["bob", 4, "http://example.com"]]
    job = data_fixture.create_file_import_job(user=user, table=table, data=data)
    run_async_job(job.id)

    rows = model.objects.all()
    assert len(rows) == 4

    # Import data with error
    data = [
        ["good", 2.3, "Not an URL"],
        [None, None, None],
        ["good", "ugly", "http://example.com"],
        ["good", 2.3, "http://example.com"],
    ]
    job = data_fixture.create_file_import_job(user=user, table=table, data=data)
    run_async_job(job.id)

    rows = model.objects.all()
    assert len(rows) == 5

    job.refresh_from_db()

    assert sorted(job.report["failing_rows"].keys()) == ["0", "2", "3"]

    assert job.report["failing_rows"]["0"] == {
        f"field_{field2.id}": [
            {
                "code": "max_decimal_places",
                "error": "Ensure that there are no more than 0 decimal places.",
            }
        ],
        f"field_{field3.id}": [{"code": "invalid", "error": "Enter a valid value."}],
    }

    assert job.report["failing_rows"]["2"] == {
        f"field_{field2.id}": [
            {"code": "invalid", "error": "A valid number is required."}
        ]
    }

    assert job.report["failing_rows"]["3"] == {
        f"field_{field2.id}": [
            {
                "code": "max_decimal_places",
                "error": "Ensure that there are no more than 0 decimal places.",
            }
        ]
    }

    # Change user language to test message i18n
    user.profile.language = "fr"
    user.profile.save()

    # Translate messages
    data = [["good", "ugly"]]
    job = data_fixture.create_file_import_job(user=user, table=table, data=data)
    run_async_job(job.id)

    job.refresh_from_db()

    assert job.report["failing_rows"]["0"][f"field_{field2.id}"] == [
        {
            "code": "invalid",
            "error": "Un nombre valide est requis.",
        }
    ]


@pytest.mark.django_db(transaction=True)
def test_run_file_import_task_for_special_fields(data_fixture):

    user = data_fixture.create_user()
    table, table_b, link_field = data_fixture.create_two_linked_tables(user=user)

    # number field updating another table through link & formula
    number_field = data_fixture.create_number_field(
        table=table_b, order=1, name="Number"
    )
    formula_field = data_fixture.create_formula_field(
        table=table,
        order=2,
        name="Number times two",
        formula=f"lookup('{link_field.name}', '{number_field.name}')*2",
        formula_type="number",
    )
    FieldDependencyHandler.rebuild_dependencies(formula_field, FieldCache())

    # single and multiple select fields
    multiple_select_field = data_fixture.create_multiple_select_field(
        table=table_b, order=3
    )
    multi_select_option_1 = SelectOption.objects.create(
        field=multiple_select_field,
        order=1,
        value="Option 1",
        color="blue",
    )
    multi_select_option_2 = SelectOption.objects.create(
        field=multiple_select_field,
        order=2,
        value="Option 2",
        color="blue",
    )
    multiple_select_field.select_options.set(
        [multi_select_option_1, multi_select_option_2]
    )
    single_select_field = data_fixture.create_single_select_field(
        table=table_b, order=4
    )
    single_select_option_1 = SelectOption.objects.create(
        field=single_select_field,
        order=1,
        value="Option 1",
        color="blue",
    )
    single_select_option_2 = SelectOption.objects.create(
        field=single_select_field,
        order=2,
        value="Option 2",
        color="blue",
    )
    single_select_field.select_options.set(
        [single_select_option_1, single_select_option_2]
    )

    # file field
    file_field = data_fixture.create_file_field(table=table_b, order=5)
    file1 = data_fixture.create_user_file(
        original_name="test.txt",
        is_image=True,
    )
    file2 = data_fixture.create_user_file(
        original_name="test2.txt",
        is_image=True,
    )

    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()

    data = [
        [
            "one",
            10,
            [row_1.id],
            [multi_select_option_1.id],
            single_select_option_1.id,
            [{"name": file1.name, "visible_name": "new name"}],
        ],
        [
            "two",
            20,
            [row_2.id, row_1.id],
            [multi_select_option_1.id, multi_select_option_2.id],
            single_select_option_2.id,
            [{"name": file2.name, "visible_name": "another name"}],
        ],
        [
            "three",
            0,
            [],
            [],
            None,
            [],
        ],
    ]

    job = data_fixture.create_file_import_job(user=user, table=table_b, data=data)
    run_async_job(job.id)
    job.refresh_from_db()

    model = table_b.get_model()

    rows = model.objects.all()
    assert len(rows) == 3

    data = [
        [
            "four",
            10,
            [0],
            [0],
            0,
            [{"name": "missing_file.txt", "visible_name": "new name"}],
        ],
        [
            "five",
            -1,
            [row_2.id, 0],
            [multi_select_option_1.id, 0],
            9999,
            [
                {},
                {"name": file2.name, "visible_name": "another name"},
                {"name": "missing_file.txt", "visible_name": "new name"},
            ],
        ],
        [
            "seven",
            10,
            [row_2.id],
            [multi_select_option_2.id],
            single_select_option_2.id,
            [
                {"name": file2.name, "visible_name": "another name"},
            ],
        ],
        [
            "six",
            1.2,
            ["invalid_value", row_2.id],
            ["invalid_value", multi_select_option_2.id],
            "invalid_value",
            [
                {},
                {"name": file2.name, "visible_name": "another name"},
                {"name": "invalidValue", "visible_name": "new name"},
            ],
        ],
        [
            "seven",
            1,
            "bug",
            "bug",
            1.4,
            "bug",
        ],
    ]

    job = data_fixture.create_file_import_job(user=user, table=table_b, data=data)
    run_async_job(job.id)
    job.refresh_from_db()

    rows = model.objects.all()
    assert len(rows) == 4

    assert sorted(job.report["failing_rows"].keys()) == ["0", "1", "3", "4"]

    assert sorted(job.report["failing_rows"]["0"].keys()) == sorted(
        [
            f"field_{multiple_select_field.id}",
            f"field_{single_select_field.id}",
            f"field_{file_field.id}",
        ]
    )

    assert sorted(job.report["failing_rows"]["1"].keys()) == sorted(
        [
            f"field_{number_field.id}",
            f"field_{file_field.id}",
        ]
    )

    assert sorted(job.report["failing_rows"]["3"].keys()) == sorted(
        [
            f"field_{number_field.id}",
            f"field_{link_field.id + 1}",
            f"field_{multiple_select_field.id}",
            f"field_{single_select_field.id}",
            f"field_{file_field.id}",
        ]
    )

    assert sorted(job.report["failing_rows"]["4"].keys()) == sorted(
        [
            f"field_{link_field.id + 1}",
            f"field_{multiple_select_field.id}",
            f"field_{single_select_field.id}",
            f"field_{file_field.id}",
        ]
    )


@pytest.mark.django_db(transaction=True)
def test_run_file_import_test_chunk(data_fixture):

    row_count = 1024 + 5

    user = data_fixture.create_user()

    table, _, _ = data_fixture.build_table(
        columns=[
            (f"col1", "text"),
            (f"col2", "number"),
        ],
        rows=[],
        user=user,
    )

    single_select_field = data_fixture.create_single_select_field(table=table, order=4)
    single_select_option_1 = SelectOption.objects.create(
        field=single_select_field,
        order=1,
        value="Option 1",
        color="blue",
    )
    single_select_option_2 = SelectOption.objects.create(
        field=single_select_field,
        order=2,
        value="Option 2",
        color="blue",
    )

    data = [["test", 1, single_select_option_1.id]] * row_count
    # 5 erroneous values
    data[5] = ["test", "bad", single_select_option_2.id]
    data[50] = ["test", "bad", 0]
    data[100] = ["test", "bad", ""]
    data[1024] = ["test", 2, 99999]
    data[1027] = ["test", "bad", single_select_option_2.id]

    job = data_fixture.create_file_import_job(table=table, data=data, user=user)

    run_async_job(job.id)

    job.refresh_from_db()

    model = job.table.get_model()
    assert model.objects.count() == row_count - 5

    assert sorted(job.report["failing_rows"].keys()) == sorted(
        ["5", "50", "100", "1024", "1027"]
    )

    assert job.state == JOB_FINISHED
    assert job.progress_percentage == 100


@pytest.mark.django_db(transaction=True)
def test_run_file_import_limit(data_fixture):

    row_count = 2000
    max_error = settings.BASEROW_MAX_FILE_IMPORT_ERROR_COUNT

    user = data_fixture.create_user()

    table, _, _ = data_fixture.build_table(
        columns=[
            (f"col1", "text"),
            (f"col2", "number"),
        ],
        rows=[],
        user=user,
    )

    single_select_field = data_fixture.create_single_select_field(table=table, order=4)
    single_select_option_1 = SelectOption.objects.create(
        field=single_select_field,
        order=1,
        value="Option 1",
        color="blue",
    )

    # Validation errors
    data = [["test", 1, single_select_option_1.id]] * row_count
    data += [["test", "bad", single_select_option_1.id]] * (max_error + 5)

    job = data_fixture.create_file_import_job(table=table, data=data, user=user)

    with pytest.raises(FileImportMaxErrorCountExceeded):
        run_async_job(job.id)

    job.refresh_from_db()

    model = job.table.get_model()
    assert model.objects.count() == 0

    assert job.state == JOB_FAILED
    assert job.error == "Too many errors"
    assert job.human_readable_error == "This file import has raised too many errors."

    assert len(job.report["failing_rows"]) == max_error

    # Row creation errors
    data = [["test", 1, single_select_option_1.id]] * row_count
    data += [["test", 1, 0]] * (max_error + 5)

    job = data_fixture.create_file_import_job(table=table, data=data, user=user)

    with pytest.raises(FileImportMaxErrorCountExceeded):
        run_async_job(job.id)

    job.refresh_from_db()

    assert model.objects.count() == 0

    assert job.state == JOB_FAILED
    assert job.error == "Too many errors"
    assert job.human_readable_error == "This file import has raised too many errors."

    assert (
        len(job.report["failing_rows"]) == settings.BASEROW_MAX_FILE_IMPORT_ERROR_COUNT
    )

    assert len(job.report["failing_rows"]) == max_error


@pytest.mark.django_db(transaction=True)
@pytest.mark.disabled_in_ci
# You must add --run-disabled-in-ci -s to pytest to run this test, you can do this in
# intellij by editing the run config for this test and adding --run-disabled-in-ci -s
# to additional args.
# ~5 min on a 6 x i5-8400 CPU @ 2.80GHz (5599 bogomips)
def test_run_file_import_task_big_data(data_fixture):

    row_count = 100_000

    job = data_fixture.create_file_import_job(column_count=100, row_count=row_count)

    profiler = Profiler()
    profiler.start()
    run_async_job(job.id)
    profiler.stop()

    job.refresh_from_db()

    model = job.table.get_model()
    assert model.objects.count() == row_count

    assert job.state == JOB_FINISHED
    assert job.progress_percentage == 100

    print(profiler.output_text(unicode=True, color=True, show_all=True))


@pytest.mark.django_db
def test_cleanup_file_import_job(data_fixture, settings):
    now = timezone.now()
    time_before_soft_limit = now - timezone.timedelta(
        minutes=settings.BASEROW_JOB_SOFT_TIME_LIMIT + 1
    )
    # create recent job
    with freeze_time(now):
        job1 = data_fixture.create_file_import_job()

    # Create old jobs
    with freeze_time(time_before_soft_limit):
        job2 = data_fixture.create_file_import_job()
        job3 = data_fixture.create_file_import_job(state=JOB_FINISHED)

    with freeze_time(now):
        clean_up_jobs()

    job1.refresh_from_db()
    assert job1.state == JOB_PENDING

    job2.refresh_from_db()
    assert job2.state == JOB_FAILED
    assert job2.updated_on == now

    with pytest.raises(ValueError):
        job2.data_file.path

    job3.refresh_from_db()
    assert job3.state == JOB_FINISHED
    assert job3.updated_on == time_before_soft_limit
