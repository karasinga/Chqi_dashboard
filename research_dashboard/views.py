from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, UpdateView, DetailView
from .models import ResearchProject, Evaluator, Evaluation, EvaluationPhase, ProjectMilestone, ResearchDocument
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .forms import DocumentUploadForm, MetricForm
import json
from datetime import timedelta
import mimetypes
from django.http import HttpResponse, JsonResponse
import os
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

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
        
        # Start with projects where the current user is the lead researcher
        base_projects = ResearchProject.objects.filter(lead_researcher=request.user)
        projects = base_projects
        
        # Apply filters if specified
        if status_filter:
            projects = projects.filter(status=status_filter)
        if date_from:
            projects = projects.filter(start_date__gte=date_from)
        if date_to:
            projects = projects.filter(end_date__lte=date_to)
            
        # Add annotations after filtering
        projects = projects.annotate(
            active_phases=Count('phases', filter=Q(phases__completed=False)),
            completed_milestones=Count('milestones', filter=Q(milestones__status='completed')),
            total_milestones=Count('milestones')
        ).prefetch_related('phases', 'milestones')

        # Calculate completion percentage for each project
        today = timezone.now().date()
        for project in projects:
            if project.end_date and project.start_date:
                total_days = (project.end_date - project.start_date).days
                elapsed_days = (today - project.start_date).days
                
                # Handle cases where total_days is zero or negative
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
                # Fallback to milestone-based calculation
                if project.total_milestones > 0:
                    project.completion_percent = int((project.completed_milestones / project.total_milestones) * 100)
                else:
                    project.completion_percent = 0

        # Calculate status counts for all projects (not just filtered ones)
        status_counts = {
            status: base_projects.filter(status=status).count()
            for status, _ in ResearchProject.PROJECT_STATUS
        }

        # Pagination
        paginator = Paginator(projects, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'status_counts': status_counts,
            'status_filter': status_filter or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
            'status_options': ResearchProject.PROJECT_STATUS,
            'total_projects_count': base_projects.count()
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Handle project create/update/delete operations"""
        if request.POST.get('_method') == 'DELETE':
            return self._handle_delete(request)
            
        project_id = request.POST.get('project_id')
        try:
            if project_id:
                # Update existing project - verify ownership
                project = ResearchProject.objects.get(pk=project_id, lead_researcher=request.user)
                project.title = request.POST.get('title')
                project.description = request.POST.get('description')
                project.status = request.POST.get('status')
                project.start_date = request.POST.get('start_date')
                project.end_date = request.POST.get('end_date') or None
                project.save()
                messages.success(request, 'Project updated successfully!')
            else:
                # Create new project
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
            project = ResearchProject.objects.get(pk=project_id, lead_researcher=request.user)
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
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)

        if document_id:
            return self.view_document(request, document_id)

        context = {
            'project': project,
            'current_view': 'overview',
            'documents': project.documents.all(),
            'document_form': DocumentUploadForm(),
        }

        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/overview_content.html', context)
        return render(request, self.template_name, context)

    def post(self, request, project_id):
        """Handle document uploads"""
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
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
    data = json.loads(request.body)
    milestone.status = data.get('status')
    milestone.save()
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["POST"])
def update_timeline_order(request):
    data = json.loads(request.body)
    items = data.get('items', [])
    
    for item in items:
        if item['type'] == 'phase':
            obj = get_object_or_404(EvaluationPhase, id=item['id'])
        else:  # milestone
            obj = get_object_or_404(ProjectMilestone, id=item['id'])
            
        obj.order = item['order']
        obj.save()
    
    return JsonResponse({'success': True})

class ProjectTimelineView(View):
    """View for project timeline section"""
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        """Handle GET requests for project timeline"""
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)

        # Prepare timeline data
        tasks = []
        for phase in project.phases.all():
            start_date_str = phase.start_date.strftime('%Y-%m-%d') if phase.start_date else None
            end_date_str = phase.end_date.strftime('%Y-%m-%d') if phase.end_date else None
            if start_date_str and end_date_str:
                tasks.append({
                    'id': f'phase-{phase.id}',
                    'name': phase.get_phase_type_display(),
                    'start': start_date_str,
                    'end': end_date_str,
                    'progress': 100 if phase.completed else 0,
                    'dependencies': ''
                })
        for milestone in project.milestones.all():
            if milestone.due_date:
                due_date = milestone.due_date
                tasks.append({
                    'id': f'milestone-{milestone.id}',
                    'name': f"★ {milestone.name}",
                    'start': due_date.strftime('%Y-%m-%d'),
                    'end': (due_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                    'progress': 100 if milestone.status == 'completed' else 0,
                    'dependencies': '',
                    'custom_class': 'milestone',
                    'milestone': True
                })
        gantt_chart = self._generate_gantt_chart(tasks) if tasks else '<div class="alert alert-info">No phases or milestones with valid dates defined for this project to generate a timeline.</div>'

        context = {
            'project': project,
            'current_view': 'timeline',
            'phases': project.phases.all(),
            'milestones': project.milestones.all(),
            'gantt_chart': gantt_chart
        }

        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/timeline_content.html', context)
        return render(request, self.template_name, context)

    def post(self, request, project_id):
        """Handle timeline operations (phases and milestones)"""
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        
        # Handle AJAX status updates
        if 'update_phase_status' in request.POST:
            try:
                phase = EvaluationPhase.objects.get(
                    pk=request.POST.get('phase_id'),
                    project_id=project_id
                )
                phase.completed = request.POST.get('status') == 'completed'
                phase.save()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
                
        elif 'update_milestone_status' in request.POST:
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.status = request.POST.get('status')
                milestone.save()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
                
        elif 'update_timeline_order' in request.POST:
            try:
                items = json.loads(request.POST.get('items', '[]'))
                for item in items:
                    if item['type'] == 'phase':
                        obj = EvaluationPhase.objects.get(pk=item['id'], project_id=project_id)
                    else:  # milestone
                        obj = ProjectMilestone.objects.get(pk=item['id'], project_id=project_id)
                    obj.order = item['order']
                    obj.save()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
        # Existing CRUD operations below...
        if request.POST.get('_method') == 'DELETE' and request.POST.get('phase_id'):
            try:
                phase = EvaluationPhase.objects.get(
                    pk=request.POST.get('phase_id'),
                    project_id=project_id
                )
                phase.delete()
                if request.headers.get('HX-Request'):
                    context = self._get_timeline_context(project)
                    response = render(request, 'research_dashboard/partials/timeline_content.html', context)
                    response['HX-Redirect'] = request.path_info
                    return response
                messages.success(request, 'Phase deleted successfully!')
                return redirect('project_timeline', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error deleting phase: {str(e)}')
            return redirect('project_timeline', project_id=project_id)
            
        elif 'phase_type' in request.POST:
            try:
                if request.POST.get('phase_id'):
                    return self._handle_phase_update(request, project_id)
                else:
                    phase = EvaluationPhase.objects.create(
                        project=project,
                        phase_type=request.POST.get('phase_type'),
                        start_date=request.POST.get('start_date'),
                        end_date=request.POST.get('end_date'),
                        notes=request.POST.get('notes')
                    )
                    if request.headers.get('HX-Request'):
                        context = self._get_timeline_context(project)
                        response = render(request, 'research_dashboard/partials/timeline_content.html', context)
                        response['HX-Redirect'] = request.path_info
                        return response
                    messages.success(request, 'Phase added successfully!')
                    return redirect('project_timeline', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error modifying phase: {str(e)}')
            return redirect('project_timeline', project_id=project_id)

        # Milestone CRUD operations
        elif 'add_milestone' in request.POST:
            try:
                milestone = ProjectMilestone.objects.create(
                    project=project,
                    name=request.POST.get('name'),
                    due_date=request.POST.get('due_date'),
                    description=request.POST.get('description')
                )
                if request.headers.get('HX-Request'):
                    context = self._get_timeline_context(project)
                    response = render(request, 'research_dashboard/partials/timeline_content.html', context)
                    response['HX-Redirect'] = request.path_info
                    return response
                messages.success(request, 'Milestone added successfully!')
                return redirect('project_timeline', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error adding milestone: {str(e)}')
            return redirect('project_timeline', project_id=project_id)

        elif 'update_milestone' in request.POST:
            try:
                from django.utils import timezone
                from datetime import datetime
                
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.name = request.POST.get('name')
                due_date_str = request.POST.get('due_date')
                milestone.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                milestone.description = request.POST.get('description')
                milestone.save()
                if request.headers.get('HX-Request'):
                    context = self._get_timeline_context(project)
                    response = render(request, 'research_dashboard/partials/timeline_content.html', context)
                    response['HX-Redirect'] = request.path_info
                    return response
                messages.success(request, 'Milestone updated successfully!')
                return redirect('project_timeline', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error updating milestone: {str(e)}')
            return redirect('project_timeline', project_id=project_id)

        elif request.POST.get('_method') == 'DELETE' and request.POST.get('milestone_id'):
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.delete()
                if request.headers.get('HX-Request'):
                    context = self._get_timeline_context(project)
                    response = render(request, 'research_dashboard/partials/timeline_content.html', context)
                    response['HX-Redirect'] = request.path_info
                    return response
                messages.success(request, 'Milestone deleted successfully!')
                return redirect('project_timeline', project_id=project_id)
            except Exception as e:
                messages.error(request, 'Error deleting milestone: {str(e)}')
            return redirect('project_timeline', project_id=project_id)

    def _get_timeline_context(self, project):
        """Get context for timeline view"""
        tasks = self._prepare_tasks_data(project)
        gantt_chart = self._generate_gantt_chart(tasks) if tasks else '<div class="alert alert-info">No timeline data</div>'
        
        return {
            'project': project,
            'phases': project.phases.all(),
            'milestones': project.milestones.all(),
            'gantt_chart': gantt_chart
        }

    def _handle_phase_update(self, request, project_id):
        """Handle phase update (internal method)"""
        phase = EvaluationPhase.objects.get(
            pk=request.POST.get('phase_id'),
            project_id=project_id
        )
        phase.phase_type = request.POST.get('phase_type')
        phase.start_date = request.POST.get('start_date')
        phase.end_date = request.POST.get('end_date')
        phase.notes = request.POST.get('notes')
        phase.completed = 'completed' in request.POST
        phase.save()
        messages.success(request, 'Phase updated successfully!')
        return redirect('project_timeline', project_id=project_id)

    def _prepare_tasks_data(self, project):
        """Prepare tasks data for Gantt chart visualization"""
        tasks = []
        for phase in project.phases.order_by('order'):
            tasks.append({
                'id': f'phase-{phase.id}',
                'name': phase.get_phase_type_display(),
                'start': phase.start_date.strftime('%Y-%m-%d'),
                'end': phase.end_date.strftime('%Y-%m-%d'),
                'progress': 100 if phase.completed else 0,
                'dependencies': ''
            })
        for milestone in project.milestones.order_by('order'):
            tasks.append({
                'id': f'milestone-{milestone.id}',
                'name': milestone.name,
                'start': milestone.due_date.strftime('%Y-%m-%d'),
                'end': milestone.due_date.strftime('%Y-%m-%d'),
                'progress': 100 if milestone.status == 'completed' else 0,
                'dependencies': '',
                'custom_class': 'milestone'
            })
        return tasks

    def _generate_gantt_chart(self, tasks):
        """Generate Gantt chart HTML from tasks data"""
        try:
            import plotly.graph_objects as go
            from plotly.offline import plot
            import pandas as pd
            from datetime import datetime

            # Create a DataFrame from the tasks data
            df = pd.DataFrame(tasks)

            # Convert date strings to datetime objects
            df['start'] = pd.to_datetime(df['start'])
            df['end'] = pd.to_datetime(df['end'])

            # Calculate duration in days for each task
            df['duration'] = (df['end'] - df['start']).dt.days

            # Add text column for the labels
            df['text'] = df.apply(lambda row: f"{row['name']} ({row['duration']} days)", axis=1)

            # Add progress to custom data
            df['progress'] = [task['progress'] for task in tasks]

            # Identify phases and milestones
            df['is_milestone'] = df['id'].str.startswith('milestone-')

            # Sort everything chronologically by start date
            df = df.sort_values("start")

            # Get today's date for overdue checking
            today = datetime.now()

            # Create a figure
            fig = go.Figure()

            # Add phases as horizontal bars
            for _, row in df[~df['is_milestone']].iterrows():
                # Choose color based on progress and date
                if row['progress'] == 100:
                    color = '#22c55e'  # Green for completed
                elif row['end'] < today and row['progress'] < 100:
                    color = '#ef4444'  # Red for overdue
                else:
                    color = '#4361EE'  # Blue for in progress and not overdue
                
                fig.add_trace(go.Scatter(
                    x=[row['start'], row['end']],
                    y=[row['name'], row['name']],
                    mode='lines',
                    line=dict(color=color, width=20),
                    name=row['name'],
                    text=row['text'],
                    hoverinfo='text',
                hovertext=(
                    f"<b>{row['name']}</b><br>" +
                    f"Start: {row['start'].strftime('%b %d, %Y')}<br>" +
                    f"End: {row['end'].strftime('%b %d, %Y')}<br>" +
                    f"Duration: {row['duration']} days<br>" +
                    f"Status: " + 
                    ("Completed" if row['progress'] == 100 else
                     f"⚠️ OVERDUE by {(today - row['end']).days} day{'s' if (today - row['end']).days != 1 else ''}" 
                     if row['end'] < today and row['progress'] < 100 else
                     f"{row['progress']}% Complete" + 
                     (f" ({(row['end'] - today).days} day{'s' if (row['end'] - today).days != 1 else ''} remaining)" 
                      if row['end'] > today else ""))
                ),
                    showlegend=False
                ))
                
                # Calculate the midpoint timestamp properly
                mid_timestamp = row['start'] + (row['end'] - row['start'])/2
                
                # Add text labels on the bars
                fig.add_annotation(
                    x=mid_timestamp,
                    y=row['name'],
                    text=row['text'],
                    showarrow=False,
                    font=dict(color='white', size=12, family='Arial'),
                    xanchor="center"
                )

            # Add milestones as diamond markers
            for _, row in df[df['is_milestone']].iterrows():
                # Choose color based on progress and date
                if row['progress'] == 100:
                    color = '#22c55e'  # Green for completed
                elif row['start'] < today and row['progress'] < 100:
                    color = '#ef4444'  # Red for overdue
                else:
                    color = '#4361EE'  # Blue for in progress and not overdue
                
                fig.add_trace(go.Scatter(
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
                    hovertext=(
                        f"<b>{row['name']}</b><br>" +
                        f"Date: {row['start'].strftime('%b %d, %Y')}<br>" +
                        f"Status: {row['progress']}% complete" +
                        (f"<br>⚠️ OVERDUE" if row['start'] < today and row['progress'] < 100 else "")
                    ),
                    showlegend=False
                ))

            # Update the layout for a sleek, modern look
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
                    autorange="reversed",  # This keeps the chronological order top-to-bottom
                    showgrid=False,
                    showline=False,
                    zeroline=False,
                    tickfont=dict(family="Arial, sans-serif", size=12),
                    categoryorder='array',
                    categoryarray=df['name'].tolist()  # This ensures the order matches our sorted dataframe
                ),
                plot_bgcolor='white',
                paper_bgcolor='white',
                height=max(400, len(df)-4 * 40),  # Dynamic height based on number of items
                margin=dict(l=120, r=30, b=50, t=70, pad=10),
                hoverlabel=dict(
                    bgcolor="white",
                    font_size=12,
                    font_family="Arial, sans-serif"
                ),
                showlegend=False
            )

            # Add subtle horizontal grid lines for better readability
            unique_names = df['name'].unique()
            for i, name in enumerate(unique_names):
                fig.add_shape(
                    type="line",
                    x0=df['start'].min(),
                    x1=df['end'].max(),
                    y0=name,
                    y1=name,
                    line=dict(color="#F5F5F5", width=1),
                    layer="below"
                )

            # Add today marker as a shape
            fig.add_shape(
                type="line",
                x0=today,
                x1=today,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(
                    color="#FF4136",
                    width=2,
                    dash="dash"
                )
            )

            # Add "Today" label
            fig.add_annotation(
                x=today,
                y=1,
                yref="paper",
                text="Today",
                showarrow=False,
                font=dict(
                    color="#FF4136",
                    size=12
                ),
                xanchor="center",
                yanchor="bottom"
            )

            # Add a color legend
            fig.add_annotation(
                x=1.0,
                y=-0.12,
                xref="paper",
                yref="paper",
                text="<span style='color:#22c55e;'>■</span> Completed &nbsp; <span style='color:#4361EE;'>■</span> In Progress &nbsp; <span style='color:#ef4444;'>■</span> Overdue",
                showarrow=False,
                font=dict(size=12, family="Arial"),
                align="right",
                xanchor="right",
                yanchor="top"
            )

            # Generate the HTML
            return plot(fig, output_type='div', include_plotlyjs='cdn', config={
                'displayModeBar': False,
                'responsive': True
            })
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return f'<div class="alert alert-danger">Error generating Gantt chart: {str(e)}<br><pre>{error_details}</pre></div>'

    

class ProjectMetricsView(View):
    """View for project metrics section"""
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        """Handle GET requests for project metrics"""
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)

        context = {
            'project': project,
            'current_view': 'metrics',
            'metrics': project.metrics.all(),
            'metric_form': MetricForm(initial={'project': project}),
        }

        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/metrics_content.html', context)
        return render(request, self.template_name, context)

    def post(self, request, project_id):
        """Handle metric submissions"""
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        form = MetricForm(request.POST)
        if form.is_valid():
            metric = form.save(commit=False)
            metric.project = project
            metric.save()
            if request.headers.get('HX-Request'):
                context = {
                    'project': project,
                    'metrics': project.metrics.all(),
                    'metric_form': MetricForm(initial={'project': project})
                }
                return render(request, 'research_dashboard/partials/metrics_content.html', context)
            return redirect('project_metrics', project_id=project.id)
        else:
            context = {
                'project': project,
                'current_view': 'metrics',
                'metrics': project.metrics.all(),
                'metric_form': form,
            }
            if request.headers.get('HX-Request'):
                return render(request, 'research_dashboard/partials/metrics_content.html', context)
            return render(request, self.template_name, context)
    
    # The rest of the class remains the same (post method, helper methods, etc.)
    # ...
    
    def post(self, request, project_id):
        # Verify project ownership
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        
        if 'document_submit' in request.POST:
            form = DocumentUploadForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.project = project
                document.save()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'documents': project.documents.all(),
                        'document_form': DocumentUploadForm()
                    }
                    return render(request, 'research_dashboard/partials/overview_content.html', context)
                
                # Get current view from POST data or default to 'overview'
                current_view = request.POST.get('current_view', 'overview')
                if current_view == 'overview':
                    return redirect('project_detail', project_id=project.id)
                elif current_view == 'timeline':
                    return redirect('project_timeline', project_id=project.id)
                elif current_view == 'metrics':
                    return redirect('project_metrics', project_id=project.id)
                else:
                    return redirect('project_detail', project_id=project.id)
            else:
                # Handle invalid form - get current view from POST data
                current_view = request.POST.get('current_view', 'overview')
                context = {
                    'project': project,
                    'current_view': current_view,
                    'documents': project.documents.all(),
                    'document_form': form,
                    'metric_form': MetricForm(initial={'project': project}),
                    'phases': project.phases.all(),
                    'milestones': project.milestones.all(),
                    'metrics': project.metrics.all()
                }
                
                # Return the appropriate view based on current_view
                if current_view == 'overview':
                    return render(request, 'research_dashboard/partials/overview_content.html', context)
                elif current_view == 'timeline':
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                elif current_view == 'metrics':
                    return render(request, 'research_dashboard/partials/metrics_content.html', context)
                else:
                    return render(request, 'research_dashboard/partials/overview_content.html', context)

        elif 'metric_submit' in request.POST:
            form = MetricForm(request.POST)
            if form.is_valid():
                metric = form.save(commit=False)
                metric.project = project
                metric.save()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'metrics': project.metrics.all(),
                        'metric_form': MetricForm(initial={'project': project})
                    }
                    return render(request, 'research_dashboard/partials/metrics_content.html', context)
                
                # Get current view from POST data or default to 'overview'
                current_view = request.POST.get('current_view', 'overview')
                if current_view == 'overview':
                    return redirect('project_detail', project_id=project.id)
                elif current_view == 'timeline':
                    return redirect('project_timeline', project_id=project.id)
                elif current_view == 'metrics':
                    return redirect('project_metrics', project_id=project.id)
                else:
                    return redirect('project_detail', project_id=project.id)
            else:
                # Handle invalid form - get current view from POST data
                current_view = request.POST.get('current_view', 'overview')
                context = {
                    'project': project,
                    'current_view': current_view,
                    'documents': project.documents.all(),
                    'document_form': DocumentUploadForm(),
                    'metric_form': form,
                    'phases': project.phases.all(),
                    'milestones': project.milestones.all(),
                    'metrics': project.metrics.all()
                }
                
                # Return the appropriate view based on current_view
                if current_view == 'overview':
                    return render(request, 'research_dashboard/partials/overview_content.html', context)
                elif current_view == 'timeline':
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                elif current_view == 'metrics':
                    return render(request, 'research_dashboard/partials/metrics_content.html', context)
                else:
                    return render(request, 'research_dashboard/partials/overview_content.html', context)
                
        elif request.POST.get('_method') == 'DELETE' and request.POST.get('phase_id'):
            try:
                phase = EvaluationPhase.objects.get(
                    pk=request.POST.get('phase_id'),
                    project_id=project_id
                )
                phase.delete()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Phase deleted successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error deleting phase: {str(e)}')
            return redirect('project_detail', project_id=project_id)
            
        elif 'phase_type' in request.POST:
            try:
                if request.POST.get('phase_id'):
                    # Update existing phase
                    phase = EvaluationPhase.objects.get(
                        pk=request.POST.get('phase_id'),
                        project_id=project_id
                    )
                    phase.phase_type = request.POST.get('phase_type')
                    phase.start_date = request.POST.get('start_date')
                    phase.end_date = request.POST.get('end_date')
                    phase.notes = request.POST.get('notes')
                    phase.completed = 'completed' in request.POST
                    phase.save()
                    # Return HTMX partial instead of redirecting
                    if request.headers.get('HX-Request'):
                        context = {
                            'project': project,
                            'phases': project.phases.all(),
                            'milestones': project.milestones.all()
                        }
                        return render(request, 'research_dashboard/partials/timeline_content.html', context)
                    messages.success(request, 'Phase updated successfully!')
                    return redirect('project_detail', project_id=project_id)
                else:
                    # Create new phase
                    phase = EvaluationPhase.objects.create(
                        project=project,
                        phase_type=request.POST.get('phase_type'),
                        start_date=request.POST.get('start_date'),
                        end_date=request.POST.get('end_date'),
                        notes=request.POST.get('notes')
                    )
                    # Return HTMX partial instead of redirecting
                    if request.headers.get('HX-Request'):
                        context = {
                            'project': project,
                            'phases': project.phases.all(),
                            'milestones': project.milestones.all()
                        }
                        return render(request, 'research_dashboard/partials/timeline_content.html', context)
                    messages.success(request, 'Phase added successfully!')
                    return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error modifying phase: {str(e)}')
            return redirect('project_detail', project_id=project_id)
            
        # Milestone CRUD operations
        elif 'add_milestone' in request.POST:
            try:
                milestone = ProjectMilestone.objects.create(
                    project=project,
                    name=request.POST.get('name'),
                    due_date=request.POST.get('due_date'),
                    description=request.POST.get('description')
                )
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Milestone added successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error adding milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        elif 'update_milestone' in request.POST:
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.name = request.POST.get('name')
                # Convert string date to date object
                due_date_str = request.POST.get('due_date')
                milestone.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                milestone.description = request.POST.get('description')
                milestone.save()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Milestone updated successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error updating milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        elif request.POST.get('_method') == 'DELETE' and request.POST.get('milestone_id'):
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.delete()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Milestone deleted successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error deleting milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)
                
        elif request.POST.get('_method') == 'DELETE' and request.POST.get('phase_id'):
            try:
                return self._handle_phase_delete(request, project_id)
            except Exception as e:
                messages.error(request, f'Error deleting phase: {str(e)}')
            return redirect('project_detail', project_id=project_id)
            
        elif 'phase_type' in request.POST:
            try:
                if request.POST.get('phase_id'):
                    return self._handle_phase_update(request, project_id)
                else:
                    phase = EvaluationPhase.objects.create(
                        project=project,
                        phase_type=request.POST.get('phase_type'),
                        start_date=request.POST.get('start_date'),
                        end_date=request.POST.get('end_date'),
                        notes=request.POST.get('notes')
                    )
                    # Return HTMX partial instead of redirecting
                    if request.headers.get('HX-Request'):
                        context = {
                            'project': project,
                            'phases': project.phases.all(),
                            'milestones': project.milestones.all()
                        }
                        return render(request, 'research_dashboard/partials/timeline_content.html', context)
                    messages.success(request, 'Phase added successfully!')
                    return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error modifying phase: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        # Milestone CRUD operations
        elif 'add_milestone' in request.POST:
            try:
                milestone = ProjectMilestone.objects.create(
                    project=project,
                    name=request.POST.get('name'),
                    due_date=request.POST.get('due_date'),
                    description=request.POST.get('description')
                )
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Milestone added successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error adding milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        elif 'update_milestone' in request.POST:
            try:
                from django.utils import timezone
                from datetime import datetime
                
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.name = request.POST.get('name')
                # Convert string date to date object
                due_date_str = request.POST.get('due_date')
                milestone.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                milestone.description = request.POST.get('description')
                milestone.save()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Milestone updated successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, f'Error updating milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        elif 'toggle_milestone' in request.POST:
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                # Toggle status
                milestone.status = 'completed' if milestone.status != 'completed' else 'pending'
                milestone.save()
                
                return JsonResponse({
                    'success': True,
                    'new_status': milestone.status,
                    'status_display': milestone.get_status_display(),
                    'button_class': 'btn-success' if milestone.status == 'completed' else 
                                   'btn-danger' if milestone.status == 'overdue' else 'btn-info'
                })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

        elif request.POST.get('_method') == 'DELETE' and request.POST.get('milestone_id'):
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.delete()
                # Return HTMX partial instead of redirecting
                if request.headers.get('HX-Request'):
                    context = {
                        'project': project,
                        'phases': project.phases.all(),
                        'milestones': project.milestones.all()
                    }
                    return render(request, 'research_dashboard/partials/timeline_content.html', context)
                messages.success(request, 'Milestone deleted successfully!')
                return redirect('project_detail', project_id=project_id)
            except Exception as e:
                messages.error(request, 'Error deleting milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)
        
        # For initial page load or non-HTMX requests, render the main project_detail.html
        return render(request, self.template_name, context)
    
    # The rest of the class remains the same (post method, helper methods, etc.)
    # ...

    def post(self, request, project_id):
        # Verify project ownership
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        
        if 'document_submit' in request.POST:
            form = DocumentUploadForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.project = project
                document.save()
                return redirect('project_detail', project_id=project.id)
            else:
                tasks = self._prepare_tasks_data(project)
                tasks_json = json.dumps(tasks, ensure_ascii=False)
                context = {
                    'project': project,
                    'phases': project.phases.all(),
                    'milestones': project.milestones.all(),
                    'metrics': project.metrics.all(),
                    'documents': project.documents.all(),
                    'document_form': form,
                    'metric_form': MetricForm(initial={'project': project}),
                    'tasks_json': tasks_json
                }
                return render(request, self.template_name, context)

        elif 'metric_submit' in request.POST:
            form = MetricForm(request.POST)
            if form.is_valid():
                metric = form.save(commit=False)
                metric.project = project
                metric.save()
                return redirect('project_detail', project_id=project.id)
                
        elif request.POST.get('_method') == 'DELETE' and request.POST.get('phase_id'):
            try:
                return self._handle_phase_delete(request, project_id)
            except Exception as e:
                messages.error(request, f'Error deleting phase: {str(e)}')
            return redirect('project_detail', project_id=project_id)
        elif 'phase_type' in request.POST:
            try:
                if request.POST.get('phase_id'):
                    return self._handle_phase_update(request, project_id)
                else:
                    EvaluationPhase.objects.create(
                        project=project,
                        phase_type=request.POST.get('phase_type'),
                        start_date=request.POST.get('start_date'),
                        end_date=request.POST.get('end_date'),
                        notes=request.POST.get('notes')
                    )
                    messages.success(request, 'Phase added successfully!')
            except Exception as e:
                messages.error(request, f'Error modifying phase: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        # Milestone CRUD operations
        elif 'add_milestone' in request.POST:
            try:
                ProjectMilestone.objects.create(
                    project=project,
                    name=request.POST.get('name'),
                    due_date=request.POST.get('due_date'),
                    description=request.POST.get('description')
                )
                messages.success(request, 'Milestone added successfully!')
            except Exception as e:
                messages.error(request, f'Error adding milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        elif 'update_milestone' in request.POST:
            try:
                from django.utils import timezone
                from datetime import datetime
                
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.name = request.POST.get('name')
                # Convert string date to date object
                due_date_str = request.POST.get('due_date')
                milestone.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                milestone.description = request.POST.get('description')
                milestone.save()
                messages.success(request, 'Milestone updated successfully!')
            except Exception as e:
                messages.error(request, f'Error updating milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

        elif 'toggle_milestone' in request.POST:
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                # Toggle status
                milestone.status = 'completed' if milestone.status != 'completed' else 'pending'
                milestone.save()
                
                return JsonResponse({
                    'success': True,
                    'new_status': milestone.status,
                    'status_display': milestone.get_status_display(),
                    'button_class': 'btn-success' if milestone.status == 'completed' else 
                                   'btn-danger' if milestone.status == 'overdue' else 'btn-info'
                })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

        elif request.POST.get('_method') == 'DELETE' and request.POST.get('milestone_id'):
            try:
                milestone = ProjectMilestone.objects.get(
                    pk=request.POST.get('milestone_id'),
                    project=project
                )
                milestone.delete()
                messages.success(request, 'Milestone deleted successfully!')
            except Exception as e:
                messages.error(request, 'Error deleting milestone: {str(e)}')
            return redirect('project_detail', project_id=project_id)

    def _handle_phase_update(self, request, project_id):
        """Handle phase update (internal method)"""
        phase = EvaluationPhase.objects.get(
            pk=request.POST.get('phase_id'),
            project_id=project_id
        )
        phase.phase_type = request.POST.get('phase_type')
        phase.start_date = request.POST.get('start_date')
        phase.end_date = request.POST.get('end_date')
        phase.notes = request.POST.get('notes')
        phase.completed = 'completed' in request.POST
        phase.save()
        messages.success(request, 'Phase updated successfully!')
        return redirect('project_detail', project_id=project_id)

    def _handle_phase_delete(self, request, project_id):
        """Handle phase deletion (internal method)"""
        phase = EvaluationPhase.objects.get(
            pk=request.POST.get('phase_id'),
            project_id=project_id
        )
        phase.delete()
        messages.success(request, 'Phase deleted successfully!')
        return redirect('project_detail', project_id=project_id)   
        

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

    def _generate_gantt_chart(self, tasks):
        """Generate Gantt chart HTML from tasks data"""
        try:
            import plotly.graph_objects as go
            from plotly.offline import plot
            import pandas as pd
            from datetime import datetime

            # Create a DataFrame from the tasks data
            df = pd.DataFrame(tasks)

            # Convert date strings to datetime objects
            df['start'] = pd.to_datetime(df['start'])
            df['end'] = pd.to_datetime(df['end'])

            # Calculate duration in days for each task
            df['duration'] = (df['end'] - df['start']).dt.days

            # Add text column for the labels
            df['text'] = df.apply(lambda row: f"{row['name']} ({row['duration']} days)", axis=1)

            # Add progress to custom data
            df['progress'] = [task['progress'] for task in tasks]

            # Identify phases and milestones
            df['is_milestone'] = df['id'].str.startswith('milestone-')

            # Sort everything chronologically by start date
            df = df.sort_values("start")

            # Get today's date for overdue checking
            today = datetime.now()

            # Create a figure
            fig = go.Figure()

            # Add phases as horizontal bars
            for _, row in df[~df['is_milestone']].iterrows():
                # Choose color based on progress and date
                if row['progress'] == 100:
                    color = '#22c55e'  # Green for completed
                elif row['end'] < today and row['progress'] < 100:
                    color = '#ef4444'  # Red for overdue
                else:
                    color = '#4361EE'  # Blue for in progress and not overdue
                
                fig.add_trace(go.Scatter(
                    x=[row['start'], row['end']],
                    y=[row['name'], row['name']],
                    mode='lines',
                    line=dict(color=color, width=20),
                    name=row['name'],
                    text=row['text'],
                    hoverinfo='text',
                hovertext=(
                    f"<b>{row['name']}</b><br>" +
                    f"Start: {row['start'].strftime('%b %d, %Y')}<br>" +
                    f"End: {row['end'].strftime('%b %d, %Y')}<br>" +
                    f"Duration: {row['duration']} days<br>" +
                    f"Status: " + 
                    ("Completed" if row['progress'] == 100 else
                     f"⚠️ OVERDUE by {(today - row['end']).days} day{'s' if (today - row['end']).days != 1 else ''}" 
                     if row['end'] < today and row['progress'] < 100 else
                     f"{row['progress']}% Complete" + 
                     (f" ({(row['end'] - today).days} day{'s' if (row['end'] - today).days != 1 else ''} remaining)" 
                      if row['end'] > today else ""))
                ),
                    showlegend=False
                ))
                
                # Calculate the midpoint timestamp properly
                mid_timestamp = row['start'] + (row['end'] - row['start'])/2
                
                # Add text labels on the bars
                fig.add_annotation(
                    x=mid_timestamp,
                    y=row['name'],
                    text=row['text'],
                    showarrow=False,
                    font=dict(color='white', size=12, family='Arial'),
                    xanchor="center"
                )

            # Add milestones as diamond markers
            for _, row in df[df['is_milestone']].iterrows():
                # Choose color based on progress and date
                if row['progress'] == 100:
                    color = '#22c55e'  # Green for completed
                elif row['start'] < today and row['progress'] < 100:
                    color = '#ef4444'  # Red for overdue
                else:
                    color = '#4361EE'  # Blue for in progress and not overdue
                
                fig.add_trace(go.Scatter(
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
                    hovertext=(
                        f"<b>{row['name']}</b><br>"
                        f"Date: {row['start'].strftime('%b %d, %Y')}<br>"
                        f"Status: {row['progress']}% complete" +
                        (f"<br>⚠️ OVERDUE" if row['start'] < today and row['progress'] < 100 else "")
                    ),
                    showlegend=False
                ))

            # Update the layout for a sleek, modern look
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
                    autorange="reversed",  # This keeps the chronological order top-to-bottom
                    showgrid=False,
                    showline=False,
                    zeroline=False,
                    tickfont=dict(family="Arial, sans-serif", size=12),
                    categoryorder='array',
                    categoryarray=df['name'].tolist()  # This ensures the order matches our sorted dataframe
                ),
                plot_bgcolor='white',
                paper_bgcolor='white',
                height=max(400, len(df) * 40),  # Dynamic height based on number of items
                margin=dict(l=120, r=30, b=50, t=70, pad=10),
                hoverlabel=dict(
                    bgcolor="white",
                    font_size=12,
                    font_family="Arial, sans-serif"
                ),
                showlegend=False
            )

            # Add subtle horizontal grid lines for better readability
            unique_names = df['name'].unique()
            for i, name in enumerate(unique_names):
                fig.add_shape(
                    type="line",
                    x0=df['start'].min(),
                    x1=df['end'].max(),
                    y0=name,
                    y1=name,
                    line=dict(color="#F5F5F5", width=1),
                    layer="below"
                )

            # Add today marker as a shape
            fig.add_shape(
                type="line",
                x0=today,
                x1=today,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(
                    color="#FF4136",
                    width=2,
                    dash="dash"
                )
            )

            # Add "Today" label
            fig.add_annotation(
                x=today,
                y=1,
                yref="paper",
                text="Today",
                showarrow=False,
                font=dict(
                    color="#FF4136",
                    size=12
                ),
                xanchor="center",
                yanchor="bottom"
            )

            # Add a color legend
            fig.add_annotation(
                x=1.0,
                y=-0.12,
                xref="paper",
                yref="paper",
                text="<span style='color:#22c55e;'>■</span> Completed &nbsp; <span style='color:#4361EE;'>■</span> In Progress &nbsp; <span style='color:#ef4444;'>■</span> Overdue",
                showarrow=False,
                font=dict(size=12, family="Arial"),
                align="right",
                xanchor="right",
                yanchor="top"
            )

            # Generate the HTML
            return plot(fig, output_type='div', include_plotlyjs='cdn', config={
                'displayModeBar': False,
                'responsive': True
            })
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return f'<div class="alert alert-danger">Error generating Gantt chart: {str(e)}<br><pre>{error_details}</pre></div>'

    def _prepare_tasks_data(self, project):
        """Prepare tasks data for Gantt chart visualization"""
        tasks = []
        for phase in project.phases.all():
            tasks.append({
                'id': f'phase-{phase.id}',
                'name': phase.get_phase_type_display(),
                'start': phase.start_date.strftime('%Y-%m-%d'),
                'end': phase.end_date.strftime('%Y-%m-%d'),
                'progress': 100 if phase.completed else 0,
                'dependencies': ''
            })
        for milestone in project.milestones.all():
            tasks.append({
                'id': f'milestone-{milestone.id}',
                'name': milestone.name,
                'start': milestone.due_date.strftime('%Y-%m-%d'),
                'end': milestone.due_date.strftime('%Y-%m-%d'),
                'progress': 100 if milestone.status == 'completed' else 0,
                'dependencies': '',
                'custom_class': 'milestone'
            })
        return tasks

# New views for the added pages
class ProjectHIVServicesView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'hiv_services',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/hiv_services_content.html', context)
        return render(request, self.template_name, context)

class ProjectNCDServicesView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'ncd_services',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/ncd_services_content.html', context)
        return render(request, self.template_name, context)

class ProjectIntegrationView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'integration',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/integration_content.html', context)
        return render(request, self.template_name, context)

class ProjectStockSupplyView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'stock_supply',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/stock_supply_content.html', context)
        return render(request, self.template_name, context)

class ProjectReferralLinkageView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'referral_linkage',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/referral_linkage_content.html', context)
        return render(request, self.template_name, context)

class ProjectDataQualityView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'data_quality',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/data_quality_content.html', context)
        return render(request, self.template_name, context)

class ProjectDisaggregationView(View):
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(ResearchProject, pk=project_id, lead_researcher=request.user)
        context = {
            'project': project,
            'current_view': 'disaggregation',
        }
        if request.headers.get('HX-Request'):
            return render(request, 'research_dashboard/partials/disaggregation_content.html', context)
        return render(request, self.template_name, context)
