#!/usr/bin/env python3
"""
Batch standardize downloaded codelist files based on annotated patterns
"""

import os
import pandas as pd
from pathlib import Path
import json
import re

class CodelistStandardizer:
    def __init__(self, download_root, mapping_config=None):
        self.download_root = Path(download_root)
        self.successful_path = self.download_root / 'successful'
        self.standardized_path = self.download_root / 'standardized'
        self.mapping_config = mapping_config or self.get_default_mappings()
        
        # Create standardized directory
        self.standardized_path.mkdir(exist_ok=True)
        
        # Statistics
        self.stats = {
            'processed': 0,
            'standardized': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def get_default_mappings(self):
        """Column mappings based on your annotated standardization plan"""
        return {
            'med_code_id': {
                'primary_patterns': [
                    r'^medcodeid$',
                    r'^med_code_id$', 
                    r'^medcode_id$'
                ],
                'secondary_patterns': [
                    r'med_?code_?id',
                    r'medcode',
                    r'^code_?id$',
                    r'^code$'
                ],
                'ignore_patterns': [
                    r'cleansedreadcode',
                    r'originalreadcode',
                    r'readcode',
                    r'codelist_name'
                ],
                'prefixes_to_remove': ['a', 'b']
            },
            'term': {
                'primary_patterns': [
                    r'^term$',
                    r'^description$'
                ],
                'secondary_patterns': [
                    r'read_?term',
                    r'desc',
                    r'label',
                    r'name'
                ],
                'ignore_patterns': [
                    r'snomedctdescriptionid',
                    r'snomed.*description',
                    r'readterm'
                ]
            },
            'snomed_ct_concept_id': {
                'primary_patterns': [
                    r'^snomed_ct_concept_id$',
                    r'^snomedctconceptid$',
                    r'^snomedct_conceptid$'
                ],
                'secondary_patterns': [
                    r'snomed.*concept',
                    r'conceptid'
                ],
                'ignore_patterns': [
                    r'snomedctdescriptionid',
                    r'snomed.*description'
                ],
                'prefixes_to_remove': ['b']
            },
            'observations': {
                'primary_patterns': [
                    r'^observations$',
                    r'^count$'
                ],
                'secondary_patterns': [
                    r'freq(uency)?',
                    r'clinical_?events?',
                    r'events?',
                    r'^obs$'
                ],
                'ignore_patterns': []
            }
        }
    
    def find_column_mapping(self, columns):
        """Find the best column mapping for a set of columns based on your priorities"""
        mapping = {}
        used_columns = set()
        
        for target_field, config in self.mapping_config.items():
            best_match = None
            best_score = 0
            match_type = None
            
            for col in columns:
                if col in used_columns:
                    continue
                    
                col_lower = col.lower().strip()
                
                # Check if column should be ignored
                ignore_this = False
                for ignore_pattern in config.get('ignore_patterns', []):
                    if re.search(ignore_pattern, col_lower, re.IGNORECASE):
                        ignore_this = True
                        break
                
                if ignore_this:
                    continue
                
                # Check primary patterns first (highest priority)
                for pattern in config.get('primary_patterns', []):
                    if re.search(pattern, col_lower, re.IGNORECASE):
                        score = 100 + len(pattern)  # High score for primary
                        if score > best_score:
                            best_match = col
                            best_score = score
                            match_type = 'primary'
                
                # Check secondary patterns if no primary match
                if match_type != 'primary':
                    for pattern in config.get('secondary_patterns', []):
                        if re.search(pattern, col_lower, re.IGNORECASE):
                            score = 50 + len(pattern)  # Medium score for secondary
                            if score > best_score:
                                best_match = col
                                best_score = score
                                match_type = 'secondary'
            
            if best_match:
                mapping[target_field] = {
                    'column': best_match,
                    'type': match_type
                }
                used_columns.add(best_match)
        
        return mapping
    
    def clean_value(self, value, field_type, config):
        """Clean and standardize a value based on field type"""
        if pd.isna(value) or str(value).strip().lower() in ['nan', 'none', 'null', '']:
            return None
        
        value_str = str(value).strip()
        
        # Remove prefixes if specified
        if 'prefixes_to_remove' in config:
            for prefix in config['prefixes_to_remove']:
                if value_str.lower().startswith(prefix.lower()) and len(value_str) > 1:
                    value_str = value_str[1:]
                    break
        
        # Field-specific cleaning
        if field_type == 'observations':
            # Convert to integer if possible
            try:
                return int(float(value_str))
            except (ValueError, TypeError):
                return None
        elif field_type in ['med_code_id', 'snomed_ct_concept_id']:
            # Clean code fields
            return value_str.strip()
        elif field_type == 'term':
            # Clean term fields
            return value_str.strip()
        
        return value_str
    
    def standardize_file(self, input_file, project_name, codelist_name):
        """Standardize a single file"""
        try:
            # Try to read the file
            encodings = ['utf-8', 'latin-1', 'cp1252']
            df = None
            
            for encoding in encodings:
                try:
                    if input_file.suffix.lower() == '.csv':
                        df = pd.read_csv(input_file, encoding=encoding, on_bad_lines='skip')
                    elif input_file.suffix.lower() == '.txt':
                        # Try tab-delimited first
                        try:
                            df = pd.read_csv(input_file, delimiter='\t', encoding=encoding, on_bad_lines='skip')
                            if len(df.columns) == 1:
                                df = pd.read_csv(input_file, delimiter=',', encoding=encoding, on_bad_lines='skip')
                        except:
                            df = pd.read_csv(input_file, delimiter=',', encoding=encoding, on_bad_lines='skip')
                    break
                except UnicodeDecodeError:
                    continue
            
            if df is None or len(df) == 0:
                return None, "Could not read file or file is empty"
            
            print(f"  📄 Processing: {len(df)} rows, {len(df.columns)} columns")
            
            # Find column mapping
            column_mapping = self.find_column_mapping(df.columns.tolist())
            
            if not column_mapping.get('med_code_id'):
                return None, "No med_code_id column identified"
            
            print(f"  🔄 Column mapping:")
            for field, match_info in column_mapping.items():
                if isinstance(match_info, dict):
                    print(f"    {field}: {match_info['column']} ({match_info['type']})")
                else:
                    print(f"    {field}: {match_info}")
            
            # Create standardized dataframe
            standardized_data = []
            
            for _, row in df.iterrows():
                std_row = {}
                
                # Process each mapped column
                for target_field, match_info in column_mapping.items():
                    source_column = match_info['column'] if isinstance(match_info, dict) else match_info
                    
                    if source_column in df.columns:
                        raw_value = row[source_column]
                        config = self.mapping_config.get(target_field, {})
                        cleaned_value = self.clean_value(raw_value, target_field, config)
                        std_row[target_field] = cleaned_value
                
                # Skip rows without med_code_id
                if not std_row.get('med_code_id'):
                    continue
                
                # Add default values for missing core fields
                if 'term' not in std_row or not std_row['term']:
                    std_row['term'] = 'Unknown'
                if 'snomed_ct_concept_id' not in std_row:
                    std_row['snomed_ct_concept_id'] = ''
                if 'observations' not in std_row:
                    std_row['observations'] = None
                
                standardized_data.append(std_row)
            
            if not standardized_data:
                return None, "No valid rows after processing"
            
            # Create standardized DataFrame
            std_df = pd.DataFrame(standardized_data)
            
            # Create output path
            output_dir = self.standardized_path / project_name
            output_dir.mkdir(exist_ok=True)
            
            # Save standardized file
            output_file = output_dir / f"{codelist_name}_standardized.csv"
            std_df.to_csv(output_file, index=False)
            
            # Save mapping info
            mapping_file = output_dir / f"{codelist_name}_mapping.json"
            mapping_info = {
                'original_file': str(input_file),
                'original_columns': df.columns.tolist(),
                'column_mapping': {k: (v['column'] if isinstance(v, dict) else v) for k, v in column_mapping.items()},
                'mapping_details': column_mapping,
                'rows_processed': len(df),
                'rows_standardized': len(std_df),
                'project': project_name,
                'codelist': codelist_name
            }
            
            with open(mapping_file, 'w') as f:
                json.dump(mapping_info, f, indent=2)
            
            return len(std_df), None
            
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def standardize_all(self):
        """Standardize all files"""
        print("🚀 Starting batch standardization...")
        
        if not self.successful_path.exists():
            print(f"❌ {self.successful_path} does not exist")
            return
        
        # Process each project
        for project_folder in self.successful_path.iterdir():
            if not project_folder.is_dir():
                continue
            
            project_name = project_folder.name
            print(f"\n📁 Processing project: {project_name}")
            
            # Process each codelist
            for codelist_folder in project_folder.iterdir():
                if not codelist_folder.is_dir():
                    continue
                
                codelist_name = codelist_folder.name
                self.stats['processed'] += 1
                
                # Find main data file
                main_files = [f for f in codelist_folder.iterdir() 
                             if f.suffix.lower() in ['.csv', '.txt'] 
                             and f.name not in ['metadata.txt', 'analysis.txt']]
                
                if not main_files:
                    print(f"  ⚠️  No data file found in {codelist_name}")
                    self.stats['skipped'] += 1
                    continue
                
                main_file = main_files[0]
                print(f"  🔄 {codelist_name}")
                
                # Standardize the file
                result, error = self.standardize_file(main_file, project_name, codelist_name)
                
                if result is not None:
                    print(f"  ✅ Standardized {result} rows")
                    self.stats['standardized'] += 1
                else:
                    print(f"  ❌ Failed: {error}")
                    self.stats['failed'] += 1
        
        # Print summary
        print(f"\n📊 STANDARDIZATION SUMMARY")
        print(f"Files processed: {self.stats['processed']}")
        print(f"Successfully standardized: {self.stats['standardized']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Skipped: {self.stats['skipped']}")
        print(f"Success rate: {self.stats['standardized']/self.stats['processed']*100:.1f}%")
        
        # Save summary
        summary_file = self.standardized_path / 'standardization_summary.txt'
        with open(summary_file, 'w') as f:
            f.write("BATCH STANDARDIZATION SUMMARY\n")
            f.write("=" * 30 + "\n\n")
            f.write(f"Files processed: {self.stats['processed']}\n")
            f.write(f"Successfully standardized: {self.stats['standardized']}\n")
            f.write(f"Failed: {self.stats['failed']}\n")
            f.write(f"Skipped: {self.stats['skipped']}\n")
            f.write(f"Success rate: {self.stats['standardized']/self.stats['processed']*100:.1f}%\n")

def main():
    download_root = './codelists_bulk'
    
    # Create standardizer
    standardizer = CodelistStandardizer(download_root)
    
    # Run standardization
    standardizer.standardize_all()
    
    print(f"\n✅ Batch standardization complete!")
    print(f"📁 Standardized files saved to: {standardizer.standardized_path}")

if __name__ == '__main__':
    main()