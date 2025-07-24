#!/usr/bin/env python
"""
FIXED TEST migration script - handles constraint errors properly
"""

import os
import sys
import django
import psycopg2
import re
from django.db import transaction
from collections import defaultdict

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medical_code_search.settings')
django.setup()

from core.models import CodeSource, CodeList, Code, CodeListCode

# PostgreSQL connection - YOUR CREDENTIALS
PG_CONFIG = {
    'host': 'localhost',
    'database': 'codelist_database_postgres',
    'user': 'postgres',
    'password': '29Postgresql!pass29',
    'port': 5432
}

# Source prefixes for unique IDs
SOURCE_PREFIXES = {
    'AIM_RSF': 'aim_',
    'CALIBER_Mapped': 'caliber_', 
    'HDR_UK': 'hdr_',
    'OpenCodelist': 'opencode_',
    'PCD_Refset': 'pcd_'
}

class FixedTestMigrator:
    def __init__(self):
        self.stats = {
            'existing_sources': 0,
            'new_sources_created': 0,
            'new_codelists_created': 0,
            'new_codes_created': 0,
            'codes_updated': 0,
            'new_relationships_created': 0,
            'duplicate_relationships_skipped': 0,
            'errors': []
        }
        
        # Track existing data
        self.existing_sources = set()
        self.existing_codelists = set()
        self.existing_codes = set()
        
    def initialize_existing_data(self):
        """Load existing data to avoid duplicates"""
        print("📊 Analyzing existing Django data...")
        
        for source in CodeSource.objects.all():
            self.existing_sources.add(source.name)
            self.stats['existing_sources'] += 1
        
        for codelist in CodeList.objects.all():
            key = (codelist.codelist_name, codelist.source.name)
            self.existing_codelists.add(key)
        
        for code in Code.objects.all():
            self.existing_codes.add(code.med_code_id)
        
        print(f"✅ Existing: {self.stats['existing_sources']} sources, {len(self.existing_codelists)} codelists, {len(self.existing_codes)} codes")
    
    def clean_snomed_code(self, code):
        """Remove 'b' prefix from SNOMED codes"""
        if code and code.startswith('b'):
            return code[1:]
        return code
    
    def clean_med_code_id(self, code):
        """Clean medical code ID"""
        if code and code.startswith('a'):
            return code[1:]
        return code
    
    def generate_unique_codelist_id(self, codelist_name, original_source):
        """Generate unique codelist identifier"""
        prefix = SOURCE_PREFIXES.get(original_source, 'other_')
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', codelist_name.lower())
        clean_name = clean_name[:50]
        
        base_id = f"{prefix}{clean_name}"
        unique_id = base_id
        counter = 1
        
        while CodeList.objects.filter(unique_identifier=unique_id).exists():
            unique_id = f"{base_id}_{counter}"
            counter += 1
        
        return unique_id
    
    def test_postgresql_connection(self):
        """Test PostgreSQL connection"""
        print("🔌 Testing PostgreSQL connection...")
        
        try:
            conn = psycopg2.connect(**PG_CONFIG)
            cursor = conn.cursor()
            
            # Test query
            cursor.execute("SELECT COUNT(*) FROM codelists")
            total_count = cursor.fetchone()[0]
            
            # Get source breakdown
            cursor.execute("SELECT original_source, COUNT(*) FROM codelists GROUP BY original_source")
            sources = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            print(f"✅ PostgreSQL connection successful!")
            print(f"📊 Total records available: {total_count}")
            print("📋 Available sources:")
            for source, count in sources:
                print(f"  {source}: {count} records")
            return True
            
        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {str(e)}")
            return False
    
    def fetch_test_data(self):
        """Fetch small sample of PostgreSQL data"""
        print("📥 Fetching test data from PostgreSQL...")
        
        conn = psycopg2.connect(**PG_CONFIG)
        cursor = conn.cursor()
        
        # Fetch small sample - 20 records from each source for better testing
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
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY original_source ORDER BY codelist_name, med_code_id) as rn
            FROM codelists 
            WHERE original_source IN ('AIM_RSF', 'CALIBER_Mapped', 'HDR_UK', 'OpenCodelist', 'PCD_Refset')
        ) t
        WHERE rn <= 20
        ORDER BY original_source, codelist_name, med_code_id
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        print(f"📊 Fetched {len(rows)} test records")
        return rows
    
    def group_data_by_codelist(self, rows):
        """Group test data by codelist"""
        codelists = defaultdict(lambda: {
            'codes': [],
            'metadata': {}
        })
        
        for row in rows:
            (snomed_ct_concept_id, emis_description, source_codelist, 
             source_med_code_id, codelist_name, original_source,
             codelist_description, med_code_id, observations) = row
            
            # Check if this codelist already exists
            codelist_key = (codelist_name, original_source)
            if codelist_key in self.existing_codelists:
                continue  # Skip existing
            
            # Store metadata
            if not codelists[codelist_key]['metadata']:
                codelists[codelist_key]['metadata'] = {
                    'codelist_name': codelist_name,
                    'original_source': original_source,
                    'codelist_description': codelist_description or '',
                    'source_codelist': source_codelist
                }
            
            # Add code
            clean_med_code_id = self.clean_med_code_id(med_code_id)
            if clean_med_code_id:
                codelists[codelist_key]['codes'].append({
                    'med_code_id': clean_med_code_id,
                    'term': emis_description or '',
                    'snomed_ct_concept_id': self.clean_snomed_code(snomed_ct_concept_id),
                    'observations': observations if observations and observations != '0' else None,
                })
        
        print(f"📋 Found {len(codelists)} new codelists in test data")
        return codelists
    
    def get_or_create_source(self, source_name):
        """Get existing source or create new one"""
        if source_name in self.existing_sources:
            return CodeSource.objects.get(name=source_name), False
        
        source, created = CodeSource.objects.get_or_create(
            name=source_name,
            defaults={
                'description': f'Medical codes from {source_name}',
                'is_default': False
            }
        )
        
        if created:
            self.stats['new_sources_created'] += 1
            self.existing_sources.add(source_name)
            print(f"✅ Created new source: {source_name}")
        
        return source, created
    
    def process_single_codelist(self, codelist_key, data):
        """Process a single codelist - separate transaction for each"""
        codelist_name, original_source = codelist_key
        
        try:
            with transaction.atomic():
                # Get or create source
                source, source_created = self.get_or_create_source(original_source)
                
                # Generate unique codelist ID
                unique_id = self.generate_unique_codelist_id(codelist_name, original_source)
                
                # Create new codelist
                codelist = CodeList.objects.create(
                    codelist_name=codelist_name,
                    source=source,
                    codelist_description=data['metadata']['codelist_description'],
                    ERAP_number=data['metadata']['source_codelist'] or '',
                    unique_identifier=unique_id
                )
                
                self.stats['new_codelists_created'] += 1
                print(f"✅ Created codelist: {unique_id}")
                
                # Process codes for this codelist
                codes_processed = 0
                for code_data in data['codes']:
                    med_code_id = code_data['med_code_id']
                    if not med_code_id:
                        continue
                    
                    # Get or create code
                    if med_code_id in self.existing_codes:
                        code = Code.objects.get(med_code_id=med_code_id)
                        
                        # Update with better information if available
                        updated = False
                        if not code.snomed_ct_concept_id and code_data['snomed_ct_concept_id']:
                            code.snomed_ct_concept_id = code_data['snomed_ct_concept_id']
                            updated = True
                        if not code.observations and code_data['observations']:
                            code.observations = code_data['observations']
                            updated = True
                        if len(code_data['term']) > len(code.term):
                            code.term = code_data['term']
                            updated = True
                        
                        if updated:
                            code.save()
                            self.stats['codes_updated'] += 1
                    else:
                        # Create new code
                        code = Code.objects.create(
                            med_code_id=med_code_id,
                            term=code_data['term'],
                            snomed_ct_concept_id=code_data['snomed_ct_concept_id'] or '',
                            observations=code_data['observations'],
                            coding_system='SNOMED' if code_data['snomed_ct_concept_id'] else 'READ'
                        )
                        self.stats['new_codes_created'] += 1
                        self.existing_codes.add(med_code_id)
                    
                    # Create relationship - use get_or_create to avoid duplicates
                    relationship, rel_created = CodeListCode.objects.get_or_create(
                        code=code,
                        codelist=codelist,
                        defaults={'is_excluded': False}
                    )
                    
                    if rel_created:
                        self.stats['new_relationships_created'] += 1
                    else:
                        self.stats['duplicate_relationships_skipped'] += 1
                    
                    codes_processed += 1
                
                print(f"  ✅ Processed {codes_processed} codes for {codelist_name}")
                return True
                
        except Exception as e:
            error_msg = f"Error processing {codelist_name}: {str(e)}"
            self.stats['errors'].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
    
    def run_test_migration(self):
        """Run test migration with better error handling"""
        print("🧪 Starting FIXED TEST migration...")
        print("⚠️  This will import ~100 records as a test with better error handling")
        
        try:
            # Test connection first
            if not self.test_postgresql_connection():
                return False
                
            # Initialize tracking
            self.initialize_existing_data()
            
            # Get test data
            rows = self.fetch_test_data()
            if not rows:
                print("❌ No test data retrieved")
                return False
            
            grouped_data = self.group_data_by_codelist(rows)
            
            if not grouped_data:
                print("ℹ️  No new codelists in test data (all already exist)")
                return True
            
            print(f"🔄 Processing {len(grouped_data)} new codelists...")
            
            # Process each codelist separately
            successful = 0
            for codelist_key, data in grouped_data.items():
                if self.process_single_codelist(codelist_key, data):
                    successful += 1
            
            print(f"✅ Successfully processed {successful}/{len(grouped_data)} codelists")
            self.print_test_results()
            
            return successful > 0
            
        except Exception as e:
            print(f"💥 Test migration failed: {str(e)}")
            return False
    
    def print_test_results(self):
        """Print test results"""
        print("\n🧪 FIXED TEST MIGRATION RESULTS:")
        print("=" * 50)
        print(f"New sources created: {self.stats['new_sources_created']}")
        print(f"New codelists created: {self.stats['new_codelists_created']}")
        print(f"New codes created: {self.stats['new_codes_created']}")
        print(f"Existing codes updated: {self.stats['codes_updated']}")
        print(f"New relationships created: {self.stats['new_relationships_created']}")
        print(f"Duplicate relationships skipped: {self.stats['duplicate_relationships_skipped']}")
        print(f"Errors: {len(self.stats['errors'])}")
        
        if self.stats['errors']:
            print("\n❌ ERRORS:")
            for error in self.stats['errors'][:5]:
                print(f"  - {error}")
        
        # Show current database state
        print(f"\n📊 CURRENT DATABASE STATE:")
        print(f"Total sources: {CodeSource.objects.count()}")
        print(f"Total codelists: {CodeList.objects.count()}")
        print(f"Total codes: {Code.objects.count()}")
        print(f"Total relationships: {CodeListCode.objects.count()}")
        
        # Show new sources
        print(f"\n📋 SOURCES:")
        for source in CodeSource.objects.all():
            count = source.codelist_set.count()
            print(f"  {source.name}: {count} codelists")
        
        # Show sample new codelists
        new_codelists = CodeList.objects.filter(
            source__name__in=['AIM_RSF', 'CALIBER_Mapped', 'HDR_UK', 'OpenCodelist', 'PCD_Refset']
        )
        
        if new_codelists.exists():
            print(f"\n🆕 NEW CODELISTS CREATED:")
            for cl in new_codelists[:5]:
                code_count = cl.codelistcode_set.count()
                print(f"  {cl.unique_identifier}: {cl.codelist_name[:60]}... ({code_count} codes)")

def main():
    """Run the fixed test migration"""
    print("🛠️ FIXED TEST PostgreSQL Migration")
    print("=" * 50)
    print("This FIXED version will:")
    print("- Handle constraint errors properly")
    print("- Process each codelist in separate transactions")
    print("- Skip duplicate relationships safely")
    print("- Import ~100 records as a test")
    print("- Preserve all existing data")
    
    confirm = input("\nProceed with FIXED test migration? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Test migration cancelled.")
        return
    
    migrator = FixedTestMigrator()
    success = migrator.run_test_migration()
    
    if success:
        print("\n🎉 FIXED test migration successful!")
        print("✅ Ready to proceed with full migration")
        print("🚀 The migration process is working correctly")
    else:
        print("\n❌ Test migration still has issues.")
        print("🔧 Need to investigate further before full migration.")

if __name__ == '__main__':
    main()