from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from scipy.stats import norm, poisson
import numpy as np

# Configuration variables
SCROLL_PAUSE_TIME = .2
DEBUG_MODE = False  # Set to True for debugging with first 5 companies, False for all companies

# List of keywords to include only specific jobs
include_terms = ["Early", "Entry", "Associate", "Apprentice", "New Grad", "Junior", "Trainee", "Graduate", "2025", "2024"]

# Terms to omit from job titles
omitted_terms =  ["II", "III", "IV", "V", "senior", "sr", "lead", "director", "manager", "principal", "chief", "head", "vp", "vice president", "executive", "experienced", "seasoned", "Intern", "Internship"]

# Load the list of companies from the Companies.txt file
file_path = r"C:\Users\yunus\source\repos\job_scraper\Companies.txt"
with open(file_path, 'r') as file:
    companies = [line.strip() for line in file.readlines()]

# Limit the number of companies if in DEBUG_MODE
if DEBUG_MODE:
    companies = companies[:5]

# Timer start
start_time = time.time()

# Function to generate a random sleep time
def random_sleep():
    lambda_value = np.random.uniform(1, 3)  # Randomly change lambda for the Poisson distribution
    sleep_time = poisson.rvs(mu=lambda_value, size=1)[0] + abs(norm.rvs(loc=0.5, scale=0.2, size=1)[0])
    sleep_time = max(0.5, sleep_time)  # Ensure a minimum sleep time
    print(f"Sleeping for {sleep_time:.2f} seconds")
    time.sleep(sleep_time)

# Function to scrape jobs for a single company
def scrape_jobs_for_company(company):
    """
    Scrape job listings from Google Jobs for a specific company.
    
    Args:
        company (str): Name of the company to search for
    
    Returns:
        list: List of dictionaries containing job details
    """
    options = Options()
    options.use_chromium = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")  # Set consistent window size
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = None
    all_jobs = []
    
    try:
        driver = webdriver.Edge(options=options)
        wait = WebDriverWait(driver, 10)
        print(f"\n--- Starting search for {company} ---")
        
        # Load the page with error handling
        try:
            url = f"https://www.google.com/search?q={company}+jobs&ibp=htl;jobs"
            driver.get(url)
            print(f"Successfully loaded page for {company}: {url}")
            random_sleep()
        except Exception as e:
            print(f"Failed to load page for {company}: {str(e)}")
            return []
        
        # Check for no jobs messages
        try:
            no_jobs_selectors = [
                'div.wDVoZ div.v3jTId',
                'div[jsname="gO3NVb"].VSHIPc'
            ]
            
            for selector in no_jobs_selectors:
                try:
                    message = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    message_text = message.text.lower()
                    if any(phrase in message_text for phrase in [
                        "no more jobs match your exact search",
                        "it looks like there aren't many 'jobs' matches",
                        "no jobs found"
                    ]):
                        print(f"No jobs found for {company}. Skipping this company.")
                        return []
                except TimeoutException:
                    continue
        except Exception as e:
            print(f"Error checking for no jobs messages: {str(e)}")
        
        # Scroll through results with improved handling
        last_height = driver.execute_script("return document.body.scrollHeight")
        no_change_count = 0
        MAX_NO_CHANGE = 3
        MAX_SCROLL_ATTEMPTS = 30  # Prevent infinite scrolling
        scroll_attempts = 0
        
        while no_change_count < MAX_NO_CHANGE and scroll_attempts < MAX_SCROLL_ATTEMPTS:
            scroll_attempts += 1
            print(f"Scroll attempt {scroll_attempts}/{MAX_SCROLL_ATTEMPTS}")
            
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_sleep()
            
            # Get new height
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            # Check for "No more jobs" message
            try:
                no_more_jobs = driver.find_element(By.CSS_SELECTOR, 'div[jsname="gO3NVb"].VSHIPc')
                if no_more_jobs.is_displayed():
                    print("Found 'No more jobs' message.")
                    break
            except NoSuchElementException:
                pass
            
            # Check if height changed
            if new_height == last_height:
                no_change_count += 1
                print(f"No height change detected ({no_change_count}/{MAX_NO_CHANGE})")
            else:
                no_change_count = 0
                last_height = new_height
        
        print(f"Finished scrolling for {company}, proceeding to extract job cards.")
        
        # Extract job cards with improved error handling
        try:
            job_cards = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[jscontroller="b11o3b"]'))
            )
            print(f"Found {len(job_cards)} job cards for {company}.")
            
            for index, card in enumerate(job_cards, 1):
                try:
                    # Use WebDriverWait for each element to ensure they're loaded
                    title = WebDriverWait(card, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'tNxQIb.PUpOsf'))
                    ).text
                    
                    company_name = WebDriverWait(card, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'wHYlTd.MKCbgd.a3jPc'))
                    ).text
                    
                    location = WebDriverWait(card, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'wHYlTd.FqK3wc.MKCbgd'))
                    ).text
                    
                    # Clean up location
                    location = location.split('•')[0].strip() if '•' in location else location
                    
                    link = WebDriverWait(card, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a.MQUd2b'))
                    ).get_attribute('href')
                    
                    print(f"Successfully processed job card {index}/{len(job_cards)}")
                    
                    job_info = {
                        'title': title.strip(),
                        'company': company_name.strip(),
                        'location': location.strip(),
                        'link': link,
                        'source_company': company  # Add original search company
                    }
                    
                    all_jobs.append(job_info)
                    
                except TimeoutException:
                    print(f"Timeout while processing job card {index}/{len(job_cards)}")
                    continue
                except Exception as e:
                    print(f"Error processing job card {index}/{len(job_cards)}: {str(e)}")
                    continue
                    
        except TimeoutException:
            print(f"Timeout while waiting for job cards for {company}")
        except Exception as e:
            print(f"Error extracting job cards for {company}: {str(e)}")
            
    except Exception as e:
        print(f"Unexpected error processing {company}: {str(e)}")
        
    finally:
        if driver:
            try:
                driver.quit()
                print(f"Successfully closed browser for {company}")
            except Exception as e:
                print(f"Error closing browser for {company}: {str(e)}")
    
    print(f"Completed scraping for {company}. Found {len(all_jobs)} jobs.")
    return all_jobs

