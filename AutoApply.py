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

# --- Main Script ---
if __name__ == "__main__":
    latest_csv = find_latest_csv(SCRAPER_OUTPUT_FOLDER, CSV_FILENAME_PATTERN)
    if not latest_csv: exit()

    answers_db = load_answers(ANSWERS_DB_FILE)
    jobs_to_apply = []

    # 1. Read the CSV and find marked jobs
    try:
        with open(latest_csv, 'r', newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            if APPLY_MARKER_COLUMN not in reader.fieldnames: raise ValueError(f"Column '{APPLY_MARKER_COLUMN}' not found.")
            for i, row in enumerate(reader):
                if row.get(APPLY_MARKER_COLUMN, '').strip().lower() == APPLY_MARKER_VALUE.lower():
                    link = row.get('Link', '').strip()
                    if link and link != 'N/A':
                        jobs_to_apply.append({
                            'row_num': i + 2, 'title': row.get('Job Title', 'N/A'),
                            'company': row.get('Company', 'N/A'), 'link': link })
                    else: print(f"Skipping Row {i + 2} ({row.get('Job Title', 'N/A')}): Missing/Invalid Link")
    except FileNotFoundError: print(f"ERROR: CSV file not found: {latest_csv}"); exit()
    except ValueError as ve: print(f"ERROR: {ve}"); exit()
    except Exception as e: print(f"Error reading CSV file {latest_csv}: {e}"); exit()

    if not jobs_to_apply: print(f"No jobs marked '{APPLY_MARKER_VALUE}' found in {latest_csv}."); exit()
    print(f"\nFound {len(jobs_to_apply)} jobs marked for application help.")

    driver = None
    for job_index, job in enumerate(jobs_to_apply): # <<< OUTER JOB LOOP START >>>
        print(f"\n--- Processing Job {job_index + 1}/{len(jobs_to_apply)} (Row {job['row_num']}): {job['title']} at {job['company']} ---")
        print(f"Link: {job['link']}")

        # <<< START OF TRY BLOCK FOR A SINGLE JOB >>>
        try:
            # --- Browser Setup ---
            options = Options(); options.use_chromium = True; options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage"); options.add_argument("--start-maximized")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            driver = webdriver.Edge(options=options)
            wait = WebDriverWait(driver, WAIT_TIMEOUT) # Main wait

            # --- 1. Navigate ---
            print(f"Navigating to: {job['link']}")
            driver.get(job['link']); time.sleep(1.5)

            # --- 2. Dismiss Initial Modal ---
            print("Checking for initial 'Sign in' modal...")
            try:
                WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'section[aria-modal="true"]')))
                print("Modal container detected. Attempting dismissal...")
                dismiss_locator = (By.CSS_SELECTOR, 'button.contextual-sign-in-modal__modal-dismiss[aria-label="Dismiss"]')
                try:
                    modal_dismiss_button = WebDriverWait(driver, 7).until(EC.presence_of_element_located(dismiss_locator))
                    print("  Dismiss button found.")
                    try: driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modal_dismiss_button); time.sleep(0.2)
                    except: pass # Ignore scroll errors
                    if attempt_action_click(driver, modal_dismiss_button, dismiss_locator): print("  Dismissed successfully."); time.sleep(1.5)
                    else: print("  Dismiss click failed. Proceeding anyway.")
                except TimeoutException: print("  Warning: Dismiss button not found.")
                except Exception as e_dismiss: print(f"  Error dismissing modal: {e_dismiss}")
            except TimeoutException: print("Initial modal not detected.")
            except Exception as e_modal_outer: print(f"Error checking for initial modal: {e_modal_outer}")

            # --- 3. Click First Apply Button ---
            print("\nSearching for FIRST 'Apply' button...")
            first_apply_clicked = False
            possible_first_apply_selectors = ['button.top-card-layout__cta--primary.btn-primary', 'button[data-tracking-control-name="public_jobs_apply-link-offsite_sign-up-modal"]', "//button[normalize-space(.)='Apply' and not(@aria-label='Dismiss')]", 'button[data-modal="sign-up-modal-outlet"]']
            for selector in possible_first_apply_selectors:
                try:
                    print(f"Trying selector: {selector}")
                    locator = (By.XPATH, selector) if selector.startswith('/') else (By.CSS_SELECTOR, selector)
                    first_apply_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(locator))
                    print("Found FIRST Apply button.")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_apply_button); time.sleep(0.3)
                    first_apply_button.click() # Use standard click
                    print("Clicked FIRST Apply button."); first_apply_clicked = True; break
                except TimeoutException: print(f"Selector '{selector}' timed out."); continue
                except Exception as e_click: print(f"Error clicking FIRST Apply button: {e_click}"); continue
            if not first_apply_clicked: raise Exception("Could not find/click FIRST Apply button.")

            # --- 3b. Handle Secondary Modal / Navigate ---
            print("\nChecking for secondary modal / direct link...")
            company_link_locator = (By.CSS_SELECTOR, 'a[data-tracking-control-name="public_jobs_apply-link-offsite_sign-up-modal-sign-up-later"]')
            secondary_modal_container = (By.CSS_SELECTOR, 'div.sign-up-modal__direct-apply-on-company-site')
            try:
                WebDriverWait(driver, 4).until(EC.presence_of_element_located(secondary_modal_container))
                print("Secondary modal detected. Extracting company link...")
                try:
                    link_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located(company_link_locator))
                    company_href = link_element.get_attribute('href')
                    if company_href: print(f"  Extracted href: {company_href}"); driver.get(company_href); print("  Navigated directly."); time.sleep(2.5)
                    else: print("  Warning: href attribute empty.")
                except TimeoutException: print("  Warning: Company link not found.")
                except Exception as e_href: print(f"  Error getting/navigating href: {e_href}")
            except TimeoutException: print("Secondary modal not detected. Assuming direct redirect."); time.sleep(1.5)

            # --- 4. Wait for User readiness on Application Page ---
            print("\n>>> ACTION REQUIRED <<<"); print("Confirm page loaded and complete LOGIN/initial steps if needed.")
            try: print(f"Current URL: {driver.current_url}")
            except: print("Could not get current URL.")
            while True:
                user_ready = input("Type 'scan' to begin filling fields, or 'skip' for next job: ").strip().lower()
                if user_ready == 'scan': break
                elif user_ready == 'skip': raise Exception("User skipped application scan.")
                else: print("Please type 'scan' or 'skip'.")

            print("\nScanning page for form fields (Single Pass)..."); time.sleep(0.5)

