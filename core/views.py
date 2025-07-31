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
    sources = CodeSource.objects.all()
    default_source = CodeSource.objects.filter(is_default=True).first()
    
    # Get search parameters
    source_ids = request.GET.getlist('sources', [])
    if not source_ids and default_source:
        source_ids = [str(default_source.id)]
        
    search_term = request.GET.get('search', '')
    
    # Base query
    codelists = CodeList.objects.all()
    
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
    
    return render(request, 'core/codelist_search.html', {
        'sources': sources,
        'codelists': codelists,
        'search_term': search_term,
        'selected_sources': source_ids,
    })

def codelist_detail(request, codelist_id):
    """Codelist detail view with data enrichment."""
    codelist = get_object_or_404(CodeList, id=codelist_id)
    codes = Code.objects.filter(codelists=codelist).order_by('term')

    # --- Data Enrichment Logic ---
    # 1. Get all med_code_ids and clean them (remove leading 'a')
    raw_med_code_ids = [c.med_code_id for c in codes]
    cleaned_med_code_ids = {
        item[1:] if item.startswith('a') and len(item) > 1 else item
        for item in raw_med_code_ids
    }

    # 2. Fetch all relevant EmisCode data in one query
    emis_codes_data = EmisCode.objects.filter(med_code_id__in=cleaned_med_code_ids).values(
        'med_code_id', 'snomed_ct_concept_id', 'observations'
    )

    # 3. Create a lookup dictionary for fast access
    emis_lookup = {
        item['med_code_id']: {
            'snomed': item['snomed_ct_concept_id'],
            'observations': item['observations']
        } for item in emis_codes_data
    }

    # 4. Enrich the original codes list
    enriched_codes = []
    for code in codes:
        # Clean the ID for lookup
        cleaned_id = code.med_code_id[1:] if code.med_code_id.startswith('a') else code.med_code_id
        
        # Get enriched data from the lookup, with defaults
        dictionary_data = emis_lookup.get(cleaned_id, {})
        code.enriched_snomed = dictionary_data.get('snomed', '-')
        code.enriched_observations = dictionary_data.get('observations', 0)
        enriched_codes.append(code)

    # Sort the final list by observations, descending
    enriched_codes.sort(key=lambda x: x.enriched_observations, reverse=True)

    return render(request, 'core/codelist_detail.html', {
        'codelist': codelist,
        'codes': enriched_codes, # Pass the enriched list to the template
    })

