from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('playlists', '0003_add_playlist_songs_id_position'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            CREATE INDEX IF NOT EXISTS playlists_user_created_at_idx
                ON playlists(user_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS playlist_songs_playlist_position_idx
                ON playlist_songs(playlist_id, position);
            ''',
            reverse_sql='''
            DROP INDEX IF EXISTS playlist_songs_playlist_position_idx;
            DROP INDEX IF EXISTS playlists_user_created_at_idx;
            ''',
        ),
    ]
