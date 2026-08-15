"""
Resolving an execution's agents, custom tools and MCP servers.

These three lookups are the engine's per-run resource resolution. They used to
be "Postgres first, local JSON if that returns nothing", gated on a
process-global ``IS_SCALE_WORKER`` flag — and the Postgres half carried **no
tenant predicate at all**: ``select(ToolDB)`` returned every tenant's custom
tools, on every worker, for every run.

Now there is one path. The store is the source of truth, scoped to
``core.tenancy.get_tenant()``. An embedder that needs to resolve resources some
other way — from its own schema, with its own row-level security, decrypting
credentials on the way — registers a provider and answers all three itself.

Fail closed
-----------
When a provider is registered it is the *only* source. There is deliberately no
fallback to the local store if the provider returns nothing: a fallback is how
an authorization failure turns into another tenant's data. An empty answer is
an answer.
"""
from __future__ import annotations

from typing import Protocol

from core.tenancy import disable_multi_tenancy, enable_multi_tenancy


class ResourceProvider(Protocol):
    """How an embedder answers the engine's resource lookups.

    Every method is called with the tenant already established in the context;
    implementations read ``core.tenancy.get_tenant()``.

    ``resolve_orchestration`` is a lookup by id, not a listing. Listing every
    orchestration is a UI concern, and requiring an embedder to expose one to
    run a workflow would be the wrong default; the store answers those directly.
    """

    async def resolve_agent(self, agent_id: str) -> dict | None: ...
    async def resolve_orchestration(self, orch_id: str) -> dict | None: ...
    async def resolve_custom_tools(self) -> list[dict]: ...
    async def resolve_mcp_servers(self) -> list[dict]: ...


_provider: ResourceProvider | None = None


def set_resource_provider(provider: ResourceProvider | None) -> None:
    """Install a resource provider, and with it, multi-tenancy.

    Registering a provider is what unlocks ``core.tenancy.tenant_scope()``.
    The two are deliberately coupled: switching tenants without a tenant-aware
    way to resolve resources would hand every tenant the same agents and tools,
    which is worse than refusing to switch at all.
    """
    global _provider
    _provider = provider
    if provider is None:
        disable_multi_tenancy()
    else:
        enable_multi_tenancy()


def get_resource_provider() -> ResourceProvider | None:
    return _provider


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------

async def resolve_agent(agent_id: str) -> dict | None:
    """The agent definition for `agent_id`, within the current tenant."""
    if not agent_id:
        return None
    if _provider is not None:
        return await _provider.resolve_agent(agent_id)

    from core.store.resources import get_agent

    return await get_agent(agent_id)


async def resolve_orchestration(orch_id: str) -> dict | None:
    """The orchestration definition for `orch_id`, within the current tenant.

    Routed through the provider like the others, because an orchestration is the
    resource that *names* every other one — its steps carry agent ids, forced
    tools and sub-orchestration ids. Resolving those through an embedder's
    row-level security while loading the orchestration itself straight from the
    store would bypass the boundary at the one place it matters most.
    """
    if not orch_id:
        return None
    if _provider is not None:
        return await _provider.resolve_orchestration(orch_id)

    from core.store.resources import get_orchestration

    return await get_orchestration(orch_id)


async def resolve_custom_tools() -> list[dict]:
    """Every custom tool belonging to the current tenant."""
    if _provider is not None:
        return await _provider.resolve_custom_tools()

    from core.store.resources import load_tools

    return await load_tools()


async def resolve_mcp_servers() -> list[dict]:
    """Every MCP server registered by the current tenant."""
    if _provider is not None:
        return await _provider.resolve_mcp_servers()

    from core.store.resources import load_mcp_servers

    return await load_mcp_servers()
