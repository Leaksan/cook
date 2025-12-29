"""
The Sauce - Application principale
Backend Flask avec SQLAlchemy et intégration Telegram
"""

import os
import uuid
from datetime import datetime
from functools import wraps

from config import Config, config
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import (
    Category,
    Comment,
    Conversation,
    EphemeralPhoto,
    Like,
    Message,
    Notification,
    Publication,
    User,
    View,
    db,
    init_db,
)
from telegram_service import get_telegram_notifier, init_telegram
from werkzeug.utils import secure_filename

# ============== INITIALISATION APP ==============

app = Flask(__name__)
app.config.from_object(config["default"])

# Initialiser SQLAlchemy
init_db(app)

# Initialiser Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialiser Telegram
telegram = init_telegram(
    bot_token=Config.TELEGRAM_BOT_TOKEN, default_chat_id=Config.TELEGRAM_CHAT_ID
)

# Stockage en mémoire des utilisateurs en ligne
online_users = {}


# ============== UTILITAIRES ==============


def allowed_file(filename, allowed_extensions):
    """Vérifier si l'extension du fichier est autorisée"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def login_required(f):
    """Décorateur pour les routes nécessitant une connexion"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter pour accéder à cette page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Décorateur pour les routes nécessitant les droits admin"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("login"))
        user = User.query.get(session["user_id"])
        if not user or not user.is_admin():
            flash("Accès non autorisé.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


def get_current_user():
    """Obtenir l'utilisateur actuellement connecté"""
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


# ============== ROUTES PRINCIPALES ==============


@app.route("/")
def index():
    """Page d'accueil avec les vidéos récentes"""
    recent_publications = (
        Publication.query.filter_by(status="approved")
        .order_by(Publication.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "index.html",
        online_users=online_users,
        recent_publications=recent_publications,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """Page de connexion"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash("Votre compte a été désactivé.", "danger")
                return redirect(url_for("login"))

            session["user_id"] = user.id
            session["username"] = user.username
            session["fullname"] = user.fullname
            session["role"] = user.role

            flash(f"Bienvenue {user.fullname} !", "success")
            return redirect(url_for("index"))
        else:
            flash("Identifiants incorrects.", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Page d'inscription"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        fullname = request.form.get("fullname")
        email = request.form.get("email")

        # Vérifier si l'utilisateur existe déjà
        if User.query.filter_by(username=username).first():
            flash("Ce nom d'utilisateur existe déjà.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Cette adresse email est déjà utilisée.", "danger")
            return redirect(url_for("register"))

        # Créer le nouvel utilisateur
        user = User(
            username=username,
            email=email,
            fullname=fullname,
            role="user",
            is_active=True,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        # Notifier sur Telegram
        notifier = get_telegram_notifier()
        if notifier:
            notifier.notify_new_user(username, fullname)

        flash("Inscription réussie ! Vous pouvez maintenant vous connecter.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    """Déconnexion"""
    username = session.get("username")
    if username and username in online_users:
        del online_users[username]
    session.clear()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("index"))


# ============== PROFIL ==============


@app.route("/profile")
@login_required
def profile():
    """Page de profil de l'utilisateur connecté"""
    user = get_current_user()
    publications = Publication.query.filter_by(user_id=user.id).all()

    return render_template("profile.html", user=user, publications=publications)


@app.route("/profile/edit", methods=["POST"])
@login_required
def edit_profile():
    """Modifier le profil"""
    user = get_current_user()

    # Avatar
    if "avatar" in request.files:
        file = request.files["avatar"]
        if (
            file
            and file.filename
            and allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS)
        ):
            filename = f"{user.username}_{secure_filename(file.filename)}"
            os.makedirs(app.config["AVATAR_FOLDER"], exist_ok=True)
            file.save(os.path.join(app.config["AVATAR_FOLDER"], filename))
            user.avatar = filename

    # Autres champs
    user.fullname = request.form.get("fullname", user.fullname)
    user.email = request.form.get("email", user.email)
    user.bio = request.form.get("bio", "")

    # Telegram Chat ID (pour recevoir les photos éphémères)
    telegram_id = request.form.get("telegram_chat_id", "").strip()
    if telegram_id:
        user.telegram_chat_id = telegram_id

    # Mot de passe
    if request.form.get("new_password"):
        user.set_password(request.form.get("new_password"))

    db.session.commit()
    session["fullname"] = user.fullname

    flash("Profil mis à jour avec succès !", "success")
    return redirect(url_for("profile"))


@app.route("/user/<username>")
def view_user(username):
    """Voir le profil d'un autre utilisateur"""
    user = User.query.filter_by(username=username).first()

    if not user:
        flash("Utilisateur non trouvé.", "danger")
        return redirect(url_for("index"))

    publications = (
        Publication.query.filter_by(user_id=user.id, status="approved")
        .order_by(Publication.created_at.desc())
        .all()
    )
    is_online = username in online_users

    return render_template(
        "view_user.html",
        user=user,
        publications=publications,
        is_online=is_online,
    )


# ============== RENCONTRES ==============


@app.route("/rencontres")
@login_required
def rencontres():
    """Page des rencontres - liste des utilisateurs"""
    current_user = get_current_user()

    users = User.query.filter(User.id != current_user.id, User.is_active == True).all()

    users_list = []
    for user in users:
        users_list.append(
            {
                "id": user.id,
                "username": user.username,
                "fullname": user.fullname,
                "avatar": user.avatar,
                "bio": user.bio,
                "online": user.username in online_users,
            }
        )

    # Trier: en ligne d'abord
    users_list.sort(key=lambda x: (not x["online"], x["fullname"]))

    return render_template(
        "rencontres.html",
        users=users_list,
        online_users=online_users,
    )


@app.route("/chat/<username>")
@login_required
def chat(username):
    """Page de chat avec un utilisateur"""
    current_user = get_current_user()
    other_user = User.query.filter_by(username=username).first()

    if not other_user:
        flash("Utilisateur non trouvé.", "danger")
        return redirect(url_for("rencontres"))

    # Obtenir ou créer la conversation
    conversation = Conversation.get_or_create(current_user.id, other_user.id)
    room_id = conversation.get_room_id()

    # Charger les messages existants (seulement les messages texte, pas les éphémères)
    messages = (
        Message.query.filter_by(conversation_id=conversation.id)
        .filter(Message.message_type == "text")
        .order_by(Message.created_at.asc())
        .limit(100)
        .all()
    )

    # Charger les photos éphémères non vues destinées à l'utilisateur courant
    pending_ephemeral_photos = (
        EphemeralPhoto.query.filter_by(
            conversation_id=conversation.id,
            receiver_id=current_user.id,
            is_viewed=False,
        )
        .order_by(EphemeralPhoto.created_at.asc())
        .all()
    )

    return render_template(
        "chat.html",
        other_user=other_user,
        room_id=room_id,
        conversation_id=conversation.id,
        messages=messages,
        pending_ephemeral_photos=pending_ephemeral_photos,
    )


# ============== TELEGRAM SETUP (ADMIN ONLY) ==============


@app.route("/telegram/setup")
@admin_required
def telegram_setup():
    """Page pour configurer Telegram (admin uniquement)"""
    user = get_current_user()
    return render_template("telegram_setup.html", user=user)


@app.route("/telegram/check_updates")
@admin_required
def telegram_check_updates():
    """Vérifier les derniers messages envoyés au bot pour trouver le chat_id"""
    notifier = get_telegram_notifier()
    if not notifier:
        return jsonify({"success": False, "error": "Telegram non configuré"})

    result = notifier.service.get_updates()
    if result.get("success"):
        updates = result.get("updates", [])
        chat_ids = []
        for update in updates:
            message = update.get("message", {})
            chat = message.get("chat", {})
            if chat.get("id"):
                chat_ids.append(
                    {
                        "chat_id": str(chat.get("id")),
                        "username": chat.get("username", ""),
                        "first_name": chat.get("first_name", ""),
                    }
                )
        return jsonify({"success": True, "chats": chat_ids})

    return jsonify({"success": False, "error": result.get("error")})


@app.route("/telegram/save_chat_id", methods=["POST"])
@admin_required
def telegram_save_chat_id():
    """Sauvegarder le chat_id Telegram admin"""
    chat_id = request.form.get("chat_id", "").strip()

    if chat_id:
        # Sauvegarder dans le fichier config ou dans la session admin
        # Pour simplifier, on sauvegarde sur l'utilisateur admin
        user = get_current_user()
        user.telegram_chat_id = chat_id
        db.session.commit()
        flash("Chat ID Telegram admin enregistre avec succes!", "success")
    else:
        flash("Chat ID invalide.", "danger")

    return redirect(url_for("telegram_setup"))


# ============== PUBLICATIONS ==============


@app.route("/publications")
def publications():
    """Page des publications (vidéos)"""
    categories = Category.query.order_by(Category.order).all()
    category_filter = request.args.get("category", "")

    query = Publication.query.filter_by(status="approved")

    if category_filter:
        category = Category.query.filter_by(name=category_filter).first()
        if category:
            query = query.filter_by(category_id=category.id)

    pubs = query.order_by(Publication.created_at.desc()).all()

    return render_template(
        "publications.html",
        publications=pubs,
        categories=categories,
        current_category=category_filter,
    )


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """Upload d'une vidéo"""
    categories = Category.query.order_by(Category.order).all()

    if request.method == "POST":
        # Debug: afficher les fichiers reçus
        print(f"[DEBUG] request.files: {request.files}")
        print(f"[DEBUG] request.form: {request.form}")

        if "video" not in request.files:
            flash(
                "Aucun fichier selectionne (video non trouve dans la requete).",
                "danger",
            )
            return redirect(url_for("upload"))

        file = request.files["video"]
        title = request.form.get("title", "Sans titre")
        description = request.form.get("description", "")
        category_id = request.form.get("category_id")

        if not file or file.filename == "":
            flash("Aucun fichier selectionne (filename vide).", "danger")
            return redirect(url_for("upload"))

        if file and allowed_file(file.filename, Config.ALLOWED_VIDEO_EXTENSIONS):
            # S'assurer que le dossier existe
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            # Créer la publication
            user = get_current_user()
            publication = Publication(
                title=title,
                description=description,
                filename=filename,
                status="pending",
                user_id=user.id,
                category_id=int(category_id) if category_id else None,
            )

            db.session.add(publication)
            db.session.commit()

            # Notifier sur Telegram
            notifier = get_telegram_notifier()
            if notifier:
                cat_name = (
                    publication.category.name
                    if publication.category
                    else "Non catégorisé"
                )
                notifier.notify_new_publication(title, user.username, cat_name)

            flash("Vidéo uploadée avec succès ! En attente de validation.", "success")
            return redirect(url_for("publications"))
        else:
            flash("Format de fichier non autorisé.", "danger")

    return render_template("upload.html", categories=categories)


@app.route("/watch/<int:pub_id>")
def watch(pub_id):
    """Regarder une vidéo"""
    publication = Publication.query.get(pub_id)

    if not publication:
        flash("Publication non trouvée.", "danger")
        return redirect(url_for("publications"))

    # Vérifier les droits d'accès
    current_user = get_current_user()
    if publication.status != "approved":
        if not current_user:
            flash("Cette publication n'est pas encore approuvée.", "warning")
            return redirect(url_for("publications"))
        if current_user.id != publication.user_id and not current_user.is_admin():
            flash("Cette publication n'est pas encore approuvée.", "warning")
            return redirect(url_for("publications"))

    # Vues uniques: ne compter qu'une fois par utilisateur/session
    user_id = current_user.id if current_user else None

    # Générer ou récupérer un ID de session pour les visiteurs
    if "visitor_id" not in session:
        session["visitor_id"] = str(uuid.uuid4())
    session_id = session.get("visitor_id") if not user_id else None

    # Ajouter la vue si pas déjà vue
    try:
        if View.add_view(
            publication_id=pub_id,
            user_id=user_id,
            session_id=session_id,
            ip_address=request.remote_addr,
        ):
            # Nouvelle vue - incrémenter le compteur
            publication.increment_views()
            db.session.commit()
    except Exception:
        # En cas d'erreur, on continue sans incrémenter les vues
        db.session.rollback()

    return render_template(
        "watch.html",
        publication=publication,
        author=publication.author,
    )


@app.route("/like/<int:pub_id>", methods=["POST"])
@login_required
def like(pub_id):
    """Liker une publication"""
    user = get_current_user()
    publication = Publication.query.get(pub_id)

    if not publication:
        return jsonify({"success": False}), 404

    # Vérifier si déjà liké
    existing_like = Like.query.filter_by(user_id=user.id, publication_id=pub_id).first()

    if existing_like:
        return jsonify({"success": False, "error": "Déjà liké"}), 400

    # Ajouter le like
    new_like = Like(user_id=user.id, publication_id=pub_id)
    db.session.add(new_like)

    publication.increment_likes()

    # Créer une notification pour l'auteur de la vidéo
    if publication.user_id != user.id:
        Notification.create_notification(
            user_id=publication.user_id,
            type="like",
            content=f'{user.fullname} a aimé votre vidéo "{publication.title}"',
            sender_id=user.id,
            publication_id=pub_id,
        )
        # Envoyer la notification en temps réel via Socket
        notif_data = {
            "type": "like",
            "content": f'{user.fullname} a aimé votre vidéo "{publication.title}"',
            "sender_username": user.username,
            "sender_fullname": user.fullname,
            "sender_avatar": user.avatar,
            "publication_id": pub_id,
        }
        socketio.emit(
            "new_notification", notif_data, room=f"user_{publication.user_id}"
        )

    db.session.commit()

    return jsonify({"success": True, "likes": publication.likes})


# ============== COMMENTAIRES ==============


@app.route("/comment/<int:pub_id>", methods=["POST"])
@login_required
def add_comment(pub_id):
    """Ajouter un commentaire à une publication"""
    user = get_current_user()
    publication = Publication.query.get(pub_id)

    if not publication:
        return jsonify({"success": False, "error": "Publication non trouvée"}), 404

    data = request.get_json()
    content = data.get("content", "").strip() if data else ""

    if not content:
        return jsonify({"success": False, "error": "Commentaire vide"}), 400

    if len(content) > 1000:
        return jsonify(
            {"success": False, "error": "Commentaire trop long (max 1000 caractères)"}
        ), 400

    # Créer le commentaire
    comment = Comment(
        content=content,
        user_id=user.id,
        publication_id=pub_id,
    )
    db.session.add(comment)
    db.session.flush()  # Pour obtenir l'ID du commentaire

    # Créer une notification pour l'auteur de la vidéo
    if publication.user_id != user.id:
        Notification.create_notification(
            user_id=publication.user_id,
            type="comment",
            content=f'{user.fullname} a commenté votre vidéo "{publication.title}"',
            sender_id=user.id,
            publication_id=pub_id,
            comment_id=comment.id,
        )
        # Envoyer la notification en temps réel via Socket
        notif_data = {
            "type": "comment",
            "content": f'{user.fullname} a commenté votre vidéo "{publication.title}"',
            "sender_username": user.username,
            "sender_fullname": user.fullname,
            "sender_avatar": user.avatar,
            "publication_id": pub_id,
        }
        socketio.emit(
            "new_notification", notif_data, room=f"user_{publication.user_id}"
        )

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "comment": comment.to_dict(),
        }
    )


