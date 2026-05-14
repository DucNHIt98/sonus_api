from django.urls import path

from .views import RecommendView

urlpatterns = [
    path('recommendations/', RecommendView.as_view(), name='recommendations'),
]
