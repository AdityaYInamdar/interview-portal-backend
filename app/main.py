"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import socketio

from datetime import datetime
from app.core.config import settings
from app.core.supabase import get_supabase_service
from app.api.v1 import auth, interviews, candidates, companies, interviewers, code, users, tests, questions_api, sessions


# Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=settings.cors_origins_list,
    logger=True,
    engineio_logger=True
)

# Socket.IO app
socket_app = socketio.ASGIApp(
    socketio_server=sio,
    other_asgi_app=None,
)

# In-memory registry: room_id -> list of participant dicts
# Each participant: { sid, userId, userName, userRole }
room_participants: dict[str, list[dict]] = {}
# Reverse map: sid -> { roomId, userId }
sid_to_info: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for the application."""
    # Startup
    print("🚀 Starting Interview Portal API...")
    print(f"📝 Environment: {settings.ENVIRONMENT}")
    print(f"🔒 CORS Origins: {settings.cors_origins_list}")
    
    yield
    
    # Shutdown
    print("👋 Shutting down Interview Portal API...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Remote Interview Platform API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.DEBUG else "An error occurred"
        }
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Interview Portal API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


# Include API routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(interviews.router, prefix=settings.API_V1_PREFIX)
app.include_router(candidates.router, prefix=settings.API_V1_PREFIX)
app.include_router(companies.router, prefix=settings.API_V1_PREFIX)
app.include_router(interviewers.router, prefix=settings.API_V1_PREFIX)
app.include_router(code.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
# Testing platform routes
app.include_router(tests.router, prefix=settings.API_V1_PREFIX)
app.include_router(questions_api.router, prefix=settings.API_V1_PREFIX)
app.include_router(sessions.router, prefix=settings.API_V1_PREFIX)

# Mount Socket.IO
app.mount("/socket.io", socket_app)


# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    print(f"🔌 Client connected: {sid}")
    await sio.emit('connected', {'sid': sid}, room=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    print(f"🔌 Client disconnected: {sid}")
    # Remove from participant registry and notify room
    info = sid_to_info.pop(sid, None)
    if info:
        room_id = info.get('roomId')
        user_id = info.get('userId')
        user_name = info.get('userName')
        if room_id and room_id in room_participants:
            room_participants[room_id] = [
                p for p in room_participants[room_id] if p['sid'] != sid
            ]
            await sio.emit(
                'user-left',
                {'userId': user_id, 'userName': user_name},
                room=room_id
            )


@sio.event
async def join_room(sid, data):
    """
    Handle joining an interview room.
    
    Data: {
        "room_id": str,
        "user_id": str,
        "user_name": str,
        "role": str
    }
    """
    room_id = data.get('room_id')
    user_id = data.get('user_id')
    user_name = data.get('user_name')
    role = data.get('role')
    
    if not room_id:
        return
    
    # Join the room
    sio.enter_room(sid, room_id)
    
    print(f"👤 User {user_name} ({role}) joined room {room_id}")
    
    # Notify others in the room
    await sio.emit(
        'user_joined',
        {
            'user_id': user_id,
            'user_name': user_name,
            'role': role,
            'timestamp': datetime.utcnow().isoformat()
        },
        room=room_id,
        skip_sid=sid
    )
    
    # Send confirmation to the user
    await sio.emit('joined_room', {'room_id': room_id}, room=sid)


@sio.event
async def leave_room(sid, data):
    """Handle leaving an interview room."""
    room_id = data.get('room_id')
    user_id = data.get('user_id')
    user_name = data.get('user_name')
    
    if not room_id:
        return
    
    # Leave the room
    sio.leave_room(sid, room_id)
    
    print(f"👤 User {user_name} left room {room_id}")
    
    # Notify others in the room
    await sio.emit(
        'user_left',
        {
            'user_id': user_id,
            'user_name': user_name,
            'timestamp': datetime.utcnow().isoformat()
        },
        room=room_id
    )


@sio.event
async def code_change(sid, data):
    """
    Handle code editor changes.
    
    Data: {
        "room_id": str,
        "user_id": str,
        "code": str,
        "language": str,
        "cursor_position": dict
    }
    """
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    # Broadcast to all users in the room except sender
    await sio.emit('code_change', data, room=room_id, skip_sid=sid)


@sio.event
async def cursor_position(sid, data):
    """Handle cursor position updates in code editor."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('cursor_position', data, room=room_id, skip_sid=sid)


