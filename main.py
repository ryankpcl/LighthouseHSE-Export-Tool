import api
import argparse
import config
import database
from datetime import datetime
import excel
import glob
from jinja2 import Template, Environment
import json
import logging
import os
from pathlib import Path
import pdfkit
import re
import requests
import sys
from time import sleep
from urllib.parse import urljoin

# Import threading modules
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm  # For progress bar (install via pip if not available)

# Load settings file
settings = config.load()

# Configure Jinja2
def from_json(value):
    return json.loads(value)

env = Environment()
env.filters['from_json'] = from_json

# Configure PDF writer
path_wkhtmltopdf = settings['wkhtmltopdf']
pdfkit_config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

# Lists to store skipped items
skipped_processes = []
skipped_downloads = []
skipped_forms = []

# Threading lock for shared resources
lock = threading.Lock()

# Thread-local storage for database connections
thread_local = threading.local()

# Event to signal when API limit is reached
api_limit_reached = threading.Event()

# Function to handle groups data
def sync_groups(cursor, url, cnx):
    global settings
    
    data = api.fetch_data(url, settings)
    if "Result" not in data or "Groups" not in data["Result"]:
        raise ValueError("Invalid response structure for groups")
    groups = data["Result"]["Groups"]
    total_groups = len(groups)

    for i, group in enumerate(groups):
        database.group_insert(cursor, group, cnx)  # Pass cnx for committing transactions
        completion_percentage = ((i + 1) / total_groups) * 100
        sys.stdout.write(f"\r    Groups: {completion_percentage:.2f}%")
        sys.stdout.flush()
    print()  # Move to the next line after completion

# Function to handle processes data
def sync_processes(cursor, url, cnx):
    global settings
    
    data = api.fetch_data(url, settings)
    if "Result" not in data or "Procs" not in data["Result"]:
        raise ValueError("Invalid response structure for processes")
    procs = data["Result"]["Procs"]
    total_procs = len(procs)

    for i, proc in enumerate(procs):
        database.process_insert(cursor, proc, cnx)  # Pass cnx for committing transactions
        completion_percentage = ((i + 1) / total_procs) * 100
        sys.stdout.write(f"\r    Processes: {completion_percentage:.2f}%")
        sys.stdout.flush()
    print()  # Move to the next line after completion
    
# Function to handle forms data
def sync_forms(cursor, url, cnx, proc_id="0"):
    global skipped_processes
    
    # If --sync specific process is called, run this
    if not proc_id == "0":
        processes = database.process_specific(cursor, proc_id)
    else:
    # Fetch all processes
        processes = database.process_list(cursor)
    
    processes_total = len(processes)
    processes_current = 1

    print("    Forms:")
    for x in processes:
        enabled = database.process_status(cursor, x[0])
        
        # Check if process is enabled in SQL.  This feature can be used to temporarily skip syncing big processes.
        if enabled:
            # Fetch forms data for each ProcessID
            forms_data = api.fetch_data(url, {"ProcessID": x[0]})
            
            # Handle potential API errors
            if "Result" in forms_data and "Error" in forms_data["Result"]:
                error_message = forms_data["Result"]["Error"]["Message"]
                if error_message == "Process is archived":
                    print(f"Process {x[1]} is archived. Skipping...")
                    continue
                elif error_message == "User lacks permission to Read forms of the template":
                    print(f"Process {x[1]} lacks permission. Skipping...")
                    skipped_processes.append(x[0])
                    continue
            
            if "Result" not in forms_data or "Forms" not in forms_data["Result"]:
                raise ValueError(f"Invalid response structure for forms for ProcessID {x[0]}")
            
            # Extract forms data
            forms = forms_data["Result"]["Forms"]
            total_forms = len(forms)
            
            if not forms:
                # No forms for this process, report 100% completion
                sys.stdout.write(f"\r      ({processes_current} of {processes_total}) {x[1]}: 100%")
                sys.stdout.flush()
            else:
                # Process each form
                for j, form in enumerate(forms):
                    # Insert form into the database
                    database.form_insert(cursor, x[0], form, cnx)
                    
                    # Calculate completion percentage for the current process
                    form_completion_percentage = ((j + 1) / total_forms) * 100
                    sys.stdout.write(f"\r      ({processes_current} of {processes_total}) {x[1]}: {form_completion_percentage:.2f}%")
                    sys.stdout.flush()
        else:
            sys.stdout.write(f"\r      ({processes_current} of {processes_total}): SKIPPED")
            sys.stdout.flush()
        
        print()  # Move to the next line after form completion
        processes_current += 1  # Increment current process counter

