from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text)
    profile_pic = db.Column(db.String(255), default='default.png')
    trust_score = db.Column(db.Float, default=5.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    offered_skills = db.relationship('Skill', back_populates='user', foreign_keys='Skill.user_id', 
                                     primaryjoin="and_(User.id==Skill.user_id, Skill.skill_type=='offer')")
    wanted_skills = db.relationship('Skill', back_populates='user', foreign_keys='Skill.user_id',
                                   primaryjoin="and_(User.id==Skill.user_id, Skill.skill_type=='want')")
    
    sent_messages = db.relationship('Message', back_populates='sender', foreign_keys='Message.sender_id')
    sessions_as_teacher = db.relationship('Session', back_populates='teacher', foreign_keys='Session.teacher_id')
    sessions_as_learner = db.relationship('Session', back_populates='learner', foreign_keys='Session.learner_id')
    reviews_given = db.relationship('Review', back_populates='reviewer', foreign_keys='Review.reviewer_id')
    reviews_received = db.relationship('Review', back_populates='reviewee', foreign_keys='Review.reviewee_id')
    complaints_filed = db.relationship('Complaint', back_populates='complainant', foreign_keys='Complaint.complainant_id')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def calculate_trust_score(self):
        reviews = Review.query.filter_by(reviewee_id=self.id).all()
        if not reviews:
            return 5.0
        total = sum(r.rating for r in reviews)
        return round(total / len(reviews), 1)
    
    def update_trust_score(self):
        self.trust_score = self.calculate_trust_score()
        db.session.commit()


class Skill(db.Model):
    __tablename__ = 'skills'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    skill_name = db.Column(db.String(100), nullable=False)
    skill_type = db.Column(db.String(10), nullable=False)
    proficiency_level = db.Column(db.String(50))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='offered_skills', foreign_keys=[user_id])


class Match(db.Model):
    __tablename__ = 'matches'
    
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user1_offers = db.Column(db.String(100))
    user1_wants = db.Column(db.String(100))
    user2_offers = db.Column(db.String(100))
    user2_wants = db.Column(db.String(100))
    match_percentage = db.Column(db.Float)
    is_double_swap = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])


class Session(db.Model):
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    learner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    skill_topic = db.Column(db.String(100), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    status = db.Column(db.String(20), default='scheduled')
    room_id = db.Column(db.String(100), unique=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    teacher = db.relationship('User', back_populates='sessions_as_teacher', foreign_keys=[teacher_id])
    learner = db.relationship('User', back_populates='sessions_as_learner', foreign_keys=[learner_id])


class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User', back_populates='sent_messages', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Review(db.Model):
    __tablename__ = 'reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'))
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    reviewer = db.relationship('User', back_populates='reviews_given', foreign_keys=[reviewer_id])
    reviewee = db.relationship('User', back_populates='reviews_received', foreign_keys=[reviewee_id])


class Complaint(db.Model):
    __tablename__ = 'complaints'
    
    id = db.Column(db.Integer, primary_key=True)
    complainant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    complained_against_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    complainant = db.relationship('User', back_populates='complaints_filed', foreign_keys=[complainant_id])
    complained_against = db.relationship('User', foreign_keys=[complained_against_id])
