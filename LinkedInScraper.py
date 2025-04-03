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
import urllib.parse
from urllib.parse import urljoin

# Configuration variables
SCROLL_PAUSE_TIME = 0.2
MAX_SCROLL_ATTEMPTS = 40
DEBUG_MODE = False  # Set to True for debugging with first 5 companies, False for all companies

# Load the list of companies from the Companies.txt file
file_path = r"C:\Users\yunus\source\repos\job_scraper\Companies.txt"
try:
    with open(file_path, 'r') as file:
        companies = [line.strip() for line in file.readlines() if line.strip()]
except FileNotFoundError:
    print(f"ERROR: Companies.txt not found at path: {file_path}")
    print("Please create the file with one company name per line or correct the path.")
    exit()

if DEBUG_MODE:
    print("--- RUNNING IN DEBUG MODE ---")
    companies = companies[:5]

start_time = time.time()

def random_sleep(min_sleep=1.0, max_sleep=3.0):
    sleep_time = np.random.uniform(min_sleep, max_sleep)
    time.sleep(sleep_time)

def scrape_jobs_for_company(company):
    """
    Scrape job listings from LinkedIn Jobs, focusing on Entry/Associate roles.
    Added modal dismissal and improved robustness.
    """
    options = Options()
    options.use_chromium = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    driver = None
    all_jobs = []
    base_url = "https://www.linkedin.com/"

    try:
        driver = webdriver.Edge(options=options)
        wait = WebDriverWait(driver, 20)
        card_wait = WebDriverWait(driver, 5)

        print(f"\n--- Starting LinkedIn search for {company} (Entry/Associate) ---")
        encoded_company = urllib.parse.quote_plus(company)
        url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_company}&f_E=2%2C3&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"

        try:
            driver.get(url)
            print(f"Successfully loaded LinkedIn jobs page for {company}: {url}")
            random_sleep(2, 4)
        except Exception as e:
            print(f"Failed to load page for {company}: {str(e)}")
            return []

                # --- MODAL DISMISSAL - REVISED AGAIN (JavaScript Click) ---
        print("Checking for 'Sign in' modal...")
        try:
            modal_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'section[aria-modal="true"]')) # Wait for modal container
            )
            print("Modal container detected. Now looking for dismiss button using specific class...")

            # Wait specifically for the button to be PRESENT in the DOM using the more specific class
            dismiss_button_selector = 'button.contextual-sign-in-modal__modal-dismiss[aria-label="Dismiss"]'
            modal_dismiss_button = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, dismiss_button_selector))
            )
            print(f"Dismiss button ({dismiss_button_selector}) found in DOM. Attempting JavaScript click...")

            # Try clicking using JavaScript, which can sometimes bypass visibility/interactability issues
            driver.execute_script("arguments[0].click();", modal_dismiss_button)

            print("JavaScript click executed for modal dismissal.")
            random_sleep(1.5, 2.5) # Slightly longer sleep after JS click to ensure effect

            # Optional check to see if modal is truly gone after JS click
            try:
                WebDriverWait(driver, 3).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'section[aria-modal="true"]'))
                )
                print("Modal successfully dismissed (verified by absence).")
            except TimeoutException:
                print("Warning: Modal might still be present after JavaScript click attempt.")

        except TimeoutException:
            print("Modal not detected (or timed out waiting for container or dismiss button). Proceeding without dismissal.")
        except Exception as e:
            print(f"Error during modal dismissal process: {e}")
            # Optionally add traceback for more detailed error info
            import traceback
            print(traceback.format_exc())
        # --- END MODAL DISMISSAL - REVISED AGAIN ---

        # --- Scrolling Logic (remains the same) ---
        print(f"Scrolling to load jobs for {company}...")
        scroll_attempts = 0
        last_height = driver.execute_script("return document.body.scrollHeight")
        no_change_count = 0
        MAX_NO_CHANGE = 4

        while scroll_attempts < MAX_SCROLL_ATTEMPTS:
            scroll_attempts += 1
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_sleep(SCROLL_PAUSE_TIME, SCROLL_PAUSE_TIME + 1.0)

            try:
                see_more_button = driver.find_element(By.CSS_SELECTOR, ".infinite-scroller__show-more-button--visible")
                if see_more_button.is_displayed() and see_more_button.is_enabled():
                    print("Clicking 'See more jobs' button...")
                    driver.execute_script("arguments[0].click();", see_more_button)
                    random_sleep(2, 4)
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    no_change_count = 0
                    continue
            except NoSuchElementException:
                pass
            except Exception as e:
                 print(f"Error trying to click 'See more jobs' button: {e}")

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                no_change_count += 1
                if no_change_count >= MAX_NO_CHANGE:
                    print(f"Scroll height hasn't changed for {MAX_NO_CHANGE} attempts. Assuming all jobs loaded.")
                    break
            else:
                last_height = new_height
                no_change_count = 0

        print(f"Finished scrolling for {company} after {scroll_attempts} attempts. Proceeding to extract job cards.")

        job_cards = []
        try:
            job_card_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.jobs-search__results-list'))
            )
            job_cards = job_card_container.find_elements(By.TAG_NAME, 'li')
            print(f"Found job card container. Proceeding to extract job cards. Potential cards found: {len(job_cards)}")

        except TimeoutException:
            print(f"Timeout waiting for job card container 'ul.jobs-search__results-list' for {company}.")
            return []
        except Exception as e:
            print(f"Error finding job card container for {company}: {str(e)}")
            return []

        if not job_cards:
            try:
                no_results_el = driver.find_element(By.CSS_SELECTOR, '.jobs-search-results-list__no-results')
                if no_results_el.is_displayed():
                    print(f"LinkedIn shows no results for '{company}' with current filters.")
            except NoSuchElementException:
                 print(f"No job cards found within the container for {company}, and no specific 'no results' message detected.")
            return []

        for index, card in enumerate(job_cards, 1):
            job_info = {'source_company': company, 'card_index': index}

            card_wait_context = WebDriverWait(card, 5)

            try:
                try:
                    title_element = card_wait_context.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'h3.base-search-card__title'))
                    )
                    job_info['title'] = title_element.text.strip()
                except (NoSuchElementException, TimeoutException) as e:
                    job_info['title'] = "N/A"
                    print(f"Warning[Card {index}]: Title (h3.base-search-card__title) not found. Error: {type(e).__name__}")

                try:
                    company_element = card_wait_context.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'h4.base-search-card__subtitle a.hidden-nested-link'))
                    )
                    job_info['company'] = company_element.text.strip()
                except (NoSuchElementException, TimeoutException) as e:
                    job_info['company'] = "N/A"
                    print(f"Warning[Card {index}]: Company (h4.base-search-card__subtitle a.hidden-nested-link) not found. Error: {type(e).__name__}")

                try:
                    location_element = card_wait_context.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'span.job-search-card__location'))
                    )
                    job_info['location'] = location_element.text.strip()
                except (NoSuchElementException, TimeoutException) as e:
                    job_info['location'] = "N/A"
                    print(f"Warning[Card {index}]: Location (span.job-search-card__location) not found. Error: {type(e).__name__}")

                try:
                    link_element = card.find_element(By.CSS_SELECTOR, 'a.base-card__full-link')
                    raw_link = link_element.get_attribute('href')
                    job_info['link'] = urljoin(base_url, raw_link)
                except NoSuchElementException:
                    job_info['link'] = "N/A"
                    print(f"Warning[Card {index}]: Link (a.base-card__full-link) not found.")

                if job_info.get('title') != "N/A" and job_info.get('link') != "N/A":
                    all_jobs.append(job_info)
                else:
                    print(f"Skipping[Card {index}]: Missing title or link. Data: {job_info}")

            except Exception as e:
                print(f"Error processing job card {index} for {company}: {str(e)}")
                continue

    except TimeoutException:
        print(f"Timeout occurred while processing {company}. Page load issue or container selector timed out.")
    except Exception as e:
        print(f"Unexpected error during scraping {company}: {str(e)}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Error closing browser for {company}: {str(e)}")

    print(f"Completed LinkedIn scraping for {company}. Found {len(all_jobs)} valid jobs.")
    return all_jobs

