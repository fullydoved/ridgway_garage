"""
Forms for the Ridgway Garage telemetry app.
"""

from django import forms
from django.core.validators import FileExtensionValidator

from .models import Session, Track, Car, Team, Analysis, Lap


class SessionUploadForm(forms.ModelForm):
    """
    Form for uploading IBT telemetry files.
    Track, car, and session type are auto-detected from the file.
    """

    class Meta:
        model = Session
        fields = ['ibt_file', 'team']
        widgets = {
            'ibt_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.ibt,.IBT',
            }),
            'team': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Team is optional
        self.fields['team'].required = False

        # Filter teams to only those the user is a member of
        if self.user:
            self.fields['team'].queryset = Team.objects.filter(members=self.user)

        # Add help text
        self.fields['ibt_file'].help_text = 'Upload an iRacing telemetry file (.ibt) - track, car, and session type will be auto-detected'
        self.fields['team'].help_text = 'Optional: Share this session with a team'

    def clean_ibt_file(self):
        """
        Validate the uploaded file.
        """
        file = self.cleaned_data.get('ibt_file')

        if file:
            # Check file extension
            if not file.name.lower().endswith('.ibt'):
                raise forms.ValidationError('Only .ibt files are allowed.')

            # Check file size (max 500MB)
            max_size = 500 * 1024 * 1024  # 500MB in bytes
            if file.size > max_size:
                raise forms.ValidationError(f'File size must be under 500MB. Your file is {file.size / (1024*1024):.1f}MB.')

        return file


class AnalysisForm(forms.ModelForm):
    """
    Form for creating/editing lap comparison analyses.
    """

    class Meta:
        model = Analysis
        fields = ['name', 'description', 'team', 'track', 'car', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Baseline vs New Setup'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional notes about this analysis...'
            }),
            'team': forms.Select(attrs={'class': 'form-select'}),
            'track': forms.Select(attrs={'class': 'form-select'}),
            'car': forms.Select(attrs={'class': 'form-select'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # All fields except name are optional
        self.fields['description'].required = False
        self.fields['team'].required = False
        self.fields['track'].required = False
        self.fields['car'].required = False

        # Filter teams to only those the user is a member of
        if self.user:
            self.fields['team'].queryset = Team.objects.filter(members=self.user)

        # Add help text
        self.fields['name'].help_text = 'Give this analysis a descriptive name'
        self.fields['description'].help_text = 'Optional notes about what you\'re comparing'
        self.fields['team'].help_text = 'Optional: Share with a team'
        self.fields['track'].help_text = 'Optional: Filter by track (for convenience)'
        self.fields['car'].help_text = 'Optional: Filter by car (for convenience)'
        self.fields['is_public'].help_text = 'Allow public viewing of this analysis'


class TeamForm(forms.ModelForm):
    """
    Form for creating/editing teams.
    """

    class Meta:
        model = Team
        fields = ['name', 'description', 'is_public', 'allow_join_requests', 'discord_webhook_url']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Racing Team Name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Team description...'
            }),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_join_requests': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'discord_webhook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://discord.com/api/webhooks/...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Optional fields
        self.fields['description'].required = False
        self.fields['discord_webhook_url'].required = False

        # Add help text
        self.fields['name'].help_text = 'Team name (must be unique)'
        self.fields['description'].help_text = 'Optional team description'
        self.fields['is_public'].help_text = 'Allow public viewing of team telemetry'
        self.fields['allow_join_requests'].help_text = 'Allow users to request to join'
        self.fields['discord_webhook_url'].help_text = 'Discord webhook URL for sharing laps (optional)'

    def clean_discord_webhook_url(self):
        """Validate Discord webhook URL format"""
        url = self.cleaned_data.get('discord_webhook_url')
        if url and not url.startswith('https://discord.com/api/webhooks/'):
            raise forms.ValidationError('Invalid Discord webhook URL. Must start with https://discord.com/api/webhooks/')
        return url
