from django.core.management.base import BaseCommand
from core.models import CodeSource, CodeList, Code, EmisCode, CodeListCode
import json

class Command(BaseCommand):
    help = 'Load essential data for Heroku'

    def add_arguments(self, parser):
        parser.add_argument('--create-sources', action='store_true', help='Create basic CodeSources')
        parser.add_argument('--status', action='store_true', help='Show current data status')

    def handle(self, *args, **options):
        if options['status']:
            self.show_status()
            return
            
        if options['create_sources']:
            self.create_sources()
            return
        
        # Default: show status and create sources
        self.show_status()
        self.create_sources()
        self.show_status()

    def show_status(self):
        self.stdout.write("📊 Current database status:")
        self.stdout.write(f"   CodeSource: {CodeSource.objects.count()}")
        self.stdout.write(f"   CodeList: {CodeList.objects.count()}")
        self.stdout.write(f"   Code: {Code.objects.count()}")
        self.stdout.write(f"   EmisCode: {EmisCode.objects.count()}")
        self.stdout.write(f"   CodeListCode: {CodeListCode.objects.count()}")

    def create_sources(self):
        self.stdout.write("Creating essential CodeSources...")
        
        sources_data = [
            {"name": "Oxford_CPRD", "description": "Oxford CPRD Codelist Source", "is_default": True},
            {"name": "NHS_Ref_Sets", "description": "NHS Reference Sets", "is_default": False},
            {"name": "HDR_UK_Phenotype_Libraries", "description": "HDR UK Phenotype Libraries", "is_default": False},
            {"name": "Opencodelists", "description": "Open Codelists Repository", "is_default": False},
            {"name": "AIM_RSF_Codelists", "description": "AIM RSF Codelists", "is_default": False},
            {"name": "LSHTM_Data_Compass", "description": "LSHTM Data Compass", "is_default": False}
        ]
        
        created_count = 0
        for source_data in sources_data:
            source, created = CodeSource.objects.get_or_create(
                name=source_data["name"],
                defaults={
                    "description": source_data["description"], 
                    "is_default": source_data["is_default"]
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f'✅ Created source: {source_data["name"]}')
            else:
                self.stdout.write(f'⚠️  Source exists: {source_data["name"]}')
        
        self.stdout.write(f'✅ Created {created_count} new sources')