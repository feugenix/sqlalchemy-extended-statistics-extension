from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.declarative import declarative_base


engine = create_engine('postgresql://admin:@localhost/test_sqlaclhemy')
public_metadata = MetaData()
test_metadata = MetaData(schema="test")

PublicBase = declarative_base(metadata=public_metadata)
TestBase = declarative_base(metadata=test_metadata)