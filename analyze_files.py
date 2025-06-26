#!/usr/bin/env python3
"""
Analyze all downloaded codelist files to understand their structure
and create a standardization plan
"""

import os
import pandas as pd
from pathlib import Path
from collections import defaultdict, Counter
import csv

def analyze_all_files(download_root):
    """Analyze all downloaded files and create a comprehensive report"""
    
    download_path = Path(download_root)
    successful_path = download_path / 'successful'
    
    if not successful_path.exists():
        print(f"ERROR: {successful_path} does not exist")
        return
    
    analysis_results = {
        'total_files': 0,
        'readable_files': 0,
        'unreadable_files': 0,
        'column_patterns': defaultdict(list),
        'file_sizes': [],
        'projects': defaultdict(int),
        'file_extensions': Counter(),
        'column_variations': {
            'med_code_id': set(),
            'term': set(), 
            'snomed': set(),
            'observations': set()
        },
        'sample_data': [],
        'problematic_files': []
    }
    
    print("🔍 Analyzing all downloaded files...")
    
    # Walk through all project folders
    for project_folder in successful_path.iterdir():
        if not project_folder.is_dir():
            continue
            
        project_name = project_folder.name
        analysis_results['projects'][project_name] = 0
        
        print(f"\n📁 Analyzing project: {project_name}")
        
        # Walk through each codelist folder
        for codelist_folder in project_folder.iterdir():
            if not codelist_folder.is_dir():
                continue
                
            analysis_results['projects'][project_name] += 1
            
            # Find the main CSV/TXT file (not metadata or analysis)
            main_files = [f for f in codelist_folder.iterdir() 
                         if f.suffix.lower() in ['.csv', '.txt'] 
                         and f.name not in ['metadata.txt', 'analysis.txt']]
            
            if not main_files:
                analysis_results['problematic_files'].append({
                    'path': str(codelist_folder),
                    'issue': 'No main data file found'
                })
                continue
                
            # Use the first main file found
            main_file = main_files[0]
            analysis_results['total_files'] += 1
            analysis_results['file_extensions'][main_file.suffix.lower()] += 1
            analysis_results['file_sizes'].append(main_file.stat().st_size)
            
            # Analyze the file
            try:
                file_analysis = analyze_single_file(main_file)
                if file_analysis:
                    analysis_results['readable_files'] += 1
                    
                    # Store column patterns
                    columns_key = '|'.join(sorted(file_analysis['columns']))
                    analysis_results['column_patterns'][columns_key].append({
                        'file': str(main_file),
                        'project': project_name,
                        'rows': file_analysis['rows'],
                        'columns': file_analysis['columns']
                    })
                    
                    # Track column variations
                    for key_type, variations in analysis_results['column_variations'].items():
                        if key_type in file_analysis:
                            variations.update(file_analysis[key_type])
                    
                    # Store sample data from interesting files
                    if file_analysis['rows'] > 10:  # Only from substantial files
                        analysis_results['sample_data'].append({
                            'file': str(main_file),
                            'project': project_name,
                            'sample': file_analysis.get('sample_rows', [])
                        })
                        
                else:
                    analysis_results['unreadable_files'] += 1
                    
            except Exception as e:
                analysis_results['unreadable_files'] += 1
                analysis_results['problematic_files'].append({
                    'path': str(main_file),
                    'issue': f'Analysis failed: {str(e)}'
                })
    
    return analysis_results

