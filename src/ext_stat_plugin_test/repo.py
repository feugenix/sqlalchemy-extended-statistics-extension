from sqlalchemy import Column, Integer, String, Index, PrimaryKeyConstraint
from .db import Base
from plugin.extended_stat import ExtendedStatistics, NDISTINCT, MCV

class SomeClass(Base):
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
            NDISTINCT,
            "name",
            "clear_col",
        ),
        ExtendedStatistics(
            "some_table_id_name_stats",
            MCV,
            "id",
            "name",
        ),
    )