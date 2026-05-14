import uuid

from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AddSongSerializer,
    PlaylistCreateSerializer,
    PlaylistUpdateSerializer,
)


class PlaylistListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT id, title, description, image_url, created_at FROM playlists ORDER BY created_at DESC'
            )
            rows = cursor.fetchall()

        playlists = []
        for row in rows:
            playlist_id = str(row[0])
            with connection.cursor() as c:
                c.execute(
                    'SELECT COUNT(*) FROM playlist_songs WHERE playlist_id = %s',
                    [playlist_id],
                )
                song_count = c.fetchone()[0]
            playlists.append({
                'id': playlist_id,
                'title': row[1],
                'description': row[2],
                'image_url': row[3],
                'song_count': song_count,
                'created_at': row[4],
            })

        return Response({'playlists': playlists})

    def post(self, request):
        serializer = PlaylistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        playlist_id = str(uuid.uuid4())

        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO playlists (id, user_id, title, description, image_url, created_at) VALUES (%s, %s, %s, %s, %s, %s)',
                [
                    playlist_id,
                    str(request.user.id),
                    serializer.validated_data['title'],
                    serializer.validated_data.get('description', ''),
                    serializer.validated_data.get('image_url', ''),
                    timezone.now(),
                ],
            )

        return Response({
            'id': playlist_id,
            'title': serializer.validated_data['title'],
            'description': serializer.validated_data.get('description', ''),
            'image_url': serializer.validated_data.get('image_url', ''),
            'song_count': 0,
            'created_at': timezone.now(),
        }, status=status.HTTP_201_CREATED)


class PlaylistDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT id, title, description, image_url, created_at FROM playlists WHERE id = %s',
                [pk],
            )
            row = cursor.fetchone()
            if not row:
                return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

            cursor.execute(
                'SELECT s.id, s.title, s.subtitle, s.image_url, s.audio_url, s.duration, s.source, ps.added_at '
                'FROM playlist_songs ps JOIN songs s ON s.id = ps.song_id '
                'WHERE ps.playlist_id = %s ORDER BY ps.added_at',
                [pk],
            )
            song_rows = cursor.fetchall()

        songs = [
            {
                'id': r[0],
                'title': r[1],
                'subtitle': r[2],
                'image_url': r[3],
                'audio_url': r[4],
                'duration': r[5],
                'source': r[6],
            }
            for r in song_rows
        ]

        return Response({
            'id': str(row[0]),
            'title': row[1],
            'description': row[2],
            'image_url': row[3],
            'songs': songs,
            'created_at': row[4],
        })

    def patch(self, request, pk):
        serializer = PlaylistUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updates = []
        params = []
        for field in ['title', 'description']:
            if field in serializer.validated_data:
                updates.append(f'{field} = %s')
                params.append(serializer.validated_data[field])

        if not updates:
            return Response({'detail': 'No fields to update'})

        params.append(pk)
        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE playlists SET {", ".join(updates)} WHERE id = %s RETURNING id, title, description, image_url, created_at',
                params,
            )
            row = cursor.fetchone()
            if not row:
                return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

            cursor.execute(
                'SELECT COUNT(*) FROM playlist_songs WHERE playlist_id = %s',
                [pk],
            )
            song_count = cursor.fetchone()[0]

        return Response({
            'id': str(row[0]),
            'title': row[1],
            'description': row[2],
            'image_url': row[3],
            'song_count': song_count,
            'created_at': row[4],
        })

    def delete(self, request, pk):
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM playlists WHERE id = %s RETURNING id', [pk])
            if not cursor.fetchone():
                return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlaylistSongManageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM playlists WHERE id = %s', [pk])
            if not cursor.fetchone():
                return Response({'detail': 'Playlist not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AddSongSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        song_id = serializer.validated_data['song_id']

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT 1 FROM playlist_songs WHERE playlist_id = %s AND song_id = %s',
                [pk, song_id],
            )
            if cursor.fetchone():
                return Response({'detail': 'Song already in playlist'})

            cursor.execute(
                'INSERT INTO playlist_songs (playlist_id, song_id, added_at) VALUES (%s, %s, %s)',
                [pk, song_id, timezone.now()],
            )

        return Response({'detail': 'Song added to playlist'}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk, song_id):
        with connection.cursor() as cursor:
            cursor.execute(
                'DELETE FROM playlist_songs WHERE playlist_id = %s AND song_id = %s',
                [pk, song_id],
            )
            if cursor.rowcount == 0:
                return Response({'detail': 'Song not in playlist'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'Song removed from playlist'})
