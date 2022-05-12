from io import BytesIO

import pytest
from django.urls import reverse
from pytest_unordered import unordered
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT

from baserow.contrib.database.fields.dependencies.models import FieldDependency
from baserow.contrib.database.fields.handler import FieldHandler
from baserow.contrib.database.fields.models import FormulaField, LookupField
from baserow.contrib.database.fields.registries import field_type_registry
from baserow.contrib.database.formula import (
    BaserowFormulaInvalidType,
    BaserowFormulaNumberType,
    BaserowFormulaArrayType,
)
from baserow.contrib.database.rows.handler import RowHandler
from baserow.core.handler import CoreHandler


@pytest.mark.django_db
def test_can_update_lookup_field_value(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(lookupfield=f"2021-02-01", primaryfield="primary a")
    b = table2_model.objects.create(lookupfield=f"2022-02-03", primaryfield="primary b")

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table2.id, "row_id": a.id},
        ),
        {f"field_{looked_up_field.id}": "2000-02-01"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2000-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_can_batch_create_lookup_field_value(
    data_fixture, api_client, django_assert_num_queries
):
    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="tableprimary", table=table, primary=True
    )
    table2_primary_field = data_fixture.create_text_field(
        name="table2primary", table=table2, primary=True
    )
    link_row_field = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=link_row_field.id,
        target_field_id=table2_primary_field.id,
    )

    table2_model = table2.get_model(attribute_names=True)
    table2_row_1 = table2_model.objects.create(table2primary="row A")

    response = api_client.post(
        reverse(
            "api:database:rows:batch",
            kwargs={"table_id": table.id},
        ),
        {
            "items": [
                {
                    f"field_{table_primary_field.id}": "row 1",
                    f"field_{link_row_field.id}": [table2_row_1.id],
                }
            ]
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "items": [
            {
                "id": 1,
                "order": "1.00000000000000000000",
                f"field_{table_primary_field.id}": "row 1",
                f"field_{link_row_field.id}": [{"id": 1, "value": "row A"}],
                f"field_{lookup_field.id}": [{"id": 1, "value": "row A"}],
            }
        ]
    }


@pytest.mark.django_db
def test_can_batch_update_lookup_field_value(
    data_fixture, api_client, django_assert_num_queries
):
    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="tableprimary", table=table, primary=True
    )
    table2_primary_field = data_fixture.create_text_field(
        name="table2primary", table=table2, primary=True
    )
    link_row_field = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=link_row_field.id,
        target_field_id=table2_primary_field.id,
    )

    table1_model = table.get_model(attribute_names=True)
    table1_row_1 = table1_model.objects.create(tableprimary="row 1")

    table2_model = table2.get_model(attribute_names=True)
    table2_row_1 = table2_model.objects.create(table2primary="row A")

    response = api_client.patch(
        reverse(
            "api:database:rows:batch",
            kwargs={"table_id": table.id},
        ),
        {
            "items": [
                {"id": table1_row_1.id, f"field_{link_row_field.id}": [table2_row_1.id]}
            ]
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "items": [
            {
                "id": 1,
                "order": "1.00000000000000000000",
                f"field_{table_primary_field.id}": "row 1",
                f"field_{link_row_field.id}": [{"id": 1, "value": "row A"}],
                f"field_{lookup_field.id}": [{"id": 1, "value": "row A"}],
            }
        ]
    }


@pytest.mark.django_db
def test_can_set_sub_type_options_for_lookup_field(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_number_field(
        name="lookupfield",
        table=table2,
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(lookupfield=1, primaryfield="primary a")
    b = table2_model.objects.create(lookupfield=2, primaryfield="primary b")

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
        number_decimal_places=2,
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "1.00"},
                    {"id": b.id, "value": "2.00"},
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_can_lookup_single_select(data_fixture, api_client, django_assert_num_queries):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_single_select_field(
        table=table2, name="lookupfield"
    )
    option_a = data_fixture.create_select_option(
        field=looked_up_field, value="A", color="blue"
    )
    option_b = data_fixture.create_select_option(
        field=looked_up_field, value="B", color="red"
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(lookupfield=option_a, primaryfield="primary a")
    b = table2_model.objects.create(lookupfield=option_b, primaryfield="primary b")

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
        number_decimal_places=2,
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {
                        "id": a.id,
                        "value": {
                            "id": option_a.id,
                            "value": option_a.value,
                            "color": option_a.color,
                        },
                    },
                    {
                        "id": b.id,
                        "value": {
                            "id": option_b.id,
                            "value": option_b.value,
                            "color": option_b.color,
                        },
                    },
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_import_export_lookup_field_when_through_field_trashed(
    data_fixture, api_client
):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)
    id_mapping = {}

    target_field = data_fixture.create_text_field(name="target", table=table_b)
    table_a_model = table_a.get_model(attribute_names=True)
    table_b_model = table_b.get_model(attribute_names=True)
    row_1 = table_b_model.objects.create(primary="1", target="target 1")
    row_2 = table_b_model.objects.create(primary="2", target="target 2")

    row_a = table_a_model.objects.create(primary="a")
    row_a.link.add(row_1.id)
    row_a.link.add(row_2.id)
    row_a.save()

    lookup = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name="link",
        target_field_name="target",
    )

    FieldHandler().delete_field(user, link_field)

    lookup.refresh_from_db()
    lookup_field_type = field_type_registry.get_by_model(lookup)
    lookup_serialized = lookup_field_type.export_serialized(lookup)

    assert lookup_serialized["through_field_id"] is None
    assert lookup_serialized["through_field_name"] == link_field.name
    assert lookup_serialized["target_field_id"] is None
    assert lookup_serialized["target_field_name"] == target_field.name

    lookup.name = "rename to prevent import clash"
    lookup.save()

    lookup_field_imported = lookup_field_type.import_serialized(
        table_a,
        lookup_serialized,
        id_mapping,
    )
    assert lookup_field_imported.through_field is None
    assert lookup_field_imported.through_field_name == link_field.name
    assert lookup_field_imported.target_field is None
    assert lookup_field_imported.target_field_name == lookup.target_field_name
    assert lookup_field_imported.formula_type == BaserowFormulaInvalidType.type
    assert lookup_field_imported.error == "references the deleted or unknown field link"


@pytest.mark.django_db
def test_import_export_lookup_field_trashed_target_field(data_fixture, api_client):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)
    id_mapping = {}

    target_field = data_fixture.create_text_field(name="target", table=table_b)
    table_a_model = table_a.get_model(attribute_names=True)
    table_b_model = table_b.get_model(attribute_names=True)
    row_1 = table_b_model.objects.create(primary="1", target="target 1")
    row_2 = table_b_model.objects.create(primary="2", target="target 2")

    row_a = table_a_model.objects.create(primary="a")
    row_a.link.add(row_1.id)
    row_a.link.add(row_2.id)
    row_a.save()

    lookup = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name="link",
        target_field_name="target",
    )

    FieldHandler().delete_field(user, target_field)

    lookup.refresh_from_db()
    lookup_field_type = field_type_registry.get_by_model(lookup)
    lookup_serialized = lookup_field_type.export_serialized(lookup)

    assert lookup_serialized["through_field_id"] == link_field.id
    assert lookup_serialized["through_field_name"] == link_field.name
    assert lookup_serialized["target_field_id"] is None
    assert lookup_serialized["target_field_name"] == target_field.name

    lookup.name = "rename to prevent import clash"
    lookup.save()

    lookup_field_imported = lookup_field_type.import_serialized(
        table_a,
        lookup_serialized,
        id_mapping,
    )
    assert lookup_field_imported.through_field is None
    assert lookup_field_imported.through_field_name == link_field.name
    assert lookup_field_imported.target_field is None
    assert lookup_field_imported.target_field_name == lookup.target_field_name
    assert lookup_field_imported.formula_type == BaserowFormulaInvalidType.type
    assert (
        lookup_field_imported.error
        == "references the deleted or unknown field target in table table_b"
    )


