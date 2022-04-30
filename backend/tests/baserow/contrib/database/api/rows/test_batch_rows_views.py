from decimal import Decimal
import pytest
from django.shortcuts import reverse
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
)

from baserow.contrib.database.fields.dependencies.handler import FieldDependencyHandler
from baserow.contrib.database.fields.field_cache import FieldCache
from baserow.contrib.database.fields.handler import FieldHandler
from baserow.contrib.database.tokens.handler import TokenHandler
from baserow.test_utils.helpers import is_dict_subset
from django.conf import settings


# Create


@pytest.mark.django_db
@pytest.mark.api_rows
@pytest.mark.parametrize("token_header", ["JWT invalid", "Token invalid"])
def test_batch_create_rows_invalid_token(api_client, data_fixture, token_header):
    table = data_fixture.create_database_table()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})

    response = api_client.post(
        url,
        {},
        format="json",
        HTTP_AUTHORIZATION=token_header,
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_token_no_create_permission(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    no_create_perm_token = TokenHandler().create_token(
        user, table.database.group, "no permissions"
    )
    TokenHandler().update_token_permissions(
        user, no_create_perm_token, False, True, True, True
    )
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})

    response = api_client.post(
        url,
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Token {no_create_perm_token.key}",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_NO_PERMISSION_TO_TABLE"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_user_not_in_group(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table()
    request_body = {
        "items": [
            {
                f"field_11": "green",
            },
        ]
    }
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_invalid_table_id(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    url = reverse("api:database:rows:batch", kwargs={"table_id": 14343})

    response = api_client.post(
        url,
        {},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_TABLE_DOES_NOT_EXIST"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_no_rows_provided(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {"items": []}
    expected_error_detail = {
        "items": [
            {
                "code": "min_length",
                "error": "Ensure this field has at least 1 elements.",
            },
        ],
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    print(response.json())
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert response.json()["detail"] == expected_error_detail


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_batch_size_limit(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    num_rows = settings.BATCH_ROWS_SIZE_LIMIT + 1
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {"items": [{f"field_{number_field.id}": i} for i in range(num_rows)]}
    expected_error_detail = {
        "items": [
            {
                "code": "max_length",
                "error": f"Ensure this field has no more than"
                f" {settings.BATCH_ROWS_SIZE_LIMIT} elements.",
            },
        ],
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert response.json()["detail"] == expected_error_detail


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_field_validation(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"field_{number_field.id}": 120,
            },
            {
                f"field_{number_field.id}": -200,
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert (
        response.json()["detail"]["items"]["1"][f"field_{number_field.id}"][0]["code"]
        == "min_value"
    )


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field = data_fixture.create_text_field(
        table=table, order=0, name="Color", text_default="white"
    )
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    boolean_field = data_fixture.create_boolean_field(
        table=table, order=2, name="For sale"
    )
    model = table.get_model()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"field_{text_field.id}": "green",
                f"field_{number_field.id}": 120,
                f"field_{boolean_field.id}": True,
            },
            {
                f"field_{text_field.id}": "yellow",
                f"field_{number_field.id}": 240,
                f"field_{boolean_field.id}": False,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                "id": 1,
                f"field_{text_field.id}": "green",
                f"field_{number_field.id}": "120",
                f"field_{boolean_field.id}": True,
                "order": "1.00000000000000000000",
            },
            {
                "id": 2,
                f"field_{text_field.id}": "yellow",
                f"field_{number_field.id}": "240",
                f"field_{boolean_field.id}": False,
                "order": "2.00000000000000000000",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body
    row_1 = model.objects.get(pk=1)
    row_2 = model.objects.get(pk=2)
    assert getattr(row_1, f"field_{text_field.id}") == "green"
    assert getattr(row_2, f"field_{text_field.id}") == "yellow"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_id_field_ignored(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field = data_fixture.create_text_field(
        table=table, order=0, name="Color", text_default="white"
    )
    model = table.get_model()
    row_1 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                "id": 1,
                f"field_{text_field.id}": "green",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert len(list(model.objects.all())) == 2


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_different_fields_provided(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field = data_fixture.create_text_field(
        table=table, order=0, name="Color", text_default="white"
    )
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    boolean_field = data_fixture.create_boolean_field(
        table=table, order=2, name="For sale"
    )
    model = table.get_model()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"field_{number_field.id}": 120,
            },
            {
                f"field_{text_field.id}": "yellow",
                f"field_{boolean_field.id}": True,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                "id": 1,
                f"field_{text_field.id}": "white",
                f"field_{number_field.id}": "120",
                f"field_{boolean_field.id}": False,
                "order": "1.00000000000000000000",
            },
            {
                "id": 2,
                f"field_{text_field.id}": "yellow",
                f"field_{number_field.id}": None,
                f"field_{boolean_field.id}": True,
                "order": "2.00000000000000000000",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body
    row_1 = model.objects.get(pk=1)
    row_2 = model.objects.get(pk=2)
    assert getattr(row_1, f"field_{text_field.id}") == "white"
    assert getattr(row_2, f"field_{text_field.id}") == "yellow"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_user_field_names(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field_name = "Color"
    number_field_name = "Horsepower"
    boolean_field_name = "For sale"
    text_field = data_fixture.create_text_field(
        table=table, order=0, name=text_field_name, text_default="white"
    )
    number_field = data_fixture.create_number_field(
        table=table, order=1, name=number_field_name
    )
    boolean_field = data_fixture.create_boolean_field(
        table=table, order=2, name=boolean_field_name
    )
    model = table.get_model()
    url = (
        reverse("api:database:rows:batch", kwargs={"table_id": table.id})
        + "?user_field_names"
    )
    request_body = {
        "items": [
            {
                f"{number_field_name}": 120,
            },
            {
                f"{text_field_name}": "yellow",
                f"{boolean_field_name}": True,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": 1,
                f"{text_field_name}": "white",
                f"{number_field_name}": "120",
                f"{boolean_field_name}": False,
                "order": "1.00000000000000000000",
            },
            {
                f"id": 2,
                f"{text_field_name}": "yellow",
                f"{number_field_name}": None,
                f"{boolean_field_name}": True,
                "order": "2.00000000000000000000",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body
    row_1 = model.objects.get(pk=1)
    row_2 = model.objects.get(pk=2)
    assert getattr(row_1, f"field_{text_field.id}") == "white"
    assert getattr(row_2, f"field_{text_field.id}") == "yellow"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_readonly_fields(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    created_on_field = data_fixture.create_created_on_field(table=table)
    model = table.get_model()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"field_{created_on_field.id}": "2019-08-24T14:15:22Z",
            },
            {
                f"field_{created_on_field.id}": "2019-08-24T14:15:22Z",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert (
        response.json()["detail"]
        == "Field of type created_on is read only and should not be set manually."
    )


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_ordering_last_rows(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    model = table.get_model()
    row_1 = model.objects.create(order=Decimal("1.00000000000000000000"))
    row_2 = model.objects.create(order=Decimal("2.00000000000000000000"))
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"field_{number_field.id}": 120,
            },
            {
                f"field_{number_field.id}": 240,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                "id": 3,
                f"field_{number_field.id}": "120",
                "order": "3.00000000000000000000",
            },
            {
                "id": 4,
                f"field_{number_field.id}": "240",
                "order": "4.00000000000000000000",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_create_rows_ordering_before_row(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    model = table.get_model()
    row_1 = model.objects.create(order=Decimal("1.00000000000000000000"))
    row_2 = model.objects.create(order=Decimal("2.00000000000000000000"))
    url = (
        reverse("api:database:rows:batch", kwargs={"table_id": table.id}) + "?before=2"
    )
    request_body = {
        "items": [
            {
                f"field_{number_field.id}": 120,
            },
            {
                f"field_{number_field.id}": 240,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                "id": 3,
                f"field_{number_field.id}": "120",
                "order": "1.99999999999999999998",
            },
            {
                "id": 4,
                f"field_{number_field.id}": "240",
                "order": "1.99999999999999999999",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body


@pytest.mark.django_db
@pytest.mark.field_formula
@pytest.mark.api_rows
def test_batch_create_rows_dependent_fields(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(table=table, order=1, name="Number")
    formula_field = data_fixture.create_formula_field(
        table=table,
        order=2,
        name="Number times two",
        formula="field('Number')*2",
        formula_type="number",
    )
    model = table.get_model()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"field_{number_field.id}": 120,
            },
            {
                f"field_{number_field.id}": 240,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": 1,
                f"field_{formula_field.id}": f"{str(120*2)}",
            },
            {
                f"id": 2,
                f"field_{formula_field.id}": f"{str(240*2)}",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert is_dict_subset(expected_response_body, response.json())


# Update


@pytest.mark.django_db
@pytest.mark.api_rows
@pytest.mark.parametrize("token_header", ["JWT invalid", "Token invalid"])
def test_batch_update_rows_invalid_token(api_client, data_fixture, token_header):
    table = data_fixture.create_database_table()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})

    response = api_client.patch(
        url,
        {},
        format="json",
        HTTP_AUTHORIZATION=token_header,
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_token_no_update_permission(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    no_update_perm_token = TokenHandler().create_token(
        user, table.database.group, "no permissions"
    )
    TokenHandler().update_token_permissions(
        user, no_update_perm_token, True, True, False, True
    )
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})

    response = api_client.patch(
        url,
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Token {no_update_perm_token.key}",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_NO_PERMISSION_TO_TABLE"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_user_not_in_group(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table()
    request_body = {
        "items": [
            {
                f"id": 1,
                f"field_11": "green",
            },
        ]
    }
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_invalid_table_id(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    url = reverse("api:database:rows:batch", kwargs={"table_id": 14343})

    response = api_client.patch(
        url,
        {},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_TABLE_DOES_NOT_EXIST"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_notexisting_row_ids(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    invalid_row_ids = [32, 3465]
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {"items": [{"id": id} for id in invalid_row_ids]}

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_ROW_DOES_NOT_EXIST"
    assert response.json()["detail"] == f"The rows {str(invalid_row_ids)} do not exist."


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_batch_size_limit(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    num_rows = settings.BATCH_ROWS_SIZE_LIMIT + 1
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {"items": [{"id": i} for i in range(num_rows)]}
    expected_error_detail = {
        "items": [
            {
                "code": "max_length",
                "error": f"Ensure this field has no more than {settings.BATCH_ROWS_SIZE_LIMIT} elements.",
            },
        ],
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert response.json()["detail"] == expected_error_detail


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_no_payload(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {}

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert response.json()["detail"]["items"][0]["error"] == "This field is required."


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_field_validation(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{number_field.id}": 120,
            },
            {
                f"id": row_2.id,
                f"field_{number_field.id}": -200,
            },
        ]
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert (
        response.json()["detail"]["items"]["1"][f"field_{number_field.id}"][0]["code"]
        == "min_value"
    )


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_missing_row_ids(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {"items": [{f"field_{number_field.id}": 123}]}

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert (
        response.json()["detail"]["items"]["0"]["id"][0]["error"]
        == "This field is required."
    )


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_repeated_row_ids(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    repeated_row_id = 32
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {"items": [{"id": repeated_row_id} for i in range(2)]}

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_ROW_IDS_NOT_UNIQUE"
    assert (
        response.json()["detail"]
        == f"The provided row ids {str([repeated_row_id])} are not unique."
    )


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field = data_fixture.create_text_field(
        table=table, order=0, name="Color", text_default="white"
    )
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    boolean_field = data_fixture.create_boolean_field(
        table=table, order=2, name="For sale"
    )
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{text_field.id}": "green",
                f"field_{number_field.id}": 120,
                f"field_{boolean_field.id}": True,
            },
            {
                f"id": row_2.id,
                f"field_{text_field.id}": "yellow",
                f"field_{number_field.id}": 240,
                f"field_{boolean_field.id}": False,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{text_field.id}": "green",
                f"field_{number_field.id}": "120",
                f"field_{boolean_field.id}": True,
                "order": "1.00000000000000000000",
            },
            {
                f"id": row_2.id,
                f"field_{text_field.id}": "yellow",
                f"field_{number_field.id}": "240",
                f"field_{boolean_field.id}": False,
                "order": "1.00000000000000000000",
            },
        ]
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body
    row_1.refresh_from_db()
    row_2.refresh_from_db()
    assert getattr(row_1, f"field_{text_field.id}") == "green"
    assert getattr(row_2, f"field_{text_field.id}") == "yellow"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_different_fields_provided(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field = data_fixture.create_text_field(
        table=table, order=0, name="Color", text_default="white"
    )
    number_field = data_fixture.create_number_field(
        table=table, order=1, name="Horsepower"
    )
    boolean_field = data_fixture.create_boolean_field(
        table=table, order=2, name="For sale"
    )
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{number_field.id}": 120,
            },
            {
                f"id": row_2.id,
                f"field_{text_field.id}": "yellow",
                f"field_{boolean_field.id}": True,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{text_field.id}": "white",
                f"field_{number_field.id}": "120",
                f"field_{boolean_field.id}": False,
                "order": "1.00000000000000000000",
            },
            {
                f"id": row_2.id,
                f"field_{text_field.id}": "yellow",
                f"field_{number_field.id}": None,
                f"field_{boolean_field.id}": True,
                "order": "1.00000000000000000000",
            },
        ]
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body
    row_1.refresh_from_db()
    row_2.refresh_from_db()
    assert getattr(row_1, f"field_{text_field.id}") == "white"
    assert getattr(row_2, f"field_{text_field.id}") == "yellow"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_user_field_names(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    text_field_name = "Color"
    number_field_name = "Horsepower"
    boolean_field_name = "For sale"
    text_field = data_fixture.create_text_field(
        table=table, order=0, name=text_field_name, text_default="white"
    )
    number_field = data_fixture.create_number_field(
        table=table, order=1, name=number_field_name
    )
    boolean_field = data_fixture.create_boolean_field(
        table=table, order=2, name=boolean_field_name
    )
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = (
        reverse("api:database:rows:batch", kwargs={"table_id": table.id})
        + "?user_field_names"
    )
    request_body = {
        "items": [
            {
                f"id": row_1.id,
                f"{number_field_name}": 120,
            },
            {
                f"id": row_2.id,
                f"{text_field_name}": "yellow",
                f"{boolean_field_name}": True,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": row_1.id,
                f"{text_field_name}": "white",
                f"{number_field_name}": "120",
                f"{boolean_field_name}": False,
                "order": "1.00000000000000000000",
            },
            {
                f"id": row_2.id,
                f"{text_field_name}": "yellow",
                f"{number_field_name}": None,
                f"{boolean_field_name}": True,
                "order": "1.00000000000000000000",
            },
        ]
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == expected_response_body
    row_1.refresh_from_db()
    row_2.refresh_from_db()
    assert getattr(row_1, f"field_{text_field.id}") == "white"
    assert getattr(row_2, f"field_{text_field.id}") == "yellow"


@pytest.mark.django_db
@pytest.mark.api_rows
def test_batch_update_rows_readonly_fields(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    created_on_field = data_fixture.create_created_on_field(table=table)
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{created_on_field.id}": "2019-08-24T14:15:22Z",
            },
            {
                f"id": row_2.id,
                f"field_{created_on_field.id}": "2019-08-24T14:15:22Z",
            },
        ]
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert (
        response.json()["detail"]
        == "Field of type created_on is read only and should not be set manually."
    )


@pytest.mark.django_db
@pytest.mark.field_formula
@pytest.mark.api_rows
def test_batch_update_rows_dependent_fields(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    number_field = data_fixture.create_number_field(table=table, order=1, name="Number")
    formula_field = data_fixture.create_formula_field(
        table=table,
        order=2,
        name="Number times two",
        formula="field('Number')*2",
        formula_type="number",
    )
    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    url = reverse("api:database:rows:batch", kwargs={"table_id": table.id})
    request_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{number_field.id}": 120,
            },
            {
                f"id": row_2.id,
                f"field_{number_field.id}": 240,
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": row_1.id,
                f"field_{formula_field.id}": f"{str(120*2)}",
            },
            {
                f"id": row_2.id,
                f"field_{formula_field.id}": f"{str(240*2)}",
            },
        ]
    }

    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert is_dict_subset(expected_response_body, response.json())


@pytest.mark.django_db
@pytest.mark.field_formula
@pytest.mark.api_rows
def test_batch_update_rows_dependent_fields_diff_table(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table, table_b, link_field = data_fixture.create_two_linked_tables(user=user)
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

    model_b = table_b.get_model()
    row_b_1 = model_b.objects.create()
    row_b_2 = model_b.objects.create()

    model = table.get_model()
    row_1 = model.objects.create()
    row_2 = model.objects.create()
    getattr(row_1, f"field_{link_field.id}").set([row_b_1.id, row_b_2.id])
    getattr(row_2, f"field_{link_field.id}").set([row_b_2.id])
    row_1.save()
    row_2.save()

    url = reverse("api:database:rows:batch", kwargs={"table_id": table_b.id})
    request_body = {
        "items": [
            {
                f"id": row_b_1.id,
                f"field_{number_field.id}": 120,
            },
            {
                f"id": row_b_2.id,
                f"field_{number_field.id}": 240,
            },
        ]
    }
    response = api_client.patch(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    row_1.refresh_from_db()
    row_2.refresh_from_db()
    assert getattr(row_1, f"field_{formula_field.id}")[0]["value"] == 120 * 2
    assert getattr(row_1, f"field_{formula_field.id}")[1]["value"] == 240 * 2
    assert getattr(row_2, f"field_{formula_field.id}")[0]["value"] == 240 * 2


@pytest.mark.django_db
@pytest.mark.field_formula
@pytest.mark.api_rows
def test_batch_create_rows_dependent_fields_lookup(api_client, data_fixture):
    user, jwt_token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)
    number_field = data_fixture.create_number_field(
        table=table_b, order=1, name="Number"
    )
    lookup_formula = FieldHandler().create_field(
        user,
        table_a,
        "formula",
        name="Sum of looked up number",
        formula=f"sum(lookup('{link_field.name}', 'Number'))",
    )
    assert lookup_formula.formula_type == "number"
    row_id_formula = FieldHandler().create_field(
        user,
        table_a,
        "formula",
        name="Row ID",
        formula=f"row_id()",
    )
    assert row_id_formula.formula_type == "number"
    model_a = table_a.get_model()
    model_b = table_b.get_model()
    row_b_1 = model_b.objects.create(**{f"field_{number_field.id}": 1})
    row_b_2 = model_b.objects.create(**{f"field_{number_field.id}": 1})

    url = reverse("api:database:rows:batch", kwargs={"table_id": table_a.id})
    request_body = {
        "items": [
            {
                f"field_{link_field.id}": [row_b_1.id, row_b_2.id],
            },
            {
                f"field_{link_field.id}": [row_b_1.id],
            },
            {
                f"field_{link_field.id}": [],
            },
        ]
    }
    expected_response_body = {
        "items": [
            {
                f"id": 1,
                f"field_{lookup_formula.id}": "2",
                f"field_{row_id_formula.id}": "1",
            },
            {
                f"id": 2,
                f"field_{lookup_formula.id}": "1",
                f"field_{row_id_formula.id}": "2",
            },
            {
                f"id": 3,
                f"field_{lookup_formula.id}": None,
                f"field_{row_id_formula.id}": "3",
            },
        ]
    }

    response = api_client.post(
        url,
        request_body,
        format="json",
        HTTP_AUTHORIZATION=f"JWT {jwt_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert is_dict_subset(expected_response_body, response.json())
