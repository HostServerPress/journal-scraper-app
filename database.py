# database.py
import os
import streamlit as st
import pandas as pd
from datetime import date
import libsql_client

# --- MODIFIED: The get_db_connection function is updated ---
def get_db_connection():
    """
    Establishes a connection to the database.
    If running on Streamlit Cloud, it connects to Turso.
    Otherwise, it connects to a local SQLite file.
    """
    if "TURSO_DATABASE_URL" in st.secrets:
        url = st.secrets["TURSO_DATABASE_URL"]
        
        # --- THIS IS THE FIX ---
        # We replace the 'libsql' scheme with 'https', which is more compatible
        # with the underlying HTTP libraries used for the WebSocket handshake.
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
            
        auth_token = st.secrets["TURSO_AUTH_TOKEN"]
        conn = libsql_client.create_client_sync(url=url, auth_token=auth_token)
    else:
        # Fallback to a local file for local development
        url = "journal_data.db"
        conn = libsql_client.create_client_sync(url=url)
    
    return conn

def initialize_database():
    """Creates the 'articles' table if it doesn't already exist."""
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            "Website Link" TEXT PRIMARY KEY,
            "Journal Name" TEXT,
            "Paper Title" TEXT,
            "Full Authors" TEXT,
            "Year Published" TEXT,
            "Volume" TEXT,
            "Type" TEXT,
            "Page" TEXT,
            "Abstract" TEXT,
            "Keywords" TEXT,
            "DOI/Link Updated" TEXT,
            "APA Citation" TEXT,
            "Citation IEEE" TEXT,
            "Remarks" TEXT,
            "last_validated" TEXT
        )
    ''')
    conn.close()

def add_or_update_article(data_dict):
    """Inserts a new article or replaces an existing one."""
    conn = get_db_connection()
    conn.execute(
        statement='''
            INSERT OR REPLACE INTO articles (
                "Website Link", "Journal Name", "Paper Title", "Full Authors", "Year Published",
                "Volume", "Type", "Page", "Abstract", "Keywords", "DOI/Link Updated",
                "APA Citation", "Citation IEEE", "Remarks"
            ) VALUES (:link, :journal, :title, :authors, :year, :volume, :type, :page, :abstract, :keywords, :doi, :apa, :ieee, :remarks)
        ''',
        args={
            "link": data_dict.get('Website Link'), "journal": data_dict.get('Journal Name'),
            "title": data_dict.get('Paper Title'), "authors": data_dict.get('Full Authors'),
            "year": data_dict.get('Year Published'), "volume": data_dict.get('Volume'),
            "type": data_dict.get('Type'), "page": data_dict.get('Page'),
            "abstract": data_dict.get('Abstract'), "keywords": data_dict.get('Keywords'),
            "doi": data_dict.get('DOI/Link Updated'), "apa": data_dict.get('APA Citation'),
            "ieee": data_dict.get('Citation IEEE'), "remarks": data_dict.get('Remarks', '❓ Not Checked')
        }
    )
    conn.close()

def get_all_articles_df():
    """Retrieves all articles and returns them as a DataFrame."""
    conn = get_db_connection()
    try:
        rs = conn.execute("SELECT * FROM articles")
        # Convert the result set to a list of dictionaries, then to a DataFrame
        if not rs.rows:
            return pd.DataFrame() # Return empty dataframe if no rows
        df = pd.DataFrame.from_records([dict(row) for row in rs.rows])
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def update_article_remark(link, remark):
    """Updates the remark and validation date for a specific article."""
    conn = get_db_connection()
    today = date.today().isoformat()
    conn.execute(
        'UPDATE articles SET "Remarks" = ?, "last_validated" = ? WHERE "Website Link" = ?',
        [remark, today, link]
    )
    conn.close()

def get_unchecked_articles_df():
    """Gets only articles that have never been checked."""
    conn = get_db_connection()
    try:
        rs = conn.execute("SELECT * FROM articles WHERE Remarks = '❓ Not Checked'")
        if not rs.rows:
            return pd.DataFrame() # Return empty dataframe if no rows
        df = pd.DataFrame.from_records([dict(row) for row in rs.rows])
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def delete_articles_by_link(links_to_delete):
    """Deletes a list of articles from the database."""
    if not links_to_delete: return
    conn = get_db_connection()
    # Create placeholders for the query
    placeholders = ', '.join(['?'] * len(links_to_delete))
    conn.batch_execute([
        {"stmt": f'DELETE FROM articles WHERE "Website Link" IN ({placeholders})', "args": links_to_delete}
    ])
    conn.close()

def clear_all_data():
    """Deletes all records from the articles table."""
    conn = get_db_connection()
    conn.execute('DELETE FROM articles')
    conn.close()
