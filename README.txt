Description:
	This script will make copies of every Cube record in your system.  By default, it will export every record's JSON data and any attachments that were saved.  However, you can create definition files for your processes to also extract data to Excel and PDF.

	The MySQL database is used to keep track of which forms have already been exported, to reduce API consumption and handle scenarios where more than 40,000 forms exist (the daily limit of Cube's API).

Important Notes:
	Deleting the "Processes.xlsx" file inside an export folder will reset the completion status of that process and re-render all of the forms for the process.  This is by design for when you add or change definition files for the process.

Pre-Requisites:
	1. Python3
	2. MySQL (recommend using XAMPP stack which includes PHPMyAdmin)
	3. Python libraries in requirements.txt file
	4. PDFKit - wkhtmltopdf.org
	
Installation:
	1. Install pre-requisites
	2. Copy this repository to location on your computer (eg. C:\lighthouse)
	2. Create an API key for Lighthouse
	3. Create a new MySQL database and import the schema from schema.sql
	4. Set the variables in config.json for your environment
	
Usage:
	Command Line Arguments:
	--nocloud
		This will skip steps of creating SharePoint friendly HTML renderings.  Use this if you don't intend to copy the final output to a Document repository in SharePoint Online.
	
	--nosync
		This will skip the step of synchronising the list of forms in Cube with the local database.  Use this if you simply want to re-render existing information (eg. Adding new definition files).
		
	--sync *
		This will sync the groups, processes and the forms for ONE process.  Replace * with the ProcessID number.  The ProcessID can be found in Cube's JSON output file.
		
		Example:
		"main.py --sync 406"
			This will sync all of the forms for ProcessID 406
				
	Definition Files:
		Inside of the folder with "main.py", add a folder that is titled as ProcessID number for which you want to create HTML, PDF, and Excel sheets for.
		The following files can be added to this folder depending on what you would like to create.
		
		HTML & PDF's
			html.json
				This extracts the field and values you would like to use in your layout.html file.  A layout.html file is required for this, and I don't think I wrote an error handler if you forget to add one.
				
			layout.html
				This provides the layout to use for your HTML and PDF files.  These are commonly taken from existing print layouts inside Cube and modified for the "Jinja2" library format.
		
		Excel Sheets
			toc.json
				This will create a spreadsheet called "Process.xlsx" with a sheet called "0 - Table of Contents".  You then populate this json file with what you would like on the Table of Contents.  You can use this to summarize all of the data in a form.  For example, the replicate the default view of a process.
				
			report.json
				This will create a spreadsheet called "Process.xlsx" with a sheet for each year (or year and month if more than 5000 forms).  You then populate this JSON file with what you would like included.  Use this include detailed information of each process.