import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"
CREDS_FILE = "houseflow_gheet_key.json.json"

def debug_gsheet():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open_by_key(SHEET_KEY).sheet1
        print("Successfully opened sheet.")
        
        # Get all values instead of all records to avoid header-related crashes
        all_values = sheet.get_all_values()
        if not all_values:
            print("Sheet is empty!")
            return
            
        headers = all_values[0]
        print(f"Total columns: {len(headers)}")
        for i, h in enumerate(headers):
            if h.strip():
                print(f"Col {i}: {repr(h)}")
        
        # Check for duplicates
        seen = set()
        duplicates = []
        for h in headers:
            if h in seen:
                duplicates.append(h)
            seen.add(h)
            
        if duplicates:
            print(f"ERROR: Duplicate headers found: {duplicates}")
            
        # Check for empty headers
        empty_indices = [i for i, h in enumerate(headers) if not h or h.strip() == ""]
        if empty_indices:
            print(f"ERROR: Empty headers found at indices: {empty_indices}")
            
        # Check for data row column count vs header row
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > len(headers):
                print(f"WARNING: Row {i} has more columns ({len(row)}) than headers ({len(headers)}).")
                
        # Try to run get_all_records and catch the specific error
        try:
            data = sheet.get_all_records()
            print("get_all_records() succeeded.")
        except Exception as e:
            print(f"get_all_records() failed with: {e}")
            
    except Exception as e:
        print(f"Failed to access sheet: {e}")

if __name__ == "__main__":
    debug_gsheet()
