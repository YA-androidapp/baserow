import dataclasses
from typing import Optional
from baserow.contrib.database.fields.handler import FieldHandler

from baserow.contrib.database.fields.models import Field
from baserow.contrib.database.views.handler import ViewHandler
from baserow.contrib.database.views.models import View, ViewFilter, ViewSort
from baserow.core.action.models import Action
from baserow.core.action.registries import ActionScopeStr, ActionType
from baserow.core.action.scopes import ViewActionScopeType
from django.contrib.auth.models import AbstractUser


class CreateViewFilterActionType(ActionType):
    type = "create_view_filter"

    @dataclasses.dataclass
    class Params:
        view_filter_id: int
        view_id: int
        field_id: int
        filter_type: str
        filter_value: str

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        view: View,
        field: Field,
        filter_type: str,
        filter_value: str,
    ) -> ViewFilter:
        """
        Creates a new filter for the provided view.
        See baserow.contrib.database.views.handler.ViewHandler.create_field
        for more. When undone the view_filter is fully deleted from the
        database and when redone it is recreated.

        :param user: The user creating the filter.
        :param view: The view to create the filter for.
        :param field: The field to filter by.
        :param filter_type: Indicates how the field's value
        must be compared to the filter's value.
        :param filter_value: The filter value that must be
        compared to the field's value.
        """

        view_filter = ViewHandler().create_filter(
            user, view, field, filter_type, filter_value
        )
        cls.register_action(
            user=user,
            params=cls.Params(
                view_filter.id, view.id, field.id, filter_type, filter_value
            ),
            scope=cls.scope(view.id),
        )
        return view_filter

    @classmethod
    def scope(cls, view_id: int) -> ActionScopeStr:
        return ViewActionScopeType.value(view_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_to_undo: Action):
        view_filter = ViewHandler().get_filter(user, params.view_filter_id)

        ViewHandler().delete_filter(user, view_filter)

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_to_redo: Action):
        view_handler = ViewHandler()
        view = view_handler.get_view(params.view_id)
        field = FieldHandler().get_field(params.field_id)

        view_filter = view_handler.create_filter(
            user, view, field, params.filter_type, params.filter_value
        )

        # Update params with id of newly created view filter
        action_to_redo.params["view_filter_id"] = view_filter.id


class UpdateViewFilterActionType(ActionType):
    type = "update_view_filter"

    @dataclasses.dataclass
    class Params:
        view_filter_id: int
        original_field_id: int
        original_filter_type: str
        original_filter_value: str
        new_field_id: int
        new_filter_type: str
        new_filter_value: str

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        view_filter: ViewFilter,
        field: Optional[Field] = None,
        filter_type: Optional[str] = None,
        filter_value: Optional[str] = None,
    ) -> ViewFilter:
        """
        Updates the values of an existing view filter.
        See baserow.contrib.database.views.handler.ViewHandler.update_filter
        for more. When undone the view_filter is restored to it's original state
        and when redone it is updated to it's new state.

        :param user: The user on whose behalf the view filter is updated.
        :param view_filter: The view filter that needs to be updated.
        :param field: The model of the field to filter by.
        :param filter_type: Indicates how the field's value
        must be compared to the filter's value.
        :param filter_value: The filter value that must be
        compared to the field's value.
        """

        original_view_filter_field_id = view_filter.field.id
        original_view_filter_type = view_filter.type
        original_view_filter_value = view_filter.value

        view_handler = ViewHandler()
        updated_view_filter = view_handler.update_filter(
            user, view_filter, field, filter_type, filter_value
        )
        cls.register_action(
            user=user,
            params=cls.Params(
                view_filter.id,
                original_view_filter_field_id,
                original_view_filter_type,
                original_view_filter_value,
                updated_view_filter.field.id,
                updated_view_filter.type,
                updated_view_filter.value,
            ),
            scope=cls.scope(view_filter.view.id),
        )

        return updated_view_filter

    @classmethod
    def scope(cls, view_id: int) -> ActionScopeStr:
        return ViewActionScopeType.value(view_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_to_undo: Action):
        field = FieldHandler().get_field(params.original_field_id)

        view_handler = ViewHandler()
        view_filter = view_handler.get_filter(user, params.view_filter_id)

        view_handler.update_filter(
            user,
            view_filter,
            field,
            params.original_filter_type,
            params.original_filter_value,
        )

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_to_redo: Action):
        field = FieldHandler().get_field(params.new_field_id)

        view_handler = ViewHandler()
        view_filter = view_handler.get_filter(user, params.view_filter_id)

        data = {"field": field}
        if params.new_filter_type is not None:
            data["type_name"] = params.new_filter_type
        if params.new_filter_value is not None:
            data["value"] = params.new_filter_value

        view_handler.update_filter(user, view_filter, **data)


