from django.db import models
from django.contrib.auth.models import User

# Create your models here.



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
