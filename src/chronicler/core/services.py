from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository

class ChronicleService:
    def __init__(self, repository: ChronicleRepository):
        self.repository = repository

    async def list_chronicles(self):
        return await self.repository.get_all()

    async def create_chronicle(self, title: str):
        chronicle = Chronicle(title=title)
        return await self.repository.create(chronicle)
