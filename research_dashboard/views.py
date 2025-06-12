from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.edit import DeleteView, UpdateView
from django.urls import reverse_lazy
from django.http import HttpResponse, FileResponse, JsonResponse
from django.contrib import messages
from django.db.models import Count, Q
from .models import ResearchProject, EvaluationPhase, ProjectMilestone, ResearchDocument, Evaluator, Evaluation
from .forms import DocumentUploadForm, MetricForm, ResearchProjectForm, EvaluatorForm, EvaluationForm
from datetime import timedelta
import json
import mimetypes
import os

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

class LandingPageView(TemplateView):
    """
    Renders the public-facing landing page.
    
    This view uses Django's generic TemplateView, which simplifies the process
    of displaying a static template. We just need to specify the template_name.
    """
    template_name = 'research_dashboard/landing_page.html'

class AboutView(View):
    """View for about page"""
    template_name = 'research_dashboard/about.html'

    def get(self, request):
        """Handle GET requests for about page"""
        context = {
            'user': request.user
        }
        return render(request, self.template_name, context)

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

class DashboardView(View):
    """View for research project dashboard"""
    template_name = 'research_dashboard/dashboard.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request):
        """Display dashboard with project statistics"""
        status_filter = request.GET.get('status')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        sort = request.GET.get('sort')
        order = request.GET.get('order')
        print(f"Debug - Active filters - status: {status_filter}, date_from: {date_from}, date_to: {date_to}")  # Debug output
        
        projects = ResearchProject.objects.all()
        
        # Apply status filter if specified
        if status_filter:
            projects = projects.filter(status=status_filter)
            
        # Apply date range filter if specified
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

        for project in projects:
            from django.utils import timezone
            today = timezone.now().date()
            
            if project.end_date and project.start_date:
                total_days = (project.end_date - project.start_date).days
                elapsed_days = (today - project.start_date).days
                
                if elapsed_days <= 0:
                    project.completion_percent = 0  # Project hasn't started yet
                elif elapsed_days >= total_days:
                    project.completion_percent = 100  # Project should be completed
                else:
                    project.completion_percent = int((elapsed_days / total_days) * 100)
            else:
                # Fallback to milestone-based calculation if dates aren't set
                if project.total_milestones > 0:
                    project.completion_percent = int((project.completed_milestones / project.total_milestones) * 100)
                else:
                    project.completion_percent = 0

        # Calculate status counts
        status_counts = {
            'active': ResearchProject.objects.filter(status='active').count(),
            'completed': ResearchProject.objects.filter(status='completed').count(),
            'on_hold': ResearchProject.objects.filter(status='on_hold').count(),
            'planned': ResearchProject.objects.filter(status='planned').count(),
            'cancelled': ResearchProject.objects.filter(status='cancelled').count(),
        }

        from django.core.paginator import Paginator
        print(f"Debug - Total projects before pagination: {projects.count()}")  # Debug output
        paginator = Paginator(projects, 10)  # Show 10 projects per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        print(f"Debug - Page {page_obj.number} of {paginator.num_pages}")  # Debug output

        context = {
            'page_obj': page_obj,
            'status_counts': status_counts,
            'status_filter': status_filter or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
            'status_options': ResearchProject.PROJECT_STATUS,
            'total_projects_count': ResearchProject.objects.count()
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if request.POST.get('_method') == 'DELETE':
            return self._handle_delete(request)
            
        project_id = request.POST.get('project_id')
        try:
            if project_id:
                # Update existing project
                project = ResearchProject.objects.get(pk=project_id)
                project.title = request.POST.get('title')
                project.description = request.POST.get('description')
                project.status = request.POST.get('status')
                project.start_date = request.POST.get('start_date')
                project.end_date = request.POST.get('end_date') or None
                project.save()
                messages.success(request, 'Evaluation updated successfully!')
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
                messages.success(request, 'Evaluation created successfully!')
        except Exception as e:
            messages.error(request, f'Error creating evaluation: {str(e)}')
        return redirect('dashboard')

    def _handle_delete(self, request):
        """Handle project deletion (internal method)"""
        project_id = request.POST.get('project_id')
        try:
            project = ResearchProject.objects.get(pk=project_id)
            project.delete()
            messages.success(request, 'Evaluation deleted successfully!')
        except ResearchProject.DoesNotExist:
            messages.error(request, 'Project not found')
        except Exception as e:
            messages.error(request, f'Error deleting evaluation: {str(e)}')
        return redirect('dashboard')

class ProjectDetailView(View):
    """View for displaying and managing individual project details"""
    template_name = 'research_dashboard/project_detail.html'
    
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, project_id=None, document_id=None):
        """Handle GET requests for project detail or document viewing"""
        if document_id:
            return self.view_document(request, document_id)
        
        # Original project detail view logic
        project = ResearchProject.objects.prefetch_related(
            'phases', 'milestones', 'metrics', 'documents'
        ).get(pk=project_id)

        # Prepare tasks data for Gantt chart
        tasks = []
        # Add all phases first
        for phase in project.phases.all():
             # Ensure dates are not None before formatting
            start_date_str = phase.start_date.strftime('%Y-%m-%d') if phase.start_date else None
            end_date_str = phase.end_date.strftime('%Y-%m-%d') if phase.end_date else None
            if start_date_str and end_date_str: # Only add if both dates exist
                tasks.append({
                    'id': f'phase-{phase.id}',
                    'name': phase.get_phase_type_display(),
                    'start': phase.start_date.strftime('%Y-%m-%d'),
                    'end': phase.end_date.strftime('%Y-%m-%d'),
                    'progress': 100 if phase.completed else 0,
                    'dependencies': ''
                })
        
        # Add all milestones second
        for milestone in project.milestones.all():
            if milestone.due_date:
                due_date = milestone.due_date
                tasks.append({
                    'id': f'milestone-{milestone.id}',
                    'name': f"★ {milestone.name}",  # Star prefix for visual distinction
                    'start': due_date.strftime('%Y-%m-%d'),
                    'end': (due_date + timedelta(days=1)).strftime('%Y-%m-%d'), 
                    'progress': 100 if milestone.status == 'completed' else 0,
                    'dependencies': '',
                    'custom_class': 'milestone',
                    'milestone': True
                })

        metrics = project.metrics.all()
        tasks_json = json.dumps(tasks, ensure_ascii=False)
        gantt_chart = None # Initialize gantt_chart variable
        has_tasks = bool(tasks) # Check if the tasks list is populated
        
        if has_tasks:
            gantt_chart = self._generate_gantt_chart(tasks)
        else: # If not has_tasks
            gantt_chart = '<div class="alert alert-info">No phases or milestones with valid dates defined for this project to generate a timeline.</div>'
        context = {
            'project': project,
            'phases': project.phases.all(),
            'milestones': project.milestones.all(),
            'metrics': metrics,
            'metrics_json': json.dumps([{
                'date_recorded': m.date_recorded.strftime('%Y-%m-%d'),
                'value': m.value
            } for m in metrics]),
            'documents': project.documents.all(),
            'document_form': DocumentUploadForm(),
            'metric_form': MetricForm(initial={'project': project}),
            'gantt_chart': gantt_chart
        }
        return render(request, self.template_name, context)    

    def post(self, request, project_id):
        project = ResearchProject.objects.get(pk=project_id)
        
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
                'progress': 100 if phase.completed else 50,
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

