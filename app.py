import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta
import secrets
from models import db, User, Skill, Match, Session, Message, Review, Complaint

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///swapp.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

csrf = CSRFProtect(app)
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        bio = request.form.get('bio', '')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email, bio=bio)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    current_user.update_trust_score()
    
    matches = Match.query.filter(
        (Match.user1_id == current_user.id) | (Match.user2_id == current_user.id)
    ).order_by(Match.match_percentage.desc()).limit(10).all()
    
    upcoming_sessions = Session.query.filter(
        ((Session.teacher_id == current_user.id) | (Session.learner_id == current_user.id)) &
        (Session.scheduled_time > datetime.utcnow()) &
        (Session.status == 'scheduled')
    ).order_by(Session.scheduled_time).all()
    
    unread_messages = Message.query.filter_by(
        receiver_id=current_user.id, 
        is_read=False
    ).count()
    
    return render_template('dashboard.html', 
                         matches=matches, 
                         sessions=upcoming_sessions,
                         unread_count=unread_messages)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', '')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    offered_skills = Skill.query.filter_by(user_id=current_user.id, skill_type='offer').all()
    wanted_skills = Skill.query.filter_by(user_id=current_user.id, skill_type='want').all()
    
    return render_template('profile.html', 
                         offered_skills=offered_skills,
                         wanted_skills=wanted_skills)

@app.route('/add_skill', methods=['POST'])
@login_required
def add_skill():
    skill_name = request.form.get('skill_name')
    skill_type = request.form.get('skill_type')
    proficiency = request.form.get('proficiency', '')
    description = request.form.get('description', '')
    
    if skill_type not in ['offer', 'want']:
        flash('Invalid skill type', 'danger')
        return redirect(url_for('profile'))
    
    skill = Skill(
        user_id=current_user.id,
        skill_name=skill_name,
        skill_type=skill_type,
        proficiency_level=proficiency,
        description=description
    )
    db.session.add(skill)
    db.session.commit()
    
    if skill_type == 'offer':
        find_matches_for_user(current_user.id)
    
    flash(f'Skill "{skill_name}" added successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/delete_skill/<int:skill_id>', methods=['POST'])
@login_required
def delete_skill(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    if skill.user_id != current_user.id:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('profile'))
    
    db.session.delete(skill)
    db.session.commit()
    flash('Skill deleted successfully!', 'success')
    return redirect(url_for('profile'))

def find_matches_for_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return
    
    user_offers = Skill.query.filter_by(user_id=user_id, skill_type='offer').all()
    user_wants = Skill.query.filter_by(user_id=user_id, skill_type='want').all()
    
    all_users = User.query.filter(User.id != user_id).all()
    
    for other_user in all_users:
        other_offers = Skill.query.filter_by(user_id=other_user.id, skill_type='offer').all()
        other_wants = Skill.query.filter_by(user_id=other_user.id, skill_type='want').all()
        
        match_score = 0
        total_possible = 0
        matched_skills = []
        is_double = False
        
        for my_want in user_wants:
            total_possible += 1
            for their_offer in other_offers:
                if my_want.skill_name.lower() == their_offer.skill_name.lower():
                    match_score += 1
                    matched_skills.append({
                        'i_want': my_want.skill_name,
                        'they_offer': their_offer.skill_name
                    })
        
        for my_offer in user_offers:
            total_possible += 1
            for their_want in other_wants:
                if my_offer.skill_name.lower() == their_want.skill_name.lower():
                    match_score += 1
                    is_double = True
        
        if match_score > 0 and total_possible > 0:
            match_percentage = (match_score / total_possible) * 100
            
            existing_match = Match.query.filter(
                ((Match.user1_id == user_id) & (Match.user2_id == other_user.id)) |
                ((Match.user1_id == other_user.id) & (Match.user2_id == user_id))
            ).first()
            
            if not existing_match:
                user1_offer_str = ', '.join([s.skill_name for s in user_offers][:3])
                user1_want_str = ', '.join([s.skill_name for s in user_wants][:3])
                user2_offer_str = ', '.join([s.skill_name for s in other_offers][:3])
                user2_want_str = ', '.join([s.skill_name for s in other_wants][:3])
                
                match = Match(
                    user1_id=user_id,
                    user2_id=other_user.id,
                    user1_offers=user1_offer_str,
                    user1_wants=user1_want_str,
                    user2_offers=user2_offer_str,
                    user2_wants=user2_want_str,
                    match_percentage=round(match_percentage, 1),
                    is_double_swap=is_double
                )
                db.session.add(match)
    
    db.session.commit()

@app.route('/matches')
@login_required
def matches():
    all_matches = Match.query.filter(
        (Match.user1_id == current_user.id) | (Match.user2_id == current_user.id)
    ).order_by(Match.match_percentage.desc()).all()
    
    return render_template('matches.html', matches=all_matches)

