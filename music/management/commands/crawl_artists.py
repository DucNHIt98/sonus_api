import logging

from django.core.management.base import BaseCommand, CommandError

from services.crawler import crawl_youtube

logger = logging.getLogger(__name__)

VN_ARTISTS = [
    "Sơn Tùng M-TP", "Đen Vâu", "Jack J97", "Hoàng Thùy Linh", "Mỹ Tâm",
    "MIN", "ERIK", "Hương Tràm", "Tóc Tiên", "Bích Phương",
    "Đức Phúc", "Văn Mai Hương", "Hòa Minzy", "Chi Pu", "Soobin Hoàng Sơn",
    "AMEE", "Karik", "JustaTee", "Phương Ly", "B Ray",
    "Quân A.P", "Đàm Vĩnh Hưng", "Noo Phước Thịnh", "Đông Nhi", "Phan Mạnh Quỳnh",
    "Trúc Nhân", "Suni Hạ Linh", "Tiên Tiên", "Orange", "Rhymastic",
    "Wowy", "Suboi", "HuyR", "LyLy", "Ngô Kiến Huy",
    "Jun Phạm", "Đạt G", "K-ICM", "Bảo Anh", "Ali Hoàng Dương",
    "Hồ Quỳnh Hương", "OnlyC", "Vũ Cát Tường", "Uyên Linh", "Tiến Cookie",
    "Andree Right Hand", "Hồ Ngọc Hà", "Lou Hoàng", "Jsol", "Lê Bảo Bình",
    "Khắc Hưng", "Châu Khải Phong", "Quang Hùng MasterD", "Thùy Chi", "Tùng Dương",
    "Da LAB", "365DaBand", "MONSTAR", "Uni5", "Gill",
    "Lil Wuyn", "Mikelodic", "Obito", "Pu Ly", "Tăng Duy Tân",
    "Hứa Kim Tuyền", "The Men", "Phương Mỹ Chi", "Pjnboys", "Huỳnh James",
    "LEG", "Hoàng Dũng", "H'Hen Niê",
]

USUK_ARTISTS = [
    "Taylor Swift", "Ed Sheeran", "Adele", "Bruno Mars", "Billie Eilish",
    "Olivia Rodrigo", "Dua Lipa", "Harry Styles", "The Weeknd", "Ariana Grande",
    "Beyoncé", "Lady Gaga", "Rihanna", "Justin Bieber", "Katy Perry",
    "Pink", "Miley Cyrus", "Selena Gomez", "Demi Lovato", "Shawn Mendes",
    "Charlie Puth", "Sam Smith", "Lana Del Rey", "Halsey", "Camila Cabello",
    "Post Malone", "Drake", "Kendrick Lamar", "Eminem", "Kanye West",
    "Jay-Z", "Nicki Minaj", "Cardi B", "Megan Thee Stallion", "Doja Cat",
    "Lizzo", "SZA", "Lil Nas X", "Travis Scott", "J. Cole",
    "Coldplay", "Maroon 5", "Imagine Dragons", "OneRepublic", "Foo Fighters",
    "Red Hot Chili Peppers", "Green Day", "Linkin Park", "Muse", "Radiohead",
    "Arctic Monkeys", "Queen", "The Beatles", "U2", "Nirvana",
    "Metallica", "AC/DC", "Led Zeppelin", "Guns N' Roses", "The Rolling Stones",
    "Alicia Keys", "John Legend", "Aretha Franklin", "Whitney Houston", "Mariah Carey",
    "Michael Jackson", "Prince", "Stevie Wonder", "Elton John", "Billy Joel",
    "David Bowie", "Freddie Mercury", "George Michael", "Phil Collins", "Sting",
    "R.E.M.", "The Police", "Dire Straits", "Bon Jovi", "Aerosmith",
    "Journey", "Fleetwood Mac", "Eagles", "Bee Gees", "ABBA",
    "Lady A", "Keith Urban", "Carrie Underwood", "Luke Combs", "Morgan Wallen",
    "Chris Stapleton", "Zac Brown Band", "Dolly Parton", "Johnny Cash", "Willie Nelson",
    "Bob Dylan", "Bruce Springsteen", "Tom Petty", "Paul McCartney", "Eric Clapton",
    "Santana", "Carlos Santana", "Lenny Kravitz", "Sheryl Crow", "Alanis Morissette",
    "Tracy Chapman", "Norah Jones", "Amy Winehouse", "Duffy", "Joss Stone",
    "James Bay", "Hozier", "Vance Joy", "Passenger", "Lumineers",
    "Mumford and Sons", "Kings of Leon", "The Killers", "The Strokes", "Vampire Weekend",
    "Tame Impala", "Mac DeMarco", "Beach Boys", "Beach House", "The National",
    "Arcade Fire", "Florence and the Machine", "Bastille", "Twenty One Pilots", "Fall Out Boy",
    "Panic at the Disco", "My Chemical Romance", "Blink-182", "System of a Down", "Slipknot",
]

