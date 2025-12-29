import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """Configuration de base"""

    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY") or "thesauce_secret_key_2024"

    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or f"sqlite:///{os.path.join(BASE_DIR, 'thesauce.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    AVATAR_FOLDER = os.path.join(BASE_DIR, "static", "avatars")
    EPHEMERAL_FOLDER = os.path.join(BASE_DIR, "static", "ephemeral")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max

    # Extensions autorisées
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm"}
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

    # Telegram Bot API
    TELEGRAM_BOT_TOKEN = "8584470249:AAEgOPZKy1ldTC6VOfpHyIX_ucaOwUESGKY"
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or None  # À configurer

    # Catégories par défaut
    DEFAULT_CATEGORIES = [
        "Divertissement",
        "Gaming",
        "Musique",
        "Sport",
        "Tutoriel",
        "Vlog",
        "Autre",
    ]


class DevelopmentConfig(Config):
    """Configuration de développement"""

    DEBUG = True


class ProductionConfig(Config):
    """Configuration de production"""

    DEBUG = False


# Configuration active
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
