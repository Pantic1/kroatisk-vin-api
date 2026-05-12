# Standard library
import configparser

# Third-party packages
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

# Local modules
from config.config import engine, get_db
from sqlalchemy.ext.declarative import declarative_base
from fastapi.middleware.cors import CORSMiddleware

# Routers
from routers import orderRouter, userRouter
import routers.authRouter as auth_router
import routers.productsRouter as productsRouter
import routers.uploadsRouter as uploadsRouter
import routers.companyRouter as companyRouter
import routers.userRouter as userRouter


sample_config = """
[mysqld]
  user = mysql
  pid-file = /var/run/mysqld/mysqld.pid
  skip-external-locking
  old_passwords = 1
  skip-bdb
  # we don't need ACID today
  skip-innodb
"""

config = configparser.ConfigParser(allow_no_value=True)
config.read_string(sample_config)     
Base = declarative_base()

# Create the table in the database
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # You can restrict this to specific methods (e.g., ["GET", "POST"])
    allow_headers=["*"],  # You can restrict this to specific headers if needed
)

@app.get('/')
async def home(db: Session = Depends(get_db)):
    return {"success": "API is live"}

app.include_router(auth_router.router, prefix='/auth', tags=['Authentication'])
app.include_router(userRouter.router, prefix='/users', tags=['Users'])
app.include_router(productsRouter.router, prefix='/products', tags=['Products'])
app.include_router(uploadsRouter.router, prefix='/uploads', tags=['Uploads'])
app.include_router(companyRouter.router, prefix='/company', tags=['Company'])
app.include_router(orderRouter.router, prefix='/orders', tags=['Orders'])
