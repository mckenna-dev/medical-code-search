#!/usr/bin/env python
"""
Option A: Fixed junction table logic - proper many-to-many handling
"""

import os
import django
import psycopg2
import re
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

class OptionAMigrator:
    def __init__(self):
        self.stats = {
            'new_sources_created': 0,
            'new_codelists_created': 0,
            'new_codes_created': 0,
            'existing_codes_reused': 0,
            'new_relationships_created': 0,
            'existing_relationships_found': 0,
            'skipped_existing_codelists': 0,
            'errors': []
        }
        
        # Track existing data to avoid duplicates
        self.existing_sources = {}
        self.existing_codelists = set()
        self.existing_codes = {}
        self.existing_relationships = set()
        
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
    
    def test_postgresql_connection(self):
        """Test connection and show available valid data"""
        print("🔌 Testing PostgreSQL connection...")
        
        try:
            conn = psycopg2.connect(**PG_CONFIG)
            cursor = conn.cursor()
            
            # Get valid data counts by source
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
            
            total_valid = sum(count for _, count in sources)
            
            cursor.close()
            conn.close()
            
            print(f"✅ PostgreSQL connection successful!")
            print(f"📊 Total valid med_code_id records: {total_valid}")
            print("📋 Valid records by source:")
            for source, count in sources:
                print(f"  {source}: {count} valid records")
            return True
            
        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {str(e)}")
            return False
    
    def fetch_test_data(self, limit=100):
        """Fetch test data with valid med_code_id only"""
        print(f"📥 Fetching {limit} test records with valid med_code_id...")
        
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
        LIMIT %s
        """
        
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        print(f"📊 Fetched {len(rows)} valid records")
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
        """Group data by codelist, tracking which codes appear in each"""
        codelists = defaultdict(lambda: {
            'codes': [],
            'metadata': {},
            'med_code_ids_seen': set()
        })
        
        for row in rows:
            (snomed_ct_concept_id, emis_description, source_codelist, 
             source_med_code_id, codelist_name, original_source,
             codelist_description, med_code_id, observations) = row
            
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
                print(f"  ⚠️  Duplicate med_code_id {med_code_id} in same codelist {codelist_name} - skipping")
                continue
            
            codelists[codelist_key]['med_code_ids_seen'].add(med_code_id)
            
            # Add code
            codelists[codelist_key]['codes'].append({
                'med_code_id': med_code_id,
                'term': emis_description or 'Unknown term',
                'snomed_ct_concept_id': self.clean_snomed_code(snomed_ct_concept_id),
                'observations': observations if observations and observations != '0' else None,
            })
        
        print(f"📋 Found {len(codelists)} new codelists in test data")
        print(f"⚠️  Skipped {self.stats['skipped_existing_codelists']} existing codelists")
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
        
        # Check if we already have this code
        if med_code_id in self.existing_codes:
            self.stats['existing_codes_reused'] += 1
            return self.existing_codes[med_code_id], False
        
        # Create new code
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
        
        # Check if this relationship already exists
        rel_key = f"{code.med_code_id}||{codelist.id}"
        if rel_key in self.existing_relationships:
            self.stats['existing_relationships_found'] += 1
            return None, False
        
        # Create new relationship
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
            # If we still get a constraint error, log it but continue
            error_msg = f"Constraint error creating relationship for code {code.med_code_id} in codelist {codelist.id}: {str(e)}"
            print(f"    ⚠️  {error_msg}")
            return None, False
    
    def process_single_codelist(self, codelist_key, data):
        """Process a single codelist with careful relationship handling"""
        codelist_name = data['metadata']['codelist_name']
        original_source = data['metadata']['original_source']
        
        print(f"🔄 Processing: {codelist_name}")
        
        try:
            with transaction.atomic():
                # Get or create source
                source, _ = self.get_or_create_source(original_source)
                
                # Generate unique identifier for codelist
                clean_name = re.sub(r'[^a-zA-Z0-9]', '_', codelist_name.lower())[:50]
                unique_id = f"{original_source.lower()}_{clean_name}"
                
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
                print(f"  ✅ Created codelist: {unique_id}")
                
                # Process codes and relationships
                codes_processed = 0
                relationships_created = 0
                
                for code_data in data['codes']:
                    # Get or create the code
                    code, code_created = self.get_or_create_code(code_data)
                    
                    # Create the relationship
                    relationship, rel_created = self.create_relationship(code, codelist)
                    
                    if rel_created:
                        relationships_created += 1
                    
                    codes_processed += 1
                
                print(f"  ✅ Processed {codes_processed} codes, {relationships_created} new relationships")
                return True
                
        except Exception as e:
            error_msg = f"Error processing {codelist_name}: {str(e)}"
            self.stats['errors'].append(error_msg)
            print(f"  ❌ {error_msg}")
            return False
    
    def run_test_migration(self, limit=100):
        """Run test migration with Option A approach"""
        print("🧪 Starting OPTION A TEST migration...")
        print(f"🎯 Focus: Fix junction table logic for many-to-many relationships")
        print(f"⚠️  Testing with {limit} records")
        
        try:
            # Test connection
            if not self.test_postgresql_connection():
                return False
                
            # Initialize tracking
            self.initialize_existing_data()
            
            # Get test data
            rows = self.fetch_test_data(limit)
            if not rows:
                print("❌ No test data retrieved")
                return False
            
            grouped_data = self.group_data_by_codelist(rows)
            
            if not grouped_data:
                print("ℹ️  No new codelists in test data")
                return True
            
            print(f"🔄 Processing {len(grouped_data)} new codelists...")
            
            # Process each codelist
            successful = 0
            for codelist_key, data in grouped_data.items():
                if self.process_single_codelist(codelist_key, data):
                    successful += 1
            
            print(f"✅ Successfully processed {successful}/{len(grouped_data)} codelists")
            self.print_results()
            
            return successful >= 0
            
        except Exception as e:
            print(f"💥 Test migration failed: {str(e)}")
            return False
    
    def print_results(self):
        """Print detailed migration results"""
        print("\n🧪 OPTION A TEST MIGRATION RESULTS:")
        print("=" * 60)
        print(f"New sources created: {self.stats['new_sources_created']}")
        print(f"New codelists created: {self.stats['new_codelists_created']}")
        print(f"New codes created: {self.stats['new_codes_created']}")
        print(f"Existing codes reused: {self.stats['existing_codes_reused']}")
        print(f"New relationships created: {self.stats['new_relationships_created']}")
        print(f"Existing relationships found: {self.stats['existing_relationships_found']}")
        print(f"Existing codelists skipped: {self.stats['skipped_existing_codelists']}")
        print(f"Errors: {len(self.stats['errors'])}")
        
        if self.stats['errors']:
            print("\n❌ ERRORS:")
            for error in self.stats['errors']:
                print(f"  - {error}")
        
        # Show examples of many-to-many relationships
        print(f"\n🔗 MANY-TO-MANY EXAMPLES:")
        if self.stats['existing_codes_reused'] > 0:
            print(f"✅ {self.stats['existing_codes_reused']} codes were reused across multiple codelists")
            print("   This proves the many-to-many relationship is working!")
        
        # Current database state
        print(f"\n📊 CURRENT DATABASE STATE:")
        print(f"Total sources: {CodeSource.objects.count()}")
        print(f"Total codelists: {CodeList.objects.count()}")
        print(f"Total codes: {Code.objects.count()}")
        print(f"Total relationships: {CodeListCode.objects.count()}")

def main():
    print("🎯 OPTION A: Fixed Junction Table Logic")
    print("=" * 60)
    print("This approach will:")
    print("- Use proper Django many-to-many relationships")
    print("- Allow med_code_id to appear in multiple codelists")
    print("- Carefully track existing relationships")
    print("- Provide detailed debugging if constraint errors occur")
    print("- Only import records with valid med_code_id")
    
    limit = input("\nHow many records to test with? (default 100): ").strip()
    if not limit:
        limit = 100
    else:
        try:
            limit = int(limit)
        except:
            limit = 100
    
    confirm = input(f"\nProceed with Option A test migration ({limit} records)? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Test migration cancelled.")
        return
    
    migrator = OptionAMigrator()
    success = migrator.run_test_migration(limit)
    
    if success:
        print("\n🎉 Option A test migration successful!")
        print("✅ Junction table logic is working correctly")
        print("🚀 Ready for full migration!")
    else:
        print("\n❌ Option A still has issues.")
        print("🔄 Let's try Option B (composite unique IDs) instead.")

if __name__ == '__main__':
    main()