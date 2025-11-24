"""
Views package for Ridgway Garage telemetry app.

This package splits views into logical modules for better organization.
All views are re-exported here to maintain backward compatibility with urls.py.
"""

# Import team views from the teams module
from .teams import (
    team_list,
    team_create,
    team_detail,
    team_edit,
    team_delete,
    # Join request views
    team_request_join,
    team_cancel_request,
    team_manage_requests,
    team_approve_request,
    team_reject_request,
    # Invitation views
    team_invite_user,
    team_manage_invites,
    team_accept_invite,
    team_decline_invite,
)

# Import all other views from views_main.py (temporary during refactoring)
# These will gradually be split into their own modules
from ..views_main import (
    # Helper functions
    api_token_required,
    build_lap_export_data,
    compress_lap_export_data,
    import_lap_from_data,

    # Core views
    home,
    dashboard_analysis,
    session_list,
    upload,
    session_delete,

    # Lap export/import
    lap_export,
    lap_share_to_discord,

    # User settings
    user_settings,
    leaderboards,

    # API endpoints
    api_auth_test,
    api_upload,
    api_lap_telemetry,
    api_fastest_laps,
    api_generate_chart,
)

__all__ = [
    # Helper functions
    'api_token_required',
    'build_lap_export_data',
    'compress_lap_export_data',
    'import_lap_from_data',

    # Team views (from teams.py)
    'team_list',
    'team_create',
    'team_detail',
    'team_edit',
    'team_delete',
    'team_request_join',
    'team_cancel_request',
    'team_manage_requests',
    'team_approve_request',
    'team_reject_request',
    'team_invite_user',
    'team_manage_invites',
    'team_accept_invite',
    'team_decline_invite',

    # Core views (from views_main.py)
    'home',
    'dashboard_analysis',
    'session_list',
    'upload',
    'session_delete',

    # Lap export/import
    'lap_export',
    'lap_share_to_discord',

    # User settings
    'user_settings',
    'leaderboards',

    # API endpoints
    'api_auth_test',
    'api_upload',
    'api_lap_telemetry',
    'api_fastest_laps',
    'api_generate_chart',
]
