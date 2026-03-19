from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Ensure models are imported so metadata is complete for Alembic.
import mealmetric.models.audit_log  # noqa: F401, E402
import mealmetric.models.auth_failure_tracker  # noqa: F401, E402
import mealmetric.models.metrics  # noqa: F401, E402
import mealmetric.models.order  # noqa: F401, E402
import mealmetric.models.order_item  # noqa: F401, E402
import mealmetric.models.payment_audit_log  # noqa: F401, E402
import mealmetric.models.payment_session  # noqa: F401, E402
import mealmetric.models.recommendation  # noqa: F401, E402
import mealmetric.models.role  # noqa: F401, E402
import mealmetric.models.stripe_webhook_event  # noqa: F401, E402
import mealmetric.models.subscription  # noqa: F401, E402
import mealmetric.models.training  # noqa: F401, E402
import mealmetric.models.user  # noqa: F401, E402
import mealmetric.models.user_role  # noqa: F401, E402
import mealmetric.models.vendor  # noqa: F401, E402
