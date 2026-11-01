from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='watchlist'),
    path(
        'watchlist/<int:pk>/delete/',
        views.remove,
        name='watchlist_remove',
    ),
]
