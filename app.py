# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO
import docx

# --- Import and initialize the database ---
import database as db
db.initialize_database()

# --- All data extraction and citation functions (unchanged) ---
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

def format_authors(author_string, style='apa'):
    if not author_string or author_string == "Authors Not Found": return "Authors Not Found"
    author_list = author_string.split(', ')
    formatted_names = []
    for name in author_list:
        parts = name.split()
        if not parts: continue
        last_name = parts[-1]
        first_initials = [p[0] + '.' for p in parts[:-1]]
        if style == 'apa': formatted_names.append(f"{last_name}, {' '.join(first_initials)}")
        elif style == 'ieee': formatted_names.append(f"{' '.join(first_initials)} {last_name}")
    if not formatted_names: return "Authors Not Found"
    if style == 'apa':
        return ", ".join(formatted_names[:-1]) + ", & " + formatted_names[-1] if len(formatted_names) > 1 else formatted_names[0]
    elif style == 'ieee':
        return " and ".join(formatted_names)

def generate_apa_citation(data):
    try:
        authors_apa = format_authors(data['Full Authors'], style='apa')
        parts = [authors_apa + ".", f"({data['Year Published']}).", data['Paper Title'] + "."]
        journal_info = f"{data['Journal Name']}, {data['Volume']}"
        if data['Page'] != "Page Not Found": journal_info += f", {data['Page']}"
        parts.append(journal_info + ".")
        parts.append(f"https://doi.org/{data['raw_doi']}")
        return " ".join(parts)
    except (KeyError, TypeError): return "APA Citation could not be generated (missing data)."

def generate_ieee_citation(data):
    try:
        authors_ieee = format_authors(data['Full Authors'], style='ieee')
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

st.set_page_config(page_title="Journal Data Extractor", layout="wide")
st.title("Journal Data Extractor")
st.markdown("""
Welcome to the Journal Data Extractor! This tool is designed to streamline the process of collecting academic information from journal websites.
- **Two Powerful Modes:** Scrape data by either uploading an Excel file of URLs or by pasting 'Volume/Full Issues' links directly.
- **Persistent Data & Auto-Updates:** Your collection is saved locally. Submitting a link that already exists will automatically re-scrape and update it.
- **Download Everything:** Export your complete, cleaned, and numbered dataset to a single Excel file.
""")

if 'summary_file_upload' not in st.session_state: st.session_state.summary_file_upload = {}
if 'summary_paste_url' not in st.session_state: st.session_state.summary_paste_url = {}
if 'data_editor_key' not in st.session_state: st.session_state.data_editor_key = 0

def process_links(links_to_process):
    newly_scraped_count, updated_count, failed_links = 0, 0, []
    existing_df = db.get_all_articles_df()
    scraped_urls = set(existing_df['Website Link']) if not existing_df.empty else set()
    unique_new_links = list(dict.fromkeys(links_to_process))
    for link in unique_new_links:
        is_update = link in scraped_urls
        if "/issue/view/" in link:
            discovered = discover_article_links(link)
            if not discovered:
                failed_links.append(f"(Volume Link) {link}")
                continue
            for art_link in discovered:
                is_update_discovered = art_link in scraped_urls
                result = scrape_website(art_link)
                if result:
                    db.add_or_update_article(result)
                    if is_update_discovered: updated_count += 1
                    else: newly_scraped_count += 1
                    scraped_urls.add(art_link)
                else: failed_links.append(art_link)
        else:
            result = scrape_website(link)
            if result:
                db.add_or_update_article(result)
                if is_update: updated_count += 1
                else: newly_scraped_count += 1
                scraped_urls.add(link)
            else: failed_links.append(link)
    return {"new": newly_scraped_count, "updated": updated_count, "failed_links": failed_links}

def display_summary(summary):
    if not summary: return
    st.markdown("---")
    st.subheader("Summary of Last Operation")
    st.success(f"Processing complete! Scraped {summary['new']} new article(s) and updated {summary['updated']} existing one(s).")
    if summary['failed_links']:
        st.warning(f"⚠️ {len(summary['failed_links'])} URL(s) failed to scrape.")
        with st.expander("Show Failed URLs"):
            for url in summary['failed_links']: st.write(url)

# --- Sidebar with Search and Filter options ---
st.sidebar.header("Search and Filter")
base_df_for_sidebar = db.get_all_articles_df()
if not base_df_for_sidebar.empty:
    unique_journals = sorted(base_df_for_sidebar['Journal Name'].unique())
    unique_journals.insert(0, "All Journals")
    journal_select = st.sidebar.selectbox("Select Journal Name (exact match):", unique_journals)
