import os
import csv
import pandas as pd
import requests
from urllib.parse import urlparse
from django.core.management.base import BaseCommand
from core.models import CodeSource, CodeList, Code, CodeListCode

class Command(BaseCommand):
    help = 'Import codelists from GitHub repositories using metadata CSV'

    def add_arguments(self, parser):
        parser.add_argument('--metadata-csv', type=str, required=True, 
                          help='Path to CSV file containing codelist metadata')
        parser.add_argument('--download-dir', type=str, default='./downloads/',
                          help='Directory to download codelist files')
        parser.add_argument('--source-name', type=str, default='Oxford_CPRD',
                          help='Name of the code source')
        parser.add_argument('--dry-run', action='store_true',
                          help='Show what would be imported without actually importing')
        parser.add_argument('--clean-existing', action='store_true',
                          help='Clean existing codelists from this source before importing')

    def handle(self, *args, **options):
        metadata_csv = options['metadata_csv']
        download_dir = options['download_dir']
        source_name = options['source_name']
        dry_run = options['dry_run']
        clean_existing = options['clean_existing']
        
        # Ensure download directory exists
        os.makedirs(download_dir, exist_ok=True)
        
        # Get or create the code source
        source = None
        try:
            source = CodeSource.objects.get(name=source_name)
            self.stdout.write(f'Using existing source: {source_name}')
            
            # Clean existing codelists if requested
            if clean_existing and not dry_run:
                existing_count = CodeList.objects.filter(source=source).count()
                if existing_count > 0:
                    self.stdout.write(f'Cleaning {existing_count} existing codelists from {source_name}')
                    CodeList.objects.filter(source=source).delete()
                    self.stdout.write(self.style.SUCCESS(f'Cleaned {existing_count} codelists'))
                    
        except CodeSource.DoesNotExist:
            if not dry_run:
                source = CodeSource.objects.create(
                    name=source_name,
                    description=f'Imported from GitHub repositories - Oxford CPRD Collection',
                    is_default=source_name == 'Oxford_CPRD'
                )
                self.stdout.write(self.style.SUCCESS(f'Created new source: {source_name}'))
            else:
                # Create a dummy source for dry-run
                from types import SimpleNamespace
                source = SimpleNamespace()
                source.name = source_name
                self.stdout.write(self.style.SUCCESS(f'Dry-run: Would create source: {source_name}'))
        
        # Read metadata CSV
        try:
            df = pd.read_csv(metadata_csv, encoding='utf-8-sig')
            self.stdout.write(f'Found {len(df)} entries in metadata file')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error reading metadata CSV: {str(e)}'))
            return
        
        # Process each codelist
        total_processed = 0
        total_codes_imported = 0
        total_skipped = 0
        
        for index, row in df.iterrows():
            try:
                result = self.process_codelist(row, source, download_dir, dry_run)
                if result is not None:
                    if result > 0:
                        total_processed += 1
                        total_codes_imported += result
                    else:
                        total_skipped += 1
                        
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error processing row {index}: {str(e)}')
                )
                total_skipped += 1
                continue
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Results: {total_processed} codelists processed, {total_codes_imported} codes imported, {total_skipped} skipped'
            )
        )

    def process_codelist(self, row, source, download_dir, dry_run):
        """Process a single codelist from the metadata"""
        
        # Extract metadata from the row with flexible column name matching
        codelist_name = str(row.get('Codelist_Name', '')).strip()
        erap_number = str(row.get('ERAP_Number', '')).strip()
        project_title = str(row.get('Project_Title', '')).strip()
        author = str(row.get('Author', '')).strip()
        coding_system = str(row.get('Coding System', '')).strip()
        year_created = str(row.get('Year_Created', '')).strip()
        doi_publication = str(row.get('DOI_Publication', '')).strip()
        
        # Clean up nan values
        if erap_number.lower() in ['nan', 'none', 'null', '']:
            erap_number = ''
        if project_title.lower() in ['nan', 'none', 'null', '']:
            project_title = ''
        if author.lower() in ['nan', 'none', 'null', '']:
            author = ''
        if coding_system.lower() in ['nan', 'none', 'null', '']:
            coding_system = ''
        if year_created.lower() in ['nan', 'none', 'null', '']:
            year_created = ''
        
        # Try different possible column names for the GitHub URL
        github_url = ''
        url_columns = ['Path_to_Codelist', 'URL', 'GitHub_URL', 'Codelist_URL', 'Path']
        for col in url_columns:
            if col in row and pd.notna(row[col]):
                github_url = str(row[col]).strip()
                if github_url.startswith('http'):
                    break
        
        if not codelist_name or not github_url:
            self.stdout.write(f'Skipping row due to missing name or URL: {codelist_name}')
            return None
        
        # Create composite key for uniqueness: codelist_name + project_title + erap_number
        # This ensures uniqueness while keeping original names for search
        composite_key_parts = [codelist_name]
        if project_title:
            composite_key_parts.append(project_title)
        if erap_number:
            composite_key_parts.append(erap_number)
        
        composite_key = " | ".join(composite_key_parts)
        
        self.stdout.write(f'Processing: {codelist_name}')
        self.stdout.write(f'  - Composite key: {composite_key}')
        
        if dry_run:
            self.stdout.write(f'  - Original Name: {codelist_name}')
            self.stdout.write(f'  - ERAP: {erap_number}')
            self.stdout.write(f'  - Project: {project_title}')
            self.stdout.write(f'  - Author: {author}')
            self.stdout.write(f'  - System: {coding_system}')
            self.stdout.write(f'  - URL: {github_url}')
            return 1
        
        # Check if this exact combination already exists
        # Use composite key as internal identifier but keep original name for users
        existing_codelist = CodeList.objects.filter(
            codelist_name=codelist_name,
            project_title=project_title,
            ERAP_number=erap_number,
            source=source
        ).first()
        
        if existing_codelist:
            self.stdout.write(f'  - Codelist already exists, skipping: {composite_key}')
            return 0
        
        # Create the codelist with original name (for search) but unique combination
        codelist = CodeList.objects.create(
            codelist_name=codelist_name,  # Keep original name for search
            source=source,
            project_title=project_title,
            ERAP_number=erap_number,
            author=author,
            codelist_description=f'Imported from GitHub. DOI: {doi_publication}' if doi_publication else 'Imported from GitHub',
            emis_dictionary_version=f'GitHub_{year_created}' if year_created else 'GitHub_imported'
        )
        
        self.stdout.write(f'  - Created new codelist: {codelist_name}')
        
        # Download and process the codelist file
        codes_imported = self.download_and_process_file(
            github_url, codelist, coding_system, download_dir
        )
        
        return codes_imported

    def download_and_process_file(self, github_url, codelist, coding_system, download_dir):
        """Download and process a codelist file from GitHub"""
        
        try:
            # Convert GitHub URL to raw URL if needed
            if 'github.com' in github_url and '/blob/' in github_url:
                raw_url = github_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
            else:
                raw_url = github_url
            
            # Add GitHub authentication if token is available
            headers = {}
            if 'GITHUB_TOKEN' in os.environ:
                headers['Authorization'] = f'token {os.environ["GITHUB_TOKEN"]}'
                self.stdout.write(f'  - Using GitHub authentication')
            
            self.stdout.write(f'  - Attempting to download: {raw_url}')
            
            # Try multiple branch names if the first fails
            urls_to_try = [raw_url]
            
            # If URL contains 'main', also try 'master'
            if '/main/' in raw_url:
                urls_to_try.append(raw_url.replace('/main/', '/master/'))
            # If URL contains 'master', also try 'main'  
            elif '/master/' in raw_url:
                urls_to_try.append(raw_url.replace('/master/', '/main/'))
            
            response = None
            successful_url = None
            
            for url_to_try in urls_to_try:
                self.stdout.write(f'  - Trying: {url_to_try}')
                
                try:
                    response = requests.get(url_to_try, timeout=30, headers=headers)
                    
                    if response.status_code == 200:
                        successful_url = url_to_try
                        break
                    elif response.status_code == 404:
                        self.stdout.write(f'    - 404 Not Found')
                        continue
                    elif response.status_code == 403:
                        self.stdout.write(f'    - 403 Access Denied')
                        continue
                    else:
                        self.stdout.write(f'    - HTTP {response.status_code}: {response.reason}')
                        continue
                        
                except requests.exceptions.RequestException as e:
                    self.stdout.write(f'    - Request failed: {str(e)}')
                    continue
            
            # If no URL worked, return 0
            if not successful_url or not response or response.status_code != 200:
                self.stdout.write(f'  - All URLs failed - Repository may be private or files moved')
                return 0
            
            # Check if we got actual CSV content or an error page
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' in content_type:
                self.stdout.write(f'  - Received HTML instead of CSV - likely an error page')
                return 0
            
            self.stdout.write(f'  - Successfully downloaded from: {successful_url}')
            
            # Determine file extension and save locally
            parsed_url = urlparse(successful_url)
            filename = os.path.basename(parsed_url.path)
            if not filename:
                filename = f"{codelist.codelist_name.replace(' ', '_')}.csv"
            
            local_path = os.path.join(download_dir, filename)
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            self.stdout.write(f'  - Downloaded: {filename} ({len(response.content)} bytes)')
            
            # Quick check if file has content
            if len(response.content) < 50:
                self.stdout.write(f'  - Warning: File is very small ({len(response.content)} bytes)')
            
            # Process the file
            codes_imported = self.process_codelist_file(local_path, codelist, coding_system)
            
            # Clean up downloaded file
            os.remove(local_path)
            
            return codes_imported
            
        except Exception as e:
            self.stdout.write(f'  - Error downloading/processing file: {str(e)}')
            return 0

    def process_codelist_file(self, file_path, codelist, coding_system):
        """Process a downloaded codelist file"""
        
        try:
            # Try to read the file with different encodings
            encodings = ['utf-8', 'latin-1', 'cp1252']
            df = None
            
            for encoding in encodings:
                try:
                    if file_path.endswith('.csv'):
                        df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='skip')
                    elif file_path.endswith('.txt'):
                        df = pd.read_csv(file_path, delimiter='\t', encoding=encoding, on_bad_lines='skip')
                    else:
                        # Try CSV first
                        df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='skip')
                    break
                except UnicodeDecodeError:
                    continue
            
            if df is None:
                self.stdout.write(self.style.ERROR(f'  Could not read file with any encoding'))
                return 0
            
            self.stdout.write(f'  File contains {len(df)} rows')
            
            # Try to identify key columns
            column_mapping = self.identify_columns(df.columns.tolist())
            
            if not column_mapping.get('med_code_id'):
                self.stdout.write(self.style.ERROR(f'  Could not identify code ID column'))
                self.stdout.write(f'  Available columns: {list(df.columns)}')
                return 0
            
            # Process codes
            codes_imported = 0
            codes_linked = 0
            
            for _, row in df.iterrows():
                try:
                    # Extract code data
                    med_code_id = str(row[column_mapping['med_code_id']]).strip()
                    
                    # Handle prefixed codes (remove 'a' or 'b' prefix if present)
                    if med_code_id.lower().startswith('a') and len(med_code_id) > 1:
                        med_code_id = med_code_id[1:]
                    
                    if not med_code_id or med_code_id.lower() in ['', 'nan', 'none', 'null']:
                        continue
                    
                    # Get term - handle nan values properly
                    term = 'Unknown'
                    if column_mapping.get('term'):
                        term_val = row[column_mapping['term']]
                        if pd.notna(term_val) and str(term_val).strip() not in ['nan', 'NaN', '', 'null']:
                            term = str(term_val).strip()
                    
                    # Get SNOMED ID - handle nan values and prefixes
                    snomed_ct_concept_id = ''
                    if column_mapping.get('snomed_ct_concept_id'):
                        snomed_val = row[column_mapping['snomed_ct_concept_id']]
                        if pd.notna(snomed_val) and str(snomed_val).strip() not in ['nan', 'NaN', '', 'null']:
                            snomed_ct_concept_id = str(snomed_val).strip()
                            # Handle 'b' prefix for SNOMED codes
                            if snomed_ct_concept_id.lower().startswith('b') and len(snomed_ct_concept_id) > 1:
                                snomed_ct_concept_id = snomed_ct_concept_id[1:]
                    
                    observations = None
                    if column_mapping.get('observations'):
                        try:
                            obs_val = row[column_mapping['observations']]
                            if pd.notna(obs_val) and str(obs_val).strip() not in ['nan', 'NaN', '', 'null']:
                                observations = int(float(obs_val))
                        except (ValueError, TypeError):
                            pass
                    
                    emis_category = ''
                    if column_mapping.get('emis_category'):
                        cat_val = row[column_mapping['emis_category']]
                        if pd.notna(cat_val) and str(cat_val).strip() not in ['nan', 'NaN', '', 'null']:
                            emis_category = str(cat_val).strip()
                    
                    # Set the source to Oxford_CPRD as requested
                    final_coding_system = coding_system or 'Oxford_CPRD'
                    
                    # Create or get the code
                    code, created = Code.objects.get_or_create(
                        med_code_id=med_code_id,
                        defaults={
                            'term': term,
                            'observations': observations,
                            'snomed_ct_concept_id': snomed_ct_concept_id,
                            'emis_category': emis_category,
                            'coding_system': final_coding_system
                        }
                    )
                    
                    if created:
                        codes_imported += 1
                    
                    # Link code to codelist
                    CodeListCode.objects.get_or_create(
                        code=code,
                        codelist=codelist
                    )
                    codes_linked += 1
                    
                except Exception as e:
                    continue
            
            self.stdout.write(f'  Imported {codes_imported} new codes, linked {codes_linked} codes to codelist')
            return codes_imported
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error processing file: {str(e)}'))
            return 0

    def identify_columns(self, columns):
        """Try to identify which columns contain which data"""
        
        column_mapping = {}
        
        # Print columns for debugging
        self.stdout.write(f'  Available columns: {columns}')
        
        # Convert column names to lowercase for easier matching
        lower_columns = [col.lower() for col in columns]
        
        # Look for code ID column - more comprehensive matching
        for i, col in enumerate(lower_columns):
            # Check for various code ID patterns
            if any(term in col for term in [
                'med_code_id', 'medcodeid', 'code_id', 'codeid', 'medcode', 
                'med_code', 'code', 'id'
            ]) and not any(exclude in col for exclude in ['snomed', 'concept']):
                column_mapping['med_code_id'] = columns[i]
                self.stdout.write(f'  Found med_code_id column: {columns[i]}')
                break
        
        # Look for term/description column
        for i, col in enumerate(lower_columns):
            if any(term in col for term in [
                'description', 'term', 'read_term', 'readterm', 'desc', 
                'label', 'name', 'text'
            ]):
                column_mapping['term'] = columns[i]
                self.stdout.write(f'  Found term column: {columns[i]}')
                break
        
        # Look for SNOMED column - more specific matching
        for i, col in enumerate(lower_columns):
            if any(term in col for term in [
                'snomed', 'concept_id', 'snomedct', 'snomed_ct', 
                'snomed_code', 'conceptid'
            ]):
                column_mapping['snomed_ct_concept_id'] = columns[i]
                self.stdout.write(f'  Found SNOMED column: {columns[i]}')
                break
        
        # Look for observations/frequency column
        for i, col in enumerate(lower_columns):
            if any(term in col for term in [
                'observations', 'freq', 'frequency', 'count', 
                'clinical_events', 'events', 'obs'
            ]):
                column_mapping['observations'] = columns[i]
                self.stdout.write(f'  Found observations column: {columns[i]}')
                break
        
        # Look for category column
        for i, col in enumerate(lower_columns):
            if any(term in col for term in [
                'category', 'emis_category', 'cat', 'type'
            ]):
                column_mapping['emis_category'] = columns[i]
                self.stdout.write(f'  Found category column: {columns[i]}')
                break
        
        return column_mapping