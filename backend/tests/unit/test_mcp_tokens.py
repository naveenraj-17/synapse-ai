"""
MCP OAuth material as tenant-scoped blobs.

Access tokens, refresh tokens and dynamic client registrations were per-server
JSON files in one shared folder under DATA_DIR. They are tenant secrets: with
one folder, any tenant's stored credential for `github` is the credential every
tenant reconnects with.
"""
import pytest
from mcp.shared.auth import OAuthToken

from core.mcp_client import BlobTokenStorage, _safe_server_name
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


def _token(value="tok-1"):
    return OAuthToken(access_token=value, token_type="Bearer")


async def test_tokens_round_trip():
    storage = BlobTokenStorage("github")

    assert await storage.get_tokens() is None
    await storage.set_tokens(_token())
    assert (await storage.get_tokens()).access_token == "tok-1"


async def test_delete_all_removes_both_blobs():
    storage = BlobTokenStorage("github")
    await storage.set_tokens(_token())

    storage.delete_all()

    assert await storage.get_tokens() is None
    assert await storage.get_client_info() is None


async def test_one_tenants_token_is_not_anothers(multi_tenant):
    """The reason these left DATA_DIR.

    Same server name, two tenants: each must reconnect with its own
    credential, not with whichever was stored last.
    """
    with tenant_scope("acme"):
        await BlobTokenStorage("github").set_tokens(_token("acme-token"))

    with tenant_scope("globex"):
        assert await BlobTokenStorage("github").get_tokens() is None
        await BlobTokenStorage("github").set_tokens(_token("globex-token"))

    with tenant_scope("acme"):
        assert (await BlobTokenStorage("github").get_tokens()).access_token == "acme-token"


@pytest.mark.parametrize("name,expected", [
    ("github", "github"),
    ("my server", "my_server"),
    ("scope/thing", "scope_thing"),
    ("../escape", "_escape"),
    ("..", "_"),
])
def test_server_names_cannot_shape_a_path(name, expected):
    """The old sanitiser replaced only `/` and spaces, so `../x` stayed
    traversal-shaped. The blob store's tenant guard would raise on that, which
    turns a badly-named server into a connection that cannot be made at all."""
    assert _safe_server_name(name) == expected
