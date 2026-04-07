from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import os
import time
import click
from werkzeug.utils import secure_filename
from functools import wraps

from extensions import db, login_manager
from models.user import User
from models.job import Job

# Import after app setup to avoid circular import of routes that use db
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
_db_uri = os.environ.get(
    'DATABASE_URI',
    'postgresql://postgres:postgres@localhost:5432/somali_subtitles'
)
if _db_uri.startswith('postgres://'):
    _db_uri = _db_uri.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Gmail SMTP settings for OTP emails
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'teamstudy18@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'uefh lplx ognt tjol')
app.config['MAIL_SMTP_SERVER'] = os.environ.get('MAIL_SMTP_SERVER', 'smtp.gmail.com')
app.config['MAIL_SMTP_PORT'] = int(os.environ.get('MAIL_SMTP_PORT', 587))

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed extensions: audio + video
ALLOWED_AUDIO = {'wav', 'mp3', 'm4a', 'flac', 'ogg', 'aac'}
ALLOWED_VIDEO = {'mp4', 'mkv', 'avi', 'mov', 'webm'}
ALLOWED_EXTENSIONS = ALLOWED_AUDIO | ALLOWED_VIDEO


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) if user_id else None


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask_login import current_user
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# Register blueprints
from routes.auth import auth_bp
app.register_blueprint(auth_bp)

# Lazy import to avoid circular import; admin blueprint registered below after we define it


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Global processing status (per-job status will be added when we wire Job to upload)
processing_status = {
    'is_processing': False,
    'current_file': None,
    'progress': 0,
    'message': '',
    'error': None,
    'job_id': None,
}


@app.cli.command()
def init_db():
    with app.app_context():
        db.create_all()
        print('Database tables created.')


@app.cli.command()
@click.argument('email')
@click.argument('password')
def create_admin(email, password):
    """Create an admin user: flask create-admin <email> <password>"""
    with app.app_context():
        if User.query.filter_by(email=email).first():
            print(f'User {email} already exists.')
            return
        user = User(email=email.strip().lower(), role='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f'Admin user {email} created.')


with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully.")
    except Exception as e:
        print(f"WARNING: db.create_all() failed: {e}")
        print(f"DATABASE_URI starts with: {_db_uri[:30]}...")


@app.route('/setup-admin', methods=['GET', 'POST'])
def setup_admin():
    if User.query.filter_by(role='admin').first():
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        if not email or len(password) < 6:
            flash('Email required and password must be 6+ characters.', 'error')
            return redirect(url_for('setup_admin'))
        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.role = 'admin'
            db.session.commit()
        else:
            user = User(email=email, role='admin')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        flash(f'Admin account created. Log in now.', 'success')
        return redirect(url_for('auth.login'))
    return (
        '<!DOCTYPE html><html><head><title>Setup Admin</title>'
        '<script src="https://cdn.tailwindcss.com"></script></head>'
        '<body class="bg-gray-900 text-gray-200 min-h-screen flex items-center justify-center">'
        '<form method="post" class="bg-gray-800 p-8 rounded-2xl w-full max-w-md space-y-4">'
        '<h1 class="text-2xl font-bold text-center">Create Admin Account</h1>'
        '<input name="email" type="email" placeholder="Email" required'
        ' class="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-white">'
        '<input name="password" type="password" placeholder="Password (6+ chars)" required minlength="6"'
        ' class="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-white">'
        '<button type="submit"'
        ' class="w-full py-3 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-semibold">'
        'Create Admin</button></form></body></html>'
    )


# --- Placeholder history (full implementation in phase 5)
@app.route('/history')
def history():
    from flask_login import login_required, current_user
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login') + '?next=' + url_for('history'))
    jobs = Job.query.filter_by(user_id=current_user.id).order_by(Job.created_at.desc()).all()
    return render_template('history.html', jobs=jobs)


# --- Admin blueprint (placeholder dashboard; full implementation in phase 6)
from flask import Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def require_admin():
    from flask_login import current_user
    if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
        return redirect(url_for('index'))


@admin_bp.route('/')
def dashboard():
    total_jobs = Job.query.count()
    done_jobs = Job.query.filter_by(status='done').count()
    failed_jobs = Job.query.filter_by(status='failed').count()
    total_users = User.query.count()
    return render_template('admin/dashboard.html', total_jobs=total_jobs, done_jobs=done_jobs, failed_jobs=failed_jobs, total_users=total_users)


@admin_bp.route('/users')
def users():
    users_list = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users_list=users_list)


