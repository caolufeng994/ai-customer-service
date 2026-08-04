"""
Authentication service
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest
from app.utils.auth import generate_salt, hash_password, verify_password, create_access_token
from app.core.exceptions import ValidationError, AuthenticationError, NotFoundError


class AuthService:
    """Authentication business logic"""
    
    @staticmethod
    def register(db: Session, request: RegisterRequest) -> User:
        """Register a new user"""
        # Validate phone or email
        if not request.phone and not request.email:
            raise ValidationError("Either phone or email must be provided")
        
        # Check if user already exists.
        # Only match fields that are actually provided: `User.email == None` would
        # degenerate into `email IS NULL` and falsely match every row whose email is
        # empty, so a phone-only registration could be rejected as "Email already
        # registered". Build the OR conditions dynamically from the provided fields.
        conditions = []
        if request.phone:
            conditions.append(User.phone == request.phone)
        if request.email:
            conditions.append(User.email == request.email)
        existing_user = db.query(User).filter(or_(*conditions)).first()
        
        if existing_user:
            if existing_user.phone == request.phone:
                raise ValidationError("Phone number already registered")
            if existing_user.email == request.email:
                raise ValidationError("Email already registered")
        
        # Create new user
        salt = generate_salt()
        password_hash = hash_password(request.password, salt)
        
        user = User(
            phone=request.phone,
            email=request.email,
            password_hash=password_hash,
            salt=salt
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return user
    
    @staticmethod
    def login(db: Session, request: LoginRequest) -> tuple[User, str]:
        """Login user and return token"""
        # Find user by phone or email
        user = db.query(User).filter(
            (User.phone == request.phone_or_email) | (User.email == request.phone_or_email)
        ).first()
        
        if not user:
            raise AuthenticationError("Invalid phone/email or password")
        
        # Verify password
        if not verify_password(request.password, user.salt, user.password_hash):
            raise AuthenticationError("Invalid phone/email or password")
        
        # Create access token
        token_data = {"sub": str(user.id), "phone": user.phone, "email": user.email}
        token = create_access_token(token_data)
        
        return user, token
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """Get user by ID"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundError("User not found")
        return user
