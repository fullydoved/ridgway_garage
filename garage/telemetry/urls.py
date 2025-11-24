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

    # Join requests
    path('teams/<int:pk>/request-join/', views.team_request_join, name='team_request_join'),
    path('teams/<int:pk>/cancel-request/', views.team_cancel_request, name='team_cancel_request'),
    path('teams/<int:pk>/manage-requests/', views.team_manage_requests, name='team_manage_requests'),
    path('teams/<int:pk>/requests/<int:request_id>/approve/', views.team_approve_request, name='team_approve_request'),
    path('teams/<int:pk>/requests/<int:request_id>/reject/', views.team_reject_request, name='team_reject_request'),

    # Team invitations
    path('teams/<int:pk>/invite/', views.team_invite_user, name='team_invite_user'),
    path('teams/<int:pk>/manage-invites/', views.team_manage_invites, name='team_manage_invites'),
    path('teams/invites/<uuid:token>/accept/', views.team_accept_invite, name='team_accept_invite'),
    path('teams/invites/<uuid:token>/decline/', views.team_decline_invite, name='team_decline_invite'),

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
