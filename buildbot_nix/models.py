from enum import Enum
from pathlib import Path

from buildbot.plugins import steps, util
from pydantic import BaseModel, ConfigDict, Field

from .secrets import read_secret_file


class InternalError(Exception):
    pass


def exclude_fields(fields: list[str]) -> dict[str, dict[str, bool]]:
    return {k: {"exclude": True} for k in fields}


class AuthBackendConfig(str, Enum):
    github = "github"
    gitea = "gitea"
    none = "none"


class CachixConfig(BaseModel):
    name: str

    signing_key_file: Path | None
    auth_token_file: Path | None

    @property
    def signing_key(self) -> str:
        if self.signing_key_file is None:
            raise InternalError
        return read_secret_file(self.signing_key_file)

    @property
    def auth_token(self) -> str:
        if self.auth_token_file is None:
            raise InternalError
        return read_secret_file(self.auth_token_file)

    # TODO why did the original implementation return an empty env if both files were missing?
    @property
    def environment(self) -> dict[str, str]:
        environment = {}
        environment["CACHIX_SIGNING_KEY"] = util.Secret(self.signing_key_file)
        environment["CACHIX_AUTH_TOKEN"] = util.Secret(self.auth_token_file)
        return environment

    class Config:
        fields = exclude_fields(["signing_key", "auth_token"])


class GiteaConfig(BaseModel):
    instance_url: str
    topic: str | None

    token_file: Path = Field(default=Path("gitea-token"))
    webhook_secret_file: Path = Field(default=Path("gitea-webhook-secret"))
    project_cache_file: Path = Field(default=Path("gitea-project-cache.json"))

    oauth_id: str | None
    oauth_secret_file: Path | None

    @property
    def token(self) -> str:
        return read_secret_file(self.token_file)

    @property
    def webhook_secret(self) -> str:
        return read_secret_file(self.webhook_secret_file)

    @property
    def oauth_secret(self) -> str:
        if self.oauth_secret_file is None:
            raise InternalError
        return read_secret_file(self.oauth_secret_file)

    class Config:
        fields = exclude_fields(["token", "webhook_secret", "oauth_secret"])


class GitHubLegacyConfig(BaseModel):
    token_file: Path

    @property
    def token(self) -> str:
        return read_secret_file(self.token_file)

    class Config:
        fields = exclude_fields(["token"])


class GitHubAppConfig(BaseModel):
    id: int

    secret_key_file: Path
    installation_token_map_file: Path = Field(
        default=Path("github-app-installation-token-map.json")
    )
    project_id_map_file: Path = Field(
        default=Path("github-app-project-id-map-name.json")
    )
    jwt_token_map: Path = Field(default=Path("github-app-jwt-token"))

    @property
    def secret_key(self) -> str:
        return read_secret_file(self.secret_key_file)

    class Config:
        fields = exclude_fields(["secret_key"])


class GitHubConfig(BaseModel):
    auth_type: GitHubLegacyConfig | GitHubAppConfig
    topic: str | None

    project_cache_file: Path = Field(default=Path("github-project-cache-v1.json"))
    webhook_secret_file: Path = Field(default=Path("github-webhook-secret"))

    oauth_id: str | None
    oauth_secret_file: Path | None

    @property
    def webhook_secret(self) -> str:
        return read_secret_file(self.webhook_secret_file)

    @property
    def oauth_secret(self) -> str:
        if self.oauth_secret_file is None:
            raise InternalError
        return read_secret_file(self.oauth_secret_file)


# note that serialization isn't correct, as there is no way to *rename* the field `nix_type` to `_type`,
# one must always specify `by_alias = True`, such as `model_dump(by_alias = True)`, relevant issue:
# https://github.com/pydantic/pydantic/issues/8379
class Interpolate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nix_type: str = Field(alias="_type")
    value: str


class PostBuildStep(BaseModel):
    name: str
    environment: dict[str, str | Interpolate]
    command: list[str | Interpolate]

    def to_buildstep(self) -> steps.BuildStep:
        def maybe_interpolate(value: str | Interpolate) -> str | util.Interpolate:
            if isinstance(value, str):
                return value
            return util.Interpolate(value.value)

        return steps.ShellCommand(
            name=self.name,
            env={k: maybe_interpolate(k) for k in self.environment},
            command=[maybe_interpolate(x) for x in self.command],
        )


class BuildbotNixConfig(BaseModel):
    db_url: str
    auth_backend: AuthBackendConfig
    build_retries: int
    cachix: CachixConfig | None
    gitea: GiteaConfig | None
    github: GitHubConfig | None
    admins: list[str]
    workers_file: Path
    build_systems: list[str]
    eval_max_memory_size: int
    eval_worker_count: int | None
    nix_workers_secret_file: Path = Field(default=Path("buildbot-nix-workers"))
    domain: str
    webhook_base_url: str
    use_https: bool
    outputs_path: Path | None
    url: str
    post_build_steps: list[PostBuildStep]
    job_report_limit: int | None

    @property
    def nix_workers_secret(self) -> str:
        return read_secret_file(self.nix_workers_secret_file)
