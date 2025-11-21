"""
Team management views for Ridgway Garage.

Handles team CRUD operations, membership management, and team detail views.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST

from ..models import Team


@login_required
def team_list(request):
    """
    List teams the user belongs to and public teams.
    """
    # Teams the user is a member of
    user_teams = Team.objects.filter(members=request.user).prefetch_related('members')

    # Public teams
    public_teams = Team.objects.filter(is_public=True).exclude(members=request.user)

    context = {
        'user_teams': user_teams,
        'public_teams': public_teams,
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
        except:
            pass

    # Get team members with roles
    memberships = team.teammembership_set.select_related('user').order_by('role', 'joined_at')

    context = {
        'team': team,
        'is_member': is_member,
        'user_role': user_role,
        'memberships': memberships,
        'is_owner': user_role == 'owner',
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
