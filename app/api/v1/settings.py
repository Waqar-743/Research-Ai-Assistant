"""
Settings API Endpoints
Handles user preferences and configuration.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.models import APIResponse, UserSettingsRequest, UserSettingsResponse
from app.database.document_repository import SettingsRepository
from app.database.document_schemas import LLMProvider
from app.utils.logging import logger


router = APIRouter()


# ===========================================
# User Settings
# ===========================================

@router.get("", response_model=APIResponse)
async def get_settings(user_id: str = Query(default="anonymous")):
    """Get user settings, creating defaults if not exists."""
    settings = await SettingsRepository.get_by_user(user_id)
    
    if not settings:
        # Create default settings
        settings = await SettingsRepository.create({
            "user_id": user_id,
            "theme": "system",
            "default_citation_style": "APA",
            "auto_save": True,
            "notifications_enabled": True,
            "llm_preferences": {
                "default_model": LLMProvider.DEEPSEEK.value,
                "temperature": 0.7,
                "max_tokens": 4096
            },
            "research_preferences": {
                "default_focus_areas": ["general"],
                "include_citations": True,
                "include_images": False,
                "search_depth": "thorough"
            },
            "export_preferences": {
                "default_format": "markdown",
                "include_metadata": True,
                "include_sources": True
            }
        })
        logger.info(f"Created default settings for user {user_id}")
    
    return APIResponse(
        status=200,
        message="Settings retrieved",
        data=UserSettingsResponse(
            settings_id=settings.settings_id,
            user_id=settings.user_id,
            theme=settings.theme,
            default_citation_style=settings.default_citation_style,
            auto_save=settings.auto_save,
            notifications_enabled=settings.notifications_enabled,
            llm_preferences=settings.llm_preferences,
            research_preferences=settings.research_preferences,
            export_preferences=settings.export_preferences,
            created_at=settings.created_at,
            updated_at=settings.updated_at
        ).model_dump()
    )


@router.put("", response_model=APIResponse)
async def update_settings(
    request: UserSettingsRequest,
    user_id: str = Query(default="anonymous")
):
    """Update user settings."""
    settings = await SettingsRepository.get_by_user(user_id)
    
    # Build update dict from non-None fields
    update_data = {}
    
    if request.theme is not None:
        update_data["theme"] = request.theme
    
    if request.default_citation_style is not None:
        update_data["default_citation_style"] = request.default_citation_style
    
    if request.auto_save is not None:
        update_data["auto_save"] = request.auto_save
    
    if request.notifications_enabled is not None:
        update_data["notifications_enabled"] = request.notifications_enabled
    
    if request.llm_preferences is not None:
        update_data["llm_preferences"] = request.llm_preferences
    
    if request.research_preferences is not None:
        update_data["research_preferences"] = request.research_preferences
    
    if request.export_preferences is not None:
        update_data["export_preferences"] = request.export_preferences
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No settings to update")
    
    if settings:
        updated = await SettingsRepository.update(user_id, update_data)
    else:
        # Create with provided settings + defaults
        defaults = {
            "user_id": user_id,
            "theme": "system",
            "default_citation_style": "APA",
            "auto_save": True,
            "notifications_enabled": True,
            "llm_preferences": {
                "default_model": LLMProvider.DEEPSEEK.value,
                "temperature": 0.7,
                "max_tokens": 4096
            },
            "research_preferences": {
                "default_focus_areas": ["general"],
                "include_citations": True,
                "include_images": False,
                "search_depth": "thorough"
            },
            "export_preferences": {
                "default_format": "markdown",
                "include_metadata": True,
                "include_sources": True
            }
        }
        defaults.update(update_data)
        updated = await SettingsRepository.create(defaults)
    
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update settings")
    
    return APIResponse(
        status=200,
        message="Settings updated successfully",
        data=UserSettingsResponse(
            settings_id=updated.settings_id,
            user_id=updated.user_id,
            theme=updated.theme,
            default_citation_style=updated.default_citation_style,
            auto_save=updated.auto_save,
            notifications_enabled=updated.notifications_enabled,
            llm_preferences=updated.llm_preferences,
            research_preferences=updated.research_preferences,
            export_preferences=updated.export_preferences,
            created_at=updated.created_at,
            updated_at=updated.updated_at
        ).model_dump()
    )


@router.delete("", response_model=APIResponse)
async def reset_settings(user_id: str = Query(default="anonymous")):
    """Reset user settings to defaults."""
    await SettingsRepository.delete(user_id)
    
    # Create fresh defaults
    settings = await SettingsRepository.create({
        "user_id": user_id,
        "theme": "system",
        "default_citation_style": "APA",
        "auto_save": True,
        "notifications_enabled": True,
        "llm_preferences": {
            "default_model": LLMProvider.DEEPSEEK.value,
            "temperature": 0.7,
            "max_tokens": 4096
        },
        "research_preferences": {
            "default_focus_areas": ["general"],
            "include_citations": True,
            "include_images": False,
            "search_depth": "thorough"
        },
        "export_preferences": {
            "default_format": "markdown",
            "include_metadata": True,
            "include_sources": True
        }
    })
    
    return APIResponse(
        status=200,
        message="Settings reset to defaults",
        data=UserSettingsResponse(
            settings_id=settings.settings_id,
            user_id=settings.user_id,
            theme=settings.theme,
            default_citation_style=settings.default_citation_style,
            auto_save=settings.auto_save,
            notifications_enabled=settings.notifications_enabled,
            llm_preferences=settings.llm_preferences,
            research_preferences=settings.research_preferences,
            export_preferences=settings.export_preferences,
            created_at=settings.created_at,
            updated_at=settings.updated_at
        ).model_dump()
    )


# ===========================================
# LLM Models Info
# ===========================================

@router.get("/llm-models", response_model=APIResponse)
async def get_available_llm_models():
    """Get list of available LLM models."""
    models = [
        {
            "id": LLMProvider.DEEPSEEK.value,
            "name": "DeepSeek V3",
            "description": "Fast and efficient, best for most tasks",
            "default": True,
            "pricing": "Low cost"
        },
        {
            "id": LLMProvider.CLAUDE.value,
            "name": "Claude 3.5 Sonnet",
            "description": "Excellent reasoning and analysis",
            "default": False,
            "pricing": "Medium cost"
        },
        {
            "id": LLMProvider.GPT4.value,
            "name": "GPT-4 Turbo",
            "description": "Strong general purpose model",
            "default": False,
            "pricing": "Higher cost"
        }
    ]
    
    return APIResponse(
        status=200,
        message="Available LLM models",
        data={"models": models}
    )


@router.get("/citation-styles", response_model=APIResponse)
async def get_citation_styles():
    """Get list of supported citation styles."""
    styles = [
        {
            "id": "APA",
            "name": "APA 7th Edition",
            "description": "American Psychological Association style"
        },
        {
            "id": "MLA",
            "name": "MLA 9th Edition",
            "description": "Modern Language Association style"
        },
        {
            "id": "Chicago",
            "name": "Chicago 17th Edition",
            "description": "Chicago Manual of Style"
        },
        {
            "id": "Harvard",
            "name": "Harvard Referencing",
            "description": "Harvard citation system"
        }
    ]
    
    return APIResponse(
        status=200,
        message="Available citation styles",
        data={"styles": styles}
    )
