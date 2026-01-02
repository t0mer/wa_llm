import logging
from typing import Annotated, Dict, Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession

from config import Settings
from whatsapp import WhatsAppClient
from models import Group, Message
from summarize_and_send_to_groups import summarize_and_send_to_groups, summarize
from .deps import get_db_async_session, get_whatsapp, get_settings

# Create router for send summaries to groups endpoints
router = APIRouter()

# Configure logger for this module
logger = logging.getLogger(__name__)


@router.post("/summarize_and_send_to_groups")
async def trigger_summarize_and_send_to_groups(
    session: Annotated[AsyncSession, Depends(get_db_async_session)],
    whatsapp: Annotated[WhatsAppClient, Depends(get_whatsapp)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Dict[str, Any]:
    """
    Trigger a send summaries to groups sync for all managed groups.

    This endpoint manually triggers the same process that runs
    in the daily_summary.py script. It will:
    1. Find all managed groups
    2. Check for new messages since last summary
    3. Generate AI summaries for groups with enough new messages
    4. Send summaries to the groups and related community groups
    5. Update the last_summary_sync timestamp

    Returns a success message upon completion.
    """
    try:
        logger.info("Starting manual send summaries to groups sync via API")

        # Execute the send summaries to groups sync process
        await summarize_and_send_to_groups(settings, session, whatsapp)

        logger.info("send summaries to groups sync completed successfully")

        return {
            "status": "success",
            "message": "send summaries to groups sync completed successfully",
        }

    except Exception as e:
        logger.error(f"Error during send summaries to groups sync: {str(e)}")
        # Re-raise the exception to let FastAPI handle it with proper error response
        raise


@router.get("/groups/{group_jid:path}/summary")
async def get_group_summary(
    group_jid: str,
    session: Annotated[AsyncSession, Depends(get_db_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    days: int = 7,
    language: str = None,
) -> Dict[str, Any]:
    """
    Get AI-generated summary for a specific group's recent messages.
    
    This endpoint generates a summary without sending it to the group.
    Useful for preview or dashboard display.
    
    Args:
        group_jid: The WhatsApp JID of the group
        days: Number of days to look back for messages (default: 7)
        language: Language for the summary (default: auto-detect from messages)
    
    Returns:
        Summary data including the AI-generated text and metadata
    """
    try:
        from urllib.parse import unquote
        group_jid = unquote(group_jid)
        
        # Verify group exists
        group = await session.get(Group, group_jid)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get messages for the time period
        resp = await session.exec(
            select(Message)
            .where(Message.group_jid == group_jid)
            .where(Message.timestamp >= start_date)
            .order_by(desc(Message.timestamp))
        )
        messages = list(resp.all())
        
        if len(messages) < 5:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough messages to summarize. Found {len(messages)} messages, need at least 5."
            )
        
        logger.info(f"Generating summary for group {group.group_name} with {len(messages)} messages from last {days} days")
        
        # Generate summary
        result = await summarize(
            session, settings, group.group_name or "group", messages, language
        )
        
        return {
            "group_jid": group_jid,
            "group_name": group.group_name,
            "summary": result.output,
            "message_count": len(messages),
            "days": days,
            "language": language,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating summary for group {group_jid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")