@admin_bp.route('/users/<int:user_id>/toggle-role', methods=['POST'])
def toggle_role(user_id):
    from flask_login import current_user
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin.users'))
    user.role = 'admin' if user.role == 'user' else 'user'
    db.session.commit()
    flash(f'{user.email} is now {user.role}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    from flask_login import current_user
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete yourself.', 'error')
        return redirect(url_for('admin.users'))
    db.session.delete(user)
    db.session.commit()
    flash(f'{user.email} has been deleted.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/files')
def files():
    jobs = Job.query.order_by(Job.created_at.desc()).limit(500).all()
    return render_template('admin/files.html', jobs=jobs)


@admin_bp.route('/files/<int:job_id>/delete', methods=['POST'])
def delete_file(job_id):
    job = Job.query.get_or_404(job_id)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], job.file_path)
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    db.session.delete(job)
    db.session.commit()
    flash(f'Job {job_id} deleted.', 'success')
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


app.register_blueprint(admin_bp)


# --- Main app routes (index, upload, status, download) - will be refactored to use Job in phase 2
import threading

_generator = None

def get_generator():
    global _generator
    if _generator is None:
        from main import SomaliSubtitleGenerator
        _generator = SomaliSubtitleGenerator()
    return _generator


def process_audio_file(relative_path, job_id=None):
    global processing_status
    try:
        processing_status['is_processing'] = True
        processing_status['current_file'] = os.path.basename(relative_path)
        processing_status['progress'] = 0
        processing_status['error'] = None
        processing_status['job_id'] = job_id

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], relative_path)

        output_filename = f"subtitles_{int(time.time())}.srt"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        def on_progress(current, total, msg):
            pct = 5 + int((current / max(total, 1)) * 90)
            processing_status['progress'] = min(pct, 95)
            processing_status['message'] = msg

        processing_status['progress'] = 2
        processing_status['message'] = 'Analyzing media duration...'

        segments = get_generator().generate_subtitles(
            file_path, output_path, progress_cb=on_progress)

        processing_status['progress'] = 100
        processing_status['message'] = 'Subtitles generated successfully!'
        processing_status['output_file'] = output_filename
        if job_id:
            job = Job.query.get(job_id)
            if job:
                job.status = 'done'
                job.segments = [
                    {'start': s['start_sec'], 'end': s['end_sec'],
                     'start_ts': s['start'], 'end_ts': s['end'],
                     'text': s['text']}
                    for s in (segments or [])
                ]
                db.session.commit()
    except Exception as e:
        processing_status['error'] = str(e)
        processing_status['message'] = f'Error: {str(e)}'
        if job_id:
            job = Job.query.get(job_id)
            if job:
                job.status = 'failed'
                db.session.commit()
    finally:
        processing_status['is_processing'] = False


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/create')
def create():
    return render_template('create.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use audio '
                        '(wav, mp3, m4a, flac, ogg, aac) or video '
                        '(mp4, mkv, avi, mov, webm).'}), 400
    if processing_status['is_processing']:
        return jsonify({'error': 'Another file is currently being processed. '
                        'Please wait.'}), 429

    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower()
    is_video = ext in ALLOWED_VIDEO

    from flask_login import current_user
    user_id = current_user.id if current_user.is_authenticated else None
    if user_id:
        user_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, filename)
    else:
        guest_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'guest')
        os.makedirs(guest_dir, exist_ok=True)
        file_path = os.path.join(guest_dir, filename)

    file.save(file_path)
    rel_path = os.path.relpath(file_path, app.config['UPLOAD_FOLDER'])

    job = Job(
        user_id=user_id,
        original_filename=filename,
        file_path=rel_path,
        media_type='video' if is_video else 'audio',
        status='processing'
    )
    db.session.add(job)
    db.session.commit()

    job_id = job.id

    def run_process():
        with app.app_context():
            process_audio_file(rel_path, job_id)

    thread = threading.Thread(target=run_process)
    thread.daemon = True
    thread.start()

    return jsonify({
        'message': 'File uploaded. Processing started.',
        'job_id': job.id
    })


