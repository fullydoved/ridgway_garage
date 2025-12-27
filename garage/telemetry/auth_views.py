"""
Custom authentication views for Ridgway Garage.
Email-based authentication with display name for user profiles.
Includes password reset functionality via email.
"""

import uuid
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.urls import reverse_lazy
from django import forms


class LoginForm(forms.Form):
    """Login form with email and password."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Email',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Password',
            'autocomplete': 'current-password'
        })
    )


class RegisterForm(forms.Form):
    """Registration form with display name, email, and password confirmation."""
    display_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Display Name',
            'autocomplete': 'name'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Email',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Password (min 8 characters)',
            'autocomplete': 'new-password'
        })
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Confirm Password',
            'autocomplete': 'new-password'
        })
    )

    def clean_email(self):
        """Validate email is unique."""
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Email already registered.')
        return email

    def clean(self):
        """Validate passwords match."""
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Passwords do not match.')

        return cleaned_data


def generate_username_from_email(email):
    """Generate unique username from email address."""
    base = email.split('@')[0][:30]  # Email prefix, max 30 chars
    # Clean up base - remove special characters
    base = ''.join(c for c in base if c.isalnum() or c in '_-')
    if not base:
        base = 'user'
    username = base
    # If username exists, append random suffix
    while User.objects.filter(username=username).exists():
        username = f"{base}_{uuid.uuid4().hex[:6]}"
    return username


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Login view with email and password.
    GET: Show login form
    POST: Authenticate and log in user
    """
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('telemetry:home')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # Find user by email
            try:
                user_obj = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, 'Invalid email or password.')
                return render(request, 'login.html', {'form': form})

            # Authenticate with username (Django requirement)
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None:
                auth_login(request, user)
                # Get display name from driver profile
                display_name = user.username
                if hasattr(user, 'driver_profile') and user.driver_profile.display_name:
                    display_name = user.driver_profile.display_name
                messages.success(request, f'Welcome back, {display_name}!')

                # Redirect to next URL or home
                next_url = request.GET.get('next', 'telemetry:home')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form})


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Registration view with display name, email, and password.
    GET: Show registration form
    POST: Create new user and log them in
    """
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('telemetry:home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            # Generate unique username from email
            username = generate_username_from_email(form.cleaned_data['email'])

            # Create user
            user = User.objects.create_user(
                username=username,
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )

            # Update driver profile with display name
            # (Driver profile is auto-created via signal)
            if hasattr(user, 'driver_profile'):
                user.driver_profile.display_name = form.cleaned_data['display_name']
                user.driver_profile.save(update_fields=['display_name'])

            # Log in the new user
            auth_login(request, user)
            messages.success(request, f'Account created successfully! Welcome, {form.cleaned_data["display_name"]}!')

            return redirect('telemetry:home')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """
    Logout view.
    Logs out user and redirects to home page.
    """
    auth_logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('telemetry:home')


# =============================================================================
# Password Reset Views
# =============================================================================

class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form with cyberpunk styling."""
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Email Address',
            'autocomplete': 'email'
        })
    )


class CustomSetPasswordForm(SetPasswordForm):
    """Custom set password form with cyberpunk styling."""
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'input-neon',
            'placeholder': 'New Password',
            'autocomplete': 'new-password'
        })
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Confirm New Password',
            'autocomplete': 'new-password'
        })
    )


class CustomPasswordResetView(PasswordResetView):
    """Password reset request view - enter email to receive reset link."""
    template_name = 'account/password_reset.html'
    email_template_name = 'account/password_reset_email.html'
    subject_template_name = 'account/password_reset_subject.txt'
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        """Add success message when email is sent."""
        messages.success(
            self.request,
            'If an account exists with that email, you will receive a password reset link shortly.'
        )
        return super().form_valid(form)


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Password reset done view - shows confirmation that email was sent."""
    template_name = 'account/password_reset_done.html'


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Password reset confirm view - enter new password."""
    template_name = 'account/password_reset_confirm.html'
    form_class = CustomSetPasswordForm
    success_url = reverse_lazy('password_reset_complete')

    def form_valid(self, form):
        """Add success message when password is changed."""
        messages.success(self.request, 'Your password has been reset successfully!')
        return super().form_valid(form)


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Password reset complete view - shows success message."""
    template_name = 'account/password_reset_complete.html'
