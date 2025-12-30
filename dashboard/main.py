"""
FastAPI Dashboard Application for WhatsApp LLM
Displays data from Groups, Senders, Reactions, Messages, KBTopics, and KB_Topic_Message tables
"""

import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
import secrets

from database import get_session, init_db
from models import Group, Sender, Reaction, Message, KBTopic, KBTopicMessage

# Get configuration from environment
DB_URI = os.getenv("DB_URI")
BASIC_AUTH_USER = os.getenv("WHATSAPP_BASIC_AUTH_USER", "admin")
BASIC_AUTH_PASSWORD = os.getenv("WHATSAPP_BASIC_AUTH_PASSWORD", "password")
WHATSAPP_HOST = os.getenv("WHATSAPP_HOST", "http://localhost:3000")

if not DB_URI:
    raise ValueError("DB_URI environment variable is required")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    await init_db()
    yield


app = FastAPI(title="WhatsApp LLM Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# Add global context for templates
@app.middleware("http")
async def add_whatsapp_host_to_context(request: Request, call_next):
    request.state.whatsapp_host = WHATSAPP_HOST
    response = await call_next(request)
    return response

templates.env.globals["whatsapp_host"] = WHATSAPP_HOST

security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Authentication credentials"""
    correct_username = secrets.compare_digest(credentials.username, BASIC_AUTH_USER)
    correct_password = secrets.compare_digest(
        credentials.password, BASIC_AUTH_PASSWORD
    )

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    username: str = Depends(verify_credentials),
):
    """Redirect to groups page"""
    return RedirectResponse(url="/groups")


# Pydantic models for API requests
class GroupUpdate(BaseModel):
    group_name: Optional[str] = None
    group_topic: Optional[str] = None
    owner_jid: Optional[str] = None
    managed: Optional[bool] = None
    notify_on_spam: Optional[bool] = None


class GroupCreate(BaseModel):
    group_jid: str
    group_name: Optional[str] = None
    group_topic: Optional[str] = None
    owner_jid: Optional[str] = None
    managed: bool = False
    notify_on_spam: bool = False


# API endpoints for Groups CRUD
@app.post("/api/groups")
async def create_group(
    group: GroupCreate,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Create a new group"""
    # Check if group already exists
    existing = await session.get(Group, group.group_jid)
    if existing:
        raise HTTPException(status_code=400, detail="Group already exists")
    
    new_group = Group(**group.model_dump())
    session.add(new_group)
    await session.commit()
    await session.refresh(new_group)
    
    return JSONResponse(
        content={"message": "Group created successfully", "group_jid": new_group.group_jid},
        status_code=201
    )


# API endpoint for group statistics - MUST come before generic {group_jid:path} routes
@app.get("/api/groups/{group_jid:path}/statistics")
async def get_group_statistics(
    group_jid: str,
    days: int = 2,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Get statistics for a group including message count per day and top senders"""
    from urllib.parse import unquote
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_
    
    group_jid = unquote(group_jid)
    
    # Verify group exists
    group = await session.get(Group, group_jid)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # Get messages per day
    messages_query = select(
        func.date(Message.timestamp).label('date'),
        func.count(Message.message_id).label('count')
    ).where(
        and_(
            Message.group_jid == group_jid,
            Message.timestamp >= start_date
        )
    ).group_by(func.date(Message.timestamp)).order_by(func.date(Message.timestamp))
    
    result = await session.exec(messages_query)
    messages_per_day = [{"date": str(row.date), "count": row.count} for row in result]
    
    # Get top 5 senders
    top_senders_query = select(
        Message.sender_jid,
        Sender.push_name,
        func.count(Message.message_id).label('message_count')
    ).join(
        Sender, Message.sender_jid == Sender.jid, isouter=True
    ).where(
        Message.group_jid == group_jid
    ).group_by(
        Message.sender_jid, Sender.push_name
    ).order_by(
        func.count(Message.message_id).desc()
    ).limit(5)
    
    result = await session.exec(top_senders_query)
    top_senders = [
        {
            "sender_jid": row.sender_jid,
            "push_name": row.push_name or "Unknown",
            "message_count": row.message_count
        }
        for row in result
    ]
    
    return JSONResponse(content={
        "group_jid": group_jid,
        "group_name": group.group_name,
        "messages_per_day": messages_per_day,
        "top_senders": top_senders
    })


@app.put("/api/groups/{group_jid:path}")
async def update_group(
    group_jid: str,
    group_update: GroupUpdate,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Update an existing group"""
    from urllib.parse import unquote
    group_jid = unquote(group_jid)
    
    group = await session.get(Group, group_jid)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Update only provided fields
    update_data = group_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)
    
    session.add(group)
    await session.commit()
    await session.refresh(group)
    
    return JSONResponse(content={"message": "Group updated successfully"})


@app.delete("/api/groups/{group_jid:path}")
async def delete_group(
    group_jid: str,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Delete a group"""
    from urllib.parse import unquote
    group_jid = unquote(group_jid)
    
    group = await session.get(Group, group_jid)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    await session.delete(group)
    await session.commit()
    
    return JSONResponse(content={"message": "Group deleted successfully"})


@app.get("/groups", response_class=HTMLResponse)
async def get_groups(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Display groups table with pagination"""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(Group)
    total = await session.scalar(count_query)

    # Get paginated data
    query = select(Group).offset(offset).limit(page_size).order_by(Group.created_at.desc())
    result = await session.exec(query)
    groups = result.all()

    total_pages = (total + page_size - 1) // page_size if total else 1

    return templates.TemplateResponse(
        "groups.html",
        {
            "request": request,
            "groups": groups,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "active_tab": "groups",
        },
    )


@app.get("/senders", response_class=HTMLResponse)
async def get_senders(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Display senders table with pagination"""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(Sender)
    total = await session.scalar(count_query)

    # Get paginated data
    query = select(Sender).offset(offset).limit(page_size).order_by(Sender.jid)
    result = await session.exec(query)
    senders = result.all()

    total_pages = (total + page_size - 1) // page_size if total else 1

    return templates.TemplateResponse(
        "senders.html",
        {
            "request": request,
            "senders": senders,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "active_tab": "senders",
        },
    )


@app.get("/api/senders/{sender_jid:path}/statistics")
async def get_sender_statistics(
    sender_jid: str,
    days: int = 7,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Get statistics for a sender including message count per group"""
    from urllib.parse import unquote
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_
    
    sender_jid = unquote(sender_jid)
    
    # Verify sender exists
    sender = await session.get(Sender, sender_jid)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # Get messages per group
    messages_query = select(
        Message.group_jid,
        Group.group_name,
        func.count(Message.message_id).label('count')
    ).join(
        Group, Message.group_jid == Group.group_jid, isouter=True
    ).where(
        and_(
            Message.sender_jid == sender_jid,
            Message.timestamp >= start_date
        )
    ).group_by(Message.group_jid, Group.group_name).order_by(func.count(Message.message_id).desc())
    
    result = await session.exec(messages_query)
    messages_per_group = [
        {
            "group_jid": row.group_jid,
            "group_name": row.group_name or "Unknown",
            "count": row.count
        }
        for row in result
    ]
    
    # Get total messages
    total_query = select(func.count(Message.message_id)).where(
        and_(
            Message.sender_jid == sender_jid,
            Message.timestamp >= start_date
        )
    )
    total_messages = await session.scalar(total_query) or 0
    
    return JSONResponse(content={
        "sender_jid": sender_jid,
        "push_name": sender.push_name,
        "messages_per_group": messages_per_group,
        "total_messages": total_messages
    })


@app.get("/reactions", response_class=HTMLResponse)
async def get_reactions(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Display reactions table with pagination"""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(Reaction)
    total = await session.scalar(count_query)

    # Get paginated data
    query = select(Reaction).offset(offset).limit(page_size).order_by(Reaction.timestamp.desc())
    result = await session.exec(query)
    reactions = result.all()

    total_pages = (total + page_size - 1) // page_size if total else 1

    return templates.TemplateResponse(
        "reactions.html",
        {
            "request": request,
            "reactions": reactions,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "active_tab": "reactions",
        },
    )


@app.get("/messages", response_class=HTMLResponse)
async def get_messages(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Display messages table with pagination"""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(Message)
    total = await session.scalar(count_query)

    # Get paginated data
    query = select(Message).offset(offset).limit(page_size).order_by(Message.timestamp.desc())
    result = await session.exec(query)
    messages = result.all()

    total_pages = (total + page_size - 1) // page_size if total else 1

    return templates.TemplateResponse(
        "messages.html",
        {
            "request": request,
            "messages": messages,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "active_tab": "messages",
        },
    )


@app.get("/kbtopics", response_class=HTMLResponse)
async def get_kbtopics(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Display KB topics table with pagination"""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(KBTopic)
    total = await session.scalar(count_query)

    # Get paginated data
    query = select(KBTopic).offset(offset).limit(page_size).order_by(KBTopic.start_time.desc())
    result = await session.exec(query)
    kbtopics = result.all()

    total_pages = (total + page_size - 1) // page_size if total else 1

    return templates.TemplateResponse(
        "kbtopics.html",
        {
            "request": request,
            "kbtopics": kbtopics,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "active_tab": "kbtopics",
        },
    )


@app.get("/kb_topic_message", response_class=HTMLResponse)
async def get_kb_topic_messages(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    username: str = Depends(verify_credentials),
    session: AsyncSession = Depends(get_session),
):
    """Display KB topic message relationships table with pagination"""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(KBTopicMessage)
    total = await session.scalar(count_query)

    # Get paginated data
    query = select(KBTopicMessage).offset(offset).limit(page_size)
    result = await session.exec(query)
    kb_topic_messages = result.all()

    total_pages = (total + page_size - 1) // page_size if total else 1

    return templates.TemplateResponse(
        "kb_topic_message.html",
        {
            "request": request,
            "kb_topic_messages": kb_topic_messages,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "active_tab": "kb_topic_message",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
