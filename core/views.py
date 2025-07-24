from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.db.models import Q, Count
from .models import CodeSource, CodeList, Code, CodeListCode, EmisCode
import csv

def home(request):
    """Home page view."""
    sources = CodeSource.objects.all()
    codelists_count = CodeList.objects.count()
    codes_count = Code.objects.count()
    return render(request, 'core/home.html', {
        'sources': sources,
        'codelists_count': codelists_count,
        'codes_count': codes_count
    })

def codelist_search(request):
    """Codelist search view with CPRD as default."""
    
    # Get all sources, ordered with default first
    sources = CodeSource.objects.all().order_by('-is_default', 'name')
    
    # Always ensure we have the default CPRD source
    cprd_source = CodeSource.objects.filter(is_default=True).first()
    if not cprd_source:
        # Fallback: try to find Oxford_CPRD by name
        cprd_source = CodeSource.objects.filter(name='Oxford_CPRD').first()
    
    # Get search parameters
    source_ids = request.GET.getlist('sources', [])
    
    # If no sources selected, default to CPRD only
    if not source_ids and cprd_source:
        source_ids = [str(cprd_source.id)]
    
    search_term = request.GET.get('search', '')
    
    # Base query
    codelists = CodeList.objects.all()
    
    # Apply source filter - always filter by selected sources
    if source_ids:
        codelists = codelists.filter(source_id__in=source_ids)
    
    # Apply search filter
    if search_term:
        codelists = codelists.filter(
            Q(codelist_name__icontains=search_term) | 
            Q(codelist_description__icontains=search_term) |
            Q(project_title__icontains=search_term) |
            Q(author__icontains=search_term)
        )
    
    # Annotate with code count and order by relevance
    codelists = codelists.annotate(total_codes=Count('codelistcode')).order_by('-total_codes', 'codelist_name')
    
    # Add source selection context
    source_selection_info = {
        'total_selected': len(source_ids),
        'cprd_selected': str(cprd_source.id) in source_ids if cprd_source else False,
        'other_selected': len([s for s in source_ids if s != str(cprd_source.id)]) if cprd_source else len(source_ids)
    }
    
    return render(request, 'core/codelist_search.html', {
        'sources': sources,
        'codelists': codelists,
        'search_term': search_term,
        'selected_sources': source_ids,
        'cprd_source': cprd_source,  # THIS WAS MISSING
        'source_info': source_selection_info,
    })

def codelist_detail(request, codelist_id):
    """Codelist detail view."""
    print(f"DEBUG: codelist_detail view called with ID: {codelist_id}")
    
    try:
        codelist = get_object_or_404(CodeList, id=codelist_id) 
        print(f"DEBUG: Found codelist: {codelist.codelist_name}")
        
        codes = Code.objects.filter(codelists=codelist).order_by('term')
        print(f"DEBUG: Found {codes.count()} codes for this codelist")
        
    except Exception as e:
        print(f"DEBUG: Error in codelist_detail: {e}")
        raise
    
    return render(request, 'core/codelist_detail.html', {
        'codelist': codelist,
        'codes': codes,
    })

def export_codelist(request, codelist_id):
    """Export codelist view."""
    codelist = get_object_or_404(CodeList, id=codelist_id)
    
    if request.method == 'POST':
        # Get included code IDs
        included_code_ids = request.POST.getlist('included_codes', [])
        
        # Get codes to export
        codes = Code.objects.filter(med_code_id__in=included_code_ids)
        
        # Get export format
        format_type = request.POST.get('format', 'csv')
        
        if format_type == 'csv':
            # Create CSV response
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{codelist.codelist_name}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['med_code_id', 'term', 'snomed_ct_concept_id', 'emis_category', 'coding_system'])
            
            for code in codes:
                writer.writerow([
                    code.med_code_id,
                    code.term,
                    code.snomed_ct_concept_id,
                    code.emis_category,
                    code.coding_system
                ])
            
            return response
        else:
            # Create TXT response
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = f'attachment; filename="{codelist.codelist_name}.txt"'
            
            for code in codes:
                response.write(f"{code.med_code_id}\t{code.term}\n")
            
            return response
    
    return redirect('codelist_detail', codelist_id=codelist_id)

def medical_dictionary(request):
    """Medical dictionary search view - searches EMIS dictionary, not research codelists."""
    term = request.GET.get('term', '')
    code = request.GET.get('code', '')
    category = request.GET.get('category', '')
    
    # Search EmisCode instead of Code
    codes = EmisCode.objects.all()
    
    # Apply filters
    if term:
        codes = codes.filter(term__icontains=term)
    if code:
        # Search both original and clean code IDs
        codes = codes.filter(
            Q(med_code_id__icontains=code) | 
            Q(clean_med_code_id__icontains=code)
        )
    if category:
        codes = codes.filter(parent_category=category)
    
    # Get unique categories for filter dropdown
    categories = EmisCode.objects.values_list('parent_category', flat=True).distinct().order_by('parent_category')
    
    # Limit results for performance
    codes = codes[:500]
    
    return render(request, 'core/medical_dictionary.html', {
        'codes': codes,
        'term': term,
        'code': code,
        'category': category,
        'categories': categories,
    })