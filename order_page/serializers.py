# serializers.py
from rest_framework import serializers
from .models import TermsOfConditions

class TermsOfConditionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsOfConditions
        fields = ['id', 'title', 'body', 'created_at', 'updated_at']
