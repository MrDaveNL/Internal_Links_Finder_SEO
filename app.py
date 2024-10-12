from flask import Flask, request, render_template, redirect, url_for, send_file
import pandas as pd
import requests
from urllib.parse import quote, urlparse, urlunparse
import re
import csv
import nltk
from bs4 import BeautifulSoup
import os

# Initialize Flask app
app = Flask(__name__)

# Download NLTK sentence tokenizer if not already downloaded
nltk.download('punkt')

# Define the function for sentence tokenization
def sentence_tokenizer(text):
    if not isinstance(text, str):
        return []
    sentence_endings = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_endings.split(text.strip())
    return sentences

# Define function to normalize URLs
def normalize_url(url):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if (scheme == 'http' and parsed.port == 80) or (scheme == 'https' and parsed.port == 443):
        netloc = netloc.split(':')[0]
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    path = parsed.path.rstrip('/')
    normalized = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized

# Define function to extract unlinked keywords
def find_unlinked_keywords(source_url, body_text, keywords_list):
    normalized_source_url = normalize_url(source_url)
    sentences = sentence_tokenizer(body_text)
    results = []
    for sentence in sentences:
        sentence_stripped = sentence.strip()

        if not re.search(r'[.!?]$', sentence_stripped) or re.match(r'^#+\s', sentence_stripped):
            continue
        if sentence_stripped.startswith('**') and sentence_stripped.endswith('**'):
            continue
        if sentence_stripped.startswith('*') and sentence_stripped.endswith('*'):
            continue
        if re.search(r'\[([^\]]+)\]\([^\)]+\)', sentence_stripped):
            continue

        sentence_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', sentence_stripped)

        for keyword, target_url in keywords_list:
            normalized_target_url = normalize_url(target_url)

            if normalized_source_url == normalized_target_url:
                continue

            if re.search(rf'\b{re.escape(keyword)}\b', sentence_clean, re.IGNORECASE):
                results.append({
                    'Source URL': source_url,
                    'Sentence': sentence_stripped,
                    'Keyword': keyword,
                    'Target URL': target_url
                })
    return results

@app.route('/')
def upload_files():
    return render_template('upload.html')

@app.route('/process', methods=['POST'])
def process_files():
    if 'urls_file' not in request.files or 'keywords_file' not in request.files:
        return "No file part"

    urls_file = request.files['urls_file']
    keywords_file = request.files['keywords_file']

    if urls_file.filename == '' or keywords_file.filename == '':
        return "No selected file"

    # Read the CSV files
    df = pd.read_csv(urls_file, encoding='utf-8-sig', header=None)
    keywords_df = pd.read_csv(keywords_file, header=None)

    # Assuming the columns in keywords.csv are: target_url, keyword
    keywords_list = keywords_df[[1, 0]].values.tolist()

    # Initialize lists to store final results
    source_urls = []
    body_texts = []
    all_results = []

    # Iterate over each URL and get body content
    for idx, url in enumerate(df[0]):
        url = url.strip()
        try:
            response = requests.get(url)
            response.raise_for_status()

            # Use BeautifulSoup to parse the HTML content and extract text
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
        except requests.exceptions.RequestException as e:
            text = f"Error: {e}"

        source_urls.append(url)
        body_texts.append(text)

        # Search for unlinked keywords
        results = find_unlinked_keywords(url, text, keywords_list)
        all_results.extend(results)

    # Save the results to CSV
    if all_results:
        results_df = pd.DataFrame(all_results)
        results_df = results_df.rename(columns={
            'Source URL': 'source_url',
            'Sentence': 'sentence/paragraph',
            'Keyword': 'link_text',
            'Target URL': 'target_url'
        })

        output_filename = 'unlinked_keywords.csv'
        results_df.to_csv(output_filename, index=False)
        return send_file(output_filename, as_attachment=True)
    else:
        return "No unlinked keywords found."

if __name__ == "__main__":
    app.run(debug=True)
