from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ArtifactMeta:
    path: str | None
    exists: bool
    date: str | None
    modified_at: str | None
    size_bytes: int | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedArtifacts:
    digest: ArtifactMeta
    insight: ArtifactMeta
    runtime_statuses: list[ArtifactMeta]

    def to_dict(self) -> dict:
        return {
            "digest": self.digest.to_dict(),
            "insight": self.insight.to_dict(),
            "runtime_statuses": [item.to_dict() for item in self.runtime_statuses],
        }
