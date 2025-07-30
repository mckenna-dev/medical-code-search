from django.core.management.base import BaseCommand
from core.models import CodeSource

class Command(BaseCommand):
    help = 'Import code sources'

    def handle(self, *args, **options):
        sources = [
            {"name": "Oxford_CPRD", "description": "Oxford CPRD Codelist Source", "is_default": True},
            {"name": "NHS_Ref_Sets", "description": "NHS Reference Sets", "is_default": False},
            {"name": "HDR_UK_Phenotype_Libraries", "description": "HDR UK Phenotype Libraries", "is_default": False},
            {"name": "Opencodelists", "description": "Open Codelists Repository", "is_default": False},
            {"name": "AIM_RSF_Codelists", "description": "AIM RSF Codelists", "is_default": False},
            {"name": "LSHTM_Data_Compass", "description": "LSHTM Data Compass", "is_default": False}
        ]
        
        for source in sources:
            obj, created = CodeSource.objects.get_or_create(
                name=source["name"],
                defaults={"description": source["description"], "is_default": source["is_default"]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created source: {source["name"]}'))
            else:
                self.stdout.write(f'Source already exists: {source["name"]}')
        
        self.stdout.write(self.style.SUCCESS(f'Total sources: {CodeSource.objects.count()}'))