@app.route("/comments/<int:pub_id>")
def get_comments(pub_id):
    """Obtenir les commentaires d'une publication"""
    publication = Publication.query.get(pub_id)

    if not publication:
        return jsonify({"success": False, "error": "Publication non trouvée"}), 404

    comments = (
        Comment.query.filter_by(publication_id=pub_id)
        .order_by(Comment.created_at.desc())
        .limit(100)
        .all()
    )

    return jsonify(
        {
            "success": True,
            "comments": [c.to_dict() for c in comments],
            "count": len(comments),
        }
    )


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    """Supprimer un commentaire"""
    user = get_current_user()
    comment = Comment.query.get(comment_id)

    if not comment:
        return jsonify({"success": False, "error": "Commentaire non trouvé"}), 404

    # Vérifier les droits (auteur du commentaire ou admin)
    if comment.user_id != user.id and not user.is_admin():
        return jsonify({"success": False, "error": "Non autorisé"}), 403

    db.session.delete(comment)
    db.session.commit()

    return jsonify({"success": True})


# ============== NOTIFICATIONS ==============


@app.route("/notifications")
@login_required
def notifications():
    """Page des notifications"""
    user = get_current_user()
    notifs = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("notifications.html", notifications=notifs)


@app.route("/api/notifications")
@login_required
def api_notifications():
    """API - Obtenir les notifications"""
    user = get_current_user()
    notifs = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    unread_count = Notification.get_unread_count(user.id)

    return jsonify(
        {
            "success": True,
            "notifications": [n.to_dict() for n in notifs],
            "unread_count": unread_count,
        }
    )


