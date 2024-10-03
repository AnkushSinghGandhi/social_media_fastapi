from fastapi import FastAPI, HTTPException, status
from schema import UserCreate
from utils import hash_password

app = FastAPI()

fake_users_db = {}

@app.post("/register")
def register_user(user: UserCreate):
    if user.email in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = hash_password(user.password)
    fake_users_db[user.email] = {
        "username": user.username,
        "email": user.email,
        "password": hashed_password
    }
    return {"message": "User registered successfully"}