class EvaluatorListView(View):
    """View for listing and managing research evaluators"""
    template_name = 'research_dashboard/evaluators.html'

    def get(self, request):
        """Display all evaluators with their assigned projects and add form"""
        evaluators = Evaluator.objects.prefetch_related('projects').all()
        projects = ResearchProject.objects.all()
        form = EvaluatorForm()
        context = {
            'evaluators': evaluators,
            'form': form,
            'projects': projects
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Handle new evaluator creation"""
        form = EvaluatorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Evaluator added successfully!')
            return redirect('evaluators')
        
        # If form is invalid, show errors
        evaluators = Evaluator.objects.prefetch_related('projects').all()
        context = {
            'evaluators': evaluators,
            'form': form
        }
        return render(request, self.template_name, context)

    def delete(self, request, evaluator_id):
        """Handle evaluator deletion"""
        evaluator = get_object_or_404(Evaluator, pk=evaluator_id)
        evaluator.delete()
        messages.success(request, 'Evaluator deleted successfully!')
        return redirect('evaluators')

    def update(self, request, evaluator_id):
        """Handle evaluator updates"""
        evaluator = get_object_or_404(Evaluator, pk=evaluator_id)
        if request.method == 'POST':
            form = EvaluatorForm(request.POST, instance=evaluator)
            if form.is_valid():
                form.save()
                messages.success(request, 'Evaluator updated successfully!')
                return redirect('evaluators')
        else:
            form = EvaluatorForm(instance=evaluator)
        
        evaluators = Evaluator.objects.prefetch_related('projects').all()
        context = {
            'evaluators': evaluators,
            'form': form,
            'editing': True,
            'edit_id': evaluator_id
        }
        return render(request, self.template_name, context)

class EvaluatorDeleteView(DeleteView):
    model = Evaluator
    success_url = reverse_lazy('evaluators')
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(request, 'Evaluator deleted successfully!')
        return JsonResponse({'status': 'success'})

class EvaluatorUpdateView(UpdateView):
    model = Evaluator
    form_class = EvaluatorForm
    template_name = 'research_dashboard/evaluators.html'
    success_url = reverse_lazy('evaluators')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['evaluators'] = Evaluator.objects.prefetch_related('projects').all()
        context['editing'] = True
        return context

class EvaluationView(View):
    """View for managing research evaluations"""
    template_name = 'research_dashboard/evaluations.html'

    def get(self, request):
        """Display all evaluations with status counts"""
        evaluations = Evaluation.objects.select_related('project').all()
        active_evaluations = evaluations.exclude(phase='completed')
        
        # Calculate status counts
        status_counts = {
            'planning': evaluations.filter(phase='planning').count(),
            'data_collection': evaluations.filter(phase='data_collection').count(),
            'analysis': evaluations.filter(phase='analysis').count(),
            'reporting': evaluations.filter(phase='reporting').count(),
            'completed': evaluations.filter(phase='completed').count(),
        }

        context = {
            'active_evaluations': active_evaluations,
            'planning_count': status_counts['planning'],
            'data_collection_count': status_counts['data_collection'],
            'analysis_count': status_counts['analysis'],
            'completed_count': status_counts['completed'],
            'projects': ResearchProject.objects.all()
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Handle new evaluation creation"""
        form = EvaluationForm(request.POST)
        if form.is_valid():
            evaluation = form.save()
            messages.success(request, 'Evaluation created successfully!')
            return redirect('evaluations')
        
        # If form is invalid, show errors
        evaluations = Evaluation.objects.select_related('project').all()
        context = {
            'active_evaluations': evaluations.exclude(phase='completed'),
            'planning_count': evaluations.filter(phase='planning').count(),
            'data_collection_count': evaluations.filter(phase='data_collection').count(),
            'analysis_count': evaluations.filter(phase='analysis').count(),
            'completed_count': evaluations.filter(phase='completed').count(),
            'projects': ResearchProject.objects.all(),
            'form': form
        }
        return render(request, self.template_name, context)

class EvaluationDetailView(View):
    """View for displaying evaluation details"""
    template_name = 'research_dashboard/evaluation_detail.html'

    def get(self, request, evaluation_id):
        evaluation = get_object_or_404(Evaluation.objects.select_related('project'), pk=evaluation_id)
        context = {
            'evaluation': evaluation,
            'project': evaluation.project
        }
        return render(request, self.template_name, context)

class EvaluationUpdateView(UpdateView):
    """View for updating evaluations"""
    model = Evaluation
    form_class = EvaluationForm
    template_name = 'research_dashboard/evaluation_form.html'

    def get_success_url(self):
        messages.success(self.request, 'Evaluation updated successfully!')
        return reverse_lazy('evaluations')