else:
    journal_select = "All Journals"

journal_search = st.sidebar.text_input("Filter Journal Name (contains...):")
year_search = st.sidebar.text_input("Filter by Year Published:")

# --- Main app tabs ---
tab1, tab2, tab3, tab4 = st.tabs(["User Manual", "Upload File", "Paste Volume URLs", "DOI Validator"])
with tab1:
    st.header("How to Use This Tool")
    st.markdown("""
    This guide explains how to use the different features of the Journal Data Extractor.

    ### **Collecting Data**
    You can collect data in two ways. All data is saved automatically to a local database.

    **Automatic Updates:** If you submit a link that has been scraped before, the tool will **automatically re-scrape it** and update the entry in the database with the latest information. There is no need to delete the old one.

    **1. Upload File Tab**
    *   **Purpose:** Process a large number of links at once from a file.
    *   **Instructions:**
        *   **For Excel (.xlsx, .xls):** In the first column, use the exact header `Website Link`.
        *   **For Word (.docx) or Text (.txt):** Place each URL on a new line.
        *   You can mix single article links and "Volume" / "Full Issue" links in any file type.

    **2. Paste Volume URLs Tab**
    *   **Purpose:** Quickly scrape one or more full journal issues.
    *   **Instructions:**
        *   Find the "Volume" or "Full Issue" page for the journal volumes you want to scrape.
        *   Paste one or more of these URLs into the text box. Each URL must be on a new line.

    ### **Validating Data**
    *   The **DOI Validator** tab allows you to check all the links in your database.
    *   It updates the "Remarks" column to show if the DOI link matches the original article URL, leads to a PDF, is broken, or has an error.
    *   You have the option to check only new, un-validated articles or re-validate the entire database.

    ### **Viewing and Downloading Results**
    *   **Searching:** Use the sidebar on the left to search your entire database. You can select a journal from the dropdown for an exact match, or type in the text boxes to filter by journal name or year.
    *   **Editing & Deleting:** To delete rows, click the checkboxes on the far left of the results table to select them, then press the **Delete** key on your keyboard. This permanently removes them from the database.
    *   **Filtering:** Use the "Filter by DOI Status" dropdown to easily find articles that matched or had errors within your search results.
    *   **Downloading:** Click the "Download All Data as Excel" button to save a complete, numbered, and sorted Excel file of your entire database.
    *   **Resetting:** Click the "Reset and Clear All Data" button to completely wipe the database and start a new session.
    """)

with tab2:
    st.header("Mode 1: Process a file of URLs")
    st.info("For Excel, use a 'Website Link' column. For .docx or .txt, place each URL on a new line.")
    uploaded_file = st.file_uploader("Choose a file (.xlsx, .xls, .docx, or .txt)", type=['xlsx', 'xls', 'docx', 'txt'])
    if uploaded_file and st.button("Generate from File"):
        links = []
        try:
            if uploaded_file.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file)
                if 'Website Link' in df.columns: links = df['Website Link'].dropna().tolist()
                else: st.error("Excel file must have a column named 'Website Link'.")
            elif uploaded_file.name.endswith('.docx'):
                document = docx.Document(uploaded_file)
                links = [p.text.strip() for p in document.paragraphs if p.text.strip()]
            elif uploaded_file.name.endswith('.txt'):
                string_data = uploaded_file.getvalue().decode("utf-8")
                links = [line.strip() for line in string_data.split('\n') if line.strip()]
        except Exception as e: st.error(f"Error reading file: {e}")
        if not links: st.warning("No links were found in the uploaded file.")
        else:
            with st.expander("Show Live Scraping Log", expanded=True):
                st.write(f"Found {len(links)} links to process from the file.")
                st.session_state.summary_file_upload = process_links(links)
    display_summary(st.session_state.summary_file_upload)

with tab3:
    st.header("Mode 2: Paste Volume/Issue URLs")
    toc_urls_input = st.text_area("Paste one or more URLs here (one per line):", height=150)
    if st.button("Generate from Pasted URLs"):
        links = [url.strip() for url in toc_urls_input.split('\n') if url.strip()]
        if not links: st.warning("Please paste at least one URL.")
        else:
            with st.expander("Show Live Scraping Log", expanded=True):
                st.write(f"Found {len(links)} links to process.")
                st.session_state.summary_paste_url = process_links(links)
    display_summary(st.session_state.summary_paste_url)