class DeleteViewFilterActionType(ActionType):
    type = "delete_view_filter"

    @dataclasses.dataclass
    class Params:
        view_filter_id: int
        view_id: int
        field_id: int
        filter_type: str
        filter_value: str

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        view_filter: View,
    ):
        """
        Deletes an existing view filter.
        See baserow.contrib.database.views.handler.ViewHandler.delete_filter
        for more. When undone the view_filter is recreated and when redone
        it is deleted.

        :param user: The user on whose behalf the view filter is deleted.
        :param view_filter: The view filter that needs to be deleted.
        """

        ViewHandler().delete_filter(user, view_filter)

        cls.register_action(
            user=user,
            params=cls.Params(
                view_filter.id,
                view_filter.view.id,
                view_filter.field.id,
                view_filter.type,
                view_filter.value,
            ),
            scope=cls.scope(view_filter.view.id),
        )

    @classmethod
    def scope(cls, view_id: int) -> ActionScopeStr:
        return ViewActionScopeType.value(view_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_to_undo: Action):
        view_handler = ViewHandler()
        view = view_handler.get_view(params.view_id)
        field = FieldHandler().get_field(params.field_id)

        view_filter = view_handler.create_filter(
            user, view, field, params.filter_type, params.filter_value
        )
        action_to_undo.params["view_filter_id"] = view_filter.id

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_to_redo: Action):
        view_filter = ViewHandler().get_filter(user, params.view_filter_id)

        ViewHandler().delete_filter(user, view_filter)


class CreateViewSortActionType(ActionType):
    type = "create_view_sort"

    @dataclasses.dataclass
    class Params:
        view_sort_id: int
        view_id: int
        field_id: int
        sort_order: str

    @classmethod
    def do(
        cls, user: AbstractUser, view: View, field: Field, sort_order: str
    ) -> ViewSort:
        """
        Creates a new view sort.
        See baserow.contrib.database.views.handler.ViewHandler.create_sort
        for more. When undone the view_sort is fully deleted from the
        database and when redone it is recreated.

        :param user: The user on whose behalf the view sort is created.
        :param view: The view for which the sort needs to be created.
        :param field: The field that needs to be sorted.
        :param sort_order: The desired order, can either be ascending (A to Z) or
            descending (Z to A).
        """

        view_sort = ViewHandler().create_sort(user, view, field, sort_order)

        cls.register_action(
            user=user,
            params=cls.Params(view_sort.id, view.id, field.id, sort_order),
            scope=cls.scope(view.id),
        )
        return view_sort

    @classmethod
    def scope(cls, view_id: int) -> ActionScopeStr:
        return ViewActionScopeType.value(view_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_to_undo: Action):
        view_sort = ViewHandler().get_sort(user, params.view_sort_id)

        ViewHandler().delete_sort(user, view_sort)

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_to_redo: Action):
        view_handler = ViewHandler()
        field = FieldHandler().get_field(params.field_id)
        view = view_handler.get_view(params.view_id)

        view_sort = view_handler.create_sort(user, view, field, params.sort_order)
        action_to_redo.params["view_sort_id"] = view_sort.id


