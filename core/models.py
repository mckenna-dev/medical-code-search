# Enhanced models.py - Add this to your existing models

from django.db import models
from django.contrib.auth.models import User

class CodeSource(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    
    def __str__(self):
        return self.name

class CodeList(models.Model):
    codelist_name = models.CharField(max_length=255)
    project_title = models.CharField(max_length=255, blank=True)
    ERAP_number = models.CharField(max_length=50, blank=True)
    author = models.CharField(max_length=255, blank=True)
    codelist_description = models.TextField(blank=True)
    emis_dictionary_version = models.CharField(max_length=100, blank=True)
    source = models.ForeignKey(CodeSource, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    # NEW FIELD - Add this to your existing model
    unique_identifier = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    # Additional metadata fields for enhanced functionality
    clinical_domain = models.CharField(max_length=100, blank=True)
    code_count = models.IntegerField(default=0)
    last_validated = models.DateField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        # Auto-generate unique identifier if not set
        if not self.unique_identifier:
            self.unique_identifier = self.generate_unique_identifier()
        
        # Update code count
        if self.pk:
            self.code_count = self.codelistcode_set.count()
        
        super().save(*args, **kwargs)
    
    def generate_unique_identifier(self):
        """Generate unique identifier based on source and name"""
        source_prefixes = {
            'CPRD': 'cprd_',
            'AIM_RSF': 'aim_',
            'CALIBER_Mapped': 'caliber_',
            'HDR_UK': 'hdr_',
            'OpenCodelist': 'opencode_',
            'PCD_Refset': 'pcd_'
        }
        
        prefix = source_prefixes.get(self.source.name, 'other_')
        
        # Create clean name
        import re
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', self.codelist_name.lower())
        clean_name = clean_name[:50]  # Limit length
        
        # Add number if needed to ensure uniqueness
        base_id = f"{prefix}{clean_name}"
        unique_id = base_id
        counter = 1
        
        while CodeList.objects.filter(unique_identifier=unique_id).exists():
            unique_id = f"{base_id}_{counter}"
            counter += 1
        
        return unique_id
    
    def __str__(self):
        return self.codelist_name

class Code(models.Model):
    med_code_id = models.CharField(max_length=50, primary_key=True)
    term = models.CharField(max_length=500)
    observations = models.BigIntegerField(null=True, blank=True)
    snomed_ct_concept_id = models.CharField(max_length=50, blank=True)
    emis_category = models.CharField(max_length=100, blank=True)
    coding_system = models.CharField(max_length=50, blank=True)
    
    # Additional flags
    is_negation = models.BooleanField(default=False)
    is_familial = models.BooleanField(default=False)
    is_screening = models.BooleanField(default=False)
    is_referral = models.BooleanField(default=False)
    is_suspected = models.BooleanField(default=False)
    is_advice = models.BooleanField(default=False)
    
    # Many-to-many relationship with CodeList through CodeListCode
    codelists = models.ManyToManyField(CodeList, through='CodeListCode')
    
    def __str__(self):
        return f"{self.med_code_id}: {self.term}"

class CodeListCode(models.Model):
    """Junction table to link codes to codelists and track exclusions"""
    code = models.ForeignKey(Code, on_delete=models.CASCADE)
    codelist = models.ForeignKey(CodeList, on_delete=models.CASCADE)
    is_excluded = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('code', 'codelist')

class UserCodeListSelection(models.Model):
    """Track temporary user selections for codelists and codes"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    codelist = models.ForeignKey(CodeList, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username}'s selection: {self.name or self.codelist.codelist_name}"

class UserCodeExclusion(models.Model):
    """Track which codes are excluded in a user's selection"""
    selection = models.ForeignKey(UserCodeListSelection, on_delete=models.CASCADE)
    code = models.ForeignKey(Code, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('selection', 'code')

# Add this to your core/models.py file

class EmisCode(models.Model):
    """
    Official EMIS Medical Dictionary with full metadata
    Separate from research codelists but can be used to enrich them
    """
    med_code_id = models.CharField(max_length=50, primary_key=True, help_text="Medical Code ID (may have 'a' prefix)")
    clean_med_code_id = models.CharField(max_length=50, db_index=True, help_text="Code ID with 'a' prefix removed")
    observations = models.BigIntegerField(help_text="Number of observations in EMIS")
    term = models.CharField(max_length=1000, help_text="Medical term description")
    snomed_ct_concept_id = models.CharField(max_length=50, blank=True, help_text="SNOMED CT code (may have 'b' prefix)")
    clean_snomed_ct_concept_id = models.CharField(max_length=50, blank=True, db_index=True, help_text="SNOMED code with 'b' prefix removed")
    most_recent_release_year = models.IntegerField(help_text="Most recent release year")
    emis_code_cat_id = models.IntegerField(help_text="EMIS category ID")
    emis_cat_description = models.CharField(max_length=200, help_text="EMIS category description")
    parent_category = models.CharField(max_length=200, help_text="Parent category")
    
    # Boolean flags from EMIS
    is_negated = models.BooleanField(default=False, help_text="Is this a negated term")
    is_resolved = models.BooleanField(default=False, help_text="Is this a resolved condition")
    is_historical = models.BooleanField(default=False, help_text="Is this historical")
    is_familial = models.BooleanField(default=False, help_text="Is this family history")
    is_genetic_risk = models.BooleanField(default=False, help_text="Is this genetic risk")
    is_screening = models.BooleanField(default=False, help_text="Is this screening")
    is_monitoring = models.BooleanField(default=False, help_text="Is this monitoring")
    is_administrative = models.BooleanField(default=False, help_text="Is this administrative")
    is_education = models.BooleanField(default=False, help_text="Is this education")
    is_referral = models.BooleanField(default=False, help_text="Is this referral")
    is_test_request = models.BooleanField(default=False, help_text="Is this test request")
    is_symptom = models.BooleanField(default=False, help_text="Is this symptom")
    is_exclusion = models.BooleanField(default=False, help_text="Is this exclusion")
    is_qualifier = models.BooleanField(default=False, help_text="Is this qualifier")
    
    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['clean_med_code_id']),
            models.Index(fields=['clean_snomed_ct_concept_id']),
            models.Index(fields=['parent_category']),
            models.Index(fields=['emis_cat_description']),
            models.Index(fields=['term']),
        ]
        
    def save(self, *args, **kwargs):
        # Automatically clean the prefixes when saving
        self.clean_med_code_id = self.clean_code_prefix(self.med_code_id)
        self.clean_snomed_ct_concept_id = self.clean_code_prefix(str(self.snomed_ct_concept_id))
        super().save(*args, **kwargs)
    
    @staticmethod
    def clean_code_prefix(code_str):
        """Remove 'a' or 'b' prefixes that prevent Excel corruption"""
        if not code_str:
            return ''
        code_str = str(code_str).strip()
        if code_str.lower().startswith(('a', 'b')) and len(code_str) > 1 and code_str[1:].isdigit():
            return code_str[1:]
        return code_str
    
    @property
    def category_type(self):
        """Determine the primary category type based on flags"""
        if self.is_administrative:
            return "Administrative"
        elif self.is_screening:
            return "Screening"
        elif self.is_referral:
            return "Referral"
        elif self.is_test_request:
            return "Test Request"
        elif self.is_symptom:
            return "Symptom"
        elif self.is_monitoring:
            return "Monitoring"
        elif self.is_education:
            return "Education"
        else:
            return "Clinical"
    
    def matches_code(self, code_instance):
        """Check if this EMIS code matches a Code instance"""
        if not isinstance(code_instance, Code):
            return False
        
        # Try direct match first
        if self.clean_med_code_id == Code.clean_code_prefix(code_instance.med_code_id):
            return True
        
        # Try SNOMED match if both have SNOMED codes
        if (self.clean_snomed_ct_concept_id and 
            code_instance.snomed_ct_concept_id and
            self.clean_snomed_ct_concept_id == Code.clean_code_prefix(code_instance.snomed_ct_concept_id)):
            return True
        
        return False
    
    def __str__(self):
        return f"{self.med_code_id}: {self.term[:100]}..."

# Add clean_code_prefix method to existing Code model
def clean_code_prefix(code_str):
    """Remove 'a' or 'b' prefixes that prevent Excel corruption"""
    if not code_str:
        return ''
    code_str = str(code_str).strip()
    if code_str.lower().startswith(('a', 'b')) and len(code_str) > 1 and code_str[1:].isdigit():
        return code_str[1:]
    return code_str

# Add the method to Code class
Code.clean_code_prefix = staticmethod(clean_code_prefix)