# Configure logging
logging.basicConfig(level=logging.INFO)

def extract_field(data, field_def):
    # Navigate through the path defined in field_def["path"]
    parts = field_def.get("path", "").split('.')
    for part in parts:
        if isinstance(data, dict) and part in data:
            data = data[part]
        else:
            logging.warning(f"Path '{'.'.join(parts)}' not found in data.")
            return None  # Handle missing paths gracefully

    # Determine the key to match on ('Field' or 'Uid')
    match_on = field_def.get('match_on', 'Field')

    # If there's a specific field to extract, handle it
    if "field" in field_def:
        # Ensure that 'data' is a list or collection of fields
        if isinstance(data, list):
            for field in data:
                # Check if the current item in the list is a dictionary with the matching key
                if isinstance(field, dict) and match_on in field:
                    if field[match_on] == field_def['field']:
                        # If there is a 'subfield', we need to drill down further
                        if "subfield" in field_def:
                            subfield_data = field.get(field_def['subfield'], [])
                            if subfield_data:
                                # Handle the 'extract' definitions
                                if "extract" in field_def:
                                    extracted_items = []
                                    for item in subfield_data:
                                        item_data = {}
                                        for subfield_name, subfield_def in field_def['extract'].items():
                                            # For nested paths in subfields, adjust the path
                                            subfield_def_relative = subfield_def.copy()
                                            subfield_def_relative['path'] = subfield_def.get('path', '')
                                            value = extract_field(item, subfield_def_relative)
                                            item_data[subfield_name] = value
                                        extracted_items.append(item_data)
                                    return extracted_items
                                else:
                                    return subfield_data
                            else:
                                logging.info(f"No data found for subfield '{field_def['subfield']}' in field '{field_def['field']}'.")
                                return []
                        else:
                            # Extract the 'Value' or 'Values' from the field
                            return extract_value(field, field_def)
            # If we didn't find the field, return None
            logging.warning(f"Field '{field_def['field']}' not found in data.")
            return None
        else:
            logging.warning(f"Expected a list for field '{field_def['field']}' but got {type(data)}")
            return None
    else:
        # If no 'field' key, return data
        return data

def extract_value(field, field_def):
    value = None
    if 'Value' in field:
        value = field['Value']
    elif 'Values' in field and field['Values']:
        # Extract all values and join them if necessary
        values = [v.get('Value', '') for v in field['Values']]
        value = ', '.join(values)
    else:
        value = None

    # Parse JSON if needed
    if field_def.get('parse_json') and value:
        try:
            value = json.loads(value)
        except json.JSONDecodeError as e:
            logging.warning(f"Could not parse JSON value: {e}")
            value = None

    # Convert to appropriate type if specified
    if value is not None and 'type' in field_def:
        value = convert_type(value, field_def['type'])

    return value

def convert_type(value, type_str):
    try:
        if type_str == 'int':
            return int(value)
        elif type_str == 'float':
            return float(value)
        elif type_str == 'date':
            # Adjust the date format as needed
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError) as e:
        logging.warning(f"Could not convert value '{value}' to type '{type_str}': {e}")
        return value  # Return the original value if conversion fails

    return value

def extract_data(data, html_json):
    extracted = {}
    for field_name, field_def in html_json['fields_to_extract'].items():
        extracted[field_name] = extract_field(data, field_def)
    return extracted
 
def path_to_file_url(path):
    return Path(path).as_uri()

