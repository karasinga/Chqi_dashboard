from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class ResearchProject(models.Model):
    PROJECT_STATUS = [
        ('planned', 'Planned'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PROJECT_STATUS, default='planned')
    lead_researcher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    powerbi_url = models.URLField(max_length=500, blank=True, null=True, verbose_name="PowerBI Dashboard URL")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class Evaluation(models.Model):
    PHASE_CHOICES = [
        ('planning', 'Planning'),
        ('data_collection', 'Data Collection'),
        ('analysis', 'Analysis'),
        ('reporting', 'Reporting'),
        ('completed', 'Completed'),
    ]

    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='evaluations')
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='planning')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    objectives = models.TextField()
    patient_outcomes = models.PositiveIntegerField(default=0, help_text="Percentage of positive patient outcomes")
    compliance = models.PositiveIntegerField(default=0, help_text="Percentage of protocol compliance")
    safety = models.PositiveIntegerField(default=0, help_text="Percentage of safety standards met")
    efficacy = models.PositiveIntegerField(null=True, blank=True, help_text="Percentage of treatment efficacy")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.title} - {self.get_phase_display()} Evaluation"

    class Meta:
        ordering = ['-created_at']

class EvaluationPhase(models.Model):
    PHASE_TYPES = [
        ('baseline', 'Baseline Evaluation'),
        ('midline', 'Midline Evaluation'), 
        ('endline', 'Endline Evaluation'),
        ('inception', 'Inception'),
        ('design', 'Design'),
        ('data_collection', 'Data Collection'),
        ('analysis', 'Analysis'),
        ('reporting', 'Reporting'),
        ('dissemination', 'Dissemination'),
    ]

    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='phases')
    phase_type = models.CharField(max_length=20, choices=PHASE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    def __str__(self):
        phase = self.get_phase_type_display()
        dates = f"({self.start_date} to {self.end_date})"
        return f"{self.project.title} - {phase} {dates}"

class ProjectMilestone(models.Model):
    MILESTONE_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('overdue', 'Overdue'),
    ]

    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='milestones')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=MILESTONE_STATUS, default='pending')
    completed_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.project.title} - {self.name}"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        today = timezone.now().date()
        
        # Handle status based on completion
        if self.status == 'completed':
            if not self.completed_date:
                self.completed_date = today
        else:
            if self.completed_date:
                self.completed_date = None
        
        # Handle overdue status - only if due_date exists and is a date object
        if self.status != 'completed' and self.due_date and hasattr(self.due_date, 'date'):
            if self.due_date < today:
                self.status = 'overdue'
            elif self.status == 'overdue' and self.due_date >= today:
                self.status = 'pending'
            
        super().save(*args, **kwargs)

class ProgressMetric(models.Model):
    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='metrics')
    name = models.CharField(max_length=100)
    value = models.FloatField()
    target = models.FloatField(null=True, blank=True)
    date_recorded = models.DateField()
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.project.title} - {self.name}: {self.value}"

class ResearchDocument(models.Model):
    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='documents')
    name = models.CharField(max_length=200)
    document = models.FileField(upload_to='research_documents/')
    uploaded_at = models.DateTimeField(default=timezone.now)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.project.title} - {self.name}"

class Evaluator(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    projects = models.ManyToManyField(ResearchProject, related_name='evaluators', blank=True)
    
    def __str__(self):
        return self.name
