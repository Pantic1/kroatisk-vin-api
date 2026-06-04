import bcrypt as _bcrypt
from datetime import datetime, timedelta
from models import schemas
from jose import jwt, JWTError
from fastapi import status, HTTPException, Depends, APIRouter
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from config.config import get_db
from typing import List

router = APIRouter()

# SECRET_KEY = os.environ.get("SECRET_KEY")
# ALGORITHM = os.environ.get("ALGORITHM")
# ACCESS_TOKEN_EXPIRE_MINUTES = os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES")

SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 300
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 300

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


class Hash:
    @staticmethod
    def bcrypt(password: str) -> str:
        return _bcrypt.hashpw(password[:72].encode(), _bcrypt.gensalt()).decode()

    @staticmethod
    def verify(plain_password: str, hashed_password: str) -> bool:
        return _bcrypt.checkpw(plain_password[:72].encode(), hashed_password.encode())


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(plain_password[:72].encode(), hashed_password.encode())

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


