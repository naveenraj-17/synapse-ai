"""The seam that lets a deployment speak on every session the store opens.

Why this exists at all: the engine's tenancy is the `tenant_id` column, and for
a plain install that is the whole of it. A deployment may enforce a *second*,
independent gate on the same rows — Postgres row-level security compares
against a per-transaction setting — and that cannot be said in a WHERE clause.
It has to be said on the connection, before the caller's first statement.

Nothing above `core/store/engine.py` can do that, because `collections.load()`
and its neighbours open their own sessions. By the time a caller holds a result
the opportunity has gone, and the failure is silent: rows the deployment can no
longer see look exactly like rows that were never written.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_binder():
    """Leave the module global as it was found, whatever the test did."""
    from core.store import engine

    yield
    engine.set_session_binder(None)


async def test_the_binder_runs_before_the_caller_sees_the_session():
    """Ordering is the whole point: `SET LOCAL` after the first read is a no-op
    that looks like it worked."""
    from core.store import collections, engine

    seen: list[str] = []

    async def binder(_s):
        seen.append("bound")

    engine.set_session_binder(binder)
    await collections.save("things", [{"id": "a"}])
    assert seen, "the binder never ran"

    before = len(seen)
    await collections.load("things")
    assert len(seen) > before, "a read opened a session without binding it"


async def test_a_binder_may_issue_statements_on_the_transaction():
    """It receives the live session, not a copy — that is what makes it useful."""
    from sqlalchemy import text

    from core.store import collections, engine

    async def binder(s):
        # A statement every dialect accepts, so this test says something on
        # SQLite as well as on the Postgres deployments the seam exists for.
        await s.execute(text("SELECT 1"))

    engine.set_session_binder(binder)
    await collections.save("things", [{"id": "a"}])
    assert [i["id"] for i in await collections.load("things")] == ["a"]


async def test_a_failing_binder_is_not_swallowed():
    """A binder exists to satisfy an access rule.

    Swallowing its failure would turn "this deployment's isolation is not in
    force" into "that table appears to be empty" — the harder of the two bugs
    by a wide margin, and the one that gets diagnosed as a missing feature.
    """
    from core.store import collections, engine

    class Refused(Exception):
        pass

    async def binder(_s):
        raise Refused("no")

    engine.set_session_binder(binder)
    with pytest.raises(Refused):
        await collections.load("things")


async def test_no_binder_is_the_ordinary_case():
    """The shipped product installs none, and pays an `is None` for the seam."""
    from core.store import collections, engine

    engine.set_session_binder(None)
    await collections.save("things", [{"id": "a"}])
    assert [i["id"] for i in await collections.load("things")] == ["a"]
