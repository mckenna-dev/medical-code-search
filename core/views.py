from django.shortcuts import render

# Create your views here.

def home(request):
    """Home page view."""
    return render(request, 'core/home.html')

# Add other views mentioned in your urls.py
def codelist_search(request):
    """Codelist search view."""
    return render(request, 'core/codelist_search.html')

def codelist_detail(request, codelist_id):
    """Codelist detail view."""
    return render(request, 'core/codelist_detail.html', {'codelist_id': codelist_id})

def export_codelist(request, codelist_id):
    """Export codelist view."""
    # Placeholder for export functionality
    pass

def medical_dictionary(request):
    """Medical dictionary view."""
    return render(request, 'core/medical_dictionary.html')