from django import forms
from .models import ResearchProject, ResearchDocument, ProgressMetric, Evaluator, Evaluation

class ResearchProjectForm(forms.ModelForm):
    class Meta:
        model = ResearchProject
        fields = ['title', 'description', 'status', 'start_date', 'end_date', 'lead_researcher', 'powerbi_url']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'powerbi_url': forms.URLInput(attrs={'placeholder': 'https://app.powerbi.com/...'}),
        }

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ResearchDocument
        fields = ['name', 'document', 'description']

class MetricForm(forms.ModelForm):
    class Meta:
        model = ProgressMetric
        fields = ['name', 'value', 'target', 'date_recorded', 'notes']
        widgets = {
            'date_recorded': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

class EvaluatorForm(forms.ModelForm):
    class Meta:
        model = Evaluator
        fields = ['name', 'email', 'phone', 'projects']
        widgets = {
            'projects': forms.SelectMultiple(attrs={
                'class': 'form-select select2',
                'data-placeholder': 'Select projects...'
            }),
            'phone': forms.TextInput(attrs={'placeholder': '+1234567890'}),
        }

class EvaluationForm(forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = ['project', 'phase', 'start_date', 'end_date', 'objectives', 
                 'patient_outcomes', 'compliance', 'safety', 'efficacy', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'objectives': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 2}),
            'patient_outcomes': forms.NumberInput(attrs={
                'min': 0,
                'max': 100,
                'step': 1
            }),
            'compliance': forms.NumberInput(attrs={
                'min': 0,
                'max': 100,
                'step': 1
            }),
            'safety': forms.NumberInput(attrs={
                'min': 0,
                'max': 100,
                'step': 1
            }),
            'efficacy': forms.NumberInput(attrs={
                'min': 0,
                'max': 100,
                'step': 1
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if end_date and start_date and end_date < start_date:
            raise forms.ValidationError("End date cannot be before start date")

        # Validate percentage fields
        percentage_fields = ['patient_outcomes', 'compliance', 'safety', 'efficacy']
        for field in percentage_fields:
            value = cleaned_data.get(field)
            if value is not None and (value < 0 or value > 100):
                raise forms.ValidationError(f"{field.replace('_', ' ').title()} must be between 0 and 100")

        return cleaned_data
