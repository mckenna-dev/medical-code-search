import re
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import CodeSource, CodeList

class Command(BaseCommand):
    help = 'Populate unique identifiers for existing codelists'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )

    def handle(self, *args, **options):
        self.stdout.write("🏷️ Unique Identifier Population")
        self.stdout.write("=" * 40)
        
        # Show current state
        total_codelists = CodeList.objects.count()
        
        # Check if unique_identifier field exists
        try:
            with_ids = CodeList.objects.exclude(
                unique_identifier__isnull=True
            ).exclude(unique_identifier='').count()
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error: unique_identifier field not found!")
            )
            self.stdout.write(
                self.style.ERROR("Please add the unique_identifier field to your CodeList model first:")
            )
            self.stdout.write("unique_identifier = models.CharField(max_length=100, blank=True, null=True, unique=True)")
            self.stdout.write("Then run: python manage.py makemigrations && python manage.py migrate")
            return
        
        self.stdout.write(f"Total codelists: {total_codelists}")
        self.stdout.write(f"With unique IDs: {with_ids}")
        self.stdout.write(f"Missing IDs: {total_codelists - with_ids}")
        
        if total_codelists - with_ids == 0:
            self.stdout.write(
                self.style.SUCCESS("✅ All codelists already have unique identifiers!")
            )
            return
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING("🔍 DRY RUN - No changes will be made")
            )
            self.show_preview()
            return
        
        # Confirm before proceeding
        if not options.get('verbosity', 1) == 0:
            try:
                confirm = input("\nProceed with generating unique identifiers? (yes/no): ")
                if confirm.lower() != 'yes':
                    self.stdout.write("Operation cancelled.")
                    return
            except:
                # Handle case where input() doesn't work
                self.stdout.write("Proceeding with unique ID generation...")
        
        self.populate_unique_identifiers()

    def generate_unique_identifier(self, codelist):
        """Generate unique identifier for a codelist"""
        source_prefixes = {
            'CPRD': 'cprd_',
            'AIM_RSF': 'aim_',
            'CALIBER_Mapped': 'caliber_',
            'HDR_UK': 'hdr_',
            'OpenCodelist': 'opencode_',
            'PCD_Refset': 'pcd_',
        }
        
        # Get prefix for this source
        source_name = codelist.source.name
        prefix = source_prefixes.get(source_name, source_name.lower()[:3] + '_')
        
        # Create clean name from codelist name
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', codelist.codelist_name.lower())
        clean_name = clean_name[:50]  # Limit length
        
        # Create base ID
        base_id = f"{prefix}{clean_name}"
        unique_id = base_id
        counter = 1
        
        # Ensure uniqueness
        while CodeList.objects.filter(unique_identifier=unique_id).exists():
            unique_id = f"{base_id}_{counter}"
            counter += 1
        
        return unique_id

    def show_preview(self):
        """Show preview of what would be generated"""
        self.stdout.write("\n📋 Preview of unique identifiers that would be generated:")
        
        codelists_without_id = CodeList.objects.filter(
            unique_identifier__isnull=True
        ) | CodeList.objects.filter(unique_identifier='')
        
        # Show first 10 as preview
        for i, codelist in enumerate(codelists_without_id[:10]):
            unique_id = self.generate_unique_identifier(codelist)
            self.stdout.write(
                f"  {unique_id}: {codelist.codelist_name} (Source: {codelist.source.name})"
            )
        
        if codelists_without_id.count() > 10:
            self.stdout.write(f"  ... and {codelists_without_id.count() - 10} more")

    @transaction.atomic
    def populate_unique_identifiers(self):
        """Populate unique identifiers for all existing codelists"""
        self.stdout.write("🔄 Populating unique identifiers for existing codelists...")
        
        codelists_without_id = CodeList.objects.filter(
            unique_identifier__isnull=True
        ) | CodeList.objects.filter(unique_identifier='')
        
        total = codelists_without_id.count()
        self.stdout.write(f"📊 Found {total} codelists without unique identifiers")
        
        updated = 0
        for i, codelist in enumerate(codelists_without_id):
            if i % 100 == 0 and i > 0:
                self.stdout.write(f"📈 Progress: {i}/{total}")
            
            unique_id = self.generate_unique_identifier(codelist)
            codelist.unique_identifier = unique_id
            codelist.save()
            updated += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Updated {updated} codelists with unique identifiers")
        )
        
        # Show sample results
        self.stdout.write("\n📋 Sample unique identifiers:")
        for cl in CodeList.objects.exclude(unique_identifier__isnull=True)[:10]:
            self.stdout.write(
                f"  {cl.unique_identifier}: {cl.codelist_name} (Source: {cl.source.name})"
            )