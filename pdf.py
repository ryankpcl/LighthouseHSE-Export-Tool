import config
import pdfkit

#Load settings file
settings = config.load()

def config():
    global settings
    
    path_wkhtmltopdf = config['wkhtmltopdf']
    pdfkit_config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    return pdfkit_config

def generate_pdf(html_content, output_path, pdfkit_config):
    pdfkit.from_string(html_content, output_path, configuration=pdfkit_config)