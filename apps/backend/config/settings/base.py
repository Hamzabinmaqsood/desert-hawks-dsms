from datetime import timedelta
from pathlib import Path

import django_stubs_ext
import environ

django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env(DJANGO_DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-local-development-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR.parent / "locale"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "dsms.common",
    "dsms.identity",
    "dsms.organization",
    "dsms.workforce",
    "dsms.documents",
    "dsms.finance",
    "dsms.billing",
    "dsms.recruitment",
    "dsms.training",
    "dsms.contracts",
    "dsms.deployment",
    "dsms.attendance",
    "dsms.supervision",
    "dsms.patrol",
    "dsms.incidents",
    "dsms.client_portal",
    "dsms.notifications",
    "dsms.leave",
    "dsms.assets",
    "dsms.hr_cases",
    "dsms.performance",
    "dsms.analytics",
    "dsms.audit",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://desert_hawks:change-me-local-only@db:5432/desert_hawks",
    )
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/1"),
    }
}
CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "notifications-process-pending": {
        "task": "dsms.notifications.tasks.process_pending_notification_events",
        "schedule": 60.0,
    },
    "notifications-mark-expired": {
        "task": "dsms.notifications.tasks.mark_expired_notifications",
        "schedule": 300.0,
    },
    "billing-generate-recurring-drafts": {
        "task": "dsms.billing.tasks.generate_recurring_billing_drafts",
        "schedule": 3600.0,
    },
    "billing-overdue-reminder-queue": {
        "task": "dsms.billing.tasks.queue_overdue_collection_reminders",
        "schedule": 3600.0,
    },
    "attendance-detect-missing-checkout": {
        "task": "dsms.attendance.tasks.detect_attendance_missing_checkout",
        "schedule": 300.0,
    },
    "patrol-detect-missed-tasks": {
        "task": "dsms.patrol.tasks.detect_missed_patrol_tasks",
        "schedule": 300.0,
    },
    "supervision-detect-overdue-actions": {
        "task": "dsms.supervision.tasks.detect_overdue_corrective_actions",
        "schedule": 900.0,
    },
    "incidents-reconcile-sla": {
        "task": "dsms.incidents.tasks.reconcile_incident_slas",
        "schedule": 300.0,
    },
}

AUTH_USER_MODEL = "identity.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": env.int("DJANGO_PASSWORD_MIN_LENGTH", default=10)},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR.parent / "media"
PRIVATE_MEDIA_ROOT = env.path("PRIVATE_MEDIA_ROOT", default=BASE_DIR.parent / "private-media")
DOCUMENT_MAX_UPLOAD_SIZE = env.int("DOCUMENT_MAX_UPLOAD_SIZE", default=10 * 1024 * 1024)
BILLING_SYSTEM_USER_ID = env.str("BILLING_SYSTEM_USER_ID", default="")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "dsms.common.exceptions.safe_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_RATES": {
        "login": env("DJANGO_LOGIN_THROTTLE_RATE", default="5/min"),
    },
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Desert Hawks DSMS API",
    "VERSION": "v1",
    "ENUM_NAME_OVERRIDES": {
        "PaymentBeneficiaryStatusEnum": "dsms.finance.payment_models.BeneficiaryStatus.choices",
        "PaymentBatchStatusEnum": "dsms.finance.payment_models.PaymentBatchStatus.choices",
        "PaymentInstructionStatusEnum": (
            "dsms.finance.payment_models.PaymentInstructionStatus.choices"
        ),
        "ProviderTransactionStatusEnum": (
            "dsms.finance.payment_models.ProviderTransactionStatus.choices"
        ),
        "PaymentSettlementStatusEnum": "dsms.finance.payment_models.SettlementStatus.choices",
        "BillingAdjustmentStatusEnum": "dsms.billing.enums.AdjustmentStatus.choices",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("DJANGO_ACCESS_TOKEN_LIFETIME_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("DJANGO_REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}
