# core/urls.py - Enhanced URL configuration

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('codelists/', views.codelist_search, name='codelist_search'),
    path('codelists/<int:codelist_id>/', views.codelist_detail, name='codelist_detail'),
    path('codelists/<int:codelist_id>/export/', views.export_codelist, name='export_codelist'),
    path('medical-dictionary/', views.medical_dictionary, name='medical_dictionary'),
    
    # New medical dictionary export and selection endpoints
    path('medical-dictionary/export/', views.export_medical_dictionary, name='export_medical_dictionary'),
    path('medical-dictionary/save-selection/', views.save_medical_dictionary_selection, name='save_medical_dictionary_selection'),
    path('medical-dictionary/get-selection/', views.get_medical_dictionary_selection, name='get_medical_dictionary_selection'),
    path('medical-dictionary/add-term/', views.add_search_term, name='add_search_term'),
    path('medical-dictionary/remove-term/', views.remove_search_term, name='remove_search_term'),
]