@sio.event
async def code_execution(sid, data):
    """Handle code execution requests."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    # Broadcast execution request
    await sio.emit('code_execution', data, room=room_id)


@sio.event
async def code_execution_result(sid, data):
    """Broadcast code execution results."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('code_execution_result', data, room=room_id)


@sio.event
async def whiteboard_update(sid, data):
    """Handle whiteboard updates."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('whiteboard_update', data, room=room_id, skip_sid=sid)


@sio.event
async def whiteboard_clear(sid, data):
    """Handle whiteboard clear."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('whiteboard_clear', data, room=room_id)


@sio.event
async def chat_message(sid, data):
    """
    Handle chat messages.
    
    Data: {
        "room_id": str,
        "user_id": str,
        "user_name": str,
        "message": str
    }
    """
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    # Add timestamp
    data['timestamp'] = datetime.utcnow().isoformat()
    
    # Broadcast to all in room
    await sio.emit('chat_message', data, room=room_id)


@sio.event
async def webrtc_offer(sid, data):
    """Handle WebRTC offer."""
    room_id = data.get('room_id')
    target_id = data.get('target_id')
    
    if not room_id or not target_id:
        return
    
    # Forward to specific user
    await sio.emit('webrtc_offer', data, room=room_id)


@sio.event
async def webrtc_answer(sid, data):
    """Handle WebRTC answer."""
    room_id = data.get('room_id')
    target_id = data.get('target_id')
    
    if not room_id or not target_id:
        return
    
    await sio.emit('webrtc_answer', data, room=room_id)


@sio.event
async def webrtc_ice_candidate(sid, data):
    """Handle WebRTC ICE candidate."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('webrtc_ice_candidate', data, room=room_id, skip_sid=sid)


@sio.event
async def start_recording(sid, data):
    """Handle recording start."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('start_recording', data, room=room_id)


@sio.event
async def stop_recording(sid, data):
    """Handle recording stop."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    await sio.emit('stop_recording', data, room=room_id)


@sio.event
async def interview_start(sid, data):
    """Handle interview start event."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    data['timestamp'] = datetime.utcnow().isoformat()
    await sio.emit('interview_start', data, room=room_id)


@sio.event
async def interview_end(sid, data):
    """Handle interview end event."""
    room_id = data.get('room_id')
    
    if not room_id:
        return
    
    data['timestamp'] = datetime.utcnow().isoformat()
    await sio.emit('interview_end', data, room=room_id)


@sio.on('join-interview')
async def join_interview(sid, data):
    """
    Handle user joining an interview room.
    Enhanced version with user tracking.
    
    Data: {
        "interviewId": str,
        "userId": str,
        "userName": str,
        "userRole": str
    }
    """
    interview_id = data.get('interviewId')
    user_id = data.get('userId')
    user_name = data.get('userName')
    user_role = data.get('userRole')
    
    if not interview_id:
        return
    
    # Join the interview room
    await sio.enter_room(sid, interview_id)
    
    print(f"✅ {user_name} ({user_role}) joined interview {interview_id}")
    
    # Register participant
    participant = {
        'sid': sid,
        'userId': user_id,
        'userName': user_name,
        'userRole': user_role
    }
    if interview_id not in room_participants:
        room_participants[interview_id] = []
    # Remove stale entry for same userId if rejoining
    room_participants[interview_id] = [
        p for p in room_participants[interview_id] if p['userId'] != user_id
    ]
    room_participants[interview_id].append(participant)
    sid_to_info[sid] = {'roomId': interview_id, 'userId': user_id, 'userName': user_name}
    
    # Send existing participants list to the newly joined user (excluding themselves)
    existing = [
        {'userId': p['userId'], 'userName': p['userName'], 'userRole': p['userRole']}
        for p in room_participants[interview_id]
        if p['userId'] != user_id
    ]
    await sio.emit('participants-list', {'participants': existing}, room=sid)
    
    # Notify ALL in the room (including the new joiner) about the new user
    await sio.emit(
        'user-joined',
        {
            'userId': user_id,
            'userName': user_name,
            'userRole': user_role,
            'timestamp': datetime.utcnow().isoformat()
        },
        room=interview_id
    )

    # ── Track join timestamp in DB (best-effort) ──────────────────────────────
    try:
        supabase = get_supabase_service()
        now_iso = datetime.utcnow().isoformat()
        if user_role in ('interviewer', 'admin'):
            # Record first interviewer join; also set actual_start_time if not yet set
            (
                supabase.table('interviews')
                .update({'interviewer_joined_at': now_iso, 'actual_start_time': now_iso})
                .eq('room_id', interview_id)
                .is_('interviewer_joined_at', 'null')
                .execute()
            )
        elif user_role == 'candidate':
            (
                supabase.table('interviews')
                .update({'candidate_joined_at': now_iso})
                .eq('room_id', interview_id)
                .is_('candidate_joined_at', 'null')
                .execute()
            )
    except Exception as e:
        print(f'⚠️  Join tracking DB update failed: {e}')


