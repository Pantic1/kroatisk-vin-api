"""
USERS ROUTER
============
Tilføj til din FastAPI app:

    # main.py
    from routers import usersRouter
    app.include_router(usersRouter.router, prefix="/users", tags=["Users"])

Endpoints:
  GET    /users/        -> alle brugere (uden hashed_password)
  GET    /users/{id}    -> én bruger
  DELETE /users/{id}    -> slet bruger

Bruger din eksisterende SQLAlchemy ORM-stil med User-model i config.model.
Hvis din model hedder noget andet (fx Users), så juster importen nedenunder.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.config import get_db
from config.model import User   # ← juster hvis din model hedder noget andet

router = APIRouter()


def _serialize(u: User) -> dict:
    """Send brugerdata uden hashed_password."""
    return {
        "id":         u.id,
        "username":   u.username,
        "email":      u.email,
        "role":       u.role,
        "created_at": u.created_at,
    }


# ---------------------------------------------------------------------------
# GET /users/  -> alle brugere
# ---------------------------------------------------------------------------
@router.get("/")
def list_users(db: Session = Depends(get_db)):
    users = (
        db.query(User)
          .order_by(User.created_at.desc())
          .all()
    )
    return [_serialize(u) for u in users]


# ---------------------------------------------------------------------------
# GET /users/{user_id}  -> én bruger
# ---------------------------------------------------------------------------
@router.get("/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize(u)


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}  -> slet bruger
# ---------------------------------------------------------------------------
@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(user_id: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    # Sikkerhed: tillad ikke at slette sidste admin
    if u.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Kan ikke slette den sidste admin",
            )

    db.delete(u)
    db.commit()
    return {"ok": True, "deleted_id": user_id}