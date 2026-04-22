from bs4 import BeautifulSoup

# Mock HTML content representing the YouTube page
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Deep Dive into LLMs like ChatGPT</title>
    <meta name="description" content="A comprehensive breakdown on Large Language Models (LLMs) and ChatGPT.">
    <meta itemprop="uploadDate" content="2026-04-21">
</head>
<body>
    <!-- Mock of other HTML content -->
</body>
</html>
"""

def parse_youtube_metadata(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract title
    title = soup.find('title').text.strip() if soup.find('title') else "Untitled"

    # Extract description
    description_tag = soup.find('meta', {'name': 'description'})
    description = description_tag['content'] if description_tag else "No description available"

    # Extract upload date
    upload_date_tag = soup.find('meta', {'itemprop': 'uploadDate'})
    upload_date = upload_date_tag['content'] if upload_date_tag else "Unknown upload date"

    return {
        'title': title,
        'description': description,
        'upload_date': upload_date
    }

# Use the function and display the result
metadata = parse_youtube_metadata(html_content)
print(metadata)