def download_file(url, dest_folder, file_name):
    # Remove invalid characters from file_name
    valid_file_name = re.sub(r'[<>:"/\\|?*]', '', file_name)

    response = requests.get(url)
    if response.status_code == 200:
        try:
            file_path = os.path.join(dest_folder, valid_file_name)
            with open(file_path, 'wb') as file:
                file.write(response.content)
            return file_path
        except Exception as e:
            print()
            print(f"    WARNING: Unable to open file: {file_path}")
            print()
    else:
        return 0

def process_single_form(form_id, input_dir, output_dir, x, process_name, max_form, args):
    global skipped_forms, skipped_downloads
    try:
        # Check if API limit has been reached
        if api_limit_reached.is_set():
            return False  # Stop processing

        # Get or create the thread's database connection and cursor
        if not hasattr(thread_local, 'cnx'):
            thread_local.cnx = database.setup()
            thread_local.cursor = thread_local.cnx.cursor()
        cnx = thread_local.cnx
        cursor = thread_local.cursor

        # Get the form data from Cube
        data = api.fetch_form(form_id)

        # Error handling
        error_message = data.get("Result", {}).get("Error", {}).get("Message")
        if error_message:
            if error_message == "API daily limit reached":
                with lock:
                    print(f"\n        ERROR: {error_message}. FormID: {form_id}")
                    api_limit_reached.set()  # Set the event to signal other threads
                return False  # Stop processing this form
            else:
                with lock:
                    print(f"\n        WARNING: {error_message}. FormID: {form_id}")
                    skipped_forms.append(form_id)
                return False  # Skip this form but continue processing others
        else:
            # Proceed with processing
            started_datetime = datetime.strptime(
                data["Result"]["Form"]["Started"], "%Y-%m-%d %H:%M:%S"
            )
            year = started_datetime.year
            month = started_datetime.month

            # Determine sheet name
            if max_form > 5000:
                sheet = f"{year}-{month}"
            else:
                sheet = str(year)

            form_number = data["Result"]["Form"]["Number"].replace('/', '').replace('"', '').strip()

            # Save JSON response
            form_dir = os.path.join(output_dir, form_number)
            os.makedirs(form_dir, exist_ok=True)
            json_filename = os.path.normpath(os.path.join(form_dir, f"{form_number}.json"))
            with open(json_filename, 'w') as json_file:
                json.dump(data, json_file, indent=4)

            # Save attachments
            if "Files" in data["Result"]["Form"]:
                for file in data["Result"]["Form"]["Files"]:
                    file_url = api.fetch_file_url(file["FileID"])
                    local_file_path = download_file(file_url, form_dir, file["FileName"])

                    # Check if download was successful
                    if local_file_path == 0:
                        with lock:
                            skipped_downloads.append(form_id)

            # Add Table of Contents entry to Report file
            if os.path.exists(os.path.join(input_dir, "toc.json")):
                toc_df = excel.dataframe(data, form_number, os.path.join(input_dir, "toc.json"))
                with lock:
                    excel.append(os.path.join(output_dir, 'Process.xlsx'), toc_df, f"{sheet} TOC")

            # Add form data to Report file
            if os.path.exists(os.path.join(input_dir, "report.json")):
                report_df = excel.dataframe(data, form_number, os.path.join(input_dir, "report.json"))
                with lock:
                    excel.append(os.path.join(output_dir, 'Process.xlsx'), report_df, sheet)

            # HTML report
            if os.path.exists(os.path.join(input_dir, "html.json")):
                # Load HTML definitions file
                with open(os.path.join(input_dir, "html.json"), 'r') as config_file:
                    html_config = json.load(config_file)

                # Extract data
                extracted_data = extract_data(data, html_config)

                # Load HTML template file
                html_template_path = os.path.join(input_dir, 'layout.html')
                with open(html_template_path, 'r') as html_file:
                    html_template = html_file.read()

                # Render the HTML
                css_content = ''
                with open(os.path.join(settings['assets'], 'stylesheet.css'), 'r') as css_file:
                    css_content = css_file.read()

                logo_path = os.path.abspath(os.path.join(settings['assets'], 'logo.png'))
                logo_url = path_to_file_url(logo_path)

                # Set up Jinja2 template
                template = env.from_string(html_template)

                # Configure file links
                files_html_relative = ""
                files_html_full = ""
                if "Files" in data["Result"]["Form"]:
                    for file in data["Result"]["Form"]["Files"]:
                        # Local file path
                        local_file_path = os.path.join(form_dir, file["FileName"])
                        file_url = path_to_file_url(local_file_path)

                        if file["FileName"].lower().endswith('.pdf'):
                            files_html_relative += (
                                f'<p><a href="{file_url}" target="_blank">{file["FileName"]}</a></p>'
                            )
                        else:
                            files_html_relative += (
                                f'<p><img src="{file_url}" alt="{file["FileName"]}" '
                                f'style="max-width: 200px;"></p>'
                            )

                        # SharePoint path (if not --nocloud)
                        if not args.nocloud:
                            full_url_path = urljoin(
                                settings['sharepoint'],
                                f'{process_name}/{x[1]}/{form_number}/{file["FileName"]}'
                            )

                            if file["FileName"].lower().endswith('.pdf'):
                                files_html_full += (
                                    f'<p><a href="{full_url_path}" target="_blank">'
                                    f'{file["FileName"]}</a></p>'
                                )
                            else:
                                files_html_full += (
                                    f'<p><img src="{full_url_path}" alt="{file["FileName"]}" '
                                    f'style="max-width: 200px;"></p>'
                                )

                # Render HTML with relative paths
                html_content_relative = template.render(
                    css_content=css_content,
                    logo_url=logo_url,
                    files_html=files_html_relative,
                    **extracted_data
                )

                # Define file paths
                html_filename = os.path.join(form_dir, f"report_{form_number}.html")
                pdf_filename = os.path.join(form_dir, f"report_{form_number}.pdf")

                # Write HTML to a file
                with open(html_filename, "w") as html_file:
                    html_file.write(html_content_relative)

                # Convert HTML to PDF
                options = {'enable-local-file-access': True}
                pdfkit.from_file(
                    html_filename, pdf_filename, configuration=pdfkit_config, options=options
                )

                # Re-render HTML for SharePoint (if not --nocloud)
                if not args.nocloud:
                    # Render HTML with full URL paths
                    html_content_full = template.render(
                        css_url=urljoin(settings['sharepoint_assets'], 'stylesheet.css'),
                        logo_url=urljoin(settings['sharepoint_assets'], 'logo.png'),
                        files_html=files_html_full,
                        **extracted_data
                    )

                    # Write the HTML with full URL paths to a file
                    with open(html_filename, "w") as html_file:
                        html_file.write(html_content_full)

            # Mark the form as completed in the database
            with lock:
                database.form_complete(cursor, form_id, cnx)
                cnx.commit()

        return True  # Indicate success

    except Exception as e:
        with lock:
            print(f"\n        ERROR processing form {form_id}: {e}")
            skipped_forms.append(form_id)
        return False  # Indicate failure

