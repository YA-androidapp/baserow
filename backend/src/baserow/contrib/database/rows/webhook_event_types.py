from baserow.contrib.database.api.rows.serializers import (
    get_row_serializer_class,
    remap_serialized_rows_to_user_field_names,
    RowSerializer,
)
from baserow.contrib.database.webhooks.registries import WebhookEventType
from baserow.contrib.database.ws.rows.signals import before_rows_update
from .signals import rows_created, rows_updated, rows_deleted

class RowsEventType(WebhookEventType):
    def get_row_serializer(self, webhook, model):
        return get_row_serializer_class(
            model,
            RowSerializer,
            is_response=True,
            user_field_names=webhook.use_user_field_names,
        )

    def get_payload(self, event_id, webhook, model, table, rows, **kwargs):
        payload = super().get_payload(event_id, webhook, **kwargs)
        payload["items"] = self.get_row_serializer(webhook, model)(rows, many=True).data
        return payload

class RowsCreatedEventType(RowsEventType):
    type = "rows.created"
    signal = rows_created


    def get_test_call_payload(self, table, model, event_id, webhook):
        rows = [
            model(id=0, order=0)
        ]
        payload = self.get_payload(
            event_id=event_id,
            webhook=webhook,
            model=model,
            table=table,
            rows=rows,
        )
        return payload

class RowsUpdatedEventType(RowsEventType):
    type = "rows.updated"
    signal = rows_updated

    def get_payload(
        self, event_id, webhook, model, table, rows, before_return, **kwargs
    ):
        payload = super().get_payload(event_id, webhook, model, table, rows, **kwargs)
        
        old_items = dict(before_return)[before_rows_update]

        if webhook.use_user_field_names:
            old_items = remap_serialized_rows_to_user_field_names(old_items, model)

        payload["old_items"] = old_items

        return payload

    def get_test_call_payload(self, table, model, event_id, webhook):
        rows = [
            model(id=0, order=0)
        ]
        before_return = {
            before_rows_update: before_rows_update(
                rows=rows,
                model=model,
                sender=None,
                user=None,
                table=None,
                updated_field_ids=None,
            )
        }
        payload = self.get_payload(
            event_id=event_id,
            webhook=webhook,
            model=model,
            table=table,
            rows=rows,
            before_return=before_return,
        )
        return payload


class RowsDeletedEventType(WebhookEventType):
    type = "rows.deleted"
    signal = rows_deleted

    def get_payload(self, event_id, webhook, rows, **kwargs):
        payload = super().get_payload(event_id, webhook, **kwargs)
        payload["row_ids"] = [row.id for row in rows]
        return payload

    def get_test_call_payload(self, table, model, event_id, webhook):
        rows = [
            model(id=0, order=0)
        ]
        
        payload = self.get_payload(
            event_id=event_id,
            webhook=webhook,
            model=model,
            table=table,
            rows=rows,
        )
        return payload