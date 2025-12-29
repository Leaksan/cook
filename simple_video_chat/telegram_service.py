"""
Service Telegram pour l'envoi de photos éphémères
Utilise l'API Bot Telegram pour envoyer les images
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import requests


class TelegramService:
    """Service pour interagir avec l'API Telegram Bot"""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str):
        """
        Initialiser le service Telegram

        Args:
            bot_token: Token du bot Telegram
        """
        self.bot_token = bot_token
        self.session = None

    def _get_url(self, method: str) -> str:
        """Construire l'URL de l'API"""
        return self.BASE_URL.format(token=self.bot_token, method=method)

    def send_photo_sync(
        self,
        chat_id: str,
        photo_path: str,
        caption: Optional[str] = None,
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envoyer une photo de manière synchrone

        Args:
            chat_id: ID du chat Telegram
            photo_path: Chemin vers le fichier photo
            caption: Légende de la photo
            sender_name: Nom de l'expéditeur

        Returns:
            Réponse de l'API Telegram
        """
        url = self._get_url("sendPhoto")

        # Construire la légende
        if caption is None:
            caption = f"[PHOTO] Photo ephemere de The Sauce"
            if sender_name:
                caption = f"[PHOTO] Photo ephemere de {sender_name}\n[!] Cette photo s'autodetruira apres visionnage"

        try:
            with open(photo_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}

                response = requests.post(url, data=data, files=files, timeout=30)
                result = response.json()

                if result.get("ok"):
                    print(f"[OK] Photo envoyee sur Telegram a {chat_id}")
                    return {"success": True, "result": result}
                else:
                    print(f"[ERREUR] Erreur Telegram: {result.get('description')}")
                    return {"success": False, "error": result.get("description")}

        except FileNotFoundError:
            return {"success": False, "error": "Fichier photo non trouvé"}
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_photo_async(
        self,
        chat_id: str,
        photo_path: str,
        caption: Optional[str] = None,
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envoyer une photo de manière asynchrone

        Args:
            chat_id: ID du chat Telegram
            photo_path: Chemin vers le fichier photo
            caption: Légende de la photo
            sender_name: Nom de l'expéditeur

        Returns:
            Réponse de l'API Telegram
        """
        url = self._get_url("sendPhoto")

        # Construire la légende
        if caption is None:
            caption = f"[PHOTO] Photo ephemere de The Sauce"
            if sender_name:
                caption = f"[PHOTO] Photo ephemere de {sender_name}\n[!] Cette photo s'autodetruira apres visionnage"

        try:
            async with aiohttp.ClientSession() as session:
                with open(photo_path, "rb") as photo_file:
                    data = aiohttp.FormData()
                    data.add_field("chat_id", chat_id)
                    data.add_field("caption", caption)
                    data.add_field("parse_mode", "HTML")
                    data.add_field(
                        "photo",
                        photo_file,
                        filename=os.path.basename(photo_path),
                        content_type="image/jpeg",
                    )

                    async with session.post(url, data=data) as response:
                        result = await response.json()

                        if result.get("ok"):
                            print(f"[OK] Photo envoyee sur Telegram a {chat_id}")
                            return {"success": True, "result": result}
                        else:
                            print(
                                f"[ERREUR] Erreur Telegram: {result.get('description')}"
                            )
                            return {
                                "success": False,
                                "error": result.get("description"),
                            }

        except FileNotFoundError:
            return {"success": False, "error": "Fichier photo non trouvé"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_message_sync(
        self, chat_id: str, text: str, parse_mode: str = "HTML"
    ) -> Dict[str, Any]:
        """
        Envoyer un message texte de manière synchrone

        Args:
            chat_id: ID du chat Telegram
            text: Texte du message
            parse_mode: Mode de parsing (HTML ou Markdown)

        Returns:
            Réponse de l'API Telegram
        """
        url = self._get_url("sendMessage")

        try:
            response = requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            result = response.json()

            if result.get("ok"):
                return {"success": True, "result": result}
            else:
                return {"success": False, "error": result.get("description")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_me(self) -> Dict[str, Any]:
        """
        Obtenir les informations du bot

        Returns:
            Informations du bot
        """
        url = self._get_url("getMe")

        try:
            response = requests.get(url, timeout=10)
            result = response.json()

            if result.get("ok"):
                return {"success": True, "result": result.get("result")}
            else:
                return {"success": False, "error": result.get("description")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_updates(self, offset: int = 0) -> Dict[str, Any]:
        """
        Obtenir les mises à jour (messages reçus par le bot)
        Utile pour récupérer les chat_id des utilisateurs

        Args:
            offset: ID du dernier update traité

        Returns:
            Liste des updates
        """
        url = self._get_url("getUpdates")

        try:
            response = requests.get(
                url, params={"offset": offset, "timeout": 10}, timeout=15
            )
            result = response.json()

            if result.get("ok"):
                return {"success": True, "updates": result.get("result", [])}
            else:
                return {"success": False, "error": result.get("description")}

        except Exception as e:
            return {"success": False, "error": str(e)}


class TelegramNotifier:
    """
    Classe utilitaire pour envoyer des notifications Telegram
    depuis l'application The Sauce
    """

    def __init__(self, bot_token: str, default_chat_id: Optional[str] = None):
        """
        Initialiser le notifier

        Args:
            bot_token: Token du bot Telegram
            default_chat_id: Chat ID par défaut pour les notifications admin
        """
        self.service = TelegramService(bot_token)
        self.default_chat_id = default_chat_id

    def notify_ephemeral_photo(
        self,
        photo_path: str,
        sender_name: str,
        receiver_chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Notifier l'envoi d'une photo éphémère

        Args:
            photo_path: Chemin vers la photo
            sender_name: Nom de l'expéditeur
            receiver_chat_id: Chat ID Telegram du destinataire

        Returns:
            Résultat de l'envoi
        """
        chat_id = receiver_chat_id or self.default_chat_id

        if not chat_id:
            return {"success": False, "error": "Aucun chat_id configuré"}

        timestamp = datetime.now().strftime("%d/%m/%Y à %H:%M")
        caption = (
            f"[PHOTO] <b>Photo ephemere</b>\n"
            f"De: <b>{sender_name}</b>\n"
            f"Heure: {timestamp}\n"
            f"<i>Photo de The Sauce</i>"
        )

        return self.service.send_photo_sync(
            chat_id=chat_id, photo_path=photo_path, caption=caption
        )

    def notify_admin(self, message: str) -> Dict[str, Any]:
        """
        Envoyer une notification à l'admin

        Args:
            message: Message à envoyer

        Returns:
            Résultat de l'envoi
        """
        if not self.default_chat_id:
            return {"success": False, "error": "Aucun chat_id admin configuré"}

        return self.service.send_message_sync(
            chat_id=self.default_chat_id, text=f"[NOTIF] <b>The Sauce</b>\n\n{message}"
        )

    def notify_new_publication(
        self, title: str, author: str, category: str
    ) -> Dict[str, Any]:
        """
        Notifier une nouvelle publication à modérer

        Args:
            title: Titre de la publication
            author: Auteur de la publication
            category: Catégorie de la publication

        Returns:
            Résultat de l'envoi
        """
        if not self.default_chat_id:
            return {"success": False, "error": "Aucun chat_id admin configuré"}

        message = (
            f"[VIDEO] <b>Nouvelle publication a moderer</b>\n\n"
            f"Titre: <b>{title}</b>\n"
            f"Auteur: {author}\n"
            f"Categorie: {category}\n\n"
            f"Connectez-vous a l'admin pour moderer"
        )

        return self.service.send_message_sync(
            chat_id=self.default_chat_id, text=message
        )

    def notify_new_user(self, username: str, fullname: str) -> Dict[str, Any]:
        """
        Notifier un nouvel utilisateur inscrit

        Args:
            username: Nom d'utilisateur
            fullname: Nom complet

        Returns:
            Résultat de l'envoi
        """
        if not self.default_chat_id:
            return {"success": False, "error": "Aucun chat_id admin configuré"}

        message = (
            f"[USER] <b>Nouvel utilisateur inscrit</b>\n\n"
            f"Username: @{username}\n"
            f"Nom: {fullname}"
        )

        return self.service.send_message_sync(
            chat_id=self.default_chat_id, text=message
        )


# Instance globale (à initialiser avec le token)
telegram_notifier: Optional[TelegramNotifier] = None


def init_telegram(bot_token: str, default_chat_id: Optional[str] = None):
    """
    Initialiser le service Telegram global

    Args:
        bot_token: Token du bot Telegram
        default_chat_id: Chat ID par défaut pour les notifications
    """
    global telegram_notifier
    telegram_notifier = TelegramNotifier(bot_token, default_chat_id)

    # Verifier la connexion
    result = telegram_notifier.service.get_me()
    if result.get("success"):
        bot_info = result.get("result", {})
        print(f"[OK] Telegram Bot connecte: @{bot_info.get('username')}")
    else:
        print(f"[WARN] Erreur connexion Telegram: {result.get('error')}")

    return telegram_notifier


def get_telegram_notifier() -> Optional[TelegramNotifier]:
    """Obtenir l'instance du notifier Telegram"""
    return telegram_notifier
