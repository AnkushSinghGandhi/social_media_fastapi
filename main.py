from fastapi import FastAPI, HTTPException, status, Depends
from schema import UserCreate
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from utils import hash_password, verify_password, create_access_token, verify_access_token
from database import engine, get_db
from models import Base, User

app = FastAPI()

Base.metadata.create_all(bind=engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@app.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # Check if the email is already registered
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash the password and create a new user entry
    hashed_password = hash_password(user.password)
    new_user = User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User registered successfully", "user_id": new_user.id}

@app.post("/login")
def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Query the user from the database by username (assuming username is unique)
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Create access token with the user's email as the subject
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
def read_users_me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Verify the token and extract the user email (assuming token contains email in "sub")
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    
    # Query the user by email from the database
    user = db.query(User).filter(User.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return {
        "username": user.username,
        "email": user.email,
    }
