# -*- coding: utf-8 -*-
"""
Created on Tue Jul  9 16:59:30 2024

@author: Yunushan Gulsen
"""

import os
import pandas as pd
import datetime
import re # <--- Import the regex module

# List of keywords to INCLUDE specific jobs (LEVEL or AERO DOMAIN)
# No changes needed here usually, but ensure terms are distinct words
include_terms = [
    # Level Indicators
    "Early", "Entry", "Associate", "Apprentice", "New Grad", "Junior", "Trainee", "Graduate", "Grad", "2025" , "2024", " I ", " 1 ",
    # Aero/Relevant Domains
    "Structures", "Structural", "Aerodynamic", "Dynamic", "astro", "Space", "Satellite", "Propulsion",
    "Integration", "Design", "Dynamics", "Aero", "Aerospace", "Aircraft", "Avionics", "Flight",
    "Test"
]

# Terms to OMIT (SENIORITY or NON-RELEVANT FIELDS)
# IMPORTANT: Remove "Technician" if you want to keep relevant Technician roles
# Keep the simple words here (no added spaces needed now)
omitted_terms = [
    # Seniority / Level Indicators
    "II", "III", "IV", "V", "senior", "sr", "lead", "director", "manager", "principal", "chief",
    "head", "vp", "vice president", "executive", "experienced", "seasoned", "3", "4", "2", # Keep simple numbers

    # Specific Roles/Fields to Exclude
    "Software", "Electrical", #"Technician", # <-- REMOVED Technician, decide if you want it back
    "Specialist", "Manufacturing", "Manufacture",
    "Production", "Data", "IT", "Finance", "Accountant", "Payable", "Analyst", "Sales",
    "Buyer", "Helper", "Operator", "Administrator", "Corporate", "Security",
    "Material Handler", "Driver", "Radio", "RF", "Machinist", "Tooling", "Maintanence", "Technician", 
    "Maintenance", "Quality", "Assurance", "QA", "QC", "Inspection", "Inspector", "Physician", "Medical"
    , "Health", "Nurse", "Doctor", "Pharmacist", "Pharmacy", "Laboratory", "Lab", "Warehouse", "Painter", "Welder", 
    "Assembler", "Fabricator", "Construction", "Laborer", "Electrician", "Plumber", "Carpenter", "professor", "teacher",
    "instructor", "researcher", "scientist", "analyst", "consultant", "advisor", "counselor", "mentor",

    # Intern/Co-op
    "Intern", "Internship", "Co-Op",
]

# --- Helper function to find matching terms (using REGEX) ---
def find_matching_terms(text, terms):
    matching = []
    # Process the whole text once for efficiency if needed, but simple loop is fine here
    for term in terms:
        # Create a regex pattern for the term with word boundaries \b
        # re.escape handles any special regex characters in the term itself
        # (?i) makes the search case-insensitive inline
        # Use raw string r'...' for the pattern
        pattern = r'(?i)\b' + re.escape(term.strip()) + r'\b' # Use strip() just in case
        if re.search(pattern, str(text)):
            matching.append(term) # Return original term for clarity
    return matching
# --- End Helper ---

# --- REVISED term checking functions using REGEX ---
def omitted_term_in_text(text, omitted_terms):
    text_str = str(text) # Ensure string
    for term in omitted_terms:
        term_stripped = term.strip()
        if not term_stripped: continue # Skip empty terms
        pattern = r'(?i)\b' + re.escape(term_stripped) + r'\b'
        if re.search(pattern, text_str):
            return True # Found an omitted term
    return False # No omitted terms found

def include_term_in_text(text, include_terms):
    text_str = str(text) # Ensure string
    for term in include_terms:
        # Special handling for " I " or " 1 " if needed, or just treat as words
        term_stripped = term.strip() # " I " -> "I", " 1 " -> "1"
        if not term_stripped: continue # Skip empty terms
        pattern = r'(?i)\b' + re.escape(term_stripped) + r'\b'
        if re.search(pattern, text_str):
            return True # Found an include term
    return False # No include terms found
# --- End REVISED term checking functions ---


