"""Authentication routes: register, login, logout, OTP verification, forgot password."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models.user import User
from utils.otp import generate_otp, send_otp_email, store_otp, verify_otp, clear_otp

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ---------------------------------------------------------------------------
# Registration with OTP email verification
# ---------------------------------------------------------------------------

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

        # Store registration data temporarily and send OTP
        otp_code = generate_otp()
        try:
            send_otp_email(email, otp_code, purpose='verify')
        except Exception as e:
            flash(f'Failed to send verification email: {e}', 'error')
            return render_template('register.html')

        session['pending_registration'] = {
            'email': email,
            'password': password,
        }
        store_otp(session, otp_code, email, purpose='verify')
        flash('A verification code has been sent to your email.', 'success')
        return redirect(url_for('auth.verify_register_otp'))
    return render_template('register.html')


@auth_bp.route('/verify-register', methods=['GET', 'POST'])
def verify_register_otp():
    """Verify the OTP sent during registration."""
    pending = session.get('pending_registration')
    if not pending:
        flash('No pending registration. Please sign up first.', 'error')
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        submitted = request.form.get('otp', '').strip()
        ok, err = verify_otp(session, submitted, expected_purpose='verify')
        if not ok:
            flash(err, 'error')
            return render_template('verify_otp.html', email=pending['email'], purpose='verify')

        # OTP valid – create the account
        email = pending['email']
        password = pending['password']
        if User.query.filter_by(email=email).first():
            clear_otp(session)
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('auth.register'))

        user = User(email=email, role='user')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        clear_otp(session)
        flash('Email verified! Account created. You can log in now.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('verify_otp.html', email=pending['email'], purpose='verify')


@auth_bp.route('/resend-otp')
def resend_otp():
    """Resend the OTP for the current pending flow."""
    otp_data = session.get('otp_data')
    if not otp_data:
        flash('No pending verification. Please start over.', 'error')
        return redirect(url_for('auth.register'))

    email = otp_data['email']
    purpose = otp_data['purpose']
    otp_code = generate_otp()
    try:
        send_otp_email(email, otp_code, purpose=purpose)
    except Exception as e:
        flash(f'Failed to resend email: {e}', 'error')
    else:
        store_otp(session, otp_code, email, purpose=purpose)
        flash('A new verification code has been sent.', 'success')

    if purpose == 'reset':
        return redirect(url_for('auth.verify_reset_otp'))
    return redirect(url_for('auth.verify_register_otp'))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Forgot password (OTP-based)
# ---------------------------------------------------------------------------

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        if not email:
            flash('Email is required.', 'error')
            return render_template('forgot_password.html')
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with that email.', 'error')
            return render_template('forgot_password.html')

        otp_code = generate_otp()
        try:
            send_otp_email(email, otp_code, purpose='reset')
        except Exception as e:
            flash(f'Failed to send reset email: {e}', 'error')
            return render_template('forgot_password.html')

        store_otp(session, otp_code, email, purpose='reset')
        flash('A reset code has been sent to your email.', 'success')
        return redirect(url_for('auth.verify_reset_otp'))
    return render_template('forgot_password.html')


@auth_bp.route('/verify-reset', methods=['GET', 'POST'])
def verify_reset_otp():
    """Verify the OTP sent for password reset."""
    otp_data = session.get('otp_data')
    if not otp_data or otp_data.get('purpose') != 'reset':
        flash('No pending password reset. Please start over.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        submitted = request.form.get('otp', '').strip()
        ok, err = verify_otp(session, submitted, expected_purpose='reset')
        if not ok:
            flash(err, 'error')
            return render_template('verify_otp.html', email=otp_data['email'], purpose='reset')

        # OTP valid – allow password reset
        session['reset_email'] = otp_data['email']
        clear_otp(session)
        return redirect(url_for('auth.reset_password'))

    return render_template('verify_otp.html', email=otp_data['email'], purpose='reset')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_email')
    if not email:
        flash('No verified reset session. Please start over.', 'error')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''
        if not password or len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('reset_password.html', email=email)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', email=email)
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Account not found.', 'error')
            session.pop('reset_email', None)
            return redirect(url_for('auth.forgot_password'))
        user.set_password(password)
        db.session.commit()
        session.pop('reset_email', None)
        flash('Password has been reset. You can log in now.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_password.html', email=email)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth_bp.route('/logout')
def logout():
    logout_user()
    session.pop('guest_mode', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
