from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Modèle Utilisateur"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.Text, default="")
    avatar = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(20), default="user")  # 'user' ou 'admin'
    is_active = db.Column(db.Boolean, default=True)
    telegram_chat_id = db.Column(
        db.String(50), nullable=True
    )  # Pour recevoir les photos
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relations
    publications = db.relationship(
        "Publication", backref="author", lazy="dynamic", cascade="all, delete-orphan"
    )
    sent_messages = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        backref="sender",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    received_messages = db.relationship(
        "Message",
        foreign_keys="Message.receiver_id",
        backref="receiver",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        """Hasher le mot de passe"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Vérifier le mot de passe"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Vérifier si l'utilisateur est admin"""
        return self.role == "admin"

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "fullname": self.fullname,
            "bio": self.bio,
            "avatar": self.avatar,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User {self.username}>"


class Category(db.Model):
    """Modèle Catégorie de vidéos"""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), default="")
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    publications = db.relationship("Publication", backref="category", lazy="dynamic")

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
        }

    def __repr__(self):
        return f"<Category {self.name}>"


class Publication(db.Model):
    """Modèle Publication (Vidéo)"""

    __tablename__ = "publications"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    filename = db.Column(db.String(256), nullable=False)
    thumbnail = db.Column(db.String(256), nullable=True)
    status = db.Column(
        db.String(20), default="pending"
    )  # 'pending', 'approved', 'rejected'
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    duration = db.Column(db.Integer, default=0)  # Durée en secondes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Clés étrangères
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

    def increment_views(self):
        """Incrémenter le compteur de vues"""
        self.views += 1

    def increment_likes(self):
        """Incrémenter le compteur de likes"""
        self.likes += 1

    def approve(self):
        """Approuver la publication"""
        self.status = "approved"

    def reject(self):
        """Rejeter la publication"""
        self.status = "rejected"

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "filename": self.filename,
            "thumbnail": self.thumbnail,
            "status": self.status,
            "views": self.views,
            "likes": self.likes,
            "duration": self.duration,
            "category": self.category.name if self.category else None,
            "category_id": self.category_id,
            "author": self.author.username if self.author else None,
            "author_fullname": self.author.fullname if self.author else None,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Publication {self.title}>"


class Conversation(db.Model):
    """Modèle Conversation entre deux utilisateurs"""

    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relations
    user1 = db.relationship("User", foreign_keys=[user1_id])
    user2 = db.relationship("User", foreign_keys=[user2_id])
    messages = db.relationship(
        "Message", backref="conversation", lazy="dynamic", cascade="all, delete-orphan"
    )

    @staticmethod
    def get_or_create(user1_id, user2_id):
        """Obtenir ou créer une conversation entre deux utilisateurs"""
        # S'assurer que user1_id < user2_id pour éviter les doublons
        if user1_id > user2_id:
            user1_id, user2_id = user2_id, user1_id

        conv = Conversation.query.filter_by(
            user1_id=user1_id, user2_id=user2_id
        ).first()
        if not conv:
            conv = Conversation(user1_id=user1_id, user2_id=user2_id)
            db.session.add(conv)
            db.session.commit()
        return conv

    def get_room_id(self):
        """Générer l'ID de room pour Socket.IO"""
        return f"conv_{self.id}"

    def __repr__(self):
        return f"<Conversation {self.user1_id} <-> {self.user2_id}>"


class Message(db.Model):
    """Modèle Message dans une conversation"""

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(
        db.String(20), default="text"
    )  # 'text', 'image', 'ephemeral'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Clés étrangères
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False
    )
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "content": self.content,
            "message_type": self.message_type,
            "is_read": self.is_read,
            "sender_id": self.sender_id,
            "sender_username": self.sender.username if self.sender else None,
            "sender_fullname": self.sender.fullname if self.sender else None,
            "receiver_id": self.receiver_id,
            "timestamp": self.created_at.strftime("%H:%M") if self.created_at else None,
            "date": self.created_at.strftime("%Y-%m-%d") if self.created_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Message {self.id} from {self.sender_id}>"


