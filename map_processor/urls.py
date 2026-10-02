from django.urls import path
from . import views

app_name = 'map_processor'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('verify-access/', views.verify_access_view, name='verify_access'),
    path('logout-access/', views.logout_access_view, name='logout_access'),
    path('upload/', views.upload_view, name='upload'),
    path('dashboard/', views.dashboard_view, name='dashboard_latest'),
    path('dashboard/<int:map_id>/', views.dashboard_view, name='dashboard'),
    path('reprocess/<int:map_id>/', views.reprocess_view, name='reprocess'),
    path('print/<int:map_id>/', views.print_report_view, name='print_report'),
    path('api/<int:map_id>/', views.map_api_view, name='map_api'),
]
