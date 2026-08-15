"""
API keys are a table, looked up by hash.

They were a JSON file read whole on every authenticated request, so the auth
path's cost grew with the number of keys a user had ever created. As a row with
an indexed hash it is a point lookup.

The lookup is deliberately not tenant-scoped — a request arrives carrying only
the key, so this call is what *establishes* the tenant. These tests pin that,
and the thing it must not become: a key must not authenticate as a tenant that
does not own it.
"""
import pytest

from core import api_keys
from core.scale.context import set_resource_provider
from core.tenancy import tenant_scope


class _Provider:
    async def resolve_agent(self, agent_id):
        return None

    async def resolve_orchestration(self, orch_id):
        return None

    async def resolve_custom_tools(self):
        return []

    async def resolve_mcp_servers(self):
        return []


@pytest.fixture
def multi_tenant():
    set_resource_provider(_Provider())
    yield
    set_resource_provider(None)


@pytest.mark.asyncio
async def test_a_generated_key_validates():
    raw, record = await api_keys.generate_api_key("ci")

    validated = await api_keys.validate_api_key(raw)
    assert validated is not None
    assert validated["id"] == record["id"]


@pytest.mark.asyncio
async def test_the_raw_key_is_never_stored():
    raw, _ = await api_keys.generate_api_key("ci")

    listed = await api_keys.list_api_keys()
    assert raw not in str(listed)
    assert all("key_hash" not in k for k in listed)


@pytest.mark.asyncio
async def test_a_revoked_key_stops_validating():
    raw, record = await api_keys.generate_api_key("ci")

    assert await api_keys.revoke_api_key(record["id"]) is True
    assert await api_keys.validate_api_key(raw) is None


@pytest.mark.asyncio
async def test_a_deleted_key_stops_validating():
    raw, record = await api_keys.generate_api_key("ci")

    assert await api_keys.delete_api_key(record["id"]) is True
    assert await api_keys.delete_api_key(record["id"]) is False
    assert await api_keys.validate_api_key(raw) is None


@pytest.mark.asyncio
async def test_garbage_is_rejected_without_touching_the_store():
    assert await api_keys.validate_api_key("") is None
    assert await api_keys.validate_api_key("not-a-synapse-key") is None


@pytest.mark.asyncio
async def test_validation_reports_the_owning_tenant(multi_tenant):
    """The key is the only thing a request carries, so it carries the tenant."""
    with tenant_scope("acme"):
        raw, _ = await api_keys.generate_api_key("acme's key")

    # Validated from outside any scope — this call is what establishes it.
    validated = await api_keys.validate_api_key(raw)
    assert validated["tenant_id"] == "acme"


@pytest.mark.asyncio
async def test_listing_shows_only_the_current_tenants_keys(multi_tenant):
    with tenant_scope("acme"):
        await api_keys.generate_api_key("acme's")
    with tenant_scope("globex"):
        await api_keys.generate_api_key("globex's")
        assert [k["name"] for k in await api_keys.list_api_keys()] == ["globex's"]

    with tenant_scope("acme"):
        assert [k["name"] for k in await api_keys.list_api_keys()] == ["acme's"]


@pytest.mark.asyncio
async def test_a_tenant_cannot_revoke_another_tenants_key(multi_tenant):
    with tenant_scope("acme"):
        raw, record = await api_keys.generate_api_key("acme's")

    with tenant_scope("globex"):
        assert await api_keys.revoke_api_key(record["id"]) is False
        assert await api_keys.delete_api_key(record["id"]) is False

    assert await api_keys.validate_api_key(raw) is not None
