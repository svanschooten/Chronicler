from uuid import UUID

from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service


@service
class ChronicleService:
    def __init__(self, repository: ChronicleRepository):
        self.repository = repository

    async def list_chronicles(self) -> list[Chronicle]:
        return await self.repository.get_all()

    async def get_chronicle(self, chronicle_id: UUID) -> Chronicle | None:
        return await self.repository.get_by_id(chronicle_id)

    async def create_chronicle(self, title: str) -> Chronicle:
        chronicle = Chronicle(title=title)
        return await self.repository.create(chronicle)

    async def update_chronicle(self, chronicle: Chronicle) -> Chronicle:
        return await self.repository.update(chronicle)

    async def delete_chronicle(self, chronicle_id: UUID) -> None:
        return await self.repository.delete(chronicle_id)