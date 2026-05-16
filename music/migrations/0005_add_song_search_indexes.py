from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('music', '0004_add_ids_to_history_and_likes'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            CREATE EXTENSION IF NOT EXISTS pg_trgm;

            CREATE INDEX IF NOT EXISTS songs_title_trgm_idx
                ON songs USING gin (title gin_trgm_ops);

            CREATE INDEX IF NOT EXISTS songs_subtitle_trgm_idx
                ON songs USING gin (subtitle gin_trgm_ops);

            CREATE INDEX IF NOT EXISTS songs_album_name_trgm_idx
                ON songs USING gin (album_name gin_trgm_ops);

            CREATE INDEX IF NOT EXISTS songs_created_at_idx
                ON songs(created_at DESC);
            ''',
            reverse_sql='''
            DROP INDEX IF EXISTS songs_created_at_idx;
            DROP INDEX IF EXISTS songs_album_name_trgm_idx;
            DROP INDEX IF EXISTS songs_subtitle_trgm_idx;
            DROP INDEX IF EXISTS songs_title_trgm_idx;
            ''',
        ),
    ]
