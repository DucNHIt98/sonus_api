import logging

from django.core.management.base import BaseCommand

from music.models import Song

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete songs with duration > 15 minutes (900 seconds) from DB'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Count records without deleting',
        )
        parser.add_argument(
            '--older-than',
            type=int,
            default=0,
            help='Only delete songs created more than N days ago (0 = all)',
        )

    def handle(self, *args, **options):
        qs = Song.objects.filter(duration__gt=900)
        if options['older_than'] > 0:
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(days=options['older_than'])
            qs = qs.filter(created_at__lt=cutoff)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No songs longer than 15 minutes found'))
            return

        if options['dry_run']:
            self.stdout.write(f'Would delete {total} song(s) longer than 15 minutes')
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} song(s) longer than 15 minutes'))