def analyze_single_file(file_path):
    """Analyze a single codelist file"""
    
    try:
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252']
        df = None
        
        for encoding in encodings:
            try:
                if file_path.suffix.lower() == '.csv':
                    df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='skip')
                elif file_path.suffix.lower() == '.txt':
                    # Try tab-delimited first, then comma
                    try:
                        df = pd.read_csv(file_path, delimiter='\t', encoding=encoding, on_bad_lines='skip')
                        if len(df.columns) == 1:  # Probably not tab-delimited
                            df = pd.read_csv(file_path, delimiter=',', encoding=encoding, on_bad_lines='skip')
                    except:
                        df = pd.read_csv(file_path, delimiter=',', encoding=encoding, on_bad_lines='skip')
                break
            except UnicodeDecodeError:
                continue
        
        if df is None or len(df) == 0:
            return None
            
        columns = list(df.columns)
        lower_columns = [col.lower().strip() for col in columns]
        
        # Identify potential key columns
        med_code_candidates = [col for col in columns if any(term in col.lower() 
                              for term in ['med_code', 'code_id', 'codeid', 'code', 'id', 'medcode'])]
        
        term_candidates = [col for col in columns if any(term in col.lower() 
                          for term in ['description', 'term', 'desc', 'name', 'label', 'text'])]
        
        snomed_candidates = [col for col in columns if any(term in col.lower() 
                            for term in ['snomed', 'concept', 'snomedct'])]
        
        obs_candidates = [col for col in columns if any(term in col.lower() 
                         for term in ['observations', 'freq', 'frequency', 'count', 'events', 'obs'])]
        
        # Get sample data
        sample_rows = []
        if len(df) > 0:
            sample_count = min(3, len(df))
            for i in range(sample_count):
                row_data = {}
                for col in columns[:6]:  # First 6 columns only
                    value = df.iloc[i][col]
                    if pd.isna(value):
                        row_data[col] = 'NaN'
                    else:
                        row_data[col] = str(value)[:50]  # Truncate long values
                sample_rows.append(row_data)
        
        return {
            'rows': len(df),
            'columns': columns,
            'med_code_id': med_code_candidates,
            'term': term_candidates,
            'snomed': snomed_candidates,
            'observations': obs_candidates,
            'sample_rows': sample_rows
        }
        
    except Exception as e:
        print(f"  ❌ Error analyzing {file_path}: {str(e)}")
        return None

def generate_report(analysis_results, output_file):
    """Generate a comprehensive analysis report"""
    
    print(f"\n📊 Generating analysis report: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# CODELIST FILES ANALYSIS REPORT\n")
        f.write("=" * 50 + "\n\n")
        
        # Summary statistics
        f.write("## SUMMARY STATISTICS\n")
        f.write(f"Total files analyzed: {analysis_results['total_files']}\n")
        f.write(f"Successfully readable: {analysis_results['readable_files']}\n")
        f.write(f"Unreadable files: {analysis_results['unreadable_files']}\n")
        f.write(f"Success rate: {analysis_results['readable_files']/analysis_results['total_files']*100:.1f}%\n\n")
        
        # File types
        f.write("## FILE TYPES\n")
        for ext, count in analysis_results['file_extensions'].most_common():
            f.write(f"{ext}: {count} files\n")
        f.write("\n")
        
        # Project breakdown
        f.write("## PROJECTS\n")
        for project, count in sorted(analysis_results['projects'].items()):
            f.write(f"{project}: {count} codelists\n")
        f.write("\n")
        
        # File sizes
        if analysis_results['file_sizes']:
            sizes = analysis_results['file_sizes']
            f.write("## FILE SIZES\n")
            f.write(f"Average: {sum(sizes)/len(sizes)/1024:.1f} KB\n")
            f.write(f"Largest: {max(sizes)/1024:.1f} KB\n")
            f.write(f"Smallest: {min(sizes)/1024:.1f} KB\n\n")
        
        # Column patterns
        f.write("## COLUMN PATTERNS\n")
        f.write(f"Found {len(analysis_results['column_patterns'])} unique column patterns:\n\n")
        
        for i, (pattern, files) in enumerate(analysis_results['column_patterns'].items(), 1):
            f.write(f"### Pattern {i} ({len(files)} files):\n")
            f.write(f"Columns: {pattern.replace('|', ', ')}\n")
            f.write("Example files:\n")
            for file_info in files[:3]:  # Show first 3 examples
                f.write(f"  - {file_info['project']}: {file_info['rows']} rows\n")
            if len(files) > 3:
                f.write(f"  ... and {len(files)-3} more\n")
            f.write("\n")
        
        # Column variations for key fields
        f.write("## KEY COLUMN VARIATIONS\n")
        for field_type, variations in analysis_results['column_variations'].items():
            if variations:
                f.write(f"\n### {field_type.upper()} column variations:\n")
                for variation in sorted(variations):
                    f.write(f"  - {variation}\n")
        
        # Problematic files
        if analysis_results['problematic_files']:
            f.write("\n## PROBLEMATIC FILES\n")
            for problem in analysis_results['problematic_files']:
                f.write(f"- {problem['path']}: {problem['issue']}\n")
        
        # Sample data
        f.write("\n## SAMPLE DATA\n")
        for sample in analysis_results['sample_data'][:5]:  # Show 5 examples
            f.write(f"\n### {sample['project']} - {Path(sample['file']).name}\n")
            if sample['sample']:
                first_row = sample['sample'][0]
                for col, value in list(first_row.items())[:4]:  # First 4 columns
                    f.write(f"  {col}: {value}\n")

