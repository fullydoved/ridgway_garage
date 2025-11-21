"""
Custom authentication views for Ridgway Garage.
Replaces django-allauth with simple username/email/password auth.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django import forms


class LoginForm(forms.Form):
    """Simple login form with username and password."""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Username',
            'autocomplete': 'username'
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
    """Registration form with username, email, and password confirmation."""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'input-neon',
            'placeholder': 'Username',
            'autocomplete': 'username'
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

    def clean_username(self):
        """Validate username is unique."""
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Username already taken.')
        return username

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


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Login view with username and password.
    GET: Show login form
    POST: Authenticate and log in user
    """
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('telemetry:home')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')

                # Redirect to next URL or home
                next_url = request.GET.get('next', 'telemetry:home')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form})


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Registration view with username, email, and password.
    GET: Show registration form
    POST: Create new user and log them in
    """
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('telemetry:home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            # Create user
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )

            # Log in the new user
            auth_login(request, user)
            messages.success(request, f'Account created successfully! Welcome, {user.username}!')

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
