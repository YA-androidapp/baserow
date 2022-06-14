from collections import defaultdict
from typing import Optional, Dict, List, Tuple, Union, Set, cast

from django.db.models import Expression, Q

from baserow.contrib.database.fields.dependencies.exceptions import InvalidViaPath
from baserow.contrib.database.fields.field_cache import FieldCache
from baserow.contrib.database.fields.models import Field, LinkRowField
from baserow.contrib.database.fields.signals import field_updated
from baserow.contrib.database.table.models import Table

StartingRowIdsType = Union[Optional[int], Optional[List[int]]]


class PathBasedUpdateStatementCollector:
    def __init__(
        self,
        table: Table,
        connection_here: Optional[LinkRowField],
    ):
        self.update_statements: Dict[str, Expression] = {}
        self.table = table
        self.sub_paths: Dict[str, PathBasedUpdateStatementCollector] = {}
        self.connection_here: Optional[LinkRowField] = connection_here

    def add_update_statement(
        self,
        field: Field,
        update_statement: Expression,
        path_from_starting_table: Optional[List[LinkRowField]] = None,
    ):
        if not path_from_starting_table:
            if self.table != field.table:
                raise InvalidViaPath()
            self.update_statements[field.db_column] = update_statement
        else:
            next_via_field_link = path_from_starting_table[0]
            if next_via_field_link.link_row_table != self.table:
                raise InvalidViaPath()
            next_link_db_column = next_via_field_link.db_column
            if next_link_db_column not in self.sub_paths:
                self.sub_paths[next_link_db_column] = PathBasedUpdateStatementCollector(
                    next_via_field_link.table,
                    next_via_field_link,
                )
            self.sub_paths[next_link_db_column].add_update_statement(
                field, update_statement, path_from_starting_table[1:]
            )

    def execute_all(
        self,
        field_cache: FieldCache,
        starting_row_id: StartingRowIdsType = None,
        path_to_starting_table: Optional[List[str]] = None,
        deleted_m2m_rels_per_link_field: Optional[Dict[int, Set[int]]] = None,
    ):
        path_to_starting_table = path_to_starting_table or []
        if self.connection_here is not None:
            path_to_starting_table = [self.connection_here] + path_to_starting_table
        self._execute_pending_update_statements(
            field_cache,
            path_to_starting_table,
            starting_row_id,
            deleted_m2m_rels_per_link_field,
        )

        for sub_path in self.sub_paths.values():
            sub_path.execute_all(
                starting_row_id=starting_row_id,
                path_to_starting_table=path_to_starting_table,
                field_cache=field_cache,
                deleted_m2m_rels_per_link_field=deleted_m2m_rels_per_link_field,
            )

    def _execute_pending_update_statements(
        self,
        field_cache: FieldCache,
        path_to_starting_table: List[LinkRowField],
        starting_row_id: Optional[int],
        deleted_m2m_rels_per_link_field: Optional[Dict[int, Set[int]]],
    ):
        model = field_cache.get_model(self.table)
        qs = model.objects_and_trash
        if starting_row_id is not None:
            if len(path_to_starting_table) == 0:
                path_to_starting_table_id_column = "id"
            else:
                path_to_starting_table_id_column = (
                    "__".join([p.db_column for p in path_to_starting_table]) + "__id"
                )
            if isinstance(starting_row_id, list):
                path_to_starting_table_id_column += "__in"

            filter_for_rows_connected_to_starting_row = Q(
                **{path_to_starting_table_id_column: starting_row_id}
            ) | self._include_rows_connected_to_deleted_m2m_relationships(
                deleted_m2m_rels_per_link_field,
                path_to_starting_table,
            )

            qs = qs.filter(filter_for_rows_connected_to_starting_row)
        qs.update(**self.update_statements)

    def _include_rows_connected_to_deleted_m2m_relationships(
        self,
        deleted_m2m_rels_per_link_field: Dict[int, Set[int]],
        path_to_starting_table: List[LinkRowField],
    ):
        """
        If a row or batch of rows have been updated breaking their link row connections
        with other rows, we need to ensure that those other rows are still updated.
        We can't just join back to the starting row id as that m2m relation has been
        deleted by now. Instead the provided dict contains per link field which rows
        have had their connections deleted. This method then constructs a Q filter that
        ensures this UPDATE statement will also update those rows as they need to
        change their values because a connection has been removed for them.

        :return: A filter including any rows which previously were connected to the
            starting row.
        """

        if deleted_m2m_rels_per_link_field is None or not path_to_starting_table:
            return Q()

        # The first link row field in the path will be a link row field not in the
        # starting table, but which leads to the starting table. However the
        # deleted_m2m_rels_per_link_field is a dictionary per link field of rows in
        # the table it links to which have had their connections removed. Hence we
        # need to use the link row field in the starting table to lookup the deleted
        # row ids in the table after the starting table.
        link_row_field_in_starting_table: int = cast(
            int, path_to_starting_table[-1].link_row_related_field_id
        )
        filters = Q()
        if link_row_field_in_starting_table in deleted_m2m_rels_per_link_field:
            path_to_table_after_starting_table = "".join(
                [p.db_column + "__" for p in path_to_starting_table[:-1]]
            )

            row_ids = deleted_m2m_rels_per_link_field[link_row_field_in_starting_table]
            filter_kwargs_forcing_update_for_row_with_deleted_rels = {
                f"{path_to_table_after_starting_table}id__in": row_ids
            }
            filters |= Q(**filter_kwargs_forcing_update_for_row_with_deleted_rels)
        return filters