# Initialize the ThreadPoolExecutor
all_scraped_jobs = []
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(scrape_jobs_for_company, company) for company in companies]

    for future in as_completed(futures):
        all_scraped_jobs.extend(future.result())

# Timer end
end_time = time.time()
elapsed_time = (end_time - start_time) / 60  # Convert to minutes

# Debug statement to show the total number of jobs found before filtering
print(f"\nTotal jobs found before filtering: {len(all_scraped_jobs)}")

# Get the current working directory
current_directory = os.path.dirname(os.path.abspath(__file__))

# Create JobScraper3 folder if it doesn't exist
output_folder = os.path.join(current_directory, 'JobScraper3')
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Determine the next available file name for unfiltered jobs (e.g., ScrapedJobs1.csv)
run_number = 1
while True:
    csv_filename_unfiltered = f"ScrapedJobs{run_number}.csv"
    csv_filepath_unfiltered = os.path.join(output_folder, csv_filename_unfiltered)
    if not os.path.exists(csv_filepath_unfiltered):
        break
    run_number += 1

# Write the unfiltered jobs to the CSV file
print(f"Writing unfiltered jobs to {csv_filepath_unfiltered}...")
with open(csv_filepath_unfiltered, 'w', newline='', encoding='utf-8') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(['Job Title', 'Company', 'Location', 'Link'])
    for job in all_scraped_jobs:
        csv_writer.writerow([job['title'], job['company'], job['location'], job['link']])

print(f"Unfiltered jobs saved in {csv_filepath_unfiltered}")

# ======== COMMENTED OUT FILTERING LOGIC ========
# # Filter 1: Removing duplicate jobs
# print("Starting Filter 1: Removing duplicate jobs...")
# unique_jobs = []
# seen_jobs = set()
# for job in all_scraped_jobs:
#     job_identifier = (job['title'], job['company'], job['link'])
#     if job_identifier not in seen_jobs:
#         unique_jobs.append(job)
#         seen_jobs.add(job_identifier)
# print(f"Filter 1 complete. {len(unique_jobs)} unique jobs found.")

# # Filter 2: Omit jobs based on omitted_terms
# print("Starting Filter 2: Omitting jobs with specified terms...")
# omit_filtered_jobs = []
# for job in unique_jobs:
#     if not any(term.lower() in job['title'].lower() for term in omitted_terms):
#         omit_filtered_jobs.append(job)
# print(f"Filter 2 complete. {len(omit_filtered_jobs)} jobs remaining after omitting specified terms.")

# # Filter 3: Include jobs only if they match the include_terms
# print("Starting Filter 3: Including jobs with specific terms...")
# filtered_jobs = []
# for job in omit_filtered_jobs:
#     if any(term.lower() in job['title'].lower() for term in include_terms):
#         filtered_jobs.append(job)
# print(f"Filter 3 complete. {len(filtered_jobs)} jobs remaining after filtering specific terms.")

# # Filter 4: Verify company name matches
# print("Starting Filter 4: Verifying company name matches...")
# final_jobs = []
# for job in filtered_jobs:
#     if any(company.lower() in job['company'].lower() for company in companies):
#         final_jobs.append(job)
# print(f"Filter 4 complete. {len(final_jobs)} jobs remaining after verifying company names.")

# Remove the filtered jobs file creation and final_jobs reference
csv_filename_unfiltered = f"UnfilteredJobs{run_number}.csv"
csv_filepath_unfiltered = os.path.join(output_folder, csv_filename_unfiltered)

# Write the unfiltered jobs to the CSV file
print(f"Writing unfiltered jobs to {csv_filepath_unfiltered}...")
with open(csv_filepath_unfiltered, 'w', newline='', encoding='utf-8') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(['Job Title', 'Company', 'Location', 'Link'])
    for job in all_scraped_jobs:
        csv_writer.writerow([job['title'], job['company'], job['location'], job['link']])

print(f"Unfiltered jobs saved in {csv_filepath_unfiltered}")
print(f"Scraping completed in {elapsed_time:.2f} minutes")
print(f"Total unfiltered jobs found: {len(all_scraped_jobs)}")  # Changed to all_scraped_jobs