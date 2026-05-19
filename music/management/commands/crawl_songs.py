from django.core.management.base import BaseCommand, CommandError

from services.crawler import crawl_queries, crawl_youtube_channel

PRESET_QUERIES = {
}

CHANNEL_PRESETS = {
    'viet-nam-top': [
        # === Vpop Solo Artists ===
        'https://www.youtube.com/@SonTungMTP/videos',
        'https://www.youtube.com/@JackJ97/videos',
        'https://www.youtube.com/@DenVauOfficial/videos',
        'https://www.youtube.com/@HoangThuyLinh/videos',
        'https://www.youtube.com/@MyTamOfficial/videos',
        'https://www.youtube.com/@HoNgocHaOfficial/videos',
        'https://www.youtube.com/@MINofficial/videos',
        'https://www.youtube.com/@ErikOfficial/videos',
        'https://www.youtube.com/@HuongTramOfficial/videos',
        'https://www.youtube.com/@TocTienOfficial/videos',
        'https://www.youtube.com/@BichPhuongOfficial/videos',
        'https://www.youtube.com/@DucPhucOfficial/videos',
        'https://www.youtube.com/@VanMaiHuongOfficial/videos',
        'https://www.youtube.com/@HoaMinzy/videos',
        'https://www.youtube.com/@ChiPuOfficial/videos',
        'https://www.youtube.com/@SoobinHoangSon/videos',
        'https://www.youtube.com/@AmeeOfficial/videos',
        'https://www.youtube.com/@KarikOfficial/videos',
        'https://www.youtube.com/@JustaTee/videos',
        'https://www.youtube.com/@PhuongLyOfficial/videos',
        'https://www.youtube.com/@BRayOfficial/videos',
        'https://www.youtube.com/@QuanAPOfficial/videos',
        'https://www.youtube.com/@DamVinhHungOfficial/videos',
        'https://www.youtube.com/@NooPhuocThinh/videos',
        'https://www.youtube.com/@DongNhiOfficial/videos',
        'https://www.youtube.com/@PhanManhQuynh/videos',
        'https://www.youtube.com/@TrucNhanOfficial/videos',
        'https://www.youtube.com/@SuniHaLinh/videos',
        'https://www.youtube.com/@TienTienOfficial/videos',
        'https://www.youtube.com/@OrangeVpop/videos',
        'https://www.youtube.com/@AndreeRightHand/videos',
        'https://www.youtube.com/@Rhymastic/videos',
        'https://www.youtube.com/@WowyOfficial/videos',
        'https://www.youtube.com/@Suboi/videos',
        'https://www.youtube.com/@HuyROfficial/videos',
        'https://www.youtube.com/@TienCookie/videos',
        'https://www.youtube.com/@JsolOfficial/videos',
        'https://www.youtube.com/@LyLyOfficial/videos',
        'https://www.youtube.com/@NgoKienHuy/videos',
        'https://www.youtube.com/@JunPham/videos',
        'https://www.youtube.com/@LouHoang/videos',
        'https://www.youtube.com/@DatGOfficial/videos',
        'https://www.youtube.com/@KICM/videos',
        'https://www.youtube.com/@BaoAnhOfficial/videos',
        'https://www.youtube.com/@HoangDungOfficial/videos',
        'https://www.youtube.com/@AliHoangDuong/videos',
        'https://www.youtube.com/@HoQuynhHuongOfficial/videos',
        'https://www.youtube.com/@OnlyC/videos',
        'https://www.youtube.com/@VuCatTuong/videos',
        'https://www.youtube.com/@UyenLinh/videos',
        # === Vpop Groups ===
        'https://www.youtube.com/@DaLABOfficial/videos',
        'https://www.youtube.com/@365DaBand/videos',
        'https://www.youtube.com/@MonstarOfficial/videos',
        'https://www.youtube.com/@Uni5Official/videos',
        'https://www.youtube.com/@SGO48/videos',
        'https://www.youtube.com/@LipBOfficial/videos',
        # === Traditional / Older Generation ===
        'https://www.youtube.com/@MyLinhOfficial/videos',
        'https://www.youtube.com/@HaTranOfficial/videos',
        'https://www.youtube.com/@HongNhungOfficial/videos',
        'https://www.youtube.com/@LeQuyenOfficial/videos',
        'https://www.youtube.com/@CamLyOfficial/videos',
        'https://www.youtube.com/@DanTruongOfficial/videos',
        'https://www.youtube.com/@QuangLeOfficial/videos',
        'https://www.youtube.com/@TuanHung/videos',
        'https://www.youtube.com/@HaAnhTuanOfficial/videos',
        'https://www.youtube.com/@LuongBichHuu/videos',
        'https://www.youtube.com/@PhuongVyOfficial/videos',
        'https://www.youtube.com/@HoVietTrung/videos',
        'https://www.youtube.com/@ChauKhaiPhong/videos',
        'https://www.youtube.com/@QuangHungMasterD/videos',
        'https://www.youtube.com/@PhamQuynhAnh/videos',
        'https://www.youtube.com/@ThuyChi/videos',
        'https://www.youtube.com/@ThanhLam/videos',
        'https://www.youtube.com/@TungDuong/videos',
        # === Rap / Hip-hop ===
        'https://www.youtube.com/@HuuDuyen/videos',
        'https://www.youtube.com/@TienDat/videos',
        'https://www.youtube.com/@GillNeo/videos',
        'https://www.youtube.com/@LilWuyn/videos',
        'https://www.youtube.com/@Mikelodic/videos',
        'https://www.youtube.com/@Obito/videos',
        'https://www.youtube.com/@PuLy/videos',
        'https://www.youtube.com/@SMOfficial/videos',
        'https://www.youtube.com/@Killerman/videos',
        # === Indie / Acoustic / Others ===
        'https://www.youtube.com/@VoHaTran/videos',
        'https://www.youtube.com/@HualanAnh/videos',
        'https://www.youtube.com/@TheMen/videos',
        'https://www.youtube.com/@DuongGiaHuy/videos',
        'https://www.youtube.com/@MaiMinh/videos',
        'https://www.youtube.com/@MyraTran/videos',
        'https://www.youtube.com/@ThuyChiOfficial/videos',
        'https://www.youtube.com/@PhuongMyChi/videos',
        'https://www.youtube.com/@HienHo/videos',
        'https://www.youtube.com/@HoangTon/videos',
        'https://www.youtube.com/@Pjnboys/videos',
        'https://www.youtube.com/@HuynhJames/videos',
        'https://www.youtube.com/@LEG/videos',
        # === More Artists ===
        'https://www.youtube.com/@AnhTuyet/videos',
        'https://www.youtube.com/@NguyenSang/videos',
        'https://www.youtube.com/@DuongHieu/videos',
        'https://www.youtube.com/@PhuongAnh/videos',
        'https://www.youtube.com/@HoangMy/videos',
        'https://www.youtube.com/@ThaiThuyLinh/videos',
        'https://www.youtube.com/@BaoThy/videos',
        'https://www.youtube.com/@TruongThaoNhi/videos',
        'https://www.youtube.com/@TramAnh/videos',
        'https://www.youtube.com/@HienThuc/videos',
        'https://www.youtube.com/@KhacViet/videos',
        'https://www.youtube.com/@ThanhNgan/videos',
        'https://www.youtube.com/@NhuQuynh/videos',
        'https://www.youtube.com/@CheLinh/videos',
        'https://www.youtube.com/@MaiHoa/videos',
        'https://www.youtube.com/@MyDung/videos',
        'https://www.youtube.com/@DinhHuong/videos',
        'https://www.youtube.com/@TamDoan/videos',
        'https://www.youtube.com/@AnhKhoa/videos',
        'https://www.youtube.com/@DangKhoi/videos',
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
