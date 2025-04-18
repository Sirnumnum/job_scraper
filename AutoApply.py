# -*- coding: utf-8 -*-

import traceback
import csv
import os
import time
import json
import re
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementNotInteractableException,
    StaleElementReferenceException, MoveTargetOutOfBoundsException
)
from selenium.webdriver.support.ui import Select  # Needed for standard dropdowns
from selenium.webdriver.common.keys import Keys

# --- Configuration ---
SCRAPER_OUTPUT_FOLDER = r"C:\Users\yunus\source\repos\job_scraper\LinkedIn_Job_Scrapes"  # CHANGE IF NEEDED
CSV_FILENAME_PATTERN = "filtered_LinkedInJobs_Run{}.csv"  # Pattern to find the CSV
APPLY_MARKER_COLUMN = "Apply Status"  # Column header you added manually
APPLY_MARKER_VALUE = "Apply"  # Value indicating you want to apply
ANSWERS_DB_FILE = "application_answers.json"
COMPANY_FLOWS_FILE = "company_flows.json"
WAIT_TIMEOUT = 5  # Seconds to wait for elements

# --- Helper Functions ---

def find_latest_csv(folder_path, pattern):
    """Finds the CSV file with the highest run number."""
    latest_run = 0
    latest_file = None
    try:
        for filename in os.listdir(folder_path):
            base_name = pattern.split('{}')[0]
            if filename.startswith(base_name) and filename.endswith(".csv"):
                try:
                    # Extract run number using regex for safety
                    match = re.search(r'Run(\d+)\.csv$', filename)
                    if match:
                        run_num = int(match.group(1))
                        if run_num > latest_run:
                            latest_run = run_num
                            latest_file = os.path.join(folder_path, filename)
                except (ValueError, IndexError):
                    continue  # Ignore files not matching the pattern exactly
    except FileNotFoundError:
        print(f"ERROR: Output folder not found: {folder_path}")
        return None

    if latest_file:
        print(f"Found latest CSV: {latest_file}")
    else:
        print(f"ERROR: No CSV files matching pattern '{pattern}' found in {folder_path}")
    return latest_file

def load_answers(filepath):
    """Loads the Q&A database from JSON."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {filepath}. Starting with empty answers.")
            return {}
        except Exception as e:
            print(f"Error loading answers from {filepath}: {e}")
            return {}
    return {}

def save_answers(filepath, answers_db):
    """Saves the Q&A database to JSON."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(answers_db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving answers to {filepath}: {e}")

def normalize_question(text):
    """Cleans question text for better matching."""
    if not text:
        return ""
    # Lowercase, strip whitespace, remove common punctuation that might vary
    text = text.lower().strip()
    text = re.sub(r'[.:*?]+$', '', text)  # Remove trailing punctuation often found in labels
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text.strip()

def normalize_text(text):
    """Normalizes text for comparison by handling quotes and spaces."""
    if not text:
        return ""
    # Replace curly quotes with straight quotes
    text = text.replace('“', '"').replace('”', '"')
    # Remove extra spaces and normalize
    return text.strip()

def get_associated_label(driver, element):
    """Tries to find the <label> associated with a form element."""
    try:
        # 1. Try finding label by 'for' attribute matching element's ID
        element_id = element.get_attribute('id')
        if element_id:
            # Need to escape quotes if ID contains them, although rare
            escaped_id = element_id.replace('"', '\\"')
            try:
                label = driver.find_element(By.CSS_SELECTOR, f'label[for="{escaped_id}"]')
                return label.text
            except NoSuchElementException:
                pass  # Fall through to other methods

        # 2. Try finding label by traversing upwards to a common parent (e.g., div, p)
        #    and looking for a label sibling or child label. This is highly structure-dependent.
        parent = element.find_element(By.XPATH, '..')
        try:
            label = parent.find_element(By.TAG_NAME, 'label')
            return label.text
        except NoSuchElementException:
            # Try grandparent
            grandparent = parent.find_element(By.XPATH, '..')
            try:
                label = grandparent.find_element(By.TAG_NAME, 'label')
                return label.text
            except NoSuchElementException:
                pass  # Fall through

        # 3. Try finding preceding sibling label (less reliable)
        try:
            label = element.find_element(By.XPATH, 'preceding-sibling::label')
            return label.text
        except NoSuchElementException:
            pass

        # 4. As a last resort, maybe placeholder text or aria-label?
        placeholder = element.get_attribute('placeholder')
        if placeholder:
            return placeholder  # Often a good hint

        aria_label = element.get_attribute('aria-label')
        if aria_label:
            return aria_label

    except StaleElementReferenceException:
        print("Warning: Stale element reference while trying to find label.")
        return None
    except Exception as e:
        print(f"Warning: Error finding label: {e}")
        return None
    return None  # No label found

def attempt_fill_field(element, answer):
    """Attempts to fill a form field with the given answer."""
    try:
        tag_name = element.tag_name.lower()
        element_type = element.get_attribute('type')

        # Clear field first if it's a text input or textarea
        if tag_name in ['input', 'textarea'] and element_type not in ['checkbox', 'radio', 'submit', 'button', 'file']:
            try:
                element.clear()
                time.sleep(0.2)  # Small pause after clear
            except ElementNotInteractableException:
                print("Warning: Field not interactable for clearing.")

        if tag_name == 'input' or tag_name == 'textarea':
            if element_type not in ['checkbox', 'radio', 'submit', 'button', 'file']:
                element.send_keys(answer)
                print(f"   Attempted to fill field with: '{answer[:30]}...'")
                return True
        elif tag_name == 'select':
            try:
                select = Select(element)
                select.select_by_visible_text(answer)
                print(f"   Attempted to select dropdown option: '{answer}'")
                return True
            except NoSuchElementException:
                print(f"   Warning: Option '{answer}' not found in dropdown.")
                try:
                    select.select_by_value(answer)
                    print(f"   Attempted to select dropdown by value: '{answer}'")
                    return True
                except NoSuchElementException:
                    print(f"   Warning: Value '{answer}' also not found in dropdown.")
            except Exception as e_select:
                print(f"   Error selecting dropdown option: {e_select}")
    except ElementNotInteractableException:
        print("   Warning: Element not interactable. Could not fill.")
    except StaleElementReferenceException:
        print("   Warning: Stale element reference during filling.")
    except Exception as e:
        print(f"   Error attempting to fill field: {e}")
    return False

