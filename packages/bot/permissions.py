def is_admin(member_role_ids: list[int], admin_role_id: int | None) -> bool:
    if not admin_role_id:
        return False
    return admin_role_id in member_role_ids


ADMIN_ONLY_MESSAGE = "⛔ This command is restricted to RansomWatch admins."
