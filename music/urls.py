from django.urls import path

from .views import (
    AutocompleteView,
    ChartDetailView,
    FavoriteListView,
    FavoriteToggleView,
    GenreTrackListView,
    HomeFeedView,
    PlayHistoryView,
    RecordPlayView,
    ResolveAudioView,
    SearchView,
    TopPlayedView,
)

urlpatterns = [
    path('music/resolve/', ResolveAudioView.as_view(), name='music-resolve'),
    path('music/search/', SearchView.as_view(), name='music-search'),
    path('music/autocomplete/', AutocompleteView.as_view(), name='music-autocomplete'),
    path('music/feed/', HomeFeedView.as_view(), name='music-feed'),
    path('music/charts/', ChartDetailView.as_view(), name='music-charts'),
    path('music/genres/', GenreTrackListView.as_view(), name='music-genres'),
    # Phase 3 — History
    path('history/record/', RecordPlayView.as_view(), name='history-record'),
    path('history/', PlayHistoryView.as_view(), name='history-list'),
    path('history/top/', TopPlayedView.as_view(), name='history-top'),

    # Phase 3 — Favorites
    path('favorites/', FavoriteListView.as_view(), name='favorites-list'),
    path('favorites/<str:song_id>/', FavoriteToggleView.as_view(), name='favorites-toggle'),
]
