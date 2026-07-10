import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.services import ChronicleService

@pytest.mark.asyncio
async def test_list_chronicles():
    repo = MagicMock(spec=ChronicleRepository)
    repo.get_all = AsyncMock(return_value=[])
    
    service = ChronicleService(repo)
    result = await service.list_chronicles()
    
    assert result == []
    repo.get_all.assert_called_once()

@pytest.mark.asyncio
async def test_create_chronicle():
    repo = MagicMock(spec=ChronicleRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)
    
    service = ChronicleService(repo)
    result = await service.create_chronicle("New Chronicle")
    
    assert result.title == "New Chronicle"
    repo.create.assert_called_once()
