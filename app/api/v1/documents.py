"""
Document API Endpoints
Handles document upload, management, analysis, comparison, and citations.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime
import io

from app.models import (
    APIResponse,
    DocumentUploadResponse,
    DocumentResponse,
    DocumentListResponse,
    CitationResponse,
    ComparisonRequest,
    ComparisonResponse,
    SummarizeRequest,
    DocumentStatusEnum
)
from app.database.document_repository import (
    DocumentRepository,
    CitationRepository,
    ComparisonRepository
)
from app.database.document_schemas import DocumentStatus, DocumentType
from app.tools.document_tools import DocumentTools
from app.agents.document_analyzer import DocumentAnalyzer
from app.utils.logging import logger


router = APIRouter()
document_tools = DocumentTools()


# ===========================================
# Document Upload
# ===========================================

@router.post("/upload", response_model=APIResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="PDF files to upload (max 10)"),
    user_id: str = Query(default="anonymous", description="User ID")
):
    """
    Upload one or more documents for analysis.
    
    - Accepts PDF, DOCX, TXT, MD files
    - Max 5MB per file
    - Max 10 files per request
    - Processing happens in background
    """
    if len(files) > DocumentTools.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {DocumentTools.MAX_BATCH_SIZE} files allowed per upload"
        )
    
    uploaded = []
    errors = []
    
    for file in files:
        try:
            # Read file content
            content = await file.read()
            
            # Validate file
            is_valid, error_msg, doc_type = DocumentTools.validate_file(
                file.filename,
                file.content_type,
                len(content)
            )
            
            if not is_valid:
                errors.append({
                    "filename": file.filename,
                    "error": error_msg
                })
                continue
            
            # Upload to GridFS
            gridfs_id = await DocumentRepository.upload_file(
                file_content=content,
                filename=file.filename,
                content_type=file.content_type,
                metadata={"user_id": user_id}
            )
            
            # Create document record
            document = await DocumentRepository.create({
                "user_id": user_id,
                "filename": file.filename,
                "original_filename": file.filename,
                "file_size": len(content),
                "mime_type": file.content_type,
                "document_type": DocumentType(doc_type),
                "gridfs_file_id": gridfs_id,
                "status": DocumentStatus.PENDING
            })
            
            uploaded.append(DocumentUploadResponse(
                document_id=document.document_id,
                filename=document.filename,
                file_size=document.file_size,
                status=DocumentStatusEnum(document.status.value),
                uploaded_at=document.uploaded_at
            ))
            
            # Queue background processing
            background_tasks.add_task(
                process_document,
                document.document_id,
                content,
                doc_type
            )
            
        except Exception as e:
            logger.error(f"Upload failed for {file.filename}: {e}")
            errors.append({
                "filename": file.filename,
                "error": str(e)
            })
    
    return APIResponse(
        status=200 if uploaded else 400,
        message=f"Uploaded {len(uploaded)} document(s)" + (f", {len(errors)} failed" if errors else ""),
        data={
            "uploads": [u.model_dump() for u in uploaded],
            "errors": errors
        }
    )


async def process_document(document_id: str, content: bytes, doc_type: str):
    """Background task to process a document."""
    try:
        # Update status to processing
        await DocumentRepository.update(document_id, {
            "status": DocumentStatus.PROCESSING,
            "processing_progress": 10
        })
        
        # Extract text
        tools = DocumentTools()
        extraction = await tools.extract_text(content, doc_type, document_id)
        
        if extraction.get("error"):
            await DocumentRepository.update(document_id, {
                "status": DocumentStatus.FAILED,
                "error_message": extraction["error"]
            })
            return
        
        await DocumentRepository.update(document_id, {
            "extracted_text": extraction.get("extracted_text"),
            "page_count": extraction.get("page_count"),
            "word_count": extraction.get("word_count"),
            "metadata": extraction.get("metadata", {}),
            "processing_progress": 40
        })
        
        # Extract citations
        citations = tools.extract_citations(extraction.get("extracted_text", ""))
        if citations:
            citation_docs = []
            for cit in citations:
                citation_docs.append({
                    "document_id": document_id,
                    "raw_text": cit.get("raw_text", ""),
                    "authors": cit.get("authors", []),
                    "title": cit.get("title"),
                    "year": cit.get("year"),
                    "doi": cit.get("doi"),
                    "formatted_apa": tools.format_citation(cit, "APA"),
                    "formatted_mla": tools.format_citation(cit, "MLA"),
                    "formatted_chicago": tools.format_citation(cit, "Chicago"),
                    "formatted_harvard": tools.format_citation(cit, "Harvard"),
                    "position": cit.get("position")
                })
            await CitationRepository.create_many(citation_docs)
        
        await DocumentRepository.update(document_id, {"processing_progress": 60})
        
        # Run analysis
        analyzer = DocumentAnalyzer()
        analysis = await analyzer.execute({
            "document_id": document_id,
            "extracted_text": extraction.get("extracted_text", ""),
            "filename": document_id,
            "analysis_depth": "thorough"
        })
        
        # Update with analysis results
        await DocumentRepository.update(document_id, {
            "summary": analysis.get("summary"),
            "topics": analysis.get("topics", []),
            "key_findings": analysis.get("key_findings", []),
            "entities": analysis.get("entities", []),
            "status": DocumentStatus.COMPLETED,
            "processing_progress": 100,
            "processed_at": datetime.utcnow()
        })
        
        logger.info(f"Document {document_id} processed successfully")
        
    except Exception as e:
        logger.error(f"Document processing failed for {document_id}: {e}")
        await DocumentRepository.update(document_id, {
            "status": DocumentStatus.FAILED,
            "error_message": str(e)
        })


# ===========================================
# Document List & Get
# ===========================================

@router.get("", response_model=APIResponse)
async def list_documents(
    user_id: str = Query(default="anonymous"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100)
):
    """List all documents for a user with pagination."""
    offset = (page - 1) * limit
    
    status_filter = DocumentStatus(status) if status else None
    
    documents = await DocumentRepository.get_by_user(
        user_id=user_id,
        status=status_filter,
        skip=offset,
        limit=limit
    )
    
    total = await DocumentRepository.count_by_user(user_id, status_filter)
    
    doc_responses = [
        DocumentResponse(
            document_id=d.document_id,
            filename=d.filename,
            original_filename=d.original_filename,
            file_size=d.file_size,
            document_type=d.document_type.value,
            status=d.status.value,
            processing_progress=d.processing_progress,
            page_count=d.page_count,
            word_count=d.word_count,
            summary=d.summary,
            topics=d.topics,
            key_findings=d.key_findings,
            uploaded_at=d.uploaded_at,
            processed_at=d.processed_at
        )
        for d in documents
    ]
    
    return APIResponse(
        status=200,
        message=f"Found {total} document(s)",
        data=DocumentListResponse(
            total=total,
            limit=limit,
            offset=offset,
            documents=doc_responses
        ).model_dump()
    )


@router.get("/{document_id}", response_model=APIResponse)
async def get_document(document_id: str):
    """Get a specific document by ID."""
    document = await DocumentRepository.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return APIResponse(
        status=200,
        message="Document retrieved",
        data=DocumentResponse(
            document_id=document.document_id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_size=document.file_size,
            document_type=document.document_type.value,
            status=document.status.value,
            processing_progress=document.processing_progress,
            page_count=document.page_count,
            word_count=document.word_count,
            summary=document.summary,
            topics=document.topics,
            key_findings=document.key_findings,
            uploaded_at=document.uploaded_at,
            processed_at=document.processed_at
        ).model_dump()
    )


@router.delete("/{document_id}", response_model=APIResponse)
async def delete_document(document_id: str):
    """Delete a document and its associated data."""
    # Delete citations first
    await CitationRepository.delete_by_document(document_id)
    
    # Delete document (also deletes GridFS file)
    deleted = await DocumentRepository.delete(document_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return APIResponse(
        status=200,
        message="Document deleted successfully",
        data={"document_id": document_id}
    )


# ===========================================
# Document Download
# ===========================================

@router.get("/{document_id}/download")
async def download_document(document_id: str):
    """Download the original document file."""
    document = await DocumentRepository.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not document.gridfs_file_id:
        raise HTTPException(status_code=404, detail="Document file not found")
    
    content = await DocumentRepository.download_file(document.gridfs_file_id)
    
    if not content:
        raise HTTPException(status_code=404, detail="Failed to retrieve document file")
    
    return StreamingResponse(
        io.BytesIO(content),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.original_filename}"'
        }
    )


# ===========================================
# Citations
# ===========================================

@router.get("/{document_id}/citations", response_model=APIResponse)
async def get_document_citations(
    document_id: str,
    style: str = Query(default="APA", description="Citation style: APA, MLA, Chicago, Harvard")
):
    """Get citations extracted from a document."""
    document = await DocumentRepository.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    citations = await CitationRepository.get_by_document(document_id)
    
    style_field_map = {
        "APA": "formatted_apa",
        "MLA": "formatted_mla",
        "Chicago": "formatted_chicago",
        "Harvard": "formatted_harvard"
    }
    
    formatted_citations = [
        {
            "citation_id": c.citation_id,
            "raw_text": c.raw_text,
            "formatted": getattr(c, style_field_map.get(style.upper(), "formatted_apa")),
            "authors": c.authors,
            "title": c.title,
            "year": c.year,
            "doi": c.doi
        }
        for c in citations
    ]
    
    return APIResponse(
        status=200,
        message=f"Found {len(citations)} citation(s)",
        data={
            "document_id": document_id,
            "style": style.upper(),
            "citations": formatted_citations
        }
    )


# ===========================================
# Document Comparison
# ===========================================

@router.post("/compare", response_model=APIResponse)
async def compare_documents(request: ComparisonRequest, user_id: str = Query(default="anonymous")):
    """Compare multiple documents to find similarities and differences."""
    # Fetch all documents
    documents = []
    for doc_id in request.document_ids:
        doc = await DocumentRepository.get_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        if doc.status != DocumentStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Document {doc_id} is not fully processed yet"
            )
        documents.append({
            "document_id": doc.document_id,
            "filename": doc.filename,
            "summary": doc.summary,
            "topics": doc.topics,
            "key_findings": doc.key_findings
        })
    
    # Run comparison
    analyzer = DocumentAnalyzer()
    comparison_result = await analyzer.compare_documents(documents)
    
    if comparison_result.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=comparison_result.get("error", "Comparison failed")
        )
    
    # Save comparison
    comparison = await ComparisonRepository.create({
        "user_id": user_id,
        "document_ids": request.document_ids,
        "similarities": comparison_result.get("similarities", []),
        "differences": comparison_result.get("differences", []),
        "recommendation": comparison_result.get("recommendation"),
        "overall_analysis": comparison_result.get("overall_analysis")
    })
    
    return APIResponse(
        status=200,
        message="Document comparison completed",
        data=ComparisonResponse(
            comparison_id=comparison.comparison_id,
            document_ids=comparison.document_ids,
            similarities=comparison.similarities,
            differences=comparison.differences,
            recommendation=comparison.recommendation,
            overall_analysis=comparison.overall_analysis,
            created_at=comparison.created_at
        ).model_dump()
    )


# ===========================================
# Summarize
# ===========================================

@router.get("/{document_id}/summarize", response_model=APIResponse)
async def summarize_document(
    document_id: str,
    length: str = Query(default="medium", pattern="^(short|medium|long)$")
):
    """
    Generate or retrieve document summary.
    
    - short: 2-3 sentences
    - medium: 1-2 paragraphs (default, stored summary)
    - long: Detailed 3-4 paragraphs
    """
    document = await DocumentRepository.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if document.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Document is not fully processed yet"
        )
    
    # For medium length, return stored summary
    if length == "medium" and document.summary:
        return APIResponse(
            status=200,
            message="Summary retrieved",
            data={
                "document_id": document_id,
                "length": length,
                "summary": document.summary
            }
        )
    
    # Generate new summary for short/long
    depth_map = {"short": "quick", "medium": "thorough", "long": "deep"}
    
    analyzer = DocumentAnalyzer()
    result = await analyzer._generate_summary(
        document.extracted_text or "",
        document.topics,
        document.key_findings,
        depth_map[length]
    )
    
    return APIResponse(
        status=200,
        message="Summary generated",
        data={
            "document_id": document_id,
            "length": length,
            "summary": result
        }
    )


# ===========================================
# Reprocess Document
# ===========================================

@router.post("/{document_id}/reprocess", response_model=APIResponse)
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks
):
    """Reprocess a failed or completed document."""
    document = await DocumentRepository.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not document.gridfs_file_id:
        raise HTTPException(status_code=400, detail="Document file not available")
    
    # Download file content
    content = await DocumentRepository.download_file(document.gridfs_file_id)
    if not content:
        raise HTTPException(status_code=500, detail="Failed to retrieve document file")
    
    # Reset status
    await DocumentRepository.update(document_id, {
        "status": DocumentStatus.PENDING,
        "processing_progress": 0,
        "error_message": None
    })
    
    # Queue reprocessing
    background_tasks.add_task(
        process_document,
        document_id,
        content,
        document.document_type.value
    )
    
    return APIResponse(
        status=200,
        message="Document queued for reprocessing",
        data={"document_id": document_id, "status": "pending"}
    )
