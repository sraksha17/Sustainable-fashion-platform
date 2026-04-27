from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from utils import hash_password, get_user_by_email, user_has_role
from models import get_db
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed = hash_password(password)
        user = get_user_by_email(email)
        if user and user['password'] == hashed:
            session['user_email'] = email
            session['user_name'] = user.get('name', '')
            session['roles'] = user.get('roles', [])
            # Set active role to the first role in the list (or donor if present)
            if 'donor' in session['roles']:
                session['active_role'] = 'donor'
            elif 'designer' in session['roles']:
                session['active_role'] = 'designer'
            elif 'buyer' in session['roles']:
                session['active_role'] = 'buyer'
            else:
                session['active_role'] = None
            # Update last login
            db = get_db()
            db.users.update_one({'email': email}, {'$set': {'last_login': datetime.utcnow()}})
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        hashed = hash_password(password)
        db = get_db()
        # Check if user exists
        if db.users.find_one({'email': email}):
            flash('Email already registered', 'danger')
            return redirect(url_for('auth.signup'))
        # Create new user with all three roles by default
        new_user = {
            'name': name,
            'email': email,
            'password': hashed,
            'roles': ['donor', 'designer', 'buyer'],  # All roles
            'user_type': 'donor',  # For backward compatibility
            'reward_points': 0,
            'total_donations': 0,
            'created_at': datetime.utcnow(),
            'last_login': datetime.utcnow()
        }
        db.users.insert_one(new_user)
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('signup.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/switch-role/<role>')
def switch_role(role):
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))
    if role in session.get('roles', []):
        session['active_role'] = role
    return redirect(url_for('dashboard'))