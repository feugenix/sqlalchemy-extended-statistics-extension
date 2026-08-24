from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.declarative import declarative_base


engine = create_engine('postgresql://admin:@localhost/test_sqlaclhemy')
metadata = MetaData()

Base = declarative_base(metadata=metadata)
