"""
Document Analysis MongoDB Schemas using Beanie ODM.
Defines document models for the document analysis feature.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from beanie import Document, Indexed
from pydantic import BaseModel, Field
import uuid


# ===========================================
# Document Analysis Enums
# ===========================================

class DocumentStatus(str, Enum):
    """Status of an uploaded document."""
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, Enum):
    """Supported document types."""
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"


class ResearchType(str, Enum):
    """Type of research session."""
    QUERY = "query"           # Traditional web search only
    DOCUMENT = "document"     # Document analysis only
    HYBRID = "hybrid"         # Both documents and web search


class LLMProvider(str, Enum):
    """Available LLM providers."""
    DEEPSEEK = "deepseek"
    CLAUDE = "claude"
    GPT4 = "gpt4"
    GPT4O = "gpt4o"


class ConversationRole(str, Enum):
    """Role in a conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ===========================================
# Document Models
# ===========================================

class UploadedDocument(Document):
    """Uploaded document for analysis."""
    
    document_id: Indexed(str, unique=True) = Field(
        default_factory=lambda: f"doc_{uuid.uuid4().hex[:12]}"
    )
    user_id: Indexed(str)
    
    # File information
    filename: str
    original_filename: str
    file_size: int  # bytes
    mime_type: str
    document_type: DocumentType
    
    # GridFS reference
    gridfs_file_id: Optional[str] = None
    
    # Processing status
    status: DocumentStatus = DocumentStatus.PENDING
    processing_progress: int = Field(default=0, ge=0, le=100)
    error_message: Optional[str] = None
    
    # Extracted content
    extracted_text: Optional[str] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    
    # Analysis results
    summary: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    key_findings: List[str] = Field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    
    class Settings:
        name = "documents"
        indexes = [
            "document_id",
            "user_id",
            "status",
            "uploaded_at"
        ]


class DocumentCitation(Document):
    """Citation extracted from a document."""
    
    citation_id: Indexed(str, unique=True) = Field(
        default_factory=lambda: f"cit_{uuid.uuid4().hex[:12]}"
    )
    document_id: Indexed(str)
    
    # Citation details
    raw_text: str
    formatted_apa: Optional[str] = None
    formatted_mla: Optional[str] = None
    formatted_chicago: Optional[str] = None
    formatted_harvard: Optional[str] = None
    
    # Parsed fields
    authors: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    publication: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    
    # Position in document
    page_number: Optional[int] = None
    position: Optional[int] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "document_citations"
        indexes = ["citation_id", "document_id"]


class DocumentComparison(Document):
    """Comparison between two or more documents."""
    
    comparison_id: Indexed(str, unique=True) = Field(
        default_factory=lambda: f"cmp_{uuid.uuid4().hex[:12]}"
    )
    user_id: Indexed(str)
    document_ids: List[str]
    
    # Comparison results
    similarities: List[Dict[str, Any]] = Field(default_factory=list)
    differences: List[Dict[str, Any]] = Field(default_factory=list)
    recommendation: Optional[str] = None
    overall_analysis: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "document_comparisons"
        indexes = ["comparison_id", "user_id"]


class UserSettings(Document):
    """User preferences and settings."""
    
    settings_id: Indexed(str, unique=True) = Field(
        default_factory=lambda: f"set_{uuid.uuid4().hex[:12]}"
    )
    user_id: Indexed(str, unique=True)
    
    # UI Settings
    theme: str = Field(default="system")
    auto_save: bool = True
    
    # Default Modes
    default_citation_style: str = "APA"
    default_report_format: str = "markdown"
    
    # Notifications
    notifications_enabled: bool = True
    
    # LLM Preferences (dict for flexibility)
    llm_preferences: Dict[str, Any] = Field(default_factory=lambda: {
        "default_model": "deepseek",
        "temperature": 0.7,
        "max_tokens": 4096
    })
    
    # Research Preferences
    research_preferences: Dict[str, Any] = Field(default_factory=lambda: {
        "default_focus_areas": ["general"],
        "include_citations": True,
        "include_images": False,
        "search_depth": "thorough"
    })
    
    # Export Preferences
    export_preferences: Dict[str, Any] = Field(default_factory=lambda: {
        "default_format": "markdown",
        "include_metadata": True,
        "include_sources": True
    })
    
    # Legacy fields (kept for compatibility)
    llm_provider: LLMProvider = LLMProvider.DEEPSEEK
    custom_api_key: Optional[str] = None
    agents_enabled: Dict[str, bool] = Field(default_factory=lambda: {
        "researcher": True,
        "analyst": True,
        "fact_checker": True,
        "report_generator": True,
        "document_analyzer": True
    })
    auto_summarize: bool = True
    auto_extract_citations: bool = True
    max_batch_size: int = Field(default=10, ge=1, le=20)
    default_research_mode: str = "auto"
    default_analysis_depth: str = "thorough"
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "user_settings"
        indexes = ["user_id"]


class ConversationMessage(BaseModel):
    """Embedded message in a conversation (not a standalone document)."""
    
    message_id: str = Field(
        default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}"
    )
    
    # Message content
    role: ConversationRole
    content: str
    agent_name: Optional[str] = None  # For assistant messages
    
    # Sources/references
    sources: List[str] = Field(default_factory=list)
    document_refs: List[str] = Field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationHistory(Document):
    """Conversation history for a research session."""
    
    conversation_id: Indexed(str, unique=True) = Field(
        default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}"
    )
    session_id: Indexed(str, unique=True)
    user_id: Indexed(str)
    document_ids: List[str] = Field(default_factory=list)
    
    # Context from research session
    context: Dict[str, Any] = Field(default_factory=dict)
    
    # Embedded messages
    messages: List[ConversationMessage] = Field(default_factory=list)
    message_count: int = 0
    
    # Summary
    summary: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "conversation_histories"
        indexes = ["conversation_id", "session_id", "user_id"]