@app.route('/schedule_session/<int:match_id>', methods=['GET', 'POST'])
@login_required
def schedule_session(match_id):
    match = Match.query.get_or_404(match_id)
    
    if match.user1_id == current_user.id:
        other_user = match.user2
    else:
        other_user = match.user1
    
    if request.method == 'POST':
        skill_topic = request.form.get('skill_topic')
        scheduled_date = request.form.get('scheduled_date')
        scheduled_time = request.form.get('scheduled_time')
        duration = int(request.form.get('duration', 60))
        notes = request.form.get('notes', '')
        
        datetime_str = f"{scheduled_date} {scheduled_time}"
        scheduled_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
        
        room_id = secrets.token_urlsafe(16)
        
        session = Session(
            teacher_id=other_user.id,
            learner_id=current_user.id,
            skill_topic=skill_topic,
            scheduled_time=scheduled_datetime,
            duration_minutes=duration,
            room_id=room_id,
            notes=notes
        )
        db.session.add(session)
        db.session.commit()
        
        flash('Session scheduled successfully!', 'success')
        return redirect(url_for('sessions'))
    
    return render_template('schedule_session.html', match=match, other_user=other_user)

@app.route('/sessions')
@login_required
def sessions():
    my_sessions = Session.query.filter(
        (Session.teacher_id == current_user.id) | (Session.learner_id == current_user.id)
    ).order_by(Session.scheduled_time.desc()).all()
    
    return render_template('sessions.html', sessions=my_sessions)

@app.route('/classroom/<int:session_id>')
@login_required
def classroom(session_id):
    session = Session.query.get_or_404(session_id)
    
    if session.teacher_id != current_user.id and session.learner_id != current_user.id:
        flash('You are not authorized to access this classroom', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('classroom.html', session=session)

@app.route('/messages')
@login_required
def messages():
    conversations = db.session.query(User).join(
        Message, 
        ((Message.sender_id == User.id) & (Message.receiver_id == current_user.id)) |
        ((Message.receiver_id == User.id) & (Message.sender_id == current_user.id))
    ).distinct().all()
    
    return render_template('messages.html', conversations=conversations)

@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    other_user = User.query.get_or_404(user_id)
    
    chat_messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at).all()
    
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    return render_template('chat.html', other_user=other_user, messages=chat_messages)

@app.route('/review/<int:session_id>', methods=['GET', 'POST'])
@login_required
def review(session_id):
    session = Session.query.get_or_404(session_id)
    
    if session.teacher_id != current_user.id and session.learner_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        rating = int(request.form.get('rating'))
        comment = request.form.get('comment', '')
        
        reviewee_id = session.teacher_id if current_user.id == session.learner_id else session.learner_id
        
        review_obj = Review(
            reviewer_id=current_user.id,
            reviewee_id=reviewee_id,
            session_id=session_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review_obj)
        
        reviewee = User.query.get(reviewee_id)
        reviewee.update_trust_score()
        
        db.session.commit()
        
        flash('Review submitted successfully!', 'success')
        return redirect(url_for('sessions'))
    
    return render_template('review.html', session=session)

@app.route('/complaints', methods=['GET', 'POST'])
@login_required
def complaints():
    if request.method == 'POST':
        complained_against_id = request.form.get('complained_against_id')
        category = request.form.get('category')
        description = request.form.get('description')
        
        complaint = Complaint(
            complainant_id=current_user.id,
            complained_against_id=int(complained_against_id) if complained_against_id else None,
            category=category,
            description=description,
            status='pending'
        )
        db.session.add(complaint)
        db.session.commit()
        
        flash('Complaint submitted successfully. Our team will review it.', 'success')
        return redirect(url_for('dashboard'))
    
    my_complaints = Complaint.query.filter_by(complainant_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    all_users = User.query.filter(User.id != current_user.id).all()
    
    return render_template('complaints.html', my_complaints=my_complaints, all_users=all_users)

@socketio.on('send_message')
def handle_send_message(data):
    receiver_id = data['receiver_id']
    content = data['content']
    
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content
    )
    db.session.add(message)
    db.session.commit()
    
    emit('receive_message', {
        'sender_id': current_user.id,
        'sender_name': current_user.username,
        'content': content,
        'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f'user_{receiver_id}')
    
    emit('receive_message', {
        'sender_id': current_user.id,
        'sender_name': current_user.username,
        'content': content,
        'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f'user_{current_user.id}')

@socketio.on('join_user_room')
def handle_join_user_room():
    room = f'user_{current_user.id}'
    join_room(room)

@socketio.on('join_classroom')
def handle_join_classroom(data):
    room = data['room_id']
    join_room(room)
    emit('user_joined', {
        'user_id': current_user.id,
        'username': current_user.username
    }, room=room)

@socketio.on('leave_classroom')
def handle_leave_classroom(data):
    room = data['room_id']
    leave_room(room)
    emit('user_left', {
        'user_id': current_user.id,
        'username': current_user.username
    }, room=room)

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    room = data['room_id']
    emit('webrtc_signal', {
        'signal': data['signal'],
        'sender_id': current_user.id
    }, room=room, include_self=False)

@socketio.on('classroom_chat')
def handle_classroom_chat(data):
    room = data['room_id']
    emit('classroom_chat_message', {
        'user_id': current_user.id,
        'username': current_user.username,
        'message': data['message'],
        'timestamp': datetime.utcnow().strftime('%H:%M:%S')
    }, room=room)

if __name__ == '__main__':
    #start
    from app import app
    app.run(host='0.0.0.0', port=5000)
    #new
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