@require_POST
def export_codelist(request, codelist_id):
    """Export codelist view with enriched data."""
    codelist = get_object_or_404(CodeList, id=codelist_id)
    
    included_code_ids = request.POST.getlist('included_codes', [])
    codes_to_export = Code.objects.filter(med_code_id__in=included_code_ids).order_by('term')
    
    # --- Apply the same enrichment logic as the detail view ---
    raw_med_code_ids = [c.med_code_id for c in codes_to_export]
    cleaned_med_code_ids = {
        item[1:] if item.startswith('a') and len(item) > 1 else item
        for item in raw_med_code_ids
    }
    emis_codes_data = EmisCode.objects.filter(med_code_id__in=cleaned_med_code_ids).values(
        'med_code_id', 'snomed_ct_concept_id', 'observations'
    )
    emis_lookup = {
        item['med_code_id']: {
            'snomed': item['snomed_ct_concept_id'],
            'observations': item['observations']
        } for item in emis_codes_data
    }
    enriched_codes = []
    for code in codes_to_export:
        cleaned_id = code.med_code_id[1:] if code.med_code_id.startswith('a') else code.med_code_id
        dictionary_data = emis_lookup.get(cleaned_id, {})
        code.enriched_snomed = dictionary_data.get('snomed', '')
        code.enriched_observations = dictionary_data.get('observations', 0)
        enriched_codes.append(code)

    format_type = request.POST.get('format', 'csv')
    
    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{codelist.codelist_name}.csv"'
        
        writer = csv.writer(response)
        # Updated header
        writer.writerow(['med_code_id', 'term', 'snomed_ct_concept_id', 'observations'])
        
        for code in enriched_codes:
            writer.writerow([
                code.med_code_id,
                code.term,
                code.enriched_snomed,
                code.enriched_observations
            ])
        
        return response
    else: # TXT format
        response = HttpResponse(content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="{codelist.codelist_name}.txt"'
        
        # Updated header for TXT file
        response.write('med_code_id\tterm\tsnomed_ct_concept_id\tobservations\n')
        
        for code in enriched_codes:
            response.write(
                f"{code.med_code_id}\t"
                f"{code.term}\t"
                f"{code.enriched_snomed}\t"
                f"{code.enriched_observations}\n"
            )
        
        return response

def parse_search_terms(term_string):
    """Parse comma-separated search terms, handling multi-word phrases."""
    if not term_string:
        return []
    
    terms = []
    for term in term_string.split(','):
        cleaned_term = term.strip()
        if cleaned_term:
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
    
    query = Q()
    for term in terms:
        query |= (
            Q(term__icontains=term) |
            Q(med_code_id__icontains=term) |
            Q(clean_med_code_id__icontains=term) |
            Q(emis_cat_description__icontains=term) |
            Q(snomed_ct_concept_id__icontains=term) |
            Q(clean_snomed_ct_concept_id__icontains=term)
        )
    
    return query

def medical_dictionary(request):
    """Enhanced medical dictionary search view with multi-term search and exclusions."""
    search_terms_raw = request.GET.get('search_terms', '')
    exclusion_terms_raw = request.GET.get('exclusion_terms', '')
    code_param = request.GET.get('code', '')
    sort_by = request.GET.get('sort')
    
    search_terms = parse_search_terms(search_terms_raw)
    exclusion_terms = parse_search_terms(exclusion_terms_raw)
    
    codes = EmisCode.objects.all()
    
    if search_terms:
        search_query = build_term_query(search_terms, 'term')
        codes = codes.filter(search_query)
    
    if code_param:
        codes = codes.filter(
            Q(med_code_id__icontains=code_param) | 
            Q(clean_med_code_id__icontains=code_param)
        )
    
    if exclusion_terms:
        exclusion_query = build_exclusion_query(exclusion_terms)
        codes = codes.exclude(exclusion_query)
        
    if sort_by == 'observations':
        codes = codes.order_by('observations')
        current_sort = 'observations_asc'
    else:
        codes = codes.order_by('-observations')
        current_sort = 'observations_desc'

    total_count = codes.count()
    codes = codes[:500]
    
    search_params = {
        'search_terms': search_terms_raw,
        'exclusion_terms': exclusion_terms_raw,
        'code': code_param,
    }
    
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
        selected_codes = request.POST.getlist('selected_codes', [])
        export_format = request.POST.get('format', 'csv')
        
        if not selected_codes:
            messages.error(request, 'No codes selected for export.')
            return redirect('medical_dictionary')
        
        codes = EmisCode.objects.filter(med_code_id__in=selected_codes).order_by('term')
        
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="medical_dictionary_export.csv"'
            
            writer = csv.writer(response)
            header = ['med_code_id', 'term', 'snomed_ct_concept_id', 'observations']
            writer.writerow(header)
            
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
            
            response.write('med_code_id\tterm\tsnomed_ct_concept_id\tobservations\n')
            
            for code in codes:
                response.write(
                    f"{code.med_code_id}\t"
                    f"{code.term}\t"
                    f"{code.snomed_ct_concept_id or ''}\t"
                    f"{code.observations or 0}\n"
                )
            
            return response
            
        else:
            response = HttpResponse(content_type='application/json')
            response['Content-Disposition'] = 'attachment; filename="medical_dictionary_export.json"'
            
            codes_data = []
            for code in codes:
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

# --- AJAX Handlers ---

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
        field_type = data.get('field_type', 'search')
        current_terms = data.get('current_terms', '')
        
        if not term_to_add:
            return JsonResponse({'status': 'error', 'message': 'No term provided'})
        
        current_list = parse_search_terms(current_terms)
        
        if term_to_add not in current_list:
            current_list.append(term_to_add)
        
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
        
        current_list = parse_search_terms(current_terms)
        
        if term_to_remove in current_list:
            current_list.remove(term_to_remove)
        
        new_terms_string = ', '.join(current_list)
        
        return JsonResponse({
            'status': 'success', 
            'new__terms': new_terms_string,
            'parsed_terms': current_list
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})