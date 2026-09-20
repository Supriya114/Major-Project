from app.api import developer as developer_api


class FakeResult:
    modified_count = 1


class FakeProjects:
    def update_many(self, *args, **kwargs):
        return FakeResult()


class FakeDB:
    projects = FakeProjects()


def test_recover_interrupted_generations_runs():
    developer_api.recover_interrupted_generations(FakeDB())
