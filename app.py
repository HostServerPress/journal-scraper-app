# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO

# --- All of our perfected data extraction and scraping functions ---
# --- (These are all included and require no changes) ---
def extract_journal_name(soup):
    journal_meta = soup.find('meta', attrs={'name': 'citation_journal_title'})
    if journal_meta: return journal_meta['content']
    og_site_name = soup.find('meta', property='og:site_name')
    if og_site_name: return og_site_name['content']
    return "Journal Name Not Found"

def extract_paper_title(soup):
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title['content'] != extract_journal_name(soup): return og_title['content']
    citation_title = soup.find('meta', attrs={'name': 'citation_title'})
    if citation_title: return citation_title['content']
    h1_tag = soup.find('h1')
    if h1_tag: return h1_tag.get_text(strip=True)
    return "Paper Title Not Found"

def extract_full_authors(soup):
    authors = soup.find_all('meta', attrs={'name': 'citation_author'})
    if authors:
        author_list = [author['content'] for author in authors]
        return ", ".join(author_list)
    return "Authors Not Found"

def extract_publication_date(soup):
    try:
        published_label = soup.find('strong', string=re.compile(r'Published:'))
        if published_label:
            container_text = published_label.find_parent().get_text(strip=True)
            match = re.search(r'([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})', container_text)
            if match:
                month_full = match.group(1).capitalize()
                year = match.group(3)
                return {'year': year, 'month': month_full[:3]}
    except Exception: pass
    date_meta = soup.find('meta', attrs={'name': 'citation_publication_date'})
    if date_meta:
        date_str = date_meta['content']
        parts = date_str.split('/')
        year = parts[0]
        month_num = int(parts[1]) if len(parts) > 1 else 1
        month_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month_num - 1]
        return {'year': year, 'month': month_abbr}
    return {'year': "Year Not Found", 'month': None}

def extract_type(soup):
    try:
        section_label = soup.find(string=re.compile(r'Section', re.I))
        if section_label:
            value_element = section_label.find_parent().find_next_sibling()
            if value_element:
                return value_element.get_text(strip=True)
    except Exception: pass
    return "Type Not Found"

def extract_volume(soup):
    volume_tag = soup.find('meta', attrs={'name': 'citation_volume'})
    issue_tag = soup.find('meta', attrs={'name': 'citation_issue'})
    vol = volume_tag['content'] if volume_tag else None
    iss = issue_tag['content'] if issue_tag else None
    if vol and iss: return f"{vol}({iss})"
    elif vol: return vol
    return "Volume Not Found"

def extract_page(soup):
    first_page = soup.find('meta', attrs={'name': 'citation_firstpage'})
    last_page = soup.find('meta', attrs={'name': 'citation_lastpage'})
    if first_page and last_page: return f"{first_page['content']}–{last_page['content']}"
    return "Page Not Found"

def extract_abstract(soup):
    og_desc = soup.find('meta', property='og:description')
    if og_desc: return og_desc['content']
    abstract_heading = soup.find(['h2', 'h3'], string=re.compile(r'^\s*Abstract\s*$', re.I))
    if abstract_heading:
        abstract_content = abstract_heading.find_next_sibling('div')
        if abstract_content: return abstract_content.get_text(separator=' ', strip=True)
    return "Abstract Not Found"

def extract_keywords(soup):
    keywords_meta = soup.find('meta', attrs={'name': 'citation_keywords'})
    if keywords_meta: return keywords_meta['content'].replace(';', ',')
    return "Keywords Not Found"

def extract_doi(soup):
    doi_meta = soup.find('meta', attrs={'name': 'citation_doi'})
    if doi_meta: return doi_meta['content']
    return "DOI Not Found"

def generate_apa_citation(data):
    try:
        authors = data['Full Authors']
        author_list = authors.split(', ')
        if len(author_list) > 1:
            authors_apa = ", ".join(author_list[:-1]) + ", & " + author_list[-1]
        else: authors_apa = authors
        parts = [authors_apa + ".", f"({data['Year Published']}).", data['Paper Title'] + "."]
        journal_info = f"{data['Journal Name']}, {data['Volume']}"
        if data['Page'] != "Page Not Found": journal_info += f", {data['Page']}"
        parts.append(journal_info + ".")
        parts.append(f"https://doi.org/{data['raw_doi']}")
        return " ".join(parts)
    except (KeyError, TypeError): return "APA Citation could not be generated (missing data)."

