from chronicler.core.models import TranscriptLine
from chronicler.core.repositories import TranscriptRepository
from chronicler.core.rpc import service


@service
class TranscriptService:
    def __init__(self, repository: TranscriptRepository):
        self.repository = repository

    async def get_transcript(self) -> list[TranscriptLine]:
        return await self.repository.get_lines()

    async def update_line(self, line: TranscriptLine) -> TranscriptLine:
        # For now, let's just implement the get.
        # Update would need finding the line and updating it.
        # But for this task, we mostly need display.
        return line
