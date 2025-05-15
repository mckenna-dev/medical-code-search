from django.contrib import admin
from .models import CodeSource, CodeList, Code, CodeListCode, UserCodeListSelection

# Register your models here.


@admin.register(CodeSource)
class CodeSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_default']
    search_fields = ['name']

@admin.register(CodeList)
class CodeListAdmin(admin.ModelAdmin):
    list_display = ['codelist_name', 'source', 'project_title', 'author', 'updated_date']
    search_fields = ['codelist_name', 'project_title', 'author', 'codelist_description']
    list_filter = ['source', 'emis_dictionary_version']

@admin.register(Code)
class CodeAdmin(admin.ModelAdmin):
    list_display = ['med_code_id', 'term', 'emis_category', 'coding_system']
    search_fields = ['med_code_id', 'term', 'snomed_ct_concept_id']
    list_filter = ['emis_category', 'coding_system', 'is_negation', 'is_familial']

@admin.register(CodeListCode)
class CodeListCodeAdmin(admin.ModelAdmin):
    list_display = ['codelist', 'code', 'is_excluded']
    list_filter = ['is_excluded', 'codelist']
    search_fields = ['code__med_code_id', 'code__term', 'codelist__codelist_name']

@admin.register(UserCodeListSelection)
class UserCodeListSelectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'codelist', 'name', 'created_date']
    search_fields = ['user__username', 'codelist__codelist_name', 'name']