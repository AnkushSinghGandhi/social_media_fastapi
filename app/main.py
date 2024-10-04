from fastapi import FastAPI, HTTPException, status, Depends
from app.schema import UserCreate, PostCreate, CommentCreate
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.utils import hash_password, verify_password, create_access_token, verify_access_token
from app.database import engine, get_db
from app.models import Base, User, Post, Comment, Like

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

@app.post("/posts")
def create_post(post: PostCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    new_post = Post(title=post.title, content=post.content, owner_id=user.id)
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    
    return new_post

@app.get("/posts")
def get_posts(db: Session = Depends(get_db)):
    posts = db.query(Post).all()
    return posts

@app.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post

@app.post("/posts/{post_id}/comments")
def create_comment(post_id: int, comment: CommentCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    # Verify user
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Verify post exists
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # Create comment
    new_comment = Comment(content=comment.content, post_id=post.id, user_id=user.id)
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    return new_comment

@app.get("/posts/{post_id}/comments")
def get_comments(post_id: int, db: Session = Depends(get_db)):
    comments = db.query(Comment).filter(Comment.post_id == post_id).all()
    return comments

@app.post("/posts/{post_id}/like")
def like_post(post_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    # Verify user
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Verify post exists
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    # Check if user already liked the post
    like = db.query(Like).filter(Like.post_id == post_id, Like.user_id == user.id).first()
    if like:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already liked this post")
    
    # Create new like
    new_like = Like(post_id=post.id, user_id=user.id)
    db.add(new_like)
    db.commit()
    db.refresh(new_like)
    
    return {"message": "Post liked successfully"}

@app.get("/posts/{post_id}/likes")
def get_likes(post_id: int, db: Session = Depends(get_db)):
    likes_count = db.query(Like).filter(Like.post_id == post_id).count()
    return {"post_id": post_id, "likes": likes_count}
