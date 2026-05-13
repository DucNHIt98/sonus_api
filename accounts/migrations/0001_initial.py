# Generated manually to register unmanaged Supabase users table in Django state.

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('avatar_url', models.TextField(blank=True, null=True)),
                ('full_name', models.TextField(blank=True, null=True)),
                ('email', models.TextField(blank=True, null=True, unique=True)),
                ('username', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'users',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='UserSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('device_id', models.CharField(blank=True, max_length=255)),
                ('device_name', models.CharField(blank=True, max_length=255)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='accounts.user')),
            ],
            options={
                'db_table': 'user_sessions',
            },
        ),
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['token_hash'], name='user_sessio_token_h_e8cef0_idx'),
        ),
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['user', 'revoked_at'], name='user_sessio_user_id_ae2696_idx'),
        ),
    ]
