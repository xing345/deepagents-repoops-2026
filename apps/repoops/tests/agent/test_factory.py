import sys
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from repoops.agent_factory import create_repoops_agent
from repoops.application import RepoOpsApplication
from repoops.security.policy import ExecutionPolicy


def test_factory_builds_deep_agent_without_external_model_api(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    policy = ExecutionPolicy(
        workspace_root=sample_repository,
        allowed_executables=frozenset({Path(sys.executable).name}),
    )
    app = RepoOpsApplication(sample_repository, tmp_path / "state", policy=policy)
    app.rebuild_index()
    model = FakeListChatModel(responses=["ready"])

    agent = create_repoops_agent(model, app)

    assert agent is not None
