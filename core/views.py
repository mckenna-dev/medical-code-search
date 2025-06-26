from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.db.models import Q, Count
from .models import CodeSource, CodeList, Code, CodeListCode
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
    """Codelist search view."""
    print("DEBUG: codelist_search view called")  # Add this debug line
    
    sources = CodeSource.objects.all()
    print(f"DEBUG: Found {sources.count()} sources")  # Add this debug line
    
    default_source = CodeSource.objects.filter(is_default=True).first()
    
    # Get search parameters
    source_ids = request.GET.getlist('sources', [])
    if not source_ids and default_source:
        source_ids = [str(default_source.id)]
        
    search_term = request.GET.get('search', '')
    
    # Base query
    codelists = CodeList.objects.all()
    print(f"DEBUG: Found {codelists.count()} codelists")  # Add this debug line
    
    # Apply filters
    if source_ids:
        codelists = codelists.filter(source_id__in=source_ids)
    if search_term:
        codelists = codelists.filter(
            Q(codelist_name__icontains=search_term) | 
            Q(codelist_description__icontains=search_term)
        )
    
    # Annotate with code count
    codelists = codelists.annotate(code_count=Count('codelistcode'))
    
    print(f"DEBUG: Rendering template with {codelists.count()} codelists")  # Add this debug line
    
    return render(request, 'core/codelist_search.html', {
        'sources': sources,
        'codelists': codelists,
        'search_term': search_term,
        'selected_sources': source_ids,
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
    """Medical dictionary search view."""
    term = request.GET.get('term', '')
    code = request.GET.get('code', '')
    category = request.GET.get('category', '')
    
    codes = Code.objects.all()
    
    # Apply filters
    if term:
        codes = codes.filter(term__icontains=term)
    if code:
        codes = codes.filter(med_code_id__icontains=code)
    if category:
        codes = codes.filter(emis_category=category)
    
    # Get unique categories for filter dropdown
    categories = Code.objects.values_list('emis_category', flat=True).distinct().order_by('emis_category')
    
    # Limit results for performance
    codes = codes[:500]
    
    return render(request, 'core/medical_dictionary.html', {
        'codes': codes,
        'term': term,
        'code': code,
        'category': category,
        'categories': categories,
    })