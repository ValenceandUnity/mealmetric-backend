"""SQLAlchemy models."""

from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory, AuditLog
from mealmetric.models.auth_failure_tracker import AuthFailureTracker
from mealmetric.models.bookmark import BookmarkFolder, BookmarkItem
from mealmetric.models.metrics import (
    ActivityExpenditureRecord,
    CalorieIntakeRecord,
    ClientMetricSnapshot,
    DeficitTarget,
    DeficitTargetStatus,
    MetricRecordSource,
    StrengthMetricRollup,
    WeeklyMetricRollup,
)
from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItem, OrderItemType
from mealmetric.models.payment_audit_log import PaymentAuditLog, PaymentTransitionSource
from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.models.recommendation import (
    MealPlanRecommendation,
    MealPlanRecommendationStatus,
)
from mealmetric.models.role import Role as NormalizedRole
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.models.subscription import (
    MealPlanSubscription,
    MealPlanSubscriptionStatus,
    SubscriptionBillingInterval,
    SubscriptionInvoiceStatus,
)
from mealmetric.models.training import (
    AssignmentStatus,
    ChecklistItem,
    ClientTrainingPackageAssignment,
    PtClientLink,
    PtClientLinkStatus,
    PtFolder,
    PtProfile,
    Routine,
    TrainingPackage,
    TrainingPackageRoutine,
    TrainingPackageStatus,
    WorkoutCompletionStatus,
    WorkoutLog,
)
from mealmetric.models.user import Role, User
from mealmetric.models.user_role import UserRole
from mealmetric.models.vendor import (
    MealPlan,
    MealPlanAvailability,
    MealPlanAvailabilityStatus,
    MealPlanItem,
    MealPlanStatus,
    Vendor,
    VendorMenuItem,
    VendorMenuItemStatus,
    VendorPickupWindow,
    VendorPickupWindowStatus,
    VendorStatus,
)
from mealmetric.models.vendor_membership import VendorUserMembership

__all__ = [
    "ActivityExpenditureRecord",
    "AssignmentStatus",
    "AuditEventAction",
    "AuditEventCategory",
    "AuditLog",
    "AuthFailureTracker",
    "BookmarkFolder",
    "BookmarkItem",
    "CalorieIntakeRecord",
    "ChecklistItem",
    "ClientMetricSnapshot",
    "ClientTrainingPackageAssignment",
    "DeficitTarget",
    "DeficitTargetStatus",
    "MealPlan",
    "MealPlanAvailability",
    "MealPlanAvailabilityStatus",
    "MealPlanItem",
    "MealPlanRecommendation",
    "MealPlanRecommendationStatus",
    "MealPlanSubscription",
    "MealPlanSubscriptionStatus",
    "MealPlanStatus",
    "MetricRecordSource",
    "NormalizedRole",
    "Order",
    "OrderFulfillmentStatus",
    "OrderItem",
    "OrderItemType",
    "OrderPaymentStatus",
    "PaymentAuditLog",
    "PaymentSession",
    "PaymentStatus",
    "PaymentTransitionSource",
    "PtClientLink",
    "PtClientLinkStatus",
    "PtFolder",
    "PtProfile",
    "Role",
    "Routine",
    "StrengthMetricRollup",
    "SubscriptionBillingInterval",
    "SubscriptionInvoiceStatus",
    "StripeWebhookEvent",
    "TrainingPackage",
    "TrainingPackageRoutine",
    "TrainingPackageStatus",
    "User",
    "UserRole",
    "Vendor",
    "VendorMenuItem",
    "VendorMenuItemStatus",
    "VendorPickupWindow",
    "VendorPickupWindowStatus",
    "VendorUserMembership",
    "VendorStatus",
    "WebhookProcessingStatus",
    "WeeklyMetricRollup",
    "WorkoutCompletionStatus",
    "WorkoutLog",
]
