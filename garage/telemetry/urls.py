"""
URL configuration for the telemetry app.
"""

from django.urls import path
from . import views

app_name = 'telemetry'

urlpatterns = [
    # Home/Dashboard
    path('', views.home, name='home'),

    # Session management
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/delete/', views.session_delete, name='session_delete'),

    # Upload
    path('upload/', views.upload, name='upload'),

    # Lap views
    path('laps/<int:pk>/', views.lap_detail, name='lap_detail'),
    path('laps/<int:pk>/export/', views.lap_export, name='lap_export'),
    path('laps/<int:pk>/share-to-discord/<int:team_id>/', views.lap_share_to_discord, name='lap_share_to_discord'),
    path('laps/import/', views.lap_import, name='lap_import'),
    path('laps/import/protocol/<str:base64_data>/', views.protocol_import, name='protocol_import'),
    path('compare/', views.lap_compare, name='lap_compare'),

    # Analysis (lap comparison)
    path('analyses/', views.analysis_list, name='analysis_list'),
    path('analyses/create/', views.analysis_create, name='analysis_create'),
    path('analyses/<int:pk>/', views.analysis_detail, name='analysis_detail'),
    path('analyses/<int:pk>/edit/', views.analysis_edit, name='analysis_edit'),
    path('analyses/<int:pk>/delete/', views.analysis_delete, name='analysis_delete'),
    path('analyses/<int:pk>/add-lap/<int:lap_id>/', views.analysis_add_lap, name='analysis_add_lap'),
    path('analyses/<int:pk>/remove-lap/<int:lap_id>/', views.analysis_remove_lap, name='analysis_remove_lap'),

    # Team management
    path('teams/', views.team_list, name='team_list'),
    path('teams/create/', views.team_create, name='team_create'),
    path('teams/<int:pk>/', views.team_detail, name='team_detail'),
    path('teams/<int:pk>/edit/', views.team_edit, name='team_edit'),
    path('teams/<int:pk>/delete/', views.team_delete, name='team_delete'),

    # System Update (admin only)
    path('system/update/', views.system_update_page, name='system_update'),
    path('system/update/check/', views.system_update_check, name='system_update_check'),
    path('system/update/trigger/', views.system_update_trigger, name='system_update_trigger'),
    path('system/update/history/', views.system_update_history, name='system_update_history'),

    # Live Telemetry
    path('live/', views.live_sessions, name='live_sessions'),
    path('live/<int:pk>/', views.live_session_detail, name='live_session_detail'),
    path('api-token/', views.api_token_view, name='api_token'),
]
