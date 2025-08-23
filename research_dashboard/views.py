from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView, ListView, UpdateView, DetailView

from research_dashboard.data_utils import create_average_df, load_and_clean_data
from .models import ResearchProject, Evaluator, Evaluation, EvaluationPhase, ProjectMilestone, ResearchDocument
from .forms import MilestoneStatusForm, ProjectMilestoneForm, MetricForm
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .forms import DocumentUploadForm
import json
from datetime import timedelta
import mimetypes
from django.http import HttpResponse, JsonResponse
import os
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import plotly.graph_objects as go
from plotly.offline import plot
import plotly.express as px
import plotly.io as pio
from django.conf import settings
from django.core.cache import cache
import pandas as pd
import numpy as np
from datetime import datetime
import geopandas as gpd
from django.conf import settings
import os
import json
from .data_utils import load_and_clean_data, create_average_df

def get_baseline_data():
    """Centralized function to load and cache baseline data consistently across views"""
    df = cache.get('baseline_df')
    if df is None:
        csv_path = os.path.join(settings.BASE_DIR, 'redcap_baseline_complete.csv')
        df = load_and_clean_data(csv_path)
        if df is None:
            raise ValueError("Failed to load baseline data file")
        cache.set('baseline_df', df, 3600)
    return df

def get_baseline_data_with_averages():
    """Get both baseline data and averaged data with consistent caching"""
    df = get_baseline_data()
    df_with_averages = cache.get('baseline_df_with_averages')
    if df_with_averages is None:
        df_with_averages = create_average_df(df)
        cache.set('baseline_df_with_averages', df_with_averages, 3600)
    return df, df_with_averages

