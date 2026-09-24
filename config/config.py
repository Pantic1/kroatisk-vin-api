import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SQLALCHEMY_DATABASE_URL = os.environ.get("DB_LOGIN")

# MySQL lukker selv forbindelser efter 300 sekunders inaktivitet (wait_timeout).
# Uden pre_ping deler puljen en død forbindelse ud, og den første forespørgsel
# efter en stille periode fejler med OperationalError. recycle holder os under
# serverens grænse, så det sjældent når at ske.
# connect_timeout kender kun MySQL-driveren; SQLite (som bruges i test) fejler på den
_connect_args = ({"connect_timeout": 10}
                 if SQLALCHEMY_DATABASE_URL.startswith("mysql") else {})

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280,
    connect_args=_connect_args,
)

sessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_db():
    db = sessionLocal()
    try:
        yield db
        db.commit()  # Commit the transaction if successful
        db.close()
    except Exception as e:
        db.rollback()  # Rollback the transaction on exception
        raise e
    finally:
        db.close()