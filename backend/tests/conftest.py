import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.db import init_db, get_engine

@pytest.fixture
def engine(tmp_path):
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    init_db(engine)
    return engine