with tab4:
    st.header("DOI Link Validator")
    st.info("Choose to validate only new articles or re-validate the entire database.")
    col1, col2 = st.columns(2)
    df_to_validate = pd.DataFrame()
    with col1:
        unchecked_articles = db.get_unchecked_articles_df()
        if st.button(f"Validate {len(unchecked_articles)} Un-checked Articles", disabled=unchecked_articles.empty):
            df_to_validate = unchecked_articles
    with col2:
        all_articles = db.get_all_articles_df()
        if st.button(f"Re-validate all {len(all_articles)} Articles", disabled=all_articles.empty):
            df_to_validate = all_articles
    if not df_to_validate.empty:
        st.write(f"Processing {len(df_to_validate)} articles for validation...")
        progress_bar = st.progress(0)
        total_articles = len(df_to_validate)
        with st.spinner("Validating... This may take a while."):
            for i, (index, row) in enumerate(df_to_validate.iterrows()):
                original_url, doi_url = row['Website Link'], row['DOI/Link Updated']
                remark = "❓ Not Checked"
                try:
                    response = requests.head(doi_url, allow_redirects=True, timeout=10)
                    if response.status_code == 404: remark = "❌ Not Found (404)"
                    elif 'application/pdf' in response.headers.get('Content-Type', ''): remark = "📄 PDF"
                    else:
                        norm_final = response.url.replace('https://','').replace('http://','').replace('www.','').strip('/')
                        norm_orig = original_url.replace('https://','').replace('http://','').replace('www.','').strip('/')
                        if norm_final == norm_orig: remark = "✔️ Match"
                        else: remark = "⚠️ Mismatch"
                except requests.exceptions.RequestException: remark = "❌ Link Error"
                db.update_article_remark(original_url, remark)
                progress_bar.progress((i + 1) / total_articles)
        st.success("Validation complete! The 'Remarks' column has been updated.")
        st.rerun()

st.markdown("---")
st.header("Combined Results Table")

base_df = db.get_all_articles_df()

if base_df.empty:
    st.info("No data has been scraped yet. The results table will appear here.")
else:
    searched_df = base_df.copy()
    
    if journal_select != "All Journals":
        searched_df = searched_df[searched_df['Journal Name'] == journal_select]
    if journal_search:
        searched_df = searched_df[searched_df['Journal Name'].str.contains(journal_search, case=False, na=False)]
    if year_search:
        searched_df = searched_df[searched_df['Year Published'].astype(str).str.contains(year_search, na=False)]
    
    filter_option = st.selectbox("Filter by DOI Status:", ["All", "✔️ Match", "⚠️ Mismatch / PDF", "❌ Error", "❓ Not Checked"])
    
    if filter_option == "All":
        filtered_df = searched_df
    else:
        status_map = {
            "✔️ Match": ['✔️ Match'], "⚠️ Mismatch / PDF": ['Mismatch', 'PDF'],
            "❌ Error": ['Not Found', 'Error'], "❓ Not Checked": ['❓ Not Checked']
        }
        search_terms = status_map.get(filter_option, [])
        pattern = '|'.join(map(re.escape, search_terms))
        if pattern:
             filtered_df = searched_df[searched_df['Remarks'].str.contains(pattern, na=False)]
        else:
             filtered_df = searched_df

    st.write(f"**Showing {len(filtered_df)} of {len(base_df)} total articles**")
    st.info("💡 **Tip:** To delete rows, select them using the checkboxes and press the 'Delete' key.")
    
    edited_df = st.data_editor(
        filtered_df,
        column_config={"Website Link": st.column_config.LinkColumn(), "DOI/Link Updated": st.column_config.LinkColumn()},
        num_rows="dynamic",
        key=f"editor_{st.session_state.data_editor_key}"
    )
    
    if len(edited_df) < len(filtered_df):
        original_links = set(filtered_df['Website Link'])
        remaining_links = set(edited_df['Website Link'])
        links_to_delete = list(original_links - remaining_links)
        db.delete_articles_by_link(links_to_delete)
        st.success(f"Deleted {len(links_to_delete)} row(s) from the database.")
        st.session_state.data_editor_key += 1
        st.rerun()
    
    df_to_download = db.get_all_articles_df().copy()
    if not df_to_download.empty:
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
    db.clear_all_data()
    st.session_state.summary_file_upload, st.session_state.summary_paste_url = {}, {}
    st.success("All collected data has been cleared from the database. You can start a new session.")
    st.rerun()