class FieldUpdateCollector:
    """
    From a starting table this class collects updated fields and an update
    statements to re-calculate their cell values. Then can execute the cell update
    statements in the correct
    order and send field_updated signals informing the user about the updated fields.
    """

    def __init__(
        self,
        starting_table: Table,
        starting_row_id: StartingRowIdsType = None,
        deleted_m2m_rels_per_link_field: Optional[Dict[int, Set[int]]] = None,
    ):
        """

        :param starting_table: The table where the triggering field update begins.
        :param starting_row_id: If the update starts from a single row in the
            starting table set this and all update statements executed by this collector
            will only update rows which join back to this starting row.
        """

        self._updated_fields_per_table: Dict[int, Dict[int, Field]] = defaultdict(dict)
        self._starting_row_id = starting_row_id
        self._starting_table = starting_table
        self._deleted_m2m_rels_per_link_field = deleted_m2m_rels_per_link_field

        self._update_statement_collector = PathBasedUpdateStatementCollector(
            self._starting_table, connection_here=None
        )

    def add_field_with_pending_update_statement(
        self,
        field: Field,
        update_statement: Expression,
        via_path_to_starting_table: Optional[List[LinkRowField]] = None,
    ):
        """
        Stores the provided field as an updated one to send in field updated signals
        when triggered to do so. Also stores the provided update statement to execute
        later when apply_updates is called.

        :param field: The field which has been updated.
        :param update_statement: The update statement to run over the fields row values
            to update them.
        :param via_path_to_starting_table: A list of link row fields which lead from
            the self.starting_table to the table containing field. Used to properly
            order the update statements so the graph is updated in sequence and also
            used if self.starting_row_id is set so only rows which join back to the
            starting row via this path are updated.
        """

        # noinspection PyTypeChecker
        self._updated_fields_per_table[field.table_id][field.id] = field
        self._update_statement_collector.add_update_statement(
            field, update_statement, via_path_to_starting_table
        )

    def apply_updates_and_get_updated_fields(
        self, field_cache: FieldCache
    ) -> List[Field]:
        """
        Triggers all update statements to be executed in the correct order in as few
        update queries as possible.
        :return: The list of all fields which have been updated in the starting table.
        """

        self._update_statement_collector.execute_all(
            field_cache,
            self._starting_row_id,
            deleted_m2m_rels_per_link_field=self._deleted_m2m_rels_per_link_field,
        )
        return self._for_table(self._starting_table)

    def send_additional_field_updated_signals(self):
        """
        Sends field_updated signals for all fields which have been updated in tables
        which were not the self._starting_table. Will group together fields per table
        so only one signal is sent per table where the field_updated.field will be the
        first updated field encountered for that table and field_updated.related_fields
        will be all the other updated fields in that table.
        """

        for field, related_fields in self._get_updated_fields_per_table():
            if field.table != self._starting_table:
                field_updated.send(
                    self,
                    field=field,
                    related_fields=related_fields,
                    user=None,
                )

    def _get_updated_fields_per_table(self) -> List[Tuple[Field, List[Field]]]:
        result = []
        for fields_dict in self._updated_fields_per_table.values():
            fields = list(fields_dict.values())
            result.append((fields[0], fields[1:]))
        return result

    def _for_table(self, table) -> List[Field]:
        return list(self._updated_fields_per_table.get(table.id, {}).values())