@app.route('/status')
def get_status():
    return jsonify(processing_status)


@app.route('/download/<filename>')
def download_file(filename):
    # Allow download from uploads or subdirs (user_id/ or guest/)
    base = app.config['UPLOAD_FOLDER']
    file_path = os.path.join(base, filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(base)):
        return jsonify({'error': 'Invalid path'}), 403
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_file(file_path, as_attachment=True, download_name=filename)
    return jsonify({'error': 'File not found'}), 404


@app.route('/job/<int:job_id>/media')
def job_media(job_id):
    """Serve the original media file for a job (for editor preview)."""
    from flask_login import current_user
    job = Job.query.get_or_404(job_id)
    if job.user_id and (not current_user.is_authenticated or current_user.id != job.user_id):
        return jsonify({'error': 'Forbidden'}), 403
    path = os.path.join(app.config['UPLOAD_FOLDER'], job.file_path)
    if not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(path, mimetype='application/octet-stream', conditional=True)


@app.route('/editor/<int:job_id>')
def editor(job_id):
    from flask_login import current_user
    job = Job.query.get_or_404(job_id)
    if job.user_id and (not current_user.is_authenticated or current_user.id != job.user_id):
        return redirect(url_for('index'))
    if job.status != 'done':
        return redirect(url_for('history') if current_user.is_authenticated else url_for('create'))
    return render_template('editor.html', job=job)


@app.route('/editor/<int:job_id>/save', methods=['POST'])
def editor_save(job_id):
    from flask_login import current_user
    job = Job.query.get_or_404(job_id)
    if job.user_id and (not current_user.is_authenticated or current_user.id != job.user_id):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    segments = data.get('segments', [])
    if not isinstance(segments, list):
        return jsonify({'error': 'Invalid segments'}), 400
    job.segments = segments
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/job/<int:job_id>/burned')
def download_burned(job_id):
    """Generate and download video with burned-in subtitles. Works for both video and audio jobs."""
    from flask_login import current_user
    import subprocess
    import tempfile
    from io import BytesIO
    from utils.subtitle_formats import segments_to_srt
    job = Job.query.get_or_404(job_id)
    if job.user_id and (not current_user.is_authenticated or current_user.id != job.user_id):
        return jsonify({'error': 'Forbidden'}), 403
    segments = job.segments or []
    if not segments:
        return jsonify({'error': 'No subtitles for this job'}), 404
    media_path = os.path.join(app.config['UPLOAD_FOLDER'], job.file_path)
    if not os.path.isfile(media_path):
        return jsonify({'error': 'Original file not found'}), 404
    base_name = os.path.splitext(job.original_filename)[0]
    srt_path = None
    out_path = None
    work_dir = None
    try:
        # Use a short temp directory without spaces/colons for ffmpeg subtitles filter
        work_dir = tempfile.mkdtemp(prefix='ssai')
        srt_path = os.path.join(work_dir, 'subs.srt')
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(segments_to_srt(segments))
        out_path = os.path.join(work_dir, 'out.mp4')

        if job.media_type == 'video':
            subprocess.run([
                'ffmpeg', '-y', '-i', media_path,
                '-vf', f'subtitles=subs.srt',
                '-c:a', 'copy', out_path
            ], check=True, capture_output=True, timeout=600, cwd=work_dir)
        else:
            max_end = max((s.get('end_sec') or s.get('end') or 0) for s in segments) if segments else 10
            duration = max(max_end + 2, 5)
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', f'color=c=#0b0f19:s=1280x720:d={duration}',
                '-i', media_path,
                '-vf', "subtitles=subs.srt:force_style='Fontsize=22,PrimaryColour=&Hffffff&,Alignment=2,MarginV=60'",
                '-c:v', 'libx264', '-preset', 'fast', '-tune', 'stillimage',
                '-c:a', 'aac', '-b:a', '192k',
                '-shortest', out_path
            ], check=True, capture_output=True, timeout=600, cwd=work_dir)

        if os.path.isfile(out_path):
            with open(out_path, 'rb') as f:
                data = f.read()
            try:
                os.remove(out_path)
            except OSError:
                pass
            return send_file(BytesIO(data), as_attachment=True, download_name=f'{base_name}_subtitles.mp4', mimetype='video/mp4')
        return jsonify({'error': 'Burn-in failed'}), 500
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors='replace') if e.stderr else ''
        # ffmpeg prints banner to stderr; grab the last meaningful lines
        lines = [l.strip() for l in stderr.splitlines() if l.strip()]
        err = '\n'.join(lines[-5:]) if lines else str(e)
        flash(f'Burn-in failed: {err}', 'error')
        return redirect(url_for('editor', job_id=job_id))
    except FileNotFoundError:
        flash('Burn-in failed: ffmpeg not found. Please install ffmpeg and add it to PATH.', 'error')
        return redirect(url_for('editor', job_id=job_id))
    except Exception as e:
        flash(f'Burn-in failed: {e}', 'error')
        return redirect(url_for('editor', job_id=job_id))
    finally:
        if work_dir and os.path.isdir(work_dir):
            import shutil
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except OSError:
                pass


