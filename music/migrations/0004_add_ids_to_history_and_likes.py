from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('music', '0003_lyric_downloadedsong'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            ALTER TABLE play_history
                ADD COLUMN IF NOT EXISTS id bigserial;

            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'play_history'::regclass
                      AND contype = 'p'
                ) THEN
                    ALTER TABLE play_history
                        ADD CONSTRAINT play_history_pkey PRIMARY KEY (id);
                END IF;
            END $$;

            CREATE UNIQUE INDEX IF NOT EXISTS play_history_user_song_uidx
                ON play_history(user_id, song_id);

            ALTER TABLE liked_songs
                ADD COLUMN IF NOT EXISTS id bigserial;

            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'liked_songs'::regclass
                      AND contype = 'p'
                ) THEN
                    ALTER TABLE liked_songs
                        ADD CONSTRAINT liked_songs_pkey PRIMARY KEY (id);
                END IF;
            END $$;

            CREATE UNIQUE INDEX IF NOT EXISTS liked_songs_user_song_uidx
                ON liked_songs(user_id, song_id);
            ''',
            reverse_sql='''
            DROP INDEX IF EXISTS liked_songs_user_song_uidx;
            ALTER TABLE liked_songs DROP CONSTRAINT IF EXISTS liked_songs_pkey;
            ALTER TABLE liked_songs DROP COLUMN IF EXISTS id;

            DROP INDEX IF EXISTS play_history_user_song_uidx;
            ALTER TABLE play_history DROP CONSTRAINT IF EXISTS play_history_pkey;
            ALTER TABLE play_history DROP COLUMN IF EXISTS id;
            ''',
        ),
    ]
