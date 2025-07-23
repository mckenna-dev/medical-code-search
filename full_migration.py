#!/usr/bin/env python
"""
FULL MIGRATION: Import all 256K valid med_code_id records
Based on successful Option A test
"""

import os
import django
import psycopg2
import re
import time
from django.db import transaction
from collections import defaultdict

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medical_code_search.settings')
django.setup()

from core.models import CodeSource, CodeList, Code, CodeListCode

# PostgreSQL connection
PG_CONFIG = {
    'host': 'localhost',
    'database': 'codelist_database_postgres',
    'user': 'postgres',
    'password': '29Postgresql!pass29',
    'port': 5432
}

class FullMigrator:
    def __init__(self):
        self.stats = {
            'new_sources_created': 0,
            'new_codelists_created': 0,
            'new_codes_created': 0,
            'existing_codes_reused': 0,
            'new_relationships_created': 0,
            'existing_relationships_found': 0,
            'skipped_existing_codelists': 0,
            'duplicates_skipped': 0,
            'errors': [],
            'processed_records': 0,
            'total_records': 0
        }
        
        # Track existing data
        self.existing_sources = {}
        self.existing_codelists = set()
        self.existing_codes = {}
        self.existing_relationships = set()
        
        # Timing
        self.start_time = None
        self.last_progress_time = None
        
    def initialize_existing_data(self):
        """Load existing data to avoid duplicates"""
        print("📊 Analyzing existing Django data...")
        
        # Load existing sources
        for source in CodeSource.objects.all():
            self.existing_sources[source.name] = source
        
        # Load existing codelists
        for codelist in CodeList.objects.all():
            key = f"{codelist.codelist_name}||{codelist.source.name}"
            self.existing_codelists.add(key)
        
        # Load existing codes
        for code in Code.objects.all():
            self.existing_codes[code.med_code_id] = code
        
        # Load existing relationships
        for rel in CodeListCode.objects.all():
            rel_key = f"{rel.code.med_code_id}||{rel.codelist.id}"
            self.existing_relationships.add(rel_key)
        
        print(f"✅ Existing: {len(self.existing_sources)} sources, {len(self.existing_codelists)} codelists, {len(self.existing_codes)} codes, {len(self.existing_relationships)} relationships")
    
    def get_total_records(self):
        """Get total count of valid records for progress tracking"""
        print("📊 Counting total valid records...")
        
        conn = psycopg2.connect(**PG_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM codelists 
            WHERE med_code_id IS NOT NULL 
              AND med_code_id != '' 
              AND med_code_id != '0'
        """)
        total = cursor.fetchone()[0]
        
        # Get breakdown by source
        cursor.execute("""
            SELECT original_source, COUNT(*) as valid_count
            FROM codelists 
            WHERE med_code_id IS NOT NULL 
              AND med_code_id != '' 
              AND med_code_id != '0'
            GROUP BY original_source 
            ORDER BY valid_count DESC
        """)
        sources = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        print(f"📊 Total valid records to import: {total:,}")
        print("📋 By source:")
        for source, count in sources:
            print(f"  {source}: {count:,} records")
        
        self.stats['total_records'] = total
        return total
    
    def fetch_batch_data(self, offset=0, batch_size=5000):
        """Fetch a batch of data for processing"""
        conn = psycopg2.connect(**PG_CONFIG)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            snomed_ct_concept_id,
            emis_description, 
            source_codelist,
            source_med_code_id,
            codelist_name,
            original_source,
            codelist_description,
            med_code_id,
            observations
        FROM codelists 
        WHERE med_code_id IS NOT NULL 
          AND med_code_id != '' 
          AND med_code_id != '0'
        ORDER BY original_source, codelist_name, med_code_id
        LIMIT %s OFFSET %s
        """
        
        cursor.execute(query, (batch_size, offset))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return rows
    
    def clean_snomed_code(self, code):
        """Remove 'b' prefix from SNOMED codes"""
        if not code:
            return ''
        code = str(code).strip()
        if code.startswith('b'):
            return code[1:]
        return code
    
    def group_data_by_codelist(self, rows):
        """Group data by codelist, tracking duplicates"""
        codelists = defaultdict(lambda: {
            'codes': [],
            'metadata': {},
            'med_code_ids_seen': set()
        })
        
        for row in rows:
            (snomed_ct_concept_id, emis_description, source_codelist, 
             source_med_code_id, codelist_name, original_source,
             codelist_description, med_code_id, observations) = row
            
            self.stats['processed_records'] += 1
            
            # Skip if no codelist name
            if not codelist_name:
                continue
                
            codelist_key = f"{codelist_name}||{original_source}"
            
            # Skip if this codelist already exists in Django
            if codelist_key in self.existing_codelists:
                self.stats['skipped_existing_codelists'] += 1
                continue
            
            # Store metadata
            if not codelists[codelist_key]['metadata']:
                codelists[codelist_key]['metadata'] = {
                    'codelist_name': codelist_name,
                    'original_source': original_source,
                    'codelist_description': codelist_description or '',
                    'source_codelist': source_codelist or ''
                }
            
            # Check for duplicate med_code_id within the same codelist in this batch
            if med_code_id in codelists[codelist_key]['med_code_ids_seen']:
                self.stats['duplicates_skipped'] += 1
                continue
            
            codelists[codelist_key]['med_code_ids_seen'].add(med_code_id)
            
            # Add code
            codelists[codelist_key]['codes'].append({
                'med_code_id': med_code_id,
                'term': emis_description or 'Unknown term',
                'snomed_ct_concept_id': self.clean_snomed_code(snomed_ct_concept_id),
                'observations': observations if observations and observations != '0' else None,
            })
        
        return codelists
    
    def get_or_create_source(self, source_name):
        """Get existing source or create new one"""
        if source_name in self.existing_sources:
            return self.existing_sources[source_name], False
        
        source, created = CodeSource.objects.get_or_create(
            name=source_name,
            defaults={
                'description': f'Medical codes from {source_name}',
                'is_default': False
            }
        )
        
        if created:
            self.stats['new_sources_created'] += 1
            self.existing_sources[source_name] = source
            print(f"✅ Created new source: {source_name}")
        
        return source, created
    
    def get_or_create_code(self, code_data):
        """Get existing code or create new one"""
        med_code_id = code_data['med_code_id']
        
        if med_code_id in self.existing_codes:
            self.stats['existing_codes_reused'] += 1
            return self.existing_codes[med_code_id], False
        
        code = Code.objects.create(
            med_code_id=med_code_id,
            term=code_data['term'],
            snomed_ct_concept_id=code_data['snomed_ct_concept_id'] or '',
            observations=code_data['observations'],
            coding_system='READ_V2'
        )
        
        self.stats['new_codes_created'] += 1
        self.existing_codes[med_code_id] = code
        return code, True
    
    def create_relationship(self, code, codelist):
        """Create code-codelist relationship if it doesn't exist"""
        rel_key = f"{code.med_code_id}||{codelist.id}"
        if rel_key in self.existing_relationships:
            self.stats['existing_relationships_found'] += 1
            return None, False
        
        try:
            relationship = CodeListCode.objects.create(
                code=code,
                codelist=codelist,
                is_excluded=False
            )
            self.stats['new_relationships_created'] += 1
            self.existing_relationships.add(rel_key)
            return relationship, True
            
        except Exception as e:
            error_msg = f"Constraint error for code {code.med_code_id} in codelist {codelist.id}: {str(e)}"
            self.stats['errors'].append(error_msg)
            return None, False
    
    def process_batch_codelists(self, codelists):
        """Process a batch of codelists"""
        successful = 0
        
        for codelist_key, data in codelists.items():
            try:
                with transaction.atomic():
                    codelist_name = data['metadata']['codelist_name']
                    original_source = data['metadata']['original_source']
                    
                    # Get or create source
                    source, _ = self.get_or_create_source(original_source)
                    
                    # Generate unique identifier
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', codelist_name.lower())[:50]
                    unique_id = f"{original_source.lower()}_{clean_name}"
                    
                    # Check if codelist with this unique_id already exists
                    if CodeList.objects.filter(unique_identifier=unique_id).exists():
                        counter = 1
                        while CodeList.objects.filter(unique_identifier=f"{unique_id}_{counter}").exists():
                            counter += 1
                        unique_id = f"{unique_id}_{counter}"
                    
                    # Create codelist
                    codelist = CodeList.objects.create(
                        codelist_name=codelist_name,
                        source=source,
                        codelist_description=data['metadata']['codelist_description'],
                        ERAP_number=data['metadata']['source_codelist'],
                        unique_identifier=unique_id,
                        project_title=f'Imported from {original_source}',
                        author='PostgreSQL Import'
                    )
                    
                    self.stats['new_codelists_created'] += 1
                    
                    # Process codes and relationships
                    for code_data in data['codes']:
                        code, _ = self.get_or_create_code(code_data)
                        self.create_relationship(code, codelist)
                    
                    successful += 1
                    
            except Exception as e:
                error_msg = f"Error processing {codelist_name}: {str(e)}"
                self.stats['errors'].append(error_msg)
                continue
        
        return successful
    
    def show_progress(self, force=False):
        """Show progress update"""
        current_time = time.time()
        
        # Show progress every 30 seconds or when forced
        if not force and self.last_progress_time and (current_time - self.last_progress_time) < 30:
            return
        
        self.last_progress_time = current_time
        elapsed = current_time - self.start_time
        
        if self.stats['total_records'] > 0:
            progress_pct = (self.stats['processed_records'] / self.stats['total_records']) * 100
            
            if self.stats['processed_records'] > 0:
                records_per_sec = self.stats['processed_records'] / elapsed
                eta_seconds = (self.stats['total_records'] - self.stats['processed_records']) / records_per_sec
                eta_mins = eta_seconds / 60
                
                print(f"📊 Progress: {self.stats['processed_records']:,}/{self.stats['total_records']:,} ({progress_pct:.1f}%) | "
                      f"Speed: {records_per_sec:.0f} rec/sec | ETA: {eta_mins:.1f} mins")
            else:
                print(f"📊 Progress: {self.stats['processed_records']:,}/{self.stats['total_records']:,} ({progress_pct:.1f}%)")
    
    def run_full_migration(self, batch_size=5000):
        """Run the full migration in batches"""
        print("🚀 Starting FULL MIGRATION...")
        print(f"🎯 Importing all valid med_code_id records in batches of {batch_size:,}")
        
        self.start_time = time.time()
        self.last_progress_time = self.start_time
        
        try:
            # Get total count
            total_records = self.get_total_records()
            if total_records == 0:
                print("❌ No valid records found")
                return False
            
            # Initialize tracking
            self.initialize_existing_data()
            
            print(f"\n🔄 Processing {total_records:,} records in batches...")
            
            offset = 0
            batch_num = 1
            total_codelists_processed = 0
            
            while offset < total_records:
                print(f"\n📦 Batch {batch_num} (records {offset:,}-{min(offset + batch_size, total_records):,})")
                
                # Fetch batch
                rows = self.fetch_batch_data(offset, batch_size)
                if not rows:
                    break
                
                # Group by codelist
                codelists = self.group_data_by_codelist(rows)
                
                # Process codelists
                if codelists:
                    successful = self.process_batch_codelists(codelists)
                    total_codelists_processed += successful
                    print(f"  ✅ Processed {successful} codelists in batch {batch_num}")
                
                # Show progress
                self.show_progress()
                
                offset += batch_size
                batch_num += 1
                
                # Small delay to avoid overwhelming the database
                time.sleep(0.1)
            
            # Final progress
            self.show_progress(force=True)
            
            print(f"\n🎉 Full migration completed!")
            print(f"📊 Total codelists processed: {total_codelists_processed}")
            self.print_final_results()
            
            return True
            
        except Exception as e:
            print(f"💥 Full migration failed: {str(e)}")
            self.print_final_results()
            return False
    
    def print_final_results(self):
        """Print comprehensive final results"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        print("\n🎯 FULL MIGRATION RESULTS:")
        print("=" * 80)
        print(f"⏱️  Total time: {elapsed/60:.1f} minutes")
        print(f"📊 Records processed: {self.stats['processed_records']:,}/{self.stats['total_records']:,}")
        print(f"🆕 New sources created: {self.stats['new_sources_created']}")
        print(f"📋 New codelists created: {self.stats['new_codelists_created']}")
        print(f"🆕 New codes created: {self.stats['new_codes_created']:,}")
        print(f"♻️  Existing codes reused: {self.stats['existing_codes_reused']:,}")
        print(f"🔗 New relationships created: {self.stats['new_relationships_created']:,}")
        print(f"⚠️  Duplicates skipped: {self.stats['duplicates_skipped']:,}")
        print(f"⚠️  Existing codelists skipped: {self.stats['skipped_existing_codelists']:,}")
        print(f"❌ Errors: {len(self.stats['errors'])}")
        
        if self.stats['errors']:
            print("\n❌ SAMPLE ERRORS (first 10):")
            for error in self.stats['errors'][:10]:
                print(f"  - {error}")
        
        # Final database state
        print(f"\n📊 FINAL DATABASE STATE:")
        print(f"Sources: {CodeSource.objects.count()}")
        print(f"Codelists: {CodeList.objects.count():,}")
        print(f"Codes: {Code.objects.count():,}")
        print(f"Relationships: {CodeListCode.objects.count():,}")
        
        # Performance stats
        if elapsed > 0:
            records_per_sec = self.stats['processed_records'] / elapsed
            print(f"\n⚡ Performance: {records_per_sec:.0f} records/second")

def main():
    print("🚀 FULL POSTGRESQL MIGRATION")
    print("=" * 80)
    print("This will import ALL 256K+ valid med_code_id records")
    print("Based on successful Option A test results")
    print("\nEstimated time: 15-30 minutes")
    print("Database size will increase significantly")
    
    batch_size = input("\nBatch size (default 5000): ").strip()
    if not batch_size:
        batch_size = 5000
    else:
        try:
            batch_size = int(batch_size)
        except:
            batch_size = 5000
    
    print(f"\n⚠️  This will:")
    print(f"- Process ~256K records in batches of {batch_size:,}")
    print(f"- Create hundreds of new codelists")
    print(f"- Take 15-30 minutes to complete")
    print(f"- Significantly increase database size")
    
    confirm = input(f"\nProceed with FULL migration? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Full migration cancelled.")
        return
    
    migrator = FullMigrator()
    success = migrator.run_full_migration(batch_size)
    
    if success:
        print("\n🎉 FULL MIGRATION SUCCESSFUL!")
        print("✅ All valid records imported")
        print("🎯 Your medical codelist database is now complete!")
    else:
        print("\n❌ Full migration had issues.")
        print("Check the error log above for details.")

if __name__ == '__main__':
    main()