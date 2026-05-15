from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('playlists', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='playlist',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=models.CASCADE,
                to='accounts.user',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='playlistsong',
            name='created_at',
            field=models.DateTimeField(db_column='added_at'),
        ),
    ]