class EphemeralPhoto(db.Model):
    """Modèle Photo Éphémère"""

    __tablename__ = "ephemeral_photos"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    is_viewed = db.Column(db.Boolean, default=False)
    is_sent_telegram = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Clés étrangères
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=True
    )

    # Relations
    sender = db.relationship("User", foreign_keys=[sender_id])
    receiver = db.relationship("User", foreign_keys=[receiver_id])

    def mark_as_viewed(self):
        """Marquer comme vue"""
        self.is_viewed = True

    def mark_as_sent_telegram(self):
        """Marquer comme envoyée sur Telegram"""
        self.is_sent_telegram = True

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "filename": self.filename,
            "is_viewed": self.is_viewed,
            "is_sent_telegram": self.is_sent_telegram,
            "sender_id": self.sender_id,
            "sender_username": self.sender.username if self.sender else None,
            "receiver_id": self.receiver_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<EphemeralPhoto {self.id}>"


class Like(db.Model):
    """Modèle Like sur une publication (évite les doublons)"""

    __tablename__ = "likes"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Clés étrangères
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    publication_id = db.Column(
        db.Integer, db.ForeignKey("publications.id"), nullable=False
    )

    # Contrainte d'unicité
    __table_args__ = (
        db.UniqueConstraint("user_id", "publication_id", name="unique_like"),
    )

    def __repr__(self):
        return f"<Like user={self.user_id} pub={self.publication_id}>"


class View(db.Model):
    """Modèle View pour tracker les vues uniques par utilisateur/session"""

    __tablename__ = "views"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Clés étrangères
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )  # Peut être null pour visiteurs
    publication_id = db.Column(
        db.Integer, db.ForeignKey("publications.id"), nullable=False
    )

    # Session ID pour les visiteurs non connectés
    session_id = db.Column(db.String(100), nullable=True)

    # IP pour éviter les abus (optionnel)
    ip_address = db.Column(db.String(50), nullable=True)

    # Index pour améliorer les performances des requêtes
    __table_args__ = (
        db.Index("idx_user_publication", "user_id", "publication_id"),
        db.Index("idx_session_publication", "session_id", "publication_id"),
    )

    @staticmethod
    def has_viewed(publication_id, user_id=None, session_id=None):
        """Vérifier si l'utilisateur/session a déjà vu la publication"""
        if user_id:
            existing = View.query.filter(
                View.user_id == user_id, View.publication_id == publication_id
            ).first()
            return existing is not None
        elif session_id:
            existing = View.query.filter(
                View.session_id == session_id, View.publication_id == publication_id
            ).first()
            return existing is not None
        return False

    @staticmethod
    def add_view(publication_id, user_id=None, session_id=None, ip_address=None):
        """Ajouter une vue si pas déjà vue"""
        # Vérifier si déjà vue
        if View.has_viewed(publication_id, user_id, session_id):
            return False  # Déjà vue

        # Créer la nouvelle vue
        view = View(
            publication_id=publication_id,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
        )
        try:
            db.session.add(view)
            db.session.flush()  # Flush pour détecter les erreurs sans commit
            return True  # Nouvelle vue ajoutée
        except Exception:
            db.session.rollback()
            return False  # Erreur (probablement doublon)

    def __repr__(self):
        return f"<View user={self.user_id} session={self.session_id} pub={self.publication_id}>"


