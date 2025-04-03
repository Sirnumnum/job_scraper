# -*- coding: utf-8 -*-
"""
Created on Tue Jul  9 16:59:30 2024

@author: Yunushan Gulsen
"""

import os
import pandas as pd
import datetime # To add timestamp to log file name

# List of keywords to INCLUDE specific jobs (LEVEL or AERO DOMAIN)
include_terms = [
    # Level Indicators
    "Early", "Entry", "Associate", "Apprentice", "New Grad", "Junior", "Trainee", "Graduate", "Grad", "2025" , "2024", " I ", " 1 ",
    # Aero/Relevant Domains
    "Structures", "Structural", "Aerodynamic", "Dynamic", "astro", "Space", "Satellite", "Propulsion",
    "Integration", "Design", "Dynamics", "Aero", "Aerospace", "Aircraft", "Avionics", "Flight",
    "Test"
]

# Terms to OMIT (SENIORITY or NON-RELEVANT FIELDS)
omitted_terms = [
    # Seniority / Level Indicators
    "II", "III", "IV", "V", "senior", "sr", "lead", "director", "manager", "principal", "chief",
    "head", "vp", "vice president", "executive", "experienced", "seasoned", "3", "4", "2",

    # Specific Roles/Fields to Exclude
    "Software", "Electrical", "Technician", "Specialist", "Manufacturing", "Manufacture",
    "Production", "Data", "IT", "Finance", "Accountant", "Payable", "Analyst", "Sales",
    "Buyer", "Helper", "Operator", "Administrator", "Corporate", "Security",
    "Material Handler", "Driver", "Radio", "RF", "Machinist", "Tooling", "Maintanence",

    # Intern/Co-op
    "Intern", "Internship", "Co-Op",
]

# --- Helper function to find matching terms (for debugging) ---
def find_matching_terms(text, terms):
    normalized_text = str(text).lower().replace(" ", "")
    matching = []
    for term in terms:
        normalized_term = term.lower().replace(" ", "")
        if normalized_term and normalized_term in normalized_text: # Ensure term is not empty after normalization
            matching.append(term) # Return original term for clarity
    return matching
# --- End Helper ---


def omitted_term_in_text(text, omitted_terms):
    normalized_text = str(text).lower().replace(" ", "")
    normalized_terms = [term.lower().replace(" ", "") for term in omitted_terms]
    # Filter out empty strings that might result from terms like " I "
    normalized_terms = [term for term in normalized_terms if term]
    return any(term in normalized_text for term in normalized_terms)

def include_term_in_text(text, include_terms):
    normalized_text = str(text).lower().replace(" ", "")
    normalized_terms = [term.lower().replace(" ", "") for term in include_terms]
    # Filter out empty strings
    normalized_terms = [term for term in normalized_terms if term]
    return any(term in normalized_text for term in normalized_terms)


# MODIFIED filter_jobs_by_terms function with DEBUGGING TO FILE
def filter_jobs_by_terms(job_listings, omitted_terms, include_terms, log_file_path): # Added log_file_path parameter
    filtered_listings = []
    seen_jobs = set()

    # Open the log file in write mode ('w'). This will overwrite the file if it exists.
    # Use utf-8 encoding for broader character support.
    with open(log_file_path, 'w', encoding='utf-8') as log_f:
        log_f.write("--- Starting Filtering Process ---\n") # Mark start

        for i, job in enumerate(job_listings): # Use enumerate for progress indication
            job_title_raw = job.get('Job Title', '')
            company_raw = job.get('Company', '')
            location_raw = job.get('Location', '')

            job_key = (str(job_title_raw), str(company_raw), str(location_raw))

            if job_key not in seen_jobs:
                job_title = str(job_title_raw)
                company = str(company_raw)

                # --- Perform checks ---
                should_include = include_term_in_text(job_title, include_terms)
                should_omit = omitted_term_in_text(job_title, omitted_terms)

                # --- Log Block ---
                log_f.write(f"\nProcessing Record {i+1}: '{job_title}' ({company})\n")
                log_f.write(f"  Checking Inclusion: {should_include}\n")
                if should_include:
                    matches = find_matching_terms(job_title, include_terms)
                    log_f.write(f"    Matched Include Terms: {matches}\n")

                log_f.write(f"  Checking Omission: {should_omit}\n")
                if should_omit:
                    matches = find_matching_terms(job_title, omitted_terms)
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
                 # Log skipped duplicates if needed (optional)
                 # log_f.write(f"\nSkipping Duplicate: {job_key}\n")
                 pass


        log_f.write(f"\n--- Filtering Complete ---\n") # Mark end
        log_f.write(f"Filtered down to {len(filtered_listings)} jobs after applying include and then omit terms.\n")

    # Inform console user where the log is
    print(f"Detailed filtering log written to: {log_file_path}")
    print(f"Filtered down to {len(filtered_listings)} jobs.") # Also print final count to console
    return filtered_listings

# MODIFIED filter_specific_csv function to pass log file path
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
            df[col] = df[col].fillna('').astype(str)
    # --- End Cleaning Step ---

    job_listings = df.to_dict('records')

    # Define log file path (place it alongside the script or in a specific logs folder)
    script_dir = os.path.dirname(__file__) # Get directory where the script is running
    log_filename = f"filtering_log_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    log_file_path = os.path.join(script_dir, log_filename)

    # --- Pass log path to the filter function ---
    filtered_job_listings = filter_jobs_by_terms(job_listings, omitted_terms, include_terms, log_file_path)

    # Save filtered results (no changes needed here)
    if filtered_job_listings:
        directory, filename = os.path.split(file_path)
        # Make sure filtered filename is different from log filename
        filtered_filename = f"filtered_{filename}"
        if filtered_filename == log_filename: # Avoid rare collision
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
    file_path = r"C:\Users\yunus\Source\Repos\job_scraper\LinkedIn_Job_Scrapes\LinkedInJobs_Run11.csv"
    if os.path.exists(file_path):
        filter_specific_csv(file_path)
    else:
        print(f"The file does not exist at the specified path: {file_path}")