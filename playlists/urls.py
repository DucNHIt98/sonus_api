from django.urls import path

from .views import PlaylistDetailView, PlaylistListView, PlaylistSongManageView

urlpatterns = [
    path('playlists/', PlaylistListView.as_view(), name='playlists-list'),
    path('playlists/<uuid:pk>/', PlaylistDetailView.as_view(), name='playlists-detail'),
    path('playlists/<uuid:pk>/songs/', PlaylistSongManageView.as_view(), name='playlists-add-song'),
    path('playlists/<uuid:pk>/songs/<str:song_id>/', PlaylistSongManageView.as_view(), name='playlists-remove-song'),
]
