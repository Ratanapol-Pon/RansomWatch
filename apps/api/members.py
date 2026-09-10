"""Explicit operator enrollment; dashboard users cannot grant themselves roles."""

import argparse
from uuid import UUID

from packages.shared.db import get_session
from packages.shared.models import DashboardMember


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, type=UUID, help="Supabase Auth user UUID")
    parser.add_argument("--role", choices=["viewer", "analyst", "admin"], default="viewer")
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    with get_session() as session:
        member = session.get(DashboardMember, args.user_id)
        if member is None:
            member = DashboardMember(user_id=args.user_id)
            session.add(member)
        member.role, member.enabled = args.role, not args.disable
    print("Dashboard membership updated.")


if __name__ == "__main__":
    main()
