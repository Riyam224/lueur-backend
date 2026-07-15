from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from accounts.services import delete_user_account


class Command(BaseCommand):
    help = (
        "Deletes a user's Firebase identity, MoodEntry rows, and local account "
        "by email. Used to fulfil web-based deletion requests (see the "
        "Account Deletion section of the privacy policy) from users who "
        "cannot open the app to use the self-service delete-account endpoint."
    )

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)

    def handle(self, *args, **options):
        email = options["email"]
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'.")

        delete_user_account(user)
        self.stdout.write(
            self.style.SUCCESS(f"Deleted account and journal entries for '{email}'.")
        )
