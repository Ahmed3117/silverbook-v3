"""
Django settings for core project.
Django 5.1.2
"""

from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os

#^ Load environment variables from .env file
load_dotenv(override=True) 

#^ Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

#^ SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-dbpx)!#%s!#n^&&r^e0!t&ot$vit@t8++_=1*)#84ym)j-v@(w'

#^ SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost','127.0.0.1','13.49.226.161','api2.bookefay.com']


#^ Application definition 

INSTALLED_APPS = [ 
    'boto3',
    'admin_interface',
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    #* Libs
    'corsheaders',
    'django_filters',
    'rest_framework',
    'rest_framework_api_key',
    'rest_framework_simplejwt',
    'storages',
    #* Apps
    'accounts',
    'products',
    'analysis',
]
AUTH_USER_MODEL ='accounts.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# ^ DATABASES
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'ecom_db',           # the database you created
#         'USER': 'postgres',          # default postgres user
#         'PASSWORD': 'withALLAH', # the one you set during install
#         'HOST': 'localhost',         # since it's local
#         'PORT': '5432',              # default PostgreSQL port
#     }
# }



#^ Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


#^ Internationalization
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


#^ < ==========================Static Files========================== >
STATIC_URL = 'static/'
#STATICFILES_DIRS = os.path.join(BASE_DIR, 'static')
STATIC_ROOT = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATA_UPLOAD_MAX_NUMBER_FIELDS=50000


#^ < ==========================Email========================== >
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'platraincloud@gmail.com'
EMAIL_HOST_PASSWORD = 'meczfpooichwkudl'

#^ < ==========================CACHES CONFIG========================== >

# CACHES = {
#     'default': {
#         'BACKEND': 'django_redis.cache.RedisCache',
#         'LOCATION': 'redis://127.0.0.1:6379/1',  
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#         }
#     }
# }


#^ < ==========================REST FRAMEWORK SETTINGS========================== >

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'accounts.authentication.MultiDeviceJWTAuthentication',  # Custom JWT auth with multi-device enforcement for students
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],
    
    #'DEFAULT_THROTTLE_CLASSES': [
    #    'rest_framework.throttling.AnonRateThrottle',    # For anonymous users
    #    'rest_framework.throttling.UserRateThrottle',    # For authenticated users
    #],

    #'DEFAULT_THROTTLE_RATES': {
    #    'anon': '200/day',   # Limit anonymous users to 10 requests per day
    #    'user': '3000/hour' # Limit authenticated users to 1000 requests per hour
    #},

    'DEFAULT_PAGINATION_CLASS': 'accounts.pagination.CustomPageNumberPagination',
    'PAGE_SIZE': 100,
}




# ^ < ==========================AUTHENTICATION CONFIG========================== >

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=3),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=3),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": "Bearer",
    "AUTH_HEADER_NAME": "HTTP_AUTH",
    'TOKEN_OBTAIN_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenObtainPairSerializer',
}

# ^ < ==========================CORS ORIGIN CONFIG========================== >

CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'Auth',
    'Authorization',
    'Content-Type',  
]

CORS_ALLOW_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
]


# ^ < ==========================WHATSAPP CONFIG========================== >

#* WHATSAPP CREDENTIALS
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_ID = os.getenv('WHATSAPP_ID')

# ^ < ==========================BEON SMS CONFIG========================== >

BEON_SMS_BASE_URL = os.getenv('BEON_SMS_BASE_URL', 'https://v3.api.beon.chat/api/v3/messages/sms/bulk')
BEON_SMS_TOKEN = os.getenv('BEON_SMS_TOKEN', 'XCuzhHqoHZXY21F5PdK0NMZDWKy67NoHG4Trscg#5ghFVrKadomBDaa024CV')

# ^ < ==========================AWS / Cloudflare R2 Storage CONFIG========================== >

# Cloudflare R2 Configuration (S3-compatible)
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL')  # R2 endpoint
AWS_S3_CUSTOM_DOMAIN = os.getenv('AWS_S3_CUSTOM_DOMAIN')  # Public CDN domain

# S3 Settings
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_REGION_NAME = 'auto'  # R2 uses 'auto' for region
AWS_S3_FILE_OVERWRITE = False  # Don't overwrite files with same name
AWS_DEFAULT_ACL = None  # R2 doesn't support ACLs
AWS_QUERYSTRING_AUTH = False  # Use custom domain without query strings for public files
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',  # Cache files for 1 day
}

# Toggle S3 storage on/off (useful for local development)
USE_S3_STORAGE = os.getenv('USE_S3_STORAGE', 'False').lower() == 'true'

if USE_S3_STORAGE:
    # Use S3 for all file storage
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    # Media files will be served from the custom domain
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
else:
    # Use local file storage (for development)
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    MEDIA_URL = 'media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')



# ^ < ==========================Payment CONFIG========================== >

ACTIVE_SITE_NAME = os.getenv('ACTIVE_SITE_NAME', 'silverbook')

# Payment Gateway Configuration
ACTIVE_PAYMENT_METHOD = os.getenv('ACTIVE_PAYMENT_METHOD', 'easypay').lower()  # 'shakeout' or 'easypay'

# Site URL
SITE_URL = os.getenv('SITE_URL', 'https://silverbook.easy-stream.net')

# Shake-out Configuration - with fallbacks and validation
SHAKEOUT_API_KEY = os.getenv('SHAKEOUT_API_KEY', '')
SHAKEOUT_SECRET_KEY = os.getenv('SHAKEOUT_SECRET_KEY', '')
SHAKEOUT_BASE_URL = os.getenv('SHAKEOUT_BASE_URL', 'https://dash.shake-out.com/api/public/vendor')
SHAKEOUT_WEBHOOK_URL = os.getenv('SHAKEOUT_WEBHOOK_URL', f'{SITE_URL}/api/webhook/shakeout/')

# EasyPay Configuration
EASYPAY_VENDOR_CODE = os.getenv('EASYPAY_VENDOR_CODE', 'gomaa_elsayed_37045144337603')
EASYPAY_SECRET_KEY = os.getenv('EASYPAY_SECRET_KEY', 'de791d26-505e-450d-80e4-6b2dbb0fe775')
EASYPAY_BASE_URL = os.getenv('EASYPAY_BASE_URL', 'https://api.easy-adds.com/api')
EASYPAY_WEBHOOK_URL = os.getenv('EASYPAY_WEBHOOK_URL', f'{SITE_URL}/api/webhook/easypay/')
EASYPAY_PAYMENT_METHOD = os.getenv('EASYPAY_PAYMENT_METHOD', 'fawry')  # Default payment method
EASYPAY_PAYMENT_EXPIRY = int(os.getenv('EASYPAY_PAYMENT_EXPIRY', '172800000'))  # 48 hours in milliseconds


PILL_STATUS_URL = os.getenv('PILL_STATUS_URL', '')



# Your normal domain (orange cloud, cached, etc.)
DOMAIN = "silverbook.easy-stream.net"

# Bypass domain for large uploads (DNS-only / grey cloud in Cloudflare)
UPLOAD_DOMAIN = "easy.easy-stream.net"

# Optional: only use upload domain for files > 50 MB
USE_UPLOAD_SUBDOMAIN_FOR_LARGE_FILES = True
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50 MB

