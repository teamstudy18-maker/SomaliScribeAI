"""Admin blueprint: dashboard, users, files, stats."""
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import current_user

from extensions import db
from models.user import User
from models.job import Job
from utils.subtitle_formats import segments_to_srt

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required():
    if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
        return redirect(url_for('auth.login'))
    return None


@admin_bp.before_request
def require_admin():
    r = admin_required()
    if r is not None:
        return r


@admin_bp.route('/')
def dashboard():
    total_jobs = Job.query.count()
    done_jobs = Job.query.filter_by(status='done').count()
    total_users = User.query.count()
    return render_template('admin/dashboard.html', total_jobs=total_jobs, done_jobs=done_jobs, total_users=total_users)


@admin_bp.route('/users', methods=['GET', 'POST'])
def users():
    users_list = User.query.order_by(User.id).all()
    return render_template('admin/users.html', users=users_list)


@admin_bp.route('/users/<int:user_id>/toggle-role', methods=['POST'])
def toggle_role(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        return redirect(url_for('admin.users'))
    u.role = 'user' if u.role == 'admin' else 'admin'
    db.session.commit()
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        return redirect(url_for('admin.users'))
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('admin.users'))


@admin_bp.route('/files')
def files():
    jobs = Job.query.order_by(Job.id.desc()).all()
    return render_template('admin/files.html', jobs=jobs)


@admin_bp.route('/files/<int:job_id>/delete', methods=['POST'])
def delete_file(job_id):
    job = Job.query.get_or_404(job_id)
    import os
    from flask import current_app
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], job.file_path)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    db.session.delete(job)
    db.session.commit()
    return redirect(url_for('admin.files'))


@admin_bp.route('/stats')
def stats():
    jobs = Job.query.filter_by(status='done').all()
    total_segments = 0
    total_duration_sec = 0.0
    for j in jobs:
        segs = j.segments or []
        total_segments += len(segs)
        for s in segs:
            try:
                end = float(s.get('end_sec') or s.get('end') or 0)
                start = float(s.get('start_sec') or s.get('start') or 0)
                total_duration_sec += max(end - start, 0)
            except (TypeError, ValueError):
                continue
    total_duration_min = round(total_duration_sec / 60, 1)
    avg_segments = round(total_segments / len(jobs), 1) if jobs else 0
    return render_template('admin/stats.html', jobs=jobs, total_segments=total_segments,
                           total_duration_min=total_duration_min, avg_segments=avg_segments)
