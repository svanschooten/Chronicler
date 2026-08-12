from chronicler.core.models import Chronicle, Speaker, Tag, Task
from chronicler.core.repositories import ChronicleRepository, TagRepository, TaskRepository
from chronicler.core.rpc import service


@service
class SearchService:
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
        # TODO search both the chronicle metadata and the tags and merge the results
        raise NotImplementedError("search_chronicle_meta is not implemented yet")

    async def search_chronicle_content(self, query: str) -> list[Chronicle]:
        # TODO do full text search on the chronicle line content
        raise NotImplementedError("search_chronicle_content is not implemented yet")

    async def search_tags(self, query: str) -> list[Tag]:
        # TODO search both the tag name and the tag description
        raise NotImplementedError("search_tags is not implemented yet")

    async def search_tasks(self, query: str) -> list[Task]:
        # TODO search both the task name, the task description, and the task payload
        raise NotImplementedError("search_tasks is not implemented yet")

    async def search_speakers(self, query: str) -> list[Speaker]:
        # TODO search the speaker by name
        raise NotImplementedError("search_speakers is not implemented yet")
