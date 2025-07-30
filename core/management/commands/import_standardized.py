import os
import pandas as pd
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import CodeSource, CodeList, Code, CodeListCode

class Command(BaseCommand):
    help = 'Import standardized codelists into Django database'

    def add_arguments(self, parser):
        parser.add_argument('--standardized-root', type=str, default='./codelists_bulk/standardized/',
                          help='Path to standardized files directory')
        parser.add_argument('--source-name', type=str, default='Oxford_CPRD',
                          help='Name of the code source')
        parser.add_argument('--dry-run', action='store_true',
                          help='Show what would be imported without actually importing')
        parser.add_argument('--clear-existing', action='store_true',
                          help='Clear existing data from this source before importing')

    def handle(self, *args, **options):
        standardized_root = Path(options['standardized_root'])
        source_name = options['source_name']
        dry_run = options['dry_run']
        clear_existing = options['clear_existing']
        
        if not standardized_root.exists():
            self.stdout.write(self.style.ERROR(f'Standardized directory not found: {standardized_root}'))
            return
        
        # Get or create source
        if not dry_run:
            source, created = CodeSource.objects.get_or_create(
                name=source_name,
                defaults={
                    'description': 'Oxford CPRD Codelists Collection',
                    'is_default': True
                }
            )
            
            if clear_existing:
                self.stdout.write(f'Clearing existing data for source: {source_name}')
                CodeList.objects.filter(source=source).delete()
                self.stdout.write(self.style.SUCCESS('Existing data cleared'))
        else:
            from types import SimpleNamespace
            source = SimpleNamespace()
            source.name = source_name
        
        # Import statistics
        stats = {
            'projects_processed': 0,
            'codelists_created': 0,
            'codes_created': 0,
            'codes_linked': 0,
            'skipped': 0,
            'errors': 0
        }
        
        # Process each project folder
        for project_folder in standardized_root.iterdir():
            if not project_folder.is_dir():
                continue
                
            project_name = project_folder.name
            stats['projects_processed'] += 1
            
            self.stdout.write(f'\n📁 Processing project: {project_name}')
            
            # Process each standardized file in the project
            csv_files = list(project_folder.glob('*_standardized.csv'))
            mapping_files = {f.stem.replace('_mapping', ''): f for f in project_folder.glob('*_mapping.json')}
            
            for csv_file in csv_files:
                # Extract codelist name (remove _standardized suffix)
                codelist_name = csv_file.stem.replace('_standardized', '')
                
                # Get corresponding mapping file
                mapping_file = mapping_files.get(codelist_name)
                
                try:
                    result = self.import_standardized_file(
                        csv_file, mapping_file, project_name, source, dry_run
                    )
                    
                    if result:
                        stats['codelists_created'] += 1
                        stats['codes_created'] += result['codes_created']
                        stats['codes_linked'] += result['codes_linked']
                        
                        self.stdout.write(
                            f"  ✅ {codelist_name}: {result['codes_linked']} codes linked"
                        )
                    else:
                        stats['skipped'] += 1
                        self.stdout.write(f"  ⚠️  Skipped: {codelist_name}")
                        
                except Exception as e:
                    stats['errors'] += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ❌ Error processing {codelist_name}: {str(e)}")
                    )
        
        # Print final summary
        self.print_summary(stats, dry_run)

    def import_standardized_file(self, csv_file, mapping_file, project_name, source, dry_run):
        """Import a single standardized CSV file"""
        
        # Read the standardized data
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            self.stdout.write(f"    Error reading {csv_file}: {str(e)}")
            return None
        
        if len(df) == 0:
            return None
        
        # Read mapping metadata if available
        metadata = {}
        if mapping_file and mapping_file.exists():
            try:
                with open(mapping_file, 'r') as f:
                    metadata = json.load(f)
            except:
                pass
        
        # Extract codelist information
        codelist_name = csv_file.stem.replace('_standardized', '')
        
        # Parse project and ERAP from folder structure
        # Format: project/ERAP_CodelistName
        folder_parts = codelist_name.split('_', 1)
        erap_number = folder_parts[0] if len(folder_parts) > 1 else ''
        original_name = folder_parts[1] if len(folder_parts) > 1 else codelist_name
        
        if dry_run:
            unique_codes = df['med_code_id'].nunique() if 'med_code_id' in df.columns else 0
            total_rows = len(df)
            self.stdout.write(
                f"    Would create: {original_name} ({project_name}) with {total_rows} codes"
            )
            return {
                'codes_created': unique_codes,
                'codes_linked': total_rows
            }
        
        # Create or get the codelist
        with transaction.atomic():
            # Check if codelist already exists with this exact combination
            existing_codelist = CodeList.objects.filter(
                codelist_name=original_name,
                project_title=project_name,
                ERAP_number=erap_number,
                source=source
            ).first()
            
            if existing_codelist:
                self.stdout.write(f"    Codelist already exists: {original_name}")
                return None
            
            # Create new codelist
            codelist = CodeList.objects.create(
                codelist_name=original_name,
                project_title=project_name,
                ERAP_number=erap_number,
                author=metadata.get('author', ''),
                codelist_description=f'Imported from standardized file. Original columns: {", ".join(metadata.get("original_columns", []))}',
                emis_dictionary_version='Standardized_Import',
                source=source
            )
            
            # Process codes
            codes_created = 0
            codes_linked = 0
            
            for _, row in df.iterrows():
                med_code_id = str(row['med_code_id']).strip()
                if not med_code_id or med_code_id.lower() in ['nan', 'none']:
                    continue
                
                # Get or create the code
                code, created = Code.objects.get_or_create(
                    med_code_id=med_code_id,
                    defaults={
                        'term': row.get('term', 'Unknown'),
                        'observations': row.get('observations') if pd.notna(row.get('observations')) else None,
                        'snomed_ct_concept_id': row.get('snomed_ct_concept_id', ''),
                        'emis_category': '',
                        'coding_system': 'Oxford_CPRD'
                    }
                )
                
                if created:
                    codes_created += 1
                
                # Link code to codelist
                link, link_created = CodeListCode.objects.get_or_create(
                    code=code,
                    codelist=codelist
                )
                
                if link_created:
                    codes_linked += 1
            
            return {
                'codes_created': codes_created,
                'codes_linked': codes_linked
            }

    def print_summary(self, stats, dry_run):
        """Print import summary"""
        action = "Would import" if dry_run else "Imported"
        
        self.stdout.write(f'\n📊 IMPORT SUMMARY')
        self.stdout.write(f'Projects processed: {stats["projects_processed"]}')
        self.stdout.write(f'Codelists {action.lower()}: {stats["codelists_created"]}')
        self.stdout.write(f'New codes {action.lower()}: {stats["codes_created"]}')
        self.stdout.write(f'Code-codelist links {action.lower()}: {stats["codes_linked"]}')
        self.stdout.write(f'Files skipped: {stats["skipped"]}')
        self.stdout.write(f'Errors: {stats["errors"]}')
        
        if stats['projects_processed'] > 0:
            success_rate = (stats['codelists_created'] / (stats['codelists_created'] + stats['skipped'] + stats['errors'])) * 100
            self.stdout.write(f'Success rate: {success_rate:.1f}%')
        
        if not dry_run and stats['codelists_created'] > 0:
            self.stdout.write(f'\n✅ Import complete! Check your Django admin to see the imported codelists.')