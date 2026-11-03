# -*- coding: utf-8 -*-
from .account import router as account_router  # noqa: F401
from .auth import router as auth_router  # noqa: F401
from .child import router as child_router  # noqa: F401
from .extra import child_router as extra_child_router  # noqa: F401
from .extra import parent_router as extra_parent_router  # noqa: F401
from .misc import router as misc_router  # noqa: F401
from .parent import router as parent_router  # noqa: F401
from .textbook import child_router as book_child_router  # noqa: F401
from .textbook import common_router as book_common_router  # noqa: F401
from .textbook import parent_router as book_parent_router  # noqa: F401
from .wrong import child_router as wrong_child_router  # noqa: F401
from .wrong import parent_router as wrong_parent_router  # noqa: F401
