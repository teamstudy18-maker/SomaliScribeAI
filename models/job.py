from extensions import db


class Job(db.Model):
    __tablename__ = 'job'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    original_filename = db.Column(db.String(512), nullable=False)
    file_path = db.Column(db.String(1024), nullable=False)
    media_type = db.Column(db.String(10), nullable=False, default='audio')
    status = db.Column(db.String(20), nullable=False, default='pending')
    segments = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    burned_video_path = db.Column(db.String(1024), nullable=True)