def attempt_action_click(driver, element, locator=None):
    """Tries to click an element using ActionChains with retry and JS fallback."""
    is_checkbox = False
    try: # Check if it's a checkbox safely
         if element.get_attribute('type') == 'checkbox': is_checkbox = True
    except: pass

    for attempt in range(2): # Retry up to 2 times
        try:
            if attempt > 0 and locator:
                 print("    Re-finding element due to previous error...")
                 element = WebDriverWait(driver, 3).until(EC.presence_of_element_located(locator))
                 driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element); time.sleep(0.2)

            print(f"    Attempting ActionChains click (Attempt {attempt+1})...")
            actions = ActionChains(driver)
            actions.move_to_element(element).pause(0.1).click().perform() # Added tiny pause
            print("    ActionChains click performed.")
            time.sleep(0.3)
            return True # Success
        except StaleElementReferenceException:
            print(f"    Stale element detected on ActionChains click attempt {attempt + 1}.")
            if attempt == 1: print("    Final ActionChains attempt failed due to staleness.") # Failed last retry
            # Loop continues to possibly re-find element if locator provided
        except (ElementNotInteractableException, MoveTargetOutOfBoundsException) as action_err:
            print(f"    ActionChains click failed ({type(action_err).__name__}).")
            # --- MODIFICATION START ---
            # Try JavaScript click as fallback, especially useful for checkboxes
            print("    Trying JavaScript click as fallback...")
            try:
                driver.execute_script("arguments[0].click();", element)
                print("    JavaScript click performed.")
                time.sleep(0.3)
                return True # JS click succeeded
            except Exception as js_err:
                print(f"    JavaScript click also failed: {js_err}")
                # If JS fails on the last attempt, return False overall
                if attempt == 1: return False
            # --- MODIFICATION END ---
        except Exception as action_other_err:
            print(f"    ActionChains click failed (Other Error: {action_other_err}).")
            # If other error on last attempt, return False
            if attempt == 1: return False

    print("    Failed to click element after multiple attempts.")
    return False # Return False if all attempts failed

# --- Add new helper functions ---

def load_company_flows(filepath):
    """Loads the company application flow database."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {filepath}. Starting empty.")
            return {}
        except Exception as e:
            print(f"Error loading company flows from {filepath}: {e}")
            return {}
    return {}

def save_company_flows(filepath, company_flows_db):
    """Saves the company application flow database."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(company_flows_db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving company flows to {filepath}: {e}")

def get_company_key(company_name):
    """Normalizes company name for use as a dictionary key."""
    if not company_name: return None
    # Lowercase, remove common suffixes, normalize spaces
    key = company_name.lower()
    key = re.sub(r'[,.\s]*(inc|llc|ltd|corp|corporation|incorporated)$', '', key).strip()
    key = re.sub(r'\s+', '_', key) # Replace spaces with underscore
    return key