@pytest.mark.django_db()
def test_import_export_tables_with_lookup_fields(
    data_fixture, django_assert_num_queries
):
    user = data_fixture.create_user()
    imported_group = data_fixture.create_group(user=user)
    database = data_fixture.create_database_application(user=user, name="Placeholder")
    table = data_fixture.create_database_table(name="Example", database=database)
    customers_table = data_fixture.create_database_table(
        name="Customers", database=database
    )
    customer_name = data_fixture.create_text_field(table=customers_table, primary=True)
    customer_age = data_fixture.create_number_field(table=customers_table)
    field_handler = FieldHandler()
    core_handler = CoreHandler()
    link_row_field = field_handler.create_field(
        user=user,
        table=table,
        name="Link Row",
        type_name="link_row",
        link_row_table=customers_table,
    )

    row_handler = RowHandler()
    c_row = row_handler.create_row(
        user=user,
        table=customers_table,
        values={
            f"field_{customer_name.id}": "mary",
            f"field_{customer_age.id}": 65,
        },
    )
    c_row_2 = row_handler.create_row(
        user=user,
        table=customers_table,
        values={
            f"field_{customer_name.id}": "bob",
            f"field_{customer_age.id}": 67,
        },
    )
    row = row_handler.create_row(
        user=user,
        table=table,
        values={f"field_{link_row_field.id}": [c_row.id, c_row_2.id]},
    )

    lookup_field = field_handler.create_field(
        user=user,
        table=table,
        name="lookup",
        type_name="lookup",
        through_field_id=link_row_field.id,
        target_field_id=customer_age.id,
    )

    exported_applications = core_handler.export_group_applications(
        database.group, BytesIO()
    )
    imported_applications, id_mapping = core_handler.import_applications_to_group(
        imported_group, exported_applications, BytesIO(), None
    )
    imported_database = imported_applications[0]
    imported_tables = imported_database.table_set.all()
    imported_table = imported_tables[0]

    imported_lookup_field = imported_table.field_set.get(
        name=lookup_field.name
    ).specific
    imported_through_field = imported_table.field_set.get(
        name=link_row_field.name
    ).specific
    imported_target_field = imported_through_field.link_row_table.field_set.get(
        name=customer_age.name
    ).specific
    assert imported_lookup_field.formula == lookup_field.formula
    assert imported_lookup_field.formula_type == BaserowFormulaArrayType.type
    assert imported_lookup_field.array_formula_type == BaserowFormulaNumberType.type
    assert imported_lookup_field.through_field.name == link_row_field.name
    assert imported_lookup_field.target_field.name == customer_age.name
    assert imported_lookup_field.through_field_name == link_row_field.name
    assert imported_lookup_field.target_field_name == customer_age.name
    assert imported_lookup_field.target_field_id == imported_target_field.id
    assert imported_lookup_field.through_field_id == imported_through_field.id

    imported_table_model = imported_table.get_model(attribute_names=True)
    imported_rows = imported_table_model.objects.all()
    assert imported_rows.count() == 1
    imported_row = imported_rows.first()
    assert imported_row.id == row.id
    assert len(imported_row.lookup) == 2
    assert {"id": c_row.id, "value": 65} in imported_row.lookup
    assert {"id": c_row_2.id, "value": 67} in imported_row.lookup


