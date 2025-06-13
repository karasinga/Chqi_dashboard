from django.urls import path
from .views import DashboardView, ProjectOverviewView, ProjectTimelineView, ProjectMetricsView
from .views import AboutView, LandingPageView, EvaluatorListView, EvaluatorUpdateView
from .views import EvaluatorDeleteView, EvaluationView, EvaluationDetailView, EvaluationUpdateView
from .views import update_phase_status, update_milestone_status, update_timeline_order
from .views import ProjectHIVServicesView, ProjectNCDServicesView, ProjectIntegrationView
from .views import ProjectStockSupplyView, ProjectReferralLinkageView, ProjectDataQualityView
from .views import ProjectDisaggregationView
from django.contrib.auth.views import LogoutView  # Add logout view

urlpatterns = [
    path('logout/', LogoutView.as_view(), name='logout'),  # Add logout URL
    path('', LandingPageView.as_view(), name='landing_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('project/<int:project_id>/overview/', ProjectOverviewView.as_view(), name='project_overview'),
    path('project/<int:project_id>/timeline/', ProjectTimelineView.as_view(), name='project_timeline'),
    path('update_phase_status/<int:phase_id>/', update_phase_status, name='update_phase_status'),
    path('update_milestone_status/<int:milestone_id>/', update_milestone_status, name='update_milestone_status'),
    path('update_timeline_order/', update_timeline_order, name='update_timeline_order'),
    path('project/<int:project_id>/metrics/', ProjectMetricsView.as_view(), name='project_metrics'),
    path('project/<int:project_id>/hiv_services/', ProjectHIVServicesView.as_view(), name='project_hiv_services'),
    path('project/<int:project_id>/ncd_services/', ProjectNCDServicesView.as_view(), name='project_ncd_services'),
    path('project/<int:project_id>/integration/', ProjectIntegrationView.as_view(), name='project_integration'),
    path('project/<int:project_id>/stock_supply/', ProjectStockSupplyView.as_view(), name='project_stock_supply'),
    path('project/<int:project_id>/referral_linkage/', ProjectReferralLinkageView.as_view(), name='project_referral_linkage'),
    path('project/<int:project_id>/data_quality/', ProjectDataQualityView.as_view(), name='project_data_quality'),
    path('project/<int:project_id>/disaggregation/', ProjectDisaggregationView.as_view(), name='project_disaggregation'),
    path('project/<int:project_id>/download/<int:document_id>/', 
         ProjectOverviewView.as_view(), name='download_document'),
    path('about/', AboutView.as_view(), name='about'),
    path('evaluators/', EvaluatorListView.as_view(), name='evaluators'),
    path('evaluators/<int:pk>/delete/', EvaluatorDeleteView.as_view(), name='delete_evaluator'),
    path('evaluators/<int:pk>/edit/', EvaluatorUpdateView.as_view(), name='edit_evaluator'),
    path('evaluations/', EvaluationView.as_view(), name='evaluations'),
    path('evaluations/create/', EvaluationView.as_view(), name='create_evaluation'),
    path('evaluations/<int:evaluation_id>/', EvaluationDetailView.as_view(), name='evaluation_detail'),
    path('evaluations/<int:pk>/edit/', EvaluationUpdateView.as_view(), name='edit_evaluation'),
]
