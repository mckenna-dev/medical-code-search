#!/usr/bin/env python3
"""
Standalone bulk download script for medical codelists
Run this directly with: python bulk_download_standalone.py
"""

import os
import csv
import pandas as pd
import requests
from urllib.parse import urlparse
from pathlib import Path
import time
from collections import defaultdict
import argparse

def main():
    parser = argparse.ArgumentParser(description='Bulk download medical codelists from GitHub')
    parser.add_argument('--metadata-csv', type=str, required=True, 
                      help='Path to CSV file containing codelist metadata')
    parser.add_argument('--download-root', type=str, default='./codelists_bulk/',
                      help='Root directory for bulk downloads')
    parser.add_argument('--dry-run', action='store_true',
                      help='Show what would be downloaded without downloading')
    parser.add_argument('--resume', action='store_true',
                      help='Resume downloads, skip existing files')
    
    args = parser.parse_args()
    
    downloader = BulkDownloader(
        metadata_csv=args.metadata_csv,
        download_root=args.download_root,
        dry_run=args.dry_run,
        resume=args.resume
    )
    
    downloader.run()

class BulkDownloader:
    def __init__(self, metadata_csv, download_root, dry_run=False, resume=False):
        self.metadata_csv = metadata_csv
        self.download_root = download_root
        self.dry_run = dry_run
        self.resume = resume
        
    def run(self):
        # Create download structure
        download_path = Path(self.download_root)
        if not self.dry_run:
            download_path.mkdir(exist_ok=True)
            (download_path / 'successful').mkdir(exist_ok=True)
            (download_path / 'failed').mkdir(exist_ok=True)
            (download_path / 'standardized').mkdir(exist_ok=True)
        
        # Read metadata
        try:
            df = pd.read_csv(self.metadata_csv)
            print(f'Found {len(df)} entries in metadata file')
        except Exception as e:
            print(f'Error reading metadata CSV: {str(e)}')
            return
        
        # Download summary
        summary = {
            'total': len(df),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'projects': defaultdict(int)
        }
        
        # Process each entry
        for index, row in df.iterrows():
            print(f"Processing {index + 1}/{len(df)}: ", end="")
            
            result = self.process_download(row, download_path)
            
            if result['status'] == 'success':
                summary['successful'] += 1
            elif result['status'] == 'failed':
                summary['failed'] += 1
            elif result['status'] == 'skipped':
                summary['skipped'] += 1
            
            if result.get('project'):
                summary['projects'][result['project']] += 1
            
            # Add small delay to be nice to GitHub
            if not self.dry_run:
                time.sleep(0.5)
        
        # Generate summary report
        self.generate_summary_report(download_path, summary)
        
        # Generate standardization template
        if not self.dry_run:
            self.generate_standardization_template(download_path)

    def process_download(self, row, download_path):
        """Process a single download"""
        
        # Extract metadata
        codelist_name = str(row.get('Codelist_Name', '')).strip()
        project_title = str(row.get('Project_Title', '')).strip()
        erap_number = str(row.get('ERAP_Number', '')).strip()
        author = str(row.get('Author', '')).strip()
        
        # Clean up nan values
        if project_title.lower() in ['nan', 'none', 'null', '']:
            project_title = 'Unknown_Project'
        if erap_number.lower() in ['nan', 'none', 'null', '']:
            erap_number = 'No_ERAP'
        
        # Get GitHub URL
        github_url = ''
        url_columns = ['Path_to_Codelist', 'URL', 'GitHub_URL', 'Codelist_URL', 'Path']
        for col in url_columns:
            if col in row and pd.notna(row[col]):
                github_url = str(row[col]).strip()
                if github_url.startswith('http'):
                    break
        
        if not codelist_name or not github_url:
            print(f'SKIP: {codelist_name} - missing data')
            return {'status': 'failed', 'reason': 'missing_data'}
        
        # Create organized folder structure: Project/ERAP_CodelistName
        safe_project = self.make_safe_filename(project_title)
        safe_codelist = self.make_safe_filename(codelist_name)
        safe_erap = self.make_safe_filename(erap_number)
        
        folder_name = f"{safe_project}/{safe_erap}_{safe_codelist}"
        project_folder = download_path / 'successful' / folder_name
        
        # Create filename
        parsed_url = urlparse(github_url)
        original_filename = os.path.basename(parsed_url.path) or f"{safe_codelist}.csv"
        
        if not self.dry_run:
            project_folder.mkdir(parents=True, exist_ok=True)
        
        file_path = project_folder / original_filename
        metadata_path = project_folder / 'metadata.txt'
        
        # Check if already exists (for resume functionality)
        if self.resume and file_path.exists():
            print(f'SKIP: {folder_name} (already exists)')
            return {'status': 'skipped', 'project': safe_project}
        
        print(f'{folder_name}... ', end="")
        
        if self.dry_run:
            print(f'DRY-RUN: Would download {github_url}')
            return {'status': 'success', 'project': safe_project}
        
        # Download the file
        download_result = self.download_file(github_url, file_path, metadata_path, row)
        
        if download_result['success']:
            # Analyze the downloaded file
            analysis = self.analyze_downloaded_file(file_path)
            
            # Save analysis
            analysis_path = project_folder / 'analysis.txt'
            with open(analysis_path, 'w') as f:
                f.write("=== FILE ANALYSIS ===\n")
                f.write(f"Rows: {analysis.get('rows', 'Unknown')}\n")
                f.write(f"Columns: {analysis.get('columns', 'Unknown')}\n")
                f.write(f"Column names: {analysis.get('column_names', [])}\n")
                f.write(f"Has med_code_id: {analysis.get('has_code_id', False)}\n")
                f.write(f"Has term/description: {analysis.get('has_term', False)}\n")
                f.write(f"Has SNOMED: {analysis.get('has_snomed', False)}\n")
                f.write(f"Sample data:\n{analysis.get('sample', 'N/A')}\n")
            
            print(f'SUCCESS: {analysis.get("rows", "?")} rows')
            return {'status': 'success', 'project': safe_project}
        else:
            # Move to failed folder
            failed_folder = download_path / 'failed' / folder_name
            failed_folder.mkdir(parents=True, exist_ok=True)
            
            error_path = failed_folder / 'error.txt'
            with open(error_path, 'w') as f:
                f.write(f"Failed to download: {github_url}\n")
                f.write(f"Error: {download_result.get('error', 'Unknown error')}\n")
                f.write(f"Metadata:\n")
                f.write(f"  Codelist: {codelist_name}\n")
                f.write(f"  Project: {project_title}\n")
                f.write(f"  ERAP: {erap_number}\n")
                f.write(f"  Author: {author}\n")
            
            print(f'FAILED: {download_result.get("error", "Unknown error")}')
            return {'status': 'failed', 'project': safe_project, 'reason': download_result.get('error')}

    def download_file(self, github_url, file_path, metadata_path, row):
        """Download a single file from GitHub"""
        
        try:
            # Convert to raw URL
            if 'github.com' in github_url and '/blob/' in github_url:
                raw_url = github_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
            else:
                raw_url = github_url
            
            # Try multiple branches
            urls_to_try = [raw_url]
            if '/main/' in raw_url:
                urls_to_try.append(raw_url.replace('/main/', '/master/'))
            elif '/master/' in raw_url:
                urls_to_try.append(raw_url.replace('/master/', '/main/'))
            
            # Add GitHub token if available
            headers = {}
            if 'GITHUB_TOKEN' in os.environ:
                headers['Authorization'] = f'token {os.environ["GITHUB_TOKEN"]}'
            
            response = None
            successful_url = None
            
            for url in urls_to_try:
                try:
                    response = requests.get(url, timeout=30, headers=headers)
                    if response.status_code == 200:
                        successful_url = url
                        break
                except requests.exceptions.RequestException:
                    continue
            
            if not response or response.status_code != 200:
                return {'success': False, 'error': f'HTTP {response.status_code if response else "timeout"}'}
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' in content_type:
                return {'success': False, 'error': 'HTML_response'}
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            # Save metadata
            with open(metadata_path, 'w') as f:
                f.write(f"Original URL: {github_url}\n")
                f.write(f"Downloaded from: {successful_url}\n")
                f.write(f"Codelist Name: {row.get('Codelist_Name', '')}\n")
                f.write(f"Project Title: {row.get('Project_Title', '')}\n")
                f.write(f"ERAP Number: {row.get('ERAP_Number', '')}\n")
                f.write(f"Author: {row.get('Author', '')}\n")
                f.write(f"Coding System: {row.get('Coding System', '')}\n")
                f.write(f"Year Created: {row.get('Year_Created', '')}\n")
                f.write(f"Downloaded: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"File Size: {len(response.content)} bytes\n")
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def analyze_downloaded_file(self, file_path):
        """Analyze a downloaded file to understand its structure"""
        
        try:
            # Try different encodings
            encodings = ['utf-8', 'latin-1', 'cp1252']
            df = None
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='skip')
                    break
                except UnicodeDecodeError:
                    continue
            
            if df is None:
                return {'error': 'Could not read file'}
            
            columns = list(df.columns)
            lower_columns = [col.lower() for col in columns]
            
            # Check for key columns
            has_code_id = any(term in col for col in lower_columns 
                            for term in ['med_code', 'code_id', 'codeid', 'code', 'id'])
            
            has_term = any(term in col for col in lower_columns 
                         for term in ['description', 'term', 'desc', 'name', 'label'])
            
            has_snomed = any(term in col for col in lower_columns 
                           for term in ['snomed', 'concept'])
            
            # Get sample data (first 3 rows, first 5 columns max)
            sample_df = df.head(3).iloc[:, :5] if len(df.columns) > 5 else df.head(3)
            sample = sample_df.to_string() if len(df) > 0 else "No data"
            
            return {
                'rows': len(df),
                'columns': len(columns),
                'column_names': columns,
                'has_code_id': has_code_id,
                'has_term': has_term,
                'has_snomed': has_snomed,
                'sample': sample
            }
            
        except Exception as e:
            return {'error': str(e)}

    def make_safe_filename(self, name):
        """Make a filesystem-safe filename"""
        import re
        # Remove or replace unsafe characters
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        safe = re.sub(r'\s+', '_', safe)
        return safe[:100]  # Limit length

    def generate_summary_report(self, download_path, summary):
        """Generate a summary report"""
        
        print(f'\n=== DOWNLOAD SUMMARY ===')
        print(f'Total entries: {summary["total"]}')
        print(f'Successful downloads: {summary["successful"]}')
        print(f'Failed downloads: {summary["failed"]}')
        print(f'Skipped: {summary["skipped"]}')
        
        print(f'\nProjects found:')
        for project, count in sorted(summary['projects'].items()):
            print(f'  {project}: {count} codelists')
        
        if not self.dry_run:
            # Write summary to file
            summary_path = download_path / 'download_summary.txt'
            with open(summary_path, 'w') as f:
                f.write(f'BULK DOWNLOAD SUMMARY\n')
                f.write(f'Generated: {time.strftime("%Y-%m-%d %H:%M:%S")}\n\n')
                f.write(f'Total entries: {summary["total"]}\n')
                f.write(f'Successful downloads: {summary["successful"]}\n')
                f.write(f'Failed downloads: {summary["failed"]}\n')
                f.write(f'Skipped: {summary["skipped"]}\n\n')
                f.write(f'Projects:\n')
                for project, count in sorted(summary['projects'].items()):
                    f.write(f'  {project}: {count} codelists\n')

    def generate_standardization_template(self, download_path):
        """Generate templates for manual standardization"""
        
        template_path = download_path / 'standardization_template.csv'
        
        # Create a template for standardized column names
        template_data = [
            ['original_filename', 'med_code_id_column', 'term_column', 'snomed_column', 'observations_column', 'notes'],
            ['example.csv', 'Med_Code_Id', 'Description', 'SNOMED_CT_Concept_ID', 'Observations', 'Remove a/b prefixes'],
            ['', '', '', '', '', ''],
        ]
        
        with open(template_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(template_data)
        
        print(f'Generated standardization template: {template_path}')
        
        # Create README for manual process
        readme_path = download_path / 'README_STANDARDIZATION.md'
        with open(readme_path, 'w') as f:
            f.write("""# Manual Standardization Process

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
""")
        
        print(f'Generated README: {readme_path}')

if __name__ == '__main__':
    main()