class UpdateViewSortActionType(ActionType):
    type = "update_view_sort"

    @dataclasses.dataclass
    class Params:
        view_sort_id: int
        original_field_id: int
        original_sort_order: str
        new_field_id: int
        new_sort_order: str

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        view_sort: ViewSort,
        field: Optional[Field] = None,
        order: Optional[str] = None,
    ) -> ViewSort:
        """
        Updates the values of an existing view sort.
        See baserow.contrib.database.views.handler.ViewHandler.update_sort
        for more. When undone the view_sort is restored to it's original state
        and when redone it is updated to it's new state.

        :param user: The user on whose behalf the view sort is updated.
        :param view_sort: The view sort that needs to be updated.
        :param field: The field that must be sorted on.
        :param order: Indicates the sort order direction.
        """

        data = {}
        if field is not None:
            data["field"] = field
        if order is not None:
            data["order"] = order

        original_view_sort_field_id = view_sort.field.id
        original_view_sort_sort_order = view_sort.order

        handler = ViewHandler()
        updated_view_sort = handler.update_sort(user, view_sort, **data)

        cls.register_action(
            user=user,
            params=cls.Params(
                view_sort.id,
                original_view_sort_field_id,
                original_view_sort_sort_order,
                updated_view_sort.field.id,
                updated_view_sort.order,
            ),
            scope=cls.scope(view_sort.view.id),
        )

        return updated_view_sort

    @classmethod
    def scope(cls, view_id: int) -> ActionScopeStr:
        return ViewActionScopeType.value(view_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_to_undo: Action):
        field = FieldHandler().get_field(params.original_field_id)

        view_handler = ViewHandler()
        view_sort = view_handler.get_sort(user, params.view_sort_id)

        data = {"field": field}
        if params.original_sort_order is not None:
            data["order"] = params.original_sort_order

        view_handler.update_sort(user, view_sort, **data)

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_to_redo: Action):
        field = FieldHandler().get_field(params.new_field_id)

        view_handler = ViewHandler()
        view_sort = view_handler.get_sort(user, params.view_sort_id)

        data = {"field": field}
        if params.new_sort_order is not None:
            data["order"] = params.new_sort_order

        view_handler.update_sort(user, view_sort, **data)


class DeleteViewSortActionType(ActionType):
    type = "delete_view_sort"

    @dataclasses.dataclass
    class Params:
        view_sort_id: int
        view_id: int
        field_id: int
        sort_order: str

    @classmethod
    def do(cls, user: AbstractUser, view_sort: ViewSort):
        """
        Deletes an existing view sort.
        See baserow.contrib.database.views.handler.ViewHandler.delete_sort
        for more. When undone the view_sort is recreated and when redone
        it is deleted.

        :param user: The user on whose behalf the view sort is deleted.
        :param view_sort: The view sort instance that needs
        to be deleted.
        """

        ViewHandler().delete_sort(user, view_sort)

        cls.register_action(
            user=user,
            params=cls.Params(
                view_sort.id,
                view_sort.view.id,
                view_sort.field.id,
                view_sort.order,
            ),
            scope=cls.scope(view_sort.view.id),
        )

    @classmethod
    def scope(cls, view_id: int) -> ActionScopeStr:
        return ViewActionScopeType.value(view_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_to_undo: Action):
        view_handler = ViewHandler()
        view = view_handler.get_view(params.view_id)
        field = FieldHandler().get_field(params.field_id)

        view_sort = view_handler.create_sort(user, view, field, params.sort_order)
        action_to_undo.params["view_sort_id"] = view_sort.id

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_to_redo: Action):
        view_sort = ViewHandler().get_sort(user, params.view_sort_id)

        ViewHandler().delete_sort(user, view_sort)
