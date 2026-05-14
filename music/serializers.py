from rest_framework import serializers

from .models import Song, PlayHistory, LikedSong


class SongSerializer(serializers.ModelSerializer):
    class Meta:
        model = Song
        fields = [
            'id', 'title', 'subtitle', 'image_url', 'audio_url',
            'album_name', 'source', 'genre', 'region', 'duration',
        ]


class PlayHistorySerializer(serializers.ModelSerializer):
    song = SongSerializer(read_only=True)

    class Meta:
        model = PlayHistory
        fields = ['song', 'count', 'last_played']


class RecordPlaySerializer(serializers.Serializer):
    song_id = serializers.CharField(required=True)
    progress_percent = serializers.FloatField(required=True, min_value=0, max_value=100)
    title = serializers.CharField(required=False, allow_blank=True)
    subtitle = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.CharField(required=False, allow_blank=True)
    duration = serializers.IntegerField(required=False, allow_null=True)

    def validate_progress_percent(self, value):
        if value < 50:
            raise serializers.ValidationError('Progress must be at least 50% to record a play')
        return value


class LikedSongSerializer(serializers.ModelSerializer):
    song = SongSerializer(read_only=True)

    class Meta:
        model = LikedSong
        fields = ['song', 'created_at']


class ResolveAudioSerializer(serializers.Serializer):
    video_id = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    artist = serializers.CharField(required=False)
    deezer_id = serializers.CharField(required=False)
    youtube_id = serializers.CharField(required=False)

    def validate(self, attrs):
        if not any(k in attrs for k in ('video_id', 'youtube_id', 'title')):
            raise serializers.ValidationError('Provide video_id, youtube_id, or title+artist')
        return attrs


class SearchSerializer(serializers.Serializer):
    q = serializers.CharField(required=True)
    limit = serializers.IntegerField(default=10, min_value=1, max_value=50)
    sources = serializers.CharField(required=False, default='youtube,jamendo,nct')
