from sqlalchemy import func, select

from apbra_api.persistence import CompanyRow, Database, ExternalIdentityRow, MembershipRow


def test_bootstrap_is_idempotent_and_server_controlled(database: Database) -> None:
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CompanyRow)) == 2
        assert db.scalar(select(func.count()).select_from(ExternalIdentityRow)) == 4
        assert db.scalar(select(func.count()).select_from(MembershipRow)) == 3
