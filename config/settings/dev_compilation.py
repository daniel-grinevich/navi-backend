"""
Minimal settings for compilation only.
This file is used ONLY during Docker build for compilemessages.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "dummy-key-for-compilation-only"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []

# Only include the minimal set of apps needed for compilemessages
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    # Add only the bare minimum required apps here
]

# Minimal middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# Simple database config (not actually used)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Internationalization
USE_I18N = True
USE_TZ = True

# This is the important part for compilemessages
LOCALE_PATHS = [str(BASE_DIR / "locale")]
