# -*- coding: utf-8 -*-
"""
Created on Tue Jul  9 16:59:30 2024

@author: Yunushan Gulsen
"""

import os
import pandas as pd

# Terms to omit from job titles
omitted_terms = [
"II", "III", "IV", "V", "senior", "sr", "lead", "director", "manager", "principal", "chief",
"head", "vp", "vice president", "executive", "experienced", "seasoned" , "Intern" , "Internship", "3", "4", "2", "Software", "Maintanence", "Technician", "Specialist",
"Tooling", "IT", "Radio", "RF", "Buyer", "Co-Op", "Electrical", "Apprentice", "Machinist", "Technician", "Data", "Manufacturing", "Manufacture",
"Expert", "Sales", "Production",
]

# List of keywords to include only specific jobs
include_terms = [
"Early", "Entry", "Associate", "Apprentice", "New Grad", "Junior", "Trainee", "Graduate" , "2025" , "2024" , "Structures", "Structural", "Aerodynamic",
"Dynamic", "astro", "Space", "Satellite", "Propulsion", "Integration", "Design",
]

def omitted_term_in_text(text, omitted_terms):
    normalized_text = text.lower().replace(" ", "")
    normalized_terms = [term.lower().replace(" ", "") for term in omitted_terms]
    return any(term in normalized_text for term in normalized_terms)

def include_term_in_text(text, include_terms):
    normalized_text = text.lower().replace(" ", "")
    normalized_terms = [term.lower().replace(" ", "") for term in include_terms]
    return any(term in normalized_text for term in normalized_terms)

def filter_jobs_by_terms(job_listings, omitted_terms, include_terms):
    filtered_listings = []
    seen_jobs = set()
    for job in job_listings:
        job_key = (job['Job Title'], job['Company'], job['Location'])
        if job_key not in seen_jobs:
            job_title = job['Job Title']
            if not omitted_term_in_text(job_title, omitted_terms) and include_term_in_text(job_title, include_terms):
                filtered_listings.append(job)
                seen_jobs.add(job_key)
    print(f"Filtered down to {len(filtered_listings)} jobs")  # Debug statement
    return filtered_listings

def filter_specific_csv(file_path):
    df = pd.read_csv(file_path)
    
    # Apply filtering
    job_listings = df.to_dict('records')
    filtered_job_listings = filter_jobs_by_terms(job_listings, omitted_terms, include_terms)
    
    # Save filtered results to a new CSV file
    directory, filename = os.path.split(file_path)
    filtered_filename = f"filtered_{filename}"
    filtered_file_path = os.path.join(directory, filtered_filename)
    filtered_df = pd.DataFrame(filtered_job_listings)
    filtered_df.to_csv(filtered_file_path, index=False)
    print(f"Filtered file saved as {filtered_file_path}")

if __name__ == "__main__":
    # Specify the full path to your CSV file
    file_path = r"C:\Users\yunus\Source\Repos\job_scraper\LinkedIn_Job_Scrapes\LinkedInJobs_Run10.csv"  # Provide the full path to your CSV file
    
    if os.path.exists(file_path):
        filter_specific_csv(file_path)
    else:
        print(f"The file does not exist at the specified path: {file_path}")
