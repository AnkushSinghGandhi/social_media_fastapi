from fastapi import FastAPI, HTTPException, status, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import List
from app.schemas import UserCreate, PostCreate, CommentCreate
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.utils import hash_password, verify_password, create_access_token, verify_access_token
from app.database import engine, get_db
from app.models import Base, User, Post, Comment, Like, Follower, Notification
import redis
from aiosmtplib import SMTP
from email.message import EmailMessage
from app.config import settings

# Initialize Redis client
redis_client = redis.Redis(host="localhost", port=6379, db=0)

description = """
A social media application built with FastAPI that enables user registration, login, and profile management. It features a real-time messaging system using WebSockets, PostgreSQL for data storage, and Redis for caching and rate limiting.
"""

tags_metadata = [
    {
        "name": "Users",
        "description": "Operations with users. The **login** logic is also here.",
        "externalDocs": {
            "description": "Items external docs",
            "url": "https://fastapi.tiangolo.com/",
        },
    },
]

app = FastAPI(
    title="Social Media FastAPI 🚀🚀",
    description=description,
    summary="Tech Stack - FastAPI, PostgressSQL, Reddis",
    version="0.0.1",
    openapi_tags=tags_metadata,
    contact={
        "name": "Ankush Singh Gandhi",
        "url": "http://warriorwhocodes.com",
        "email": "ankushsinghgandhi@gmail.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

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

def create_notification(message: str, user_id: int, db: Session):
    notification = Notification(message=message, user_id=user_id)
    db.add(notification)
    db.commit()
    db.refresh(notification)

    redis_client.publish(f"user_{user_id}_notifications", message)

    return notification

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

async def send_email_background(email_to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = settings.MAIL_FROM
    message["To"] = email_to
    message["Subject"] = subject
    message.set_content(body)

    async with SMTP(hostname=settings.MAIL_SERVER, port=settings.MAIL_PORT, use_tls=settings.MAIL_TLS) as smtp:
        await smtp.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        await smtp.send_message(message)

# Create an instance of the connection manager
manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket)

    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"user_{user_id}_notifications")

    try:
        while True:
            message = pubsub.get_message()
            if message:
                await manager.send_message(message['data'].decode('utf-8'), websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/send-notification/")
async def send_notification(email_to: str, background_tasks: BackgroundTasks):
    # Add the background task for sending the email
    background_tasks.add_task(send_email_background, email_to, "New Notification", "You have a new notification.")
    return {"message": "Notification email is being sent in the background"}

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

    create_notification(f"{user.email} commented on your post", post.user_id, db)

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

    create_notification(f"{user.email} liked your post", post.user_id, db)

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

@app.get("/notifications")
def get_notifications(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    notifications = db.query(Notification).filter(Notification.user_id == user.id).all()
    return notifications
