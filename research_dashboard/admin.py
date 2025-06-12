from django.contrib import admin
from .models import ResearchProject, EvaluationPhase, ProjectMilestone, ProgressMetric, ResearchDocument, Evaluator, Evaluation

@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'start_date', 'end_date', 'lead_researcher', 'powerbi_url')
    list_filter = ('status', 'lead_researcher')
    search_fields = ('title', 'description', 'powerbi_url')

@admin.register(EvaluationPhase)
class EvaluationPhaseAdmin(admin.ModelAdmin):
    list_display = ('project', 'phase_type', 'start_date', 'end_date', 'completed')
    list_filter = ('phase_type', 'completed')
    search_fields = ('project__title', 'notes')

@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = ('project', 'name', 'due_date', 'status')
    list_filter = ('status',)
    search_fields = ('project__title', 'name', 'description')

@admin.register(ProgressMetric)
class ProgressMetricAdmin(admin.ModelAdmin):
    list_display = ('project', 'name', 'value', 'target', 'date_recorded')
    search_fields = ('project__title', 'name', 'notes')

@admin.register(ResearchDocument)
class ResearchDocumentAdmin(admin.ModelAdmin):
    list_display = ('project', 'name', 'uploaded_at')
    search_fields = ('project__title', 'name', 'description')

@admin.register(Evaluator)
class EvaluatorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
    search_fields = ('name', 'email', 'phone')

@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ('project', 'phase', 'start_date', 'end_date', 'patient_outcomes', 'compliance', 'safety')
    list_filter = ('phase', 'project')
    search_fields = ('project__title', 'objectives', 'notes')
    date_hierarchy = 'start_date'
