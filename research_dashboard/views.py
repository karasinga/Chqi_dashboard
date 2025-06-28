from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, UpdateView, DetailView
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
import pandas as pd
from datetime import datetime

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

class ProjectDisaggregationView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id)
        context = {
            'project': project,
            'current_view': 'disaggregation',
        }
        if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'research_dashboard/partials/disaggregation_content.html', context)
        return render(request, self.template_name, context)

import geopandas as gpd
from django.conf import settings
import os
import json

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
        print(f"Error loading county data: {str(e)}")
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

# [Rest of the file remains unchanged...]
