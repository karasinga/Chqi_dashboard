from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from research_dashboard.views import UsernameRecoveryView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('research_dashboard.urls')),
    path('accounts/', include([
        path('login/', auth_views.LoginView.as_view(template_name='research_dashboard/login.html'), name='login'),
        path('logout/', auth_views.LogoutView.as_view(next_page='landing_page'), name='logout'),
        path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
        path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
        path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
        path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
        path('username_recovery/', UsernameRecoveryView.as_view(), name='username_recovery'),
        path('username_recovery/done/', auth_views.PasswordResetDoneView.as_view(
            template_name='registration/username_recovery_done.html'
        ), name='username_recovery_done'),
    ])),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
