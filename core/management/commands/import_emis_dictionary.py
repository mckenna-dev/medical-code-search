import csv
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import EmisCode

class Command(BaseCommand):
    help = 'Import EMIS medical dictionary from CSV/TSV file'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, 
                          help='Path to EMIS dictionary CSV/TSV file')
        parser.add_argument('--clear', action='store_true',
                          help='Clear existing EMIS data before importing')
        parser.add_argument('--delimiter', type=str, default='\t',
                          help='File delimiter (default: tab)')
        parser.add_argument('--batch-size', type=int, default=5000,
                          help='Batch size for imports (default: 5000)')

    def handle(self, *args, **options):
        file_path = options['file']
        clear_existing = options['clear']
        delimiter = options['delimiter']
        batch_size = options['batch_size']
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return
        
        # Clear existing data if requested
        if clear_existing:
            count = EmisCode.objects.count()
            if count > 0:
                confirm = input(f'This will delete {count:,} existing EMIS codes. Continue? (yes/no): ')
                if confirm.lower() == 'yes':
                    EmisCode.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS(f'Cleared {count:,} existing codes'))
                else:
                    self.stdout.write('Import cancelled.')
                    return
        
        self.stdout.write(f'📥 Importing EMIS dictionary from: {file_path}')
        self.stdout.write(f'📊 Batch size: {batch_size:,}')
        
        # Import data
        try:
            imported_count = self.import_emis_data(file_path, delimiter, batch_size)
            self.stdout.write(
                self.style.SUCCESS(f'✅ Successfully imported {imported_count:,} EMIS codes')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Import failed: {str(e)}')
            )

    def import_emis_data(self, file_path, delimiter, batch_size):
        """Import EMIS data in batches"""
        imported_count = 0
        batch = []
        
        with open(file_path, 'r', encoding='utf-8') as file:
            # Try to detect if first line is header
            first_line = file.readline()
            file.seek(0)
            
            reader = csv.DictReader(file, delimiter=delimiter)
            
            # Verify headers
            expected_headers = ['MedCodeId', 'Observations', 'Term', 'SnomedCTConceptId']
            missing_headers = [h for h in expected_headers if h not in reader.fieldnames]
            if missing_headers:
                raise ValueError(f'Missing required headers: {missing_headers}')
            
            self.stdout.write(f'📋 Found headers: {list(reader.fieldnames)}')
            
            for row_num, row in enumerate(reader, 1):
                try:
                    # Parse boolean values
                    def parse_bool(value):
                        """
                        Converts input value to a PostgreSQL-safe string ('t' or 'f') 
                        to bypass the 'bit varying' bulk_create type error.
                        """
                        return 't' if str(value).upper() == 'TRUE' else 'f'
                   
                    # Parse integer values
                    def parse_int(value):
                        try:
                            return int(value) if value and value.strip() else None
                        except ValueError:
                            return None
                    
                    emis_code = EmisCode(
                        med_code_id=row['MedCodeId'].strip(),
                        observations=parse_int(row.get('Observations')),
                        term=row['Term'].strip()[:500],  # Truncate if too long
                        snomed_ct_concept_id=row.get('SnomedCTConceptId', '').strip(),
                        most_recent_release_year=parse_int(row.get('MostRecentReleaseYear')),
                        emis_code_cat_id=parse_int(row.get('emiscodecatid')),
                        emis_cat_description=row.get('emis_cat_Description', '').strip()[:200],
                        parent_category=row.get('ParentCategory', '').strip()[:200],
                        
                        # Boolean flags
                        is_negated=parse_bool(row.get('IsNegated', False)),
                        is_resolved=parse_bool(row.get('IsResolved', False)),
                        is_historical=parse_bool(row.get('IsHistorical', False)),
                        is_familial=parse_bool(row.get('IsFamilial', False)),
                        is_genetic_risk=parse_bool(row.get('IsGeneticRisk', False)),
                        is_screening=parse_bool(row.get('IsScreening', False)),
                        is_monitoring=parse_bool(row.get('IsMonitoring', False)),
                        is_administrative=parse_bool(row.get('IsAdministrative', False)),
                        is_education=parse_bool(row.get('IsEducation', False)),
                        is_referral=parse_bool(row.get('IsReferral', False)),
                        is_test_request=parse_bool(row.get('IsTestRequest', False)),
                        is_symptom=parse_bool(row.get('IsSymptom', False)),
                        is_exclusion=parse_bool(row.get('IsExclusion', False)),
                        is_qualifier=parse_bool(row.get('IsQualifier', False)),
                    )
                    
                    batch.append(emis_code)
                    
                    # Process batch when it reaches the batch size
                    if len(batch) >= batch_size:
                        imported_count += self.process_batch(batch)
                        batch = []
                        
                        # Progress update
                        if row_num % (batch_size * 10) == 0:
                            self.stdout.write(f'📊 Processed {row_num:,} rows, imported {imported_count:,} codes')
                
                except Exception as e:
                    self.stdout.write(f'⚠️  Error on row {row_num}: {str(e)}')
                    continue
            
            # Process remaining batch
            if batch:
                imported_count += self.process_batch(batch)
        
        return imported_count
    
    def process_batch(self, batch):
        """Process a batch of EMIS codes"""
        try:
            with transaction.atomic():
                # Use bulk_create with ignore_conflicts to handle duplicates
                created_objects = EmisCode.objects.bulk_create(
                    batch, 
                    ignore_conflicts=True,
                    batch_size=1000
                )
                return len(created_objects)
        except Exception as e:
            self.stdout.write(f'❌ Batch processing failed: {str(e)}')
            return 0