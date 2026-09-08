from tempfile import NamedTemporaryFile
from jarvis.db import Database

def test_database_roundtrip():
    with NamedTemporaryFile(suffix='.db') as f:
        db=Database(f"sqlite:///{f.name}");db.init()
        sid=db.create_session();db.add_message(sid,"user","hello")
        assert db.recent_messages(sid)[0]["content"]=="hello"
