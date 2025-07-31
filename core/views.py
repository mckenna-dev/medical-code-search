# core/views.py - Enhanced medical dictionary with term-based search and exclusions

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Count
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import CodeSource, CodeList, Code, CodeListCode, EmisCode
import csv
import json
import re

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
    codelists = codelists.annotate(total_codes=Count('codelistcode'))
    
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

def parse_search_terms(term_string):
    """Parse comma-separated search terms, handling multi-word phrases."""
    if not term_string:
        return []
    
    # Split by comma and clean up each term
    terms = []
    for term in term_string.split(','):
        cleaned_term = term.strip()
        if cleaned_term:  # Only add non-empty terms
            terms.append(cleaned_term)
    
    return terms

def build_term_query(terms, field_name):
    """Build a Q object for searching multiple terms in a field."""
    if not terms:
        return Q()
    
    query = Q()
    for term in terms:
        query |= Q(**{f'{field_name}__icontains': term})
    
    return query

def build_exclusion_query(terms):
    """Build a Q object for excluding codes that match any of the terms."""
    if not terms:
        return Q()
    
    # Search across multiple fields for exclusion - UPDATED for EmisCode model
    query = Q()
    for term in terms:
        query |= (
            Q(term__icontains=term) |
            Q(med_code_id__icontains=term) |
            Q(clean_med_code_id__icontains=term) |
            Q(emis_cat_description__icontains=term) |  # Changed from emis_category
            Q(snomed_ct_concept_id__icontains=term) |
            Q(clean_snomed_ct_concept_id__icontains=term)  # Added clean version
        )
    
    return query

def medical_dictionary(request):
    """Enhanced medical dictionary search view with multi-term search and exclusions."""
    
    # Get search parameters
    search_terms_raw = request.GET.get('search_terms', '')
    exclusion_terms_raw = request.GET.get('exclusion_terms', '')
    code_param = request.GET.get('code', '')
    sort_by = request.GET.get('sort')
    
    # Parse comma-separated terms
    search_terms = parse_search_terms(search_terms_raw)
    exclusion_terms = parse_search_terms(exclusion_terms_raw)
    
    # Use EmisCode model
    codes = EmisCode.objects.all()
    
    # Apply search filters
    if search_terms:
        search_query = build_term_query(search_terms, 'term')
        codes = codes.filter(search_query)
    
    if code_param:
        codes = codes.filter(
            Q(med_code_id__icontains=code_param) | 
            Q(clean_med_code_id__icontains=code_param)
        )
    
    # Apply exclusions
    if exclusion_terms:
        exclusion_query = build_exclusion_query(exclusion_terms)
        codes = codes.exclude(exclusion_query)
        
    # Handle sorting by Observations
    if sort_by == 'observations':
        codes = codes.order_by('observations')
        current_sort = 'observations_asc'
    else: # Default to descending observations
        codes = codes.order_by('-observations')
        current_sort = 'observations_desc'

    # Get total count before limiting
    total_count = codes.count()
    
    # Limit results for performance
    codes = codes[:500]
    
    # Store search parameters for template
    search_params = {
        'search_terms': search_terms_raw,
        'exclusion_terms': exclusion_terms_raw,
        'code': code_param,
    }
    
    # Create user-friendly display of parsed terms
    parsed_terms_info = {
        'search_terms_parsed': search_terms,
        'exclusion_terms_parsed': exclusion_terms,
    }
    
    return render(request, 'core/medical_dictionary.html', {
        'codes': codes,
        'total_count': total_count,
        'showing_count': len(codes),
        'search_params': search_params,
        'parsed_terms_info': parsed_terms_info,
        'current_sort': current_sort,
    })

