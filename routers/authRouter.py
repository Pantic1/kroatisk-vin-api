from datetime import date, datetime
from multiprocessing import get_context
import uuid
from fastapi import APIRouter, Body, Depends, status, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from config.config import get_db
from sqlalchemy import exc, inspect

from config.model import User
from controllers.authController import create_access_token
from models.schemas import LoginRequest, TokenResponse, UserCreate, UserResponse
from passlib.context import CryptContext

router = APIRouter()
MAX_RETRIES = 3

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Hash:
    @staticmethod
    def encrypt(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
    
@router.post("/signup", response_model=UserResponse)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    # Tjek om email allerede findes
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En bruger med denne email findes allerede."
        )

    hashed_pw = Hash.encrypt(user.password)  # bruger Hash.encrypt nu

    db_user = User(
        id=str(uuid.uuid4()),
        username=user.username,
        email=user.email,
        hashed_password=hashed_pw,
        role=user.role
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Forkert e-mail eller adgangskode")

    if not Hash.verify(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Forkert e-mail eller adgangskode")

    access_token = create_access_token({"sub": user.email, "name": user.username, "id": user.id})
    return {"token": access_token}