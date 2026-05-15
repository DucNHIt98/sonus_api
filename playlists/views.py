from django.db.models import Count, Max
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import FREE_PLAYLIST_LIMIT, is_premium

from .models import Playlist, PlaylistSong
from .serializers import (
    AddSongSerializer,
    PlaylistCreateSerializer,
    PlaylistUpdateSerializer,
)


class PlaylistListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = Playlist.objects.filter(user=request.user)\
            .annotate(song_count=Count('playlistsong'))\
            .order_by('-created_at')
        total = qs.count()

        playlists = [
            {
                'id': str(p.id),
                'title': p.title,
                'description': p.description,
                'image_url': p.image_url,
                'song_count': p.song_count,
                'created_at': p.created_at,
            }
            for p in qs[offset:offset + limit]
        ]

        return Response({'playlists': playlists, 'total': total})

    def post(self, request):
        if not is_premium(str(request.user.id)):
            current_count = Playlist.objects.filter(user=request.user).count()
            if current_count >= FREE_PLAYLIST_LIMIT:
                return Response(
                    {'detail': f'Playlist limit reached ({FREE_PLAYLIST_LIMIT}). Upgrade to Premium for unlimited playlists.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = PlaylistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        playlist = Playlist.objects.create(
            user=request.user,
            title=serializer.validated_data['title'],
            description=serializer.validated_data.get('description', ''),
            image_url=serializer.validated_data.get('image_url', ''),
            created_at=timezone.now(),
        )

        return Response({
            'id': str(playlist.id),
            'title': playlist.title,
            'description': playlist.description,
            'image_url': playlist.image_url,
            'song_count': 0,
            'created_at': playlist.created_at,
        }, status=status.HTTP_201_CREATED)


class PlaylistDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 50))

        try:
            playlist = Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        song_qs = PlaylistSong.objects.filter(playlist=playlist)\
            .select_related('song')\
            .order_by('position')[offset:offset + limit]
        total_songs = PlaylistSong.objects.filter(playlist=playlist).count()

        songs = [
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
            for ps in song_qs
        ]

        return Response({
            'id': str(playlist.id),
            'title': playlist.title,
            'description': playlist.description,
            'image_url': playlist.image_url,
            'songs': songs,
            'song_count': total_songs,
            'created_at': playlist.created_at,
        })

    def patch(self, request, pk):
        serializer = PlaylistUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            playlist = Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        for field in ('title', 'description', 'image_url'):
            if field in serializer.validated_data:
                setattr(playlist, field, serializer.validated_data[field])

        if not any(f in serializer.validated_data for f in ('title', 'description', 'image_url')):
            return Response({'detail': 'No fields to update'})

        playlist.save()
        song_count = PlaylistSong.objects.filter(playlist=playlist).count()

        return Response({
            'id': str(playlist.id),
            'title': playlist.title,
            'description': playlist.description,
            'image_url': playlist.image_url,
            'song_count': song_count,
            'created_at': playlist.created_at,
        })

    def delete(self, request, pk):
        deleted, _ = Playlist.objects.filter(id=pk, user=request.user).delete()
        if deleted == 0:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlaylistSongManageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            playlist = Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return Response({'detail': 'Playlist not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AddSongSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        song_id = serializer.validated_data['song_id']

        if PlaylistSong.objects.filter(playlist=playlist, song_id=song_id).exists():
            return Response({'detail': 'Song already in playlist'})

        max_pos = PlaylistSong.objects.filter(playlist=playlist)\
            .aggregate(max_pos=Max('position'))['max_pos'] or 0

        PlaylistSong.objects.create(
            playlist=playlist,
            song_id=song_id,
            position=max_pos + 1,
            created_at=timezone.now(),
        )

        return Response({'detail': 'Song added to playlist', 'position': max_pos + 1}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk, song_id):
        deleted, _ = PlaylistSong.objects.filter(
            playlist__id=pk, playlist__user=request.user, song_id=song_id,
        ).delete()
        if deleted == 0:
            return Response({'detail': 'Song not in playlist'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'Song removed from playlist'})


class PlaylistReorderView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        song_ids = request.data.get('song_ids', [])
        if not isinstance(song_ids, list) or len(song_ids) < 2:
            return Response({'detail': 'song_ids must be a list with at least 2 items'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return Response({'detail': 'Playlist not found'}, status=status.HTTP_404_NOT_FOUND)

        for idx, song_id in enumerate(song_ids):
            PlaylistSong.objects.filter(playlist_id=pk, song_id=song_id).update(position=idx)

        return Response({'detail': 'Playlist reordered', 'song_ids': song_ids})
