import pytest
from pyinstrument import Profiler

from baserow.contrib.database.rows.handler import RowHandler
from baserow.contrib.database.table.usage_types import TableGroupStorageUsageItemType


@pytest.mark.django_db
def test_table_group_storage_usage_item_type(data_fixture):
    user = data_fixture.create_user()
    group = data_fixture.create_group(user=user)
    database = data_fixture.create_database_application(group=group)
    table = data_fixture.create_database_table(user=user, database=database)
    file_field = data_fixture.create_file_field(table=table)

    usage = TableGroupStorageUsageItemType().calculate_storage_usage(group.id)

    assert usage == 0

    user_file_1 = data_fixture.create_user_file(
        original_name="test.png", is_image=True, size=500
    )

    RowHandler().create_row(user, table, {file_field.id: [{"name": user_file_1.name}]})

    usage = TableGroupStorageUsageItemType().calculate_storage_usage(group.id)

    assert usage == 500

    user_file_2 = data_fixture.create_user_file(
        original_name="another_file", is_image=True, size=200
    )

    RowHandler().create_row(user, table, {file_field.id: [{"name": user_file_2.name}]})

    usage = TableGroupStorageUsageItemType().calculate_storage_usage(group.id)

    assert usage == 700


@pytest.mark.django_db
@pytest.mark.disabled_in_ci
# You must add --run-disabled-in-ci -s to pytest to run this test, you can do this in
# intellij by editing the run config for this test and adding --run-disabled-in-ci -s
# to additional args.
def test_table_group_storage_usage_item_type_performance(data_fixture):
    files_amount = 1000
    file_size_each = 200

    user = data_fixture.create_user()
    group = data_fixture.create_group(user=user)
    database = data_fixture.create_database_application(group=group)
    table = data_fixture.create_database_table(user=user, database=database)
    file_field = data_fixture.create_file_field(table=table)

    user_files = [
        {
            f"field_{file_field.id}": [
                {
                    "name": data_fixture.create_user_file(
                        is_image=True, size=file_size_each
                    ).name
                }
            ]
        }
        for i in range(files_amount)
    ]

    RowHandler().create_rows(user, table, user_files)

    profiler = Profiler()
    profiler.start()
    usage = TableGroupStorageUsageItemType().calculate_storage_usage(group.id)
    profiler.stop()

    print(profiler.output_text(unicode=True, color=True))

    assert usage == files_amount * file_size_each
