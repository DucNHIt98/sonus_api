from .settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.InMemoryStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

SUPABASE_URL = 'https://test.supabase.co'
SUPABASE_ANON_KEY = 'test-anon-key'
SUPABASE_JWT_SECRET = 'test-jwt-secret'
STRIPE_SECRET_KEY = 'sk_test_dummy'
STRIPE_PUBLISHABLE_KEY = 'pk_test_dummy'
STRIPE_WEBHOOK_SECRET = 'whsec_dummy'
STRIPE_PREMIUM_PRICE_ID = 'price_test'
GEMINI_API_KEY = 'test-gemini-key'
JAMENDO_CLIENT_ID = 'test-jamendo-client'
