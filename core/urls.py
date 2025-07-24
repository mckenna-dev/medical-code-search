from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('codelists/', views.codelist_search, name='codelist_search'),
    path('codelists/<int:codelist_id>/', views.codelist_detail, name='codelist_detail'),
    path('codelists/<int:codelist_id>/export/', views.export_codelist, name='export_codelist'),
    path('medical-dictionary/', views.medical_dictionary, name='medical_dictionary'),
]