from rest_framework import serializers

from music.models import Song
from music.serializers import SongSerializer
from .models import Playlist, PlaylistSong


class PlaylistListSerializer(serializers.ModelSerializer):
    song_count = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = ['id', 'title', 'description', 'image_url', 'song_count', 'created_at']

    def get_song_count(self, obj):
        return obj.playlistsong_set.count()


class PlaylistDetailSerializer(serializers.ModelSerializer):
    songs = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = ['id', 'title', 'description', 'image_url', 'songs', 'created_at']

    def get_songs(self, obj):
        playlist_songs = obj.playlistsong_set.select_related('song').all().order_by('position')
        return [
            {
                'id': ps.song.id,
                'title': ps.song.title,
                'subtitle': ps.song.subtitle,
                'image_url': ps.song.image_url,
                'audio_url': ps.song.audio_url,
                'duration': ps.song.duration,
                'source': ps.song.source,
                'position': ps.position,
            }
            for ps in playlist_songs
        ]


class PlaylistCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    image_url = serializers.CharField(required=False, allow_blank=True, default='')


class PlaylistUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)


class AddSongSerializer(serializers.Serializer):
    song_id = serializers.CharField(required=True)
