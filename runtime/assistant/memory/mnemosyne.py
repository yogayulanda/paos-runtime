from .local import LocalMemoryProvider
from .provider import MemoryHealth, MemoryItem, MemoryQuery, MemoryWrite, MemoryWriteResult


class MnemosyneMemoryProvider(LocalMemoryProvider):
    name = "mnemosyne"

    def healthcheck(self) -> MemoryHealth:
        health = super().healthcheck()
        return MemoryHealth(
            provider=self.name,
            healthy=False,
            warning=True,
            message=(
                "Mnemosyne is not integrated yet; using local JSONL-backed placeholder only."
            ),
            details={
                "path": str(self.path),
                "placeholder": True,
                "fallback_health": health.to_dict(),
            },
        )

    def recall(self, query: MemoryQuery) -> list[MemoryItem]:
        return super().recall(query)

    def write(self, item: MemoryWrite) -> MemoryWriteResult:
        result = super().write(item)
        return MemoryWriteResult(
            ok=result.ok,
            item=result.item,
            path=result.path,
            warning="Mnemosyne placeholder wrote to local JSONL storage.",
        )