KPOP_ARTISTS = [
    "BTS", "BLACKPINK", "TWICE", "EXO", "NCT 127", "NCT DREAM", "Stray Kids",
    "ATEEZ", "SEVENTEEN", "TXT", "ENHYPEN", "ITZY", "Red Velvet", "MAMAMOO",
    "(G)I-DLE", "aespa", "IVE", "LE SSERAFIM", "NewJeans", "BABYMONSTER",
    "KISS OF LIFE", "ZEROBASEONE", "RIIZE", "BOYNEXTDOOR", "TWS",
    "BIGBANG", "2NE1", "Girls' Generation", "SHINee", "Super Junior",
    "2PM", "Wonder Girls", "KARA", "T-ARA", "SISTAR", "miss A", "f(x)",
    "Apink", "GFRIEND", "IZ*ONE", "Fromis_9", "Oh My Girl", "LOONA",
    "Dreamcatcher", "Everglow", "STAYC", "Weeekly", "Cherry Bullet",
    "WJSN", "Pentagon", "Monsta X", "VIXX", "BTOB", "INFINITE",
    "Highlight", "CNBLUE", "FTISLAND", "Day6", "The Rose", "N.Flying",
    "ASTRO", "Golden Child", "ONF", "SF9", "The Boyz", "Cravity",
    "AB6IX", "CIX", "VERIVERY", "ONEUS", "OnlyOneOf", "EPEX",
    "IU", "Zico", "PSY", "G-Dragon", "Taeyang", "CL", "Bobby",
    "Mino", "BewhY", "Jay Park", "Crush", "Dean", "Beenzino",
    "Changmo", "Loco", "Gray", "Sik-K", "pH-1", "Haon",
    "Taeyeon", "Sunmi", "Chungha", "Heize", "Ailee", "Hyuna",
    "Lee Hi", "Baekhyun", "Kai", "D.O.", "Chen", "Suho", "Xiumin",
    "Taemin", "Key", "Onew", "Minho", "Jonghyun",
    "Solar", "Moonbyul", "Wheein", "Hwasa",
    "J.Y. Park", "Rain", "BoA", "Se7en", "Bibi", "Somi",
    "Younha", "Yerin Baek", "BOL4", "AKMU", "DAVICHI", "Urban Zakapa",
    "M.C the Max", "Jannabi", "Nell", "Guckkasten", "Busker Busker",
    "Epik High", "Dynamic Duo", "Leessang", "Gary", "Verbal Jint",
]

PRESETS = {
    'vn': VN_ARTISTS,
    'us-uk': USUK_ARTISTS,
    'k-pop': KPOP_ARTISTS,
}


class Command(BaseCommand):
    help = 'Search và lưu bài hát từ danh sách nghệ sĩ (dùng YouTube search)'

    def add_arguments(self, parser):
        parser.add_argument('--preset', choices=list(PRESETS.keys()), default='vn', help='Danh sách nghệ sĩ')
        parser.add_argument('--limit', type=int, default=50, help='Kết quả tối đa / nghệ sĩ')
        parser.add_argument('--dry-run', action='store_true', help='Chỉ in kết quả, không lưu')
        parser.add_argument('--from', type=int, default=1, dest='from_idx', help='Bắt đầu từ index (1-based)')
        parser.add_argument('--to', type=int, default=0, dest='to_idx', help='Kết thúc tại index (0 = hết)')
        parser.add_argument('--query-suffix', default=' nhạc', help='Hậu tố tìm kiếm (mặc định: " nhạc")')

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        from_idx = options['from_idx'] - 1
        to_idx = options['to_idx'] or 0
        preset = options['preset']
        suffix = options['query_suffix']

        artists = PRESETS[preset]
        if to_idx:
            artists = artists[from_idx:to_idx]
        elif from_idx:
            artists = artists[from_idx:]

        if preset in ('us-uk', 'k-pop'):
            suffix = ' songs'

        total_saved = 0
        total_exists = 0
        total_errors = 0

        for i, artist in enumerate(artists, 1):
            query = f'{artist}{suffix}'
            self.stdout.write(f'[{i}/{len(artists)}] {query}... ', ending='')
            self.stdout.flush()

            if dry_run:
                from services.youtube import search_youtube
                try:
                    results = search_youtube(query, limit=limit)
                    from music.models import Song
                    ids = [r['id'] for r in results]
                    existing = set(Song.objects.filter(id__in=ids).values_list('id', flat=True))
                    new_count = sum(1 for rid in ids if rid not in existing)
                    self.stdout.write(f'{len(results)} kq ({new_count} mới, {len(results) - new_count} cũ)')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ {e}'))
                    total_errors += 1
            else:
                result = crawl_youtube(query, limit)
                saved = result.get('saved', 0)
                exists = result.get('exists', 0)
                errors = result.get('errors', 0)
                total_saved += saved
                total_exists += exists
                total_errors += errors
                self.stdout.write(f'{saved} saved, {exists} exists, {errors} errors')

        if dry_run:
            msg = f'\nDone dry-run: {len(artists)} artists, {total_errors} errors'
        else:
            msg = f'\nDone: {total_saved} saved, {total_exists} exists, {total_errors} errors'
        self.stdout.write(self.style.SUCCESS(msg))
