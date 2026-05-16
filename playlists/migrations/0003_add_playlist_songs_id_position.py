from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('playlists', '0002_playlist_user_playlistsong_added_at'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            ALTER TABLE playlist_songs
                ADD COLUMN IF NOT EXISTS id bigserial;

            ALTER TABLE playlist_songs
                ADD COLUMN IF NOT EXISTS position integer NOT NULL DEFAULT 0;

            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'playlist_songs'::regclass
                      AND contype = 'p'
                ) THEN
                    ALTER TABLE playlist_songs
                        ADD CONSTRAINT playlist_songs_pkey PRIMARY KEY (id);
                END IF;
            END $$;

            CREATE INDEX IF NOT EXISTS playlist_songs_playlist_id_idx
                ON playlist_songs(playlist_id);

            CREATE INDEX IF NOT EXISTS playlist_songs_song_id_idx
                ON playlist_songs(song_id);
            ''',
            reverse_sql='''
            DROP INDEX IF EXISTS playlist_songs_song_id_idx;
            DROP INDEX IF EXISTS playlist_songs_playlist_id_idx;
            ALTER TABLE playlist_songs DROP CONSTRAINT IF EXISTS playlist_songs_pkey;
            ALTER TABLE playlist_songs DROP COLUMN IF EXISTS position;
            ALTER TABLE playlist_songs DROP COLUMN IF EXISTS id;
            ''',
        ),
    ]
