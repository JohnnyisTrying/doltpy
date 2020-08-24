from typing import Mapping, Callable
from doltpy.etl.sql_sync.db_tools import DoltAsTargetReader, DoltAsTargetWriter, DoltAsSourceReader, DoltAsSourceWriter
from doltpy.core.dolt import Dolt
from sqlalchemy.engine import Engine
from sqlalchemy import Table, Column, MetaData


def sync_to_dolt(source_reader: DoltAsTargetReader, target_writer: DoltAsTargetWriter, table_map: Mapping[str, str]):
    """
    Executes a sync from another database (currently on MySQL) to Dolt. Since generally other databases have a single
    notion of state, we merely seek to capture that notion of state. The source_reader function in
    doltpy.etl.sql_sync.mysql captures the state of the table, and then the target_writer in doltpy.etl.sql_sync.dolt
    merely writes that data to a commit.

    One could imagine a more complex implementation were the source_reader captures only rows that have updated_at
    field that is greater than the last sync timestamp. They would be easy enough to implement and we will provide
    examples in future documentation.
    :param source_reader:
    :param target_writer:
    :param table_map:
    :return:
    """
    _sync_helper(source_reader, target_writer, table_map)


def sync_from_dolt(source_reader: DoltAsSourceReader, target_writer: DoltAsSourceWriter, table_map: Mapping[str, str]):
    """
    Executes a sync from Dolt to another database (currently only MySQL). Works by taking source_reader that reads from
    Dolt. Various implementations are provided in doltpy.etl.sql_sync.dolt that offer different semantics. For example,
    one might want to choose whether to sync the state of table at HEAD of master, or take only incremental diffs.
    The writer implementations are more straightforward, and found in doltpy.etl.sql_sync.mysql. They offer the user the
    ability to configure what to do on primary key duplicates.

    Of course one can easily implement their own reads and writers, as they conform to the relevant type interfaces at
    the top of the file.
    :param source_reader:
    :param target_writer:
    :param table_map:
    :return:
    """
    _sync_helper(source_reader, target_writer, table_map)


def _sync_helper(source_reader, target_writer, table_map: Mapping[str, str]):
    to_sync = source_reader(list(table_map.keys()))
    remapped = {table_map[source_table]: source_data for source_table, source_data in to_sync.items()}
    target_writer(remapped)


def sync_schema_to_dolt(source_engine: Engine, repo: Dolt, table_map: Mapping[str, str], type_mapping: dict):
    """

    :param source_engine:
    :param repo:
    :param table_map:
    :param type_mapping:
    :return:
    """
    source_metadata = MetaData(bind=source_engine)
    source_metadata.reflect()
    target_metadata = MetaData(bind=repo.engine)
    target_metadata.reflect()
    for source_table_name, target_table_name in table_map.items():
        source_table = source_metadata.tables[source_table_name]
        target_table = coerce_schema_to_dolt(target_table_name, source_table, type_mapping)
        if target_table_name in target_metadata.tables.keys():
            # drop the table if it exists, Dolt will compute diffs when we recreate it
            target_table.drop(repo.engine)

        target_table.create(repo.engine)


def coerce_schema_to_dolt(target_table_name: str,
                          table: Table,
                          type_mapping: dict) -> Table:
    target_cols = []
    for col in table.columns:
        target_col = coerce_column_to_dolt(col, type_mapping)
        target_cols.append(target_col)
    # TODO:
    #   currently we do not support table or column level contraints except for nullability. We simply ignore these.
    return Table(target_table_name, MetaData(), *target_cols)


def coerce_column_to_dolt(column: Column, type_mapping: dict):
    """
    Defines how we map MySQL types to Dolt types, and removes unsupported column level constraints. Eventually this
    function should be trivial since we aim to faithfully support MySQL.
    :param column:
    :param type_mapping:
    :return:
    """
    return Column(column.name,
                  type_mapping[type(column.type)] if type(column.type) in type_mapping else column.type,
                  primary_key=column.primary_key,
                  autoincrement=column.autoincrement,
                  nullable=column.nullable)