all_scraped_jobs = []
MAX_WORKERS = 8
print(f"\nStarting scrape with {MAX_WORKERS} workers...")
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(scrape_jobs_for_company, company): company for company in companies}

    for future in as_completed(futures):
        company_name = futures[future]
        try:
            result = future.result()
            if result:
                all_scraped_jobs.extend(result)
            print(f"Finished processing future for: {company_name}")
        except Exception as e:
            print(f"Error retrieving result for {company_name}: {e}")

end_time = time.time()
elapsed_time = (end_time - start_time) / 60

print(f"\nTotal raw jobs scraped from LinkedIn: {len(all_scraped_jobs)}")

# Removing duplicate jobs (based on Title, Company, Link)
print("Starting to remove duplicate jobs...")
unique_jobs = []
seen_jobs = set()
for job in all_scraped_jobs:
    job_identifier = (job.get('title', '').lower(), job.get('company', '').lower(), job.get('link', ''))
    if job_identifier not in seen_jobs and job.get('link') != "N/A":
        unique_jobs.append(job)
        seen_jobs.add(job_identifier)
print(f"Duplicate removal complete. {len(unique_jobs)} unique jobs found.")


current_directory = os.path.dirname(os.path.abspath(__file__))
output_folder = os.path.join(current_directory, 'LinkedIn_Job_Scrapes')
if not os.path.exists(output_folder):
    os.makedirs(output_folder)
    print(f"Created output folder: {output_folder}")

run_number = 1
while True:
    csv_filename_unfiltered = f"LinkedInJobs_Run{run_number}.csv" # Changed filename to unfiltered as requested
    csv_filepath_unfiltered = os.path.join(output_folder, csv_filename_unfiltered)
    if not os.path.exists(csv_filepath_unfiltered):
        break
    run_number += 1

print(f"\nWriting {len(unique_jobs)} jobs to {csv_filepath_unfiltered}...") # Writing unique_jobs now
if unique_jobs:
    with open(csv_filepath_unfiltered, 'w', newline='', encoding='utf-8') as csv_file:
        fieldnames = ['Job Title', 'Company', 'Location', 'Link', 'Source Company']
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        csv_writer.writeheader()
        for job in unique_jobs: # Writing unique_jobs to CSV
            row = {
                'Job Title': job.get('title', 'N/A'),
                'Company': job.get('company', 'N/A'),
                'Location': job.get('location', 'N/A'),
                'Link': job.get('link', 'N/A'),
                'Source Company': job.get('source_company', 'N/A')
            }
            csv_writer.writerow(row)
    print(f"Unfiltered jobs successfully saved to {csv_filepath_unfiltered}") # Changed message to unfiltered
else:
    print("No jobs found after scraping. CSV file not created.")


print("\n--- Scraping Summary ---")
print(f"Script finished in {elapsed_time:.2f} minutes.")
print(f"Searched for {len(companies)} companies.")
print(f"Total raw job postings found: {len(all_scraped_jobs)}") # Updated summary
print(f"Total unique jobs found (after duplicate removal): {len(unique_jobs)}") # Updated summary
if unique_jobs:
    print(f"Unfiltered results saved to: {csv_filepath_unfiltered}") # Updated message