from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Code, EmisCode

class Command(BaseCommand):
    help = 'Update existing codes with observations and SNOMED data from EMIS dictionary'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000,
                          help='Batch size for updates (default: 1000)')
        parser.add_argument('--dry-run', action='store_true',
                          help='Show what would be updated without making changes')

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')
        
        # Get statistics
        total_codes = Code.objects.count()
        total_emis = EmisCode.objects.count()
        
        self.stdout.write(f'📊 Current state:')
        self.stdout.write(f'  Research codes: {total_codes:,}')
        self.stdout.write(f'  EMIS dictionary: {total_emis:,}')
        
        # Find potential matches
        code_ids = set(Code.objects.values_list('med_code_id', flat=True))
        emis_ids = set(EmisCode.objects.values_list('med_code_id', flat=True))
        matches = code_ids.intersection(emis_ids)
        
        self.stdout.write(f'  Potential matches: {len(matches):,}')
        
        if not matches:
            self.stdout.write(self.style.WARNING('❌ No matching codes found'))
            return
        
        # Analyze what needs updating
        self.analyze_update_needs(matches)
        
        if not dry_run:
            confirm = input(f'\nProceed with updating {len(matches):,} codes? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write('Update cancelled.')
                return
        
        # Perform updates
        updated_count = self.update_codes(matches, batch_size, dry_run)
        
        if dry_run:
            self.stdout.write(f'🔍 DRY RUN: Would update {updated_count:,} codes')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Successfully updated {updated_count:,} codes')
            )

    def analyze_update_needs(self, matching_ids):
        """Analyze what updates are needed"""
        self.stdout.write(f'\n📋 Analyzing update requirements...')
        
        # Check current data quality
        codes_with_obs = Code.objects.filter(
            med_code_id__in=matching_ids
        ).exclude(observations__isnull=True).count()
        
        codes_with_snomed = Code.objects.filter(
            med_code_id__in=matching_ids
        ).exclude(snomed_ct_concept_id='').count()
        
        # Check EMIS data availability
        emis_with_obs = EmisCode.objects.filter(
            med_code_id__in=matching_ids
        ).exclude(observations__isnull=True).count()
        
        emis_with_snomed = EmisCode.objects.filter(
            med_code_id__in=matching_ids
        ).exclude(snomed_ct_concept_id='').count()
        
        self.stdout.write(f'  Current codes with observations: {codes_with_obs:,}')
        self.stdout.write(f'  Current codes with SNOMED: {codes_with_snomed:,}')
        self.stdout.write(f'  EMIS records with observations: {emis_with_obs:,}')
        self.stdout.write(f'  EMIS records with SNOMED: {emis_with_snomed:,}')
        
        # Potential improvements
        obs_improvements = emis_with_obs - codes_with_obs
        snomed_improvements = emis_with_snomed - codes_with_snomed
        
        if obs_improvements > 0:
            self.stdout.write(f'  📈 Can improve observations for ~{obs_improvements:,} codes')
        if snomed_improvements > 0:
            self.stdout.write(f'  📈 Can improve SNOMED for ~{snomed_improvements:,} codes')

    def update_codes(self, matching_ids, batch_size, dry_run):
        """Update codes with EMIS data"""
        updated_count = 0
        processed = 0
        
        # Process in batches
        matching_list = list(matching_ids)
        
        for i in range(0, len(matching_list), batch_size):
            batch_ids = matching_list[i:i + batch_size]
            
            if not dry_run:
                batch_updated = self.update_batch(batch_ids)
                updated_count += batch_updated
            else:
                # For dry run, just count potential updates
                batch_updated = self.count_potential_updates(batch_ids)
                updated_count += batch_updated
            
            processed += len(batch_ids)
            
            # Progress update
            if processed % (batch_size * 10) == 0:
                self.stdout.write(f'📊 Processed {processed:,}/{len(matching_list):,} codes')
        
        return updated_count
    
    def update_batch(self, batch_ids):
        """Update a batch of codes"""
        updated_count = 0
        
        try:
            with transaction.atomic():
                for med_code_id in batch_ids:
                    try:
                        code = Code.objects.get(med_code_id=med_code_id)
                        emis = EmisCode.objects.get(med_code_id=med_code_id)
                        
                        updated = False
                        
                        # Update observations if missing or EMIS has more
                        if not code.observations and emis.observations:
                            code.observations = emis.observations
                            updated = True
                        elif (code.observations and emis.observations and 
                              emis.observations > code.observations):
                            code.observations = emis.observations
                            updated = True
                        
                        # Update SNOMED if missing or empty
                        if not code.snomed_ct_concept_id and emis.snomed_ct_concept_id:
                            code.snomed_ct_concept_id = emis.snomed_ct_concept_id
                            updated = True
                        
                        # Update coding system if it's more specific
                        if code.coding_system in ['READ_V2', 'OTHER'] and emis.snomed_ct_concept_id:
                            code.coding_system = 'SNOMED_CT'
                            updated = True
                        
                        if updated:
                            code.save()
                            updated_count += 1
                            
                    except (Code.DoesNotExist, EmisCode.DoesNotExist):
                        continue
                    except Exception as e:
                        self.stdout.write(f'⚠️  Error updating {med_code_id}: {str(e)}')
                        continue
                        
        except Exception as e:
            self.stdout.write(f'❌ Batch update failed: {str(e)}')
        
        return updated_count
    
    def count_potential_updates(self, batch_ids):
        """Count how many codes would be updated (for dry run)"""
        count = 0
        
        for med_code_id in batch_ids:
            try:
                code = Code.objects.get(med_code_id=med_code_id)
                emis = EmisCode.objects.get(med_code_id=med_code_id)
                
                would_update = False
                
                # Check if observations would be updated
                if not code.observations and emis.observations:
                    would_update = True
                elif (code.observations and emis.observations and 
                      emis.observations > code.observations):
                    would_update = True
                
                # Check if SNOMED would be updated
                if not code.snomed_ct_concept_id and emis.snomed_ct_concept_id:
                    would_update = True
                
                if would_update:
                    count += 1
                    
            except (Code.DoesNotExist, EmisCode.DoesNotExist):
                continue
        
        return count