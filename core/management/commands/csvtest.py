import pandas as pd
df = pd.read_csv(r"C:\Users\mcken\medical_code_search\codelist_metadata.csv")
print("Column names:", df.columns.tolist())
print("\nFirst 3 rows:")
for i, row in df.head(3).iterrows():
    print(f"Row {i}:")
    print(f"  Name: {row.get('Codelist_Name', 'MISSING')}")
    print(f"  URL: {row.get('Path_to_Codelist', 'MISSING')}")
    print()