# --- 5. Form Filling Logic (Tab-Based Navigation) ---
            processed_elements_ids = set() # Track processed element IDs to avoid loops/reprocessing
            max_tabs = 250  # Safety limit to prevent infinite loops
            tab_count = 0
            consecutive_skips = 0
            max_consecutive_skips = 15 # If we skip too many unknown elements in a row, assume we're done or stuck

            print("\nStarting Tab-based field processing...")
            # Initial tab to move focus into the form (usually needed)
            try:
                print("Sending initial TAB to enter form...")
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                time.sleep(0.5)
            except Exception as e_initial_tab:
                 print(f"Warning: Error sending initial tab: {e_initial_tab}")

            processed_group_questions = set() # Keep this set for the main loop
            group_question_map = {} # Initialize the map HERE
            print("Running preliminary scan to identify checkbox/radio groups...")
            try:
                # Find all input elements once for group scanning
                all_inputs = driver.find_elements(By.TAG_NAME, 'input')
                print(f"Found {len(all_inputs)} inputs for group scan.")
                for element in all_inputs:
                    # Only process potentially visible elements for group ID
                    if not element.is_displayed(): continue
                    try:
                        elem_type = element.get_attribute('type').lower() if element.tag_name == 'input' else None
                        if elem_type in ['checkbox', 'radio']:
                            input_name = element.get_attribute('name')
                            if not input_name: continue # Need name for grouping

                            # Use the helper function to find the label/question
                            group_question = get_associated_label(driver, element)
                            # Add fallback to find legend if label fails
                            if not group_question:
                                try:
                                     fieldset = element.find_element(By.XPATH, './ancestor::fieldset[1]')
                                     legend = fieldset.find_element(By.TAG_NAME, 'legend')
                                     group_question = legend.text.strip()
                                except: pass # Ignore if no fieldset/legend

                            if group_question and input_name not in group_question_map:
                                normalized_group_q = normalize_question(group_question)
                                group_question_map[input_name] = normalized_group_q
                                print(f"  Identified Group: '{normalized_group_q}' (Input Name: {input_name})")

                    except StaleElementReferenceException:
                        print("  Stale element during group ID scan, might miss some groups.")
                        continue # Skip this element
                    except Exception as e_group_id:
                        print(f"  Minor error identifying group for an element: {e_group_id}")
                print("Finished preliminary group scan.")
            except Exception as e_pass1:
                print(f"--- ERROR during preliminary group scan: {e_pass1} ---")
                group_question_map = {} # Ensure it's an empty dict if scan fails

            # --- Now start the main tabbing loop ---
            processed_elements_ids = set()
            max_tabs = 250
            tab_count = 0
            consecutive_skips = 0
            max_consecutive_skips = 15

            print("\nStarting Tab-based field processing...")
            # (The initial TAB send can remain here or be removed if focus starts correctly)
            try:
                print("Sending initial TAB to focus form...")
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                time.sleep(0.5)
            except Exception as e_initial_tab:
                 print(f"Warning: Error sending initial tab: {e_initial_tab}")


            while tab_count < max_tabs:
                tab_count += 1
                active_element = None
                element_processed_this_cycle = False # Flag to reset consecutive skips if we process something

                try:
                    # Get the currently focused element using JavaScript
                    active_element = driver.execute_script("return document.activeElement;")
                    if active_element is None:
                        print(f"Tab {tab_count}: No active element found. Tabbing again.")
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB) # Send tab from body
                        time.sleep(0.3)
                        continue

                    element_id = active_element.get_attribute('id')
                    element_outer_html_snippet = active_element.get_attribute('outerHTML')[:80] # For logging

                    # Prevent reprocessing the exact same element immediately if focus gets stuck
                    if element_id and element_id in processed_elements_ids:
                         print(f"Tab {tab_count}: Focus seems stuck on already processed element ID: {element_id}. Tabbing again.")
                         active_element.send_keys(Keys.TAB)
                         time.sleep(0.3)
                         continue

                    tag_name = active_element.tag_name.lower()
                    elem_type = active_element.get_attribute('type').lower() if tag_name == 'input' else None

                    # --- Identify the Question/Label for the focused element ---
                    question_text = get_associated_label(driver, active_element)
                    if not question_text: # Fallbacks if no label found
                         question_text = active_element.get_attribute('aria-label') or \
                                         active_element.get_attribute('placeholder') or \
                                         active_element.get_attribute('name') or \
                                         f"Focused Element (tag:{tag_name}, type:{elem_type}, id:{element_id})"
                    normalized_q = normalize_question(question_text or "")

                    print(f"\nTab {tab_count}: Focused on -> '{question_text}' (Type: {elem_type or tag_name}, HTML: {element_outer_html_snippet}...)")

                    # --- Check if it's a Submit/Next button ---
                    submit_texts = ['submit', 'review', 'continue', 'next', 'save']
                    button_text = active_element.text.lower() if active_element.text else ""
                    button_value = active_element.get_attribute('value').lower() if tag_name == 'input' and elem_type in ['submit','button'] else ""
                    is_submit_button = (tag_name == 'button' and any(s in button_text for s in submit_texts)) or \
                                       (elem_type == 'submit') or \
                                       (elem_type in ['button'] and any(s in button_value for s in submit_texts))

                    if is_submit_button:
                         print(f"INFO: Focused on a potential Submit/Next button ('{active_element.text or button_value}'). Stopping automatic tabbing.")
                         break # Exit the while loop, proceed to final prompt

                    # --- Interaction Logic based on Element Type ---
                    interaction_handled = False # Flag if we did something with this element

                    # --- Standard Text Inputs / Textarea ---
                    if (tag_name == 'input' and elem_type not in ['checkbox', 'radio', 'file', 'submit', 'button', 'reset', 'image', 'hidden']) or \
                         tag_name == 'textarea':
                        print("  Handling Standard Input/Textarea.")
                        interaction_handled = True
                        if normalized_q in answers_db:
                            answer = answers_db[normalized_q]; print(f"  Stored: '{str(answer)[:50]}...'")
                            try:
                                 # Clear and fill (attempt_fill_field handles this)
                                 if not attempt_fill_field(active_element, answer): print("  Manual input might be needed.")
                            except Exception as e_fill: print(f"    Error filling field: {e_fill}")
                        else:
                             print(f"  ? Answer for '{question_text}' not in DB.")
                             user_answer = input(f"  Enter answer for '{question_text}': ")
                             answers_db[normalized_q] = user_answer; save_answers(ANSWERS_DB_FILE, answers_db); print("    Saved.")
                             try:
                                 if not attempt_fill_field(active_element, user_answer): print("  Manual input might be needed after saving.")
                             except Exception as e_fill_new: print(f"    Error filling field after saving: {e_fill_new}")

                    # --- File Inputs ---
                    elif elem_type == 'file':
                        print("  Handling File Input.")
                        interaction_handled = True
                        # Use specific key logic
                        specific_normalized_q = normalized_q
                        if "resume" in question_text.lower() or "cv" in question_text.lower(): specific_normalized_q += "_resume"
                        elif "cover letter" in question_text.lower(): specific_normalized_q += "_cover_letter"

                        if specific_normalized_q in answers_db:
                            file_path = answers_db[specific_normalized_q]; print(f"  Stored path: '{file_path}'")
                            if os.path.exists(file_path):
                                try: active_element.send_keys(file_path); print("    Set file path.")
                                except Exception as e_sk: print(f"    Error sending keys: {e_sk}. Manual upload needed.")
                            else: print(f"  Warning: Stored path invalid!"); del answers_db[specific_normalized_q]
                        if specific_normalized_q not in answers_db:
                            print(f"  ? File path for '{question_text}' not found in DB.")
                            while True:
                                user_path = input(f"  Enter FULL path for '{question_text}' (or 'skip'): ").strip('"\' ')
                                if user_path.lower() == 'skip': print("    Skipping."); break
                                if os.path.exists(user_path):
                                    answers_db[specific_normalized_q] = user_path; save_answers(ANSWERS_DB_FILE, answers_db); print(f"    Saved path for key '{specific_normalized_q}'.")
                                    try: active_element.send_keys(user_path); print("    Set file path.")
                                    except Exception as e_sk_new: print(f"    Error sending keys: {e_sk_new}. Manual upload needed.")
                                    break
                                else: print("  ERROR: File not found. Try again or 'skip'.")

                    # --- Checkboxes --- (Simplified: Prompt user to interact)
                    elif elem_type == 'checkbox':
                        print("  Handling Checkbox.")
                        interaction_handled = True
                        input_name = active_element.get_attribute('name')
                        group_question = group_question_map.get(input_name) # Get normalized group question if identified
                        option_label = get_associated_label(driver, active_element) or f"Checkbox value: {active_element.get_attribute('value')}"

                        if group_question:
                            print(f"  Belongs to group: '{group_question}'")
                            # Process group only once
                            if group_question not in processed_group_questions:
                                processed_group_questions.add(group_question)
                                if group_question in answers_db:
                                    stored_answer = answers_db[group_question]
                                    print(f"  Stored answer for group is: '{stored_answer}'")
                                    print(f"  >>> Focus is on option: '{option_label}'. Please CHECK/UNCHECK manually to match stored answer. <<<")
                                    input("      Press Enter when done...")
                                else:
                                    print(f"  ? Answer for group '{group_question}' not in DB.")
                                    # List available options for context
                                    try: group_elements = driver.find_elements(By.CSS_SELECTOR, f'input[name="{input_name}"]'); print("    Group Options:"); [print(f"      - {get_associated_label(driver, o) or o.get_attribute('value')}") for o in group_elements]
                                    except: pass
                                    print(f"  >>> Focus is on option: '{option_label}'. Please CHECK/UNCHECK the correct option(s) manually. <<<")
                                    input("      Press Enter when done...")
                                    user_answer = input(f"      Enter the EXACT text of the option(s) you selected (comma-separated if multiple): ").strip()
                                    if user_answer: answers_db[group_question] = user_answer; save_answers(ANSWERS_DB_FILE, answers_db); print("    Saved group answer.")
                            # else: Group already handled, just tab past this specific checkbox
                        else:
                             # Handle standalone checkbox
                             print(f"  Handling standalone checkbox: '{option_label}'")
                             if normalized_q in answers_db:
                                 stored_answer = answers_db[normalized_q] # Should be 'True'/'False' or similar
                                 print(f"  Stored answer: '{stored_answer}'")
                                 is_checked = active_element.is_selected()
                                 should_be_checked = str(stored_answer).lower() in ['true', 'yes', 'checked', 'on']
                                 if is_checked != should_be_checked:
                                     print(f"  State mismatch (Should be {should_be_checked}, is {is_checked}). Sending SPACE key.")
                                     active_element.send_keys(Keys.SPACE) # Space usually toggles checkboxes
                                     time.sleep(0.2)
                                 else: print("  Checkbox state matches stored answer.")
                             else:
                                 print(f"  ? Answer for '{option_label}' not in DB.")
                                 is_checked_now = active_element.is_selected()
                                 print(f"  >>> Current state is: {'CHECKED' if is_checked_now else 'UNCHECKED'}. Check/Uncheck manually if needed. <<<")
                                 input("      Press Enter when done...")
                                 final_state = active_element.is_selected()
                                 user_answer = "True" if final_state else "False" # Save boolean state
                                 answers_db[normalized_q] = user_answer
                                 save_answers(ANSWERS_DB_FILE, answers_db)
                                 print(f"    Saved state '{user_answer}' for '{normalized_q}'.")

                    # --- Radio Buttons --- (Simplified: Prompt user to interact)
                    elif elem_type == 'radio':
                         print("  Handling Radio Button.")
                         interaction_handled = True
                         input_name = active_element.get_attribute('name')
                         group_question = group_question_map.get(input_name)
                         option_label = get_associated_label(driver, active_element) or f"Radio value: {active_element.get_attribute('value')}"

                         if group_question:
                             print(f"  Belongs to group: '{group_question}'")
                             if group_question not in processed_group_questions:
                                 processed_group_questions.add(group_question)
                                 if group_question in answers_db:
                                     stored_answer = answers_db[group_question]
                                     print(f"  Stored answer for group is: '{stored_answer}'")
                                     print(f"  >>> Focus is on option: '{option_label}'. Please ensure the correct option for '{stored_answer}' is selected manually (using arrows/space). <<<")
                                     input("      Press Enter when done...")
                                 else:
                                     print(f"  ? Answer for group '{group_question}' not in DB.")
                                     # List options
                                     try: group_elements = driver.find_elements(By.CSS_SELECTOR, f'input[name="{input_name}"]'); print("    Group Options:"); [print(f"      - {get_associated_label(driver, o) or o.get_attribute('value')}") for o in group_elements]
                                     except: pass
                                     print(f"  >>> Focus is on option: '{option_label}'. Please select the correct radio button manually. <<<")
                                     input("      Press Enter when done...")
                                     user_answer = input(f"      Enter the EXACT text of the option you selected: ").strip()
                                     if user_answer: answers_db[group_question] = user_answer; save_answers(ANSWERS_DB_FILE, answers_db); print("    Saved group answer.")
                             # else: Group processed, tab past
                         else: print("  Warning: Radio button found without identified group. Manual interaction needed.")

                    # --- Standard Select Dropdowns ---
                    elif tag_name == 'select':
                        print("  Handling Standard Select.")
                        interaction_handled = True
                        # (Standard select logic using attempt_fill_field - kept from previous version)
                        if normalized_q in answers_db:
                            answer = answers_db[normalized_q]; print(f"  Stored: '{answer}'")
                            if not attempt_fill_field(active_element, answer): print("  Manual selection might be needed.")
                        else:
                            print(f"  ? Answer for '{question_text}' not in DB.")
                            options = []; # (List options logic...)
                            try: select_obj = Select(active_element); options = [o.text for o in select_obj.options if o.text and not o.is_disabled()]; print("    Options:"); [print(f"      - {t}") for t in options]
                            except: pass
                            user_answer = input(f"  Enter EXACT text for '{question_text}': ").strip()
                            if user_answer:
                                if options and user_answer not in options: print(f"  Warning: Input '{user_answer}' not in options list.")
                                if attempt_fill_field(active_element, user_answer): answers_db[normalized_q] = user_answer; save_answers(ANSWERS_DB_FILE, answers_db); print("    Saved.")
                                else: print("  Warning: Could not select.")

                    # --- Custom Dropdowns (Prompt User + Keyboard Assist Attempt) ---
                    elif (tag_name == 'input' and active_element.get_attribute('role') == 'combobox') or \
                         (tag_name == 'div' and ('select' in active_element.get_attribute('class').lower() or 'dropdown' in active_element.get_attribute('class').lower())) or \
                         (active_element.get_attribute('role') in ['listbox', 'combobox']): # Broader check
                        print("  Handling Custom Dropdown (Keyboard Assist/Manual).")
                        interaction_handled = True
                        if normalized_q in answers_db:
                            stored_answer = answers_db[normalized_q]
                            print(f"  Stored Answer: '{stored_answer}'.")
                            print(f"  >>> Focus is on '{question_text}'. Please select '{stored_answer}' using ARROW KEYS and ENTER/SPACE if possible, or mouse. <<<")
                            # Attempt to send ENTER just to open it, user does the rest
                            print("    (Attempting ENTER to open dropdown...)")
                            try: active_element.send_keys(Keys.ENTER); time.sleep(0.3)
                            except: print("    (Sending ENTER failed, dropdown might already be open or needs different interaction)")
                            input("      Press Enter here AFTER you have selected the correct option...")
                            # We assume user selected correctly, no readback for now
                        else:
                            print(f"  ? Answer for '{question_text}' not in DB.")
                            print("    (Attempting ENTER to open dropdown...)")
                            try: active_element.send_keys(Keys.ENTER); time.sleep(0.3)
                            except: print("    (Sending ENTER failed, dropdown might already be open or needs different interaction)")
                            print(f"  >>> Focus is on '{question_text}'. Please select the desired option manually in the browser NOW. <<<")
                            input("      Press Enter here AFTER you have selected the option...")
                            # Read back attempt
                            # --- Try reading selected value ---
                            retrieved_value = None
                            try:
                                # Give the UI a moment to update after user selection and Enter press
                                time.sleep(0.75) # Slightly longer pause

                                # Strategy 1: Input value attribute
                                if active_element.tag_name == 'input':
                                    value_attr = active_element.get_attribute('value')
                                    if value_attr and value_attr.strip(): # Check if value exists and isn't just whitespace
                                        retrieved_value = value_attr.strip()
                                        print(f"    Read from input value: '{retrieved_value}'")

                                # Strategy 2: Main element text (if not input or value was empty)
                                if not retrieved_value:
                                    try:
                                        main_text = active_element.text
                                        placeholder_text = active_element.get_attribute('placeholder')
                                        # Only use main_text if it's not empty and differs from placeholder
                                        if main_text and main_text.strip() and main_text != placeholder_text:
                                            retrieved_value = main_text.strip()
                                            print(f"    Read from element text: '{retrieved_value}'")
                                    except Exception as e_text_read:
                                        print(f"      Minor error reading main text: {e_text_read}")

                                # Strategy 3: Specific child element
                                if not retrieved_value:
                                    child_selectors = [
                                        "div[class*='singleValue']",      # Common pattern
                                        "div[class*='single-value']",     # Another common pattern
                                        "div[class*='Select-value'] span", # Older pattern
                                        "div[class*='value-container'] > div:not([class*='placeholder'])", # Avoid placeholder div
                                        "span[class*='selection-item']",    # Another possible pattern
                                        ".select__single-value"           # Another common class
                                    ]
                                    print(f"    Looking for selected value display using selectors: {child_selectors}")
                                    for sel in child_selectors:
                                        try:
                                            # Search *within* the main dropdown element
                                            selected_display = active_element.find_element(By.CSS_SELECTOR, sel)
                                            value_text = selected_display.text
                                            if value_text and value_text.strip(): # Ensure text is not empty
                                                 retrieved_value = value_text.strip()
                                                 print(f"    Read from child '{sel}': '{retrieved_value}'")
                                                 break # Found it, stop searching selectors
                                        except NoSuchElementException:
                                            continue # Try next selector if this one didn't find anything
                                        except Exception as e_find_child:
                                             print(f"    Minor error checking child selector '{sel}': {e_find_child}")
                                             continue # Try next selector even on other errors

                                # Strategy 4: Fallback - Get text directly if strategies fail but element has text
                                if not retrieved_value and active_element.text:
                                     try:
                                         placeholder_text = active_element.get_attribute('placeholder')
                                         current_text = active_element.text.strip()
                                         if current_text and current_text != placeholder_text:
                                            retrieved_value = current_text
                                            print(f"    Read from element text (Fallback): '{retrieved_value}'")
                                     except Exception as e_fallback_text:
                                         print(f"      Minor error reading fallback text: {e_fallback_text}")


                                # Final Clean up the retrieved value
                                if retrieved_value:
                                    # Remove potential trailing interactive elements (like clear buttons often added via newline)
                                    if "\n" in retrieved_value:
                                        retrieved_value = retrieved_value.split('\n')[0].strip()

                            except Exception as e_read:
                                 print(f"    Error occurred while trying to automatically read selected value: {e_read}")
                            # Save or fallback
                            if retrieved_value: print(f"    Read value: '{retrieved_value}'"); answers_db[normalized_q] = retrieved_value; save_answers(ANSWERS_DB_FILE, answers_db); print("    Saved.")
                            else: print("    Could not read value automatically."); user_answer = input(f"      Please type EXACT text you selected: ").strip(); answers_db[normalized_q] = user_answer; save_answers(ANSWERS_DB_FILE, answers_db); print("    Saved manually typed answer.")

                    # --- Handle other focusable elements ---
                    elif tag_name in ['button', 'a']:
                         # Usually ignore buttons/links unless identified as Submit/Next earlier
                         if not is_submit_button:
                             print(f"  Skipping button/link: '{active_element.text[:50]}...'")
                         interaction_handled = False # Don't reset skip counter for non-interactive elements
                    else:
                         print(f"  Skipping unknown/non-interactive element (Tag: {tag_name}, Type: {elem_type})")
                         interaction_handled = False # Don't reset skip counter

                    # --- Mark as processed and Tab to next ---
                    if element_id:
                        processed_elements_ids.add(element_id) # Add ID to processed set

                    if interaction_handled:
                        consecutive_skips = 0 # Reset counter if we interacted
                    else:
                        consecutive_skips += 1 # Increment if we skipped

                    if consecutive_skips >= max_consecutive_skips:
                         print(f"INFO: Skipped {max_consecutive_skips} consecutive elements. Assuming end of relevant fields or stuck focus.")
                         break # Exit the while loop

                    print("  Sending TAB...")
                    active_element.send_keys(Keys.TAB)
                    time.sleep(0.3) # Pause after tabbing

                except StaleElementReferenceException:
                    print(f"Tab {tab_count}: Stale element reference encountered. Trying to recover focus...")
                    try:
                        # Try sending tab from body to potentially move focus forward
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB)
                        time.sleep(0.3)
                    except Exception as e_recover:
                         print(f"  Recovery tab failed: {e_recover}. May be stuck.")
                    continue # Continue to next iteration of while loop
                except Exception as e_main_loop:
                    print(f"--- ERROR in main processing loop (Tab {tab_count}) for element '{question_text}': {e_main_loop} ---")
                    print(traceback.format_exc()) # Print detailed error
                    print("--- Attempting to continue by sending TAB ---")
                    try: active_element.send_keys(Keys.TAB) # Try to tab past the error
                    except: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.TAB) # Fallback tab
                    time.sleep(0.3)
                    continue # Continue loop

            # --- End of WHILE Loop (tab_count < max_tabs) ---
            if tab_count >= max_tabs:
                 print(f"WARNING: Reached maximum tab limit ({max_tabs}). Stopping scan.")

            # --- 6. Final Prompt (Submit Button Check is now integrated above) ---
            print("\n>>> FINAL REVIEW & SUBMIT <<<")
            print("The script has finished tabbing through fields.")
            print("1. Please carefully REVIEW the entire application form in the browser.")
            print("2. Fill in any remaining fields manually.")
            print("3. Find and click the 'Submit', 'Review', or 'Continue' button YOURSELF.")
            input("4. Press Enter here AFTER you have submitted the application...")

        # --- Error Handling for Main Job Loop ---
        except Exception as e_main_job_loop:
            print(f"\n--- An error occurred processing job {job['title']}: {e_main_job_loop} ---")
            if "User skipped application scan" in str(e_main_job_loop): pass # Expected skip
            else: print("Recommend manual review for this job."); print(traceback.format_exc()); input("Press Enter to acknowledge and continue...")

        # --- Cleanup for Each Job ---
        finally:
            if driver:
                try: print("Closing browser window for this job..."); driver.quit(); driver = None
                except Exception as e_quit: print(f"Error trying to quit WebDriver: {e_quit}")
            save_answers(ANSWERS_DB_FILE, answers_db) # Save progress after each job

    # --- End of OUTER JOB LOOP ---

    print("\n--- All marked jobs processed ---")
    print(f"Final answers database saved to {ANSWERS_DB_FILE}")