@app.route('/job/<int:job_id>/export')
def export_subtitles(job_id):
    from flask_login import current_user
    from io import BytesIO
    from utils.subtitle_formats import segments_to_srt, segments_to_vtt
    job = Job.query.get_or_404(job_id)
    if job.user_id and (not current_user.is_authenticated or current_user.id != job.user_id):
        return jsonify({'error': 'Forbidden'}), 403
    fmt = request.args.get('format', 'srt').lower()
    if fmt not in ('srt', 'vtt'):
        fmt = 'srt'
    segments = job.segments or []
    if not segments:
        return jsonify({'error': 'No subtitles for this job'}), 404
    base_name = os.path.splitext(job.original_filename)[0]
    if fmt == 'srt':
        content = segments_to_srt(segments)
        filename = f"{base_name}.srt"
        mimetype = 'text/plain'
    else:
        content = segments_to_vtt(segments)
        filename = f"{base_name}.vtt"
        mimetype = 'text/vtt'
    buf = BytesIO(content.encode('utf-8'))
    return send_file(buf, as_attachment=True, download_name=filename, mimetype=mimetype)


@app.route('/batch-export')
def batch_export():
    """Download all completed subtitles for the current user as a ZIP archive."""
    from flask_login import current_user
    from io import BytesIO
    import zipfile
    from utils.subtitle_formats import segments_to_srt, segments_to_vtt

    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    fmt = request.args.get('format', 'srt').lower()
    if fmt not in ('srt', 'vtt'):
        fmt = 'srt'

    jobs = Job.query.filter_by(user_id=current_user.id, status='done').all()
    jobs_with_segments = [j for j in jobs if j.segments]

    if not jobs_with_segments:
        flash('No completed subtitles to export.', 'error')
        return redirect(url_for('history'))

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for job in jobs_with_segments:
            base_name = os.path.splitext(job.original_filename)[0]
            if fmt == 'vtt':
                content = segments_to_vtt(job.segments)
                fname = f"{base_name}.vtt"
            else:
                content = segments_to_srt(job.segments)
                fname = f"{base_name}.srt"
            zf.writestr(fname, content.encode('utf-8'))

    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f'subtitles_{fmt}.zip',
                     mimetype='application/zip')


@app.route('/clear')
def clear_status():
    global processing_status
    processing_status = {
        'is_processing': False,
        'current_file': None,
        'progress': 0,
        'message': '',
        'error': None,
        'job_id': None,
    }
    return jsonify({'message': 'Status cleared'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