def generate_ieee_citation(data):
    try:
        authors_ieee = data['Full Authors'].replace(",", " and", 1)
        vol_match = re.search(r'(\d+)\((\d+)\)', data['Volume'])
        if vol_match:
            vol, iss = vol_match.group(1), vol_match.group(2)
            journal_part = f"{data['Journal Name']}, vol. {vol}, no. {iss},"
        else: journal_part = f"{data['Journal Name']}, vol. {data['Volume']},"
        parts = [f'{authors_ieee},', f'"{data["Paper Title"]},"', journal_part]
        if data['Page'] != "Page Not Found": parts.append(f"pp. {data['Page']},")
        if data['month'] and data['Year Published']: parts.append(f"{data['month']}. {data['Year Published']},")
        parts.append(f"doi: {data['raw_doi']}.")
        return " ".join(parts)
    except (KeyError, TypeError): return "IEEE Citation could not be generated (missing data)."

def scrape_website(url):
    st.write(f"  - Scraping article: {url}")
    headers = {'User-Agent': 'My-DOI-Scraper-Bot/1.0'}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        date_info = extract_publication_date(soup)
        raw_doi = extract_doi(soup)
        scraped_data = {
            'Website Link': url, 'Journal Name': extract_journal_name(soup), 'Paper Title': extract_paper_title(soup),
            'Full Authors': extract_full_authors(soup), 'Year Published': date_info['year'],
            'Volume': extract_volume(soup), 'Type': extract_type(soup), 'Page': extract_page(soup),
            'Abstract': extract_abstract(soup), 'Keywords': extract_keywords(soup),
            'DOI/Link Updated': f"https://doi.org/{raw_doi}" if raw_doi != "DOI Not Found" else "DOI Not Found",
            'Remarks': ''
        }
        scraped_data['month'] = date_info['month']; scraped_data['raw_doi'] = raw_doi
        scraped_data['APA Citation'] = generate_apa_citation(scraped_data); scraped_data['Citation IEEE'] = generate_ieee_citation(scraped_data)
        st.write(f"  - ✓ Success: {scraped_data['Paper Title']}")
        return scraped_data
    except Exception as e:
        st.warning(f"  - ✗ FAILED to scrape {url}. Error: {e}"); return None