class Comment(db.Model):
    """Modèle Commentaire sur une publication"""

    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Clés étrangères
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    publication_id = db.Column(
        db.Integer, db.ForeignKey("publications.id"), nullable=False
    )

    # Relations
    user = db.relationship("User", backref=db.backref("comments", lazy="dynamic"))
    publication = db.relationship(
        "Publication", backref=db.backref("comments", lazy="dynamic")
    )

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "content": self.content,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "fullname": self.user.fullname if self.user else None,
            "avatar": self.user.avatar if self.user else None,
            "publication_id": self.publication_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "time_ago": self._time_ago(),
        }

    def _time_ago(self):
        """Retourne le temps écoulé depuis la création"""
        if not self.created_at:
            return ""
        now = datetime.utcnow()
        diff = now - self.created_at
        seconds = diff.total_seconds()

        if seconds < 60:
            return "À l'instant"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            return f"Il y a {minutes} min"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"Il y a {hours}h"
        elif seconds < 604800:
            days = int(seconds // 86400)
            return f"Il y a {days}j"
        else:
            return self.created_at.strftime("%d/%m/%Y")

    def __repr__(self):
        return f"<Comment {self.id} by {self.user_id}>"


class Notification(db.Model):
    """Modèle Notification pour les utilisateurs"""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(
        db.String(50), nullable=False
    )  # 'message', 'comment', 'like', 'follow'
    content = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Clés étrangères
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )  # Destinataire
    sender_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )  # Expéditeur (optionnel)
    publication_id = db.Column(
        db.Integer, db.ForeignKey("publications.id"), nullable=True
    )  # Publication liée (optionnel)
    comment_id = db.Column(
        db.Integer, db.ForeignKey("comments.id"), nullable=True
    )  # Commentaire lié (optionnel)

    # Relations
    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("notifications", lazy="dynamic"),
    )
    sender = db.relationship("User", foreign_keys=[sender_id])
    publication = db.relationship("Publication")
    comment = db.relationship("Comment")

    @staticmethod
    def create_notification(
        user_id, type, content, sender_id=None, publication_id=None, comment_id=None
    ):
        """Créer une notification"""
        # Ne pas notifier soi-même
        if sender_id and sender_id == user_id:
            return None

        notif = Notification(
            user_id=user_id,
            type=type,
            content=content,
            sender_id=sender_id,
            publication_id=publication_id,
            comment_id=comment_id,
        )
        db.session.add(notif)
        return notif

    @staticmethod
    def get_unread_count(user_id):
        """Obtenir le nombre de notifications non lues"""
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @staticmethod
    def mark_all_as_read(user_id):
        """Marquer toutes les notifications comme lues"""
        Notification.query.filter_by(user_id=user_id, is_read=False).update(
            {"is_read": True}
        )
        db.session.commit()

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "is_read": self.is_read,
            "sender_id": self.sender_id,
            "sender_username": self.sender.username if self.sender else None,
            "sender_fullname": self.sender.fullname if self.sender else None,
            "sender_avatar": self.sender.avatar if self.sender else None,
            "publication_id": self.publication_id,
            "comment_id": self.comment_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "time_ago": self._time_ago(),
        }

    def _time_ago(self):
        """Retourne le temps écoulé depuis la création"""
        if not self.created_at:
            return ""
        now = datetime.utcnow()
        diff = now - self.created_at
        seconds = diff.total_seconds()

        if seconds < 60:
            return "À l'instant"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            return f"Il y a {minutes} min"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"Il y a {hours}h"
        elif seconds < 604800:
            days = int(seconds // 86400)
            return f"Il y a {days}j"
        else:
            return self.created_at.strftime("%d/%m/%Y")

    def __repr__(self):
        return f"<Notification {self.id} for {self.user_id}>"


# Fonction d'initialisation de la base de données
def init_db(app):
    """Initialiser la base de données"""
    db.init_app(app)

    with app.app_context():
        # Créer toutes les tables
        db.create_all()

        # Créer les catégories par défaut si elles n'existent pas
        from config import Config

        if Category.query.count() == 0:
            for i, cat_name in enumerate(Config.DEFAULT_CATEGORIES):
                category = Category(name=cat_name, order=i)
                db.session.add(category)

        # Créer un admin par défaut si aucun utilisateur n'existe
        if User.query.count() == 0:
            admin = User(
                username="admin",
                email="admin@thesauce.com",
                fullname="Administrateur",
                role="admin",
                is_active=True,
            )
            admin.set_password("admin123")
            db.session.add(admin)

            # Créer quelques utilisateurs de test
            user1 = User(
                username="user1",
                email="user1@thesauce.com",
                fullname="Jean Dupont",
                role="user",
                is_active=True,
            )
            user1.set_password("password1")
            db.session.add(user1)

            user2 = User(
                username="user2",
                email="user2@thesauce.com",
                fullname="Marie Martin",
                role="user",
                is_active=True,
            )
            user2.set_password("password2")
            db.session.add(user2)

        db.session.commit()
        print("[OK] Base de donnees initialisee avec succes!")
