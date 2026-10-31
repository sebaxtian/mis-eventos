"""User administration business services."""

from datetime import datetime, timezone
import logging

from sqlalchemy import func
from sqlmodel import Session, select

from app.users.models import User, UserRole
from app.users.schemas import AdminUserUpdateRequest, UserListParams

logger = logging.getLogger(__name__)


class UserNotFoundError(Exception):
    """Raised when a user does not exist."""


class SelfRoleChangeNotAllowedError(Exception):
    """Raised when an admin attempts to change their own role."""


class SelfDeactivationNotAllowedError(Exception):
    """Raised when an admin attempts to deactivate their own account."""


class LastActiveAdminError(Exception):
    """Raised when an operation would leave no active administrator."""


def list_users(
    session: Session,
    params: UserListParams,
) -> tuple[list[User], int]:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)

    if params.role is not None:
        stmt = stmt.where(User.role == params.role.value)
        count_stmt = count_stmt.where(User.role == params.role.value)
    if params.is_active is not None:
        stmt = stmt.where(User.is_active == params.is_active)
        count_stmt = count_stmt.where(User.is_active == params.is_active)

    total = int(session.exec(count_stmt).one())
    items = list(
        session.exec(
            stmt.order_by(User.id).offset(params.offset).limit(params.size)
        ).all()
    )
    return items, total


def get_user_by_id(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError
    return user


def update_user_by_admin(
    session: Session,
    *,
    target_user_id: int,
    actor: User,
    payload: AdminUserUpdateRequest,
) -> User:
    target = get_user_by_id(session, target_user_id)
    if target.id == actor.id:
        if payload.role is not None:
            raise SelfRoleChangeNotAllowedError
        if payload.is_active is not None:
            raise SelfDeactivationNotAllowedError

    is_currently_active_admin = (
        UserRole(target.role) == UserRole.ADMIN and target.is_active
    )
    will_lose_active_admin = (
        payload.role is not None and payload.role != UserRole.ADMIN
    ) or (payload.is_active is False)

    if is_currently_active_admin and will_lose_active_admin:
        active_admins = list(
            session.exec(
                select(User)
                .where(
                    User.role == UserRole.ADMIN.value,
                    User.is_active.is_(True),  # type: ignore[attr-defined]
                )
                .order_by(User.id)
                .with_for_update()
            ).all()
        )
        remaining_active_admins = [
            admin for admin in active_admins if admin.id != target.id
        ]
        if not remaining_active_admins:
            raise LastActiveAdminError

    if payload.full_name is not None:
        target.full_name = payload.full_name
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
    target.updated_at = datetime.now(timezone.utc)
    session.add(target)
    session.commit()
    session.refresh(target)
    logger.info(
        "Admin user_id=%s updated target_user_id=%s role=%s is_active=%s",
        actor.id,
        target.id,
        target.role,
        target.is_active,
    )
    return target