@sio.on('switch-tab')
async def switch_tab(sid, data):
    """
    Handle tab switching by interviewer.
    Broadcasts tab change to all participants (so candidate can auto-follow).
    
    Data: {
        "interviewId": str,
        "tab": str ('meeting' or 'code'),
        "userId": str,
        "userRole": str
    }
    """
    interview_id = data.get('interviewId')
    tab = data.get('tab')
    user_role = data.get('userRole')
    
    if not interview_id or not tab:
        return
    
    print(f"🔄 Tab switched to: {tab} by {user_role}")
    
    # Broadcast to all participants
    await sio.emit(
        'tab-switched',
        {
            'tab': tab,
            'userRole': user_role,
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat()
        },
        room=interview_id,
        skip_sid=sid
    )


@sio.on('code-change')
async def interview_code_change(sid, data):
    """
    Handle real-time code editor changes.
    Syncs code across all participants.
    
    Data: {
        "interviewId": str,
        "code": str,
        "language": str,
        "userId": str
    }
    """
    interview_id = data.get('interviewId')
    
    if not interview_id:
        return
    
    # Broadcast to all except sender
    await sio.emit(
        'code-changed',
        {
            'code': data.get('code'),
            'language': data.get('language'),
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat()
        },
        room=interview_id,
        skip_sid=sid
    )


@sio.on('code-execute')
async def code_execute(sid, data):
    """
    Handle code execution result broadcast.
    
    Data: {
        "interviewId": str,
        "output": str,
        "userId": str
    }
    """
    interview_id = data.get('interviewId')
    
    if not interview_id:
        return
    
    # Broadcast execution result to all participants
    await sio.emit(
        'code-executed',
        {
            'output': data.get('output'),
            'userId': data.get('userId'),
            'success': data.get('success'),
            'outputType': data.get('outputType'),
            'timestamp': datetime.utcnow().isoformat()
        },
        room=interview_id
    )


# ─── Whiteboard handlers ────────────────────────────────────────────────────

@sio.on('whiteboard-stroke')
async def whiteboard_stroke(sid, data):
    """
    Broadcast a completed drawing stroke to all room participants.

    Data: { interviewId, stroke: { id, tool, color, width, points|x1/y1/x2/y2|text, ... } }
    """
    interview_id = data.get('interviewId')
    if not interview_id:
        return
    await sio.emit(
        'whiteboard-stroke',
        {
            'stroke': data.get('stroke'),
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat(),
        },
        room=interview_id,
        skip_sid=sid,
    )


@sio.on('whiteboard-undo')
async def whiteboard_undo(sid, data):
    """
    Broadcast an undo action (remove a stroke by id) to all room participants.

    Data: { interviewId, strokeId, userId }
    """
    interview_id = data.get('interviewId')
    if not interview_id:
        return
    await sio.emit(
        'whiteboard-undo',
        {
            'strokeId': data.get('strokeId'),
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat(),
        },
        room=interview_id,
        skip_sid=sid,
    )


@sio.on('whiteboard-clear')
async def whiteboard_clear(sid, data):
    """
    Broadcast a clear-all action to all room participants.

    Data: { interviewId, userId }
    """
    interview_id = data.get('interviewId')
    if not interview_id:
        return
    await sio.emit(
        'whiteboard-clear',
        {
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat(),
        },
        room=interview_id,
        skip_sid=sid,
    )


@sio.on('whiteboard-request-sync')
async def whiteboard_request_sync(sid, data):
    """
    A newly joined participant requests the current board state.
    Broadcasts the request to all other participants — whoever has data responds
    via whiteboard-sync-response.

    Data: { interviewId, requesterId }
    """
    interview_id = data.get('interviewId')
    if not interview_id:
        return
    await sio.emit(
        'whiteboard-sync-request',
        {
            'requesterId': data.get('requesterId'),
            'timestamp': datetime.utcnow().isoformat(),
        },
        room=interview_id,
        skip_sid=sid,
    )