@pytest.mark.django_db
def test_can_create_new_row_with_immediate_link_row_values_and_lookup_will_match(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user)

    table_b_model = table_b.get_model(attribute_names=True)
    b_row_1 = table_b_model.objects.create(primary="1")
    b_row_2 = table_b_model.objects.create(primary="2")

    lookup_field = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup_field",
        through_field_id=link_field.id,
        target_field_name="primary",
    )
    assert lookup_field.error is None

    response = api_client.post(
        reverse("api:database:rows:list", kwargs={"table_id": table_a.id}),
        {f"field_{link_field.id}": [b_row_1.id, b_row_2.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    lookup_values = response.json()[f"field_{lookup_field.id}"]
    assert {"id": b_row_1.id, "value": "1"} in lookup_values
    assert {"id": b_row_2.id, "value": "2"} in lookup_values

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table_a.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    lookup_values = response.json()["results"][0][f"field_{lookup_field.id}"]
    assert {"id": b_row_1.id, "value": "1"} in lookup_values
    assert {"id": b_row_2.id, "value": "2"} in lookup_values


@pytest.mark.django_db
def test_moving_a_looked_up_row_updates_the_order(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:move",
            kwargs={"table_id": table2.id, "row_id": a.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": b.id, "value": "primary b"},
                    {"id": a.id, "value": "primary a"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": b.id, "value": "2022-02-03"},
                    {"id": a.id, "value": "2021-02-01"},
                ],
                f"field_{string_agg.id}": "02/03/2022, 02/01/2021",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_can_modify_row_containing_lookup(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    table_long_field = data_fixture.create_long_text_field(
        name="long",
        table=table,
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{table_long_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table.id, "row_id": table_row.id},
        ),
        {f"field_{table_primary_field.id}": "other"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table.id, "row_id": table_row.id},
        ),
        {f"field_{table_long_field.id}": "other"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": "other",
                f"field_{table_long_field.id}": "other",
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_deleting_restoring_lookup_target_works(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }

    response = api_client.delete(
        reverse(
            "api:database:fields:item",
            kwargs={"field_id": looked_up_field.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": None,
                f"field_{string_agg.id}": None,
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "invalid"
    assert (
        lookup_field.error
        == "references the deleted or unknown field lookupfield in table table 2"
    )
    assert lookup_field.target_field is None
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "invalid"
    assert (
        string_agg.error
        == "references the deleted or unknown field lookupfield in table table 2"
    )

    response = api_client.patch(
        reverse(
            "api:trash:restore",
        ),
        {
            "trash_item_type": "field",
            "trash_item_id": looked_up_field.id,
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "array"
    assert lookup_field.array_formula_type == "date"
    assert lookup_field.error is None
    assert lookup_field.target_field.id == looked_up_field.id
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "text"
    assert string_agg.error is None


@pytest.mark.django_db
def test_deleting_related_link_row_field_dep_breaks_deps(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    depends_on_related_field = FieldHandler().create_field(
        user,
        table2,
        "formula",
        name="depends on related",
        formula=f"field('{linkrowfield.link_row_related_field.name}')",
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )

    response = api_client.delete(
        reverse(
            "api:database:fields:item",
            kwargs={"field_id": linkrowfield.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK

    new_row = RowHandler().create_row(
        user,
        table,
        values={f"field_{table_primary_field.id}": "bbb"},
    )
    RowHandler().create_row(user, table2, values={})

    depends_on_related_field.refresh_from_db()
    assert depends_on_related_field.formula_type == "invalid"
    assert "references the deleted or unknown field" in depends_on_related_field.error

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{lookup_field.id}": None,
                f"field_{string_agg.id}": None,
                "id": table_row.id,
                "order": "1.00000000000000000000",
            },
            {
                f"field_{table_primary_field.id}": "bbb",
                f"field_{lookup_field.id}": None,
                f"field_{string_agg.id}": None,
                "id": new_row.id,
                "order": "2.00000000000000000000",
            },
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "invalid"
    assert lookup_field.error == "references the deleted or unknown field linkrowfield"
    assert lookup_field.target_field is None
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field is None
    assert lookup_field.through_field_name == linkrowfield.name

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "invalid"
    assert string_agg.error == "references the deleted or unknown field linkrowfield"

    response = api_client.patch(
        reverse(
            "api:trash:restore",
        ),
        {
            "trash_item_type": "field",
            "trash_item_id": linkrowfield.id,
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            },
            {
                f"field_{table_primary_field.id}": "bbb",
                f"field_{linkrowfield.id}": [],
                f"field_{lookup_field.id}": [],
                f"field_{string_agg.id}": None,
                "id": new_row.id,
                "order": "2.00000000000000000000",
            },
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "array"
    assert lookup_field.array_formula_type == "date"
    assert lookup_field.error is None
    assert lookup_field.target_field.id == looked_up_field.id
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "text"
    assert string_agg.error is None


@pytest.mark.django_db
def test_deleting_table_with_dependants_works(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user, name="table 1")
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    depends_on_related_field = FieldHandler().create_field(
        user,
        table2,
        "formula",
        name="depends on related",
        formula=f"field('{linkrowfield.link_row_related_field.name}')",
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )

    response = api_client.delete(
        reverse(
            "api:database:tables:item",
            kwargs={"table_id": table2.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    new_row = RowHandler().create_row(
        user,
        table,
        values={f"field_{table_primary_field.id}": "bbb"},
    )

    assert not depends_on_related_field.dependencies.exists()
    assert not depends_on_related_field.dependants.exists()
    assert [str(o) for o in FieldDependency.objects.all()] == unordered(
        [
            str(FieldDependency(dependant=string_agg, dependency=lookup_field)),
            str(
                FieldDependency(
                    dependant=lookup_field,
                    broken_reference_field_name=linkrowfield.name,
                )
            ),
        ]
    )

    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "invalid"
    assert "references the deleted or unknown" in lookup_field.error
    assert lookup_field.target_field is None
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field is None
    assert lookup_field.through_field_name == linkrowfield.name

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "invalid"
    assert "references the deleted or unknown" in string_agg.error

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{lookup_field.id}": None,
                f"field_{string_agg.id}": None,
                "id": table_row.id,
                "order": "1.00000000000000000000",
            },
            {
                f"field_{table_primary_field.id}": "bbb",
                f"field_{lookup_field.id}": None,
                f"field_{string_agg.id}": None,
                "id": new_row.id,
                "order": "2.00000000000000000000",
            },
        ],
    }

    response = api_client.patch(
        reverse(
            "api:trash:restore",
        ),
        {
            "trash_item_type": "table",
            "trash_item_id": table2.id,
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    assert depends_on_related_field.dependencies.exists()

    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "array"
    assert lookup_field.target_field.id == looked_up_field.id
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id
    assert lookup_field.through_field_name == linkrowfield.name

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "text"

    assert [str(o) for o in lookup_field.dependencies.all()] == unordered(
        [
            str(
                FieldDependency(
                    dependant=lookup_field, dependency=looked_up_field, via=linkrowfield
                )
            ),
        ]
    )

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            },
            {
                f"field_{table_primary_field.id}": "bbb",
                f"field_{linkrowfield.id}": [],
                f"field_{lookup_field.id}": [],
                f"field_{string_agg.id}": None,
                "id": new_row.id,
                "order": "2.00000000000000000000",
            },
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "array"
    assert lookup_field.array_formula_type == "date"
    assert lookup_field.error is None
    assert lookup_field.target_field.id == looked_up_field.id
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "text"
    assert string_agg.error is None


@pytest.mark.django_db
def test_deleting_related_link_row_field_still_lets_you_create_edit_rows(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    FieldHandler().create_field(
        user,
        table2,
        "formula",
        name="depends on related",
        formula=f"field('{linkrowfield.link_row_related_field.name}')",
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )

    response = api_client.delete(
        reverse(
            "api:database:fields:item",
            kwargs={"field_id": linkrowfield.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK

    RowHandler().create_row(
        user,
        table,
        values={f"field_{table_primary_field.id}": "bbb"},
    )
    RowHandler().create_row(user, table2, values={})
    RowHandler().update_row_by_id(user, table, row_id=table_row.id, values={})


@pytest.mark.django_db
def test_deleting_related_table_still_lets_you_create_edit_rows(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    FieldHandler().create_field(
        user,
        table2,
        "formula",
        name="depends on related",
        formula=f"field('{linkrowfield.link_row_related_field.name}')",
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )

    response = api_client.delete(
        reverse(
            "api:database:tables:item",
            kwargs={"table_id": table2.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    RowHandler().create_row(
        user,
        table,
        values={f"field_{table_primary_field.id}": "bbb"},
    )
    RowHandler().update_row_by_id(user, table, row_id=table_row.id, values={})


@pytest.mark.django_db
def test_converting_away_from_lookup_field_deletes_parent_formula_field(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    data_fixture.create_text_field(name="p", table=table, primary=True)
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )
    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )

    assert FormulaField.objects.count() == 1
    assert LookupField.objects.count() == 1

    response = api_client.patch(
        reverse(
            "api:database:fields:item",
            kwargs={"field_id": lookup_field.id},
        ),
        {"type": "boolean"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK

    assert LookupField.objects.count() == 0
    assert FormulaField.objects.count() == 0


@pytest.mark.django_db
def test_updating_other_side_of_link_row_field_updates_lookups(
    data_fixture, api_client
):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)

    target_field = data_fixture.create_text_field(name="target", table=table_b)
    table_a_model = table_a.get_model(attribute_names=True)
    table_b_model = table_b.get_model(attribute_names=True)
    row_1 = table_b_model.objects.create(primary="1", target="target 1")
    row_2 = table_b_model.objects.create(primary="2", target="target 2")

    row_a = table_a_model.objects.create(primary="a")
    row_a.save()

    lookup = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name="link",
        target_field_name="target",
    )

    RowHandler().update_row_by_id(
        user,
        table_b,
        row_1.id,
        {f"{link_field.link_row_related_field.db_column}": [row_a.id]},
    )

    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=row_a.id).lookup == [
        {"id": row_1.id, "value": "target 1"}
    ]


@pytest.mark.django_db
def test_can_modify_row_containing_lookup_diamond_dep(
    data_fixture, api_client, django_assert_num_queries
):
    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table3 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="primaryfield", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table3, primary=True)
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)

    FieldHandler().create_field(
        user,
        table2,
        "link_row",
        name="linkrowfield",
        link_row_table=table,
    )
    FieldHandler().create_field(
        user,
        table3,
        "link_row",
        name="a",
        link_row_table=table2,
    )
    FieldHandler().create_field(
        user,
        table3,
        "link_row",
        name="b",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    table2_row1 = table2_model.objects.create(primaryfield="table2_row1", order=0)
    table2_row2 = table2_model.objects.create(primaryfield="table2_row2", order=1)

    table_model = table.get_model(attribute_names=True)

    starting_row = table_model.objects.create(primaryfield="table1_primary_row_1")
    table2_row1.linkrowfield.add(starting_row.id)
    table2_row1.save()
    table2_row2.linkrowfield.add(starting_row.id)
    table2_row2.save()

    table3_model = table3.get_model(attribute_names=True)
    table3_row_1 = table3_model.objects.create(primaryfield="table3_row_1")
    table3_row_2 = table3_model.objects.create(primaryfield="table3_row_2")

    table3_row_1.a.add(table2_row1.id)
    table3_row_1.save()

    table3_row_2.b.add(table2_row2.id)
    table3_row_2.save()

    FieldHandler().create_field(
        user,
        table2,
        "formula",
        name="middle_lookup",
        formula="""join(lookup('linkrowfield', 'primaryfield'), " ")""",
    )
    FieldHandler().create_field(
        user,
        table3,
        "formula",
        name="final_lookup",
        formula="""join(lookup('a', 'middle_lookup'), " ")+join(lookup('b',
        'middle_lookup'), " ")""",
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table2.id})
        + f"?include=middle_lookup&user_field_names=true",
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": table2_row1.id,
                "linkrowfield": [
                    {"id": starting_row.id, "value": "table1_primary_row_1"}
                ],
                "middle_lookup": "table1_primary_row_1",
                "order": "0.00000000000000000000",
            },
            {
                "id": table2_row2.id,
                "linkrowfield": [
                    {"id": starting_row.id, "value": "table1_primary_row_1"}
                ],
                "middle_lookup": "table1_primary_row_1",
                "order": "1.00000000000000000000",
            },
        ],
    }
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table3.id})
        + f"?include=final_lookup&user_field_names=true",
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                "a": [{"id": 1, "value": "table2_row1"}],
                "b": [],
                "final_lookup": "table1_primary_row_1",
                "id": 1,
                "order": "1.00000000000000000000",
            },
            {
                "a": [],
                "b": [{"id": 2, "value": "table2_row2"}],
                "final_lookup": "table1_primary_row_1",
                "id": 2,
                "order": "1.00000000000000000000",
            },
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table.id, "row_id": starting_row.id},
        ),
        {
            f"field_{table_primary_field.id}": "changed",
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table3.id})
        + f"?include=final_lookup&user_field_names=true",
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                "a": [{"id": table2_row1.id, "value": "table2_row1"}],
                "b": [],
                "final_lookup": "changed",
                "id": table3_row_1.id,
                "order": "1.00000000000000000000",
            },
            {
                "a": [],
                "b": [{"id": table2_row2.id, "value": "table2_row2"}],
                "final_lookup": "changed",
                "id": table3_row_2.id,
                "order": "1.00000000000000000000",
            },
        ],
    }


@pytest.mark.django_db
def test_deleting_link_in_other_side_of_link_row_field_updates_lookups(
    data_fixture, api_client, django_assert_num_queries
):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)

    target_field = data_fixture.create_text_field(name="target", table=table_b)

    # Make some rows in table b which we will lookup from table a
    table_b_model = table_b.get_model(attribute_names=True)
    table_b_row_1 = table_b_model.objects.create(primary="1", target="target 1")
    table_b_row_2 = table_b_model.objects.create(primary="2", target="target 2")

    # Make a row in table a
    table_a_model = table_a.get_model(attribute_names=True)
    table_a_row_1 = table_a_model.objects.create(primary="a")
    table_a_row_1.save()

    # Create a lookup from table a to table b's target column
    FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name=link_field.name,
        target_field_name=target_field.name,
    )

    # Create a connection between table b and table a
    RowHandler().update_row_by_id(
        user,
        table_b,
        table_b_row_1.id,
        {f"{link_field.link_row_related_field.db_column}": [table_a_row_1.id]},
    )

    # Assert that the lookup was updated in table a
    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=table_a_row_1.id).lookup == [
        {"id": table_b_row_1.id, "value": "target 1"}
    ]

    # Delete the connection in table b
    RowHandler().update_row_by_id(
        user,
        table_b,
        table_b_row_1.id,
        {f"{link_field.link_row_related_field.db_column}": []},
    )

    # Assert that the lookup was updated in table a
    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=table_a_row_1.id).lookup == []


@pytest.mark.django_db
def test_batch_deleting_all_links_in_other_side_of_link_row_field_updates_lookups(
    data_fixture, api_client, django_assert_num_queries
):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)

    target_field = data_fixture.create_text_field(name="target", table=table_b)

    # Make some rows in table b which we will lookup from table a
    table_b_model = table_b.get_model(attribute_names=True)
    table_b_row_1 = table_b_model.objects.create(primary="1", target="target 1")
    table_b_row_2 = table_b_model.objects.create(primary="2", target="target 2")

    # Make rows in table a
    table_a_model = table_a.get_model(attribute_names=True)
    table_a_row_1 = table_a_model.objects.create(primary="a")
    table_a_row_2 = table_a_model.objects.create(primary="b")

    # Create a lookup from table a to table b's target column
    FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name=link_field.name,
        target_field_name=target_field.name,
    )

    # Create a connection between table b and table a
    RowHandler().update_rows(
        user,
        table_b,
        [
            {
                "id": table_b_row_1.id,
                f"{link_field.link_row_related_field.db_column}": [table_a_row_1.id],
            },
            {
                "id": table_b_row_2.id,
                f"{link_field.link_row_related_field.db_column}": [table_a_row_2.id],
            },
        ],
    )

    # Assert that the lookup was updated in table a
    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=table_a_row_1.id).lookup == [
        {"id": table_b_row_1.id, "value": "target 1"},
    ]
    assert table_a_model.objects.get(id=table_a_row_2.id).lookup == [
        {"id": table_b_row_2.id, "value": "target 2"},
    ]

    # Delete the connections in table b
    RowHandler().update_rows(
        user,
        table_b,
        [
            {
                "id": table_b_row_1.id,
                f"{link_field.link_row_related_field.db_column}": [],
            },
            {
                "id": table_b_row_2.id,
                f"{link_field.link_row_related_field.db_column}": [],
            },
        ],
    )

    # Assert that the lookup was updated in table a
    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=table_a_row_1.id).lookup == []
    assert table_a_model.objects.get(id=table_a_row_2.id).lookup == []


