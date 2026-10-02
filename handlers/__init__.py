"""Router assembly.

Order matters:
  1. admin router      — /admin and every "adm:*" callback (permission-guarded)
  2. user router tree  — behind the subscription gate:
       start -> submission -> user (fallbacks, must stay last)
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType

from ..middlewares import SubscriptionMiddleware
from . import admin, start, submission, user


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(admin.router)

    user_root = Router(name="user_root")
    user_root.message.filter(F.chat.type == ChatType.PRIVATE)
    gate = SubscriptionMiddleware()
    user_root.message.outer_middleware(gate)
    user_root.callback_query.outer_middleware(gate)
    user_root.include_router(start.router)
    user_root.include_router(submission.router)
    user_root.include_router(user.router)

    root.include_router(user_root)
    return root