def discover_article_links(toc_url):
    st.info(f"Discovering links from: {toc_url}")
    headers = {'User-Agent': 'My-DOI-Scraper-Bot/1.0'}
    try:
        response = requests.get(toc_url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        selector = 'div.article-summary.media h3.media-heading a'
        article_links = [a['href'] for a in soup.select(selector)]
        if not article_links: st.warning("  - No article links found."); return []
        st.success(f"  - Found {len(article_links)} article links.")
        return article_links
    except Exception as e:
        st.error(f"FAILED to load the Table of Contents page. Error: {e}"); return []

# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Journal Data Extractor", layout="wide")
st.title("Journal Data Extractor")
st.markdown("""
Welcome to the Journal Data Extractor! This tool is designed to streamline the process of collecting academic information from journal websites. 
- **Two Powerful Modes:** Scrape data by either uploading an Excel file containing a list of URLs, or by pasting one or more 'Table of Contents' links directly.
- **Accumulate Data:** Add multiple batches of articles to a single session. The results are combined for you.
- **Validate DOIs:** Use the built-in validator to check if the scraped DOIs correctly lead to the article webpage.
- **Download Everything:** Export your complete, cleaned, and numbered dataset to a single Excel file at any time.
""")

# Initialize all session state variables
if 'all_results' not in st.session_state: st.session_state.all_results = []
if 'summary_file_upload' not in st.session_state: st.session_state.summary_file_upload = {}
if 'summary_paste_url' not in st.session_state: st.session_state.summary_paste_url = {}

def process_links(links_to_process):
    newly_scraped_results = []
    failed_links = []
    skipped_count = 0
    scraped_urls = {item['Website Link'] for item in st.session_state.all_results}
    unique_new_links = list(dict.fromkeys(links_to_process))
    for link in unique_new_links:
        if link in scraped_urls:
            skipped_count += 1
            continue
        if "/issue/view/" in link:
            discovered = discover_article_links(link)
            if not discovered:
                failed_links.append(f"(Volume Link) {link}")
                continue
            for art_link in discovered:
                if art_link in scraped_urls:
                    skipped_count += 1
                    continue
                result = scrape_website(art_link)
                if result: 
                    newly_scraped_results.append(result)
                    scraped_urls.add(art_link)
                else: failed_links.append(art_link)
        else:
            result = scrape_website(link)
            if result:
                newly_scraped_results.append(result)
                scraped_urls.add(link)
            else: failed_links.append(link)
    st.session_state.all_results.extend(newly_scraped_results)
    return {"success": len(newly_scraped_results), "failed_links": failed_links, "skipped": skipped_count}

def display_summary(summary):
    if not summary: return
    st.markdown("---")
    st.subheader("Summary of Last Operation")
    st.success(f"Batch processing complete! Successfully scraped {summary['success']} new article(s).")
    if summary['failed_links']:
        st.warning(f"⚠️ {len(summary['failed_links'])} URL(s) failed to scrape.")
        with st.expander("Show Failed URLs"):
            for url in summary['failed_links']: st.write(url)

# --- UI Tabs ---
# --- IMPROVEMENT: Reordered tabs to put User Manual first ---
tab1, tab2, tab3, tab4 = st.tabs(["User Manual", "Upload Excel File", "Paste Volume URLs", "DOI Validator"])

with tab1:
    st.header("How to Use This Tool")
    st.markdown("""
    This guide explains how to use the different features of the Journal Data Extractor.

    ### **Collecting Data**
    You can collect data in two ways. You can use both methods in the same session, and all results will be combined.

    **1. Upload Excel File Tab**
    *   **Purpose:** Process a large number of links at once from a file.
    *   **Instructions:**
        *   Create an Excel file (`.xlsx` or `.xls`).
        *   In the first column, use the exact header `Website Link`.
        *   Paste all your URLs in this column. You can mix single article links and "Volume" / "Full Issue" links.
        *   Upload the file and click "Generate from Excel File".

    **2. Paste Volume URLs Tab**
    *   **Purpose:** Quickly scrape one or more full journal issues.
    *   **Instructions:**
        *   Find the "Volume" or "Full Issue" page for the journal volumes you want to scrape.
        *   Paste one or more of these URLs into the text box. Each URL must be on a new line.
        *   Click "Generate from Pasted URLs".

    ### **Validating Data**
    After you have scraped some articles, you can check if their DOIs are correct.

    **DOI Validator Tab**
    *   **Purpose:** Check if the DOI for each article correctly leads to the article's webpage.
    *   **Instructions:**
        *   After scraping data, go to this tab.
        *   Click the "Validate DOIs..." button.
        *   The tool will add a status (`✔️ Match`, `⚠️ Mismatch / 📄 PDF`, `❌ Error`.) to the "Remarks" column for every row in the results table below.

    ### **Viewing and Downloading Results**
    All your results are collected at the bottom of the page.

    **Combined Results Table**
    *   **Filtering:** Use the "Filter by DOI Status" dropdown to easily find articles that matched, were PDFs, or had errors. This is very useful after running the validator.
    *   **Downloading:** Click the "Download All Data as Excel" button at any time to save a complete, numbered, and sorted Excel file of all the articles you have collected in your session.
    *   **Resetting:** Click the "Reset and Clear All Data" button to clear the results table and start a completely new session.
    """)

with tab2:
    st.header("Mode 1: Process an Excel file of URLs")
    st.info("Your Excel file must contain a column with the exact header: `Website Link`")
    uploaded_file = st.file_uploader("Choose an Excel file", type=['xlsx', 'xls'])
    if uploaded_file is not None:
        if st.button("Generate from Excel File"):
            df = pd.read_excel(uploaded_file)
            if 'Website Link' not in df.columns:
                st.error("Upload failed. The Excel file must have a column named 'Website Link'.")
            else:
                links = df['Website Link'].dropna().tolist()
                with st.expander("Show Live Scraping Log", expanded=True):
                    st.write(f"Found {len(links)} links to process from the file.")
                    st.session_state.summary_file_upload = process_links(links)
    display_summary(st.session_state.summary_file_upload)

with tab3:
    st.header("Mode 2: Paste Volume/Issue URLs")
    toc_urls_input = st.text_area("Paste one or more URLs here (one per line):", height=150)
    if st.button("Generate from Pasted URLs"):
        links = [url.strip() for url in toc_urls_input.split('\n') if url.strip()]
        if not links:
            st.warning("Please paste at least one URL.")
        else:
            with st.expander("Show Live Scraping Log", expanded=True):
                st.write(f"Found {len(links)} links to process.")
                st.session_state.summary_paste_url = process_links(links)
    display_summary(st.session_state.summary_paste_url)

with tab4:
    st.header("DOI Link Validator")
    st.info("This tool will check the 'DOI/Link Updated' for every row in the 'Combined Results Table' and add a validation status to the 'Remarks' column.")
    if not st.session_state.all_results:
        st.warning("There is no data in the results table to validate. Please scrape some articles first.")
    else:
        if st.button(f"Validate DOIs for all {len(st.session_state.all_results)} articles"):
            progress_bar = st.progress(0)
            with st.spinner("Validating... This may take a while."):
                for i, row in enumerate(st.session_state.all_results):
                    original_url = row['Website Link']
                    doi_url = row['DOI/Link Updated']
                    remark = "❓ Not Checked"
                    try:
                        response = requests.head(doi_url, allow_redirects=True, timeout=10)
                        if response.status_code == 404:
                            remark = "❌ Not Found (404)"
                        elif 'application/pdf' in response.headers.get('Content-Type', ''):
                            remark = "📄 PDF"
                        else:
                            final_url = response.url
                            norm_final = final_url.replace('https://', '').replace('http://', '').replace('www.', '').strip('/')
                            norm_orig = original_url.replace('https://', '').replace('http://', '').replace('www.', '').strip('/')
                            if norm_final == norm_orig:
                                remark = "✔️ Match"
                            else:
                                remark = "⚠️ Mismatch"
                    except requests.exceptions.RequestException:
                        remark = "❌ Link Error"
                    st.session_state.all_results[i]['Remarks'] = remark
                    progress_bar.progress((i + 1) / len(st.session_state.all_results))
            st.success("Validation complete! The 'Remarks' column in the results table has been updated.")
            st.rerun()

st.markdown("---")
st.header("Combined Results Table")

if not st.session_state.all_results:
    st.info("No data has been scraped yet. The results table will appear here.")
else:
    df = pd.DataFrame(st.session_state.all_results)
    
    # --- IMPROVEMENT: Updated Filter Logic ---
    filter_option = st.selectbox(
        "Filter by DOI Status:",
        ["All", "✔️ Match", "⚠️ Mismatch / PDF", "❌ Error"]
    )

    if filter_option == "All":
        filtered_df = df
    elif filter_option == "✔️ Match":
        filtered_df = df[df['Remarks'] == '✔️ Match']
    elif filter_option == "⚠️ Mismatch / PDF":
        filtered_df = df[df['Remarks'].str.contains('Mismatch|PDF', na=False)]
    elif filter_option == "❌ Error":
        filtered_df = df[df['Remarks'].str.contains('Not Found|Error', na=False)]

    st.write(f"**Total unique articles collected so far:** {len(st.session_state.all_results)}")
    st.dataframe(filtered_df, column_config={
        "Website Link": st.column_config.LinkColumn(),
        "DOI/Link Updated": st.column_config.LinkColumn()
    })
    
    df_to_download = pd.DataFrame(st.session_state.all_results).copy()
    df_to_download['Year Published'] = pd.to_numeric(df_to_download['Year Published'], errors='coerce')
    df_to_download.sort_values(by=['Year Published', 'Journal Name', 'Volume'], inplace=True, kind='mergesort')
    df_to_download['No_Y'] = df_to_download.groupby('Year Published').cumcount() + 1
    df_to_download['No_J'] = df_to_download.groupby(['Journal Name', 'Volume']).cumcount() + 1
    final_column_order = [
        'No_Y', 'No_J', 'Journal Name', 'Year Published', 'Volume', 'Type', 'Page', 
        'Paper Title', 'Full Authors', 'Abstract', 'Keywords', 'DOI/Link Updated', 
        'Remarks', 'APA Citation', 'Citation IEEE', 'Website Link'
    ]
    df_final_download = df_to_download.reindex(columns=final_column_order)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final_download.to_excel(writer, index=False, sheet_name='ScrapedData')
    
    st.download_button(
        label="Download All Data as Excel",
        data=output.getvalue(),
        file_name="scraped_journal_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if st.button("Reset and Clear All Data"):
    st.session_state.all_results = []; st.session_state.summary_file_upload = {}; st.session_state.summary_paste_url = {}
    st.success("All collected data has been cleared. You can start a new session.")
    st.rerun()