@require_POST
def export_medical_dictionary(request):
    """Export selected codes from medical dictionary search."""
    try:
        # Get selected code IDs from request
        selected_codes = request.POST.getlist('selected_codes', [])
        export_format = request.POST.get('format', 'csv')
        
        if not selected_codes:
            messages.error(request, 'No codes selected for export.')
            return redirect('medical_dictionary')
        
        # Get the actual code objects
        codes = EmisCode.objects.filter(med_code_id__in=selected_codes).order_by('term')
        
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="medical_dictionary_export.csv"'
            
            writer = csv.writer(response)
            
            # Use the new, corrected header
            header = ['med_code_id', 'term', 'snomed_ct_concept_id', 'observations']
            writer.writerow(header)
            
            # Write data with the correct attributes
            for code in codes:
                row = [
                    code.med_code_id,
                    code.term,
                    code.snomed_ct_concept_id or '',
                    code.observations or 0,
                ]
                writer.writerow(row)
            
            return response
            
        elif export_format == 'txt':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="medical_dictionary_export.txt"'
            
            # Write a header for the text file
            response.write('med_code_id\tterm\tsnomed_ct_concept_id\tobservations\n')
            
            # Write data with the new columns, tab-separated
            for code in codes:
                response.write(
                    f"{code.med_code_id}\t"
                    f"{code.term}\t"
                    f"{code.snomed_ct_concept_id or ''}\t"
                    f"{code.observations or 0}\n"
                )
            
            return response
            
        else:  # JSON format
            response = HttpResponse(content_type='application/json')
            response['Content-Disposition'] = 'attachment; filename="medical_dictionary_export.json"'
            
            codes_data = []
            for code in codes:
                # Use the new, corrected fields for JSON
                code_data = {
                    'med_code_id': code.med_code_id,
                    'term': code.term,
                    'snomed_ct_concept_id': code.snomed_ct_concept_id or '',
                    'observations': code.observations or 0,
                }
                codes_data.append(code_data)
            
            response.write(json.dumps(codes_data, indent=2))
            return response
    
    except Exception as e:
        messages.error(request, f'Export failed: {str(e)}')
        return redirect('medical_dictionary')

def save_medical_dictionary_selection(request):
    """AJAX endpoint to save selected codes to session."""
    if request.method == 'POST':
        try:
            selected_codes = json.loads(request.body).get('selected_codes', [])
            request.session['medical_dictionary_selection'] = selected_codes
            return JsonResponse({'status': 'success', 'count': len(selected_codes)})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def get_medical_dictionary_selection(request):
    """AJAX endpoint to get saved selected codes from session."""
    selected_codes = request.session.get('medical_dictionary_selection', [])
    return JsonResponse({'selected_codes': selected_codes})

@require_POST
def add_search_term(request):
    """AJAX endpoint to add a term to search or exclusion."""
    try:
        data = json.loads(request.body)
        term_to_add = data.get('term', '').strip()
        field_type = data.get('field_type', 'search')  # 'search' or 'exclusion'
        current_terms = data.get('current_terms', '')
        
        if not term_to_add:
            return JsonResponse({'status': 'error', 'message': 'No term provided'})
        
        # Parse current terms
        current_list = parse_search_terms(current_terms)
        
        # Add new term if not already present
        if term_to_add not in current_list:
            current_list.append(term_to_add)
        
        # Join back into string
        new_terms_string = ', '.join(current_list)
        
        return JsonResponse({
            'status': 'success',
            'new_terms': new_terms_string,
            'parsed_terms': current_list
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_POST 
def remove_search_term(request):
    """AJAX endpoint to remove a term from search or exclusion."""
    try:
        data = json.loads(request.body)
        term_to_remove = data.get('term', '').strip()
        current_terms = data.get('current_terms', '')
        
        # Parse current terms
        current_list = parse_search_terms(current_terms)
        
        # Remove term if present
        if term_to_remove in current_list:
            current_list.remove(term_to_remove)
        
        # Join back into string
        new_terms_string = ', '.join(current_list)
        
        return JsonResponse({
            'status': 'success', 
            'new_terms': new_terms_string,
            'parsed_terms': current_list
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})