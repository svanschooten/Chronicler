from chronicler.core.models import Chronicle, Speaker, Tag, Task
from chronicler.core.repositories import ChronicleRepository, TagRepository, TaskRepository
from chronicler.core.rpc import service


@service
class SearchService:
    """Cross-entity search. Separate from the per-entity services because a search UI
    wants to query several kinds of thing at once, and because content search will
    eventually need its own index rather than a repository LIKE query.
    """

    def __init__(
        self,
        task_repository: TaskRepository,
        chronicle_repository: ChronicleRepository,
        tag_repository: TagRepository,
    ):
        self.task_repository = task_repository
        self.chronicle_repository = chronicle_repository
        self.tag_repository = tag_repository

    async def search_chronicle_meta(self, query: str) -> list[Chronicle]:
        """Chronicles matching `query` in their own metadata (title, description).
        Tag names are not searched yet - see TODO.md Phase 3."""
        return await self.chronicle_repository.search(query)

    async def search_tags(self, query: str) -> list[Tag]:
        return await self.tag_repository.search(query)

    async def search_tasks(self, query: str) -> list[Task]:
        return await self.task_repository.search(query)

    async def search_chronicle_content(self, query: str) -> list[Chronicle]:
        """Full-text search across transcript line content.

        Not implemented: unlike every other method here, this can't be a repository
        LIKE query. Transcript lines live in per-chronicle project databases, so
        answering it means either fanning out across every project db or maintaining a
        workspace-level FTS index. See TODO.md Phase 3.
        """
        raise NotImplementedError("Transcript content search needs an FTS index first")

    async def search_speakers(self, query: str) -> list[Speaker]:
        """Not implemented for the same reason as search_chronicle_content: speakers
        are per-project rows, not archive-level ones."""
        raise NotImplementedError("Speaker search needs per-project fan-out first")
