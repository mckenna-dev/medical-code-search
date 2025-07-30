# core/management/commands/validate_medical_search.py

from django.core.management.base import BaseCommand
from core.models import Code, CodeList, CodeSource
from django.db.models import Count

class Command(BaseCommand):
    help = 'Validate medical code data for multi-term search functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--show-samples',
            action='store_true',
            help='Show sample data for verification',
        )

    def handle(self, *args, **options):
        self.stdout.write('=== Medical Dictionary Search Validation ===\n')
        
        # Basic counts
        total_codes = Code.objects.count()
        
        self.stdout.write(f'📊 Data Overview:')
        self.stdout.write(f'   Total Medical Codes: {total_codes:,}')
        
        if total_codes == 0:
            self.stdout.write(self.style.WARNING('⚠️  No codes found in database!'))
            self.stdout.write('   This enhancement requires existing medical codes.')
            return
        
        # Test search functionality
        self.stdout.write(f'\n🔍 Search Functionality Tests:')
        
        # Test common terms
        test_terms = ['diabetes', 'heart', 'blood', 'infection', 'pain']
        for term in test_terms:
            count = Code.objects.filter(term__icontains=term).count()
            self.stdout.write(f'   "{term}": {count:,} codes found')
        
        # Test code fields
        self.stdout.write(f'\n📋 Code Field Analysis:')
        
        # Check for required fields
        codes_with_terms = Code.objects.exclude(term='').count()
        codes_with_snomed = Code.objects.exclude(snomed_ct_concept_id='').count()
        codes_with_category = Code.objects.exclude(emis_category='').count()
        
        self.stdout.write(f'   Codes with terms: {codes_with_terms:,} ({self.percentage(codes_with_terms, total_codes)}%)')
        self.stdout.write(f'   Codes with SNOMED: {codes_with_snomed:,} ({self.percentage(codes_with_snomed, total_codes)}%)')
        self.stdout.write(f'   Codes with categories: {codes_with_category:,} ({self.percentage(codes_with_category, total_codes)}%)')
        
        # Check boolean flags (for display badges)
        self.stdout.write(f'\n🏷️  Clinical Flags Analysis:')
        
        flag_fields = [
            ('is_screening', 'Screening'),
            ('is_referral', 'Referral'), 
            ('is_familial', 'Family History'),
            ('is_suspected', 'Suspected'),
            ('is_advice', 'Advice'),
            ('is_negation', 'Negation'),
        ]
        
        flags_available = True
        for flag_field, flag_name in flag_fields:
            try:
                count = Code.objects.filter(**{flag_field: True}).count()
                percentage = self.percentage(count, total_codes)
                self.stdout.write(f'   {flag_name}: {count:,} codes ({percentage}%)')
            except Exception:
                self.stdout.write(f'   {flag_name}: Field not found')
                flags_available = False
        
        # Sample data
        if options['show_samples']:
            self.stdout.write(f'\n📝 Sample Codes:')
            sample_codes = Code.objects.order_by('?')[:3]
            
            for i, code in enumerate(sample_codes, 1):
                self.stdout.write(f'   {i}. {code.med_code_id}: {code.term[:80]}...')
                if code.snomed_ct_concept_id:
                    self.stdout.write(f'      SNOMED: {code.snomed_ct_concept_id}')
                if code.emis_category:
                    self.stdout.write(f'      Category: {code.emis_category}')
        
        # Multi-term search test
        self.stdout.write(f'\n🔍 Multi-Term Search Test:')
        test_multi_terms = ['diabetes', 'heart disease', 'high blood pressure']
        
        # Simulate multi-term search
        from django.db.models import Q
        query = Q()
        for term in test_multi_terms:
            query |= Q(term__icontains=term)
        
        multi_result_count = Code.objects.filter(query).count()
        self.stdout.write(f'   Search for "{", ".join(test_multi_terms)}": {multi_result_count:,} codes')
        
        # Exclusion test
        exclusion_terms = ['screening', 'family']
        exclusion_query = Q()
        for term in exclusion_terms:
            exclusion_query |= (
                Q(term__icontains=term) |
                Q(med_code_id__icontains=term) |
                Q(emis_category__icontains=term)
            )
        
        exclusion_count = Code.objects.filter(exclusion_query).count()
        final_count = Code.objects.filter(query).exclude(exclusion_query).count()
        
        self.stdout.write(f'   Codes to exclude with "{", ".join(exclusion_terms)}": {exclusion_count:,}')
        self.stdout.write(f'   Final result after exclusions: {final_count:,}')
        
        # Recommendations
        self.stdout.write(f'\n💡 Recommendations:')
        
        if total_codes > 1000:
            self.stdout.write('   ✅ Good code volume for multi-term search')
        else:
            self.stdout.write('   ⚠️  Low code count - search may have limited results')
        
        if codes_with_terms / total_codes > 0.95:
            self.stdout.write('   ✅ Excellent term coverage - search will work well')
        else:
            self.stdout.write('   📝 Some codes missing terms - may affect search quality')
        
        if flags_available:
            self.stdout.write('   ✅ Clinical flags available - badge display will work')
        else:
            self.stdout.write('   📝 Clinical flags missing - only basic display available')
        
        if codes_with_snomed / total_codes > 0.5:
            self.stdout.write('   ✅ Good SNOMED coverage for clinical context')
        
        # Performance note
        if total_codes > 100000:
            self.stdout.write('   ⚡ Large dataset - results limited to 500 for performance')
        
        self.stdout.write(f'\n✅ Validation complete!')
        self.stdout.write('🚀 Your medical dictionary is ready for multi-term search enhancements.')
    
    def percentage(self, part, total):
        """Calculate percentage with 1 decimal place."""
        if total == 0:
            return 0
        return round((part / total) * 100, 1)