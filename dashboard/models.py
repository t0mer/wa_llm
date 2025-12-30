"""Database models - import from main project"""

import sys
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import models from the main project
from src.models.group import Group
from src.models.sender import Sender
from src.models.reaction import Reaction
from src.models.message import Message
from src.models.knowledge_base_topic import KBTopic
from src.models.kb_topic_message import KBTopicMessage

__all__ = ["Group", "Sender", "Reaction", "Message", "KBTopic", "KBTopicMessage"]
