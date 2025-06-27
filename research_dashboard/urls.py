from django.urls import path
from .views import DashboardView, ProjectOverviewView, ProjectTimelineView
from .views import AboutView, LandingPageView, EvaluatorListView, EvaluatorUpdateView
from .views import EvaluatorDeleteView, EvaluationView, EvaluationDetailView, EvaluationUpdateView
from .views import update_phase_status, update_milestone_status, update_timeline_order
from .views import ProjectServiceDeliveryView, ProjectHealthProductsTechnologiesView, ProjectHumanResourceForHealthView
from .views import ProjectHealthInfoSystemsView, ProjectHealthFinancingView, ProjectDataQualityView
from .views import ProjectLeadershipGovernanceView, county_boundaries_api
from django.contrib.auth.views import LogoutView  # Add logout view

urlpatterns = [
    path('logout/', LogoutView.as_view(), name='logout'),  # Add logout URL
    path('', LandingPageView.as_view(), name='landing_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('project/<int:project_id>/overview/', ProjectOverviewView.as_view(), name='project_overview'),
    path('project/<int:project_id>/', ProjectOverviewView.as_view(), name='project_detail'),
    path('project/<int:project_id>/timeline/', ProjectTimelineView.as_view(), name='project_timeline'),
    path('update_phase_status/<int:phase_id>/', update_phase_status, name='update_phase_status'),
    path('update_milestone_status/<int:milestone_id>/', update_milestone_status, name='update_milestone_status'),
    path('update_timeline_order/', update_timeline_order, name='update_timeline_order'),
    path('project/<int:project_id>/service_delivery/', ProjectServiceDeliveryView.as_view(), name='project_service_delivery'),
    path('project/<int:project_id>/health_products_and_technologies/', ProjectHealthProductsTechnologiesView.as_view(), name='project_health_products_technologies'),
    path('project/<int:project_id>/human_resource_for_health/', ProjectHumanResourceForHealthView.as_view(), name='project_human_resource_for_health'),
    path('project/<int:project_id>/health_info_systems/', ProjectHealthInfoSystemsView.as_view(), name='project_health_info_systems'),
    path('project/<int:project_id>/health_financing/', ProjectHealthFinancingView.as_view(), name='project_health_financing'),
    path('project/<int:project_id>/leadership_governance/', ProjectLeadershipGovernanceView.as_view(), name='project_leadership_governance'),
    path('project/<int:project_id>/data_quality/', ProjectDataQualityView.as_view(), name='project_data_quality'),
    path('project/<int:project_id>/download/<int:document_id>/', 
         ProjectOverviewView.as_view(), name='download_document'),
    path('api/county-boundaries/', county_boundaries_api, name='api_county_boundaries'),
    path('about/', AboutView.as_view(), name='about'),
    path('evaluators/', EvaluatorListView.as_view(), name='evaluators'),
    path('evaluators/<int:pk>/delete/', EvaluatorDeleteView.as_view(), name='delete_evaluator'),
    path('evaluators/<int:pk>/edit/', EvaluatorUpdateView.as_view(), name='edit_evaluator'),
    path('evaluations/', EvaluationView.as_view(), name='evaluations'),
    path('evaluations/create/', EvaluationView.as_view(), name='create_evaluation'),
    path('evaluations/<int:evaluation_id>/', EvaluationDetailView.as_view(), name='evaluation_detail'),
    path('evaluations/<int:pk>/edit/', EvaluationUpdateView.as_view(), name='edit_evaluation'),
]
