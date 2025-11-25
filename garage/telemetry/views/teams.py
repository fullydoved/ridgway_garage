"""
Team management views for Ridgway Garage.

Handles team CRUD operations, membership management, and team detail views.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db.models import Q

from ..models import Team, JoinRequest, TeamInvitation, TeamMembership


@login_required
def team_list(request):
    """
    List teams the user belongs to and public teams with search.
    """
    # Get search query
    search_query = request.GET.get('search', '').strip()

    # Teams the user is a member of
    user_teams = Team.objects.filter(members=request.user).prefetch_related('members')

    if search_query:
        user_teams = user_teams.filter(name__icontains=search_query)

    # Teams that allow join requests (not a member of)
    public_teams = Team.objects.filter(allow_join_requests=True).exclude(members=request.user)

    if search_query:
        public_teams = public_teams.filter(name__icontains=search_query)

    # Get user's pending join requests
    pending_requests = JoinRequest.objects.filter(
        user=request.user,
        status='pending'
    ).values_list('team_id', flat=True)

    context = {
        'user_teams': user_teams,
        'public_teams': public_teams,
        'pending_requests': list(pending_requests),
        'search_query': search_query,
    }

    return render(request, 'telemetry/teams/team_list.html', context)


@login_required
def team_create(request):
    """
    Create a new team.
    """
    from ..forms import TeamForm

    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save(commit=False)
            team.owner = request.user
            team.save()

            # Add creator as team member with owner role
            from ..models import TeamMembership
            TeamMembership.objects.create(
                team=team,
                user=request.user,
                role='owner'
            )

            messages.success(request, f'Team "{team.name}" created successfully!')
            return redirect('telemetry:team_detail', pk=team.pk)
    else:
        form = TeamForm()

    context = {
        'form': form,
        'page_title': 'Create Team',
    }

    return render(request, 'telemetry/teams/team_form.html', context)


@login_required
def team_detail(request, pk):
    """
    View team details and members.
    """
    team = get_object_or_404(Team.objects.prefetch_related('members'), pk=pk)

    # Check if user is a member
    is_member = request.user in team.members.all()

    # Get user's role if they're a member
    user_role = None
    if is_member:
        try:
            membership = team.teammembership_set.get(user=request.user)
            user_role = membership.role
        except TeamMembership.DoesNotExist:
            pass

    # Get team members with roles
    memberships = team.teammembership_set.select_related('user').order_by('role', 'joined_at')

    # Check if user has a pending join request
    has_pending_request = team.has_pending_request(request.user)

    context = {
        'team': team,
        'is_member': is_member,
        'user_role': user_role,
        'memberships': memberships,
        'is_owner': user_role == 'owner',
        'has_pending_request': has_pending_request,
    }

    return render(request, 'telemetry/teams/team_detail.html', context)


@login_required
def team_edit(request, pk):
    """
    Edit team settings (owner only).
    """
    from ..forms import TeamForm

    team = get_object_or_404(Team, pk=pk)

    # Check if user is the owner
    if team.owner != request.user:
        messages.error(request, "Only the team owner can edit team settings.")
        return redirect('telemetry:team_detail', pk=pk)

    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, f'Team "{team.name}" updated successfully!')
            return redirect('telemetry:team_detail', pk=pk)
    else:
        form = TeamForm(instance=team)

    context = {
        'form': form,
        'team': team,
        'page_title': f'Edit {team.name}',
    }

    return render(request, 'telemetry/teams/team_form.html', context)


@login_required
@require_POST
def team_delete(request, pk):
    """
    Delete a team (owner only).
    """
    team = get_object_or_404(Team, pk=pk, owner=request.user)
    team_name = team.name
    team.delete()

    messages.success(request, f'Team "{team_name}" deleted successfully.')
    return redirect('telemetry:team_list')


# ===== Join Request Views =====

@login_required
def team_request_join(request, pk):
    """
    Submit a request to join a team.
    """
    team = get_object_or_404(Team, pk=pk)

    # Validate user can request to join
    if not team.can_user_request_join(request.user):
        if team.is_user_member(request.user):
            messages.info(request, "You are already a member of this team.")
        elif not team.allow_join_requests:
            messages.error(request, "This team is not accepting join requests.")
        elif team.has_pending_request(request.user):
            messages.info(request, "You already have a pending request for this team.")
        else:
            messages.error(request, "You cannot request to join this team.")
        return redirect('telemetry:team_detail', pk=pk)

    if request.method == 'POST':
        from ..forms import JoinRequestForm
        form = JoinRequestForm(request.POST)
        if form.is_valid():
            join_request = form.save(commit=False)
            join_request.team = team
            join_request.user = request.user
            join_request.save()

            messages.success(request, f'Your request to join "{team.name}" has been submitted!')
            return redirect('telemetry:team_detail', pk=pk)
    else:
        from ..forms import JoinRequestForm
        form = JoinRequestForm()

    context = {
        'form': form,
        'team': team,
    }

    return render(request, 'telemetry/teams/team_request_join.html', context)


@login_required
@require_POST
def team_cancel_request(request, pk):
    """
    Cancel a pending join request.
    """
    team = get_object_or_404(Team, pk=pk)

    try:
        join_request = JoinRequest.objects.get(team=team, user=request.user, status='pending')
        join_request.delete()
        messages.success(request, f'Your join request for "{team.name}" has been cancelled.')
    except JoinRequest.DoesNotExist:
        messages.error(request, "No pending join request found.")

    return redirect('telemetry:team_detail', pk=pk)


@login_required
def team_manage_requests(request, pk):
    """
    View and manage pending join requests (owner/admin only).
    """
    team = get_object_or_404(Team, pk=pk)

    # Check if user has admin privileges
    if not team.is_user_admin(request.user):
        messages.error(request, "Only team owners and admins can manage join requests.")
        return redirect('telemetry:team_detail', pk=pk)

    # Get all requests (pending first, then recent approved/rejected)
    pending_requests = team.join_requests.filter(status='pending').select_related('user')
    recent_requests = team.join_requests.filter(status__in=['approved', 'rejected']).select_related('user', 'reviewed_by').order_by('-reviewed_at')[:20]

    context = {
        'team': team,
        'pending_requests': pending_requests,
        'recent_requests': recent_requests,
    }

    return render(request, 'telemetry/teams/team_manage_requests.html', context)


@login_required
@require_POST
def team_approve_request(request, pk, request_id):
    """
    Approve a join request (owner/admin only).
    """
    team = get_object_or_404(Team, pk=pk)

    # Check if user has admin privileges
    if not team.is_user_admin(request.user):
        messages.error(request, "Only team owners and admins can approve join requests.")
        return redirect('telemetry:team_detail', pk=pk)

    join_request = get_object_or_404(JoinRequest, pk=request_id, team=team, status='pending')

    try:
        join_request.approve(approved_by=request.user)
        messages.success(request, f'{join_request.user.username} has been added to the team!')
    except Exception as e:
        messages.error(request, f'Error approving request: {str(e)}')

    return redirect('telemetry:team_manage_requests', pk=pk)


@login_required
@require_POST
def team_reject_request(request, pk, request_id):
    """
    Reject a join request (owner/admin only).
    """
    team = get_object_or_404(Team, pk=pk)

    # Check if user has admin privileges
    if not team.is_user_admin(request.user):
        messages.error(request, "Only team owners and admins can reject join requests.")
        return redirect('telemetry:team_detail', pk=pk)

    join_request = get_object_or_404(JoinRequest, pk=request_id, team=team, status='pending')

    try:
        join_request.reject(rejected_by=request.user)
        messages.info(request, f'Join request from {join_request.user.username} has been rejected.')
    except Exception as e:
        messages.error(request, f'Error rejecting request: {str(e)}')

    return redirect('telemetry:team_manage_requests', pk=pk)


# ===== Team Invitation Views =====

@login_required
def team_invite_user(request, pk):
    """
    Invite a user to join the team (owner/admin only).
    """
    team = get_object_or_404(Team, pk=pk)

    # Check if user has admin privileges
    if not team.is_user_admin(request.user):
        messages.error(request, "Only team owners and admins can invite users.")
        return redirect('telemetry:team_detail', pk=pk)

    if request.method == 'POST':
        from ..forms import TeamInviteForm
        form = TeamInviteForm(request.POST)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.team = team
            invitation.invited_by = request.user

            # Check if email belongs to existing user
            from django.contrib.auth.models import User
            try:
                invited_user = User.objects.get(email=invitation.email)
                invitation.invited_user = invited_user

                # Check if user is already a member
                if team.is_user_member(invited_user):
                    messages.error(request, f'{invited_user.username} is already a member of this team.')
                    return redirect('telemetry:team_detail', pk=pk)
            except User.DoesNotExist:
                pass  # Email doesn't match existing user

            invitation.save()
            messages.success(request, f'Invitation sent to {invitation.email}!')
            return redirect('telemetry:team_manage_invites', pk=pk)
    else:
        from ..forms import TeamInviteForm
        form = TeamInviteForm()

    context = {
        'form': form,
        'team': team,
    }

    return render(request, 'telemetry/teams/team_invite_user.html', context)


@login_required
def team_manage_invites(request, pk):
    """
    View and manage team invitations (owner/admin only).
    """
    team = get_object_or_404(Team, pk=pk)

    # Check if user has admin privileges
    if not team.is_user_admin(request.user):
        messages.error(request, "Only team owners and admins can manage invitations.")
        return redirect('telemetry:team_detail', pk=pk)

    # Get all invitations
    pending_invites = team.invitations.filter(status='pending').select_related('invited_by', 'invited_user')
    recent_invites = team.invitations.filter(status__in=['accepted', 'declined', 'expired']).select_related('invited_by', 'invited_user').order_by('-created_at')[:20]

    context = {
        'team': team,
        'pending_invites': pending_invites,
        'recent_invites': recent_invites,
    }

    return render(request, 'telemetry/teams/team_manage_invites.html', context)


@login_required
def team_accept_invite(request, token):
    """
    Accept a team invitation via token.
    """
    invitation = get_object_or_404(TeamInvitation, token=token)

    # Verify user email matches invitation
    if request.user.email != invitation.email:
        messages.error(request, "This invitation was sent to a different email address.")
        return redirect('telemetry:team_list')

    try:
        invitation.accept(request.user)
        messages.success(request, f'You have joined "{invitation.team.name}"!')
        return redirect('telemetry:team_detail', pk=invitation.team.pk)
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect('telemetry:team_list')


@login_required
@require_POST
def team_decline_invite(request, token):
    """
    Decline a team invitation.
    """
    invitation = get_object_or_404(TeamInvitation, token=token)

    # Verify user email matches invitation
    if request.user.email != invitation.email:
        messages.error(request, "This invitation was sent to a different email address.")
        return redirect('telemetry:team_list')

    if invitation.status == 'pending':
        invitation.decline()
        messages.info(request, f'You have declined the invitation to join "{invitation.team.name}".')
    else:
        messages.error(request, "This invitation has already been processed.")

    return redirect('telemetry:team_list')
