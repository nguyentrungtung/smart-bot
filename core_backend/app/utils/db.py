# app/utils/db.py
import logging
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger("db")

# Global variables for the pool and checkpointer
# initialized by the lifespan manager in main.py
pool = None
checkpointer = None

def get_pool():
    global pool
    return pool

def get_checkpointer():
    global checkpointer
    return checkpointer
