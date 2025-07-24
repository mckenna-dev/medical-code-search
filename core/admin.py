from django.contrib import admin
from .models import CodeSource, CodeList, Code, CodeListCode, UserCodeListSelection, EmisCode

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
    list_display = ['med_code_id', 'term', 'emis_category', 'coding_system', 'observations']
    search_fields = ['med_code_id', 'term', 'snomed_ct_concept_id']
    list_filter = ['emis_category', 'coding_system', 'is_negation', 'is_familial', 'is_screening', 'is_referral']
    readonly_fields = ['codelists_count']
    
    def codelists_count(self, obj):
        return obj.codelists.count()
    codelists_count.short_description = 'Number of Codelists'

@admin.register(EmisCode)
class EmisCodeAdmin(admin.ModelAdmin):
    list_display = [
        'med_code_id', 
        'term_truncated', 
        'observations', 
        'parent_category', 
        'category_type',
        'most_recent_release_year'
    ]
    
    search_fields = [
        'med_code_id', 
        'clean_med_code_id',
        'term', 
        'snomed_ct_concept_id',
        'clean_snomed_ct_concept_id'
    ]
    
    list_filter = [
        'parent_category',
        'emis_cat_description', 
        'most_recent_release_year',
        'is_administrative', 
        'is_screening', 
        'is_referral',
        'is_negated',
        'is_familial',
        'is_symptom',
        'is_test_request'
    ]
    
    readonly_fields = [
        'clean_med_code_id',
        'clean_snomed_ct_concept_id', 
        'category_type',
        'created_date',
        'updated_date'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'med_code_id',
                'clean_med_code_id',
                'term',
                'observations'
            )
        }),
        ('Classification', {
            'fields': (
                'snomed_ct_concept_id',
                'clean_snomed_ct_concept_id',
                'parent_category',
                'emis_cat_description',
                'emis_code_cat_id',
                'category_type',
                'most_recent_release_year'
            )
        }),
        ('Clinical Flags', {
            'fields': (
                'is_negated',
                'is_resolved',
                'is_historical',
                'is_familial',
                'is_genetic_risk'
            )
        }),
        ('Process Flags', {
            'fields': (
                'is_screening',
                'is_monitoring',
                'is_administrative',
                'is_education',
                'is_referral',
                'is_test_request'
            )
        }),
        ('Content Flags', {
            'fields': (
                'is_symptom',
                'is_exclusion',
                'is_qualifier'
            )
        }),
        ('System Information', {
            'fields': (
                'created_date',
                'updated_date'
            ),
            'classes': ('collapse',)
        })
    )
    
    def term_truncated(self, obj):
        """Show truncated term for better display in list view"""
        if len(obj.term) > 80:
            return f"{obj.term[:80]}..."
        return obj.term
    term_truncated.short_description = 'Term'
    
    def get_queryset(self, request):
        """Optimize queryset to reduce database hits"""
        return super().get_queryset(request).select_related()

@admin.register(CodeListCode)
class CodeListCodeAdmin(admin.ModelAdmin):
    list_display = ['codelist', 'code', 'is_excluded']
    list_filter = ['is_excluded', 'codelist']
    search_fields = ['code__med_code_id', 'code__term', 'codelist__codelist_name']
    raw_id_fields = ['code', 'codelist']  # Use raw ID fields for better performance

@admin.register(UserCodeListSelection)
class UserCodeListSelectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'codelist', 'name', 'created_date']
    search_fields = ['user__username', 'codelist__codelist_name', 'name']
    list_filter = ['created_date']
    raw_id_fields = ['user', 'codelist']

# Add some custom admin actions for bulk operations
@admin.action(description='Export selected codes to CSV')
def export_codes_csv(modeladmin, request, queryset):
    """Export selected codes to CSV"""
    # This would be implemented based on your export requirements
    pass

# Add the action to relevant admin classes
CodeAdmin.actions = [export_codes_csv]
EmisCodeAdmin.actions = [export_codes_csv]