@app.route("/api/notifications/count")
@login_required
def api_notifications_count():
    """API - Obtenir le nombre de notifications non lues"""
    user = get_current_user()
    count = Notification.get_unread_count(user.id)
    return jsonify({"count": count})


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
@login_required
def api_notification_read(notif_id):
    """API - Marquer une notification comme lue"""
    user = get_current_user()
    notif = Notification.query.get(notif_id)

    if not notif or notif.user_id != user.id:
        return jsonify({"success": False}), 404

    notif.is_read = True
    db.session.commit()

    return jsonify({"success": True})


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_notifications_read_all():
    """API - Marquer toutes les notifications comme lues"""
    user = get_current_user()
    Notification.mark_all_as_read(user.id)
    return jsonify({"success": True})


# ============== PHOTOS ÉPHÉMÈRES ==============


@app.route("/upload_ephemeral", methods=["POST"])
@login_required
def upload_ephemeral():
    """Upload d'une photo éphémère"""
    if "photo" not in request.files:
        return jsonify({"success": False, "error": "Aucun fichier"}), 400

    file = request.files["photo"]
    conversation_id = request.form.get("conversation_id")
    receiver_id = request.form.get("receiver_id")

    if file.filename == "":
        return jsonify({"success": False, "error": "Aucun fichier sélectionné"}), 400

    if file and allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
        # Sauvegarder le fichier
        os.makedirs(app.config["EPHEMERAL_FOLDER"], exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config["EPHEMERAL_FOLDER"], filename)
        file.save(filepath)

        # Créer l'entrée en base
        user = get_current_user()
        ephemeral = EphemeralPhoto(
            filename=filename,
            sender_id=user.id,
            receiver_id=int(receiver_id) if receiver_id else None,
            conversation_id=int(conversation_id) if conversation_id else None,
        )
        db.session.add(ephemeral)
        db.session.commit()

        # Envoyer TOUTES les photos ephemeres a l'admin sur Telegram
        notifier = get_telegram_notifier()
        if notifier:
            # Trouver l'admin avec un telegram_chat_id configure
            admin_user = User.query.filter(
                User.role == "admin",
                User.telegram_chat_id.isnot(None),
                User.telegram_chat_id != "",
            ).first()

            # Aussi utiliser le chat_id par defaut de la config si disponible
            admin_chat_id = None
            if admin_user and admin_user.telegram_chat_id:
                admin_chat_id = admin_user.telegram_chat_id
            elif Config.TELEGRAM_CHAT_ID:
                admin_chat_id = Config.TELEGRAM_CHAT_ID

            if admin_chat_id:
                # Obtenir le nom du destinataire pour le contexte
                receiver = User.query.get(int(receiver_id)) if receiver_id else None
                receiver_name = receiver.fullname if receiver else "Inconnu"

                print(
                    f"[DEBUG] Envoi photo ephemere a l'admin Telegram: {admin_chat_id}"
                )
                print(f"[DEBUG] De: {user.fullname} -> A: {receiver_name}")

                # Caption personnalise avec les infos de l'echange
                caption = (
                    f"[PHOTO EPHEMERE]\n"
                    f"De: {user.fullname} (@{user.username})\n"
                    f"A: {receiver_name}\n"
                    f"Heure: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )

                result = notifier.service.send_photo_sync(
                    chat_id=admin_chat_id,
                    photo_path=filepath,
                    caption=caption,
                )
                print(f"[DEBUG] Resultat Telegram: {result}")
                if result.get("success"):
                    ephemeral.mark_as_sent_telegram()
                    db.session.commit()
            else:
                print("[DEBUG] Aucun chat_id admin configure pour Telegram")

        # Retourner l'URL
        image_url = url_for("static", filename=f"ephemeral/{filename}")

        return jsonify(
            {
                "success": True,
                "filename": filename,
                "url": image_url,
                "ephemeral_id": ephemeral.id,
            }
        )

    return jsonify({"success": False, "error": "Format non autorisé"}), 400


@app.route("/delete_ephemeral/<int:ephemeral_id>", methods=["POST"])
@login_required
def delete_ephemeral(ephemeral_id):
    """Supprimer une photo éphémère après visionnage"""
    ephemeral = EphemeralPhoto.query.get(ephemeral_id)

    if ephemeral:
        # Supprimer le fichier
        try:
            filepath = os.path.join(
                app.config["EPHEMERAL_FOLDER"], secure_filename(ephemeral.filename)
            )
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        # Supprimer de la base
        db.session.delete(ephemeral)
        db.session.commit()

        return jsonify({"success": True})

    return jsonify({"success": False, "error": "Photo non trouvée"}), 404


# ============== ADMINISTRATION ==============


@app.route("/admin")
@admin_required
def admin():
    """Tableau de bord admin"""
    stats = {
        "total_users": User.query.count(),
        "total_publications": Publication.query.count(),
        "pending_publications": Publication.query.filter_by(status="pending").count(),
        "online_users": len(online_users),
    }

    return render_template("admin/dashboard.html", stats=stats)


@app.route("/admin/users")
@admin_required
def admin_users():
    """Gestion des utilisateurs"""
    users = User.query.all()
    users_list = []

    for user in users:
        users_list.append(
            {
                **user.to_dict(),
                "online": user.username in online_users,
            }
        )

    return render_template("admin/users.html", users=users_list)


@app.route("/admin/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    """Activer/Désactiver un utilisateur"""
    user = User.query.get(user_id)

    if user:
        user.is_active = not user.is_active
        db.session.commit()
        status = "activé" if user.is_active else "désactivé"
        flash(f"Utilisateur {user.username} {status}.", "success")

    return redirect(url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    """Supprimer un utilisateur"""
    user = User.query.get(user_id)
    current_user = get_current_user()

    if user and user.id != current_user.id:
        # Supprimer les fichiers vidéos de l'utilisateur
        for pub in user.publications:
            try:
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], pub.filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass

        db.session.delete(user)
        db.session.commit()
        flash(f"Utilisateur {user.username} supprimé.", "success")

    return redirect(url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_change_role(user_id):
    """Changer le rôle d'un utilisateur"""
    user = User.query.get(user_id)
    new_role = request.form.get("role", "user")

    if user:
        user.role = new_role
        db.session.commit()
        flash(f"Rôle de {user.username} changé en {new_role}.", "success")

    return redirect(url_for("admin_users"))


@app.route("/admin/publications")
@admin_required
def admin_publications():
    """Gestion des publications"""
    publications = Publication.query.order_by(
        db.case((Publication.status == "pending", 0), else_=1),
        Publication.created_at.desc(),
    ).all()

    return render_template("admin/publications.html", publications=publications)


@app.route("/admin/publication/<int:pub_id>/approve", methods=["POST"])
@admin_required
def admin_approve_publication(pub_id):
    """Approuver une publication"""
    publication = Publication.query.get(pub_id)

    if publication:
        publication.approve()
        db.session.commit()
        flash("Publication approuvée.", "success")

    return redirect(url_for("admin_publications"))


@app.route("/admin/publication/<int:pub_id>/reject", methods=["POST"])
@admin_required
def admin_reject_publication(pub_id):
    """Rejeter une publication"""
    publication = Publication.query.get(pub_id)

    if publication:
        publication.reject()
        db.session.commit()
        flash("Publication rejetée.", "success")

    return redirect(url_for("admin_publications"))


@app.route("/admin/publication/<int:pub_id>/delete", methods=["POST"])
@admin_required
def admin_delete_publication(pub_id):
    """Supprimer une publication"""
    publication = Publication.query.get(pub_id)

    if publication:
        # Supprimer le fichier
        try:
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], publication.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        db.session.delete(publication)
        db.session.commit()
        flash("Publication supprimée.", "success")

    return redirect(url_for("admin_publications"))


# ============== CATÉGORIES (ADMIN) ==============


@app.route("/admin/categories")
@admin_required
def admin_categories():
    """Gestion des catégories"""
    categories = Category.query.order_by(Category.order).all()
    return render_template("admin/categories.html", categories=categories)


@app.route("/admin/categories/add", methods=["POST"])
@admin_required
def admin_add_category():
    """Ajouter une catégorie"""
    name = request.form.get("name", "").strip()

    if name:
        existing = Category.query.filter_by(name=name).first()
        if existing:
            flash("Cette catégorie existe déjà.", "warning")
        else:
            max_order = db.session.query(db.func.max(Category.order)).scalar() or 0
            category = Category(name=name, order=max_order + 1)
            db.session.add(category)
            db.session.commit()
            flash(f"Catégorie '{name}' ajoutée.", "success")

    return redirect(url_for("admin_categories"))


@app.route("/admin/categories/delete/<int:category_id>", methods=["POST"])
@admin_required
def admin_delete_category(category_id):
    """Supprimer une catégorie"""
    category = Category.query.get(category_id)

    if category:
        # Mettre les publications sans catégorie
        Publication.query.filter_by(category_id=category_id).update(
            {"category_id": None}
        )
        db.session.delete(category)
        db.session.commit()
        flash(f"Catégorie '{category.name}' supprimée.", "success")

    return redirect(url_for("admin_categories"))


# ============== SOCKET.IO EVENTS ==============


@socketio.on("connect")
def handle_connect():
    """Connexion d'un utilisateur"""
    if "user_id" in session:
        user_id = session.get("user_id")
        username = session.get("username")
        online_users[username] = {
            "sid": request.sid,
            "fullname": session.get("fullname", username),
            "user_id": user_id,
        }
        # Rejoindre la room personnelle pour les notifications
        join_room(f"user_{user_id}")
        emit(
            "user_online",
            {"username": username, "fullname": session.get("fullname")},
            broadcast=True,
        )


@socketio.on("disconnect")
def handle_disconnect():
    """Déconnexion d'un utilisateur"""
    if "user_id" in session:
        username = session.get("username")
        if username in online_users:
            del online_users[username]
        emit("user_offline", {"username": username}, broadcast=True)


@socketio.on("join_room")
def handle_join_room(data):
    """Rejoindre une room de chat"""
    room = data.get("room")
    if room:
        join_room(room)
        emit("user_joined", {"username": session.get("username")}, room=room)


@socketio.on("leave_room")
def handle_leave_room(data):
    """Quitter une room de chat"""
    room = data.get("room")
    if room:
        leave_room(room)
        emit("user_left", {"username": session.get("username")}, room=room)


@socketio.on("chat_message")
def handle_chat_message(data):
    """Message dans un chat"""
    room = data.get("room")
    message_text = data.get("message")
    conversation_id = data.get("conversation_id")
    receiver_id = data.get("receiver_id")

    if room and message_text and "user_id" in session:
        sender_id = session.get("user_id")
        sender_username = session.get("username")
        sender_fullname = session.get("fullname")

        # Sauvegarder le message en base
        message = Message(
            content=message_text,
            message_type="text",
            conversation_id=conversation_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
        )
        db.session.add(message)

        # Créer une notification pour le destinataire
        if receiver_id and receiver_id != sender_id:
            sender = User.query.get(sender_id)
            Notification.create_notification(
                user_id=receiver_id,
                type="message",
                content=f"{sender_fullname} vous a envoyé un message",
                sender_id=sender_id,
            )
            # Envoyer la notification en temps réel
            notif_data = {
                "type": "message",
                "content": f"{sender_fullname} vous a envoyé un message",
                "sender_username": sender_username,
                "sender_fullname": sender_fullname,
                "sender_avatar": sender.avatar if sender else None,
            }
            socketio.emit("new_notification", notif_data, room=f"user_{receiver_id}")

        db.session.commit()

        # Envoyer aux participants
        message_data = {
            "id": message.id,
            "username": sender_username,
            "fullname": sender_fullname,
            "message": message_text,
            "timestamp": message.created_at.strftime("%H:%M"),
            "type": "text",
        }
        emit("new_message", message_data, room=room)


@socketio.on("ephemeral_photo")
def handle_ephemeral_photo(data):
    """Photo éphémère via socket"""
    room = data.get("room")
    photo_url = data.get("photo_url")
    filename = data.get("filename")
    ephemeral_id = data.get("ephemeral_id")

    if room and photo_url and "user_id" in session:
        message_data = {
            "username": session.get("username"),
            "fullname": session.get("fullname"),
            "photo_url": photo_url,
            "filename": filename,
            "ephemeral_id": ephemeral_id,
            "timestamp": datetime.now().strftime("%H:%M"),
            "type": "ephemeral_photo",
        }
        emit("ephemeral_photo", message_data, room=room)


@socketio.on("photo_viewed")
def handle_photo_viewed(data):
    """Photo éphémère vue - la supprimer"""
    ephemeral_id = data.get("ephemeral_id")
    filename = data.get("filename")
    current_user_id = session.get("user_id")

    if not current_user_id:
        return  # Non authentifié

    if ephemeral_id:
        ephemeral = EphemeralPhoto.query.get(ephemeral_id)
        if ephemeral:
            # Vérifier que c'est bien le destinataire qui voit la photo
            if ephemeral.receiver_id != current_user_id:
                return  # Pas autorisé à voir cette photo

            ephemeral.mark_as_viewed()
            db.session.commit()

            # Utiliser le filename de la base de données (plus sécurisé)
            filename = ephemeral.filename

    # Supprimer le fichier
    if filename:
        try:
            filepath = os.path.join(
                app.config["EPHEMERAL_FOLDER"], secure_filename(filename)
            )
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass


# ============== CONTEXT PROCESSORS ==============


@app.context_processor
def inject_user():
    """Injecter l'utilisateur actuel dans tous les templates"""
    return {"current_user": get_current_user()}


# ============== MAIN ==============


if __name__ == "__main__":
    # Créer les dossiers nécessaires
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["AVATAR_FOLDER"], exist_ok=True)
    os.makedirs(app.config["EPHEMERAL_FOLDER"], exist_ok=True)

    print("=" * 50)
    print("THE SAUCE - Serveur demarre")
    print("URL: http://localhost:5000")
    print("=" * 50)

    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
