from sqlalchemy import Column, Integer, String, Index, PrimaryKeyConstraint

from ext_stat_plugin.extended_statistic.sqlalchemy import ExtendedStatistics
from .db import PublicBase, TestBase
from ext_stat_plugin.extended_statistic.sqlalchemy import NDISTINCT, MCV

class SomeClass(PublicBase):
    __tablename__ = 'some_table'

    id = Column(Integer, info={'ext_stats': {
        "target": 1000,
    }})
    name = Column(String(50))
    clear_col = Column(String(50), info={'ext_stats': {
        "target": 1051,
    }})

    __table_args__ = (
        Index('ix_some_table_name_clear_col', 'name', 'clear_col'),
        PrimaryKeyConstraint("id", "name", name="mytable_pk"),
        ExtendedStatistics(
            "some_table_name_clear_col_stats",
            [NDISTINCT],
            "name",
            "clear_col",
        ),
        ExtendedStatistics(
            "some_table_id_name_stats",
            [MCV],
            "id",
            "name",
        ),
    )

class SomeClassTest(TestBase):
    __tablename__ = 'some_table_test'

    id = Column(Integer, primary_key=True, info={'ext_stats': {
        "target": 1000,
    }})
    name = Column(String(50))
    description = Column(String(50))

    __table_args__ = (
        ExtendedStatistics(
            "some_table_test_name_description_stats",
            [NDISTINCT],
            "name",
            "description",
        ),
        ExtendedStatistics(
            "some_table_test_id_name_description_stats",
            [MCV],
            "id",
            "name",
            "description",
        ),
    )