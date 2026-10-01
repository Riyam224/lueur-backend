import logging

from firebase_admin import auth as firebase_auth_admin

from therapist.models import JournalEntry

logger = logging.getLogger(__name__)


def success_response(message, data=None):
    return {"success": True, "message": message, "data": data or {}}


def error_response(message, errors=None):
    return {"success": False, "message": message, "errors": errors or {}}


def delete_user_account(user):
    """Deletes the Firebase identity, the user's JournalEntry rows, and the local
    User row, in that order. Raises whatever exception the Firebase Admin SDK
    raises if `delete_user` fails; the local row is left untouched in that
    case so no orphaned Firebase identity is created. The one exception is
    UserNotFoundError: the Firebase identity is already gone, which is the
    outcome we want, so it's logged and local deletion continues.

    Shared by DeleteAccountView (self-service, in-app) and the
    delete_user_by_email management command (used to fulfil the web-based
    deletion requests promised in the privacy policy for users who can't
    open the app) so both paths perform the exact same deletion.
    """
    if user.firebase_uid:
        try:
            firebase_auth_admin.delete_user(user.firebase_uid)
        except firebase_auth_admin.UserNotFoundError:
            logger.warning(
                "Firebase user uid=%s already deleted; deleting local data anyway",
                user.firebase_uid,
            )

    JournalEntry.objects.filter(user_id=str(user.id)).delete()
    user.delete()
