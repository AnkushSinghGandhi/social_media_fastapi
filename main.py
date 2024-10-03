from fastapi import FastAPI, HTTPException, status, Depends
from schema import UserCreate
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from utils import hash_password, verify_password, create_access_token, verify_access_token

app = FastAPI()

fake_users_db = {}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

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

@app.post("/login")
def login_user(form_data: OAuth2PasswordRequestForm = Depends()):
    user = fake_users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
def read_users_me(token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = fake_users_db.get(user_email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user