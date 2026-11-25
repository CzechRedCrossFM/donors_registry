"""Application configuration.

Most configuration is set via environment variables.

For local development, use a .env file to set
environment variables.
"""

from environs import Env

env = Env()
env.read_env()  # reads .env file first

DEBUG = env.bool("FLASK_DEBUG", default=False)
SQLALCHEMY_DATABASE_URI = env.str("DATABASE_URL")
SQLALCHEMY_ECHO = DEBUG
SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "hide_parameters": not DEBUG}
SECRET_KEY = "N0-s0-s3CrEt-d3fAulT-KeY" if DEBUG else env.str("SECRET_KEY")
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
BCRYPT_LOG_ROUNDS = env.int("BCRYPT_LOG_ROUNDS", default=13)
DEBUG_TB_ENABLED = DEBUG
DEBUG_TB_INTERCEPT_REDIRECTS = False
SQLALCHEMY_TRACK_MODIFICATIONS = False
PERMANENT_SESSION_LIFETIME = 1800
SESSION_REFRESH_EACH_REQUEST = True

SMTP_SERVER = env.str("SMTP_SERVER")
SMTP_PORT = env.int("SMTP_PORT")
SMTP_LOGIN = env.str("SMTP_LOGIN")
SMTP_PASSWORD = env.str("SMTP_PASSWORD")
EMAIL_SENDER = env.str("EMAIL_SENDER")
