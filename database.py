import config
import mysql.connector
import sys

# Load settings file
settings = config.load()

def setup():
    global settings
    
    try:
        db_settings = {
            'user': settings['sql_user'],
            'password': settings['sql_pass'],
            'host': settings['sql_host'],
            'database': settings['sql_database']
        }
        cnx = mysql.connector.connect(**db_settings)
    except Exception as e:
        print(f"Error connecting to SQL database: {e}")
        sys.exit(1)
        
    return cnx

# Function to insert data into groups table
def group_insert(cursor, group, cnx):
    try:
        if not group_exists(cursor, group["GroupID"]):
            insert_group_query = "INSERT INTO groups (ID, Name) VALUES (%s, %s)"
            group_data = (group["GroupID"], group["Group"].replace('/', '').replace('"', '').strip())
            cursor.execute(insert_group_query, group_data)
            cnx.commit()  # Commit after inserting
    except Exception as e:
        print(f"Error inserting group into database - {group['Group']}: {e}")
        raise  # Raising the exception allows higher-level code to handle it properly

# Function to return name of group for a ProcessID
def group_name(cursor, proc_id):
    query = "SELECT Name FROM groups WHERE ID = %s LIMIT 1"
    cursor.execute(query, (proc_id,))
    result = cursor.fetchone()
    
    return result[0] if result else "Unsorted"

# Function to get list of forms for a process
def form_fetch(cursor, proc_id):
    query = "SELECT Form FROM forms WHERE ProcessID = %s AND Completed = 0"
    cursor.execute(query, (proc_id,))
    return [form_id[0] for form_id in cursor.fetchall()]

# Function to update the database to set Completed to 1
def form_complete(cursor, form_id, cnx):
    update_query = "UPDATE forms SET Completed = 1 WHERE Form = %s"
    cursor.execute(update_query, (form_id,))
    cnx.commit()  # Commit after updating the form status

# Function to check if a record exists in the forms table
def form_exists(cursor, process_id, form_id):
    check_query = "SELECT COUNT(*) FROM forms WHERE ProcessID = %s AND Form = %s"
    cursor.execute(check_query, (process_id, form_id))
    return cursor.fetchone()[0] > 0

# Function to insert data into forms table
def form_insert(cursor, process_id, form, cnx):
    try:
        if not form_exists(cursor, process_id, form["ID"]):
            insert_form_query = """
            INSERT INTO forms (ProcessID, Form, Archived)
            VALUES (%s, %s, %s)
            """
            form_data = (
                process_id, form["ID"], form["Archived"]
            )
            cursor.execute(insert_form_query, form_data)
            cnx.commit()
    except Exception as e:
        print(f"Error adding form in SQL: {e}")
        raise
        
        
# Function to check if a record exists in the processes table
def process_exists(cursor, proc_id):
    try:
        check_query = "SELECT COUNT(*) FROM processes WHERE ProcessID = %s"
        cursor.execute(check_query, (proc_id,))
        return cursor.fetchone()[0] > 0
    except Exception as e:
        print(f"Error checking process existence: {e}")
        raise

# Function to get name of a process
def process_name(cursor, proc_id):
    try:
        query = "SELECT Process FROM processes WHERE ProcessID = %s"
        cursor.execute(query, (proc_id,))
        return cursor.fetchone()[0]
    except Exception as e:
        print(f"Error getting name of process from SQL: {e}")
        raise

# Function to get name of a process
def process_status(cursor, proc_id):
    try:
        query = "SELECT Enabled FROM processes WHERE ProcessID = %s"
        cursor.execute(query, (proc_id,))
        return cursor.fetchone()[0]
    except Exception as e:
        print(f"Error getting name of process from SQL: {e}")
        raise

# Function to get list of processes
def process_list(cursor):
    try:
        cursor.execute("SELECT ProcessID, Process, GroupID FROM processes WHERE Enabled = 1 ORDER BY ProcessID ASC")
        results = cursor.fetchall()
        return [list(row) for row in results]
    except Exception as e:
        print(f"Error getting specific process from SQL: {e}")
        raise

# Function to get a specific process
def process_specific(cursor, proc_id):
    try:
        query = "SELECT ProcessID, Process, GroupID FROM processes WHERE ProcessID = %s AND Enabled = 1 ORDER BY ProcessID ASC"
        cursor.execute(query, (proc_id,))
        results = cursor.fetchall()
        return [list(row) for row in results]
    except Exception as e:
        print(f"Error getting list of processes from SQL: {e}")
        raise

# Resets completion status of all forms in a process to 0    
def process_reset(cursor, proc_id, cnx):
    try:
        query = "UPDATE forms SET Completed = 0 WHERE ProcessID = %s"
        cursor.execute(query, (proc_id,))
        cnx.commit()  # Commit after resetting the process status
    except Exception as e:
        print(f"Error updating process status to zero: {e}")
        raise

# Function to insert data into processes table
def process_insert(cursor, proc, cnx):
    try:
        if not process_exists(cursor, proc["ProcessID"]):
            insert_proc_query = """
                INSERT INTO processes 
                (ProcessID, Process, Enabled, Added, Modified, Forms, Archived, Fields, GroupID, RepeatingFields) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            proc_data = (
                proc["ProcessID"], proc["Process"], proc["Enabled"], proc["Added"], proc["Modified"], 
                proc["Forms"], proc["Archived"], proc["Fields"], proc["GroupID"], proc["RepeatingFields"]
            )
            cursor.execute(insert_proc_query, proc_data)
            cnx.commit()  # Commit after inserting
    except Exception as e:
        print(f"Error updating process table in SQL: {e}")
        raise

# Function to check if a record exists in the groups table
def group_exists(cursor, group_id):
    try:
        check_query = "SELECT COUNT(*) FROM groups WHERE ID = %s"
        cursor.execute(check_query, (group_id,))
        return cursor.fetchone()[0] > 0
    except Exception as e:
        print(f"Error checking if record exists in SQL: {e}")
        raise