def create_standardization_plan(analysis_results, plan_file):
    """Create a standardization plan based on the analysis"""
    
    print(f"📋 Creating standardization plan: {plan_file}")
    
    # Group similar column patterns
    common_patterns = []
    for pattern, files in analysis_results['column_patterns'].items():
        if len(files) >= 5:  # Patterns used by 5+ files
            common_patterns.append((pattern, files))
    
    common_patterns.sort(key=lambda x: len(x[1]), reverse=True)
    
    with open(plan_file, 'w', encoding='utf-8') as f:
        f.write("# STANDARDIZATION PLAN\n")
        f.write("=" * 30 + "\n\n")
        
        f.write("## APPROACH\n")
        f.write("1. **High Priority**: Standardize common patterns first (affecting most files)\n")
        f.write("2. **Medium Priority**: Handle project-specific patterns\n")
        f.write("3. **Low Priority**: Deal with unique/problematic files individually\n\n")
        
        f.write("## COMMON PATTERNS TO STANDARDIZE\n\n")
        
        for i, (pattern, files) in enumerate(common_patterns[:10], 1):
            f.write(f"### Priority {i}: {len(files)} files\n")
            f.write(f"**Pattern**: {pattern.replace('|', ', ')}\n")
            f.write("**Projects**: " + ", ".join(set(f['project'] for f in files)) + "\n")
            f.write("**Suggested mapping**:\n")
            
            # Suggest column mappings based on common patterns
            columns = pattern.split('|')
            for col in columns:
                col_lower = col.lower()
                if any(term in col_lower for term in ['med_code', 'code_id', 'codeid', 'code']):
                    f.write(f"  - {col} -> med_code_id\n")
                elif any(term in col_lower for term in ['description', 'term', 'desc', 'label']):
                    f.write(f"  - {col} -> term\n")
                elif any(term in col_lower for term in ['snomed', 'concept']):
                    f.write(f"  - {col} -> snomed_ct_concept_id\n")
                elif any(term in col_lower for term in ['observations', 'freq', 'count']):
                    f.write(f"  - {col} -> observations\n")
                else:
                    f.write(f"  - {col} -> ?\n")
            f.write("\n")

def main():
    download_root = './codelists_bulk'
    
    print("🚀 Starting comprehensive file analysis...")
    
    # Analyze all files
    results = analyze_all_files(download_root)
    
    if not results:
        print("❌ Analysis failed - no results returned")
        return
    
    # Generate reports
    report_file = Path(download_root) / 'ANALYSIS_REPORT.txt'
    plan_file = Path(download_root) / 'STANDARDIZATION_PLAN.txt'
    
    generate_report(results, report_file)
    create_standardization_plan(results, plan_file)
    
    print(f"\n✅ Analysis complete!")
    print(f"📊 See detailed report: {report_file}")
    print(f"📋 See standardization plan: {plan_file}")
    print(f"\n📈 Summary:")
    print(f"   - {results['readable_files']}/{results['total_files']} files readable")
    print(f"   - {len(results['column_patterns'])} unique column patterns found")
    print(f"   - {len(results['projects'])} projects analyzed")

if __name__ == '__main__':
    main()