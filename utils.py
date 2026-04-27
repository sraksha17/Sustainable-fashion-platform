import hashlib
import os
from datetime import datetime
from functools import wraps
from flask import session, redirect, url_for
from models import get_db

def hash_password(password):
    """Hash password with SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator to require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def user_has_role(user, role):
    """Check if user has a specific role."""
    roles = user.get('roles', [])
    # Backward compatibility: if user has user_type field and roles empty
    if not roles and 'user_type' in user:
        roles = [user['user_type']]
    return role in roles

def get_user_by_email(email):
    """Retrieve user document by email."""
    db = get_db()
    return db.users.find_one({'email': email})

def create_notification(user_email, message, notif_type='info'):
    """Create a notification document."""
    db = get_db()
    notification = {
        'user_email': user_email,
        'message': message,
        'type': notif_type,
        'read': False,
        'created_at': datetime.utcnow().isoformat()
    }
    db.notifications.insert_one(notification)
    return True