class DashboardView(View):
    """Improved view for research project dashboard"""
    template_name = 'research_dashboard/dashboard.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request):
        """Display dashboard with project statistics"""
        status_filter = request.GET.get('status')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        project_name = request.GET.get('project_name')
        
        base_projects = ResearchProject.objects.all()
        projects = base_projects
        
        # Apply filters if specified
        if status_filter:
            projects = projects.filter(status=status_filter)
        if date_from:
            projects = projects.filter(start_date__gte=date_from)
        if date_to:
            projects = projects.filter(end_date__lte=date_to)
        if project_name:
            projects = projects.filter(title__icontains=project_name)
            
        # Add annotations after filtering
        projects = projects.annotate(
            active_phases=Count('phases', filter=Q(phases__completed=False)),
            completed_milestones=Count('milestones', filter=Q(milestones__status='completed')),
            total_milestones=Count('milestones')
        ).prefetch_related('phases', 'milestones').order_by('-created_at')

        # Calculate completion percentage for each project
        today = timezone.now().date()
        for project in projects:
            if project.end_date and project.start_date:
                total_days = (project.end_date - project.start_date).days
                elapsed_days = (today - project.start_date).days
                
                if total_days <= 0:
                    project.completion_percent = 100 if elapsed_days >= 0 else 0
                else:
                    if elapsed_days <= 0:
                        project.completion_percent = 0
                    elif elapsed_days >= total_days:
                        project.completion_percent = 100
                    else:
                        project.completion_percent = min(100, max(0, int((elapsed_days / total_days) * 100)))
            else:
                if project.total_milestones > 0:
                    project.completion_percent = int((project.completed_milestones / project.total_milestones) * 100)
                else:
                    project.completion_percent = 0

        # Calculate status counts for all projects
        status_counts = {
            status: base_projects.filter(status=status).count()
            for status, _ in ResearchProject.PROJECT_STATUS
        }

        # Pagination
        paginator = Paginator(projects, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Get distinct project names for the dropdown
        project_names = base_projects.values_list('title', flat=True).distinct().order_by('title')
        
        context = {
            'page_obj': page_obj,
            'status_counts': status_counts,
            'status_filter': status_filter or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
            'status_options': ResearchProject.PROJECT_STATUS,
            'total_projects_count': base_projects.count(),
            'project_names': project_names,
            'project_name_filter': project_name or ''
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Handle project create/update/delete operations"""
        if request.POST.get('_method') == 'DELETE':
            return self._handle_delete(request)
            
        project_id = request.POST.get('project_id')
        try:
            if project_id:
                project = ResearchProject.objects.get(pk=project_id)
                project.title = request.POST.get('title')
                project.description = request.POST.get('description')
                project.status = request.POST.get('status')
                project.start_date = request.POST.get('start_date')
                project.end_date = request.POST.get('end_date') or None
                project.save()
                messages.success(request, 'Project updated successfully!')
            else:
                ResearchProject.objects.create(
                    title=request.POST.get('title'),
                    description=request.POST.get('description'),
                    status=request.POST.get('status'),
                    start_date=request.POST.get('start_date'),
                    end_date=request.POST.get('end_date') or None,
                    lead_researcher=request.user
                )
                messages.success(request, 'Project created successfully!')
        except ResearchProject.DoesNotExist:
            messages.error(request, 'Project not found or access denied')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('dashboard')

    def _handle_delete(self, request):
        """Handle project deletion"""
        project_id = request.POST.get('project_id')
        try:
            project = ResearchProject.objects.get(pk=project_id)
            project.delete()
            messages.success(request, 'Project deleted successfully!')
        except ResearchProject.DoesNotExist:
            messages.error(request, 'Project not found or access denied')
        except Exception as e:
            messages.error(request, f'Error deleting project: {str(e)}')
        return redirect('dashboard')

class AboutView(TemplateView):
    template_name = 'research_dashboard/about.html'

class LandingPageView(TemplateView):
    template_name = 'research_dashboard/landing_page.html'

class EvaluatorListView(ListView):
    model = Evaluator
    template_name = 'research_dashboard/evaluators.html'
    context_object_name = 'evaluators'

class EvaluatorUpdateView(UpdateView):
    model = Evaluator
    template_name = 'research_dashboard/evaluator_form.html'
    fields = ['name', 'email', 'expertise']
    success_url = '/evaluators/'

class EvaluatorDeleteView(UpdateView):
    model = Evaluator
    template_name = 'research_dashboard/evaluator_confirm_delete.html'
    success_url = '/evaluators/'

class EvaluationView(ListView):
    model = Evaluation
    template_name = 'research_dashboard/evaluations.html'
    context_object_name = 'evaluations'

class EvaluationDetailView(DetailView):
    model = Evaluation
    template_name = 'research_dashboard/evaluation_detail.html'
    context_object_name = 'evaluation'

class EvaluationUpdateView(UpdateView):
    model = Evaluation
    template_name = 'research_dashboard/evaluation_form.html'
    fields = ['project', 'evaluator', 'status', 'comments']
    success_url = '/evaluations/'

class ProjectOverviewView(View):
    """View for project overview section"""
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        """Handle GET requests for project overview"""
        project_id = kwargs.get('project_id')
        document_id = kwargs.get('document_id')
        project = get_object_or_404(ResearchProject, pk=project_id)

        if document_id:
            return self.view_document(request, document_id)

        context = {
            'project': project,
            'current_view': 'overview',
            'documents': project.documents.all(),
            'document_form': DocumentUploadForm(),
        }

        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/overview_content.html', context)
        return render(request, self.template_name, context)

    def post(self, request, project_id):
        """Handle document operations"""
        project = get_object_or_404(ResearchProject, pk=project_id)
        
        # Handle document deletion
        if request.POST.get('delete_document') == 'true':
            return self._handle_document_delete(request, project)
            
        # Handle document upload
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.project = project
            document.save()
            if request.headers.get('HX-Request'):
                context = {
                    'project': project,
                    'documents': project.documents.all(),
                    'document_form': DocumentUploadForm()
                }
                return render(request, 'research_dashboard/partials/overview_content.html', context)
            return redirect('project_overview', project_id=project.id)
        else:
            context = {
                'project': project,
                'current_view': 'overview',
                'documents': project.documents.all(),
                'document_form': form,
            }
            if request.headers.get('HX-Request'):
                return render(request, 'research_dashboard/partials/overview_content.html', context)
            return render(request, self.template_name, context)

    def _handle_document_delete(self, request, project):
        """Handle document deletion"""
        try:
            document = get_object_or_404(ResearchDocument, 
                pk=request.POST.get('document_id'),
                project=project
            )
            document.delete()
            
            if request.headers.get('HX-Request'):
                # Return just the documents table for HTMX requests
                return render(request, 'research_dashboard/partials/documents_table.html', {
                    'documents': project.documents.all()
                })
            return redirect('project_overview', project_id=project.id)
        except Exception as e:
            messages.error(request, f'Error deleting document: {str(e)}')
            if request.headers.get('HX-Request'):
                return HttpResponse(f'<div class="alert alert-danger">Error deleting document: {str(e)}</div>', status=400)
            return redirect('project_overview', project_id=project.id)

    def view_document(self, request, document_id):
        """View a document in the browser"""
        document = get_object_or_404(ResearchDocument, pk=document_id)
        file_path = document.document.path
        content_type, _ = mimetypes.guess_type(file_path)
        
        if content_type is None:
            content_type = 'application/octet-stream'
            
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type=content_type)
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
            return response

    def download_document(self, request, document_id):
        """Download a document"""
        document = get_object_or_404(ResearchDocument, pk=document_id)
        file_path = document.document.path
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type='application/force-download')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
            return response

@login_required
@require_http_methods(["PATCH"])
def update_phase_status(request, phase_id):
    phase = get_object_or_404(EvaluationPhase, id=phase_id)
    data = json.loads(request.body)
    phase.completed = data.get('status') == 'completed'
    phase.save()
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["PATCH"])
def update_milestone_status(request, milestone_id):
    milestone = get_object_or_404(ProjectMilestone, id=milestone_id)
    form = MilestoneStatusForm(request.POST)
    
    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'errors': form.errors.as_json()
        }, status=400)

    status = form.cleaned_data.get('status')
    completed_date = form.cleaned_data.get('completed_date')

    if status:
        milestone.status = status
    if completed_date is not None:
        milestone.completed_date = completed_date
    
    milestone.save()
    return JsonResponse({
        'success': True,
        'status': milestone.status,
        'status_display': milestone.get_status_display(),
        'completed_date': milestone.completed_date.strftime('%Y-%m-%d') if milestone.completed_date else None
    })

@login_required
@require_http_methods(["POST"])
def update_timeline_order(request):
    data = json.loads(request.body)
    items = data.get('items', [])
    
    for item in items:
        if item['type'] == 'phase':
            obj = get_object_or_404(EvaluationPhase, id=item['id'])
        else:
            obj = get_object_or_404(ProjectMilestone, id=item['id'])
            
        obj.order = item['order']
        obj.save()
    
    return JsonResponse({'success': True})


# In your views.py

class ProjectTimelineView(View):
    """View for project timeline section"""
    template_name = 'research_dashboard/project_detail.html'
    partial_template = 'research_dashboard/partials/timeline_content.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def _is_htmx_request(self, request):
        """Check if request is HTMX or AJAX"""
        return request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def _get_base_context(self, project):
        """Get common context for timeline views"""
        tasks = self._prepare_tasks_data(project)
        return {
            'project': project,
            'current_view': 'timeline',
            'phases': project.phases.all().order_by('start_date'),
            'milestones': project.milestones.all().order_by('due_date'),
            'gantt_chart': self._generate_gantt_chart(tasks) if tasks else '<div class="alert alert-info">No timeline data to display.</div>',
            'form': ProjectMilestoneForm()
        }

    def get(self, request, *args, **kwargs):
        """Handle GET requests for project timeline"""
        project = get_object_or_404(ResearchProject, pk=kwargs.get('project_id'))
        context = self._get_base_context(project)
        
        if self._is_htmx_request(request):
            return render(request, self.partial_template, context)
        # Assuming project_timeline.html is the correct full page template
        return render(request, self.template_name, context)
    
    # In your views.py

# ... keep all other class methods like get, _is_htmx_request, etc. ...

    # =========================================================================
    # REVISED POST AND PHASE HANDLER METHODS
    # =========================================================================

    def post(self, request, project_id):
        """Handle all timeline POST operations."""
        project = get_object_or_404(ResearchProject, pk=project_id)

        # Determine if this is a phase operation (add, update, or delete)
        # We check for a field common to add/edit forms, or the delete signal.
        if 'phase_type' in request.POST or 'delete_phase' in request.POST:
            return self._handle_phase_operation(request, project)

        # Determine if this is a milestone operation
        if 'add_milestone' in request.POST or 'update_milestone' in request.POST:
            return self._handle_milestone_operation(request, project, ProjectMilestoneForm)
        if request.POST.get('_method') == 'DELETE' and 'milestone_id' in request.POST:
             return self._delete_milestone(request, project)
            
        return self._error_response('Invalid request. The action was not recognized.')

    def _handle_phase_operation(self, request, project):
        """Intelligently routes phase operations based on POST data."""
        # Route to delete if the _method is DELETE
        if request.POST.get('_method') == 'DELETE':
            return self._delete_phase(request, project)
            
        # Route to update if a phase_id is present and has a value
        if 'phase_id' in request.POST and request.POST.get('phase_id'):
            return self._update_phase(request, project)
        
        # Otherwise, assume it's a create operation
        return self._create_phase(project, request.POST)

    def _create_phase(self, project, post_data):
        """Create a new phase"""
        try:
            EvaluationPhase.objects.create(
                project=project,
                phase_type=post_data.get('phase_type'),
                start_date=post_data.get('start_date'),
                end_date=post_data.get('end_date'),
                notes=post_data.get('notes', ''),
                # 'completed' checkbox is not in the add form, so it defaults to False
            )
            return self._success_response('Phase added successfully!', project)
        except Exception as e:
            return self._error_response(f'Error creating phase: {str(e)}')

    def _update_phase(self, request, project):
        """Update an existing phase"""
        try:
            phase = get_object_or_404(EvaluationPhase, pk=request.POST.get('phase_id'), project=project)
            phase.phase_type = request.POST.get('phase_type')
            phase.start_date = request.POST.get('start_date')
            phase.end_date = request.POST.get('end_date')
            # An HTML checkbox's value is 'on' if checked, and it's absent from POST data if not.
            phase.completed = request.POST.get('completed') == 'on'
            phase.notes = request.POST.get('notes', '')
            phase.save()
            return self._success_response('Phase updated successfully!', project)
        except Exception as e:
            return self._error_response(f'Error updating phase: {str(e)}')

    def _delete_phase(self, request, project):
        """Delete a phase"""
        try:
            phase = get_object_or_404(EvaluationPhase, pk=request.POST.get('phase_id'), project=project)
            phase.delete()
            return self._success_response('Phase deleted successfully!', project)
        except Exception as e:
            return self._error_response(f'Error deleting phase: {str(e)}')

    # --- KEEP ALL YOUR OTHER METHODS ---
    # (e.g., _handle_milestone_operation, _success_response, _generate_gantt_chart, etc.)
    # They are correct and do not need to be changed.
    # ...


     
    
    
    
    
    
    
    
    # --- Milestone and other helper methods remain the same ---
    # ... (keep all your other methods like _handle_milestone_operation, _create_milestone, _success_response, etc.)
    # Make sure they are correctly indented within the class.
    def _handle_milestone_operation(self, request, project, form_class):
        """Handle milestone creation/update"""
        if request.POST.get('_method') == 'DELETE':
            return self._delete_milestone(request, project)
            
        form = form_class(request.POST)
        if not form.is_valid():
            return self._form_error_response(form)
            
        try:
            if request.POST.get('milestone_id'):
                return self._update_milestone(request, project, form)
            else:
                return self._create_milestone(project, form)
        except Exception as e:
            return self._error_response(f'Error modifying milestone: {str(e)}')

    def _create_milestone(self, project, form):
        """Create a new milestone"""
        milestone = form.save(commit=False)
        milestone.project = project
        milestone.save()
        return self._success_response('Milestone added successfully!', project)

    def _update_milestone(self, request, project, form):
        """Update an existing milestone"""
        milestone = get_object_or_404(ProjectMilestone,
            pk=request.POST.get('milestone_id'),
            project=project
        )
        milestone.name = form.cleaned_data['name']
        milestone.due_date = form.cleaned_data['due_date']
        milestone.description = form.cleaned_data['description']
        milestone.status = request.POST.get('status', milestone.status)
        milestone.save()
        return self._success_response('Milestone updated successfully!', project)

    def _delete_milestone(self, request, project):
        """Delete a milestone"""
        milestone = get_object_or_404(ProjectMilestone,
            pk=request.POST.get('milestone_id'),
            project=project
        )
        milestone.delete()
        return self._success_response('Milestone deleted successfully!', project)

    def _success_response(self, message, project):
        """Generate success response"""
        messages.success(self.request, message)
        if self._is_htmx_request(self.request):
            context = self._get_base_context(project)
            response = render(self.request, self.partial_template, context)
            response['HX-Trigger'] = 'timelineUpdated'
            return response
        return redirect('project_timeline', project_id=project.id)

    def _error_response(self, error_message):
        """Generate error response"""
        messages.error(self.request, error_message)
        project_id = self.kwargs.get('project_id')
        if self._is_htmx_request(self.request):
            return HttpResponse(f'<div class="alert alert-danger">{error_message}</div>', status=400)
        return redirect('project_timeline', project_id=project_id)

    def _form_error_response(self, form):
        """Handle form validation errors"""
        error_message = 'Invalid form data. Please check the inputs.'
        if self._is_htmx_request(self.request):
            # This could be enhanced to return specific field errors
            return HttpResponse(f'<div class="alert alert-danger">{error_message}</div>', status=400)
        messages.error(self.request, error_message)
        return redirect('project_timeline', project_id=self.kwargs.get('project_id'))

    # ... Paste the rest of your view's methods here (_prepare_tasks_data, _generate_gantt_chart, etc.)
    # They should work as-is with these changes.
    def _prepare_tasks_data(self, project):
        """Prepare tasks data for Gantt chart visualization"""
        tasks = []
        for phase in project.phases.all():
            if phase.start_date and phase.end_date:
                tasks.append({
                    'id': f'phase-{phase.id}',
                    'name': phase.get_phase_type_display(),
                    'start': phase.start_date.strftime('%Y-%m-%d'),
                    'end': phase.end_date.strftime('%Y-%m-%d'),
                    'progress': 100 if phase.completed else 0,
                    'dependencies': ''
                })
        for milestone in project.milestones.all():
            if milestone.due_date:
                tasks.append({
                    'id': f'milestone-{milestone.id}',
                    'name': f"★ {milestone.name}",
                    'start': milestone.due_date.strftime('%Y-%m-%d'),
                    'end': (milestone.due_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                    'progress': 100 if milestone.status == 'completed' else 0,
                    'dependencies': '',
                    'custom_class': 'milestone',
                    'milestone': True
                })
        return tasks

    def _generate_gantt_chart(self, tasks):
        """Generate Gantt chart HTML from tasks data"""
        try:
            import plotly.graph_objects as go
            from plotly.offline import plot
            import pandas as pd
            from datetime import datetime, timedelta
            import plotly
            import plotly.graph_objs as go
            from plotly.offline import plot
            import pandas as pd
            from datetime import datetime
            from plotly.subplots import make_subplots

            # Create DataFrame and process data
            if not tasks:
                return ""
            df = pd.DataFrame(tasks)
            df['start'] = pd.to_datetime(df['start'])
            df['end'] = pd.to_datetime(df['end'])
            df['duration'] = (df['end'] - df['start']).dt.days
            df['text'] = df.apply(lambda row: f"{row['name']} ({row['duration']} days)", axis=1)
            df['is_milestone'] = df['id'].str.startswith('milestone-')
            df = df.sort_values("start")
            today = datetime.now()

            # Create figure
            fig = go.Figure()

            # Add phases as bars
            for _, row in df[~df['is_milestone']].iterrows():
                color = self._get_task_color(row, today)
                fig.add_trace(self._create_phase_trace(row, color))
                fig.add_annotation(self._create_phase_annotation(row))

            # Add milestones as markers
            for _, row in df[df['is_milestone']].iterrows():
                color = self._get_task_color(row, today)
                fig.add_trace(self._create_milestone_trace(row, color))

            # Configure layout
            self._configure_layout(fig, df, today)
            
            return plot(fig, output_type='div', include_plotlyjs='cdn', config={
                'displayModeBar': False,
                'responsive': True
            })
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return f'<div class="alert alert-danger">Error generating Gantt chart: {str(e)}<br><pre>{error_details}</pre></div>'

    def _get_task_color(self, row, today):
        """Determine color based on task status and dates"""
        if row['progress'] == 100:
            return '#22c55e'  # Green for completed
        elif row['end'].to_pydatetime() < today and row['progress'] < 100:
            return '#ef4444'  # Red for overdue
        return '#4361EE'  # Blue for in progress

    def _create_phase_trace(self, row, color):
        """Create trace for a phase"""
        return go.Scatter(
            x=[row['start'], row['end']],
            y=[row['name'], row['name']],
            mode='lines',
            line=dict(color=color, width=20),
            name=row['name'],
            text=row['text'],
            hoverinfo='text',
            hovertext=self._get_hover_text(row),
            showlegend=False
        )

    def _create_phase_annotation(self, row):
        """Create annotation for a phase"""
        mid_timestamp = row['start'] + (row['end'] - row['start'])/2
        return dict(
            x=mid_timestamp,
            y=row['name'],
            text=row['text'],
            showarrow=False,
            font=dict(color='white', size=12, family='Arial'),
            xanchor="center"
        )

    def _create_milestone_trace(self, row, color):
        """Create trace for a milestone"""
        return go.Scatter(
            x=[row['start']],
            y=[row['name']],
            mode='markers',
            marker=dict(
                symbol='diamond',
                size=16,
                color=color,
                line=dict(width=2, color='white')
            ),
            name=row['name'],
            hoverinfo='text',
            hovertext=self._get_hover_text(row),
            showlegend=False
        )

    def _get_hover_text(self, row):
        """Generate hover text for tasks"""
        if 'milestone' in row and row['milestone']:
            return (
                f"<b>{row['name']}</b><br>"
                f"Date: {row['start'].strftime('%b %d, %Y')}<br>"
                f"Status: {row['progress']}% complete"
            )
        else:
            return (
                f"<b>{row['name']}</b><br>"
                f"Start: {row['start'].strftime('%b %d, %Y')}<br>"
                f"End: {row['end'].strftime('%b %d, %Y')}<br>"
                f"Duration: {row['duration']} days<br>"
                f"Status: {row['progress']}% complete"
            )

    def _configure_layout(self, fig, df, today):
        """Configure the figure layout"""
        fig.update_layout(
            title=dict(
                text="Project Timeline",
                font=dict(size=18, family="Arial, sans-serif", color="#333333"),
                x=0.5,
            ),
            xaxis=dict(
                title=None,
                tickformat="%b %d, %Y",
                gridcolor="#F5F5F5",
                linecolor="#E0E0E0",
                zeroline=False,
                tickfont=dict(family="Arial, sans-serif", size=11),
                type='date'
            ),
            yaxis=dict(
                title=None,
                autorange="reversed",
                showgrid=False,
                showline=False,
                zeroline=False,
                tickfont=dict(family="Arial, sans-serif", size=12),
                categoryorder='array',
                categoryarray=df['name'].tolist()
            ),
            plot_bgcolor='white',
            paper_bgcolor='white',
            height=max(400, len(df) * 40),
            margin=dict(l=120, r=30, b=50, t=70, pad=10),
            hoverlabel=dict(
                bgcolor="white",
                font_size=12,
                font_family="Arial, sans-serif"
            ),
            showlegend=False
        )

        # Add grid lines
        for name in df['name'].unique():
            fig.add_shape(
                type="line",
                x0=df['start'].min(),
                x1=df['end'].max(),
                y0=name,
                y1=name,
                line=dict(color="#F5F5F5", width=1),
                layer="below"
            )

        # Add today marker
        fig.add_shape(
            type="line",
            x0=today,
            x1=today,
            y0=0,
            y1=1,
            yref="paper",
            line=dict(color="#FF4136", width=2, dash="dash")
        )

        # Add today label
        fig.add_annotation(
            x=today,
            y=1,
            yref="paper",
            text="Today",
            showarrow=False,
            font=dict(color="#FF4136", size=12),
            xanchor="center",
            yanchor="bottom"
        )

        # Add color legend
        fig.add_annotation(
            x=1.0,
            y=-0.12,
            xref="paper",
            yref="paper",
            text="<span style='color:#22c55e;'>■</span> Completed   <span style='color:#4361EE;'>■</span> In Progress   <span style='color:#ef4444;'>■</span> Overdue",
            showarrow=False,
            font=dict(size=12, family="Arial"),
            align="right",
            xanchor="right",
            yanchor="top"
        )

class ProjectServiceDeliveryView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'service_delivery',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/service_delivery_content.html', context)
        return render(request, self.template_name, context)

class ProjectHealthProductsTechnologiesView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'health_products_technologies',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/health_products_technologies_content.html', context)
        return render(request, self.template_name, context)

class ProjectHumanResourceForHealthView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'human_resource_for_health',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/human_resource_for_health_content.html', context)
        return render(request, self.template_name, context)

class ProjectHealthInfoSystemsView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'health_info_systems',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/health_info_systems_content.html', context)
        return render(request, self.template_name, context)

class ProjectHealthFinancingView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'health_financing',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/health_financing_content.html', context)
        return render(request, self.template_name, context)

class ProjectLeadershipGovernanceView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'leadership_governance',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/leadership_governance_content.html', context)
        return render(request, self.template_name, context)

class ProjectDataQualityView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'data_quality',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/data_quality_content.html', context)
        return render(request, self.template_name, context)


import logging
import pandas as pd
import plotly.express as px
import plotly.io as pio
from django.shortcuts import render, get_object_or_404
from django.views import View
from .models import ResearchProject
# Assuming your data-fetching functions are in a local 'utils.py' file or similar
# from .utils import get_baseline_data, get_baseline_data_with_averages

# Set up a logger for this module
logger = logging.getLogger(__name__)    


class ProjectBaselineView(LoginRequiredMixin, View):
    """
    This single view handles the entire Baseline section and all its tabs.
    It intelligently returns either a full page or a content partial
    based on whether the request is a normal navigation or an AJAX call.
    """
    full_page_template = 'research_dashboard/project_detail.html'
    content_partial_template = 'research_dashboard/partials/baseline_content.html'
    
    # Define all available tabs and their corresponding handler methods
    TAB_HANDLERS = {
        'facility_profile': 'get_facility_profile_context',
        'staff_profile': 'get_staff_profile_context',
        'service_integration': 'get_service_integration_context',
        'patient_load': 'get_patient_load_context',
        'his': 'get_his_context',
        'supply_chain': 'get_supply_chain_context',
        'governance': 'get_governance_context',
        'system_financing': 'get_system_financing_context',
        # Add more tabs here as needed
    }

    # ===============================================================
    # Centralized Color Palette Configuration
    # ===============================================================
    CATEGORY_COLOR_PALETTES = {
        'level': px.colors.qualitative.Vivid,
        'ownership': px.colors.qualitative.G10,
        'county': px.colors.qualitative.Safe, # Add one for county for consistency
        # Add other categories here in the future
    }
    
    # Default tab if none specified
    DEFAULT_TAB = 'facility_profile'
    
    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        
        # Determine which tab should be active
        active_tab = request.GET.get('tab', self.DEFAULT_TAB)
        
        # Base context for all tabs
        context = {
            'project': project,
            'current_sub_view': active_tab,
            'current_view': 'baseline',
        }
        
        # Get the handler method for the active tab
        handler_name = self.TAB_HANDLERS.get(active_tab)
        if handler_name and hasattr(self, handler_name):
            # Call the appropriate handler method
            handler = getattr(self, handler_name)
            try:
                context = handler(request, context)
            except Exception as e:
                logger.error(f"Error in {handler_name}:", exc_info=True)
                context['error'] = f"An error occurred while generating the {active_tab.replace('_', ' ')} data."
        else:
            # Handle invalid tab
            logger.warning(f"Invalid tab requested: {active_tab}")
            context['error'] = f"The requested tab '{active_tab}' does not exist."
        
        # Determine whether to render full page or partial content
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            logger.info("AJAX request detected. Rendering baseline content partial.")
            return render(request, self.content_partial_template, context)
        else:
            logger.info("Full page request detected. Rendering main project detail page.")
            return render(request, self.full_page_template, context)

    def get_dependent_filter_options(self, df, request):
        """
        Handles dependent filtering logic.
        1. Filters by county.
        2. Determines available levels and ownerships from the county-filtered data.
        3. Applies the final filters.
        """
        # 1. Always get the full list of counties for the first filter.
        all_distinct_counties = sorted(df['county'].unique().tolist())
        selected_counties = [c for c in request.GET.getlist('county', all_distinct_counties) if c]
        if not selected_counties:
            selected_counties = all_distinct_counties

        # 2. Create a temporary DataFrame filtered ONLY by the selected counties.
        county_filtered_df = df[df['county'].isin(selected_counties)].copy()

        # 3. Get the distinct levels and owners FROM the county-filtered data.
        distinct_levels = sorted(county_filtered_df['level'].unique().tolist())
        distinct_owners = sorted(county_filtered_df['ownership'].unique().tolist())

        # 4. Get the selected levels and owners from the request, defaulting to all available.
        selected_levels = [l for l in request.GET.getlist('level', distinct_levels) if l]
        if not selected_levels:
            selected_levels = distinct_levels

        selected_owners = [o for o in request.GET.getlist('ownership', distinct_owners) if o]
        if not selected_owners:
            selected_owners = distinct_owners

        # 5. Create the FINAL filtered DataFrame using all three selections.
        filtered_df = county_filtered_df[
            county_filtered_df['level'].isin(selected_levels) &
            county_filtered_df['ownership'].isin(selected_owners)
        ]

        # 6. Return both the filtered dataframe and the filter options for the context.
        return {
            'filtered_df': filtered_df,
            'filter_options': {
                'distinct_counties': all_distinct_counties,
                'distinct_levels': distinct_levels,
                'distinct_owners': distinct_owners,
                'selected_counties': selected_counties,
                'selected_levels': selected_levels,
                'selected_owners': selected_owners
            }
        }

    def get_chart_layout(self):
        """
        Returns a consistent chart layout for all charts
        """
        return {
        'height': 450,
        'template': 'plotly_white',
        'plot_bgcolor': '#f8fafc',

        'title': {'x': 0.5, 'xanchor': 'center', 'font': {'size': 16, 'family': 'Arial, sans-serif'}},
        'legend': {'orientation': 'h', 'yanchor': 'bottom', 'y': 1.02, 'xanchor': 'right', 'x': 1},
        'margin': {'l': 40, 'r': 20, 't': 80, 'b': 20},
        'xaxis': {'title': None, 'automargin': True },
        'yaxis': {'title': 'Count','automargin': True},
        }
    
    def get_facility_profile_context(self, request, context):
        """
        Generates all data and charts for the Facility Profile tab.
        """
        logger.info("Generating context for the 'facility_profile' tab.")
        try:
            df, df_with_averages = get_baseline_data_with_averages()
            
            # Use the new dependent filter method
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context

            # Get the standard chart layout
            chart_layout = self.get_chart_layout()

            # Generate charts
            county_counts = filtered_df['county'].value_counts().reset_index()
            level_counts = filtered_df['level'].value_counts().reset_index()
            ownership_counts = filtered_df['ownership'].value_counts().reset_index()
            
            fig_county = px.bar(county_counts, x='county', y='count', color='county', 
                               title='Distribution by County', text_auto=True,
                               color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'))
            fig_county.update_layout(chart_layout, showlegend=False)
            
            fig_level = px.bar(level_counts, x='level', y='count', color='level', 
                              title='Distribution by KEPH Level', text_auto=True,
                              color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level'), 
                              category_orders={'level': level_counts['level'].tolist()})
            fig_level.update_layout(chart_layout, showlegend=False)
            
            fig_ownership = px.bar(ownership_counts, x='ownership', y='count', color='ownership', 
                                  title='Distribution by Ownership', text_auto=True, 
                                  color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership'),
                                  category_orders={'ownership': ownership_counts['ownership'].tolist()})
            fig_ownership.update_layout(chart_layout, showlegend=False)

            # Add chart HTML to the context
            context.update({
                'chart_county': pio.to_html(fig_county, full_html=False, include_plotlyjs='cdn'),
                'chart_level': pio.to_html(fig_level, full_html=False),
                'chart_ownership': pio.to_html(fig_ownership, full_html=False),
            })

        except Exception as e:
            logger.error("Error generating facility profile context:", exc_info=True)
            context['error'] = "An error occurred while generating the facility profile charts."
            
        return context

    def get_staff_profile_context(self, request, context):
        """
        Generates all data and charts for the Staff Profile tab.
        """
        logger.info("Generating context for the 'staff_profile' tab.")
        try:
            df = get_baseline_data()
            
            # Use the new dependent filter method
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            # Get the standard chart layout
            chart_layout = self.get_chart_layout()
            
            # --- The rest of your chart generation logic remains the same ---
            key_staff_columns = [
                'employed_nurse', 'employed_co', 'employed_lab_tech', 'employed_doc', 
                'employed_hts_counsellors', 'employed_pharmaceutical', 'employed_nutritionist', 
                'employed_pharmacist'
            ]
            
            def clean_column_names(col_name):
                return col_name.replace('employed_', '').replace('_', ' ').title()

            # Generate charts
            total_staff = filtered_df[key_staff_columns].sum().astype(float).sort_values(ascending=False).reset_index()
            total_staff.columns = ['Staff Cadre', 'Total Count']
            total_staff['Staff Cadre'] = total_staff['Staff Cadre'].apply(clean_column_names)
            fig_total_staff = px.bar(
                total_staff, 
                x='Staff Cadre', 
                y='Total Count', 
                text='Total Count',
                title='Total Staff Count'
            )
            fig_total_staff.update_traces(textposition='outside', texttemplate='%{text:,.0f}')
            fig_total_staff.update_layout(chart_layout, showlegend=False, xaxis_title=None, yaxis_title='Total Staff')
            
            # Average staff per facility
            average_staff = filtered_df[key_staff_columns].mean().sort_values(ascending=False).reset_index()
            average_staff.columns = ['Staff Cadre', 'Average Count']
            average_staff['Staff Cadre'] = average_staff['Staff Cadre'].apply(clean_column_names).copy()
            fig_avg_staff = px.bar(
                average_staff, 
                x='Staff Cadre', 
                y='Average Count', 
                text='Average Count',
                title='Average Staff per Facility'
            )
            fig_avg_staff.update_traces(textposition='outside', texttemplate='%{text:.2f}')
            fig_avg_staff.update_layout(chart_layout, showlegend=False, xaxis_title=None, yaxis_title='Average Count')

            # --- Total staff count by county ---
            count_by_county = pd.melt(
                filtered_df.groupby('county')[key_staff_columns].sum().reset_index(), 
                id_vars='county'
            )
            count_by_county['variable'] = count_by_county['variable'].apply(clean_column_names)
            fig_count_by_county = px.bar(
                count_by_county, 
                x='variable', 
                y='value', 
                color='county', 
                barmode='group', 
                text ='value',  # Use True for clean integer formatting
                title='Total Staff Count by County',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'),
            )
            # Apply the shared layout and customize titles
            fig_count_by_county.update_layout(
                chart_layout, 
                xaxis_title=None, 
                yaxis_title='Total Staff Count', 
                legend_title_text='County'
            )
            fig_count_by_county.update_traces(textposition='outside', texttemplate='%{text:,.0f}')

            # Average staff by county
            avg_by_county = pd.melt(
                filtered_df.groupby('county')[key_staff_columns].mean().reset_index(), 
                id_vars='county'
            )
            avg_by_county['variable'] = avg_by_county['variable'].apply(clean_column_names)
            fig_by_county = px.bar(
                avg_by_county, 
                x='variable', 
                y='value', 
                color='county', 
                barmode='group', 
                text_auto='.2f', 
                title='Average Staff by County',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'),
            )
            fig_by_county.update_layout(
                chart_layout, 
                xaxis_title=None, 
                yaxis_title='Average per Facility', 
                legend_title_text='County'
            )
            fig_by_county.update_traces(textposition='outside')

            # Average staff by KEPH level
            avg_by_level = pd.melt(
                filtered_df.groupby('level')[key_staff_columns].mean().reset_index(), 
                id_vars='level'
            )
            avg_by_level['variable'] = avg_by_level['variable'].apply(clean_column_names)
            fig_by_level = px.bar(
                avg_by_level, 
                x='variable', 
                y='value', 
                color='level', 
                barmode='group', 
                text_auto='.2f', 
                title='Average Staff by KEPH Level',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level'),
            )
            fig_by_level.update_layout(
                chart_layout, 
                xaxis_title=None, 
                yaxis_title='Average per Facility', 
                legend_title_text='KEPH Level'
            )
            fig_by_level.update_traces(textposition='outside')

            # Average staff by ownership
            avg_by_ownership = pd.melt(
                filtered_df.groupby('ownership')[key_staff_columns].mean().reset_index(), 
                id_vars='ownership'
            )
            avg_by_ownership['variable'] = avg_by_ownership['variable'].apply(clean_column_names)
            fig_by_ownership = px.bar(
                avg_by_ownership, 
                x='variable', 
                y='value', 
                color='ownership', 
                barmode='group', 
                text_auto='.2f', 
                title='Average Staff by Ownership',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership'),
            )
            fig_by_ownership.update_layout(
                chart_layout, 
                xaxis_title=None, 
                yaxis_title='Average per Facility', 
                legend_title_text='Ownership'
            )
            fig_by_ownership.update_traces(textposition='outside')

            # Add chart HTML to the context
            context.update({
                'chart_total_staff': pio.to_html(fig_total_staff, full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False}),
                'chart_count_by_county': pio.to_html(fig_count_by_county, full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False}),
                'chart_avg_staff': pio.to_html(fig_avg_staff, full_html=False, config={'displayModeBar': False}),
                'chart_by_county': pio.to_html(fig_by_county, full_html=False, config={'displayModeBar': False}),
                'chart_by_level': pio.to_html(fig_by_level, full_html=False, config={'displayModeBar': False}),
                'chart_by_ownership': pio.to_html(fig_by_ownership, full_html=False, config={'displayModeBar': False}),
            })

        except Exception as e:
            logger.error("Error generating staff profile context:", exc_info=True)
            context['error'] = "An error occurred while generating the staff profile charts."
            
        return context


    def get_service_integration_context(self, request, context):
        """
        Generates grouped horizontal bar charts for Service Integration Model Analysis,
        matching the provided image.
        """
        logger.info("Generating context for the 'service_integration' tab.")
        try:
            df = get_baseline_data()
            
            # Use the new dependent filter method
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            # Get the standard chart layout
            chart_layout = self.get_chart_layout()

            # --- Chart 1: Service Delivery Models by County ---
            # Group the data by both county and the service model, then get the size of each group.
            model_by_county = filtered_df.groupby(['county', 'patients_hivncd_care']).size().reset_index(name='count')
            
            fig_model_by_county = px.bar(
                model_by_county,
                x='count',                      # Numerical count on the x-axis
                y='patients_hivncd_care',       # Categorical model on the y-axis
                color='county',                 # Group bars by county
                barmode='group',                # Place bars side-by-side
                title='Baseline HIV/NCD Service Delivery Models by County',
                text_auto=True,                 # Display the count on each bar
                orientation='h',                 # Ensure horizontal orientation
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'),
            )
            # Update the layout for clarity
            fig_model_by_county.update_layout(
                chart_layout,
                height=500, # Give it a bit more height for readability
                legend_title_text='County', 
                yaxis_title='Service Delivery Model', 
                xaxis_title='Number of Facilities'
            ).update_yaxes(categoryorder="total ascending") # Sort models by frequency

            # --- Chart 2: Service Delivery Models by Ownership ---
            # Use the exact same logic, just group by 'ownership' instead of 'county'.
            model_by_ownership = filtered_df.groupby(['ownership', 'patients_hivncd_care']).size().reset_index(name='count')
            
            fig_model_by_ownership = px.bar(
                model_by_ownership,
                x='count',                      # Numerical count on the x-axis
                y='patients_hivncd_care',       # Categorical model on the y-axis
                color='ownership',              # Group bars by ownership
                barmode='group',                # Place bars side-by-side
                title='Baseline HIV/NCD Service Delivery Models by Ownership',
                text_auto=True,
                orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership'),
            )
            # Update the layout for clarity
            fig_model_by_ownership.update_layout(
                chart_layout, 
                height=500, # Give it a bit more height for readability
                legend_title_text='Ownership', 
                yaxis_title='Service Delivery Model', 
                xaxis_title='Number of Facilities'
            ).update_yaxes(categoryorder="total ascending")

            # --- Chart 3: Service Delivery Models by KEPH levels ---
            # Use the exact same logic, just group by 'ownership' instead of 'county'.
            model_by_level = filtered_df.groupby(['level', 'patients_hivncd_care']).size().reset_index(name='count')
            
            fig_model_by_level = px.bar(
                model_by_level,
                x='count',                      # Numerical count on the x-axis
                y='patients_hivncd_care',       # Categorical model on the y-axis
                color='level',              # Group bars by ownership
                barmode='group',                # Place bars side-by-side
                title='Baseline HIV/NCD Service Delivery Models by KEPH levels',
                text_auto=True,
                orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level'),
            )
            # Update the layout for clarity
            fig_model_by_level.update_layout(
                chart_layout, 
                height=500, # Give it a bit more height for readability
                legend_title_text='KEPH Level', 
                yaxis_title='Service Delivery Model', 
                xaxis_title='Number of Facilities'
            ).update_yaxes(categoryorder="total ascending")

            # Add the new chart HTML to the context
            context.update({
                'chart_model_by_county': pio.to_html(fig_model_by_county, full_html=False, include_plotlyjs='cdn'),
                'chart_model_by_ownership': pio.to_html(fig_model_by_ownership, full_html=False),
                'chart_model_by_level': pio.to_html(fig_model_by_level, full_html=False),
            })

        except KeyError as e:
            logger.error(f"Column not found for service integration analysis: {e}", exc_info=True)
            context['error'] = "The data required for service integration analysis (e.g., 'patients_hivncd_care' column) is not available."
        except Exception as e:
            logger.error("Error generating service integration context:", exc_info=True)
            context['error'] = "An error occurred while generating the service integration charts."
            
        return context
    
    def get_patient_load_context(self, request, context):
        """
        Generates charts for Patient Load and Co-morbidity Analysis.
        """
        logger.info("Generating context for the 'patient_load' tab.")
        try:
            df = get_baseline_data()
            
            # Use the new dependent filter method
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            chart_layout = self.get_chart_layout()

            # --- Data Preparation (as in your notebook) ---
            conditions = {
                'HIV': [col for col in df.columns if col.startswith('hiv_') and '_dm' not in col and '_htn' not in col],
                'DM': [col for col in df.columns if col.startswith('diabetes_')],
                'Hypertension': [col for col in df.columns if col.startswith('htn_') and 'dm_htn' not in col],
                'DM + HTN': [col for col in df.columns if 'dm_htn' in col],
                'HIV + DM': [col for col in df.columns if 'hiv_dm' in col],
                'HIV + HTN': [col for col in df.columns if 'hiv_htn' in col],
                'HIV + HTN + DM': [col for col in df.columns if 'hiv_htn_dm' in col]
            }
            
            # --- Chart 1: Total Annual Visits ---
            # Calculate total annual visits from the UNFILTERED data
            annual_visits_list = []
            for condition_name, cols in conditions.items():
                if cols:
                    total_visits = filtered_df[cols].sum().sum()
                    annual_visits_list.append({'Condition': condition_name, 'Total Annual Visits (All Facilities)': total_visits})
            
            annual_visits_df = pd.DataFrame(annual_visits_list).sort_values('Total Annual Visits (All Facilities)', ascending=False)
            
            # print(annual_visits_df.head(1))
            fig_total_annual = px.bar(
                annual_visits_df,
                y='Condition',
                x='Total Annual Visits (All Facilities)',
                title='Total Annual Patient Visits by Condition (All Facilities)',
                text='Total Annual Visits (All Facilities)',
                orientation='h'
            )
            fig_total_annual.update_traces(texttemplate='%{text:,.0f}')
            fig_total_annual.update_layout(
                chart_layout,height=600,
                yaxis_title=None,
                xaxis_title='Total Annual Visits (All Facilities)'
            ).update_yaxes(categoryorder="total ascending")

            # --- Stratified Charts (using the FILTERED data) ---
            # Create the df_with_averages using the filtered_df
            avg_cols_dict = {}
            for condition_name, cols in conditions.items():
                if cols:
                    avg_cols_dict[condition_name] = filtered_df[cols].sum(axis=1) / 12
            
            df_avg = pd.DataFrame(avg_cols_dict)
            df_with_averages = pd.concat([filtered_df[['county', 'level', 'ownership']], df_avg], axis=1)
            
            cols_for_viz = list(conditions.keys())

            # --- Chart 2: Stratified by County ---
            patient_load_by_county = df_with_averages.groupby('county')[cols_for_viz].mean().reset_index()
            df_melted_county = pd.melt(patient_load_by_county, id_vars='county', var_name='Condition', value_name='Avg. Monthly Visits')
            fig_by_county = px.bar(
                df_melted_county, x='Condition', y='Avg. Monthly Visits', color='county', barmode='group',
                title='Average Monthly Patient Visits per Facility by County', text_auto='.1f',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'),
            )
            fig_by_county.update_layout(chart_layout, legend_title_text='County')

            # --- Chart 3: Stratified by KEPH Level ---
            patient_load_by_level = df_with_averages.groupby('level')[cols_for_viz].mean().reset_index()
            df_melted_level = pd.melt(patient_load_by_level, id_vars='level', var_name='Condition', value_name='Avg. Monthly Visits')
            fig_by_level = px.bar(
                df_melted_level, x='Condition', y='Avg. Monthly Visits', color='level', barmode='group',
                title='Average Monthly Patient Visits per Facility by KEPH Level', text_auto='.1f',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level'),
            )
            fig_by_level.update_layout(chart_layout, legend_title_text='KEPH Level')

            # --- Chart 4: Stratified by Ownership ---
            patient_load_by_ownership = df_with_averages.groupby('ownership')[cols_for_viz].mean().reset_index()
            df_melted_ownership = pd.melt(patient_load_by_ownership, id_vars='ownership', var_name='Condition', value_name='Avg. Monthly Visits')
            fig_by_ownership = px.bar(
                df_melted_ownership, x='Condition', y='Avg. Monthly Visits', color='ownership', barmode='group',
                title='Average Monthly Patient Visits per Facility by Ownership', text_auto='.1f',
                              color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership'),
            )
            fig_by_ownership.update_layout(chart_layout,legend_title_text='Ownership')
                       
            # --- Chart 5: Absolute Annual Visits by County ---
            # Step 1: For each facility in the filtered_df, calculate its total annual visits for each condition.
            total_counts_per_facility = pd.DataFrame()
            for condition_name, cols in conditions.items():
                if cols:
                    total_counts_per_facility.loc[:, condition_name] = filtered_df[cols].sum(axis=1)
            
            # Add the county back in for grouping - create a new DataFrame to avoid SettingWithCopyWarning
            total_counts_with_county = total_counts_per_facility.copy()
            total_counts_with_county['county'] = filtered_df['county'].values
            
            # Step 2: Now, group by county and SUM these totals.
            absolute_counts_by_county = total_counts_with_county.groupby('county')[cols_for_viz].sum().reset_index()
            
            # Step 3: Melt the data for plotting.
            df_melted_abs = pd.melt(absolute_counts_by_county, id_vars='county', var_name='Condition', value_name='Total Annual Visits')

            # Step 4: Create the horizontal bar chart.
            fig_by_county_abs = px.bar(
                df_melted_abs,
                y='Condition',              # Categorical on Y-axis
                x='Total Annual Visits',   # Numerical on X-axis
                color='county',             # Group by county
                barmode='group',            # Place bars side-by-side
                title='Total Annual Patient Visits by County',
                text='Total Annual Visits',
                orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'),
            )
            fig_by_county_abs.update_traces(texttemplate='%{text:,.0f}')
            fig_by_county_abs.update_layout(
                chart_layout,height=600,
                yaxis_title=None,
                xaxis_title='Total Annual Visits',
                legend_title_text='County'
            ).update_yaxes(categoryorder="total ascending")

            # ===============================================================
            # START OF FIX 2: Integrate the new monthly trend analysis
            # ===============================================================
            conditions = {
                'HIV Only': [col for col in df.columns if col.startswith('hiv_') and '_dm' not in col and '_htn' not in col],
                'DM Only': [col for col in df.columns if col.startswith('diabetes_')],
                'Hypertension Only': [col for col in df.columns if col.startswith('htn_') and 'dm_htn' not in col],
                'DM+HTN': [col for col in df.columns if col.startswith('dm_htn')],
                'HIV+DM': [col for col in df.columns if col.startswith('hiv_dm')],
                'HIV+HTN': [col for col in df.columns if col.startswith('hiv_htn') and '_dm' not in col],
                'HIV+HTN+DM': [col for col in df.columns if col.startswith('hiv_htn_dm')]
            }
            
            col_to_condition_map = {col: cond for cond, cols in conditions.items() for col in cols}
            all_condition_cols = list(col_to_condition_map.keys())
            
            # Use the filtered_df for the trend chart
            df_long = filtered_df.melt(id_vars=['facility_mfl'], value_vars=all_condition_cols,
                                       var_name='condition_month', value_name='visits')

            df_long['Condition'] = df_long['condition_month'].map(col_to_condition_map)
            df_long['month'] = df_long['condition_month'].apply(lambda x: x.split('_')[-1])
            month_order = ['jan', 'feb', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
            df_long['month'] = pd.Categorical(df_long['month'], categories=month_order, ordered=True)
            monthly_trends = df_long.groupby(['month', 'Condition'], observed=True)['visits'].sum().reset_index()

            # --- Visualization with Plotly Express ---
            conditions_to_plot = ['HIV Only', 'Diabetes Only', 'Hypertension Only', 'HIV+HTN', 'HIV+DM', 'HIV+HTN+DM']
            trend_data_subset = monthly_trends[monthly_trends['Condition'].isin(conditions_to_plot)]
            
            # Add a formatted text column for clean labels on the chart
            trend_data_subset = trend_data_subset.copy()
            trend_data_subset['visits_text'] = trend_data_subset['visits'].apply(lambda x: f'{x:,.0f}')

            fig_monthly_trend = px.line(
                trend_data_subset,
                x='month',
                y='visits',
                color='Condition',      # Replaces 'hue'
                line_dash='Condition',  # Replaces 'style' for different line types
                markers=True,           # Replaces 'markers=True'
                text='visits_text',     # Specify the column for text labels
                title='Total Monthly Patient Visits Trend'
            )

            # Style the text labels to appear above the markers
            fig_monthly_trend.update_traces(textposition="top center")

            # Apply the shared layout and customize further
            y_max = trend_data_subset['visits'].max()
            fig_monthly_trend.update_layout(
                self.get_chart_layout(),
                height=600,
                xaxis_title='Month',
                yaxis_title='Total Number of Monthly Visits',
                legend_title_text='Condition'
            ).update_yaxes(
                range=[0, y_max * 1.15 if y_max > 0 else 10] # Set y-axis range
            )
            
            # ===============================================================
            # END OF FIX 2
            # ===============================================================


            context.update({
                'chart_total_annual_visits': pio.to_html(fig_total_annual, full_html=False, include_plotlyjs='cdn'),
                'chart_avg_visits_by_county': pio.to_html(fig_by_county, full_html=False),
                'chart_abs_visits_by_county': pio.to_html(fig_by_county_abs, full_html=False),
                'chart_avg_visits_by_level': pio.to_html(fig_by_level, full_html=False),
                'chart_avg_visits_by_ownership': pio.to_html(fig_by_ownership, full_html=False),
                'chart_monthly_trend': pio.to_html(fig_monthly_trend, full_html=False),
            })

        except KeyError as e:
            logger.error(f"Column not found for patient load analysis: {e}", exc_info=True)
            context['error'] = "The data required for patient load analysis is not available."
        except Exception:
            logger.error("Error generating patient load context:", exc_info=True)
            context['error'] = "An error occurred while generating the patient load charts."
            
        return context

    def get_his_context(self, request, context):
        """
        Generates charts for Health Information Systems (HIS) Analysis.
        """
        logger.info("Generating context for the 'his' tab.")
        try:
            df = get_baseline_data()
            
            # Use the shared dependent filter method to get filtered data and options
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            # Use the shared layout for consistency
            chart_layout = self.get_chart_layout()

            # --- Chart 1 & 2: Overall HIS Usage ---
            # Calculate value counts for HIV and NCD systems
            hiv_counts = filtered_df['his_hiv'].value_counts().reset_index()
            ncd_counts = filtered_df['his_ncd'].value_counts().reset_index()

            fig_hiv_overall = px.bar(
                hiv_counts,
                x='count',
                y='his_hiv',
                title='Health Information Systems (HIS) Used for HIV Services',
                text_auto=True,
                orientation='h',
                color_discrete_sequence=px.colors.sequential.GnBu_r
            )
            fig_hiv_overall.update_layout(
                chart_layout,
                xaxis_title='Number of Facilities',
                yaxis_title='HIS Type'
            ).update_yaxes(categoryorder="total ascending")

            fig_ncd_overall = px.bar(
                ncd_counts,
                x='count',
                y='his_ncd',
                title='Health Information Systems (HIS) Used for NCD Services',
                text_auto=True,
                orientation='h',
                color_discrete_sequence=px.colors.sequential.OrRd_r
            )
            fig_ncd_overall.update_layout(
                chart_layout,
                xaxis_title='Number of Facilities',
                yaxis_title=None # Cleaner look side-by-side
            ).update_yaxes(categoryorder="total ascending")

            # --- Stratified Charts: HIS Usage by County ---
            hiv_by_county = filtered_df.groupby(['county', 'his_hiv']).size().reset_index(name='count')
            fig_hiv_by_county = px.bar(
                hiv_by_county, y='his_hiv', x='count', color='county', barmode='group',
                title='HIS for HIV Services by County', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county')
            )
            fig_hiv_by_county.update_layout(
                chart_layout, height=600, legend_title_text='County',
                xaxis_title='Number of Facilities', yaxis_title='HIS Type'
            ).update_yaxes(categoryorder="total ascending")

            ncd_by_county = filtered_df.groupby(['county', 'his_ncd']).size().reset_index(name='count')
            fig_ncd_by_county = px.bar(
                ncd_by_county, y='his_ncd', x='count', color='county', barmode='group',
                title='HIS for NCD Services by County', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county')
            )
            fig_ncd_by_county.update_layout(
                chart_layout, height=600, legend_title_text='County',
                xaxis_title='Number of Facilities', yaxis_title='HIS Type'
            ).update_yaxes(categoryorder="total ascending")

            # ===============================================================
            # START OF THE NEW CODE: Stratification by Level and Ownership
            # ===============================================================

            # --- Stratified Charts: HIS Usage by KEPH Level ---
            hiv_by_level = filtered_df.groupby(['level', 'his_hiv']).size().reset_index(name='count')
            fig_hiv_by_level = px.bar(
                hiv_by_level, y='his_hiv', x='count', color='level', barmode='group',
                title='HIS for HIV Services by KEPH Level', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level')
            )
            fig_hiv_by_level.update_layout(chart_layout, height=600, legend_title_text='KEPH Level', xaxis_title='Number of Facilities', yaxis_title='HIS Type').update_yaxes(categoryorder="total ascending")

            ncd_by_level = filtered_df.groupby(['level', 'his_ncd']).size().reset_index(name='count')
            fig_ncd_by_level = px.bar(
                ncd_by_level, y='his_ncd', x='count', color='level', barmode='group',
                title='HIS for NCD Services by KEPH Level', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level')
            )
            fig_ncd_by_level.update_layout(chart_layout, height=600, legend_title_text='KEPH Level', xaxis_title='Number of Facilities', yaxis_title='HIS Type').update_yaxes(categoryorder="total ascending")

            # --- Stratified Charts: HIS Usage by Ownership ---
            hiv_by_ownership = filtered_df.groupby(['ownership', 'his_hiv']).size().reset_index(name='count')
            fig_hiv_by_ownership = px.bar(
                hiv_by_ownership, y='his_hiv', x='count', color='ownership', barmode='group',
                title='HIS for HIV Services by Ownership', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership')
            )
            fig_hiv_by_ownership.update_layout(chart_layout, height=600, legend_title_text='Ownership', xaxis_title='Number of Facilities', yaxis_title='HIS Type').update_yaxes(categoryorder="total ascending")

            ncd_by_ownership = filtered_df.groupby(['ownership', 'his_ncd']).size().reset_index(name='count')
            fig_ncd_by_ownership = px.bar(
                ncd_by_ownership, y='his_ncd', x='count', color='ownership', barmode='group',
                title='HIS for NCD Services by Ownership', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership')
            )
            fig_ncd_by_ownership.update_layout(chart_layout, height=600, legend_title_text='Ownership', xaxis_title='Number of Facilities', yaxis_title='HIS Type').update_yaxes(categoryorder="total ascending")

            # Add all new chart HTML to the context
            context.update({
                'chart_hiv_overall': pio.to_html(fig_hiv_overall, full_html=False, include_plotlyjs='cdn'),
                'chart_ncd_overall': pio.to_html(fig_ncd_overall, full_html=False),
                'chart_hiv_by_county': pio.to_html(fig_hiv_by_county, full_html=False),
                'chart_ncd_by_county': pio.to_html(fig_ncd_by_county, full_html=False),
                
                'chart_hiv_by_level': pio.to_html(fig_hiv_by_level, full_html=False),
                'chart_ncd_by_level': pio.to_html(fig_ncd_by_level, full_html=False),
                'chart_hiv_by_ownership': pio.to_html(fig_hiv_by_ownership, full_html=False),
                'chart_ncd_by_ownership': pio.to_html(fig_ncd_by_ownership, full_html=False),
            })

        except KeyError as e:
            logger.error(f"Column not found for HIS analysis: {e}", exc_info=True)
            context['error'] = "The data required for HIS analysis (e.g., 'his_hiv', 'his_ncd' columns) is not available."
        except Exception as e:
            logger.error("Error generating HIS context:", exc_info=True)
            context['error'] = "An error occurred while generating the Health Information Systems charts."
            
        return context
    def get_supply_chain_context(self, request, context):
        """
        Generates charts for Supply Chain & Health Products Analysis.
        """
        logger.info("Generating context for the 'supply_chain' tab.")
        try:
            df = get_baseline_data()
            
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            chart_layout = self.get_chart_layout()

            # --- Data Preparation (No changes here) ---
            procure_cols = [col for col in df.columns if 'where_procure_med___' in col]
            source_map = {
                'where_procure_med___1': 'KEMSA', 'where_procure_med___2': 'Private Suppliers',
                'where_procure_med___3': 'Faith-Based', 'where_procure_med___4': 'Partners/Donors',
                'where_procure_med___5': 'Other'
            }
            equipment_cols = ['bp_monitor_available', 'glucometers_strips_available']
            equip_name_map = {
                'bp_monitor_available': 'BP Monitors',
                'glucometers_strips_available': 'Glucometers & Strips'
            }
            id_vars_for_melt = ['county', 'level', 'ownership']
            
            # Procurement long form
            df_procure_long = filtered_df.melt(id_vars=id_vars_for_melt, value_vars=procure_cols, var_name='source_col', value_name='value')
            df_procure_checked = df_procure_long[df_procure_long['value'] == 'Checked'].copy()
            df_procure_checked['Procurement Source'] = df_procure_checked['source_col'].map(source_map)

            # Equipment long form
            df_equip_long = filtered_df.melt(id_vars=id_vars_for_melt, value_vars=equipment_cols, var_name='Equipment', value_name='Status')
            df_equip_long['Equipment Label'] = df_equip_long['Equipment'].map(equip_name_map)
            available_statuses = ['available in use', 'available not in use']
            equip_available_df = df_equip_long[df_equip_long['Status'].isin(available_statuses)]

            # --- Overall Charts (No changes here) ---
            procure_counts = df_procure_checked['Procurement Source'].value_counts().reset_index()
            fig_procure_overall = px.bar(procure_counts, x='count', y='Procurement Source', title='Sources of Medication Procurement', text_auto=True, orientation='h')
            fig_procure_overall.update_layout(chart_layout, xaxis_title='Number of Facilities', yaxis_title='Source').update_yaxes(categoryorder="total ascending")

            equip_counts = df_equip_long.groupby(['Equipment Label', 'Status']).size().reset_index(name='count')
            status_color_map = {'available in use': 'green','available not in use': 'blue','not available': 'red'}
            fig_equip_overall = px.bar(equip_counts, x='Equipment Label', y='count', color='Status', barmode='stack',
                                        title='Availability of Basic Diagnostic Equipment', text_auto=True,
                                        color_discrete_map=status_color_map)
            fig_equip_overall.update_layout(chart_layout, xaxis_title=None, yaxis_title='Number of Facilities').update_traces(textfont_color='white')

            # --- Stratified by County ---
            procure_by_county = df_procure_checked.groupby(['county', 'Procurement Source']).size().reset_index(name='count')
            fig_procure_by_county = px.bar(procure_by_county, y='Procurement Source', x='count', color='county', barmode='group', 
                                           title='Procurement Sources by County', text_auto=True, orientation='h', 
                                           color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'))
            fig_procure_by_county.update_layout(chart_layout, 
                                                legend_title_text='County'
                                                ).update_yaxes(categoryorder="total ascending")
            
            equip_by_county_grouped = equip_available_df.groupby(['county', 'Equipment Label']
                                                                 ).size().reset_index(name='count')
            fig_equip_by_county = px.bar(equip_by_county_grouped, x='Equipment Label', y='count', 
                                         color='county', barmode='group', 
                                         title='Available Equipment by County', text_auto=True,
                                        color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county'))
            fig_equip_by_county.update_layout(chart_layout, 
                                            #   xaxis_title='Equipment Type', 
                                              yaxis_title='Number of Facilities', 
                                              legend_title_text='County').update_traces(textposition='outside')

            # --- Stratified by KEPH Level ---
            procure_by_level = df_procure_checked.groupby(['level', 'Procurement Source']).size().reset_index(name='count')
            fig_procure_by_level = px.bar(procure_by_level, y='Procurement Source', x='count', color='level', 
                                          barmode='group', title='Procurement Sources by KEPH Level', text_auto=True, orientation='h', 
                                          color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level'))
            fig_procure_by_level.update_layout(chart_layout, legend_title_text='KEPH Level'
                                               ).update_yaxes(categoryorder="total ascending")

            equip_by_level_grouped = equip_available_df.groupby(['level', 'Equipment Label']).size().reset_index(name='count')
            fig_equip_by_level = px.bar(equip_by_level_grouped, x='Equipment Label', y='count', color='level', 
                                        barmode='group', title='Available Equipment by KEPH Level', text_auto=True,
                                        color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level'))
            fig_equip_by_level.update_layout(chart_layout, 
                                            #  xaxis_title='Equipment Type', 
                                             yaxis_title='Number of Facilities', legend_title_text='KEPH Level'
                                             ).update_traces(textposition='outside')

            # --- Stratified by Ownership ---
            procure_by_ownership = df_procure_checked.groupby(['ownership', 'Procurement Source']).size().reset_index(name='count')
            fig_procure_by_ownership = px.bar(procure_by_ownership, y='Procurement Source', 
                                              x='count', color='ownership', barmode='group', 
                                              title='Procurement Sources by Ownership', text_auto=True, 
                                              orientation='h', color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership'))
            fig_procure_by_ownership.update_layout(chart_layout, 
                                                   legend_title_text='Ownership').update_yaxes(categoryorder="total ascending")

            equip_by_ownership_grouped = equip_available_df.groupby(['ownership', 'Equipment Label']).size().reset_index(name='count')
            fig_equip_by_ownership = px.bar(equip_by_ownership_grouped, x='Equipment Label', 
                                            y='count', color='ownership', barmode='group', 
                                            title='Available Equipment by Ownership', text_auto=True, 
                                            color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership'))
            fig_equip_by_ownership.update_layout(chart_layout, 
                                                #  xaxis_title='Equipment Type', 
                                                 yaxis_title='Number of Facilities', 
                                                 legend_title_text='Ownership').update_traces(textposition='outside')

            context.update({
                'chart_procure_overall': pio.to_html(fig_procure_overall, full_html=False, include_plotlyjs='cdn'),
                'chart_equip_overall': pio.to_html(fig_equip_overall, full_html=False),
                'chart_procure_by_county': pio.to_html(fig_procure_by_county, full_html=False),
                'chart_equip_by_county': pio.to_html(fig_equip_by_county, full_html=False),
                # Add the new charts to the context
                'chart_procure_by_level': pio.to_html(fig_procure_by_level, full_html=False),
                'chart_equip_by_level': pio.to_html(fig_equip_by_level, full_html=False),
                'chart_procure_by_ownership': pio.to_html(fig_procure_by_ownership, full_html=False),
                'chart_equip_by_ownership': pio.to_html(fig_equip_by_ownership, full_html=False),
            })

        except KeyError as e:
            logger.error(f"Column not found for Supply Chain analysis: {e}", exc_info=True)
            context['error'] = "The data required for Supply Chain analysis is not available."
        except Exception as e:
            logger.error("Error generating Supply Chain context:", exc_info=True)
            context['error'] = "An error occurred while generating the Supply Chain charts."
            
        return context
    def get_governance_context(self, request, context):
        """
        Generates charts for Governance and Integration Challenges Analysis.
        """
        logger.info("Generating context for the 'governance' tab.")
        try:
            df = get_baseline_data()
            
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            chart_layout = self.get_chart_layout()

            # --- Data Preparation ---
            challenge_cols = [col for col in df.columns if 'governce_challenge_integration___' in col]
            challenge_map = {
                'governce_challenge_integration___1': 'Lack of integrated guidelines/SOPs',
                'governce_challenge_integration___2': 'Separate M&E frameworks',
                'governce_challenge_integration___3': 'Inadequate leadership/governance',
                'governce_challenge_integration___4': 'Inadequate/separate funding',
                'governce_challenge_integration___6': 'Poor referral coordination',
                'governce_challenge_integration___7': 'Inadequate HR capacity/training',
                'governce_challenge_integration___8': 'High workload for providers',
                'governce_challenge_integration___5': 'Other'
            }
            
            id_vars_for_melt = ['county', 'level', 'ownership']
            df_long = filtered_df.melt(id_vars=id_vars_for_melt, value_vars=challenge_cols, var_name='variable', value_name='value')
            df_checked = df_long[df_long['value'] == 'Checked'].copy() # Use .copy() to avoid SettingWithCopyWarning
            df_checked['Challenge'] = df_checked['variable'].map(challenge_map)

            # --- Chart 1: Overall Challenges ---
            challenge_counts = df_checked['Challenge'].value_counts().reset_index()
            fig_overall = px.bar(
                challenge_counts, y='Challenge', x='count',color="count",
                title='Top Self-Reported Challenges to HIV/NCD Integration',
                text_auto=True, orientation='h', 
            )
            fig_overall.update_layout(chart_layout, height=600,
                                      xaxis_title='Number of Facilities Citing Challenge', 
                                      yaxis_title='').update_yaxes(categoryorder="total ascending")

            # --- Stratified Charts ---
            # By County
            by_county = df_checked.groupby(['county', 'Challenge']).size().reset_index(name='count')
            fig_by_county = px.bar(
                by_county, y='Challenge', x='count', color='county', barmode='group',
                title='Integration Challenges by County', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county')
            )
            fig_by_county.update_layout(chart_layout, height=600, 
                                        legend_title_text='County',
                                        yaxis_title='').update_yaxes(categoryorder="total ascending")

            # By KEPH Level
            by_level = df_checked.groupby(['level', 'Challenge']).size().reset_index(name='count')
            fig_by_level = px.bar(
                by_level, y='Challenge', x='count', color='level', barmode='group',
                title='Integration Challenges by KEPH Level', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level')
            )
            fig_by_level.update_layout(chart_layout, height=600, 
                                       legend_title_text='KEPH Level',
                                       yaxis_title='').update_yaxes(categoryorder="total ascending")

            # By Ownership
            by_ownership = df_checked.groupby(['ownership', 'Challenge']).size().reset_index(name='count')
            fig_by_ownership = px.bar(
                by_ownership, y='Challenge', x='count', color='ownership', barmode='group',
                title='Integration Challenges by Ownership', text_auto=True, orientation='h',
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership')
            )
            fig_by_ownership.update_layout(chart_layout, height=600, 
                                           legend_title_text='Ownership',
                                           yaxis_title='').update_yaxes(categoryorder="total ascending")

            context.update({
                'chart_governance_overall': pio.to_html(fig_overall, full_html=False, include_plotlyjs='cdn'),
                'chart_governance_by_county': pio.to_html(fig_by_county, full_html=False),
                'chart_governance_by_level': pio.to_html(fig_by_level, full_html=False),
                'chart_governance_by_ownership': pio.to_html(fig_by_ownership, full_html=False),
            })

        except KeyError as e:
            logger.error(f"Column not found for Governance analysis: {e}", exc_info=True)
            context['error'] = "The data required for Governance and Challenges analysis is not available."
        except Exception as e:
            logger.error("Error generating Governance context:", exc_info=True)
            context['error'] = "An error occurred while generating the Governance and Challenges charts."
            
        return context

    def get_system_financing_context(self, request, context):
        """
        Generates charts for Health System Financing Analysis.
        """
        logger.info("Generating context for the 'system_financing' tab.")
        try:
            df = get_baseline_data()
            
            filter_result = self.get_dependent_filter_options(df, request)
            filtered_df = filter_result['filtered_df']
            context.update(filter_result['filter_options'])
            
            if filtered_df.empty:
                context['no_data'] = True
                return context
            
            chart_layout = self.get_chart_layout()

            # --- Data Preparation ---
            expenditure_cols = {
                'Total Expenditure': 'total_expenditure_year',
                'HIV Expenditure': 'total_expenditure_hiv',
                'NCD Expenditure': 'total_expenditure_ncd'
            }
            expenditure_col_list = list(expenditure_cols.values())

            # Replace 9999 placeholder with NaN for accurate median calculations
            for col in expenditure_col_list:
                filtered_df[col] = filtered_df[col].replace(9999, np.nan)

            # --- Chart 1: By County ---
            median_exp_county = filtered_df.groupby('county')[expenditure_col_list].median().reset_index()
            df_melted_county = pd.melt(median_exp_county, id_vars='county', var_name='Expenditure Type', value_name='Median Annual Expenditure (KES)')
            df_melted_county['Expenditure Type'] = df_melted_county['Expenditure Type'].map({v: k for k, v in expenditure_cols.items()})

            fig_by_county = px.bar(
                df_melted_county, x='county', y='Median Annual Expenditure (KES)', color='Expenditure Type',
                barmode='group', title='Median Annual Expenditure by County', text_auto=True,
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('county')
            )
            fig_by_county.update_layout(chart_layout, legend_title_text='Expenditure').update_traces(texttemplate='%{y:,.0f}')

            # --- Chart 2: By KEPH Level ---
            median_exp_level = filtered_df.groupby('level')[expenditure_col_list].median().reset_index()
            df_melted_level = pd.melt(median_exp_level, id_vars='level', var_name='Expenditure Type', value_name='Median Annual Expenditure (KES)')
            df_melted_level['Expenditure Type'] = df_melted_level['Expenditure Type'].map({v: k for k, v in expenditure_cols.items()})

            fig_by_level = px.bar(
                df_melted_level, x='level', y='Median Annual Expenditure (KES)', color='Expenditure Type',
                barmode='group', title='Median Annual Expenditure by KEPH Level', text_auto=True,
                category_orders={'level': ['Level 2', 'Level 3', 'Level 4']},
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('level')
            )
            fig_by_level.update_layout(chart_layout, legend_title_text='Expenditure').update_traces(texttemplate='%{y:,.0f}')

            # --- Chart 3: By Ownership ---
            median_exp_ownership = filtered_df.groupby('ownership')[expenditure_col_list].median().reset_index()
            df_melted_ownership = pd.melt(median_exp_ownership, id_vars='ownership', var_name='Expenditure Type', value_name='Median Annual Expenditure (KES)')
            df_melted_ownership['Expenditure Type'] = df_melted_ownership['Expenditure Type'].map({v: k for k, v in expenditure_cols.items()})

            fig_by_ownership = px.bar(
                df_melted_ownership, x='ownership', y='Median Annual Expenditure (KES)', color='Expenditure Type',
                barmode='group', title='Median Annual Expenditure by Ownership', text_auto=True,
                color_discrete_sequence=self.CATEGORY_COLOR_PALETTES.get('ownership')
            )
            fig_by_ownership.update_layout(chart_layout, legend_title_text='Expenditure').update_traces(texttemplate='%{y:,.0f}')

            context.update({
                'chart_financing_by_county': pio.to_html(fig_by_county, full_html=False, include_plotlyjs='cdn'),
                'chart_financing_by_level': pio.to_html(fig_by_level, full_html=False),
                'chart_financing_by_ownership': pio.to_html(fig_by_ownership, full_html=False),
            })

        except KeyError as e:
            logger.error(f"Column not found for Financing analysis: {e}", exc_info=True)
            context['error'] = "The data required for Health Financing analysis is not available."
        except Exception as e:
            logger.error("Error generating Financing context:", exc_info=True)
            context['error'] = "An error occurred while generating the Health Financing charts."
            
        return context


def get_county_geodata():
    """Loads, processes, filters, and caches the GeoDataFrame."""
    global county_gdf
    if county_gdf is not None:
        return county_gdf

    try:
        gdf = gpd.read_file(os.path.join(settings.BASE_DIR, 'research_dashboard', 'data', 'ken_admbnda_adm1_iebc_20191031.shp'))
        
        # Filter for specific counties
        target_counties = ["Nairobi", "Kiambu", "Kitui"]
        gdf = gdf[gdf['ADM1_EN'].isin(target_counties)].copy()
        
        # Reproject to WGS 84 (EPSG:4326)
        if gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
            
        # Standardize the county name column
        gdf.rename(columns={'ADM1_EN': 'name'}, inplace=True)
        
        # Select only needed columns
        gdf = gdf[['name', 'geometry']]
        
        county_gdf = gdf
        return county_gdf
        
    except Exception as e:
        # print(f"Error loading county data: {str(e)}")
        return gpd.GeoDataFrame([], columns=['name', 'geometry'])

# Initialize county data cache
county_gdf = None
get_county_geodata()

def county_boundaries_api(request):
    """API endpoint that returns county boundaries as GeoJSON."""
    gdf = get_county_geodata()
    
    if gdf.empty:
        return JsonResponse({"error": "County boundary data could not be loaded"}, status=500)

    # Convert to GeoJSON
    geojson_data = json.loads(gdf.to_json())
    return JsonResponse(geojson_data)

# Username recovery view
from django.contrib.auth.views import PasswordResetDoneView
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.generic import FormView

class UsernameRecoveryView(FormView):
    template_name = 'registration/username_recovery_form.html'
    form_class = PasswordResetForm  # Reusing the password reset form for email field
    success_url = reverse_lazy('username_recovery_done')

    def form_valid(self, form):
        email = form.cleaned_data['email']
        associated_users = User.objects.filter(email__iexact=email)
        if associated_users.exists():
            for user in associated_users:
                # Send email with username
                subject = render_to_string('registration/username_recovery_subject.txt')
                # Email subject must be a single line
                subject = ''.join(subject.splitlines())
                message = render_to_string('registration/username_recovery_email.html', {
                    'user': user,
                })
                send_mail(subject, message, None, [user.email])
        # Always return success to avoid revealing if email exists
        return super().form_valid(form)