# MODIFIED filter_jobs_by_terms function (no changes needed inside, uses revised check functions)
def filter_jobs_by_terms(job_listings, omitted_terms, include_terms, log_file_path):
    filtered_listings = []
    seen_jobs = set()

    with open(log_file_path, 'w', encoding='utf-8') as log_f:
        log_f.write("--- Starting Filtering Process (Using Regex Word Boundaries) ---\n") # Note method

        for i, job in enumerate(job_listings):
            job_title_raw = job.get('Job Title', '')
            company_raw = job.get('Company', '')
            location_raw = job.get('Location', '')

            job_key = (str(job_title_raw), str(company_raw), str(location_raw))

            if job_key not in seen_jobs:
                job_title = str(job_title_raw)
                company = str(company_raw)

                # --- Perform checks (now using regex functions) ---
                should_include = include_term_in_text(job_title, include_terms)
                should_omit = omitted_term_in_text(job_title, omitted_terms) # Check omit only if include is true? Optional optimization

                # --- Log Block ---
                log_f.write(f"\nProcessing Record {i+1}: '{job_title}' ({company})\n")
                log_f.write(f"  Checking Inclusion: {should_include}\n")
                if should_include:
                    matches = find_matching_terms(job_title, include_terms) # Uses regex helper now
                    log_f.write(f"    Matched Include Terms: {matches}\n")

                # Log omission check regardless for full picture
                log_f.write(f"  Checking Omission: {should_omit}\n")
                if should_omit:
                    matches = find_matching_terms(job_title, omitted_terms) # Uses regex helper now
                    log_f.write(f"    Matched Omit Terms: {matches}\n")
                # --- END Log Block ---

                # --- Decision Logic ---
                if should_include and not should_omit:
                    log_f.write(f"  Decision: KEEP\n")
                    filtered_listings.append(job)
                    seen_jobs.add(job_key)
                else:
                     log_f.write(f"  Decision: DISCARD (Include: {should_include}, Omit: {should_omit})\n")
            else:
                 # log_f.write(f"\nSkipping Duplicate: {job_key}\n")
                 pass

        log_f.write(f"\n--- Filtering Complete ---\n")
        log_f.write(f"Filtered down to {len(filtered_listings)} jobs after applying include and then omit terms.\n")

    print(f"Detailed filtering log written to: {log_file_path}")
    print(f"Filtered down to {len(filtered_listings)} jobs.")
    return filtered_listings

# (filter_specific_csv and __main__ remain the same as the previous version
#  - they define the log path and call filter_jobs_by_terms)
def filter_specific_csv(file_path):
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Error: The file was not found at {file_path}")
        return
    except Exception as e:
        print(f"Error reading CSV file {file_path}: {e}")
        return

    # --- Data Cleaning Step ---
    if 'Job Title' not in df.columns:
        print(f"Error: 'Job Title' column not found in {file_path}")
        return
    for col in ['Job Title', 'Company', 'Location']:
        if col not in df.columns:
             print(f"Warning: Column '{col}' not found in {file_path}. Using empty strings.")
             df[col] = ''
        else:
            # Ensure string type for regex and fill NaN
            df[col] = df[col].fillna('').astype(str)
    # --- End Cleaning Step ---

    job_listings = df.to_dict('records')

    script_dir = os.path.dirname(os.path.abspath(__file__)) # Use abspath for reliability
    log_filename = f"filtering_log_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    log_file_path = os.path.join(script_dir, log_filename)

    filtered_job_listings = filter_jobs_by_terms(job_listings, omitted_terms, include_terms, log_file_path)

    if filtered_job_listings:
        directory, filename = os.path.split(file_path)
        filtered_filename = f"filtered_{filename}"
        if filtered_filename == log_filename:
             filtered_filename = f"filtered_output_{filename}"

        filtered_file_path = os.path.join(directory, filtered_filename)
        filtered_df = pd.DataFrame(filtered_job_listings)
        try:
            filtered_df.to_csv(filtered_file_path, index=False)
            print(f"Filtered CSV saved as {filtered_file_path}")
        except Exception as e:
            print(f"Error saving filtered CSV file {filtered_file_path}: {e}")
    else:
        print("No jobs remained after filtering. No output file created.")


if __name__ == "__main__":
    # Ensure the file path uses raw string or double backslashes
    file_path = r"C:\Users\yunus\Source\Repos\job_scraper\LinkedIn_Job_Scrapes\LinkedInJobs_Run11.csv"
    if os.path.exists(file_path):
        filter_specific_csv(file_path)
    else:
        print(f"The file does not exist at the specified path: {file_path}")