from django.urls import path
from .views import (DashboardView, ProjectDetailView, AboutView, LandingPageView,
                   EvaluatorListView, EvaluatorUpdateView, EvaluatorDeleteView,
                   EvaluationView, EvaluationDetailView, EvaluationUpdateView)

urlpatterns = [
    path('', LandingPageView.as_view(), name='landing_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('project/<int:project_id>/', ProjectDetailView.as_view(), name='project_detail'),
    path('project/<int:project_id>/download/<int:document_id>/', 
         ProjectDetailView.as_view(), name='download_document'),
    path('about/', AboutView.as_view(), name='about'),
    path('evaluators/', EvaluatorListView.as_view(), name='evaluators'),
    path('evaluators/<int:pk>/delete/', EvaluatorDeleteView.as_view(), name='delete_evaluator'),
    path('evaluators/<int:pk>/edit/', EvaluatorUpdateView.as_view(), name='edit_evaluator'),
    path('evaluations/', EvaluationView.as_view(), name='evaluations'),
    path('evaluations/create/', EvaluationView.as_view(), name='create_evaluation'),
    path('evaluations/<int:evaluation_id>/', EvaluationDetailView.as_view(), name='evaluation_detail'),
    path('evaluations/<int:pk>/edit/', EvaluationUpdateView.as_view(), name='edit_evaluation'),
]