@pytest.mark.django_db
def test_batch_deleting_some_links_in_other_side_of_link_row_field_updates_lookups(
    data_fixture, api_client, django_assert_num_queries
):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)

    target_field = data_fixture.create_text_field(name="target", table=table_b)

    # Make some rows in table b which we will lookup from table a
    table_b_model = table_b.get_model(attribute_names=True)
    table_b_row_1 = table_b_model.objects.create(primary="1", target="target 1")
    table_b_row_2 = table_b_model.objects.create(primary="2", target="target 2")

    # Make rows in table a
    table_a_model = table_a.get_model(attribute_names=True)
    table_a_row_1 = table_a_model.objects.create(primary="a")
    table_a_row_2 = table_a_model.objects.create(primary="b")

    # Create a lookup from table a to table b's target column
    FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name=link_field.name,
        target_field_name=target_field.name,
    )

    # Create a connection between table b and table a
    RowHandler().update_rows(
        user,
        table_b,
        [
            {
                "id": table_b_row_1.id,
                f"{link_field.link_row_related_field.db_column}": [
                    table_a_row_1.id,
                    table_a_row_2.id,
                ],
            },
            {
                "id": table_b_row_2.id,
                f"{link_field.link_row_related_field.db_column}": [table_a_row_2.id],
            },
        ],
    )

    # Assert that the lookup was updated in table a
    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=table_a_row_1.id).lookup == [
        {"id": table_b_row_1.id, "value": "target 1"},
    ]
    assert table_a_model.objects.get(id=table_a_row_2.id).lookup == [
        {"id": table_b_row_1.id, "value": "target 1"},
        {"id": table_b_row_2.id, "value": "target 2"},
    ]

    # Delete the connections in table b
    RowHandler().update_rows(
        user,
        table_b,
        [
            {
                "id": table_b_row_1.id,
                f"{link_field.link_row_related_field.db_column}": [table_a_row_1.id],
            },
            {
                "id": table_b_row_2.id,
                f"{link_field.link_row_related_field.db_column}": [],
            },
        ],
    )

    # Assert that the lookup was updated in table a
    table_a_model = table_a.get_model(attribute_names=True)
    assert table_a_model.objects.get(id=table_a_row_1.id).lookup == [
        {"id": table_b_row_1.id, "value": "target 1"},
    ]
    assert table_a_model.objects.get(id=table_a_row_2.id).lookup == []
