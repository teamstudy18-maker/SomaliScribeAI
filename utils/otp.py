"""OTP generation and email sending via Gmail SMTP."""
import random
import string
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def generate_otp(length=6):
    """Generate a random numeric OTP code."""
    return ''.join(random.choices(string.digits, k=length))


def send_otp_email(recipient_email, otp_code, purpose='verify'):
    """Send an OTP code to the given email via Gmail SMTP.

    Requires MAIL_USERNAME and MAIL_PASSWORD to be set in the Flask app config
    (or as environment variables).

    Args:
        recipient_email: The email address to send the OTP to.
        otp_code: The OTP code string.
        purpose: 'verify' for registration, 'reset' for password reset.
    """
    from flask import current_app

    sender_email = current_app.config.get('MAIL_USERNAME')
    sender_password = current_app.config.get('MAIL_PASSWORD')

    if not sender_email or not sender_password:
        raise RuntimeError(
            'MAIL_USERNAME and MAIL_PASSWORD must be configured. '
            'Set them as environment variables or in app config.'
        )

    if purpose == 'reset':
        subject = 'SomaliScribe AI – Password Reset Code'
        heading = 'Password Reset'
        body_text = 'You requested a password reset. Use the code below to reset your password.'
    else:
        subject = 'SomaliScribe AI – Email Verification Code'
        heading = 'Email Verification'
        body_text = 'Thank you for signing up! Use the code below to verify your email address.'

    html_body = f"""\
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px;
                background:#111827;border-radius:16px;border:1px solid rgba(255,255,255,0.06);">
        <div style="text-align:center;margin-bottom:20px;">
            <h2 style="color:#a78bfa;margin:0;">{heading}</h2>
        </div>
        <p style="color:#d1d5db;font-size:14px;line-height:1.6;">{body_text}</p>
        <div style="text-align:center;margin:24px 0;">
            <span style="display:inline-block;padding:16px 32px;font-size:32px;font-weight:bold;
                         letter-spacing:8px;color:#ffffff;background:linear-gradient(135deg,#7c3aed,#6d28d9);
                         border-radius:12px;">{otp_code}</span>
        </div>
        <p style="color:#9ca3af;font-size:12px;text-align:center;">
            This code expires in <strong>10 minutes</strong>. Do not share it with anyone.
        </p>
        <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:20px 0;">
        <p style="color:#6b7280;font-size:11px;text-align:center;">
            &copy; 2026 SomaliScribe AI &middot; Made by GroupMatriX
        </p>
    </div>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg.attach(MIMEText(f'Your OTP code is: {otp_code}', 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    smtp_server = current_app.config.get('MAIL_SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(current_app.config.get('MAIL_SMTP_PORT', 587))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())


# ---------------------------------------------------------------------------
# Session-based OTP storage helpers
# ---------------------------------------------------------------------------
OTP_EXPIRY_SECONDS = 600  # 10 minutes


def store_otp(session, otp_code, email, purpose='verify'):
    """Store OTP data in the Flask session."""
    session['otp_data'] = {
        'code': otp_code,
        'email': email,
        'purpose': purpose,
        'created_at': time.time(),
    }


def verify_otp(session, submitted_code, expected_purpose='verify'):
    """Verify submitted OTP against the one stored in session.

    Returns (success: bool, error_message: str | None).
    """
    data = session.get('otp_data')
    if not data:
        return False, 'No OTP request found. Please start over.'
    if data.get('purpose') != expected_purpose:
        return False, 'Invalid OTP session. Please start over.'
    if time.time() - data.get('created_at', 0) > OTP_EXPIRY_SECONDS:
        session.pop('otp_data', None)
        return False, 'OTP has expired. Please request a new one.'
    if data.get('code') != submitted_code.strip():
        return False, 'Invalid OTP code. Please try again.'
    return True, None


def clear_otp(session):
    """Remove OTP data from session."""
    session.pop('otp_data', None)
    session.pop('pending_registration', None)
