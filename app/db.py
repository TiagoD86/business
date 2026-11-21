from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import Settings

class Base(DeclarativeBase):
    pass

def make_engine(settings: Settings):
    opts = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}
    return create_engine(settings.database_url, connect_args=opts, pool_pre_ping=True)

def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
