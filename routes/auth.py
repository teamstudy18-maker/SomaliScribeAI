"""Authentication routes: register, login, logout."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models.user import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''
        if not email:
            flash('Email is required.', 'error')
            return render_template('register.html')
        if not password or len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'error')
            return render_template('register.html')
        user = User(email=email, role='user')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Account created. You can log in now.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html')
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return render_template('login.html')
        login_user(user, remember=bool(request.form.get('remember')))
        session.pop('guest_mode', None)
        next_page = request.args.get('next') or url_for('index')
        return redirect(next_page)
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    logout_user()
    session.pop('guest_mode', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
