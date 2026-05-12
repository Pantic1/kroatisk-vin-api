import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SQLALCHEMY_DATABASE_URL = os.environ.get("DB_LOGIN")

engine = create_engine(SQLALCHEMY_DATABASE_URL)

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