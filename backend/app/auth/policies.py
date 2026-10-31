"""RBAC policy helpers shared across domains."""

from app.users.models import UserRole


def can_register_for_events(role: UserRole | str) -> bool:
    try:
        return UserRole(role) == UserRole.ATTENDEE
    except ValueError:
        return False
