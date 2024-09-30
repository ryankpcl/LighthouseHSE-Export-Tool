import pandas as pd
from openpyxl import load_workbook
import json
import os

# Helper function to get a nested value from a dictionary using a list of keys.
def get_nested_value(data, keys):
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, {})
        else:
            return ""  # If data is not a dict, return empty string
    return data if data else ""

# Helper function to flatten nested 'Rows' into a single string.
def flatten_rows(field_data, subfield, extract):
    flattened = []
    for row in field_data.get(subfield, []):
        parts = []
        for label, extract_info in extract.items():
            field_value = get_nested_value(row, [extract_info['path'], extract_info['field']])
            if field_value:
                parts.append(f"{label}: {field_value}")
        if parts:
            flattened.append(", ".join(parts))
    return "; ".join(flattened) if flattened else ""

def dataframe(data, form_number, json_file):
    # Load configuration from a file
    with open(json_file, 'r') as config_file:
        config = json.load(config_file)

    # Create a dictionary to hold the DataFrame's columns dynamically
    df_data = {}

    # Iterate over the configuration and dynamically populate the dictionary
    for column, path_config in config["columns"].items():
        try:
            # If we have a simple "path", handle it by splitting and retrieving the value.
            if isinstance(path_config, dict) and "path" in path_config and "field" not in path_config:
                keys = path_config["path"].split('.')
                # Extract the nested value using the keys
                df_data[column] = [get_nested_value(data, keys)]
            
            # If we have both "path" and "field", this means we're looking in the "Fields" array.
            elif isinstance(path_config, dict) and "path" in path_config and "field" in path_config:
                keys = path_config["path"].split('.')
                fields_data = get_nested_value(data, keys)
                field_name = path_config["field"]
                # Find the field by name and extract its value
                df_data[column] = [next((item["Value"] for item in fields_data if item["Field"] == field_name), "")]
            
            else:
                # Static value or direct form_number
                df_data[column] = [form_number] if path_config == "form_number" else [path_config]

        except KeyError:
            df_data[column] = [""]  # Handle missing fields with an empty string

    # Create and return the DataFrame
    df = pd.DataFrame(df_data)
    return df

# Function to append data to an Excel file or create a new one if it doesn't exist
def append(file_path, df, sheet_name='Sheet1'):
    # Check if the file already exists
    if os.path.exists(file_path):
        # Load the existing Excel workbook
        with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            # Try to load the existing data from the specified sheet
            try:
                existing_df = pd.read_excel(file_path, sheet_name=sheet_name)
                # Append the new data to the existing data
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                # Write the updated DataFrame back to the sheet
                combined_df.to_excel(writer, sheet_name=sheet_name, index=False)
            except ValueError:
                # If the sheet does not exist, simply create it
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        # If the file does not exist, create a new one with the new data
        with pd.ExcelWriter(file_path, engine='openpyxl', mode='w') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)