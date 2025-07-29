from django import forms
from .models import Campaign


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ['title', 'prompt', 'schedule', 'start_date', 'end_date', 'is_active']