from django.core.management.base import BaseCommand, CommandError

from services.crawler import crawl_queries, crawl_youtube_channel

PRESET_QUERIES = {
}

CHANNEL_PRESETS = {
    'viet-nam-top': [
        # Most guessed handles are wrong.
        # Use `manage.py crawl_vn_artists` instead (searches by artist name).
    ],
}

PRESET_QUERIES = {
    'v-pop': [
        {'source': 'youtube', 'query': 'nhac viet nam 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'v-pop moi nhat 2024', 'limit': 20},
        {'source': 'nct', 'query': 'v-pop', 'limit': 20},
        {'source': 'nct', 'query': 'nhac tre', 'limit': 20},
    ],
    'us-uk': [
        {'source': 'youtube', 'query': 'billboard hot 100 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'top hits 2024', 'limit': 20},
        {'source': 'jamendo', 'query': 'pop', 'limit': 20},
    ],
    'k-pop': [
        {'source': 'youtube', 'query': 'k-pop 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'korean music 2024', 'limit': 20},
    ],
    'youtube-diverse': [
        {'source': 'youtube', 'query': 'nhac viet nam 2025', 'limit': 15},
        {'source': 'youtube', 'query': 'top 50 bai hat viet nam', 'limit': 15},
        {'source': 'youtube', 'query': 'v-pop acoustic', 'limit': 15},
        {'source': 'youtube', 'query': 'nhac rap viet', 'limit': 15},
        {'source': 'youtube', 'query': 'us uk hits 2023', 'limit': 15},
        {'source': 'youtube', 'query': 'edm 2024', 'limit': 15},
        {'source': 'youtube', 'query': 'chill music', 'limit': 15},
        {'source': 'youtube', 'query': 'lo-fi hip hop', 'limit': 15},
        {'source': 'youtube', 'query': 'indie folk', 'limit': 15},
        {'source': 'youtube', 'query': 'jazz piano', 'limit': 15},
        {'source': 'youtube', 'query': 'rock ballads', 'limit': 15},
        {'source': 'youtube', 'query': 'r&b soul mix', 'limit': 15},
        {'source': 'youtube', 'query': 'kpop 2023', 'limit': 15},
        {'source': 'youtube', 'query': 'jpop', 'limit': 15},
        {'source': 'youtube', 'query': 'nhac hoa', 'limit': 15},
    ],
    'jamendo-all': [
        {'source': 'jamendo', 'query': 'hip-hop', 'limit': 20},
        {'source': 'jamendo', 'query': 'jazz', 'limit': 20},
        {'source': 'jamendo', 'query': 'classical', 'limit': 20},
        {'source': 'jamendo', 'query': 'ambient', 'limit': 20},
        {'source': 'jamendo', 'query': 'blues', 'limit': 20},
        {'source': 'jamendo', 'query': 'reggae', 'limit': 20},
        {'source': 'jamendo', 'query': 'funk', 'limit': 20},
        {'source': 'jamendo', 'query': 'soul', 'limit': 20},
        {'source': 'jamendo', 'query': 'latin', 'limit': 20},
        {'source': 'jamendo', 'query': 'world', 'limit': 20},
        {'source': 'jamendo', 'query': 'instrumental', 'limit': 20},
        {'source': 'jamendo', 'query': 'country', 'limit': 20},
    ],
    'nct-viet': [
        {'source': 'nct', 'query': 'rap việt', 'limit': 20},
        {'source': 'nct', 'query': 'nhac tru tinh', 'limit': 20},
        {'source': 'nct', 'query': 'edm viet', 'limit': 20},
        {'source': 'nct', 'query': 'acoustic viet', 'limit': 20},
    ],
    'all': [
        {'source': 'youtube', 'query': 'nhac viet nam 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'billboard hot 100 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'k-pop 2024', 'limit': 20},
        {'source': 'nct', 'query': 'v-pop', 'limit': 20},
        {'source': 'nct', 'query': 'us-uk', 'limit': 20},
        {'source': 'nct', 'query': 'k-pop', 'limit': 20},
        {'source': 'jamendo', 'query': 'pop', 'limit': 20},
        {'source': 'jamendo', 'query': 'rock', 'limit': 20},
        {'source': 'jamendo', 'query': 'electronic', 'limit': 20},
    ],
    'max': [
        {'source': 'youtube', 'query': 'nhac viet nam 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'nhac viet nam 2025', 'limit': 15},
        {'source': 'youtube', 'query': 'top 50 bai hat viet nam', 'limit': 15},
        {'source': 'youtube', 'query': 'v-pop moi nhat 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'v-pop acoustic', 'limit': 15},
        {'source': 'youtube', 'query': 'nhac rap viet', 'limit': 15},
        {'source': 'youtube', 'query': 'billboard hot 100 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'us uk hits 2023', 'limit': 15},
        {'source': 'youtube', 'query': 'top hits 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'k-pop 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'kpop 2023', 'limit': 15},
        {'source': 'youtube', 'query': 'korean music 2024', 'limit': 20},
        {'source': 'youtube', 'query': 'jpop', 'limit': 15},
        {'source': 'youtube', 'query': 'nhac hoa', 'limit': 15},
        {'source': 'youtube', 'query': 'edm 2024', 'limit': 15},
        {'source': 'youtube', 'query': 'chill music', 'limit': 15},
        {'source': 'youtube', 'query': 'lo-fi hip hop', 'limit': 15},
        {'source': 'youtube', 'query': 'indie folk', 'limit': 15},
        {'source': 'youtube', 'query': 'jazz piano', 'limit': 15},
        {'source': 'youtube', 'query': 'rock ballads', 'limit': 15},
        {'source': 'youtube', 'query': 'r&b soul mix', 'limit': 15},
        {'source': 'jamendo', 'query': 'pop', 'limit': 20},
        {'source': 'jamendo', 'query': 'rock', 'limit': 20},
        {'source': 'jamendo', 'query': 'electronic', 'limit': 20},
        {'source': 'jamendo', 'query': 'hip-hop', 'limit': 20},
        {'source': 'jamendo', 'query': 'jazz', 'limit': 20},
        {'source': 'jamendo', 'query': 'classical', 'limit': 20},
        {'source': 'jamendo', 'query': 'ambient', 'limit': 20},
        {'source': 'jamendo', 'query': 'blues', 'limit': 20},
        {'source': 'jamendo', 'query': 'reggae', 'limit': 20},
        {'source': 'jamendo', 'query': 'funk', 'limit': 20},
        {'source': 'jamendo', 'query': 'soul', 'limit': 20},
        {'source': 'jamendo', 'query': 'latin', 'limit': 20},
        {'source': 'jamendo', 'query': 'world', 'limit': 20},
        {'source': 'jamendo', 'query': 'instrumental', 'limit': 20},
        {'source': 'jamendo', 'query': 'country', 'limit': 20},
        {'source': 'nct', 'query': 'v-pop', 'limit': 20},
        {'source': 'nct', 'query': 'nhac tre', 'limit': 20},
        {'source': 'nct', 'query': 'rap việt', 'limit': 20},
        {'source': 'nct', 'query': 'nhac tru tinh', 'limit': 20},
        {'source': 'nct', 'query': 'edm viet', 'limit': 20},
        {'source': 'nct', 'query': 'acoustic viet', 'limit': 20},
    ],
}


class Command(BaseCommand):
    help = 'Crawl songs from external sources and save to DB'

    def add_arguments(self, parser):
        parser.add_argument(
            '--preset',
            choices=list(PRESET_QUERIES.keys()),
            help='Use a preset list of queries',
        )
        parser.add_argument('--query', help='Single search query')
        parser.add_argument(
            '--source',
            default='youtube',
            choices=['youtube', 'jamendo', 'nct'],
            help='Source to search (default: youtube)',
        )
        parser.add_argument('--limit', type=int, default=50, help='Results per query/channel')
        parser.add_argument('--channel', help='Crawl all videos from a YouTube channel URL')
        parser.add_argument(
            '--channel-preset',
            choices=list(CHANNEL_PRESETS.keys()),
            help='Crawl channels from a preset list',
        )

    def handle(self, *args, **options):
        if options['channel']:
            self.stdout.write(f'Crawling YouTube channel: {options["channel"]}')
            result = crawl_youtube_channel(options['channel'], options['limit'])
            self.stdout.write(self.style.SUCCESS(
                f'Done: {result.get("saved", 0)} new, {result.get("exists", 0)} existed, '
                f'{result.get("errors", 0)} errors'
            ))
            return
        if options['channel_preset']:
            channels = CHANNEL_PRESETS[options['channel_preset']]
            self.stdout.write(f'Crawling channel preset: {options["channel_preset"]} ({len(channels)} channels)')
            for i, url in enumerate(channels, 1):
                self.stdout.write(f'  [{i}/{len(channels)}] {url}')
                result = crawl_youtube_channel(url, options['limit'])
                self.stdout.write(f'    saved={result.get("saved", 0)} exists={result.get("exists", 0)} errors={result.get("errors", 0)}')
                if result.get('error'):
                    self.stdout.write(self.style.WARNING(f'    error: {result["error"]}'))
            return
        if options['preset']:
            queries = PRESET_QUERIES[options['preset']]
            self.stdout.write(f'Crawling preset: {options["preset"]} ({len(queries)} queries)')
        elif options['query']:
            queries = [{'source': options['source'], 'query': options['query'], 'limit': options['limit']}]
        else:
            raise CommandError('Provide --preset, --query, --channel, or --channel-preset')

        results = crawl_queries(queries)

        total_saved = sum(r.get('saved', 0) for r in results)
        total_exists = sum(r.get('exists', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)

        self.stdout.write(self.style.SUCCESS(f'Done: {total_saved} new, {total_exists} existed, {total_errors} errors'))
        for r in results:
            self.stdout.write(f'  [{r.get("source")}] {r.get("query")}: {r.get("saved")} saved, {r.get("exists")} existed')
