"""
URL configuration for the telemetry app.
"""

from django.urls import path
from . import views

app_name = 'telemetry'

urlpatterns = [
    # Home/Dashboard
    path('', views.home, name='home'),
    path('analysis/', views.dashboard_analysis, name='analysis'),

    # Session management
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/delete/', views.session_delete, name='session_delete'),

    # Upload
    path('upload/', views.upload, name='upload'),

    # Lap views
    path('laps/<int:pk>/export/', views.lap_export, name='lap_export'),
    path('laps/<int:pk>/share-to-discord/<int:team_id>/', views.lap_share_to_discord, name='lap_share_to_discord'),

    # Team management
    path('teams/', views.team_list, name='team_list'),
    path('teams/create/', views.team_create, name='team_create'),
    path('teams/<int:pk>/', views.team_detail, name='team_detail'),
    path('teams/<int:pk>/edit/', views.team_edit, name='team_edit'),
    path('teams/<int:pk>/delete/', views.team_delete, name='team_delete'),

    # Leaderboards
    path('leaderboards/', views.leaderboards, name='leaderboards'),

    # User Settings
    path('settings/', views.user_settings, name='user_settings'),

    # API
    path('api/auth/test/', views.api_auth_test, name='api_auth_test'),
    path('api/upload/', views.api_upload, name='api_upload'),
    path('api/laps/<int:lap_id>/telemetry/', views.api_lap_telemetry, name='api_lap_telemetry'),
    path('api/fastest-laps/', views.api_fastest_laps, name='api_fastest_laps'),
    path('api/generate-chart/', views.api_generate_chart, name='api_generate_chart'),
]
