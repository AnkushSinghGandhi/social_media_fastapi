from fastapi import FastAPI, HTTPException, status, Depends
from app.schemas import UserCreate, PostCreate, CommentCreate
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.utils import hash_password, verify_password, create_access_token, verify_access_token
from app.database import engine, get_db
from app.models import Base, User, Post, Comment, Like, Follower



app = FastAPI()

Base.metadata.create_all(bind=engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def admin_required(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()

    if not user or user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")
    
    return user

@app.post("/register", tags=['Users'])
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

@app.post("/login", tags=['Users'])
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

@app.get("/users/me", tags=['Users'])
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

@app.post("/posts", tags=['Posts'])
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

@app.get("/posts", tags=['Posts'])
def get_posts(db: Session = Depends(get_db)):
    posts = db.query(Post).all()
    return posts

@app.get("/posts/{post_id}", tags=['Posts'])
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post

@app.post("/posts/{post_id}/comments", tags=['Comments & Likes'])
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

@app.get("/posts/{post_id}/comments", tags=['Comments & Likes'])
def get_comments(post_id: int, db: Session = Depends(get_db)):
    comments = db.query(Comment).filter(Comment.post_id == post_id).all()
    return comments

@app.post("/posts/{post_id}/like", tags=['Comments & Likes'])
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

@app.get("/posts/{post_id}/likes", tags=['Comments & Likes'])
def get_likes(post_id: int, db: Session = Depends(get_db)):
    likes_count = db.query(Like).filter(Like.post_id == post_id).count()
    return {"post_id": post_id, "likes": likes_count}

@app.post("/users/{user_id}/follow", tags=['Follow & Unfollow'])
def follow_user(user_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    # Verify user
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    follower = db.query(User).filter(User.email == user_email).first()

    if not follower:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follower user not found")

    # Check if user being followed exists
    followed = db.query(User).filter(User.id == user_id).first()
    if not followed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Followed user not found")

    # Check if already following
    existing_follow = db.query(Follower).filter(Follower.follower_id == follower.id, Follower.followed_id == followed.id).first()
    if existing_follow:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already following this user")

    # Create follow relationship
    new_follow = Follower(follower_id=follower.id, followed_id=followed.id)
    db.add(new_follow)
    db.commit()
    db.refresh(new_follow)

    return {"message": "You are now following this user"}

@app.get("/users/{user_id}/followers", tags=['Follow & Unfollow'])
def get_followers(user_id: int, db: Session = Depends(get_db)):
    followers = db.query(Follower).filter(Follower.followed_id == user_id).all()
    return followers

@app.get("/users/{user_id}/following", tags=['Follow & Unfollow'])
def get_following(user_id: int, db: Session = Depends(get_db)):
    following = db.query(Follower).filter(Follower.follower_id == user_id).all()
    return following

@app.get("/posts/following", tags=['Follow & Unfollow'])
def get_following_posts(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Get list of users the current user is following
    following = db.query(Follower).filter(Follower.follower_id == user.id).all()
    following_ids = [f.followed_id for f in following]

    # Fetch posts from those users
    posts = db.query(Post).filter(Post.user_id.in_(following_ids)).all()
    return posts

@app.delete("/users/{user_id}/unfollow", tags=['Follow & Unfollow'])
def unfollow_user(user_id: int, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    # Verify user
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_email = payload.get("sub")
    follower = db.query(User).filter(User.email == user_email).first()

    if not follower:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follower user not found")

    # Check if follow relationship exists
    follow_relationship = db.query(Follower).filter(Follower.follower_id == follower.id, Follower.followed_id == user_id).first()

    if not follow_relationship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You are not following this user")

    # Remove follow relationship
    db.delete(follow_relationship)
    db.commit()

    return {"message": "You have unfollowed this user"}

@app.delete("/admin/posts/{post_id}", tags=['Admin'])
def delete_post(post_id: int, db: Session = Depends(get_db), user: User = Depends(admin_required)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    db.delete(post)
    db.commit()
    return {"message": "Post deleted successfully"}