@sio.on('whiteboard-sync-response')
async def whiteboard_sync_response(sid, data):
    """
    A peer responds to a sync request by sending the full strokes array.
    We route this directly to the requesting participant only.

    Data: { interviewId, targetUserId, strokes: [...] }
    """
    interview_id   = data.get('interviewId')
    target_user_id = data.get('targetUserId')
    if not interview_id or not target_user_id:
        return
    target_sid = _find_sid_by_user_id(interview_id, target_user_id)
    if not target_sid:
        return
    await sio.emit(
        'whiteboard-sync',
        {
            'strokes': data.get('strokes', []),
            'timestamp': datetime.utcnow().isoformat(),
        },
        to=target_sid,
    )


@sio.on('whiteboard-access')
async def whiteboard_access(sid, data):
    """
    Interviewer grants or revokes candidate drawing access on the whiteboard.

    Data: { interviewId, canEdit: bool, userId }
    """
    interview_id = data.get('interviewId')
    if not interview_id:
        return
    await sio.emit(
        'whiteboard-access',
        {
            'canEdit': data.get('canEdit', False),
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat(),
        },
        room=interview_id,
    )


@sio.on('whiteboard-access')
async def whiteboard_access(sid, data):
    """
    Interviewer grants or revokes candidate drawing access on the whiteboard.

    Data: { interviewId, canEdit: bool, userId }
    """
    interview_id = data.get('interviewId')
    if not interview_id:
        return
    await sio.emit(
        'whiteboard-access',
        {
            'canEdit': data.get('canEdit', False),
            'userId': data.get('userId'),
            'timestamp': datetime.utcnow().isoformat(),
        },
        room=interview_id,
    )


def _find_sid_by_user_id(room_id: str, user_id: str) -> str | None:
    """Look up the socket SID for a user in a room."""
    for p in room_participants.get(room_id, []):
        if p['userId'] == user_id:
            return p['sid']
    return None


@sio.on('webrtc-offer')
async def interview_webrtc_offer(sid, data):
    """
    Handle WebRTC offer for peer-to-peer video connection.
    
    Data: {
        "to": str (user_id),
        "interviewId": str,
        "offer": RTCSessionDescription
    }
    """
    target_user_id = data.get('to')
    interview_id = data.get('interviewId') or (sid_to_info.get(sid, {}).get('roomId'))
    
    if not target_user_id:
        return
    
    # Resolve target socket SID from user_id
    target_sid = _find_sid_by_user_id(interview_id, target_user_id) if interview_id else target_user_id
    if not target_sid:
        return
    
    sender_info = sid_to_info.get(sid, {})
    await sio.emit(
        'webrtc-offer',
        {
            'from': sender_info.get('userId', sid),
            'offer': data.get('offer')
        },
        to=target_sid
    )


@sio.on('webrtc-answer')
async def interview_webrtc_answer(sid, data):
    """
    Handle WebRTC answer.
    
    Data: {
        "to": str (user_id),
        "interviewId": str,
        "answer": RTCSessionDescription
    }
    """
    target_user_id = data.get('to')
    interview_id = data.get('interviewId') or (sid_to_info.get(sid, {}).get('roomId'))
    
    if not target_user_id:
        return
    
    target_sid = _find_sid_by_user_id(interview_id, target_user_id) if interview_id else target_user_id
    if not target_sid:
        return
    
    sender_info = sid_to_info.get(sid, {})
    await sio.emit(
        'webrtc-answer',
        {
            'from': sender_info.get('userId', sid),
            'answer': data.get('answer')
        },
        to=target_sid
    )


@sio.on('webrtc-ice-candidate')
async def interview_webrtc_ice_candidate(sid, data):
    """
    Handle WebRTC ICE candidate exchange.
    
    Data: {
        "to": str (user_id),
        "interviewId": str,
        "candidate": RTCIceCandidate
    }
    """
    target_user_id = data.get('to')
    interview_id = data.get('interviewId') or (sid_to_info.get(sid, {}).get('roomId'))
    
    if not target_user_id:
        return
    
    target_sid = _find_sid_by_user_id(interview_id, target_user_id) if interview_id else target_user_id
    if not target_sid:
        return
    
    sender_info = sid_to_info.get(sid, {})
    await sio.emit(
        'webrtc-ice-candidate',
        {
            'from': sender_info.get('userId', sid),
            'candidate': data.get('candidate')
        },
        to=target_sid
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