def main(args):
    global settings
    global pdfkit_config
    global skipped_processes, skipped_downloads, skipped_forms

    print("#############################")
    print("#  Cube Export Tool v1.0    #")
    print("#  Created by: Ryan Louden  #")
    print("#############################")
    print("")

    # Set up database connection
    try:
        print("Creating database connection...")
        cnx = database.setup()
        cursor = cnx.cursor()
        print("OK")
        print("")
    except Exception as e:
        print(f"Unhandled database exception: {e}")
        sys.exit(1)

    print("Synchronizing Cube indexes...")
    sleep(1)

    # Only run sync operations if --nosync is not used
    if not args.nosync:
        sync_groups(cursor, settings['api_urls']['groups'], cnx)
        sync_processes(cursor, settings['api_urls']['processes'], cnx)

        if args.sync:
            sync_forms(cursor, settings['api_urls']['forms'], cnx, args.sync)
        else:
            sync_forms(cursor, settings['api_urls']['forms'], cnx)
    else:
        print("Sync operations skipped due to --nosync flag.")

    print("")
    print("Getting list of processes to export...")

    # Get the list of processes
    processes = database.process_list(cursor)
    print(f"Found {len(processes)} processes.")

    print("")

    print("Definition files detected for the following Processes...")
    for x in processes:
        if os.path.exists(os.path.join(os.getcwd(), str(x[0]))):
            print(f"    {x[1]} ({x[0]})")

    print("")
    sleep(5)

    print("Exporting forms...")

    # Execute each process export script
    y = 1
    z = len(processes)
    for x in processes:
        input_dir = os.path.join(os.getcwd(), str(x[0]))  # Path to JSON definition files
        process_name = database.group_name(cursor, x[2])

        # Create output directory
        try:
            output_dir = os.path.join(
                settings['files'],
                process_name,
                x[1].replace('/', '').replace('"', '').strip()
            )
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory for form export: {e}")
            continue

        if os.path.exists(input_dir) and not glob.glob(os.path.join(output_dir, '*.xlsx')):
            # Clear completed status for the process
            database.process_reset(cursor, x[0], cnx)
            cnx.commit()
            print("    Definitions have been added to process, resetting form statuses")

        # Get list of relevant forms for this process including export status
        form_ids = database.form_fetch(cursor, x[0])

        # Count number of forms
        max_form = len(form_ids)
        if max_form == 0:
            continue  # Skip if no forms to process

        # Initialize progress bar
        progress_bar = tqdm(total=max_form, desc=f"    ({y} of {z}) {x[1]}")

        try:
            # Process forms using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=settings['max_workers']) as executor:
                futures = {
                    executor.submit(
                        process_single_form,
                        form_id,
                        input_dir,
                        output_dir,
                        x,
                        process_name,
                        max_form,
                        args
                    ): form_id for form_id in form_ids
                }

                for future in as_completed(futures):
                    form_id = futures[future]
                    try:
                        result = future.result()
                        # Update progress bar if form processed successfully
                        if result:
                            progress_bar.update(1)
                        # Check if API limit has been reached
                        if api_limit_reached.is_set():
                            print("\nAPI daily limit reached. Stopping further processing.")
                            break  # Exit the processing loop
                    except Exception as exc:
                        print(f'\n        Form {form_id} generated an exception: {exc}')
                        with lock:
                            skipped_forms.append(form_id)

                # After breaking the loop, cancel any pending futures
                if api_limit_reached.is_set():
                    print("API limit reached.  Shutting down.")
                    for future in futures:
                        if not future.done():
                            future.cancel()

                    # Shutdown the executor immediately
                    executor.shutdown(wait=False)
                    break  # Exit the outer process loop if desired

        except KeyboardInterrupt:
            print("\nKeyboardInterrupt received, shutting down...")
            executor.shutdown(wait=False)
            sys.exit(1)

        # Close progress bar
        progress_bar.close()

        y += 1

        # Check if API limit has been reached to exit outer loop
        if api_limit_reached.is_set():
            break

    print("OK!")
    print("")

    # Print skipped processes
    if skipped_processes:
        print(f"Skipped the following processes due to lack of permission:")
        for x in skipped_processes:
            print(f"Process ID: {x}")
            print()

    # Print skipped downloads
    if skipped_downloads:
        print("Skipped downloads that were corrupt")
        for x in skipped_downloads:
            print(f"FormID: {x}")
            print()

    # Print skipped forms
    if skipped_forms:
        print("Skipped forms that were deleted:")
        for x in skipped_forms:
            print(f"FormID: {x}")
            print()

    # Close database connection
    print("Closing database connection...")
    cursor.close()
    cnx.close()
    print("OK!")

    print("")
    print("Goodbye!")

if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Sync data between API and database")
    parser.add_argument(
        '--nocloud',
        action='store_true',
        help="This will not create exports for SharePoint Online"
    )
    parser.add_argument(
        '--nosync',
        action='store_true',
        help="Skip syncing groups and processes"
    )
    parser.add_argument(
        '--sync',
        type=str,
        help="Sync only ONE process. Specify the ProcessID"
    )
    args = parser.parse_args()

    main(args)
