# Manual Standardization Process

## Overview
This folder contains all downloaded codelists organized by Project/ERAP_CodelistName.

## Folder Structure
- `successful/` - Successfully downloaded files
- `failed/` - Failed downloads with error details
- `standardized/` - Your manually standardized files (create this)

## Manual Standardization Steps

1. **Review each successful download**
   - Check the `analysis.txt` file for column information
   - Look at the actual CSV file
   
2. **Standardize column names**
   - Create standardized versions with consistent column names:
     - `med_code_id` - The medical code (remove 'a' prefix)
     - `term` - The description/term
     - `snomed_ct_concept_id` - SNOMED code (remove 'b' prefix)
     - `observations` - Observation count (numeric)
     - `emis_category` - Category if available
   
3. **Save standardized files**
   - Save in `standardized/` folder
   - Keep original folder structure
   - Add `_standardized.csv` suffix

4. **Use the template**
   - Fill out `standardization_template.csv` to track your mappings
   - This will help with batch processing later

## Next Steps
After manual standardization, you can create a batch import script
that processes all files in the `standardized/` folder with known
column mappings.
