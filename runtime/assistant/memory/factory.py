from dataclasses import dataclass

from assistant.config import load_assistant_config

from .local import LocalMemoryProvider
from .mnemosyne import MnemosyneMemoryProvider
from .provider import MemoryHealth, MemoryProvider


@dataclass(frozen=True)
class MemoryProviderSelection:
    configured_provider: str
    active_provider: str
    fallback_used: bool
    attempted_providers: list[str]
    provider: MemoryProvider
    configured_health: MemoryHealth
    active_health: MemoryHealth

    def to_dict(self) -> dict:
        return {
            "configured_provider": self.configured_provider,
            "active_provider": self.active_provider,
            "fallback_used": self.fallback_used,
            "attempted_providers": self.attempted_providers,
            "configured_health": self.configured_health.to_dict(),
            "active_health": self.active_health.to_dict(),
        }


def _build_provider(name: str, config) -> MemoryProvider | None:
    if name == "local":
        return LocalMemoryProvider(config.memory.local_path)
    if name == "mnemosyne":
        return MnemosyneMemoryProvider(config.memory.mnemosyne_path)
    return None


def load_memory_provider():
    config = load_assistant_config()
    configured = _build_provider(config.memory.provider, config)
    fallback = _build_provider(config.memory.fallback_provider, config)
    local = _build_provider("local", config)

    if configured is None:
        configured_health = MemoryHealth(
            provider=config.memory.provider,
            healthy=False,
            warning=True,
            message=f"Unknown memory provider: {config.memory.provider}",
            details={"provider": config.memory.provider},
        )
    else:
        configured_health = configured.healthcheck()

    if configured is not None and configured_health.healthy:
        return MemoryProviderSelection(
            configured_provider=config.memory.provider,
            active_provider=config.memory.provider,
            fallback_used=False,
            attempted_providers=[config.memory.provider],
            provider=configured,
            configured_health=configured_health,
            active_health=configured_health,
        )

    attempts: list[tuple[str, MemoryProvider]] = []
    if fallback is not None and fallback is not configured:
        attempts.append((config.memory.fallback_provider, fallback))
    if local is not None:
        attempts.append(("local", local))

    for provider_name, provider in attempts:
        health = provider.healthcheck()
        if health.healthy:
            return MemoryProviderSelection(
                configured_provider=config.memory.provider,
                active_provider=provider_name,
                fallback_used=provider_name != config.memory.provider,
                attempted_providers=[config.memory.provider, provider_name],
                provider=provider,
                configured_health=configured_health,
                active_health=health,
            )

    fallback_health = MemoryHealth(
        provider=config.memory.fallback_provider,
        healthy=False,
        warning=False,
        message="No memory provider is available.",
        details={"fallback_provider": config.memory.fallback_provider},
    )
    return MemoryProviderSelection(
        configured_provider=config.memory.provider,
        active_provider=config.memory.fallback_provider,
        fallback_used=True,
        attempted_providers=[config.memory.provider, config.memory.fallback_provider, "local"],
        provider=configured or fallback or local,  # type: ignore[arg-type]
        configured_health=configured_health,
        active_health=fallback_health,
    )