# --- Main Script ---
if __name__ == "__main__":
    latest_csv = find_latest_csv(SCRAPER_OUTPUT_FOLDER, CSV_FILENAME_PATTERN) # Use filtered pattern
    if not latest_csv:
        exit()

    answers_db = load_answers(ANSWERS_DB_FILE)
    company_flows = load_company_flows(COMPANY_FLOWS_FILE) # Load company flows
    jobs_to_apply = []

    # 1. Read the CSV and find marked jobs
    try:
        with open(latest_csv, 'r', newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            if APPLY_MARKER_COLUMN not in reader.fieldnames:
                 raise ValueError(f"Column '{APPLY_MARKER_COLUMN}' not found.")
            for i, row in enumerate(reader):
                apply_status = row.get(APPLY_MARKER_COLUMN, '').strip().lower()
                link = row.get('Link', '').strip()
                company_name = row.get('Company', '').strip() # Get company name
                if apply_status == APPLY_MARKER_VALUE.lower():
                    if link and link != 'N/A' and company_name: # Ensure company name exists
                        jobs_to_apply.append({
                            'row_num': i + 2, 'title': row.get('Job Title', 'N/A'),
                            'company': company_name, 'link': link }) # Store company name
                    else:
                        print(f"Skipping Row {i + 2} ({row.get('Job Title', 'N/A')}): Missing Link or Company Name")
    except FileNotFoundError:
        print(f"ERROR: CSV file not found: {latest_csv}")
        exit()
    except ValueError as ve:
        print(f"ERROR: {ve}")
        exit()
    except Exception as e:
        print(f"Error reading CSV file {latest_csv}: {e}")
        exit()

    if not jobs_to_apply:
        print(f"No jobs marked '{APPLY_MARKER_VALUE}' found in {latest_csv}.")
        exit()
    print(f"\nFound {len(jobs_to_apply)} jobs marked for application help.")

    driver = None
    for job_index, job in enumerate(jobs_to_apply): # <<< OUTER JOB LOOP START >>>
        print(f"\n--- Processing Job {job_index + 1}/{len(jobs_to_apply)} (Row {job['row_num']}): {job['title']} at {job['company']} ---")
        print(f"Link: {job['link']}")
        company_key = get_company_key(job['company'])
        if not company_key:
             print("ERROR: Could not determine company key. Skipping job.")
             continue

        # <<< START OF TRY BLOCK FOR A SINGLE JOB >>>
        try:
            # --- Browser Setup ---
            options = Options()
            options.use_chromium = True
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--start-maximized")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            driver = webdriver.Edge(options=options)
            wait = WebDriverWait(driver, WAIT_TIMEOUT) # Main wait

            # --- 1. Navigate ---
            print(f"Navigating to initial link: {job['link']}")
            driver.get(job['link'])
            time.sleep(1.5)

            # --- 2. Dismiss Initial LinkedIn Modal ---
            print("Checking for initial 'Sign in' modal...")
            try:
                WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'section[aria-modal="true"]')))
                print("Modal container detected. Attempting dismissal...")
                dismiss_locator = (By.CSS_SELECTOR, 'button.contextual-sign-in-modal__modal-dismiss[aria-label="Dismiss"]')
                try:
                    modal_dismiss_button = WebDriverWait(driver, 7).until(EC.presence_of_element_located(dismiss_locator))
                    print("  Dismiss button found.")
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modal_dismiss_button)
                        time.sleep(0.2)
                    except Exception as scroll_err:
                         print(f"    Warning: Error scrolling dismiss button: {scroll_err}")
                         pass # Ignore scroll errors
                    if attempt_action_click(driver, modal_dismiss_button, dismiss_locator):
                        print("  Dismissed successfully.")
                        time.sleep(1.5)
                    else:
                        print("  Dismiss click failed. Proceeding anyway.")
                except TimeoutException:
                    print("  Warning: Dismiss button not found.")
                except Exception as e_dismiss:
                    print(f"  Error dismissing modal: {e_dismiss}")
            except TimeoutException:
                print("Initial modal not detected.")
            except Exception as e_modal_outer:
                print(f"Error checking for initial modal: {e_modal_outer}")


            # --- 3. Click First Apply Button (LinkedIn) ---
            print("\nSearching for FIRST 'Apply' button...")
            first_apply_clicked = False
            possible_first_apply_selectors = ['button.top-card-layout__cta--primary.btn-primary', 'button[data-tracking-control-name="public_jobs_apply-link-offsite_sign-up-modal"]', "//button[normalize-space(.)='Apply' and not(@aria-label='Dismiss')]", 'button[data-modal="sign-up-modal-outlet"]']
            for selector in possible_first_apply_selectors:
                try:
                    print(f"Trying selector: {selector}")
                    locator = None
                    if selector.startswith('/'):
                        locator = (By.XPATH, selector)
                    else:
                        locator = (By.CSS_SELECTOR, selector)

                    first_apply_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(locator))
                    print("Found FIRST Apply button.")
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_apply_button)
                        time.sleep(0.3)
                    except Exception as scroll_err:
                         print(f"    Warning: Error scrolling apply button: {scroll_err}")
                    first_apply_button.click() # Standard click
                    print("Clicked FIRST Apply button.")
                    first_apply_clicked = True
                    break # Exit loop once clicked
                except TimeoutException:
                    print(f"Selector '{selector}' timed out.")
                    continue # Try next selector
                except Exception as e_click:
                    print(f"Error clicking FIRST Apply button with selector '{selector}': {e_click}")
                    continue # Try next selector
            if not first_apply_clicked:
                 raise Exception("Could not find/click FIRST Apply button.")

            # --- 3b. Handle Secondary LinkedIn Modal / Navigate ---
            print("\nChecking for secondary modal / direct link...")
            company_link_locator = (By.CSS_SELECTOR, 'a[data-tracking-control-name="public_jobs_apply-link-offsite_sign-up-modal-sign-up-later"]')
            secondary_modal_container = (By.CSS_SELECTOR, 'div.sign-up-modal__direct-apply-on-company-site')
            try:
                WebDriverWait(driver, 4).until(EC.presence_of_element_located(secondary_modal_container))
                print("Secondary modal detected. Extracting company link...")
                try:
                    link_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located(company_link_locator))
                    company_href = link_element.get_attribute('href')
                    if company_href:
                        print(f"  Extracted href: {company_href}")
                        driver.get(company_href)
                        print("  Navigated directly.")
                        time.sleep(2.5)
                    else:
                        print("  Warning: href attribute empty.")
                except TimeoutException:
                    print("  Warning: Company link not found.")
                except Exception as e_href:
                    print(f"  Error getting/navigating href: {e_href}")
            except TimeoutException:
                print("Secondary modal not detected. Assuming direct redirect.")
                time.sleep(1.5)

            # --- Reached Company Application Site ---
            print("\n--- Reached Company Application Site ---")
            print(f"Company Key: {company_key}")
            print(f"Current ATS URL: {driver.current_url}")

            # --- 2. Determine Flow: New or Existing? --- (Using original numbering for clarity)
            current_flow_steps = company_flows.get(company_key)
            is_new_flow = not current_flow_steps
            if is_new_flow:
                print(f"No stored flow found for '{job['company']}'. Defining new flow...")
                company_flows[company_key] = [] # Initialize empty flow
                current_flow_steps = company_flows[company_key]
            else:
                print(f"Found stored flow for '{job['company']}'. Executing...")

            # --- 3. Execute or Define Application Flow --- (Using original numbering)
            step_index = 0
            max_steps = 20 # Safety limit for steps in a flow
            group_question_map = {} # Initialize group map for this job

            while step_index < max_steps: # <<< OUTER STEP PROCESSING LOOP START >>>
                print(f"\n--- Processing Step {step_index + 1} ---")
                print(f"Current URL: {driver.current_url}")
                step_definition = None
                action_taken = False # Flag if an action was completed in this step

                # --- A. If Existing Flow, Get Step Definition ---
                if not is_new_flow and step_index < len(current_flow_steps):
                    step_definition = current_flow_steps[step_index]
                    print(f"Executing stored step: {step_definition}")
                # --- B. If New Flow, Ask User for Step Definition ---
                elif is_new_flow:
                    while True:
                        page_type = input("What type of page is this? (L=Login, I=Intermediate Action, F=Form Page, S=Submit/Stop Here): ").strip().upper()
                        if page_type in ['L', 'I', 'F', 'S']:
                            break
                        else:
                            print("Invalid input. Please enter L, I, F, or S.")

                    if page_type == 'L':
                        step_definition = {'type': 'LOGIN'}
                    elif page_type == 'I':
                        print("This page requires clicking a button to proceed (e.g., 'Apply to Job', 'Start').")
                        button_desc = input("Enter a short description for this button: ").strip()
                        button_selector = input(f"Enter a unique CSS Selector or XPath for the '{button_desc}' button: ").strip()
                        step_definition = {'type': 'INTERMEDIATE_ACTION', 'selector': button_selector, 'description': button_desc}
                    elif page_type == 'F':
                        print("This is a page with form fields to fill.")
                        next_q = input("Is there a 'Next' or 'Continue' button on THIS page to go to more questions? (y/n): ").strip().lower()
                        next_button_selector = None
                        if next_q == 'y':
                            next_button_selector = input("Enter a unique CSS Selector or XPath for the 'Next/Continue' button: ").strip()
                        step_definition = {'type': 'FORM_PAGE', 'next_button_selector': next_button_selector}
                    elif page_type == 'S':
                        step_definition = {'type': 'FINAL_SUBMIT'}

                    current_flow_steps.append(step_definition) # Add defined step to flow
                    save_company_flows(COMPANY_FLOWS_FILE, company_flows) # Save immediately
                    print(f"Saved step definition: {step_definition}")
                # --- C. If End of Stored Flow (but not FINAL_SUBMIT), Ask User ---
                elif not is_new_flow and step_index >= len(current_flow_steps):
                     print("Reached end of stored flow, but not marked as final.")
                     # Ask user what to do next - treat as defining new step
                     is_new_flow = True # Switch to definition mode
                     step_index -= 1 # Decrement index to redefine this step position
                     continue # Restart loop iteration to ask user

                # --- D. Execute the Determined Step ---
                step_type = step_definition.get('type')

                if step_type == 'LOGIN':
                    print("Executing LOGIN step...")
                    try:
                        password_locator = (By.CSS_SELECTOR, "input[type='password']")
                        password_field = WebDriverWait(driver, 7).until(EC.presence_of_element_located(password_locator)) # Slightly longer wait
                        username_selectors = ["input[type='email']", "input[id*='user']", "input[name*='user']", "input[id*='email']", "input[name*='mail']"]
                        username_field = None
                        for sel in username_selectors:
                            try:
                                username_field = driver.find_element(By.CSS_SELECTOR, sel)
                                break
                            except NoSuchElementException:
                                continue
                        if username_field and password_field:
                            print("\n>>> LOGIN REQUIRED <<<")
                            login_email = input("Enter Login Email/Username: ").strip()
                            login_password = getpass.getpass("Enter Login Password: ")
                            username_field.send_keys(login_email)
                            time.sleep(0.2)
                            password_field.send_keys(login_password)
                            time.sleep(0.2)
                            signin_selectors = ["button[type='submit']", "input[type='submit']", "//button[normalize-space(.)='Sign in']", "button[id*='login']", "button[id*='signin']"]
                            signin_button = None
                            signin_locator = None
                            for sel in signin_selectors:
                                try:
                                    locator = (By.XPATH, sel) if sel.startswith('/') else (By.CSS_SELECTOR, sel)
                                    signin_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(locator))
                                    signin_locator=locator
                                    break
                                except:
                                    continue
                            if signin_button:
                                print("Clicking Sign In button...")
                                if attempt_action_click(driver, signin_button, signin_locator):
                                    print("Login submitted. Waiting...")
                                    time.sleep(4)
                                else:
                                    print("ERROR: Failed to click Sign In button. Manual login required.")
                                    input("Please log in manually and press Enter...")
                            else:
                                print("ERROR: Could not find Sign In button.")
                                input("Please log in manually and press Enter...")
                        else:
                            print("Warning: Could not find both username/password fields.")
                            input("Please log in manually and press Enter...")
                        action_taken = True # Mark action as taken (even if manual)
                    except TimeoutException:
                        print("Login fields not found for LOGIN step.")
                        input("Please log in manually and press Enter...")
                        action_taken = True # Assume user handled
                    except Exception as e_login_step:
                        print(f"Error during LOGIN step execution: {e_login_step}")
                        input("Please handle login manually and press Enter...")
                        action_taken = True # Assume user handled

                elif step_type == 'INTERMEDIATE_ACTION':
                    print(f"Executing INTERMEDIATE_ACTION: Click '{step_definition.get('description', 'button')}'")
                    selector = step_definition.get('selector')
                    if not selector:
                        print("ERROR: No selector stored for intermediate action!")
                        break # Stop if flow is broken
                    try:
                        locator = (By.XPATH, selector) if selector.startswith('/') else (By.CSS_SELECTOR, selector)
                        action_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(locator))
                        print(f"Found button: '{action_button.text[:30]}...'")
                        if attempt_action_click(driver, action_button, locator):
                            print("Clicked intermediate button successfully. Waiting...")
                            time.sleep(3)
                            action_taken = True
                        else:
                             print("ERROR: Failed to click intermediate button. Manual action needed.")
                             input("Please click the button manually and press Enter...")
                             action_taken = True # Assume user did it
                    except TimeoutException:
                        print(f"ERROR: Could not find intermediate button with selector: {selector}")
                        input("Please click the button manually and press Enter...")
                        action_taken = True
                    except Exception as e_inter_click:
                        print(f"Error clicking intermediate button: {e_inter_click}")
                        input("Please click the button manually and press Enter...")
                        action_taken = True

                elif step_type == 'FORM_PAGE':
                    print("Executing FORM_PAGE step...")
                    next_button_selector = step_definition.get('next_button_selector')
                    print(f"Next button selector for this page: {next_button_selector}")

                    # --- Run Group Scan if map is empty ---
                    if not group_question_map:
                        print("Running group scan...")
                        try:
                            all_inputs_page = driver.find_elements(By.TAG_NAME, 'input')
                            for element in all_inputs_page:
                                if not element.is_displayed():
                                    continue
                                try:
                                    elem_type = element.get_attribute('type').lower() if element.tag_name == 'input' else None
                                    if elem_type in ['checkbox', 'radio']:
                                        input_name = element.get_attribute('name')
                                        if not input_name:
                                            continue
                                        group_question = get_associated_label(driver, element)
                                        if not group_question:
                                            try:
                                                fieldset=element.find_element(By.XPATH,'./ancestor::fieldset[1]')
                                                legend=fieldset.find_element(By.TAG_NAME,'legend')
                                                group_question=legend.text.strip()
                                            except:
                                                pass # Ignore if no fieldset/legend
                                        if group_question and input_name not in group_question_map:
                                            group_question_map[input_name] = normalize_question(group_question)
                                            print(f"  Group ID'd: '{group_question_map[input_name]}'")
                                except StaleElementReferenceException:
                                    continue
                                except Exception as e_gid:
                                    print(f"    Minor error during group ID: {e_gid}")
                        except Exception as e_pass1_page:
                            print(f"Error page group scan: {e_pass1_page}")

                    # --- Start Tabbing Logic ---
                    processed_elements_ids_page = set()
                    processed_group_questions_page = set()
                    max_tabs_page = 150
                    tab_count_page = 0
                    consecutive_skips_page = 0
                    max_consecutive_skips_page = 15
                    nav_button_focused = None # Store the nav button if focus lands on it

                    try:
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                        time.sleep(0.3) # Initial Tab
                    except Exception as e_init_tab:
                        print(f"    Warning: Error sending initial tab: {e_init_tab}")

                    # <<< --- START OF INNER TABBING LOOP --- >>>
                    while tab_count_page < max_tabs_page:
                        tab_count_page += 1
                        active_element = None
                        interaction_handled = False
                        try:
                            active_element = driver.execute_script("return document.activeElement;")
                            if active_element is None:
                                print(f"Tab {tab_count_page}: No active. Tabbing.")
                                try:
                                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                                except Exception as e_body_tab:
                                     print(f"    Error sending tab from body: {e_body_tab}")
                                time.sleep(0.2)
                                continue

                            element_id = active_element.get_attribute('id')
                            element_html_snippet = active_element.get_attribute('outerHTML')[:80]
                            current_element_processed = False
                            if element_id and element_id in processed_elements_ids_page:
                                print(f"Tab {tab_count_page}: Focus possibly stuck on processed ID {element_id}. Forcing TAB.")
                                try:
                                    active_element.send_keys(Keys.TAB)
                                except Exception as e_stuck_tab:
                                     print(f"    Error sending tab from stuck element: {e_stuck_tab}")
                                     try:
                                         driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB) # Fallback
                                     except:
                                         pass # Ignore if fallback fails
                                time.sleep(0.2)
                                continue # Force tab if stuck
                            else:
                                 if element_id:
                                     processed_elements_ids_page.add(element_id) # Mark as processed if new ID

                            tag_name = active_element.tag_name.lower()
                            elem_type = active_element.get_attribute('type').lower() if tag_name == 'input' else None
                            question_text = get_associated_label(driver, active_element) or active_element.get_attribute('aria-label') or active_element.get_attribute('placeholder') or active_element.get_attribute('name') or f"Focused (tag:{tag_name})"
                            normalized_q = normalize_question(question_text or "")

                            print(f"\nTab {tab_count_page}: '{question_text}' (Type: {elem_type or tag_name})")

                            # --- Check if focus is on the TARGET Next/Continue button ---
                            is_target_next_button = False
                            if next_button_selector:
                                try:
                                    target_button = None
                                    if next_button_selector.startswith('/'):
                                        target_button = driver.find_element(By.XPATH, next_button_selector)
                                    else:
                                        target_button = driver.find_element(By.CSS_SELECTOR, next_button_selector)

                                    if active_element.id == target_button.id:
                                         print(f"  INFO: Focused on TARGET Next/Continue button. Stopping tab scan.")
                                         is_target_next_button = True
                                         nav_button_focused = active_element # Store it
                                         break # Exit INNER loop
                                except NoSuchElementException:
                                     pass # Target button not found (yet) or selector invalid
                                except Exception as e_check_next:
                                     print(f"    Minor error checking target next button: {e_check_next}")

                            # --- Check if focus is on a generic Submit button (if no target next button) ---
                            is_generic_submit = False
                            if not next_button_selector: # Only check for generic submit if we aren't looking for a specific next
                                submit_texts = ['submit', 'review', 'apply'] # Exclude continue/save here
                                button_text = active_element.text.lower() if active_element.text else ""
                                button_value = active_element.get_attribute('value').lower() if tag_name == 'input' and elem_type in ['submit','button'] else ""
                                is_generic_submit = (tag_name == 'button' and any(s in button_text for s in submit_texts)) or \
                                                    (elem_type == 'submit' and any(s in button_value for s in submit_texts))
                                if is_generic_submit:
                                     print(f"  INFO: Focused on potential SUBMIT button ('{active_element.text or button_value}'). Stopping tab scan.")
                                     break # Exit INNER loop

                            # --- Interaction Logic (Expanded) ---
                            if (tag_name == 'input' and elem_type not in ['checkbox', 'radio', 'file', 'submit', 'button']) or tag_name == 'textarea':
                                interaction_handled = True
                                print("  Handling Standard Input/Textarea.")
                                if normalized_q in answers_db:
                                    answer = answers_db[normalized_q]
                                    print(f"  Stored: '{str(answer)[:50]}...'")
                                    attempt_fill_field(active_element, answer)
                                else:
                                    print(f"  ? Answer not in DB.")
                                    user_answer = input(f"  Enter answer: ")
                                    answers_db[normalized_q]=user_answer
                                    save_answers(ANSWERS_DB_FILE, answers_db)
                                    print(" Saved.")
                                    attempt_fill_field(active_element, user_answer)

                            elif elem_type == 'file':
                                interaction_handled = True
                                print("  Handling File Input.")
                                specific_normalized_q = normalized_q
                                if "resume" in question_text.lower() or "cv" in question_text.lower():
                                    specific_normalized_q += "_resume"
                                elif "cover letter" in question_text.lower():
                                    specific_normalized_q += "_cover_letter"

                                if specific_normalized_q in answers_db:
                                    file_path = answers_db[specific_normalized_q]
                                    print(f"  Stored path: '{file_path}'")
                                    if os.path.exists(file_path):
                                        try:
                                            active_element.send_keys(file_path)
                                            print(" Set path.")
                                        except Exception as e:
                                            print(f" Err sending keys:{e}")
                                    else:
                                        print(f" Warn: Path invalid!")
                                        del answers_db[specific_normalized_q] # Remove invalid entry

                                if specific_normalized_q not in answers_db:
                                    print(f"  ? Path not in DB.")
                                    while True:
                                        user_path = input(f"  Enter path for '{question_text}' (or 'skip'): ").strip('"\' ')
                                        if user_path.lower()=='skip':
                                            print(" Skip.")
                                            break
                                        if os.path.exists(user_path):
                                            answers_db[specific_normalized_q]=user_path
                                            save_answers(ANSWERS_DB_FILE,answers_db)
                                            print(f" Saved path for '{specific_normalized_q}'.")
                                            try:
                                                active_element.send_keys(user_path)
                                                print(" Set path.")
                                            except Exception as e:
                                                print(f" Err sending keys:{e}")
                                            break # Exit while loop after success
                                        else:
                                            print(" ERR: File not found.")

                            elif elem_type == 'checkbox':
                                interaction_handled = True
                                print("  Handling Checkbox.")
                                input_name = active_element.get_attribute('name')
                                group_question = group_question_map.get(input_name)
                                option_label = get_associated_label(driver, active_element) or f"Checkbox val:{active_element.get_attribute('value')}"
                                if group_question:
                                    print(f"  Group:'{group_question}'/Option:'{option_label}'")
                                    if group_question not in processed_group_questions_page:
                                        processed_group_questions_page.add(group_question)
                                        if group_question in answers_db:
                                            print(f"  Stored group answer: '{answers_db[group_question]}'")
                                            print(f"  >>> CHECK/UNCHECK Group Manually <<<")
                                            input(" Enter when done...")
                                        else:
                                            print(f"  ? Group answer not in DB.")
                                            print(f"  >>> CHECK/UNCHECK the correct option(s) manually. <<<")
                                            input(" Enter when done...")
                                            user_answer = input(f" Enter EXACT text of selected option(s): ").strip()
                                            if user_answer:
                                                answers_db[group_question] = user_answer
                                                save_answers(ANSWERS_DB_FILE, answers_db)
                                                print(" Saved group answer.")
                                else: # Standalone checkbox
                                    print(f"  Standalone:'{option_label}'")
                                    if normalized_q in answers_db:
                                        stored_answer = answers_db[normalized_q]
                                        print(f"  Stored: '{stored_answer}'")
                                        is_checked = active_element.is_selected()
                                        should_be = str(stored_answer).lower() in ['true','yes','on']
                                        if is_checked != should_be:
                                            print(f"  State mismatch. Sending SPACE.")
                                            active_element.send_keys(Keys.SPACE)
                                            time.sleep(0.1)
                                        else:
                                            print("  State matches.")
                                    else:
                                        print(f"  ? Standalone answer not in DB.")
                                        is_checked_now = active_element.is_selected()
                                        print(f"  >>> State is: {'CHECKED' if is_checked_now else 'UNCHECKED'}. Check/Uncheck manually if needed. <<<")
                                        input(" Enter when done...")
                                        final_state = active_element.is_selected()
                                        user_answer = "True" if final_state else "False"
                                        answers_db[normalized_q] = user_answer
                                        save_answers(ANSWERS_DB_FILE, answers_db)
                                        print(f" Saved state '{user_answer}'.")

                            elif elem_type == 'radio':
                                interaction_handled = True
                                print("  Handling Radio Button.")
                                input_name = active_element.get_attribute('name')
                                group_question = group_question_map.get(input_name)
                                option_label = get_associated_label(driver, active_element) or f"Radio val:{active_element.get_attribute('value')}"
                                if group_question:
                                    print(f"  Group:'{group_question}'/Option:'{option_label}'")
                                    if group_question not in processed_group_questions_page:
                                        processed_group_questions_page.add(group_question)
                                        if group_question in answers_db:
                                            print(f"  Stored group answer: '{answers_db[group_question]}'")
                                            print(f"  >>> Ensure correct option selected MANUALLY. Focus is on '{option_label}'. <<<")
                                            input(" Enter when done...")
                                        else:
                                            print(f"  ? Group answer not in DB.")
                                            print(f"  >>> Select correct option MANUALLY. Focus is on '{option_label}'. <<<")
                                            input(" Enter when done...")
                                            user_answer = input(f" Enter EXACT text of selected option: ").strip()
                                            if user_answer:
                                                answers_db[group_question] = user_answer
                                                save_answers(ANSWERS_DB_FILE, answers_db)
                                                print(" Saved group answer.")
                                else:
                                    print("  Warn: Radio w/o group. Select manually.")
                                    input(" Enter when done...")

                            elif tag_name == 'select':
                                interaction_handled = True
                                print("  Handling Standard Select.")
                                if normalized_q in answers_db:
                                    answer = answers_db[normalized_q]
                                    print(f"  Stored: '{answer}'")
                                    attempt_fill_field(active_element, answer)
                                else:
                                    print(f"  ? Answer not in DB.")
                                    options = []
                                    try:
                                        s=Select(active_element)
                                        options=[o.text for o in s.options if o.text and not o.is_disabled()]
                                        print(" Options:")
                                        for t in options: # Use multi-line print
                                            print(f" - {t}")
                                    except Exception as e_list_sel:
                                        print(f"    Error listing select options: {e_list_sel}")
                                    user_answer = input(f" Enter EXACT text: ").strip()
                                    if user_answer:
                                        if attempt_fill_field(active_element, user_answer):
                                            answers_db[normalized_q]=user_answer
                                            save_answers(ANSWERS_DB_FILE,answers_db)
                                            print(" Saved.")

                            elif (tag_name == 'input' and active_element.get_attribute('role') == 'combobox') or \
                                 (tag_name == 'div' and ('select' in active_element.get_attribute('class').lower() or 'dropdown' in active_element.get_attribute('class').lower())) or \
                                 (active_element.get_attribute('role') in ['listbox', 'combobox']):
                                 interaction_handled = True
                                 print("  Handling Custom Dropdown (Manual Assist).")
                                 if normalized_q in answers_db:
                                     stored_answer = answers_db[normalized_q]
                                     print(f"  Stored: '{stored_answer}'.")
                                     print(f"  >>> Select '{stored_answer}' MANUALLY <<<")
                                     print("    (Attempting ENTER/SPACE...)")
                                     try:
                                         active_element.send_keys(Keys.ENTER)
                                         time.sleep(0.2) # Try Enter
                                     except:
                                         try:
                                             active_element.send_keys(Keys.SPACE)
                                             time.sleep(0.2) # Try Space
                                         except Exception as e_key:
                                             print(f"    (Sending key failed: {e_key})")
                                     input("      Press Enter AFTER selection...")
                                 else:
                                     print(f"  ? Answer not in DB.")
                                     print("    (Attempting ENTER/SPACE...)")
                                     try:
                                         active_element.send_keys(Keys.ENTER)
                                         time.sleep(0.2) # Try Enter
                                     except:
                                         try:
                                             active_element.send_keys(Keys.SPACE)
                                             time.sleep(0.2) # Try Space
                                         except Exception as e_key:
                                             print(f"    (Sending key failed: {e_key})")

                                     print(f"  >>> Select MANUALLY in browser NOW <<<")
                                     input("      Press Enter AFTER selection...")
                                     # --- Read back attempt (Multi-line expanded) ---
                                     retrieved_value = None
                                     try:
                                         time.sleep(0.75)
                                         # Strategy 1
                                         if active_element.tag_name == 'input':
                                             value_attr = active_element.get_attribute('value')
                                             if value_attr and value_attr.strip():
                                                 retrieved_value = value_attr.strip()
                                                 print(f"    Read from input value: '{retrieved_value}'")
                                         # Strategy 2
                                         if not retrieved_value:
                                             try:
                                                 main_text = active_element.text
                                                 placeholder_text = active_element.get_attribute('placeholder')
                                                 if main_text and main_text.strip() and main_text != placeholder_text:
                                                     retrieved_value = main_text.strip()
                                                     print(f"    Read from element text: '{retrieved_value}'")
                                             except Exception as e_text_read:
                                                 print(f"      Minor error reading main text: {e_text_read}")
                                         # Strategy 3
                                         if not retrieved_value:
                                             child_selectors = ["div[class*='singleValue']", "div[class*='single-value']", "div[class*='Select-value'] span", "div[class*='value-container'] > div:not([class*='placeholder'])", "span[class*='selection-item']", ".select__single-value"]
                                             print(f"    Looking for selected value display using selectors: {child_selectors}")
                                             for sel in child_selectors:
                                                 try:
                                                     selected_display = active_element.find_element(By.CSS_SELECTOR, sel)
                                                     value_text = selected_display.text
                                                     if value_text and value_text.strip():
                                                         retrieved_value = value_text.strip()
                                                         print(f"    Read from child '{sel}': '{retrieved_value}'")
                                                         break # Found it
                                                 except NoSuchElementException:
                                                     continue
                                                 except Exception as e_find_child:
                                                      print(f"    Minor error checking child selector '{sel}': {e_find_child}")
                                                      continue
                                         # Strategy 4
                                         if not retrieved_value and active_element.text:
                                             try:
                                                 placeholder_text = active_element.get_attribute('placeholder')
                                                 current_text = active_element.text.strip()
                                                 if current_text and current_text != placeholder_text:
                                                    retrieved_value = current_text
                                                    print(f"    Read from element text (Fallback): '{retrieved_value}'")
                                             except Exception as e_fallback_text:
                                                 print(f"      Minor error reading fallback text: {e_fallback_text}")
                                         # Final Clean up
                                         if retrieved_value:
                                             if "\n" in retrieved_value:
                                                 retrieved_value = retrieved_value.split('\n')[0].strip()
                                     except Exception as e_read:
                                          print(f"    Error reading value: {e_read}")
                                     # --- Save or fallback ---
                                     if retrieved_value:
                                         print(f"    Read value: '{retrieved_value}'")
                                         answers_db[normalized_q] = retrieved_value
                                         save_answers(ANSWERS_DB_FILE, answers_db)
                                         print("    Saved.")
                                     else:
                                         print("    Could not read value automatically.")
                                         user_answer = input(f"      Please type EXACT text you selected: ").strip()
                                         if user_answer:
                                             answers_db[normalized_q] = user_answer
                                             save_answers(ANSWERS_DB_FILE, answers_db)
                                             print("    Saved manual.")

                            elif tag_name in ['button', 'a']:
                                print(f"  Skipping button/link: '{active_element.text[:50]}...'")
                                interaction_handled = False
                            else:
                                print(f"  Skipping unknown element (Tag: {tag_name}, Type: {elem_type})")
                                interaction_handled = False

                            # Update skip counter and Tab to next
                            if interaction_handled:
                                consecutive_skips_page = 0
                            else:
                                consecutive_skips_page += 1

                            if consecutive_skips_page >= max_consecutive_skips_page:
                                print(f"INFO: Skipped {max_consecutive_skips_page} consecutive elements.")
                                break # Exit INNER loop

                            print("  Sending TAB...")
                            try:
                                 active_element.send_keys(Keys.TAB)
                            except Exception as e_tab_send:
                                print(f"      Error sending tab from active element: {e_tab_send}")
                                # Fallback tab from body
                                try:
                                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                                except Exception as e_fb_tab:
                                    print(f"      Fallback tab also failed: {e_fb_tab}")
                            time.sleep(0.25) # Slightly shorter tab pause

                        except StaleElementReferenceException:
                            print(f"Tab {tab_count_page}: Stale element. Recovery tab...")
                            try:
                                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                            except Exception as e_recover_tab:
                                 print(f"    Recovery tab failed: {e_recover_tab}")
                            time.sleep(0.2)
                            continue # Continue to next iteration of while loop
                        except Exception as e_main_tab_loop:
                            print(f"--- ERROR in tab loop {tab_count_page} for '{question_text}': {e_main_tab_loop} ---")
                            print(traceback.format_exc()) # Print detailed error
                            print("--- Trying TAB past error ---")
                            try:
                                active_element.send_keys(Keys.TAB)
                            except:
                                try:
                                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                                except:
                                    pass # Ignore if even fallback fails
                            time.sleep(0.2)
                            continue # Continue loop
                    # --- End of INNER WHILE loop (tab_count_page) ---
                    if tab_count_page >= max_tabs_page:
                        print(f"WARNING: Reached max tabs ({max_tabs_page}) for Page {page_count}.")

                    # --- Click Next Button If Applicable ---
                    if nav_button_focused: # If tabbing stopped because focus landed on the target next button
                         print(f"\nFinished tabbing Page {page_count}. Attempting to click focused Next/Continue button...")
                         nav_locator = None
                         try:
                             # Try to create a locator based on text/attributes of the focused button
                             nav_text = nav_button_focused.text
                             if nav_text:
                                 nav_locator = (By.XPATH, f"//button[normalize-space()='{nav_text}']")
                         except: pass # Ignore errors getting locator info
                         if attempt_action_click(driver, nav_button_focused, nav_locator):
                             print("Clicked page navigation button successfully.")
                             action_taken = True
                         else:
                             print("ERROR: Failed to click focused page navigation button. Manual action needed.")
                             input("Please click the Next/Continue button manually and press Enter...")
                             action_taken = True # Assume user did it
                    elif next_button_selector: # If flow defines a next button, but focus didn't land on it, try finding explicitly
                         print(f"\nFinished tabbing Page {page_count}. Explicitly searching for Next button: {next_button_selector}")
                         try:
                             locator = (By.XPATH, next_button_selector) if next_button_selector.startswith('/') else (By.CSS_SELECTOR, next_button_selector)
                             nav_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(locator))
                             print(f"Found explicit Next button: '{nav_button.text[:30]}...'")
                             if attempt_action_click(driver, nav_button, locator):
                                 print("Clicked explicit page navigation button successfully.")
                                 action_taken = True
                             else:
                                 print("ERROR: Failed to click explicit page navigation button. Manual action needed.")
                                 input("Please click the Next/Continue button manually and press Enter...")
                                 action_taken = True
                         except TimeoutException:
                             print(f"ERROR: Explicit Next button not found/clickable using stored selector: {next_button_selector}")
                             input("Please click Next/Continue manually and press Enter...")
                             action_taken = True
                         except Exception as e_next_ex:
                             print(f"Error clicking explicit next button: {e_next_ex}")
                             input("Please click Next/Continue manually and press Enter...")
                             action_taken = True
                    else:
                         # No next button defined for this form page step
                         print(f"\nFinished tabbing Page {page_count}. No 'Next' button defined for this step.")
                         action_taken = False # Signal that we don't automatically move to next page

                elif step_type == 'FINAL_SUBMIT':
                    print("Reached FINAL_SUBMIT step. Stopping automation for this job.")
                    action_taken = False # Stop processing
                    break # Exit the step processing loop

                else:
                    print(f"ERROR: Unknown step type '{step_type}' encountered in flow.")
                    break # Stop processing if flow is corrupted

                # --- Move to next step or break ---
                if action_taken:
                    step_index += 1
                    print("-" * 20) # Separator
                    time.sleep(3.0) # Wait for next page/state to load
                else:
                    # If no action was taken (e.g., form page with no next button, or FINAL_SUBMIT)
                    break # Exit the step processing loop

            # --- End of Step Processing Loop (while step_index < max_steps) ---
            if step_index >= max_steps:
                 print(f"WARNING: Reached maximum step limit ({max_steps}).")

            # --- Final Prompt (Only reached if loop finishes/breaks without error/skip) ---
            print("\n>>> FINAL REVIEW & SUBMIT <<<")
            print("Automated filling process complete for defined steps."); print("1. REVIEW the application."); print("2. Fill/correct any remaining fields.")
            print("3. Find and click the FINAL 'Submit Application' button YOURSELF.")
            input("4. Press Enter AFTER submitting...")

        # --- Error Handling for Main Job Loop ---
        except Exception as e_main_job_loop:
            print(f"\n--- ERROR processing job {job['title']}: {e_main_job_loop} ---")
            if "User skipped application scan" in str(e_main_job_loop):
                pass # Expected skip
            else:
                print("Manual review recommended.");
                print(traceback.format_exc()) # Print detailed error traceback
                input("Press Enter to acknowledge and continue...")

        # --- Cleanup for Each Job ---
        finally:
            if driver:
                try:
                    print("Closing browser for this job...")
                    driver.quit()
                    driver = None
                except Exception as e_quit:
                    print(f"Error trying to quit WebDriver: {e_quit}")
            # Save both databases after each job attempt
            save_answers(ANSWERS_DB_FILE, answers_db)
            save_company_flows(COMPANY_FLOWS_FILE, company_flows)

    # --- End of OUTER JOB LOOP ---
    print("\n--- All marked jobs processed ---")
    print(f"Final answers database saved to {ANSWERS_DB_FILE}")
    print(f"Company flows saved to {COMPANY_FLOWS_FILE}")