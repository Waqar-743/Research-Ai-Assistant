"""
Document Repository
Data access layer for document-related operations including GridFS file storage.
"""

from typing import Optional, List, Dict, Any, BinaryIO
from datetime import datetime
from bson import ObjectId
import io

from app.database.connection import db, get_gridfs
from app.database.document_schemas import (
    UploadedDocument,
    DocumentCitation,
    DocumentComparison,
    UserSettings,
    ConversationMessage,
    ConversationHistory,
    DocumentStatus,
    LLMProvider
)
from app.utils.logging import logger


class DocumentRepository:
    """Repository for document operations."""
    
    # ===========================================
    # Document CRUD Operations
    # ===========================================
    
    @staticmethod
    async def create(document_data: Dict[str, Any]) -> UploadedDocument:
        """Create a new document record."""
        document = UploadedDocument(**document_data)
        await document.insert()
        logger.info(f"Created document record: {document.document_id}")
        return document
    
    @staticmethod
    async def get_by_id(document_id: str) -> Optional[UploadedDocument]:
        """Get document by ID."""
        return await UploadedDocument.find_one(
            UploadedDocument.document_id == document_id
        )
    
    @staticmethod
    async def get_by_user(
        user_id: str,
        status: Optional[DocumentStatus] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[UploadedDocument]:
        """Get documents for a user with optional filtering."""
        query = {"user_id": user_id}
        if status:
            query["status"] = status.value
        
        return await UploadedDocument.find(query).skip(skip).limit(limit).to_list()
    
    @staticmethod
    async def count_by_user(user_id: str, status: Optional[DocumentStatus] = None) -> int:
        """Count documents for a user."""
        query = {"user_id": user_id}
        if status:
            query["status"] = status.value
        return await UploadedDocument.find(query).count()
    
    @staticmethod
    async def update(document_id: str, update_data: Dict[str, Any]) -> Optional[UploadedDocument]:
        """Update a document record."""
        document = await DocumentRepository.get_by_id(document_id)
        if document:
            await document.update({"$set": update_data})
            return await DocumentRepository.get_by_id(document_id)
        return None
    
    @staticmethod
    async def delete(document_id: str) -> bool:
        """Delete a document and its GridFS file."""
        document = await DocumentRepository.get_by_id(document_id)
        if document:
            # Delete GridFS file if exists
            if document.gridfs_file_id:
                try:
                    fs = get_gridfs()
                    await fs.delete(ObjectId(document.gridfs_file_id))
                    logger.info(f"Deleted GridFS file: {document.gridfs_file_id}")
                except Exception as e:
                    logger.error(f"Failed to delete GridFS file: {e}")
            
            # Delete document record
            await document.delete()
            logger.info(f"Deleted document: {document_id}")
            return True
        return False
    
    # ===========================================
    # GridFS File Operations
    # ===========================================
    
    @staticmethod
    async def upload_file(
        file_content: bytes,
        filename: str,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Upload a file to GridFS and return the file ID."""
        fs = get_gridfs()
        
        file_id = await fs.upload_from_stream(
            filename,
            io.BytesIO(file_content),
            metadata={
                "content_type": content_type,
                "uploaded_at": datetime.utcnow().isoformat(),
                **(metadata or {})
            }
        )
        
        logger.info(f"Uploaded file to GridFS: {filename} -> {file_id}")
        return str(file_id)
    
    @staticmethod
    async def download_file(file_id: str) -> Optional[bytes]:
        """Download a file from GridFS."""
        try:
            fs = get_gridfs()
            grid_out = await fs.open_download_stream(ObjectId(file_id))
            content = await grid_out.read()
            return content
        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return None
    
    @staticmethod
    async def delete_file(file_id: str) -> bool:
        """Delete a file from GridFS."""
        try:
            fs = get_gridfs()
            await fs.delete(ObjectId(file_id))
            logger.info(f"Deleted GridFS file: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False


class CitationRepository:
    """Repository for document citations."""
    
    @staticmethod
    async def create(citation_data: Dict[str, Any]) -> DocumentCitation:
        """Create a new citation."""
        citation = DocumentCitation(**citation_data)
        await citation.insert()
        return citation
    
    @staticmethod
    async def create_many(citations: List[Dict[str, Any]]) -> List[DocumentCitation]:
        """Create multiple citations."""
        citation_docs = [DocumentCitation(**c) for c in citations]
        await DocumentCitation.insert_many(citation_docs)
        return citation_docs
    
    @staticmethod
    async def get_by_document(document_id: str) -> List[DocumentCitation]:
        """Get all citations for a document."""
        return await DocumentCitation.find(
            DocumentCitation.document_id == document_id
        ).to_list()
    
    @staticmethod
    async def delete_by_document(document_id: str) -> int:
        """Delete all citations for a document."""
        result = await DocumentCitation.find(
            DocumentCitation.document_id == document_id
        ).delete()
        return result.deleted_count if result else 0


class ComparisonRepository:
    """Repository for document comparisons."""
    
    @staticmethod
    async def create(comparison_data: Dict[str, Any]) -> DocumentComparison:
        """Create a new comparison."""
        comparison = DocumentComparison(**comparison_data)
        await comparison.insert()
        return comparison
    
    @staticmethod
    async def get_by_id(comparison_id: str) -> Optional[DocumentComparison]:
        """Get comparison by ID."""
        return await DocumentComparison.find_one(
            DocumentComparison.comparison_id == comparison_id
        )
    
    @staticmethod
    async def get_by_user(user_id: str, limit: int = 20) -> List[DocumentComparison]:
        """Get comparisons for a user."""
        return await DocumentComparison.find(
            DocumentComparison.user_id == user_id
        ).sort("-created_at").limit(limit).to_list()


class SettingsRepository:
    """Repository for user settings."""
    
    @staticmethod
    async def get_by_user(user_id: str) -> Optional[UserSettings]:
        """Get user settings or None if not exists."""
        return await UserSettings.find_one(UserSettings.user_id == user_id)
    
    @staticmethod
    async def get_or_create(user_id: str) -> UserSettings:
        """Get user settings or create default."""
        settings = await UserSettings.find_one(UserSettings.user_id == user_id)
        if not settings:
            settings = UserSettings(user_id=user_id)
            await settings.insert()
            logger.info(f"Created default settings for user: {user_id}")
        return settings
    
    @staticmethod
    async def create(settings_data: Dict[str, Any]) -> UserSettings:
        """Create new user settings."""
        settings = UserSettings(**settings_data)
        await settings.insert()
        logger.info(f"Created settings for user: {settings.user_id}")
        return settings
    
    @staticmethod
    async def update(user_id: str, update_data: Dict[str, Any]) -> Optional[UserSettings]:
        """Update user settings."""
        settings = await SettingsRepository.get_by_user(user_id)
        if settings:
            update_data["updated_at"] = datetime.utcnow()
            await settings.update({"$set": update_data})
            return await SettingsRepository.get_by_user(user_id)
        return None
    
    @staticmethod
    async def delete(user_id: str) -> bool:
        """Delete user settings."""
        settings = await SettingsRepository.get_by_user(user_id)
        if settings:
            await settings.delete()
            return True
        return False
    
    @staticmethod
    async def get_llm_provider(user_id: str) -> str:
        """Get user's preferred LLM provider."""
        settings = await SettingsRepository.get_or_create(user_id)
        return settings.llm_provider.value


class ConversationRepository:
    """Repository for conversation history with embedded messages."""
    
    @staticmethod
    async def create(conversation_data: Dict[str, Any]) -> ConversationHistory:
        """Create a new conversation history."""
        conversation = ConversationHistory(**conversation_data)
        await conversation.insert()
        logger.info(f"Created conversation: {conversation.conversation_id}")
        return conversation
    
    @staticmethod
    async def get_by_session(session_id: str) -> Optional[ConversationHistory]:
        """Get conversation by session ID."""
        return await ConversationHistory.find_one(
            ConversationHistory.session_id == session_id
        )
    
    @staticmethod
    async def get_by_id(conversation_id: str) -> Optional[ConversationHistory]:
        """Get conversation by conversation ID."""
        return await ConversationHistory.find_one(
            ConversationHistory.conversation_id == conversation_id
        )
    
    @staticmethod
    async def add_message(conversation_id: str, message: ConversationMessage) -> bool:
        """Add a message to conversation history."""
        conversation = await ConversationRepository.get_by_id(conversation_id)
        if conversation:
            await conversation.update({
                "$push": {"messages": message.model_dump()},
                "$inc": {"message_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            })
            logger.debug(f"Added message to conversation: {conversation_id}")
            return True
        return False
    
    @staticmethod
    async def get_messages(session_id: str, limit: int = 100) -> List[ConversationMessage]:
        """Get messages for a session."""
        conversation = await ConversationRepository.get_by_session(session_id)
        if conversation and conversation.messages:
            return conversation.messages[-limit:]
        return []
    
    @staticmethod
    async def delete(session_id: str) -> bool:
        """Delete conversation history."""
        conversation = await ConversationRepository.get_by_session(session_id)
        if conversation:
            await conversation.delete()
            logger.info(f"Deleted conversation for session: {session_id}")
            return True
        return False
