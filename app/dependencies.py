from .database import get_db as _get_db
from fastapi import Depends
from contextlib import contextmanager

def get_db():
    with _get_db() as conn:
        yield conn